"""
@description: 飞书图片/语音/文件消息处理
@refactored_from: feishu_sdk_client.py
@last_modified: 2026-03-28
"""
import json
import tempfile
import threading
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def download_feishu_image(image_key: str, message_id: str) -> bytes:
    """从飞书下载图片"""
    from scripts.feishu_handlers.chat_helpers import get_tenant_access_token, log
    import requests

    token = get_tenant_access_token()
    if not token:
        log("  [图片下载失败: 无 token]")
        return b""

    headers = {"Authorization": f"Bearer {token}"}
    url = f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/resources/{image_key}?type=image"

    try:
        resp = requests.get(url, headers=headers, timeout=30)
        log(f"  [图片下载: status={resp.status_code}, size={len(resp.content)}]")
        if resp.status_code == 200:
            return resp.content
        else:
            # 打印错误详情
            log(f"  [图片下载失败: status={resp.status_code}, body={resp.text[:200]}]")
    except Exception as e:
        log(f"  [图片下载失败: {e}]")

    return b""


def download_audio(message_id: str, file_key: str = "") -> bytes:
    """从飞书下载语音消息的音频文件"""
    from scripts.feishu_handlers.chat_helpers import get_tenant_access_token, log
    import requests

    token = get_tenant_access_token()
    if not token:
        log("  [语音下载失败: 无 token]")
        return b""

    headers = {"Authorization": f"Bearer {token}"}

    # 方式1：通过 file_key 下载
    if file_key:
        url = f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/resources/{file_key}"
        params = {"type": "file"}
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=30)
            log(f"  [语音下载 方式1: status={resp.status_code}, size={len(resp.content)}]")
            if resp.status_code == 200 and len(resp.content) > 100:
                return resp.content
        except Exception as e:
            log(f"  [语音下载 方式1 失败: {e}]")

    # 方式2：不带 file_key
    url2 = f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/resources/file"
    params2 = {"type": "file"}
    try:
        resp = requests.get(url2, headers=headers, params=params2, timeout=30)
        log(f"  [语音下载 方式2: status={resp.status_code}, size={len(resp.content)}]")
        if resp.status_code == 200 and len(resp.content) > 100:
            return resp.content
    except Exception as e:
        log(f"  [语音下载 方式2 失败: {e}]")

    return b""


def compress_image(image_bytes: bytes, max_size: int = 1024) -> bytes:
    """压缩图片"""
    try:
        from PIL import Image
        from io import BytesIO

        img = Image.open(BytesIO(image_bytes))

        # 转换为 RGB（处理 RGBA）
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        # 缩放
        if max(img.size) > max_size:
            ratio = max_size / max(img.size)
            new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)

        # 输出
        output = BytesIO()
        img.save(output, format="JPEG", quality=85)
        return output.getvalue()
    except Exception as e:
        print(f"[compress_image] 压缩失败: {e}")
        return image_bytes


def handle_image_message(open_id: str, image_key: str, message_id: str, reply_target: str = None, send_reply=None) -> None:
    """处理图片消息：优先Gemini Vision，降级OCR，智能路由"""
    from scripts.feishu_handlers.chat_helpers import log

    if send_reply is None:
        from scripts.feishu_handlers.chat_helpers import send_reply as _send_reply
        send_reply = _send_reply

    if reply_target is None:
        reply_target = open_id

    import traceback
    try:
        send_reply(reply_target, "🖼️ 正在识别图片...")
        image_data = download_feishu_image(image_key, message_id)
        if not image_data:
            send_reply(reply_target, "❌ 图片下载失败，请重试")
            return

        # 压缩后调用 Gemini Vision
        compressed = compress_image(image_data)
        from src.utils.model_gateway import get_model_gateway
        result = get_model_gateway().call_gemini_vision("gemini_3_pro", compressed,
            "请详细描述这张图片的内容。如果图片包含文字，也请提取出来。")

        if result.get("success"):
            vision_text = result["response"]
            log(f"  [Gemini Vision] 成功: {vision_text[:100]}...")
        else:
            # 降级 OCR
            log(f"  [Gemini Vision] 失败，降级OCR")
            try:
                from feishu_bridge.ocr_middleware import process_image_to_text
                with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
                    f.write(image_data)
                    tmp_path = f.name
                vision_text = f"[OCR识别结果]\n{process_image_to_text(tmp_path)}"
            except:
                vision_text = "[图片处理失败]"

        # 自动入库逻辑
        gateway = get_model_gateway()
        refine_result = gateway.call_azure_openai(
            "cpo",
            f"以下是一张用户分享图片的 AI 描述：\n{vision_text[:3000]}\n\n"
            f"判断这是否与智能骑行头盔相关。如果相关，按 JSON 回复：\n"
            f'{{"title": "20字标题", "domain": "competitors或components或standards或lessons", "tags": ["标签"], "summary": "200字摘要", "relevant": true}}\n'
            f"如果完全无关，回复：{{\"relevant\": false}}",
            "只输出 JSON。",
            "image_share_refine"
        )

        saved_title = ""
        if refine_result.get("success"):
            try:
                import re
                resp = refine_result["response"].strip()
                resp = re.sub(r'^```json\s*', '', resp)
                resp = re.sub(r'\s*```$', '', resp)
                data = json.loads(resp)
                if data.get("relevant", False):
                    from src.tools.knowledge_base import add_knowledge
                    add_knowledge(
                        title=data.get("title", "User Image"),
                        domain=data.get("domain", "lessons"),
                        content=data.get("summary", vision_text[:500]),
                        tags=data.get("tags", []) + ["user_share"],
                        source="user_share:image",
                        confidence="high",
                        caller="user_share"
                    )
                    saved_title = data.get("title", "")
                    send_reply(reply_target, f"[Image] {vision_text[:300]}\n\n[OK] Saved: {saved_title}")
                else:
                    send_reply(reply_target, f"[Image] {vision_text[:500]}")
            except Exception as e2:
                log(f"[Image] JSON解析失败: {e2}")
                send_reply(reply_target, f"[Image] {vision_text[:500]}")
        else:
            send_reply(reply_target, f"[Image] {vision_text[:500]}")

        send_reply(reply_target, "If you have questions, just ask me")
    except Exception as e:
        log(f"[Image] 处理失败: {e}")
        log(f"[Image] 详细: {traceback.format_exc()}")
        send_reply(reply_target, f"图片处理失败: {str(e)[:200]}")


def handle_audio_message(open_id: str, message_id: str, content: str = "", reply_target: str = None, send_reply=None) -> None:
    """处理语音消息：下载→Gemini音频理解→智能路由"""
    from scripts.feishu_handlers.chat_helpers import log

    if send_reply is None:
        from scripts.feishu_handlers.chat_helpers import send_reply as _send_reply
        send_reply = _send_reply

    if reply_target is None:
        reply_target = open_id

    send_reply(reply_target, "🎤 收到语音，正在识别...")

    # 提取 file_key
    file_key = ""
    try:
        content_data = json.loads(content) if isinstance(content, str) else content
        file_key = content_data.get("file_key", "")
        log(f"  [语音 file_key: {file_key}]")
    except Exception:
        log(f"  [语音 content 解析失败: {content[:200]}]")

    audio_bytes = download_audio(message_id, file_key)
    if not audio_bytes:
        send_reply(reply_target, "❌ 语音下载失败，请重试")
        return

    log(f"  [语音下载成功: {len(audio_bytes)} bytes]")

    from src.utils.model_gateway import get_model_gateway
    result = get_model_gateway().call_gemini_audio(
        "gemini_3_pro",
        audio_bytes,
        "请准确转写这段语音的内容，只输出语音中的文字内容，不要添加任何解释。如果是中文语音就输出中文。",
        "",
        "audio_transcribe"
    )

    if not result.get("success"):
        send_reply(reply_target, f"❌ 语音识别失败: {result.get('error', '未知')[:200]}")
        return

    transcribed_text = result["response"].strip()
    log(f"  [语音转写: {transcribed_text[:100]}]")
    send_reply(reply_target, f"🎤 语音识别结果：{transcribed_text}")

    if not transcribed_text:
        return

    # 语音转文字后，按文本处理
    # 这里需要调用 text_router 或其他处理逻辑
    # 简化版本：直接调用 LLM
    from src.utils.model_gateway import get_model_gateway
    reply = get_model_gateway().call_azure_openai("cpo", transcribed_text, "", "chat")
    if reply.get("success"):
        send_reply(reply_target, reply["response"])


def handle_file_message(open_id: str, file_key: str, file_name: str, reply_target: str = None, send_reply=None) -> None:
    """处理文件消息（用户发送的文件）"""
    from scripts.feishu_handlers.chat_helpers import log

    if send_reply is None:
        from scripts.feishu_handlers.chat_helpers import send_reply as _send_reply
        send_reply = _send_reply

    if reply_target is None:
        reply_target = open_id

    send_reply(reply_target, f"📎 收到文件：{file_name}\n文件处理暂未实现。")


# === 导出接口 ===
__all__ = [
    "handle_image_message",
    "handle_audio_message",
    "handle_file_message",
    "download_feishu_image",
    "download_audio",
    "compress_image",
]