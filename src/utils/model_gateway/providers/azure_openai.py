"""
模型网关 — Azure OpenAI Provider
包含: call_azure_openai (chat), call_azure_responses (o3-deep-research)
"""
import time
import requests
from typing import Dict, Any

from src.utils.model_gateway.config import ModelConfig, TIMEOUT_BY_TASK, record_usage


def call_azure_openai(cfg: ModelConfig, model_name: str, prompt: str,
                      system_prompt: str = None, task_type: str = "general",
                      max_tokens: int = None) -> Dict[str, Any]:
    """调用 Azure OpenAI Chat Completions API"""
    if not cfg.endpoint:
        return {"error": f"Azure endpoint not configured for {model_name}"}

    deployment_name = cfg.deployment or cfg.model
    api_version = cfg.api_version or "2024-12-01-preview"
    url = f"{cfg.endpoint.rstrip('/')}/openai/deployments/{deployment_name}/chat/completions?api-version={api_version}"

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    is_reasoning_model = cfg.model.startswith('o1') or cfg.model.startswith('o3')
    is_gpt5 = cfg.model.startswith('gpt-5')

    payload = {"messages": messages}
    output_tokens = max_tokens if max_tokens else cfg.max_tokens

    if not is_reasoning_model:
        payload["temperature"] = cfg.temperature
        if is_gpt5:
            payload["max_completion_tokens"] = output_tokens
        else:
            payload["max_tokens"] = output_tokens

    start_time = time.time()
    try:
        timeout = TIMEOUT_BY_TASK.get(task_type, 120)
        resp = requests.post(url, json=payload, timeout=timeout,
                             headers={"api-key": cfg.api_key, "Content-Type": "application/json"})
        result = resp.json()
        latency_ms = int((time.time() - start_time) * 1000)

        if resp.status_code == 404:
            error_msg = (f"[MODEL_404] {model_name} (deployment={deployment_name}) "
                        f"返回 404。\n  URL: {url[:120]}\n  Response: {str(result)[:200]}")
            print(error_msg)
            return {"success": False, "error": error_msg, "status_code": 404,
                    "model": model_name, "deployment": deployment_name}

        if resp.status_code >= 400:
            error_msg = f"[MODEL_ERROR] {model_name} status={resp.status_code}: {str(result)[:300]}"
            print(error_msg)
            return {"success": False, "error": error_msg, "status_code": resp.status_code, "model": model_name}

        print(f"  [Azure-Diag] task={task_type}")
        print(f"  [Azure-Diag] status={resp.status_code}")
        if 'usage' in result:
            usage = result['usage']
            print(f"  [Azure-Diag] prompt_tokens={usage.get('prompt_tokens', '?')}")
            print(f"  [Azure-Diag] completion_tokens={usage.get('completion_tokens', '?')}")

        if 'choices' in result:
            text = result['choices'][0]['message']['content']
            finish_reason = result['choices'][0].get('finish_reason', '?')

            if not text or len(text) < 50:
                print(f"  [Azure-Diag] WARN empty/short response! len={len(text) if text else 0}")
                print(f"  [Azure-Diag] finish_reason={finish_reason}")
                cfr = result['choices'][0].get('content_filter_results', None)
                if cfr:
                    try:
                        print(f"  [Azure-Diag] content_filter={cfr}")
                    except UnicodeEncodeError:
                        print(f"  [Azure-Diag] content_filter=<non-ascii>")

            usage = result.get('usage', {})
            record_usage(cfg.model, "azure_openai",
                        usage.get('prompt_tokens', 0), usage.get('completion_tokens', 0),
                        task_type, True, latency_ms)

            return {
                "success": True, "model": model_name, "response": text, "raw": result,
                "usage": {"prompt_tokens": usage.get('prompt_tokens', 0),
                          "completion_tokens": usage.get('completion_tokens', 0)},
                "finish_reason": finish_reason
            }
        else:
            record_usage(cfg.model, "azure_openai", 0, 0, task_type, False, latency_ms)
            return {"success": False, "error": str(result)}

    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        record_usage(cfg.model, "azure_openai", 0, 0, task_type, False, latency_ms)
        return {"success": False, "error": str(e)}


def call_azure_responses(cfg: ModelConfig, model_name: str, prompt: str,
                         task_type: str = "deep_research",
                         tools: list = None) -> Dict[str, Any]:
    """调用 Azure OpenAI — o3-deep-research 专用"""
    if not cfg.endpoint:
        return {"success": False, "error": f"Endpoint not configured for {model_name}"}

    deployment_name = cfg.deployment or cfg.model
    api_version = cfg.api_version or "2025-04-01-preview"
    url = (f"{cfg.endpoint.rstrip('/')}/openai/deployments/"
           f"{deployment_name}/chat/completions?api-version={api_version}")

    payload = {
        "messages": [{"role": "user", "content": prompt}],
        "max_completion_tokens": cfg.max_tokens or 16000,
    }
    if tools:
        payload["tools"] = tools

    timeout = max(TIMEOUT_BY_TASK.get(task_type, 180), 600)
    start_time = time.time()
    try:
        resp = requests.post(url, json=payload, timeout=timeout,
                             headers={"api-key": cfg.api_key, "Content-Type": "application/json"})
        result = resp.json()
        latency_ms = int((time.time() - start_time) * 1000)

        print(f"  [Azure-Responses] task={task_type} status={resp.status_code} latency={latency_ms}ms")

        if resp.status_code == 404:
            return {"success": False, "error": f"[MODEL_404] {model_name} 404", "status_code": 404}
        if resp.status_code >= 400:
            return {"success": False, "error": f"[MODEL_ERROR] {resp.status_code}: {str(result)[:300]}",
                    "status_code": resp.status_code}

        choices = result.get("choices", [])
        text = ""
        if choices:
            msg = choices[0].get("message", {})
            text = msg.get("content", "")
            if not text and "cot_summary" in msg:
                text = msg.get("cot_summary", "")

        usage = result.get("usage", {})
        p_tok = usage.get("prompt_tokens", 0)
        c_tok = usage.get("completion_tokens", 0)

        record_usage(cfg.model, "azure_responses", p_tok, c_tok, task_type, bool(text), latency_ms)

        if text:
            print(f"  [Azure-Responses] OK: {len(text)} chars, {c_tok} tokens")
            return {"success": True, "model": model_name, "response": text, "raw": result,
                    "usage": {"prompt_tokens": p_tok, "completion_tokens": c_tok}}
        else:
            return {"success": False, "error": f"Empty response: {str(result)[:200]}"}

    except requests.exceptions.Timeout:
        ms = int((time.time() - start_time) * 1000)
        return {"success": False, "error": f"Timeout after {ms}ms"}
    except Exception as e:
        return {"success": False, "error": str(e)}
