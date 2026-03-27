"""
@description: 多模型网关 - 支持Gemini/Qwen/OpenAI等异构模型调用
@dependencies: requests, yaml
@last_modified: 2026-03-16
"""

import os
import json
import yaml
import requests
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum


class ModelProvider(Enum):
    GOOGLE = "google"
    OPENAI = "openai"
    ALIBABA = "alibaba"
    ANTHROPIC = "anthropic"


@dataclass
class ModelConfig:
    provider: str
    model: str
    api_key: str
    purpose: str
    max_tokens: int
    temperature: float
    endpoint: Optional[str] = None


class ModelGateway:
    """多模型网关 - 统一调用接口"""

    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config" / "model_registry.yaml"

        self.config = self._load_config(config_path)
        self.models: Dict[str, ModelConfig] = {}
        self._parse_models()

    def _load_config(self, path: Path) -> dict:
        if not path.exists():
            return {}
        with open(path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    def _parse_models(self):
        """解析模型配置"""
        registry = self.config.get('model_registry', {})
        for name, cfg in registry.items():
            # 处理API Key（直接配置或环境变量）
            api_key = cfg.get('api_key', '')
            if not api_key and cfg.get('api_key_env'):
                api_key = os.environ.get(cfg['api_key_env'], '')

            # 处理endpoint
            endpoint = cfg.get('endpoint', '')
            if endpoint and '${' in endpoint:
                # 替换环境变量占位符
                for env_var in ['AZURE_OPENAI_ENDPOINT']:
                    placeholder = f'${{{env_var}}}'
                    if placeholder in endpoint:
                        endpoint = endpoint.replace(placeholder, os.environ.get(env_var, ''))

            self.models[name] = ModelConfig(
                provider=cfg.get('provider', 'openai'),
                model=cfg.get('model', 'gpt-4o'),
                api_key=api_key,
                purpose=cfg.get('purpose', 'general'),
                max_tokens=cfg.get('max_tokens', 4096),
                temperature=cfg.get('temperature', 0.1),
                endpoint=endpoint
            )

    def call_gemini(self, model_name: str, prompt: str, system_prompt: str = None) -> Dict[str, Any]:
        """调用Google Gemini API"""
        cfg = self.models.get(model_name)
        if not cfg or not cfg.api_key:
            return {"error": f"Model {model_name} not configured or missing API key"}

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

        try:
            resp = requests.post(
                f"{url}?key={cfg.api_key}",
                json=payload,
                timeout=120,
                headers={"Content-Type": "application/json"}
            )
            result = resp.json()

            if 'candidates' in result:
                text = result['candidates'][0]['content']['parts'][0]['text']
                return {
                    "success": True,
                    "model": model_name,
                    "response": text,
                    "raw": result
                }
            else:
                return {"success": False, "error": str(result)}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def call_qwen(self, model_name: str, prompt: str, system_prompt: str = None) -> Dict[str, Any]:
        """调用阿里云通义千问API"""
        cfg = self.models.get(model_name)
        if not cfg or not cfg.api_key:
            return {"error": f"Model {model_name} not configured or missing API key"}

        url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": cfg.model,
            "input": {"messages": messages},
            "parameters": {
                "temperature": cfg.temperature,
                "max_tokens": cfg.max_tokens
            }
        }

        try:
            resp = requests.post(
                url,
                json=payload,
                timeout=120,
                headers={
                    "Authorization": f"Bearer {cfg.api_key}",
                    "Content-Type": "application/json"
                }
            )
            result = resp.json()

            if 'output' in result:
                return {
                    "success": True,
                    "model": model_name,
                    "response": result['output'].get('text', result['output'].get('choices', [{}])[0].get('message', {}).get('content', '')),
                    "raw": result
                }
            else:
                return {"success": False, "error": str(result)}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def call(self, model_name: str, prompt: str, system_prompt: str = None) -> Dict[str, Any]:
        """统一调用接口"""
        cfg = self.models.get(model_name)
        if not cfg:
            return {"success": False, "error": f"Unknown model: {model_name}"}

        if cfg.provider == "google":
            return self.call_gemini(model_name, prompt, system_prompt)
        elif cfg.provider == "alibaba":
            return self.call_qwen(model_name, prompt, system_prompt)
        else:
            return {"success": False, "error": f"Unsupported provider: {cfg.provider}"}

    def dual_review(self, prompt: str, system_prompt: str = None) -> Dict[str, Any]:
        """
        双模型评审 - CPO_Critic专用
        必须两个模型都返回PASS才通过
        """
        # Gemini评审
        gemini_result = self.call_gemini("critic_gemini", prompt, system_prompt)

        # Qwen评审（如果配置了API Key）
        qwen_result = {"success": False, "error": "Qwen API not configured"}
        if self.models.get("critic_qwen") and self.models["critic_qwen"].api_key:
            qwen_result = self.call_qwen("critic_qwen", prompt, system_prompt)

        # 判定结果
        gemini_pass = gemini_result.get("success", False) and "PASS" in gemini_result.get("response", "").upper()
        qwen_pass = qwen_result.get("success", False) and "PASS" in qwen_result.get("response", "").upper()

        return {
            "gemini": gemini_result,
            "qwen": qwen_result,
            "dual_pass": gemini_pass and qwen_pass,
            "single_pass": gemini_pass or qwen_pass,
            "verdict": "PASS" if (gemini_pass and qwen_pass) else "BLOCK"
        }


# 全局实例
_gateway: Optional[ModelGateway] = None


def get_model_gateway() -> ModelGateway:
    """获取全局模型网关"""
    global _gateway
    if _gateway is None:
        _gateway = ModelGateway()
    return _gateway


# === 测试 ===
if __name__ == "__main__":
    print("=" * 60)
    print("[MODEL GATEWAY TEST]")
    print("=" * 60)

    gateway = get_model_gateway()

    # 测试Gemini连接
    print("\n[TEST] Testing Gemini API connection...")
    result = gateway.call_gemini(
        "critic_gemini",
        "请回复'Gemini连接成功'，并说明你是什么模型。",
        "你是一个测试助手。"
    )

    if result.get("success"):
        print(f"[SUCCESS] Gemini Response:\n{result['response'][:500]}")
    else:
        print(f"[FAILED] Error: {result.get('error')}")

    print("\n" + "=" * 60)