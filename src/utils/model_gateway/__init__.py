"""
# DEPRECATED: 此模块已被 scripts/litellm_gateway.py 替代，请勿使用
# 迁移日期: 2026-04-12
# 新接口: from scripts.litellm_gateway import get_model_gateway, call_for_search, call_for_refine

src/utils/model_gateway — 多模型网关（v2 重构版）

公开接口（向后兼容）:
    get_model_gateway()    — 获取全局 ModelGateway 实例
    call_for_search()      — 搜索环节便捷调用
    call_for_refine()      — 提炼环节便捷调用

ModelGateway 方法:
    .call()                — 统一文本调用（dispatch dict 路由）
    .call_image()          — 统一图像生成调用
    .call_gemini_vision()  — Gemini 图像理解
    .call_gemini_audio()   — Gemini 音频理解
    .dual_review()         — 双模型评审

v2 重构：
    - Provider 使用统一的 call_openai_compatible()
    - call() 改为 dispatch dict
"""
import os
import re
import yaml
import base64
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable
from datetime import datetime

from src.utils.model_gateway.config import (
    ModelConfig, ModelProvider, TaskType, TIMEOUT_BY_TASK,
    HAS_TRACKER, record_usage,
)

# Provider implementations
from src.utils.model_gateway.providers.gemini import (
    call_gemini, call_gemini_vision, call_gemini_audio, call_gemini_image_gen,
)
from src.utils.model_gateway.providers.azure_openai import (
    call_azure_openai, call_azure_responses,
)
from src.utils.model_gateway.providers.volcengine import (
    call_volcengine, call_volcengine_image_gen,
)
from src.utils.model_gateway.providers.others import (
    call_qwen, call_zhipu, call_deepseek,
)


class ModelGateway:
    """多模型网关 — 统一调用接口 + 智能路由"""

    # Peer model 映射（禁用模型的替代）
    PEER_MODELS = {
        "o3_mini": "doubao_seed_lite",
        "o3": "deepseek_r1_volcengine",
        "gpt_5_3": "gpt_4o_norway",
        "claude_opus_4_6": "gpt_5_4",
        "claude_sonnet_4_6": "gpt_4o_norway",
        "grok_4": "gpt_4o_norway",
        "gemini_deep_research": "o3_deep_research",
        "deepseek_v3_2": "deepseek_v3_volcengine",
        "deepseek_r1": "deepseek_r1_volcengine",
        "qwen_3_32b": "doubao_seed_pro",
        "llama_4_maverick": "gpt_4o_norway",
        "gemini_3_1_pro": "gemini_2_5_pro",
    }

    def __init__(self, config_path: str = None):
        try:
            from dotenv import load_dotenv
            load_dotenv(Path(__file__).parent.parent.parent.parent / ".env")
        except ImportError:
            pass

        if config_path is None:
            config_path = Path(__file__).parent.parent.parent / "config" / "model_registry.yaml"

        self.config = self._load_config(config_path)
        self.models: Dict[str, ModelConfig] = {}
        self.routing_rules: Dict[str, Any] = {}
        self._parse_models()
        self._parse_routing_rules()

        # v2: Provider dispatch dict
        self._provider_dispatch = self._build_provider_dispatch()

    def _build_provider_dispatch(self) -> Dict[str, Callable]:
        """构建 provider 路由表"""
        return {
            "alibaba": lambda cfg, mn, p, sp, tt: call_qwen(cfg, mn, p, sp, tt),
            "zhipu": lambda cfg, mn, p, sp, tt: call_zhipu(cfg, mn, p, sp, tt),
            "deepseek": lambda cfg, mn, p, sp, tt: call_deepseek(cfg, mn, p, sp, tt),
            "volcengine": lambda cfg, mn, p, sp, tt: call_volcengine(cfg, mn, p, sp, tt),
        }

    def _load_config(self, path: Path) -> dict:
        if not path.exists():
            return {}
        with open(path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    def _parse_models(self):
        registry = self.config.get('model_registry', {})
        for name, cfg in registry.items():
            api_key = cfg.get('api_key', '')
            if not api_key and cfg.get('api_key_env'):
                api_key = os.environ.get(cfg['api_key_env'], '')

            endpoint = cfg.get('endpoint', '')
            if not endpoint and cfg.get('endpoint_env'):
                endpoint = os.environ.get(cfg['endpoint_env'], '')
            elif endpoint and '${' in endpoint:
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
                enabled=cfg.get('enabled', True),
                endpoint=endpoint,
                deployment=cfg.get('deployment', cfg.get('model', 'gpt-4o')),
                api_version=cfg.get('api_version', '2024-12-01-preview'),
                capabilities=cfg.get('capabilities', []),
                cost_tier=cfg.get('cost_tier', '$$'),
                performance=cfg.get('performance', 3)
            )

    def _parse_routing_rules(self):
        self.routing_rules = self.config.get('routing_rules', {})
        self._gemini_daily_counter = {}
        self._gemini_consecutive_429 = 0

    # ============================================================
    # Gemini 配额感知
    # ============================================================
    def _gemini_rate_key(self, model: str) -> str:
        return f"{datetime.now().strftime('%Y-%m-%d')}:{model}"

    def _should_degrade_gemini(self, model_name: str) -> str:
        cfg = self.models.get(model_name)
        if not cfg or cfg.provider != "google":
            return model_name

        model_id = cfg.model
        rate_key = self._gemini_rate_key(model_id)
        count = self._gemini_daily_counter.get(rate_key, 0)

        is_pro = "pro" in model_id.lower() and "flash" not in model_id.lower()
        if is_pro and count >= 180:
            flash_candidates = [n for n, c in self.models.items()
                               if c.provider == "google" and "flash" in c.model.lower() and c.api_key
                               and "image" not in c.model.lower()]
            if flash_candidates:
                print(f"[Gateway] Gemini Pro 今日 {count} 次，降级到 Flash: {flash_candidates[0]}")
                return flash_candidates[0]

        if self._gemini_consecutive_429 >= 3:
            azure_candidates = [n for n, c in self.models.items()
                               if c.provider == "azure_openai" and c.api_key]
            if azure_candidates:
                print(f"[Gateway] Gemini 连续 {self._gemini_consecutive_429} 次 429，降级到 Azure")
                return azure_candidates[0]

        return model_name

    def _record_gemini_success(self, model_id: str):
        rate_key = self._gemini_rate_key(model_id)
        self._gemini_daily_counter[rate_key] = self._gemini_daily_counter.get(rate_key, 0) + 1
        self._gemini_consecutive_429 = 0

    # ============================================================
    # 核心路由: call() — 文本调用
    # ============================================================
    def _get_peer_model(self, model_name: str) -> str:
        """获取禁用模型的替代模型"""
        peer = self.PEER_MODELS.get(model_name)
        if peer:
            peer_cfg = self.models.get(peer)
            if peer_cfg and peer_cfg.enabled:
                return peer
        # 尝试 FALLBACK_MAP
        from scripts.deep_research.models import FALLBACK_MAP
        fallback = FALLBACK_MAP.get(model_name)
        if fallback:
            fb_cfg = self.models.get(fallback)
            if fb_cfg and fb_cfg.enabled:
                return fallback
        return None

    def call(self, model_name: str, prompt: str, system_prompt: str = None,
             task_type: str = "general") -> Dict[str, Any]:
        """统一文本调用接口

        关键改进:
        - 禁用模型自动路由到 peer model
        - 图像生成模型不再走 call_gemini()，而是路由到 call_image()
        """
        cfg = self.models.get(model_name)
        if not cfg:
            return {"success": False, "error": f"Unknown model: {model_name}"}

        # === 检查模型是否启用 ===
        if not cfg.enabled:
            peer = self._get_peer_model(model_name)
            if peer:
                print(f"[ModelGateway] {model_name} disabled, routing to {peer}")
                # 递归调用 peer model
                result = self.call(peer, prompt, system_prompt, task_type)
                result["routed_from"] = model_name
                return result
            else:
                return {"success": False, "error": f"Model {model_name} is disabled and has no peer model"}

        # === 图像生成模型拦截：不走文本通道 ===
        if "image_generation" in cfg.capabilities and task_type == "image_generation":
            return self.call_image(prompt, model_name=model_name)

        if cfg.provider == "google":
            # Gemini 配额降级检查
            actual_model = self._should_degrade_gemini(model_name)
            if actual_model != model_name:
                actual_cfg = self.models.get(actual_model)
                if actual_cfg and actual_cfg.provider == "azure_openai":
                    result = call_azure_openai(actual_cfg, actual_model, prompt, system_prompt, task_type)
                    result["degraded_from"] = model_name
                    return result
                elif actual_cfg and actual_cfg.provider == "google":
                    model_name = actual_model
                    cfg = actual_cfg

            result = call_gemini(cfg, model_name, prompt, system_prompt, task_type)

            if result.get("success"):
                self._record_gemini_success(cfg.model)
            elif result.get("is_quota_error"):
                self._gemini_consecutive_429 += 1
                # Quota 降级
                azure_candidates = [n for n, c in self.models.items()
                                   if c.provider == "azure_openai" and c.api_key]
                if azure_candidates:
                    print(f"[Gateway] Quota fallback to Azure: {azure_candidates[0]}")
                    retry_cfg = self.models[azure_candidates[0]]
                    retry = call_azure_openai(retry_cfg, azure_candidates[0], prompt, system_prompt, task_type)
                    retry["degraded_from"] = model_name
                    return retry
            return result

        elif cfg.provider == "alibaba":
            return self._provider_dispatch["alibaba"](cfg, model_name, prompt, system_prompt, task_type)

        elif cfg.provider == "azure_openai":
            if "deep-research" in (cfg.deployment or "").lower() or "deep-research" in cfg.model.lower():
                full_prompt = (f"[System]\n{system_prompt}\n\n[User]\n{prompt}"
                               if system_prompt else prompt)
                return call_azure_responses(cfg, model_name, full_prompt, task_type)
            return call_azure_openai(cfg, model_name, prompt, system_prompt, task_type)

        elif cfg.provider == "volcengine":
            return self._provider_dispatch["volcengine"](cfg, model_name, prompt, system_prompt, task_type)

        elif cfg.provider == "zhipu":
            return self._provider_dispatch["zhipu"](cfg, model_name, prompt, system_prompt, task_type)

        elif cfg.provider == "deepseek":
            return self._provider_dispatch["deepseek"](cfg, model_name, prompt, system_prompt, task_type)

        else:
            # v2: 尝试 dispatch dict
            handler = self._provider_dispatch.get(cfg.provider)
            if handler:
                return handler(cfg, model_name, prompt, system_prompt, task_type)
            return {"success": False, "error": f"Unsupported provider: {cfg.provider}"}

    # ============================================================
    # 图像生成统一接口
    # ============================================================
    def call_image(self, prompt: str, model_name: str = "nano_banana_pro",
                   size: str = "1024x1024", save_path: str = None) -> Dict[str, Any]:
        """统一图像生成接口

        Args:
            prompt: 图像描述
            model_name: 模型名 (nano_banana_pro / nano_banana_2 / gemini_flash_image /
                        nano_banana_original / seedream_3_0)
            size: 尺寸
            save_path: 可选，自动保存到文件

        Returns:
            {"success": True, "image_b64": "...", "mime_type": "image/png", ...}
        """
        cfg = self.models.get(model_name)
        if not cfg:
            return {"success": False, "error": f"Unknown model: {model_name}"}

        # enabled 检查
        if not cfg.enabled:
            # 尝试其他图像模型
            image_models = ["nano_banana_pro", "seedream_3_0", "nano_banana_2"]
            for alt in image_models:
                if alt != model_name:
                    alt_cfg = self.models.get(alt)
                    if alt_cfg and alt_cfg.enabled:
                        print(f"[ModelGateway] {model_name} disabled for image, routing to {alt}")
                        return self.call_image(prompt, alt, size, save_path)
            return {"success": False, "error": f"Model {model_name} is disabled and no image model available"}

        if cfg.provider == "google":
            result = call_gemini_image_gen(cfg, model_name, prompt)
        elif cfg.provider == "volcengine":
            result = call_volcengine_image_gen(cfg, model_name, prompt, size=size)
        else:
            return {"success": False, "error": f"Model {model_name} does not support image generation"}

        # 可选：保存到文件
        if result.get("success") and save_path and result.get("image_b64"):
            import base64 as _b64
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            with open(save_path, 'wb') as f:
                f.write(_b64.b64decode(result["image_b64"]))
            result["saved_to"] = save_path
            print(f"  [ImageGen] 已保存: {save_path}")

        return result

    def call_image_generation_multi(self, prompt: str, engines: list = None,
                                    size: str = "1024x1024") -> list:
        """多引擎并行图片生成"""
        if engines is None:
            engines = ["nano_banana_pro", "seedream_3_0"]
        results = []
        for engine in engines:
            try:
                result = self.call_image(prompt, model_name=engine, size=size)
                result["engine"] = engine
                results.append(result)
            except Exception as e:
                results.append({"success": False, "engine": engine, "error": str(e)})
        return results

    # ============================================================
    # 多模态调用（代理到 provider 模块）
    # ============================================================
    def call_gemini_vision(self, model_name: str, image_bytes: bytes, prompt: str,
                           system_prompt: str = None, task_type: str = "vision") -> Dict[str, Any]:
        cfg = self.models.get(model_name)
        if not cfg:
            return {"success": False, "error": f"Unknown model: {model_name}"}
        # enabled 检查
        if not cfg.enabled:
            peer = self._get_peer_model(model_name)
            if peer:
                print(f"[ModelGateway] {model_name} disabled for vision, routing to {peer}")
                peer_cfg = self.models.get(peer)
                if peer_cfg and peer_cfg.provider == "google":
                    result = call_gemini_vision(peer_cfg, peer, image_bytes, prompt, system_prompt, task_type)
                    result["routed_from"] = model_name
                    return result
            return {"success": False, "error": f"Model {model_name} is disabled and has no vision-capable peer"}
        return call_gemini_vision(cfg, model_name, image_bytes, prompt, system_prompt, task_type)

    def call_gemini_audio(self, model_name: str, audio_bytes: bytes, prompt: str,
                          system_prompt: str = "", task_type: str = "audio") -> Dict[str, Any]:
        cfg = self.models.get(model_name)
        if not cfg:
            return {"success": False, "error": f"Unknown model: {model_name}"}
        # enabled 检查
        if not cfg.enabled:
            peer = self._get_peer_model(model_name)
            if peer:
                print(f"[ModelGateway] {model_name} disabled for audio, routing to {peer}")
                peer_cfg = self.models.get(peer)
                if peer_cfg and peer_cfg.provider == "google":
                    result = call_gemini_audio(peer_cfg, peer, audio_bytes, prompt, system_prompt, task_type)
                    result["routed_from"] = model_name
                    return result
            return {"success": False, "error": f"Model {model_name} is disabled and has no audio-capable peer"}
        return call_gemini_audio(cfg, model_name, audio_bytes, prompt, system_prompt, task_type)

    def call_gemini(self, model_name: str, prompt: str, system_prompt: str = None,
                    task_type: str = "general") -> Dict[str, Any]:
        """向后兼容：直接调 gemini text（通过统一 call 入口）"""
        return self.call(model_name, prompt, system_prompt, task_type)

    def call_gemini_image(self, model_name: str, prompt: str) -> Dict[str, Any]:
        """向后兼容：调 gemini 图像生成"""
        return self.call_image(prompt, model_name=model_name)

    def call_azure_openai(self, model_name: str, prompt: str, system_prompt: str = None,
                          task_type: str = "general", max_tokens: int = None) -> Dict[str, Any]:
        """向后兼容（通过统一 call 入口）"""
        return self.call(model_name, prompt, system_prompt, task_type)

    def call_azure_responses(self, model_name: str, prompt: str,
                             task_type: str = "deep_research", tools: list = None) -> Dict[str, Any]:
        """向后兼容（通过统一 call 入口）"""
        return self.call(model_name, prompt, None, task_type)

    def call_volcengine(self, model_name: str, prompt: str, system_prompt: str = None,
                        task_type: str = "general", image_url: str = None) -> Dict[str, Any]:
        """向后兼容（通过统一 call 入口）"""
        return self.call(model_name, prompt, system_prompt, task_type)

    def call_image_generation(self, prompt: str, model_name: str = "seedream_3_0",
                              size: str = "1024x1024") -> Dict[str, Any]:
        """向后兼容"""
        return self.call_image(prompt, model_name=model_name, size=size)

    # ============================================================
    # 路由与工具方法
    # ============================================================
    def select_best_model(self, task_type: TaskType, prefer_cheaper: bool = True) -> str:
        task_mapping = self.routing_rules.get('task_model_mapping', {})
        preferred_order = task_mapping.get(task_type.value, ['gpt4o'])
        for model_name in preferred_order:
            if model_name in self.models and self.models[model_name].api_key:
                return model_name
        for name, cfg in self.models.items():
            if cfg.api_key:
                return name
        return None

    def route(self, task_type: TaskType, prompt: str, system_prompt: str = None) -> Dict[str, Any]:
        model_name = self.select_best_model(task_type)
        if not model_name:
            return {"success": False, "error": "No available model"}
        result = self.call(model_name, prompt, system_prompt)
        result['routed_model'] = model_name
        result['task_type'] = task_type.value
        return result

    def call_with_fallback(self, primary: str, fallback: str, prompt: str,
                           system_prompt: str = None, task_type: str = "general") -> Dict:
        result = self.call(primary, prompt, system_prompt, task_type)
        if result.get("success"):
            return result
        print(f"  [Fallback] {primary} failed, degrading to {fallback}")
        result2 = self.call(fallback, prompt, system_prompt, task_type)
        result2["degraded_from"] = primary
        return result2

    def get_model_info(self, model_name: str) -> Dict[str, Any]:
        cfg = self.models.get(model_name)
        if not cfg:
            return {"error": f"Model {model_name} not found"}
        return {
            "name": model_name, "provider": cfg.provider, "model": cfg.model,
            "purpose": cfg.purpose, "capabilities": cfg.capabilities,
            "cost_tier": cfg.cost_tier, "performance": cfg.performance,
            "max_tokens": cfg.max_tokens, "has_api_key": bool(cfg.api_key)
        }

    def list_available_models(self) -> List[Dict[str, Any]]:
        available = []
        for name, cfg in self.models.items():
            if cfg.api_key:
                available.append({
                    "name": name, "provider": cfg.provider,
                    "capabilities": cfg.capabilities,
                    "cost_tier": cfg.cost_tier, "performance": cfg.performance
                })
        return available

    def dual_review(self, prompt: str, system_prompt: str = None) -> Dict[str, Any]:
        """双模型评审"""
        results = {}
        results["gemini"] = self.call_gemini("critic_gemini", prompt, system_prompt)
        if self.models.get("critic_qwen") and self.models["critic_qwen"].api_key:
            cfg = self.models["critic_qwen"]
            results["qwen"] = call_qwen(cfg, "critic_qwen", prompt, system_prompt)
        else:
            results["qwen"] = {"success": False, "error": "Qwen API not configured"}
        if self.models.get("critic_azure") and self.models["critic_azure"].api_key:
            results["azure"] = self.call_azure_openai("critic_azure", prompt, system_prompt)
        else:
            results["azure"] = {"success": False, "error": "Azure API not configured"}

        passes = {}
        for mn, r in results.items():
            if r.get("success"):
                resp_upper = r.get("response", "").upper()
                passes[mn] = "PASS" in resp_upper or self._extract_score(r.get("response", "")) >= 8.0
            else:
                passes[mn] = False

        passing_models = [m for m, p in passes.items() if p]
        successful_models = [m for m, r in results.items() if r.get("success")]

        if len(passing_models) >= 2:
            verdict, mode = "PASS", "dual_model"
        elif len(passing_models) == 1:
            verdict, mode = "PASS", "single_model_fallback"
        else:
            verdict = "BLOCK"
            mode = "dual_model" if len(successful_models) >= 2 else "insufficient_models"

        return {
            "gemini": results["gemini"], "qwen": results["qwen"], "azure": results["azure"],
            "mode": mode, "dual_pass": len(passing_models) >= 2,
            "single_pass": len(passing_models) >= 1, "verdict": verdict,
            "passing_models": passing_models, "successful_models": successful_models
        }

    def _extract_score(self, response: str) -> float:
        match = re.search(r'"?score"?\s*[:=]\s*([\d.]+)', response)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                pass
        return 0.0


# ============================================================
# 全局实例 + 便捷函数（向后兼容）
# ============================================================
_gateway: Optional[ModelGateway] = None


def get_model_gateway() -> ModelGateway:
    global _gateway
    if _gateway is None:
        _gateway = ModelGateway()
    return _gateway


def call_for_search(prompt: str, system_prompt: str = "", task_type: str = "search") -> dict:
    gateway = get_model_gateway()
    result = gateway.call_gemini("gemini_2_5_flash", prompt, system_prompt, task_type)
    if not result.get("success"):
        result = gateway.call_azure_openai("cpo", prompt, system_prompt, task_type)
        result["degraded_from"] = "gemini_2_5_flash"
    return result


def call_for_refine(prompt: str, system_prompt: str = "", task_type: str = "refine") -> dict:
    gateway = get_model_gateway()
    return gateway.call_azure_openai("cpo", prompt, system_prompt, task_type)
