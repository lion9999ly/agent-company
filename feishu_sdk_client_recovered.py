"""
@description: 飞书长连接客户端 - 使用官方SDK
@dependencies: lark-oapi
@last_modified: 2026-03-17

使用方法:
    python scripts/feishu_sdk_client.py
"""

import os
import sys
import json
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import lark_oapi as lark
except ImportError:
    print("请安装: pip install lark-oapi")
    sys.exit(1)


# 配置
APP_ID = os.getenv("FEISHU_APP_ID", "cli_a9326fa6ba389cc5")
APP_SECRET = os.getenv("FEISHU_APP_SECRET", "PY4z2a8vPdNPuDWrjzm4zfk4olwHfIv7")


def handle_message(event: lark.im.v1.P2ImMessageReceiveV1):
    """处理接收到的消息"""
    print(f"\n{'='*50}")
    print(f"收到消息!")

    # 获取消息内容
    message = event.event.message
    sender = event.event.sender

    msg_type = message.msg_type
    content = json.loads(message.content) if message.content else {}

    print(f"  消息类型: {msg_type}")
    print(f"  发送者: {sender.sender_id.open_id}")

    if msg_type == "text":
        text = content.get("text", "")
        print(f"  内容: {text}")

        # 回复消息
        reply(message.chat_id, text, sender.sender_id.open_id)

    print(f"{'='*50}\n")


def reply(chat_id: str, text: str, open_id: str):
    """回复消息"""
    # 创建客户端
    client = lark.Client.builder() \
        .app_id(APP_ID) \
        .app_secret(APP_SECRET) \
        .log_level(lark.LogLevel.DEBUG) \
        .build()

    # 发送消息
    request = lark.im.v1.CreateMessageRequest.builder() \
        .receive_id_type(lark.im.v1.CreateMessageReceiveIdType.OPEN_ID) \
        .request_body(lark.im.v1.CreateMessageRequest.builder() \
            .receive_id(open_id) \
            .msg_type(lark.im.v1.CreateMessageRequestMsgType.TEXT) \
            .content(json.dumps({"text": f"收到你的消息: {text}\n\n我是AI Agent助手，已成功连接!"})) \
            .build()) \
        .build()

    response = client.im.v1.message.create(request)

    if response.success():
        print(f"  回复成功!")
    else:
        print(f"  回复失败: {response.code} - {response.msg}")


def main():
    print("=" * 50)
    print("飞书长连接客户端 (SDK版)")
    print("=" * 50)
    print(f"App ID: {APP_ID}")
    print()

    # 创建客户端
    client = lark.Client.builder() \
        .app_id(APP_ID) \
        .app_secret(APP_SECRET) \
        .log_level(lark.LogLevel.INFO) \
        .build()

    # 构建事件处理器
    event_handler = lark.EventDispatcherHandler.builder(
        "", ""  # 长连接模式不需要验证token
    ).register_p2_im_message_receive_v1(handle_message) \
     .build()

    print("正在启动长连接...")
    print("现在可以在飞书中发送消息给机器人测试")
    print("按 Ctrl+C 停止")
    print("=" * 50)

    # 启动长连接
    cli = lark.ws.Client(APP_ID, APP_SECRET, event_handler=event_handler)
    cli.start()


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
    main()
