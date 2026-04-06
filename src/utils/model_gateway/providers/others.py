"""
模型网关 — 其他 Provider (Alibaba/Zhipu/DeepSeek 直连)
"""
import time
import requests
from typing import Dict, Any

from src.utils.model_gateway.config import ModelConfig, record_usage


def call_qwen(cfg: ModelConfig, model_name: str, prompt: str,
              system_prompt: str = None) -> Dict[str, Any]:
    """调用阿里云通义千问 API"""
    url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": cfg.model,
        "input": {"messages": messages},
        "parameters": {"temperature": cfg.temperature, "max_tokens": cfg.max_tokens}
    }

    try:
        resp = requests.post(url, json=payload, timeout=180,
                             headers={"Authorization": f"Bearer {cfg.api_key}",
                                      "Content-Type": "application/json"})
        result = resp.json()
        if 'output' in result:
            return {
                "success": True, "model": model_name,
                "response": result['output'].get('text',
                    result['output'].get('choices', [{}])[0].get('message', {}).get('content', '')),
                "raw": result
            }
        return {"success": False, "error": str(result)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def call_zhipu(cfg: ModelConfig, model_name: str, prompt: str,
               system_prompt: str = None, task_type: str = "general") -> Dict[str, Any]:
    """调用智谱 AI GLM API"""
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": cfg.model, "messages": messages,
        "temperature": cfg.temperature, "max_tokens": cfg.max_tokens
    }

    start_time = time.time()
    try:
        resp = requests.post(url, json=payload, timeout=120,
                             headers={"Authorization": f"Bearer {cfg.api_key}",
                                      "Content-Type": "application/json"})
        result = resp.json()
        latency_ms = int((time.time() - start_time) * 1000)

        if 'choices' in result:
            text = result['choices'][0]['message']['content']
            usage = result.get('usage', {})
            record_usage(cfg.model, "zhipu", usage.get('prompt_tokens', 0),
                        usage.get('completion_tokens', 0), task_type, True, latency_ms)
            return {"success": True, "model": model_name, "response": text, "raw": result,
                    "usage": {"prompt_tokens": usage.get('prompt_tokens', 0),
                              "completion_tokens": usage.get('completion_tokens', 0)}}
        record_usage(cfg.model, "zhipu", 0, 0, task_type, False, latency_ms)
        return {"success": False, "error": str(result)}
    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        record_usage(cfg.model, "zhipu", 0, 0, task_type, False, latency_ms)
        return {"success": False, "error": str(e)}


def call_deepseek(cfg: ModelConfig, model_name: str, prompt: str,
                  system_prompt: str = None, task_type: str = "general") -> Dict[str, Any]:
    """调用 DeepSeek API (直连)"""
    url = "https://api.deepseek.com/chat/completions"
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": cfg.model, "messages": messages,
        "temperature": cfg.temperature, "max_tokens": cfg.max_tokens
    }

    start_time = time.time()
    try:
        resp = requests.post(url, json=payload, timeout=120,
                             headers={"Authorization": f"Bearer {cfg.api_key}",
                                      "Content-Type": "application/json"})
        result = resp.json()
        latency_ms = int((time.time() - start_time) * 1000)

        if 'choices' in result:
            text = result['choices'][0]['message']['content']
            usage = result.get('usage', {})
            record_usage(cfg.model, "deepseek", usage.get('prompt_tokens', 0),
                        usage.get('completion_tokens', 0), task_type, True, latency_ms)
            return {"success": True, "model": model_name, "response": text, "raw": result,
                    "usage": {"prompt_tokens": usage.get('prompt_tokens', 0),
                              "completion_tokens": usage.get('completion_tokens', 0)}}
        record_usage(cfg.model, "deepseek", 0, 0, task_type, False, latency_ms)
        return {"success": False, "error": str(result)}
    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        record_usage(cfg.model, "deepseek", 0, 0, task_type, False, latency_ms)
        return {"success": False, "error": str(e)}
