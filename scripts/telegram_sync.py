"""
@description: Telegram 消息同步脚本 - 手动拉取消息并处理
@dependencies: requests
@last_modified: 2026-03-17

使用方法:
    python scripts/telegram_sync.py --token YOUR_TOKEN

    或者设置环境变量:
    export TELEGRAM_BOT_TOKEN="your_token"
    python scripts/telegram_sync.py
"""

import argparse
import os
import sys
import json
import time
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import requests
except ImportError:
    print("请安装: pip install requests")
    sys.exit(1)


class TelegramSync:
    """Telegram 消息同步器"""

    def __init__(self, token: str, proxy: str = None):
        self.token = token
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.proxies = {"http": proxy, "https": proxy} if proxy else None
        self.last_update_id = 0
        self.messages_file = Path(__file__).parent.parent / ".ai-state" / "telegram_messages.jsonl"

    def get_updates(self, limit: int = 10) -> list:
        """获取更新"""
        url = f"{self.base_url}/getUpdates"
        params = {
            "offset": self.last_update_id + 1 if self.last_update_id else None,
            "limit": limit,
            "timeout": 0
        }

        try:
            response = requests.get(url, params=params, timeout=10, proxies=self.proxies)
            result = response.json()

            if result.get("ok"):
                updates = result.get("result", [])
                if updates:
                    self.last_update_id = updates[-1].get("update_id", 0)
                return updates
            else:
                print(f"获取失败: {result}")
        except Exception as e:
            print(f"连接错误: {e}")

        return []

    def send_message(self, chat_id: str, text: str) -> bool:
        """发送消息"""
        url = f"{self.base_url}/sendMessage"
        data = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }

        try:
            response = requests.post(url, json=data, timeout=10, proxies=self.proxies)
            result = response.json()
            return result.get("ok", False)
        except Exception as e:
            print(f"发送失败: {e}")
            return False

    def save_message(self, update: dict):
        """保存消息到文件"""
        self.messages_file.parent.mkdir(parents=True, exist_ok=True)

        with open(self.messages_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(update, ensure_ascii=False) + "\n")

    def process_message(self, update: dict) -> str:
        """处理消息，返回回复内容"""
        message = update.get("message", {})
        text = message.get("text", "")
        from_user = message.get("from", {})
        username = from_user.get("username", "unknown")
        first_name = from_user.get("first_name", "")

        print(f"[{datetime.now().strftime('%H:%M:%S')}] @{username}: {text}")

        # 保存消息
        self.save_message(update)

        # 生成回复
        if text.startswith("/"):
            return self.handle_command(text)
        else:
            return f"收到你的消息: {text}\n\n_我是 AI Agent 助手_"

    def handle_command(self, command: str) -> str:
        """处理命令"""
        commands = {
            "/start": "你好！我是 AI Agent 助手，可以帮你处理任务。\n\n发送任意消息与我互动。",
            "/help": "可用命令:\n/start - 开始对话\n/help - 显示帮助\n/status - 查看状态",
            "/status": f"状态: 在线\n时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n消息数: 已记录"
        }
        return commands.get(command.split()[0], "未知命令。发送 /help 查看可用命令。")

    def run_once(self) -> list:
        """单次拉取"""
        updates = self.get_updates()
        results = []

        for update in updates:
            message = update.get("message", {})
            chat_id = message.get("chat", {}).get("id")

            if chat_id and message.get("text"):
                reply = self.process_message(update)
                self.send_message(chat_id, reply)
                results.append({"chat_id": chat_id, "text": message.get("text"), "reply": reply})

        return results

    def run_forever(self, interval: int = 5):
        """持续轮询"""
        print(f"开始监听 Telegram 消息 (每 {interval} 秒检查一次)...")
        print("按 Ctrl+C 停止\n")

        try:
            while True:
                results = self.run_once()
                if results:
                    print(f"处理了 {len(results)} 条消息\n")
                time.sleep(interval)
        except KeyboardInterrupt:
            print("\n停止监听")


def main():
    parser = argparse.ArgumentParser(description="Telegram 消息同步")
    parser.add_argument("--token", "-t", help="Bot Token")
    parser.add_argument("--proxy", "-p", help="代理地址")
    parser.add_argument("--once", action="store_true", help="只拉取一次")
    parser.add_argument("--interval", "-i", type=int, default=5, help="轮询间隔(秒)")

    args = parser.parse_args()

    token = args.token or os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("请提供 Bot Token: --token YOUR_TOKEN")
        sys.exit(1)

    sync = TelegramSync(token, args.proxy)

    if args.once:
        results = sync.run_once()
        print(f"\n拉取完成，处理 {len(results)} 条消息")
    else:
        sync.run_forever(args.interval)


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
    main()