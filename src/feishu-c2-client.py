import requests
import json
import socket
from uuid import uuid4
import time
from requests_toolbelt import MultipartEncoder
import os
import hashlib
import subprocess
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
    out_file = os.path.join(server_info["tmp_dir"], "out.pack")

    # Check if last_out_hash exists in server_info
    if "last_out_hash" not in server_info:
        server_info["last_out_hash"] = None

    # Get current hash of out.pack
    current_out_hash = get_file_hash(out_file)

    # If out.pack changed, send it
    if current_out_hash and current_out_hash != server_info["last_out_hash"]:
        send_file(server_info, out_file)
        server_info["last_out_hash"] = current_out_hash


def list_files(path):
    try:
        return "\n".join(os.listdir(path))
    except FileNotFoundError:
        print("No such directory")
        return "Err: No such dir"


def get_active_users():
    stream = os.popen("w")
    stream.readline()
    stream.readline()  # get rid of a header and stats

    users = []
    for line in stream.readlines():
        splitted = line.split()
        users.append(splitted[0])
    return "\n".join(users)


def get_running_processes():
    stream = os.popen("ps")
    stream.readline()  # get rid of a header and stats

    processes = []
    for line in stream.readlines():
        splitted = line.split()
        processes.append(splitted[-1])
    return "\n".join(processes)


def get_local_ip():
    local_hostname = socket.gethostname()
    ip_addresses = socket.gethostbyname_ex(local_hostname)[2]
    filtered_ips = [ip for ip in ip_addresses if not ip.startswith("127.")] + [""]
    return ip_addresses, filtered_ips[0]

def run_command(command: str, timeout: int = 10) -> str:
    """
    执行shell命令并收集所有输出流，全部重定向到PIPE
    
    Args:
        command: 要执行的shell命令
        timeout: 超时时间(秒)，默认10秒
    
    Returns:
        str: 包含所有输出流的字符串(stdout + stderr)
    """
    try:
        # 创建子进程，重定向所有输出流到PIPE
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.PIPE,
            shell=True,
            universal_newlines=True,
            errors='replace'  # 处理无法解码的字符
        )

        # 等待进程完成，获取输出
        stdout, stderr = process.communicate(timeout=timeout)

        # 合并所有输出
        output = stdout + stderr

        return output
    except subprocess.TimeoutExpired as e:
        # 超时处理
        process.kill()
        stdout, stderr = process.communicate()
        return f"Command timed out after {timeout} seconds.\nPartial output:\n{stdout + stderr}"

    except Exception as e:
        # 其他异常处理
        return f"Error executing command: {str(e)}"


def get_user_ids(server_info):
    url = "https://open.feishu.cn/open-apis/contact/v3/users/batch_get_id?user_id_type=open_id"
    payload = json.dumps({"include_resigned": True, "mobiles": ADMIN})

    response = requests.request("POST", url, headers=server_info["headers"], data=payload).json()
    user_ids = [user["user_id"] for user in response["data"]["user_list"]]
    return user_ids

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
        item_data = json.loads(item["body"]["content"])
        if server_info.get(
            "last_message_time", 0
        ) >= int(item["create_time"]):
            continue
        elif item["sender"]["sender_type"] == "app":
            if not have_new_data and item_data.get("file_name", "") == "in.pack":
                have_new_data = True
                if item_data["file_key"] not in server_info["done_file_key"]:
                    save_file(server_info, item["message_id"], item_data["file_key"], item_data["file_name"])
                    server_info["done_file_key"].append(item_data["file_key"])

            if item["msg_type"] == "text" and item_data["text"].startswith("user:"):
                yield item_data["text"][len("user:"):]
        else:
            if item["msg_type"] == "text":
                yield item_data["text"]
            elif item["msg_type"] == "file":
                item_data["file_key"], item_data["file_name"]
                save_file(server_info, item["message_id"], item_data["file_key"], item_data["file_name"])
                send_text(server_info, f"File {item_data['file_name']} saved to {server_info['tmp_dir']}")

    server_info["last_message_time"] = int(response["data"]["items"][0]["create_time"])

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


def send_file(server_info, file_path):

    url = "https://open.feishu.cn/open-apis/im/v1/files"

    payload = {"file_type": "stream", "file_name": os.path.basename(file_path)}

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

    try:

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
    except:
        print(file_path)


def create_session(server_info):

    ips, ip = get_local_ip()

    url = "https://open.feishu.cn/open-apis/im/v1/chats?set_bot_manager=true&user_id_type=open_id"
    payload = json.dumps(
        {
            "bot_id_list": os.environ.get("FEISHU_BOT_ID_LIST"),
            "chat_mode": "group",
            "chat_type": "private",
            "description": "test",
            "edit_permission": "all_members",
            "group_message_type": "chat",
            "hide_member_count_setting": "all_members",
            "join_message_visibility": "all_members",
            "leave_message_visibility": "all_members",
            "membership_approval": "no_approval_required",
            "name": f"{ip} Server",
            "owner_id": os.environ.get("FEISHU_OWNER_ID"),
            "restricted_mode_setting": {
                "download_has_permission_setting": "all_members",
                "message_has_permission_setting": "all_members",
                "screenshot_has_permission_setting": "all_members",
                "status": False,
            },
            "urgent_setting": "all_members",
            "user_id_list": get_user_ids(server_info),
            "video_conference_setting": "all_members",
        }
    )

    response = requests.request("POST", url, headers=server_info["headers"], data=payload).json()

    server_info["chat_id"] = response["data"]["chat_id"]
    # server_info["tmp_dir"] = "/tmp/" + server_info["chat_id"]
    server_info["tmp_dir"] = "/tmp/chat/"
    os.makedirs(server_info["tmp_dir"], exist_ok=True)

    send_text(server_info, f"Server started on {ip}\n\nServer Info:\n{json.dumps(server_info, indent=2)}")
    send_text(server_info, "\n".join(ips))

    return response["data"]["chat_id"]


def delete_session(server_info):
    chat_id = server_info.get("chat_id")
    if chat_id:
        url = f"https://open.feishu.cn/open-apis/im/v1/chats/{chat_id}"
        r = requests.request("DELETE", url, headers=server_info["headers"], data="")
    server_info["chat_id"] = ""


def change_tmp_dir(server_info, tmp_dir):
    server_info["tmp_dir"] = tmp_dir
    os.makedirs(tmp_dir, exist_ok=True)

DIR_HTML = "<b>Directory Listing</b>\n<i>Dir: {}</i>\n<b>Items:</b>\n\n"
USR_HTML = "<b>Active Users Listing</b>\n<b>Users:</b>\n\n"
PCS_HTML = "<b>Running Processes Listing</b>\n<b>Processes:</b>\n\n"
WRT_HTML = "<b>Write Status: </b>"
OPT_HTML = "<b>Output: </b>\n\n"

def parse_payload(server_info, command):
    splitted = command.split(" ", 1)
    if splitted[0] == "ls" and len(splitted) >= 2:
        files = list_files(splitted[1])
        return DIR_HTML.format(splitted[1]) + files
    elif splitted[0] == "shell" and len(splitted) >= 2:
        return "shell_output:" + run_command(splitted[1])
    elif splitted[0] == "run" and len(splitted) >= 2:
        return OPT_HTML + run_command(splitted[1])
    elif splitted[0] == "users":
        return USR_HTML + get_active_users()
    elif splitted[0] == "processes":
        return PCS_HTML + get_running_processes()
    elif splitted[0] == "tmp_dir" and len(splitted) >= 2:
        change_tmp_dir(server_info, splitted[1])
        return "Ok"
    elif splitted[0] == "read" and len(splitted) >= 2:
        send_file(server_info, splitted[1])
        return "Ok"
    elif splitted[0] == "terminate" or splitted[0] == "done":
        return "terminate"


def update_server_info(server_info):
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"

    response = requests.request(
        "POST", url, json=server_info["app_info"]
    ).json()
    server_info["headers"]["Authorization"] = "Bearer " + response["tenant_access_token"]

server_info = {
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
    # print(server_info)
    # while True:
    #     print(get_messages(server_info))
    # delete_session(server_info)
    end = False
    while not end:
        try:
            update_id = -1
            for message in get_messages(server_info):

                response = parse_payload(server_info, message)

                if response == "terminate":
                    end = True
                    break

                send_text(server_info, response)

            sync_files(server_info)

            if not end:
                time.sleep(server_info["sleep_time"])
        except Exception as e:
            import traceback
            traceback.print_exc()
            # update_server_info(server_info)

    delete_session(server_info)
    
    # disable this in testing mode
    # shutil.rmtree(server_info["tmp_dir"])
    # os.remove(__file__)
