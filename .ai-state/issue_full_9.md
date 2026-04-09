# Day 17 系统全量审计 - scripts/feishu_handlers/chat_helpers.py

```python
"""
@description: 飞书消息通用工具 - send_reply、日志、token 管理
@refactored_from: feishu_sdk_client.py
@last_modified: 2026-03-28
"""
import os
import sys
import json
import requests
from pathlib import Path
from datetime import datetime

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(str(PROJECT_ROOT / ".env"))

# === 配置 ===
APP_ID = os.getenv("FEISHU_APP_ID", "")
APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")

# === 日志文件 ===
_LOG_FILE = PROJECT_ROOT / ".ai-state" / "feishu_debug.log"


def log(msg: str):
    """写入文件日志"""
    try:
        with open(_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
    except Exception:
        pass
    print(msg, flush=True)


# === 回复上下文：群聊时用 chat_id，私聊时用 open_id ===
_reply_context = {"target": None, "type": "open_id"}


def set_reply_context(target: str, rtype: str):
    """设置回复上下文"""
    _reply_context["target"] = target
    _reply_context["type"] = rtype


def get_tenant_access_token() -> str:
    """获取飞书 tenant_access_token"""
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    try:
        resp = requests.post(url, json={"app_id": APP_ID, "app_secret": APP_SECRET}, timeout=10)
        result = resp.json()
        if result.get("tenant_access_token"):
            return result["tenant_access_token"]
        else:
            log(f"[Token Error] {result}")
            return ""
    except Exception as e:
        log(f"[Token Exception] {e}")
        return ""


def send_reply(target_id: str = None, text: str = "", id_type: str = None) -> bool:
    """发送回复消息（支持长消息分块）

    如果不传参数，使用 _reply_context 中的默认值（群聊时自动回复到群里）

    Args:
        target_id: open_id（私聊）或 chat_id（群聊），None 时使用上下文
        text: 回复内容（超过1900字自动分块发送）
        id_type: "open_id" 或 "chat_id"，None 时使用上下文

    Returns:
        bool: 是否发送成功
    """
    # 使用上下文默认值
    if target_id is None:
        target_id = _reply_context.get("target")
    if id_type is None:
        id_type = _reply_context.get("type", "open_id")

    if not target_id:
        log("  [回复失败: 无目标ID]")
        return False

    # 消息分块处理（飞书单条消息限制约 2000 字）
    MAX_LEN = 1900  # 留一些余量
    if len(text) > MAX_LEN:
        chunks = _split_message(text, MAX_LEN)
        success = True
        for i, chunk in enumerate(chunks):
            if i > 0:
                import time
                time.sleep(0.3)  # 遇到频率限制
            if not _send_single_message(target_id, chunk, id_type):
                success = False
        return success
    else:
        return _send_single_message(target_id, text, id_type)


def _split_message(text: str, max_len: int) -> list:
    """智能分割长消息，尽量在换行处分割"""
    if len(text) <= max_len:
        return [text]

    chunks = []
    remaining = text

    while remaining:
        if len(remaining) <= max_len:
            chunks.append(remaining)
            break

        # 尝试在换行处分割
        split_pos = remaining.rfind('\n', 0, max_len)
        if split_pos > max_len // 2:
            chunks.append(remaining[:split_pos + 1])
            remaining = remaining[split_pos + 1:]
        else:
            # 没有合适的换行，直接截断
            chunks.append(remaining[:max_len] + "...")
            remaining = remaining[max_len:]

    return chunks


def _send_single_message(target_id: str, text: str, id_type: str) -> bool:
    """发送单条消息"""
    token = get_tenant_access_token()
    if not token:
        log("  [回复失败: 无法获取token]")
        return False

    url = f"https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type={id_type}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    data = {
        "receive_id": target_id,
        "msg_type": "text",
        "content": json.dumps({"text": text})
    }
    try:
        response = requests.post(url, headers=headers, json=data, timeout=10)
        result = response.json()
        if result.get("code") == 0:
            log(f"  [回复成功: {id_type}]")
            return True
        else:
            log(f"  [回复失败: {result}]")
            return False
    except Exception as e:
        log(f"  [回复异常: {e}]")
        return False


def send_image_reply(target_id: str, image_bytes: bytes, id_type: str = "open_id") -> None:
    """通过飞书发送图片消息"""
    import base64 as b64
    token = get_tenant_access_token()
    if not token:
        return
    # 先上传图片到飞书
    upload_url = "https://open.feishu.cn/open-apis/im/v1/images"
    headers = {"Authorization": f"Bearer {token}"}
    files = {"image": ("image.png", image_bytes, "image/png")}
    data = {"image_type": "message"}
    try:
        resp = requests.post(upload_url, headers=headers, files=files, data=data, timeout=30)
        result = resp.json()
        if result.get("code") != 0:
            log(f"  [图片上传失败: {result}]")
            return
        image_key = result["data"]["image_key"]
        # 发送图片消息
        msg_url = f"https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type={id_type}"
        msg_data = {
            "receive_id": target_id,
            "msg_type": "image",
            "content": json.dumps({"image_key": image_key})
        }
        msg_headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        requests.post(msg_url, headers=msg_headers, json=msg_data, timeout=10)
        log(f"  [图片发送成功: {id_type}]")
    except Exception as e:
        log(f"  [图片发送异常: {e}]")


def _safe_reply_error(send_reply, reply_target, task_name, error):
    """统一错误处理：记录详细日志，返回友好提示"""
    import traceback
    log(f"[ERROR] {task_name}: {traceback.format_exc()}")
    send_reply(reply_target, f"⚠️ {task_name} 遇到问题，已记录日志。请稍后重试。")


def get_session_id(open_id: str, chat_id: str) -> str:
    """生成会话 ID（用于对话记忆）"""
    if chat_id:
        return f"chat_{chat_id}"
    return f"user_{open_id}"


# === 导出接口 ===
__all__ = [
    "log",
    "send_reply",
    "send_image_reply",
    "get_tenant_access_token",
    "set_reply_context",
    "get_session_id",
    "_safe_reply_error",
    "APP_ID",
    "APP_SECRET",
]
```
