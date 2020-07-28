import os
import sys
import argparse
import json
import requests
import time
from math import ceil
from pprint import pprint
from tqdm import tqdm


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-name", required=True)
    parser.add_argument("--api-token", required=True)
    parser.add_argument("--console-id", type=int, required=True)
    parser.add_argument("--local-download-dir", default=".")
    parser.add_argument("--download-file-max-size", type=int, default=500 * 1024 * 1024)
    parser.add_argument("--download-urls-file", default="download_urls.txt")
    parser.add_argument("--download-urls", default="")
    args = parser.parse_args()

    user_name = args.user_name
    api_token = args.api_token
    console_id = args.console_id
    local_download_dir = args.local_download_dir
    download_file_max_size = args.download_file_max_size

    download_urls = []
    if os.path.exists(args.download_urls_file):
        download_urls += open(args.download_urls_file, "rt").readlines()
    if len(args.download_urls) > 0:
        download_urls += args.download_urls.split("\n")
    download_urls = [url.strip() for url in download_urls]
    download_urls = [url for url in download_urls if (len(url) > 0)]
    download_urls = [url for url in download_urls if (not url.startswith("#"))]
    download_urls = [(url.split("|")[0].strip(), url.split("|")[1].strip()) for url in download_urls]

    api_url_prefix = f"https://www.pythonanywhere.com/api/v0/user/{user_name}"
    request_kwargs = dict(headers={"Authorization": f"Token {api_token}"})
    remote_home_dir = f"/home/{user_name}"
    ok_file_path = f"{remote_home_dir}/OK.txt"
    command_output_file_path = f"{remote_home_dir}/command_output.txt"

    def check_response(response):
        if response.status_code != 200:
            raise RuntimeError(f"Unexpected status code {response.status_code}.")

    def get(url, params=None):
        response = requests.get(api_url_prefix + url, params=params, **request_kwargs)
        check_response(response)
        return response

    def post(url, data=None, json=None):
        response = requests.post(api_url_prefix + url, data=data, json=json, **request_kwargs)
        check_response(response)
        return response

    def remote_execute(command):
        response = post(f"/consoles/{console_id}/send_input/", json={"input": f"{command}\n"})
        time.sleep(1)

        return response

    def remote_get_content_length(url):
        content_length_file_path = f"{remote_home_dir}/content_length.txt"
        remote_execute(f"wget --spider --server-response {url} 2>&1 | grep Content-Length: | cut -b 19- >{content_length_file_path}")
        content_length = int(download_file(content_length_file_path, return_file_content=True))
        remote_execute(f"rm {content_length_file_path}")
        return content_length

    def remote_download_file(url, output_file_path=None, start_pos=0, max_size=download_file_max_size):
        remote_execute(f"ulimit -f {int(max_size / 1024)}; wget -O {output_file_path} --start-pos {start_pos} {url}; echo OK >{ok_file_path}")

        ok = False
        wait_count = 100
        for wait_index in range(wait_count):
            time.sleep(5)
            try:
                ok_ = download_file(ok_file_path)
            except RuntimeError as e:
                if "404" in str(e):
                    ok_ = False
                else:
                    raise e
            if ok_:
                ok = True
                print(f"\tOK.")
                break
            else:
                print(f"\t[{wait_index + 1}/{wait_count}] Waiting for OK.")
                continue

        if not ok:
            print(f"Not OK.")
            input("Press enter to continue")

        remote_execute(f"rm {ok_file_path}")

        return True

    def download_file(file_path, output_file_path=None, return_file_content=False):
        response = get(f"/files/path{file_path}")
        if output_file_path is not None:
            file = open(output_file_path, "wb")
            file.write(response.content)
        return True if not return_file_content else response.content

    def download_large_file(file_path, output_file_path, chunk_size=100 * 1024):
        url = api_url_prefix + f"/files/path{file_path}"

        os.system(f"wget -c -O {output_file_path} --header 'Authorization: Token {api_token}' {url}")

        return True

    def download_large_file_through_remote(url, file_name, start_pos=0, max_size=download_file_max_size, chunk_size=100 * 1024):
        remote_download_file(url, file_name, start_pos=start_pos, max_size=max_size)

        download_large_file(f"{remote_home_dir}/{file_name}", f"{local_download_dir}/{file_name}", chunk_size=chunk_size)

        remote_execute(f"rm {file_name}")

        return True

    def get_content(response):
        content = response.content
        try:
            content_str = content.decode(encoding="utf-8")
            try:
                content_json = json.loads(content_str)
                return content_json
            except Exception:
                return content_str
        except Exception:
            return content

    def print_get(url, params=None):
        response = get(url, params=params)
        content = get_content(response)
        print(f"[GET] {api_url_prefix + url}:")
        pprint(content)

    def print_post(url, data=None, json=None):
        response = post(url, data=data, json=json)
        content = get_content(response)
        print(f"[POST] {api_url_prefix + url}:")
        pprint(content)

    # print_get("/consoles/")
    # print_get(f"/consoles/{console_id}/")
    # print_get(f"/consoles/{console_id}/get_latest_output/")
    # remote_execute("ls")
    # remote_execute("wget https://s3.eu-central-1.amazonaws.com/avg-kitti/raw_data/2011_09_26_drive_0001/2011_09_26_drive_0001_sync.zip; echo OK >OK.txt")
    # remote_execute("rm OK.txt")
    # remote_execute("wget --spider --server-response https://s3.eu-central-1.amazonaws.com/avg-kitti/raw_data/2011_09_26_drive_0001/2011_09_26_drive_0001_sync.zip 2>&1 | grep "Content-Length:" | cut -b 19- >content_length.txt")
    # download_file(f"{remote_home_dir}/OK.txt", "OK.txt")
    # download_large_file(f"{remote_home_dir}/2011_09_26_drive_0001_sync.zip", "2011_09_26_drive_0001_sync.zip")

    for index, (download_url, file_name) in enumerate(download_urls):
        print(f"[{index + 1}/{len(download_urls)}] Downloading {download_url} ({file_name})")

        file_size = remote_get_content_length(download_url)
        print(f"\tFile size: {file_size}")

        if file_size < download_file_max_size:
            download_large_file_through_remote(download_url, file_name)
        else:
            split_count = ceil(file_size / download_file_max_size)
            print(f"\tSplit count: {split_count}")

            for split_index in range(split_count):
                print(f"\tDownloading split {split_index + 1}/{split_count}")
                download_large_file_through_remote(download_url, file_name + f".{split_index + 1:03d}", start_pos=download_file_max_size * split_index)

            # os.system(f"cat {' '.join([file_name + f'.{split_index + 1:03d}' for split_index in range(split_count)])} >{file_name}")
            # os.system(f"rm {file_name}.*")

    command = ""
    pwd = "~"
    while True:
        if command.startswith("cd "):
            remote_execute(f"pwd >{command_output_file_path}")
            pwd = download_file(command_output_file_path, return_file_content=True)
            pwd = pwd.decode(encoding="utf-8")
            pwd = pwd.replace(remote_home_dir, "~")
            pwd = pwd.strip()

        command = input(f"{user_name}@www.pythonanywhere.com:{pwd}$ ")

        if command in ["quit", "exit"]:
            break

        if command.endswith("[no-redirect]"):
            remote_execute(command)
        else:
            remote_execute(f"{command} >{command_output_file_path} 2>&1")
            command_output = download_file(command_output_file_path, return_file_content=True)
            try:
                command_output = command_output.decode(encoding="utf-8")
            except Exception:
                pass
            print(command_output)


if __name__ == '__main__':
    main()
