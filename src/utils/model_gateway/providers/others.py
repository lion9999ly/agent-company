"""
模型网关 — 其他 Provider (Alibaba/Zhipu/DeepSeek 直连)

v2: 统一使用 openai_compatible.call_openai_compatible()
"""
from typing import Dict, Any

from src.utils.model_gateway.config import ModelConfig
from src.utils.model_gateway.providers.openai_compatible import call_openai_compatible


def call_qwen(cfg: ModelConfig, model_name: str, prompt: str,
              system_prompt: str = None, task_type: str = "general") -> Dict[str, Any]:
    """调用阿里云通义千问 API"""
    endpoint = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    return call_openai_compatible(
        cfg, model_name, prompt, system_prompt, task_type,
        endpoint_override=endpoint,
        use_openai_sdk=False,
    )


def call_zhipu(cfg: ModelConfig, model_name: str, prompt: str,
               system_prompt: str = None, task_type: str = "general") -> Dict[str, Any]:
    """调用智谱 AI GLM API"""
    endpoint = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    return call_openai_compatible(
        cfg, model_name, prompt, system_prompt, task_type,
        endpoint_override=endpoint,
        use_openai_sdk=False,
    )


def call_deepseek(cfg: ModelConfig, model_name: str, prompt: str,
                  system_prompt: str = None, task_type: str = "general") -> Dict[str, Any]:
    """调用 DeepSeek API"""
    endpoint = "https://api.deepseek.com/chat/completions"
    return call_openai_compatible(
        cfg, model_name, prompt, system_prompt, task_type,
        endpoint_override=endpoint,
        use_openai_sdk=False,
    )
