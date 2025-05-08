# !/usr/bin/env python

import os
import argparse
import logging
from dingtalk_stream import AckMessage
import dingtalk_stream
import subprocess

def setup_logger():
    logger = logging.getLogger()
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(name)-8s %(levelname)-8s %(message)s [%(filename)s:%(lineno)d]"
        )
    )
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


def define_options():
    parser = argparse.ArgumentParser()
    # parser.add_argument(
    #     "--client_id",
    #     dest="client_id",
    #     required=True,
    #     help="app_key or suite_key from https://open-dev.digntalk.com",
    # )
    # parser.add_argument(
    #     "--client_secret",
    #     dest="client_secret",
    #     required=True,
    #     help="app_secret or suite_secret from https://open-dev.digntalk.com",
    # )
    options = parser.parse_args()
    return options


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


class EchoTextHandler(dingtalk_stream.ChatbotHandler):
    def __init__(self, logger: logging.Logger = None):
        super(dingtalk_stream.ChatbotHandler, self).__init__()
        if logger:
            self.logger = logger

    async def process(self, callback: dingtalk_stream.CallbackMessage):
        incoming_message = dingtalk_stream.ChatbotMessage.from_dict(callback.data)
        text = incoming_message.text.content.strip()
        self.reply_text(run_command(text), incoming_message)
        return AckMessage.STATUS_OK, "OK"


def main():
    logger = setup_logger()
    options = define_options()

    options.client_id = os.environ.get("DING_CLIENT_ID")
    options.client_secret = os.environ.get("DING_CLIENT_SECRET")

    credential = dingtalk_stream.Credential(options.client_id, options.client_secret)
    client = dingtalk_stream.DingTalkStreamClient(credential)
    client.register_callback_handler(
        dingtalk_stream.chatbot.ChatbotMessage.TOPIC, EchoTextHandler(logger)
    )
    client.start_forever()


if __name__ == "__main__":
    main()
