"""
模型网关 — Google Gemini Provider
包含: call_gemini (text), call_gemini_vision, call_gemini_audio, call_gemini_image_gen
"""
import base64
import time
import requests
from typing import Dict, Any

from src.utils.model_gateway.config import ModelConfig, TIMEOUT_BY_TASK, record_usage


def call_gemini(cfg: ModelConfig, model_name: str, prompt: str,
                system_prompt: str = None, task_type: str = "general",
                quota_check_fn=None) -> Dict[str, Any]:
    """调用 Google Gemini text API"""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{cfg.model}:generateContent"

    contents = []
    if system_prompt:
        contents.append({"role": "user", "parts": [{"text": f"[System]\n{system_prompt}\n\n[User]\n{prompt}"}]})
    else:
        contents.append({"role": "user", "parts": [{"text": prompt}]})

    payload = {
        "contents": contents,
        "generationConfig": {
            "temperature": cfg.temperature,
            "maxOutputTokens": cfg.max_tokens
        }
    }

    timeout = TIMEOUT_BY_TASK.get(task_type, 120)
    start_time = time.time()
    try:
        resp = requests.post(
            f"{url}?key={cfg.api_key}", json=payload, timeout=timeout,
            headers={"Content-Type": "application/json"}
        )
        result = resp.json()
        latency_ms = int((time.time() - start_time) * 1000)

        if 'candidates' in result:
            text = result['candidates'][0]['content']['parts'][0]['text']
            usage = result.get('usageMetadata', {})
            prompt_tokens = usage.get('promptTokenCount', 0)
            completion_tokens = usage.get('candidatesTokenCount', 0)

            if (prompt_tokens == 0 or completion_tokens == 0) and "deep" in cfg.model.lower():
                if prompt_tokens == 0 and prompt:
                    prompt_tokens = len(str(prompt)) // 4
                if completion_tokens == 0 and text:
                    completion_tokens = len(str(text)) // 4

            record_usage(cfg.model, "google", prompt_tokens, completion_tokens,
                        task_type, True, latency_ms)

            return {
                "success": True, "model": model_name, "response": text,
                "raw": result,
                "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens}
            }
        else:
            error_str = str(result)
            is_quota = any(k in error_str for k in ["429", "RESOURCE_EXHAUSTED", "quota", "exceeds your plan"])
            record_usage(cfg.model, "google", 0, 0, task_type, False, latency_ms)
            return {"success": False, "error": error_str, "is_quota_error": is_quota}

    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        record_usage(cfg.model, "google", 0, 0, task_type, False, latency_ms)
        return {"success": False, "error": str(e)}


def call_gemini_vision(cfg: ModelConfig, model_name: str, image_bytes: bytes,
                       prompt: str, system_prompt: str = None,
                       task_type: str = "vision") -> Dict[str, Any]:
    """调用 Gemini Vision API (多模态图像理解)"""
    image_base64 = base64.b64encode(image_bytes).decode('utf-8')
    full_prompt = f"[System]\n{system_prompt}\n\n[User]\n{prompt}" if system_prompt else prompt
    contents = [{"role": "user", "parts": [
        {"inlineData": {"mimeType": "image/jpeg", "data": image_base64}},
        {"text": full_prompt}
    ]}]
    payload = {
        "contents": contents,
        "generationConfig": {"temperature": cfg.temperature, "maxOutputTokens": cfg.max_tokens}
    }

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{cfg.model}:generateContent"
    start_time = time.time()
    try:
        resp = requests.post(f"{url}?key={cfg.api_key}", json=payload, timeout=180,
                             headers={"Content-Type": "application/json"}).json()
        latency_ms = int((time.time() - start_time) * 1000)
        if 'candidates' in resp:
            text = resp['candidates'][0]['content']['parts'][0]['text']
            usage = resp.get('usageMetadata', {})
            record_usage(cfg.model, "google", usage.get('promptTokenCount', 0),
                        usage.get('candidatesTokenCount', 0), task_type, True, latency_ms)
            return {"success": True, "model": model_name, "response": text, "raw": resp,
                    "usage": {"prompt_tokens": usage.get('promptTokenCount', 0),
                              "completion_tokens": usage.get('candidatesTokenCount', 0)}}
        record_usage(cfg.model, "google", 0, 0, task_type, False, latency_ms)
        return {"success": False, "error": str(resp)}
    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        record_usage(cfg.model, "google", 0, 0, task_type, False, latency_ms)
        return {"success": False, "error": str(e)}


def call_gemini_audio(cfg: ModelConfig, model_name: str, audio_bytes: bytes,
                      prompt: str, system_prompt: str = "",
                      task_type: str = "audio") -> Dict[str, Any]:
    """调用 Gemini 多模态音频理解"""
    audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
    contents = [{"role": "user", "parts": [
        {"inlineData": {"mimeType": "audio/ogg", "data": audio_b64}},
        {"text": prompt}
    ]}]
    payload = {
        "contents": contents,
        "generationConfig": {"temperature": cfg.temperature, "maxOutputTokens": cfg.max_tokens}
    }

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{cfg.model}:generateContent"
    start_time = time.time()
    try:
        resp = requests.post(f"{url}?key={cfg.api_key}", json=payload, timeout=180,
                             headers={"Content-Type": "application/json"}).json()
        latency_ms = int((time.time() - start_time) * 1000)
        if 'candidates' in resp:
            text = resp['candidates'][0]['content']['parts'][0]['text']
            usage = resp.get('usageMetadata', {})
            record_usage(cfg.model, "google", usage.get('promptTokenCount', 0),
                        usage.get('candidatesTokenCount', 0), task_type, True, latency_ms)
            return {"success": True, "response": text, "latency_ms": latency_ms}
        record_usage(cfg.model, "google", 0, 0, task_type, False, latency_ms)
        return {"success": False, "error": f"Gemini audio error: {str(resp)[:300]}"}
    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        record_usage(cfg.model, "google", 0, 0, task_type, False, latency_ms)
        return {"success": False, "error": str(e)}


def call_gemini_image_gen(cfg: ModelConfig, model_name: str, prompt: str,
                          task_type: str = "image_generation") -> Dict[str, Any]:
    """调用 Gemini 图像生成 API（nano_banana 系列）

    关键区别: responseModalities 包含 IMAGE，响应从 parts 中找 inlineData
    """
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{cfg.model}:generateContent"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]}
    }

    start_time = time.time()
    try:
        resp = requests.post(f"{url}?key={cfg.api_key}", json=payload, timeout=120,
                             headers={"Content-Type": "application/json"})
        data = resp.json()
        latency_ms = int((time.time() - start_time) * 1000)

        if resp.status_code >= 400:
            print(f"  [ImageGen] {model_name} status={resp.status_code}: {str(data)[:200]}")
            return {"success": False, "error": str(data)[:300]}

        if 'candidates' not in data:
            return {"success": False, "error": f"No candidates: {str(data)[:300]}"}

        parts = data['candidates'][0]['content']['parts']
        image_b64 = None
        mime_type = "image/png"
        text_response = ""

        for part in parts:
            if 'inlineData' in part:
                image_b64 = part['inlineData']['data']
                mime_type = part['inlineData'].get('mimeType', 'image/png')
            elif 'text' in part:
                text_response = part['text']

        if not image_b64:
            return {"success": False, "error": f"No image in response, text: {text_response[:200]}"}

        record_usage(cfg.model, "gemini_image", len(prompt), 0,
                    task_type, True, latency_ms)

        print(f"  [ImageGen] {model_name}: OK, {len(image_b64)//1024}KB")
        return {
            "success": True, "model": model_name,
            "image_b64": image_b64, "mime_type": mime_type,
            "text": text_response, "latency_ms": latency_ms,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
