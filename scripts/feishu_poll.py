"""
@description: 飞书HTTP长轮询客户端 - 简单可靠的接收消息方式
@dependencies: requests
@last_modified: 2026-03-17

使用方法:
    python scripts/feishu_poll.py

原理：定期调用飞书API拉取消息，无需配置公网URL
"""

import os
import sys
import json
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Callable
from queue import Queue

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import requests
except ImportError:
    print("请安装: pip install requests")
    sys.exit(1)


class FeishuPoll:
    """飞书消息轮询客户端"""

    def __init__(self, app_id: str = None, app_secret: str = None):
        self.app_id = app_id or os.getenv("FEISHU_APP_ID", "cli_a9326fa6ba389cc5")
        self.app_secret = app_secret or os.getenv("FEISHU_APP_SECRET", "PY4z2a8vPdNPuDWrjzm4zfk4olwHfIv7")
        self.base_url = "https://open.feishu.cn/open-apis"
        self.access_token = None
        self.token_expires = 0
        self.message_handlers: Dict[str, Callable] = {}
        self.message_queue = Queue()
        self.running = False

    def get_tenant_access_token(self) -> str:
        """获取 tenant_access_token"""
        if self.access_token and time.time() < self.token_expires:
            return self.access_token

        url = f"{self.base_url}/auth/v3/tenant_access_token/internal"
        data = {"app_id": self.app_id, "app_secret": self.app_secret}

        try:
            response = requests.post(url, json=data, timeout=10)
            result = response.json()
            if result.get("code") == 0:
                self.access_token = result["tenant_access_token"]
                self.token_expires = time.time() + result["expire"] - 300
                return self.access_token
        except Exception as e:
            print(f"获取token异常: {e}")
        return ""

    def send_message(self, receive_id: str, text: str, receive_id_type: str = "open_id") -> bool:
        """发送消息"""
        token = self.get_tenant_access_token()
        if not token:
            return False

        url = f"{self.base_url}/im/v1/messages?receive_id_type={receive_id_type}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        data = {
            "receive_id": receive_id,
            "msg_type": "text",
            "content": json.dumps({"text": text})
        }

        try:
            response = requests.post(url, headers=headers, json=data, timeout=10)
            result = response.json()
            if result.get("code") == 0:
                print(f"  [回复发送成功]")
                return True
            else:
                print(f"  [回复发送失败: {result.get('msg')}]")
        except Exception as e:
            print(f"发送消息异常: {e}")
        return False

    def get_user_info(self, user_id: str) -> dict:
        """获取用户信息"""
        token = self.get_tenant_access_token()
        if not token:
            return {}

        url = f"{self.base_url}/contact/v3/users/{user_id}?user_id_type=open_id"
        headers = {"Authorization": f"Bearer {token}"}

        try:
            response = requests.get(url, headers=headers, timeout=10)
            result = response.json()
            if result.get("code") == 0:
                return result.get("data", {}).get("user", {})
        except:
            pass
        return {}

    def get_chat_history(self, chat_id: str, page_size: int = 20) -> list:
        """获取会话历史消息"""
        token = self.get_tenant_access_token()
        if not token:
            return []

        url = f"{self.base_url}/im/v1/conversations/{chat_id}/messages?page_size={page_size}"
        headers = {"Authorization": f"Bearer {token}"}

        try:
            response = requests.get(url, headers=headers, timeout=10)
            result = response.json()
            if result.get("code") == 0:
                return result.get("data", {}).get("items", [])
        except:
            pass
        return []

    def get_bot_chats(self) -> list:
        """获取机器人的会话列表"""
        token = self.get_tenant_access_token()
        if not token:
            return []

        url = f"{self.base_url}/im/v1/chats?page_size=50"
        headers = {"Authorization": f"Bearer {token}"}

        try:
            response = requests.get(url, headers=headers, timeout=10)
            result = response.json()
            if result.get("code") == 0:
                return result.get("data", {}).get("items", [])
        except:
            pass
        return []

    def poll_messages(self, interval: float = 3.0):
        """轮询消息（后台线程）"""
        last_message_times: Dict[str, str] = {}

        print(f"开始轮询消息 (每{interval}秒检查一次)...")

        while self.running:
            try:
                # 获取会话列表
                chats = self.get_bot_chats()

                for chat in chats:
                    chat_id = chat.get("chat_id", "")
                    if not chat_id:
                        continue

                    # 获取会话最新消息
                    messages = self.get_chat_history(chat_id, page_size=5)

                    for msg in reversed(messages):  # 从旧到新处理
                        msg_id = msg.get("message_id", "")
                        create_time = msg.get("create_time", "")
                        sender_type = msg.get("sender", {}).get("sender_type", "")

                        # 跳过机器人自己发的消息
                        if sender_type == "app":
                            continue

                        # 检查是否是新消息
                        last_time = last_message_times.get(chat_id, "")
                        if create_time and create_time > last_time:
                            last_message_times[chat_id] = create_time

                            # 解析消息
                            msg_type = msg.get("msg_type", "")
                            content = json.loads(msg.get("body", {}).get("content", "{}"))
                            sender = msg.get("sender", {}).get("id", "")

                            if msg_type == "text":
                                text = content.get("text", "")
                                if text and last_time:  # 首次不打印历史消息
                                    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 新消息:")
                                    print(f"  会话: {chat.get('name', 'Unknown')}")
                                    print(f"  内容: {text}")

                                    # 调用处理器
                                    handler = self.message_handlers.get("text")
                                    if handler:
                                        reply = handler(text, sender)
                                        if reply:
                                            self.send_message(sender, reply)
                                    else:
                                        # 默认回复
                                        self.send_message(sender, f"收到: {text}")

                time.sleep(interval)

            except Exception as e:
                print(f"轮询异常: {e}")
                time.sleep(5)

    def register_handler(self, msg_type: str, handler: Callable):
        """注册消息处理器"""
        self.message_handlers[msg_type] = handler

    def run(self, interval: float = 3.0):
        """运行轮询"""
        # 测试连接
        token = self.get_tenant_access_token()
        if not token:
            print("ERROR: 获取token失败")
            return

        print("=" * 50)
        print("飞书消息轮询服务")
        print("=" * 50)
        print(f"Token: {token[:20]}...")
        print(f"轮询间隔: {interval}秒")
        print()

        # 获取会话列表
        chats = self.get_bot_chats()
        print(f"当前会话数: {len(chats)}")
        for chat in chats[:5]:
            print(f"  - {chat.get('name', 'Unknown')}")
        print()

        print("正在监听消息...")
        print("按 Ctrl+C 停止")
        print("=" * 50)

        self.running = True

        # 启动轮询线程
        poll_thread = threading.Thread(target=self.poll_messages, args=(interval,), daemon=True)
        poll_thread.start()

        # 主线程等待
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n停止服务")
            self.running = False


def main():
    client = FeishuPoll()
    client.run(interval=3.0)


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
    main()