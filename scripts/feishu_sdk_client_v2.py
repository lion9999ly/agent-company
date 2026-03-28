"""
@description: 飞书长连接客户端 v2 - 模块化重构版
@dependencies: lark-oapi, scripts/feishu_handlers/*
@last_modified: 2026-03-28

使用方法：
    python scripts/feishu_sdk_client_v2.py
"""
import os
import sys
import json
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

# 强制刷新日志
try:
    sys.stdout.reconfigure(line_buffering=True)
except:
    import functools
    print = functools.partial(print, flush=True)

# === lark SDK 初始化 ===
try:
    import lark_oapi as lark
except ImportError:
    print("请安装: pip install lark-oapi")
    sys.exit(1)

# === 导入各模块 ===
from scripts.feishu_handlers.chat_helpers import send_reply, log, get_session_id, set_reply_context, APP_ID, APP_SECRET
from scripts.feishu_handlers.text_router import route_text_message
from scripts.feishu_handlers.image_handler import handle_image_message, handle_audio_message, handle_file_message

# === 消息去重 ===
_processed_msgs = set()
_MAX_MSG_CACHE = 500


def handle_message(event):
    """处理收到的消息 - v2 模块化版本"""
    try:
        print(f"\n{'='*50}")
        print(f"收到消息!")

        message = event.event.message
        sender = event.event.sender

        # 获取基础信息
        msg_id = message.message_id
        msg_type = message.message_type
        chat_id = message.chat_id

        # 消息去重
        if msg_id in _processed_msgs:
            print(f"[Skip] 重复消息: {msg_id}")
            return
        _processed_msgs.add(msg_id)
        if len(_processed_msgs) > _MAX_MSG_CACHE:
            _processed_msgs.clear()

        # 过滤机器人自己的消息
        sender_type = getattr(sender, 'sender_type', '')
        if sender_type == 'app':
            print("[Skip] 机器人自己的消息")
            return

        open_id = sender.sender_id.open_id if sender.sender_id else ""
        content = json.loads(message.content) if message.content else {}

        print(f"  msg_type={msg_type}, content_len={len(str(content))}")
        print(f"  Open ID: {open_id}")
        print(f"  Chat ID: {chat_id}")

        # 判断群聊/私聊
        chat_type = message.chat_type if hasattr(message, 'chat_type') else ""
        is_group = chat_type == "group"

        # 群聊需要 @机器人
        if is_group:
            mentions = message.mentions if hasattr(message, 'mentions') else []
            is_mentioned = bool(mentions)
            if not is_mentioned:
                return
            print(f"  [群聊] 检测到 @")

        # 确定回复目标
        reply_target = chat_id if is_group else open_id
        reply_type = "chat_id" if is_group else "open_id"

        # 设置回复上下文
        set_reply_context(reply_target, reply_type)

        # 获取 session_id（用于对话记忆）
        session_id = get_session_id(open_id, chat_id)

        # === 按消息类型分发 ===
        if msg_type == "text":
            text = content.get("text", "")

            # 群聊清理 @mention
            if is_group and hasattr(message, 'mentions') and message.mentions:
                for mention in message.mentions:
                    if hasattr(mention, 'key'):
                        text = text.replace(mention.key, "").strip()
                # 额外清理 @xxx 格式
                text = __import__('re').sub(r'@[^\s]+\s*', '', text).strip()

            print(f"  消息类型: text, 内容: {text[:50]}...")

            # 交给文本路由器
            route_text_message(
                text=text,
                reply_target=reply_target,
                reply_type=reply_type,
                open_id=open_id,
                chat_id=chat_id,
                send_reply=send_reply,
                session_id=session_id
            )

        elif msg_type == "image":
            print(f"  消息类型: image")
            image_key = content.get("image_key", "")
            handle_image_message(open_id, image_key, msg_id, reply_target, send_reply)

        elif msg_type == "audio":
            print(f"  消息类型: audio")
            handle_audio_message(open_id, msg_id, json.dumps(content), reply_target, send_reply)

        elif msg_type == "file":
            print(f"  消息类型: file")
            file_key = content.get("file_key", "")
            file_name = content.get("file_name", "unknown")
            handle_file_message(open_id, file_key, file_name, reply_target, send_reply)

        elif msg_type == "post":
            print(f"  消息类型: post (富文本)")
            # 富文本消息提取纯文本
            post_content = content.get("content", [])
            text_parts = []
            for block in post_content:
                if isinstance(block, list):
                    for item in block:
                        if isinstance(item, dict) and "text" in item:
                            text_parts.append(item["text"])
            text = "\n".join(text_parts)
            if text:
                route_text_message(
                    text=text,
                    reply_target=reply_target,
                    reply_type=reply_type,
                    open_id=open_id,
                    chat_id=chat_id,
                    send_reply=send_reply,
                    session_id=session_id
                )

        else:
            print(f"  未支持的消息类型: {msg_type}")

    except Exception as e:
        print(f"[Error] handle_message: {e}")
        import traceback
        traceback.print_exc()


# === 启动服务 ===
def main():
    """启动飞书长连接客户端"""
    print(f"{'#'*60}")
    print(f"# 飞书长连接客户端 v2 启动")
    print(f"# APP_ID: {APP_ID[:10]}...")
    print(f"# 模块化架构")
    print(f"{'#'*60}")

    if not APP_ID or not APP_SECRET:
        print("[Error] 请设置环境变量 FEISHU_APP_ID 和 FEISHU_APP_SECRET")
        sys.exit(1)

    # 注册消息处理器
    event_handler = lark.EventDispatcherHandler.builder("", "") \
        .register_p2_im_message_receive_v1(handle_message) \
        .build()

    # 创建长连接客户端
    cli = lark.ws.Client(
        APP_ID,
        APP_SECRET,
        event_handler=event_handler,
        log_level=lark.LogLevel.DEBUG
    )

    print("服务启动，等待消息...")
    cli.start()


if __name__ == "__main__":
    main()