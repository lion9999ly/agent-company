"""
@description: LiteLLM 统一模型网关 - 替代 model_gateway.py
@dependencies: litellm, os, dotenv
@last_modified: 2026-04-12

LiteLLM 统一接口：
- Azure OpenAI: azure/<deployment_name>
- 火山引擎: api_base + api_key
- Gemini: gemini/<model_name>
"""

import os
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv
import litellm
from litellm import completion

# 加载环境变量
load_dotenv()

# ============================================================
# Provider 配置（从环境变量读取）
# ============================================================

PROVIDER_CONFIG = {
    "azure": {
        "api_key": os.getenv("AZURE_OPENAI_API_KEY"),
        "api_base": os.getenv("AZURE_OPENAI_ENDPOINT"),
        "api_version": "2024-12-01-preview",
    },
    "azure_norway": {
        "api_key": os.getenv("AZURE_OPENAI_NORWAY_API_KEY"),
        "api_base": os.getenv("AZURE_OPENAI_NORWAY_ENDPOINT"),
        "api_version": "2025-04-01-preview",
    },
    "volcengine": {
        "api_key": os.getenv("ARK_API_KEY"),
        "api_base": "https://ark.cn-beijing.volces.com/api/v3",
    },
    "gemini": {
        "api_key": os.getenv("GEMINI_API_KEY"),
    },
}

# ============================================================
# 模型路由映射（简化版，替代 model_registry.yaml）
# ============================================================

MODEL_MAP = {
    # Azure OpenAI (主力) - 使用正确的 deployment name
    "gpt_5_4": {"provider": "azure", "model": "azure/gpt-5.4"},
    "gpt_4o": {"provider": "azure_norway", "model": "azure/gpt-4o"},  # Norway endpoint 有 gpt-4o
    "o3_deep_research": {"provider": "azure_norway", "model": "azure/o3-deep-research"},
    "gpt_5_3_codex": {"provider": "azure", "model": "azure/gpt-5.3-codex"},
    "grok_3": {"provider": "azure", "model": "azure/grok-3"},

    # 火山引擎 (中文主力) - 使用 openai/ 前缀 + api_base
    "doubao_seed_pro": {"provider": "volcengine", "model": "openai/doubao-seed-2-0-pro-260215"},
    "doubao_seed_lite": {"provider": "volcengine", "model": "openai/doubao-seed-2-0-lite-260215"},
    "deepseek_r1_volcengine": {"provider": "volcengine", "model": "openai/deepseek-r1-250528"},
    "deepseek_v3_volcengine": {"provider": "volcengine", "model": "openai/deepseek-v3-2-251201"},
    "glm_4_7": {"provider": "volcengine", "model": "openai/glm-4-7-251222"},

    # Gemini - 直接使用 gemini/ 前缀
    "gemini_3_1_pro": {"provider": "gemini", "model": "gemini/gemini-3.1-pro-preview"},
    "gemini_2_5_pro": {"provider": "gemini", "model": "gemini/gemini-2.5-pro"},
    "gemini_2_5_flash": {"provider": "gemini", "model": "gemini/gemini-2.5-flash"},
}

# 降级链
FALLBACK_CHAIN = {
    "gpt_5_4": ["doubao_seed_pro", "gemini_2_5_flash"],
    "o3_deep_research": ["gpt_5_4", "doubao_seed_pro"],
    "doubao_seed_pro": ["gemini_2_5_flash", "gpt_4o"],
    "gemini_3_1_pro": ["gpt_5_4", "doubao_seed_pro"],
}


class LiteLLMGateway:
    """LiteLLM 统一模型网关"""

    def __init__(self):
        self.config = PROVIDER_CONFIG
        self.model_map = MODEL_MAP
        self.fallback_chain = FALLBACK_CHAIN
        self._setup_litellm()

    def _setup_litellm(self):
        """配置 LiteLLM 全局设置"""
        # 禁用详细日志
        litellm.suppress_debug_info = True
        # 启用 fallback
        litellm.num_retries = 3
        litellm.retry_after = 0.5

    def _get_model_config(self, model_name: str) -> Dict[str, Any]:
        """获取模型配置"""
        if model_name not in self.model_map:
            raise ValueError(f"Unknown model: {model_name}")

        mapping = self.model_map[model_name]
        provider = mapping["provider"]
        model = mapping["model"]
        provider_config = self.config[provider]

        return {
            "model": model,
            "api_key": provider_config.get("api_key"),
            "api_base": provider_config.get("api_base"),
            "api_version": provider_config.get("api_version"),
        }

    def call(
        self,
        model_name: str,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        task_type: Optional[str] = None,
        use_fallback: bool = True,
        **kwargs
    ) -> Dict[str, Any]:
        """统一调用接口（兼容旧 model_gateway 接口）"""

        # 获取模型配置
        model_config = self._get_model_config(model_name)

        # 构建消息
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        # 构建参数
        call_params = {
            "model": model_config["model"],
            "messages": messages,
            "api_key": model_config.get("api_key"),
        }

        if model_config.get("api_base"):
            call_params["api_base"] = model_config["api_base"]
        if model_config.get("api_version"):
            call_params["api_version"] = model_config["api_version"]
        if temperature is not None:
            call_params["temperature"] = temperature
        if max_tokens is not None:
            call_params["max_tokens"] = max_tokens

        # 合并额外参数
        call_params.update(kwargs)

        # 设置 fallback
        if use_fallback and model_name in self.fallback_chain:
            call_params["fallbacks"] = [
                {"model": self.model_map[m]["model"]}
                for m in self.fallback_chain[model_name]
            ]

        try:
            response = completion(**call_params)

            # 提取响应
            content = response.choices[0].message.content
            usage = response.usage

            return {
                "success": True,
                "response": content,
                "model": model_config["model"],
                "tokens_used": usage.total_tokens if usage else None,
                "prompt_tokens": usage.prompt_tokens if usage else None,
                "completion_tokens": usage.completion_tokens if usage else None,
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "model": model_name,
            }

    def call_async(
        self,
        model_name: str,
        prompt: str,
        **kwargs
    ) -> Dict[str, Any]:
        """异步调用（使用 acompletion）"""
        import asyncio

        async def _call():
            model_config = self._get_model_config(model_name)
            messages = [{"role": "user", "content": prompt}]

            call_params = {
                "model": model_config["model"],
                "messages": messages,
                "api_key": model_config.get("api_key"),
            }

            if model_config.get("api_base"):
                call_params["api_base"] = model_config["api_base"]

            call_params.update(kwargs)

            try:
                response = await litellm.acompletion(**call_params)
                return {
                    "success": True,
                    "response": response.choices[0].message.content,
                }
            except Exception as e:
                return {"success": False, "error": str(e)}

        return asyncio.run(_call())

    def list_models(self) -> List[str]:
        """列出可用模型"""
        return list(self.model_map.keys())

    def get_provider_status(self) -> Dict[str, bool]:
        """检查各 provider 配置状态"""
        status = {}
        for provider, config in self.config.items():
            has_key = bool(config.get("api_key"))
            has_base = bool(config.get("api_base") or provider == "gemini")
            status[provider] = has_key and has_base
        return status


# ============================================================
# 兼容旧接口的工厂函数
# ============================================================

_gateway_instance: Optional[LiteLLMGateway] = None

def get_litellm_gateway() -> LiteLLMGateway:
    """获取网关单例"""
    global _gateway_instance
    if _gateway_instance is None:
        _gateway_instance = LiteLLMGateway()
    return _gateway_instance


# 兼容旧接口
def get_model_gateway():
    """兼容旧接口 - 返回 LiteLLM Gateway"""
    return get_litellm_gateway()


def call_for_search(prompt: str, system_prompt: str = "", task_type: str = "search") -> dict:
    """兼容旧接口 - 搜索环节便捷调用（Gemini flash 优先）"""
    gateway = get_litellm_gateway()
    result = gateway.call("gemini_2_5_flash", prompt, system_prompt=system_prompt, task_type=task_type)
    if not result.get("success"):
        # 降级到 gpt_4o
        result = gateway.call("gpt_4o", prompt, system_prompt=system_prompt, task_type=task_type)
        result["degraded_from"] = "gemini_2_5_flash"
    return result


def call_for_refine(prompt: str, system_prompt: str = "", task_type: str = "refine") -> dict:
    """兼容旧接口 - 提炼环节便捷调用（使用 gpt_5_4）"""
    gateway = get_litellm_gateway()
    return gateway.call("gpt_5_4", prompt, system_prompt=system_prompt, task_type=task_type)


# ============================================================
# 测试函数
# ============================================================

def test_providers():
    """测试三个 provider 连通性"""
    gateway = get_litellm_gateway()

    test_prompt = "回复'OK'即可，这是一个连通性测试。"

    results = {}

    # 1. Azure OpenAI
    print("[Test] Azure OpenAI (gpt-4o)...")
    result = gateway.call("gpt_4o", test_prompt, max_tokens=10)
    results["azure"] = result
    print(f"  Result: {result.get('success', False)} - {result.get('response', result.get('error', 'N/A'))[:50]}")

    # 2. 火山引擎 (doubao)
    print("[Test] Volcengine (doubao_seed_pro)...")
    result = gateway.call("doubao_seed_pro", test_prompt, max_tokens=10)
    results["volcengine"] = result
    print(f"  Result: {result.get('success', False)} - {result.get('response', result.get('error', 'N/A'))[:50]}")

    # 3. Gemini
    print("[Test] Gemini (gemini_2_5_flash)...")
    result = gateway.call("gemini_2_5_flash", test_prompt, max_tokens=10)
    results["gemini"] = result
    print(f"  Result: {result.get('success', False)} - {result.get('response', result.get('error', 'N/A'))[:50]}")

    return results


if __name__ == "__main__":
    print("=== LiteLLM Gateway 测试 ===")
    print(f"Provider Status: {get_litellm_gateway().get_provider_status()}")
    print(f"Available Models: {len(get_litellm_gateway().list_models())} models")
    print()
    test_providers()