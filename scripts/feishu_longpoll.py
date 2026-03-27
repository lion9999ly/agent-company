"""
@description: 飞书长连接客户端 - WebSocket模式接收消息
@dependencies: websocket-client, requests
@last_modified: 2026-03-17

飞书长连接模式：
- 无需公网IP和ngrok
- 应用主动连接飞书服务器
- 适合内网环境

使用方法:
    python scripts/feishu_longpoll.py
"""

import os
import sys
import json
import time
import threading
import queue
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, Callable

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import requests
    import websocket
except ImportError:
    print("请安装: pip install requests websocket-client")
    sys.exit(1)


class FeishuLongPoll:
    """飞书长连接客户端"""

    def __init__(self, app_id: str = None, app_secret: str = None):
        self.app_id = app_id or os.getenv("FEISHU_APP_ID", "cli_a9326fa6ba389cc5")
        self.app_secret = app_secret or os.getenv("FEISHU_APP_SECRET", "PY4z2a8vPdNPuDWrjzm4zfk4olwHfIv7")
        self.base_url = "https://open.feishu.cn/open-apis"
        self.access_token = None
        self.token_expires = 0
        self.ws_url = None
        self.ws = None
        self.message_handlers: Dict[str, Callable] = {}
        self.running = False
        self.message_queue = queue.Queue()

    def get_tenant_access_token(self) -> str:
        """获取 tenant_access_token"""
        if self.access_token and time.time() < self.token_expires:
            return self.access_token

        url = f"{self.base_url}/auth/v3/tenant_access_token/internal"
        data = {
            "app_id": self.app_id,
            "app_secret": self.app_secret
        }

        try:
            response = requests.post(url, json=data, timeout=10)
            result = response.json()
            if result.get("code") == 0:
                self.access_token = result["tenant_access_token"]
                self.token_expires = time.time() + result["expire"] - 300
                return self.access_token
            else:
                print(f"获取token失败: {result}")
                return ""
        except Exception as e:
            print(f"获取token异常: {e}")
            return ""

    def get_websocket_url(self) -> str:
        """获取WebSocket连接地址"""
        token = self.get_tenant_access_token()
        if not token:
            return ""

        # 飞书长连接API
        url = f"{self.base_url}/callback/v2/websocket/getConnectionUrl"
        headers = {"Authorization": f"Bearer {token}"}

        try:
            response = requests.post(url, headers=headers, json={}, timeout=10)
            result = response.json()
            if result.get("code") == 0:
                self.ws_url = result.get("data", {}).get("url", "")
                return self.ws_url
            else:
                print(f"获取WebSocket URL失败: {result}")
                return ""
        except Exception as e:
            print(f"获取WebSocket URL异常: {e}")
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
            return result.get("code") == 0
        except Exception as e:
            print(f"发送消息失败: {e}")
            return False

    def on_message(self, ws, message):
        """收到消息回调"""
        try:
            data = json.loads(message)
            msg_type = data.get("type", "")

            if msg_type == "pong":
                # 心跳响应
                return

            if msg_type == "event":
                # 事件消息
                event = data.get("event", {})
                event_type = event.get("type", "")

                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 收到事件: {event_type}")

                if event_type == "im.message.receive_v1":
                    # 收到聊天消息
                    self._handle_chat_message(event)

        except Exception as e:
            print(f"解析消息异常: {e}")

    def _handle_chat_message(self, event: dict):
        """处理聊天消息"""
        try:
            message = event.get("message", {})
            sender = event.get("sender", {})

            msg_type = message.get("msg_type", "text")
            content = json.loads(message.get("content", "{}"))
            message_id = message.get("message_id", "")

            sender_id = sender.get("sender_id", {})
            open_id = sender_id.get("open_id", "")
            user_id = sender_id.get("user_id", "")

            print(f"  发送者: {open_id}")
            print(f"  消息类型: {msg_type}")

            if msg_type == "text":
                text = content.get("text", "")
                print(f"  内容: {text}")

                # 放入队列
                self.message_queue.put({
                    "type": "text",
                    "content": text,
                    "open_id": open_id,
                    "user_id": user_id,
                    "message_id": message_id
                })

                # 调用处理器
                handler = self.message_handlers.get("text")
                if handler:
                    reply = handler(text, open_id)
                    if reply:
                        self.send_message(open_id, reply)

            elif msg_type == "audio":
                # 语音消息
                file_key = content.get("file_key", "")
                print(f"  语音文件: {file_key}")
                self.message_queue.put({
                    "type": "voice",
                    "file_key": file_key,
                    "open_id": open_id,
                    "message_id": message_id
                })

            elif msg_type == "image":
                # 图片消息
                image_key = content.get("image_key", "")
                print(f"  图片: {image_key}")
                self.message_queue.put({
                    "type": "image",
                    "image_key": image_key,
                    "open_id": open_id,
                    "message_id": message_id
                })

        except Exception as e:
            print(f"处理消息异常: {e}")

    def on_error(self, ws, error):
        """错误回调"""
        print(f"WebSocket错误: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        """关闭回调"""
        print(f"WebSocket关闭: {close_status_code} - {close_msg}")
        self.running = False

    def on_open(self, ws):
        """连接成功回调"""
        print("WebSocket连接成功!")
        self.running = True

        # 启动心跳线程
        def heartbeat():
            while self.running:
                try:
                    ws.send(json.dumps({"type": "ping"}))
                    time.sleep(30)
                except:
                    break

        threading.Thread(target=heartbeat, daemon=True).start()

    def register_handler(self, msg_type: str, handler: Callable):
        """注册消息处理器"""
        self.message_handlers[msg_type] = handler

    def connect(self):
        """连接到飞书长连接服务"""
        ws_url = self.get_websocket_url()
        if not ws_url:
            print("获取WebSocket URL失败")
            return False

        print(f"正在连接飞书长连接服务...")

        self.ws = websocket.WebSocketApp(
            ws_url,
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close
        )

        return True

    def run(self):
        """运行长连接"""
        if not self.connect():
            return

        print("\n" + "=" * 50)
        print("飞书长连接已启动")
        print("=" * 50)
        print("现在可以在飞书中发送消息给机器人测试")
        print("按 Ctrl+C 停止")
        print("=" * 50 + "\n")

        # 默认处理器
        if "text" not in self.message_handlers:
            self.register_handler("text", self._default_handler)

        # 运行WebSocket
        self.ws.run_forever()

    def _default_handler(self, text: str, open_id: str) -> str:
        """默认消息处理器"""
        # 这里可以接入AI处理逻辑
        return f"收到你的消息: {text}\n\n我是AI Agent助手，正在等待接入智能处理..."


def main():
    print("=" * 50)
    print("飞书长连接客户端")
    print("=" * 50)

    client = FeishuLongPoll()

    # 测试连接
    token = client.get_tenant_access_token()
    if not token:
        print("ERROR: 获取token失败，请检查App ID和Secret")
        return

    print(f"Token: {token[:20]}...")

    # 运行长连接
    client.run()


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
    main()