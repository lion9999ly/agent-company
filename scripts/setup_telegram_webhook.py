"""
@description: Telegram Webhook 设置脚本
@dependencies: requests
@last_modified: 2026-03-17

使用方法:
    # 方式1: 直接运行（需要网络通畅）
    python scripts/setup_telegram_webhook.py

    # 方式2: 使用代理
    python scripts/setup_telegram_webhook.py --proxy http://127.0.0.1:7890

    # 方式3: 打印手动设置URL
    python scripts/setup_telegram_webhook.py --print-url
"""

import argparse
import os
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import requests
except ImportError:
    print("请安装依赖: pip install requests")
    sys.exit(1)


def setup_webhook(token: str, webhook_url: str, proxy: str = None):
    """设置 Telegram Webhook"""

    url = f"https://api.telegram.org/bot{token}/setWebhook"
    data = {"url": webhook_url}

    proxies = None
    if proxy:
        proxies = {
            "http": proxy,
            "https": proxy
        }

    try:
        print(f"正在设置 Webhook...")
        print(f"Token: {token[:10]}...")
        print(f"Webhook URL: {webhook_url}")
        if proxy:
            print(f"使用代理: {proxy}")
        print()

        response = requests.post(url, json=data, timeout=30, proxies=proxies)
        result = response.json()

        if result.get("ok"):
            print("SUCCESS: Webhook 设置成功!")
            print(f"  - URL: {webhook_url}")
            print(f"  - 结果: {result.get('description', 'OK')}")
            return True
        else:
            print(f"ERROR: 设置失败")
            print(f"  - 错误: {result}")
            return False

    except Exception as e:
        print(f"ERROR: 连接错误 - {e}")
        return False


def get_webhook_info(token: str, proxy: str = None):
    """获取当前 Webhook 信息"""

    url = f"https://api.telegram.org/bot{token}/getWebhookInfo"
    proxies = {"http": proxy, "https": proxy} if proxy else None

    try:
        response = requests.get(url, timeout=30, proxies=proxies)
        result = response.json()

        if result.get("ok"):
            info = result.get("result", {})
            print("当前 Webhook 状态:")
            print(f"  - URL: {info.get('url', '未设置')}")
            print(f"  - 待处理更新数: {info.get('pending_update_count', 0)}")
            if info.get('last_error_date'):
                print(f"  - 最后错误时间: {info.get('last_error_date')}")
                print(f"  - 最后错误信息: {info.get('last_error_message')}")
        else:
            print(f"获取信息失败: {result}")
    except Exception as e:
        print(f"连接错误: {e}")


def get_ngrok_url():
    """获取 ngrok 公网 URL"""
    try:
        response = requests.get("http://127.0.0.1:4040/api/tunnels", timeout=5)
        data = response.json()
        if data.get("tunnels"):
            return data["tunnels"][0]["public_url"]
    except:
        pass
    return None


def main():
    parser = argparse.ArgumentParser(description="Telegram Webhook 设置工具")
    parser.add_argument("--token", "-t", help="Telegram Bot Token")
    parser.add_argument("--webhook-url", "-w", help="Webhook URL")
    parser.add_argument("--proxy", "-p", help="代理地址 (如 http://127.0.0.1:7890)")
    parser.add_argument("--print-url", action="store_true", help="打印手动设置URL")
    parser.add_argument("--info", "-i", action="store_true", help="获取当前Webhook信息")
    parser.add_argument("--ngrok", action="store_true", help="自动获取ngrok URL")

    args = parser.parse_args()

    # Token (优先命令行，其次环境变量)
    token = args.token or os.getenv("TELEGRAM_BOT_TOKEN") or "8736916502:AAFcXHAIbxJXmYiFpaJRODegblLlBcv6faw"

    # Webhook URL
    if args.webhook_url:
        webhook_url = args.webhook_url
    elif args.ngrok:
        ngrok_url = get_ngrok_url()
        if ngrok_url:
            webhook_url = f"{ngrok_url}/webhook/telegram"
            print(f"检测到 ngrok URL: {ngrok_url}")
        else:
            print("ERROR: 无法获取 ngrok URL，请确保 ngrok 正在运行")
            print("启动命令: ngrok http 8080")
            sys.exit(1)
    else:
        ngrok_url = get_ngrok_url()
        if ngrok_url:
            webhook_url = f"{ngrok_url}/webhook/telegram"
        else:
            print("ERROR: 未指定 Webhook URL，且无法获取 ngrok URL")
            print("使用方式:")
            print("  python scripts/setup_telegram_webhook.py --ngrok")
            print("  python scripts/setup_telegram_webhook.py -w https://your-domain/webhook/telegram")
            sys.exit(1)

    # 打印手动设置 URL
    if args.print_url:
        print("\n" + "=" * 60)
        print("手动设置方法:")
        print("=" * 60)
        print("\n在浏览器中访问以下URL:")
        print(f"\nhttps://api.telegram.org/bot{token}/setWebhook?url={webhook_url}\n")
        print("=" * 60)
        return

    # 获取信息模式
    if args.info:
        get_webhook_info(token, args.proxy)
        return

    # 设置 Webhook
    success = setup_webhook(token, webhook_url, args.proxy)

    if success:
        print("\n下一步:")
        print("1. 启动 mobile_gateway 服务:")
        print("   python scripts/mobile_gateway.py")
        print("\n2. 在 Telegram 中搜索你的 Bot 并发送消息测试")
    else:
        print("\n如果网络不通，请尝试:")
        print("1. 使用代理:")
        print(f"   python scripts/setup_telegram_webhook.py --proxy http://127.0.0.1:7890 --ngrok")
        print("\n2. 手动在浏览器中访问:")
        print(f"   python scripts/setup_telegram_webhook.py --print-url --ngrok")

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    if sys.platform == 'win32':
        sys.stdout.reconfigure(encoding='utf-8')
    main()