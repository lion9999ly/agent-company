"""
模型网关 — 火山引擎 Provider

v2: 文本调用统一到 openai_compatible.call_openai_compatible()
仅保留图像生成专用逻辑
"""
import base64
import time
import requests
from typing import Dict, Any

from src.utils.model_gateway.config import ModelConfig, record_usage
from src.utils.model_gateway.providers.openai_compatible import call_openai_compatible


def call_volcengine(cfg: ModelConfig, model_name: str, prompt: str,
                    system_prompt: str = None, task_type: str = "general",
                    image_url: str = None) -> Dict[str, Any]:
    """调用火山引擎 API（豆包/DeepSeek/GLM）— OpenAI SDK 兼容格式

    v2: 使用统一的 call_openai_compatible()
    """
    endpoint = cfg.endpoint or "https://ark.cn-beijing.volces.com/api/v3"

    # 如果有图片，需要特殊处理
    if image_url:
        return _call_volcengine_vision(cfg, model_name, prompt, system_prompt, task_type, endpoint, image_url)

    return call_openai_compatible(
        cfg, model_name, prompt, system_prompt, task_type,
        endpoint_override=endpoint,
        use_openai_sdk=True,
    )


def _call_volcengine_vision(cfg: ModelConfig, model_name: str, prompt: str,
                             system_prompt: str, task_type: str,
                             endpoint: str, image_url: str) -> Dict[str, Any]:
    """火山引擎视觉调用"""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=cfg.api_key, base_url=endpoint)
    except ImportError:
        return {"success": False, "error": "OpenAI SDK not installed"}

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    messages.append({
        "role": "user",
        "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": image_url}}
        ]
    })

    start_time = time.time()
    try:
        resp = client.chat.completions.create(
            model=cfg.model, messages=messages,
            max_tokens=cfg.max_tokens, temperature=cfg.temperature
        )
        latency_ms = int((time.time() - start_time) * 1000)

        text = resp.choices[0].message.content
        usage = {
            "prompt_tokens": resp.usage.prompt_tokens,
            "completion_tokens": resp.usage.completion_tokens
        }

        record_usage(cfg.model, "volcengine", usage["prompt_tokens"],
                    usage["completion_tokens"], task_type, True, latency_ms)

        return {"success": True, "model": model_name, "response": text, "usage": usage}

    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        record_usage(cfg.model, "volcengine", 0, 0, task_type, False, latency_ms)
        return {"success": False, "error": str(e)}


def call_volcengine_image_gen(cfg: ModelConfig, model_name: str, prompt: str,
                              task_type: str = "image_generation",
                              size: str = "1024x1024") -> Dict[str, Any]:
    """调用火山引擎 Seedream 图像生成 API"""
    endpoint = cfg.endpoint or "https://ark.cn-beijing.volces.com/api/v3"

    try:
        from openai import OpenAI
        client = OpenAI(api_key=cfg.api_key, base_url=endpoint)
    except ImportError:
        return {"success": False, "error": "OpenAI SDK not installed"}

    start_time = time.time()
    try:
        resp = client.images.generate(
            model=cfg.model, prompt=prompt, size=size, n=1
        )
        latency_ms = int((time.time() - start_time) * 1000)

        if resp.data and len(resp.data) > 0:
            image_url = resp.data[0].url
            image_b64 = getattr(resp.data[0], 'b64_json', None)

            record_usage(cfg.model, "volcengine_image", len(prompt), 0,
                        task_type, True, latency_ms)

            result = {"success": True, "model": model_name, "latency_ms": latency_ms}
            if image_b64:
                result["image_b64"] = image_b64
                result["mime_type"] = "image/png"
            elif image_url:
                result["image_url"] = image_url
                # 尝试下载转 base64
                try:
                    img_resp = requests.get(image_url, timeout=30)
                    if img_resp.status_code == 200:
                        result["image_b64"] = base64.b64encode(img_resp.content).decode('utf-8')
                        result["mime_type"] = "image/png"
                except:
                    pass
            print(f"  [ImageGen] {model_name}: OK")
            return result
        else:
            return {"success": False, "error": "No image generated"}

    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000) if 'start_time' in locals() else 0
        record_usage(cfg.model, "volcengine_image", 0, 0, task_type, False, latency_ms)
        return {"success": False, "error": str(e)}
