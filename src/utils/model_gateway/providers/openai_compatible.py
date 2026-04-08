"""
模型网关 — OpenAI SDK 兼容层（统一调用）

覆盖：Azure OpenAI, 火山引擎, 智谱, DeepSeek, 以及任何 OpenAI SDK 兼容的 API
"""
import time
import requests
from typing import Dict, Any, Optional

from src.utils.model_gateway.config import ModelConfig, TIMEOUT_BY_TASK, record_usage


def call_openai_compatible(
    cfg: ModelConfig,
    model_name: str,
    prompt: str,
    system_prompt: str = None,
    task_type: str = "general",
    endpoint_override: str = None,
    api_key_override: str = None,
    extra_headers: Dict[str, str] = None,
    use_openai_sdk: bool = False,
) -> Dict[str, Any]:
    """统一 OpenAI SDK 兼容调用

    支持：
    - Azure OpenAI（通过 REST API）
    - 火山引擎（通过 OpenAI SDK）
    - 智谱 AI（通过 REST API）
    - DeepSeek（通过 REST API）
    - 任何 OpenAI SDK 兼容 API

    Args:
        cfg: ModelConfig
        model_name: 模型名称（日志用）
        prompt: 用户提示
        system_prompt: 系统提示
        task_type: 任务类型
        endpoint_override: 覆盖 endpoint
        api_key_override: 覆盖 api_key
        extra_headers: 额外的请求头
        use_openai_sdk: 是否使用 OpenAI SDK（火山引擎用）

    Returns:
        {"success": True/False, "response": "...", "usage": {...}, ...}
    """
    endpoint = endpoint_override or cfg.endpoint
    api_key = api_key_override or cfg.api_key

    if not api_key:
        return {"success": False, "error": f"No API key for {model_name}"}

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    start_time = time.time()
    provider = cfg.provider or "unknown"

    try:
        if use_openai_sdk:
            # 使用 OpenAI SDK（火山引擎等）
            return _call_via_openai_sdk(cfg, model_name, messages, task_type, endpoint, api_key, start_time)
        else:
            # 使用 REST API（智谱、DeepSeek、Azure 等）
            return _call_via_rest_api(cfg, model_name, messages, task_type, endpoint, api_key, extra_headers, start_time)

    except requests.exceptions.Timeout:
        latency_ms = int((time.time() - start_time) * 1000)
        record_usage(cfg.model, provider, 0, 0, task_type, False, latency_ms)
        return {"success": False, "error": f"Timeout after {latency_ms}ms"}

    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        record_usage(cfg.model, provider, 0, 0, task_type, False, latency_ms)
        return {"success": False, "error": str(e)}


def _call_via_openai_sdk(
    cfg: ModelConfig,
    model_name: str,
    messages: list,
    task_type: str,
    endpoint: str,
    api_key: str,
    start_time: float,
) -> Dict[str, Any]:
    """通过 OpenAI SDK 调用"""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url=endpoint)
    except ImportError:
        return {"success": False, "error": "OpenAI SDK not installed"}

    timeout = TIMEOUT_BY_TASK.get(task_type, 120)

    resp = client.chat.completions.create(
        model=cfg.model,
        messages=messages,
        max_tokens=cfg.max_tokens,
        temperature=cfg.temperature,
        timeout=timeout,
    )

    latency_ms = int((time.time() - start_time) * 1000)
    text = resp.choices[0].message.content
    usage = {
        "prompt_tokens": resp.usage.prompt_tokens,
        "completion_tokens": resp.usage.completion_tokens,
    }

    record_usage(cfg.model, cfg.provider or "openai_sdk", usage["prompt_tokens"],
                usage["completion_tokens"], task_type, True, latency_ms)

    return {
        "success": True,
        "model": model_name,
        "response": text,
        "usage": usage,
    }


def _call_via_rest_api(
    cfg: ModelConfig,
    model_name: str,
    messages: list,
    task_type: str,
    endpoint: str,
    api_key: str,
    extra_headers: Dict[str, str],
    start_time: float,
) -> Dict[str, Any]:
    """通过 REST API 调用"""
    payload = {
        "model": cfg.model,
        "messages": messages,
        "temperature": cfg.temperature,
        "max_tokens": cfg.max_tokens,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)

    timeout = TIMEOUT_BY_TASK.get(task_type, 120)

    resp = requests.post(endpoint, json=payload, headers=headers, timeout=timeout)
    result = resp.json()
    latency_ms = int((time.time() - start_time) * 1000)

    if resp.status_code >= 400:
        record_usage(cfg.model, cfg.provider or "rest_api", 0, 0, task_type, False, latency_ms)
        return {
            "success": False,
            "error": f"HTTP {resp.status_code}: {str(result)[:300]}",
            "status_code": resp.status_code,
        }

    if "choices" in result:
        text = result["choices"][0]["message"]["content"]
        usage = result.get("usage", {})
        p_tok = usage.get("prompt_tokens", 0)
        c_tok = usage.get("completion_tokens", 0)

        record_usage(cfg.model, cfg.provider or "rest_api", p_tok, c_tok, task_type, True, latency_ms)

        return {
            "success": True,
            "model": model_name,
            "response": text,
            "raw": result,
            "usage": {"prompt_tokens": p_tok, "completion_tokens": c_tok},
        }

    record_usage(cfg.model, cfg.provider or "rest_api", 0, 0, task_type, False, latency_ms)
    return {"success": False, "error": str(result)}