"""
@description: 飞书文件上传与发送
@refactored_from: feishu_sdk_client.py
@last_modified: 2026-03-28
"""
import requests
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def send_file_to_feishu(target_id: str, file_path, id_type: str = "open_id", file_type: str = "stream") -> bool:
    """上传文件到飞书并发送到对话

    Args:
        target_id: 目标 ID（open_id 或 chat_id）
        file_path: 文件路径
        id_type: ID 类型（"open_id" 或 "chat_id"）
        file_type: 文件类型（默认 "stream"）

    Returns:
        bool: 是否发送成功
    """
    from scripts.feishu_handlers.chat_helpers import get_tenant_access_token, log

    file_path = Path(file_path)
    if not file_path.exists():
        log(f"[Feishu] File not found: {file_path}")
        return False

    # 根据文件扩展名确定 MIME 类型
    suffix = file_path.suffix.lower()
    mime_types = {
        '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        '.xls': 'application/vnd.ms-excel',
        '.csv': 'text/csv',
        '.pdf': 'application/pdf',
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.json': 'application/json',
        '.txt': 'text/plain',
        '.md': 'text/markdown',
    }
    mime_type = mime_types.get(suffix, 'application/octet-stream')

    try:
        # Step 1: 上传文件到飞书
        upload_url = "https://open.feishu.cn/open-apis/im/v1/files"
        token = get_tenant_access_token()

        if not token:
            log("[Feishu] Failed to get token")
            return False

        headers = {"Authorization": f"Bearer {token}"}

        with open(file_path, 'rb') as f:
            files = {
                'file': (file_path.name, f, mime_type),
                'file_type': (None, file_type),
                'file_name': (None, file_path.name),
            }
            resp = requests.post(upload_url, headers=headers, files=files, timeout=60)

        if resp.status_code != 200:
            log(f"[Feishu] Upload failed: {resp.status_code}")
            return False

        result = resp.json()
        if result.get("code") != 0:
            log(f"[Feishu] Upload failed: {result.get('msg')}")
            return False

        file_key = result["data"]["file_key"]

        # Step 2: 发送文件消息
        send_url = f"https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type={id_type}"

        import json
        payload = {
            "receive_id": target_id,
            "msg_type": "file",
            "content": json.dumps({"file_key": file_key})
        }

        resp2 = requests.post(send_url, headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }, json=payload, timeout=30)

        if resp2.status_code == 200 and resp2.json().get("code") == 0:
            log(f"[Feishu] File sent: {file_path.name}")
            return True
        else:
            log(f"[Feishu] Send failed: {resp2.json()}")
            return False
    except Exception as e:
        log(f"[Feishu] File send error: {e}")
        return False


def send_image_to_feishu(target_id: str, image_path, id_type: str = "open_id") -> bool:
    """发送图片到飞书

    Args:
        target_id: 目标 ID
        image_path: 图片路径
        id_type: ID 类型

    Returns:
        bool: 是否发送成功
    """
    from scripts.feishu_handlers.chat_helpers import get_tenant_access_token, log

    image_path = Path(image_path)
    if not image_path.exists():
        log(f"[Feishu] Image not found: {image_path}")
        return False

    try:
        with open(image_path, 'rb') as f:
            image_bytes = f.read()

        from scripts.feishu_handlers.chat_helpers import send_image_reply
        send_image_reply(target_id, image_bytes, id_type)
        return True
    except Exception as e:
        log(f"[Feishu] Image send error: {e}")
        return False


# === 导出接口 ===
__all__ = [
    "send_file_to_feishu",
    "send_image_to_feishu",
]