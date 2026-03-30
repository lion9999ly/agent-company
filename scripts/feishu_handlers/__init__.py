"""
@description: 飞书消息处理器模块
@dependencies: 无
@last_modified: 2026-03-28
"""

from scripts.feishu_handlers.chat_helpers import (
    send_reply,
    send_image_reply,
    log,
    get_tenant_access_token,
    get_session_id,
    set_reply_context,
    APP_ID,
    APP_SECRET,
)

from scripts.feishu_handlers.file_sender import (
    send_file_to_feishu,
    send_image_to_feishu,
)

from scripts.feishu_handlers.commands import (
    handle_command,
    set_last_task_memory,
)

from scripts.feishu_handlers.image_handler import (
    handle_image_message,
    handle_audio_message,
    handle_file_message,
)

from scripts.feishu_handlers.rd_task import (
    is_rd_task,
    run_rd_task_background,
)

from scripts.feishu_handlers.text_router import (
    route_text_message,
)

__all__ = [
    # chat_helpers
    "send_reply",
    "send_image_reply",
    "log",
    "get_tenant_access_token",
    "get_session_id",
    "set_reply_context",
    "APP_ID",
    "APP_SECRET",
    # file_sender
    "send_file_to_feishu",
    "send_image_to_feishu",
    # commands
    "handle_command",
    "set_last_task_memory",
    # image_handler
    "handle_image_message",
    "handle_audio_message",
    "handle_file_message",
    # rd_task
    "is_rd_task",
    "run_rd_task_background",
    # text_router
    "route_text_message",
]