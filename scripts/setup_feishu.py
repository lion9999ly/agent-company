"""
@description: 飞书机器人配置脚本 - 快速设置双向通信
@dependencies: requests
@last_modified: 2026-03-17

使用方法:
    python scripts/setup_feishu.py --app-id YOUR_APP_ID --app-secret YOUR_SECRET
    python scripts/setup_feishu.py --test  # 测试连接
    python scripts/setup_feishu.py --info  # 查看配置信息
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


class FeishuSetup:
    """飞书配置管理"""

    def __init__(self, app_id: str = None, app_secret: str = None):
        self.app_id = app_id or os.getenv("FEISHU_APP_ID", "cli_a9326fa6ba389cc5")
        self.app_secret = app_secret or os.getenv("FEISHU_APP_SECRET", "PY4z2a8vPdNPuDWrjzm4zfk4olwHfIv7")
        self.base_url = "https://open.feishu.cn/open-apis"
        self.access_token = None
        self.token_expires = 0

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
            print("正在连接飞书API...")
            response = requests.post(url, json=data, timeout=10)
            result = response.json()

            if result.get("code") == 0:
                self.access_token = result["tenant_access_token"]
                self.token_expires = time.time() + result["expire"] - 300
                print(f"SUCCESS: 连接成功!")
                print(f"Token: {self.access_token[:20]}...")
                print(f"有效期: {result['expire']}秒")
                return self.access_token
            else:
                print(f"ERROR: 认证失败")
                print(f"  - 错误码: {result.get('code')}")
                print(f"  - 错误信息: {result.get('msg')}")
                return ""
        except Exception as e:
            print(f"ERROR: 连接异常 - {e}")
            return ""

    def get_bot_info(self) -> dict:
        """获取机器人信息"""
        token = self.get_tenant_access_token()
        if not token:
            return {}

        url = f"{self.base_url}/bot/v3/info"
        headers = {"Authorization": f"Bearer {token}"}

        try:
            response = requests.get(url, headers=headers, timeout=10)
            result = response.json()
            if result.get("code") == 0:
                return result.get("bot", {})
            else:
                print(f"获取机器人信息失败: {result}")
                return {}
        except Exception as e:
            print(f"获取机器人信息异常: {e}")
            return {}

    def check_permissions(self) -> dict:
        """检查权限状态"""
        token = self.get_tenant_access_token()
        if not token:
            return {}

        # 需要检查的权限列表
        required_permissions = [
            "im:message:receive_as_bot",  # 接收消息
            "im:message:send",            # 发送消息
            "im:resource",                # 资源访问
        ]

        url = f"{self.base_url}/auth/v3/app/permission/getTenantPermissionStatus"
        headers = {"Authorization": f"Bearer {token}"}

        try:
            response = requests.get(url, headers=headers, timeout=10)
            result = response.json()
            return result
        except Exception as e:
            print(f"检查权限异常: {e}")
            return {}

    def send_test_message(self, receive_id: str, receive_id_type: str = "user_id") -> bool:
        """发送测试消息"""
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
            "content": json.dumps({
                "text": f"🤖 AI Agent 测试消息\n\n发送时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n如果你收到这条消息，说明飞书机器人配置成功！"
            })
        }

        try:
            response = requests.post(url, headers=headers, json=data, timeout=10)
            result = response.json()

            if result.get("code") == 0:
                print("SUCCESS: 消息发送成功!")
                return True
            else:
                print(f"ERROR: 消息发送失败")
                print(f"  - 错误码: {result.get('code')}")
                print(f"  - 错误信息: {result.get('msg')}")
                return False
        except Exception as e:
            print(f"ERROR: 发送异常 - {e}")
            return False

    def print_setup_guide(self):
        """打印配置指南"""
        print("""
========================================
飞书机器人完整配置指南
========================================

📋 前置准备
1. 已创建飞书企业自建应用
2. 已获取 App ID 和 App Secret

📍 步骤1: 配置事件订阅（重要！）
   1. 打开飞书开放平台: https://open.feishu.cn
   2. 进入你的应用 → 事件订阅
   3. 点击"添加事件订阅"
   4. 配置请求地址:
      - 如果你使用 ngrok: https://<ngrok-url>/webhook/feishu
      - 如果你有公网服务器: https://your-domain.com/webhook/feishu
   5. 订阅事件:
      - im.message.receive_v1 (接收消息)
   6. 保存配置

📍 步骤2: 开通权限（必须！）
   进入"权限管理" → 开通以下权限:
   ✅ im:message:receive_as_bot - 接收消息
   ✅ im:message:send - 发送消息
   ✅ im:resource - 访问图片/语音资源

📍 步骤3: 发布应用
   1. 提交应用版本
   2. 等待管理员审批
   3. 审批通过后，应用即可使用

📍 步骤4: 创建机器人会话
   1. 在飞书中搜索你的机器人名称
   2. 发起会话
   3. 发送消息测试

📍 步骤5: 启动网关服务
   python scripts/mobile_gateway.py --port 8080

========================================
环境变量配置
========================================
export FEISHU_APP_ID="cli_a9326fa6ba389cc5"
export FEISHU_APP_SECRET="PY4z2a8vPdNPuDWrjzm4zfk4olwHfIv7"

或在代码中直接配置（已内置）
========================================
""")

    def print_quick_start(self):
        """打印快速开始指南"""
        print("""
========================================
飞书机器人快速开始
========================================

✅ 当前配置状态:
""")
        print(f"   App ID: {self.app_id}")
        print(f"   App Secret: {self.app_secret[:10]}...")

        token = self.get_tenant_access_token()
        if token:
            print(f"   连接状态: ✅ 正常")
            bot_info = self.get_bot_info()
            if bot_info:
                print(f"   机器人名称: {bot_info.get('app_name', 'Unknown')}")
        else:
            print(f"   连接状态: ❌ 失败")

        print("""
========================================
下一步操作
========================================
1. 启动网关服务:
   python scripts/mobile_gateway.py --port 8080

2. 配置事件订阅:
   python scripts/setup_feishu.py --guide

3. 测试消息发送:
   python scripts/setup_feishu.py --send-test <user_id>

========================================
""")


def main():
    parser = argparse.ArgumentParser(description="飞书机器人配置工具")
    parser.add_argument("--app-id", "-i", help="飞书应用ID")
    parser.add_argument("--app-secret", "-s", help="飞书应用密钥")
    parser.add_argument("--test", "-t", action="store_true", help="测试连接")
    parser.add_argument("--info", action="store_true", help="查看配置信息")
    parser.add_argument("--guide", "-g", action="store_true", help="打印完整配置指南")
    parser.add_argument("--send-test", help="发送测试消息到指定用户ID")
    parser.add_argument("--quick-start", "-q", action="store_true", help="快速开始指南")

    args = parser.parse_args()

    setup = FeishuSetup(args.app_id, args.app_secret)

    if args.guide:
        setup.print_setup_guide()
    elif args.test:
        token = setup.get_tenant_access_token()
        if token:
            print("\n✅ 飞书连接测试成功!")
            bot_info = setup.get_bot_info()
            if bot_info:
                print(f"机器人名称: {bot_info.get('app_name', 'Unknown')}")
                print(f"激活状态: {bot_info.get('activate_status', 'Unknown')}")
    elif args.info:
        setup.print_quick_start()
    elif args.send_test:
        setup.send_test_message(args.send_test)
    elif args.quick_start:
        setup.print_quick_start()
    else:
        # 默认显示快速开始
        setup.print_quick_start()


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
    main()