"""
@description: 多模型网关 - 支持Gemini/Qwen/OpenAI等异构模型调用 + 智能路由
@dependencies: requests, yaml, base64
@last_modified: 2026-03-27
"""

import os
import json
import yaml
import requests
import time
import base64
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum

# 导入Token使用追踪器
try:
    from src.utils.token_usage_tracker import get_tracker
    HAS_TRACKER = True
except ImportError:
    HAS_TRACKER = False


# ============================================================
# Timeout 配置：按任务类型分级
# ============================================================
TIMEOUT_BY_TASK = {
    # 快速任务 (30s)
    "intent_classify": 30,
    "auto_research_quality": 30,
    "failure_analysis": 30,
    "success_analysis": 30,
    "to_csv": 30,
    "translate": 30,
    "smart_chat": 30,

    # 中等任务 (60s)
    "kb_answer": 60,
    "proactive_advice": 60,
    "tavily_fallback": 60,
    "quick_qa": 60,
    "quick_summary": 60,
    "search_augmented": 60,
    "kg_retry": 60,

    # 标准任务 (120s)
    "planning": 120,
    "review": 120,
    "completeness_check": 120,
    "gap_fill": 120,
    "auto_discover_domains": 120,
    "research_summary": 120,
    "general": 120,

    # 深度任务 (180s)
    "synthesis": 180,
    "kg_refine": 180,
    "kb_deepen": 180,
    "kb_enrich": 180,
    "rebuild_decision_tree": 180,
    "doc_deepen": 180,
    "deep_research": 180,
    "competitive_research": 180,
    "market_analysis": 180,
    "code_generation": 180,
    "architecture_design": 180,
    "structured_doc": 180,  # PRD/规划类文档生成，JSON输出量大
}


class ModelProvider(Enum):
    GOOGLE = "google"
    OPENAI = "openai"
    AZURE_OPENAI = "azure_openai"
    ALIBABA = "alibaba"
    ANTHROPIC = "anthropic"
    ZHIPU = "zhipu"        # 智谱 AI
    DEEPSEEK = "deepseek"  # DeepSeek
    VOLCENGINE = "volcengine"  # 火山引擎（豆包）


class TaskType(Enum):
    """任务类型枚举"""
    # 代码类
    CODE_REVIEW = "code_review"
    CODE_GENERATION = "code_generation"
    CODE_DEBUG = "code_debug"
    # 架构设计类
    ARCHITECTURE_DESIGN = "architecture_design"
    SYSTEM_DESIGN = "system_design"
    # 快速响应类
    QUICK_QA = "quick_qa"
    QUICK_SUMMARY = "quick_summary"
    # 研究分析类
    SEARCH_AUGMENTED = "search_augmented"
    DATA_ANALYSIS = "data_analysis"
    COMPETITIVE_RESEARCH = "competitive_research"
    MARKET_ANALYSIS = "market_analysis"
    # 创意类
    CREATIVE_WRITING = "creative_writing"
    CONTENT_GENERATION = "content_generation"
    # 多语言类
    MULTILINGUAL = "multilingual"
    CHINESE_TASK = "chinese_task"
    # 硬件类
    HARDWARE_REVIEW = "hardware_review"
    # 复杂推理类
    COMPLEX_REASONING = "complex_reasoning"
    MATH_PROBLEM = "math_problem"
    LOGIC_ANALYSIS = "logic_analysis"
    # 通用
    GENERAL = "general"


@dataclass
class ModelConfig:
    provider: str
    model: str
    api_key: str
    purpose: str
    max_tokens: int
    temperature: float
    endpoint: Optional[str] = None
    deployment: Optional[str] = None  # Azure deployment name
    api_version: Optional[str] = None  # Azure API version
    capabilities: List[str] = field(default_factory=list)
    cost_tier: str = "$$"  # $, $$, $$$, $$$$
    performance: int = 3   # 1-5


class ModelGateway:
    """多模型网关 - 统一调用接口 + 智能路由"""

    def __init__(self, config_path: str = None):
        # 加载 .env 文件中的环境变量
        try:
            from dotenv import load_dotenv
            load_dotenv(Path(__file__).parent.parent.parent / ".env")
        except ImportError:
            pass  # python-dotenv 未安装，跳过

        if config_path is None:
            config_path = Path(__file__).parent.parent / "config" / "model_registry.yaml"

        self.config = self._load_config(config_path)
        self.models: Dict[str, ModelConfig] = {}
        self.routing_rules: Dict[str, Any] = {}
        self._parse_models()
        self._parse_routing_rules()

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

            # 处理endpoint（直接配置或环境变量）
            endpoint = cfg.get('endpoint', '')
            if not endpoint and cfg.get('endpoint_env'):
                endpoint = os.environ.get(cfg['endpoint_env'], '')
            elif endpoint and '${' in endpoint:
                # 兼容旧的 ${ENV_VAR} 格式
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
                endpoint=endpoint,
                deployment=cfg.get('deployment', cfg.get('model', 'gpt-4o')),
                api_version=cfg.get('api_version', '2024-12-01-preview'),
                capabilities=cfg.get('capabilities', []),
                cost_tier=cfg.get('cost_tier', '$$'),
                performance=cfg.get('performance', 3)
            )

    def _parse_routing_rules(self):
        """解析路由规则"""
        self.routing_rules = self.config.get('routing_rules', {})
        # === Gemini 配额感知降级 ===
        self._gemini_daily_counter = {}  # {"2026-03-24:gemini-3.1-pro": 150, ...}
        self._gemini_consecutive_429 = 0  # 连续 429 计数

    def select_best_model(self, task_type: TaskType, prefer_cheaper: bool = True) -> str:
        """
        智能选择最适合任务的模型

        Args:
            task_type: 任务类型
            prefer_cheaper: 同等能力下是否优先选择便宜的

        Returns:
            模型名称
        """
        task_mapping = self.routing_rules.get('task_model_mapping', {})
        preferred_order = task_mapping.get(task_type.value, ['gpt4o'])

        # 遍历优先级列表，找第一个可用的
        for model_name in preferred_order:
            if model_name in self.models and self.models[model_name].api_key:
                return model_name

        # 降级：找任意可用模型
        for name, cfg in self.models.items():
            if cfg.api_key:
                return name

        return None

    def route(self, task_type: TaskType, prompt: str, system_prompt: str = None) -> Dict[str, Any]:
        """
        智能路由：根据任务类型自动选择最合适的模型执行

        Args:
            task_type: 任务类型
            prompt: 用户提示
            system_prompt: 系统提示

        Returns:
            执行结果
        """
        # 1. 选择最佳模型
        model_name = self.select_best_model(task_type)
        if not model_name:
            return {"success": False, "error": "No available model"}

        # 2. 调用模型
        result = self.call(model_name, prompt, system_prompt)
        result['routed_model'] = model_name
        result['task_type'] = task_type.value

        return result

    def route_with_fallback(self, task_type: TaskType, prompt: str,
                            system_prompt: str = None) -> Dict[str, Any]:
        """
        智能路由 + 降级：主模型失败时自动切换备选

        Args:
            task_type: 任务类型
            prompt: 用户提示
            system_prompt: 系统提示

        Returns:
            执行结果
        """
        task_mapping = self.routing_rules.get('task_model_mapping', {})
        preferred_order = task_mapping.get(task_type.value, ['gpt4o'])

        results = {}
        for model_name in preferred_order:
            if model_name not in self.models or not self.models[model_name].api_key:
                continue

            result = self.call(model_name, prompt, system_prompt)
            results[model_name] = result

            if result.get('success'):
                result['routed_model'] = model_name
                result['task_type'] = task_type.value
                result['fallback_used'] = model_name != preferred_order[0]
                return result

        # 所有模型都失败
        return {
            "success": False,
            "error": "All models failed",
            "results": results,
            "task_type": task_type.value
        }

    def get_model_info(self, model_name: str) -> Dict[str, Any]:
        """获取模型详细信息"""
        cfg = self.models.get(model_name)
        if not cfg:
            return {"error": f"Model {model_name} not found"}

        return {
            "name": model_name,
            "provider": cfg.provider,
            "model": cfg.model,
            "purpose": cfg.purpose,
            "capabilities": cfg.capabilities,
            "cost_tier": cfg.cost_tier,
            "performance": cfg.performance,
            "max_tokens": cfg.max_tokens,
            "has_api_key": bool(cfg.api_key)
        }

    def list_available_models(self) -> List[Dict[str, Any]]:
        """列出所有可用模型"""
        available = []
        for name, cfg in self.models.items():
            if cfg.api_key:
                available.append({
                    "name": name,
                    "provider": cfg.provider,
                    "capabilities": cfg.capabilities,
                    "cost_tier": cfg.cost_tier,
                    "performance": cfg.performance
                })
        return available

    def _gemini_rate_key(self, model: str) -> str:
        """生成 Gemini 每日计数的 key"""
        from datetime import datetime
        return f"{datetime.now().strftime('%Y-%m-%d')}:{model}"

    def _should_degrade_gemini(self, model_name: str) -> str:
        """检查是否需要降级 Gemini 调用，返回实际应使用的 model_name 或 None"""
        cfg = self.models.get(model_name)
        if not cfg or cfg.provider != "google":
            return model_name  # 非 Gemini，不处理

        model_id = cfg.model
        rate_key = self._gemini_rate_key(model_id)
        count = self._gemini_daily_counter.get(rate_key, 0)

        # 策略：Pro 模型超过 180 次/天（给同事留余量），自动降级
        is_pro = "pro" in model_id.lower() and "flash" not in model_id.lower()
        if is_pro and count >= 180:
            # 尝试降级到 Flash
            flash_candidates = [name for name, c in self.models.items()
                               if c.provider == "google" and "flash" in c.model.lower() and c.api_key]
            if flash_candidates:
                print(f"[Gateway] Gemini Pro 今日 {count} 次，降级到 Flash: {flash_candidates[0]}")
                return flash_candidates[0]
            # Flash 也没有，降级到 Azure
            azure_candidates = [name for name, c in self.models.items()
                               if c.provider == "azure_openai" and c.api_key]
            if azure_candidates:
                print(f"[Gateway] Gemini Pro 今日 {count} 次，降级到 Azure: {azure_candidates[0]}")
                return azure_candidates[0]

        # 连续 429 错误 >= 3 次，强制降级
        if self._gemini_consecutive_429 >= 3:
            azure_candidates = [name for name, c in self.models.items()
                               if c.provider == "azure_openai" and c.api_key]
            if azure_candidates:
                print(f"[Gateway] Gemini 连续 {self._gemini_consecutive_429} 次 429，降级到 Azure")
                return azure_candidates[0]

        return model_name

    def call_gemini(self, model_name: str, prompt: str, system_prompt: str = None,
                     task_type: str = "general") -> Dict[str, Any]:
        """调用Google Gemini API"""
        # === 配额感知降级 ===
        actual_model = self._should_degrade_gemini(model_name)
        if actual_model != model_name:
            # 降级到非 Gemini 模型
            actual_cfg = self.models.get(actual_model)
            if actual_cfg and actual_cfg.provider == "azure_openai":
                result = self.call_azure_openai(actual_model, prompt, system_prompt, task_type)
                result["degraded_from"] = model_name
                return result
            elif actual_cfg and actual_cfg.provider == "google":
                model_name = actual_model  # 降级到 Flash，继续走 Gemini 逻辑

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

        # 动态 timeout
        timeout = TIMEOUT_BY_TASK.get(task_type, 120)

        start_time = time.time()
        try:
            resp = requests.post(
                f"{url}?key={cfg.api_key}",
                json=payload,
                timeout=timeout,
                headers={"Content-Type": "application/json"}
            )
            result = resp.json()
            latency_ms = int((time.time() - start_time) * 1000)

            if 'candidates' in result:
                text = result['candidates'][0]['content']['parts'][0]['text']

                # 提取token使用信息
                usage = result.get('usageMetadata', {})
                prompt_tokens = usage.get('promptTokenCount', 0)
                completion_tokens = usage.get('candidatesTokenCount', 0)

                # deep_research 模型如果拿不到 token 数，用长度估算
                if (prompt_tokens == 0 or completion_tokens == 0) and "deep" in cfg.model.lower():
                    if prompt_tokens == 0 and prompt:
                        prompt_tokens = len(str(prompt)) // 4  # 粗估：4字符≈1token
                    if completion_tokens == 0 and text:
                        completion_tokens = len(str(text)) // 4
                    if prompt_tokens > 0 or completion_tokens > 0:
                        print(f"[Token] {cfg.model} token estimated: in={prompt_tokens}, out={completion_tokens}")

                # 记录使用情况
                if HAS_TRACKER:
                    get_tracker().record(
                        model=cfg.model,
                        provider="google",
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        task_type=task_type,
                        success=True,
                        latency_ms=latency_ms
                    )

                # === 记录调用计数 ===
                rate_key = self._gemini_rate_key(cfg.model)
                self._gemini_daily_counter[rate_key] = self._gemini_daily_counter.get(rate_key, 0) + 1
                self._gemini_consecutive_429 = 0  # 成功了，重置连续失败计数

                return {
                    "success": True,
                    "model": model_name,
                    "response": text,
                    "raw": result,
                    "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens}
                }
            else:
                # === 检测 429 限流 / 配额耗尽 ===
                error_str = str(result)
                is_quota_error = "429" in error_str or "RESOURCE_EXHAUSTED" in error_str or "quota" in error_str.lower() or "exceeds your plan" in error_str.lower()

                if is_quota_error:
                    self._gemini_consecutive_429 += 1
                    print(f"[Gateway] Gemini quota exhausted (consecutive: {self._gemini_consecutive_429})")
                    # 立即重试一次，用降级模型
                    if self._gemini_consecutive_429 >= 1:
                        azure_candidates = [name for name, c in self.models.items()
                                           if c.provider == "azure_openai" and c.api_key]
                        if azure_candidates:
                            print(f"[Gateway] Quota fallback to Azure: {azure_candidates[0]}")
                            retry = self.call_azure_openai(azure_candidates[0], prompt, system_prompt, task_type)
                            retry["degraded_from"] = model_name
                            return retry

                # 记录失败（配额耗尽不计入真实失败，因为已有降级）
                if HAS_TRACKER and not is_quota_error:
                    get_tracker().record(
                        model=cfg.model,
                        provider="google",
                        prompt_tokens=0,
                        completion_tokens=0,
                        task_type=task_type,
                        success=False,
                        latency_ms=latency_ms
                    )
                return {"success": False, "error": str(result), "is_quota_error": is_quota_error}

        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            if HAS_TRACKER:
                get_tracker().record(
                    model=cfg.model,
                    provider="google",
                    prompt_tokens=0,
                    completion_tokens=0,
                    task_type=task_type,
                    success=False,
                    latency_ms=latency_ms
                )
            return {"success": False, "error": str(e)}

    def _record_gemini_usage(self, cfg: ModelConfig, usage: Dict, task_type: str, success: bool, latency_ms: int):
        """记录 Gemini API 使用情况"""
        if not HAS_TRACKER:
            return
        get_tracker().record(
            model=cfg.model, provider="google",
            prompt_tokens=usage.get('promptTokenCount', 0) if success else 0,
            completion_tokens=usage.get('candidatesTokenCount', 0) if success else 0,
            task_type=task_type, success=success, latency_ms=latency_ms
        )

    def call_gemini_vision(self, model_name: str, image_bytes: bytes, prompt: str,
                           system_prompt: str = None, task_type: str = "vision") -> Dict[str, Any]:
        """调用Google Gemini Vision API (多模态)"""
        cfg = self.models.get(model_name)
        if not cfg or not cfg.api_key:
            return {"success": False, "error": f"Model {model_name} not configured"}

        image_base64 = base64.b64encode(image_bytes).decode('utf-8')
        full_prompt = f"[System]\n{system_prompt}\n\n[User]\n{prompt}" if system_prompt else prompt
        contents = [{"role": "user", "parts": [
            {"inlineData": {"mimeType": "image/jpeg", "data": image_base64}}, {"text": full_prompt}]}]
        payload = {"contents": contents, "generationConfig": {"temperature": cfg.temperature, "maxOutputTokens": cfg.max_tokens}}

        start_time, url = time.time(), f"https://generativelanguage.googleapis.com/v1beta/models/{cfg.model}:generateContent"
        try:
            resp = requests.post(f"{url}?key={cfg.api_key}", json=payload, timeout=180,
                                 headers={"Content-Type": "application/json"}).json()
            latency_ms = int((time.time() - start_time) * 1000)
            if 'candidates' in resp:
                text = resp['candidates'][0]['content']['parts'][0]['text']
                usage = resp.get('usageMetadata', {})
                self._record_gemini_usage(cfg, usage, task_type, True, latency_ms)
                return {"success": True, "model": model_name, "response": text, "raw": resp,
                        "usage": {"prompt_tokens": usage.get('promptTokenCount', 0), "completion_tokens": usage.get('candidatesTokenCount', 0)}}
            self._record_gemini_usage(cfg, {}, task_type, False, latency_ms)
            return {"success": False, "error": str(resp)}
        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            self._record_gemini_usage(cfg, {}, task_type, False, latency_ms)
            return {"success": False, "error": str(e)}

    def call_gemini_audio(self, model_name: str, audio_bytes: bytes, prompt: str,
                          system_prompt: str = "", task_type: str = "audio") -> dict:
        """调用 Gemini 多模态音频理解"""
        cfg = self.models.get(model_name)
        if not cfg or not cfg.api_key:
            return {"success": False, "error": f"Model {model_name} not configured"}

        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
        contents = [{"role": "user", "parts": [
            {"inlineData": {"mimeType": "audio/ogg", "data": audio_b64}}, {"text": prompt}]}]
        payload = {"contents": contents, "generationConfig": {"temperature": cfg.temperature, "maxOutputTokens": cfg.max_tokens}}

        start_time = time.time()
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{cfg.model}:generateContent"
        try:
            resp = requests.post(f"{url}?key={cfg.api_key}", json=payload, timeout=180,
                                 headers={"Content-Type": "application/json"}).json()
            latency_ms = int((time.time() - start_time) * 1000)
            if 'candidates' in resp:
                text = resp['candidates'][0]['content']['parts'][0]['text']
                usage = resp.get('usageMetadata', {})
                self._record_gemini_usage(cfg, usage, task_type, True, latency_ms)
                return {"success": True, "response": text, "latency_ms": latency_ms}
            self._record_gemini_usage(cfg, {}, task_type, False, latency_ms)
            return {"success": False, "error": f"Gemini audio error: {str(resp)[:300]}"}
        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            self._record_gemini_usage(cfg, {}, task_type, False, latency_ms)
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
                timeout=180,
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

    def call_azure_openai(self, model_name: str, prompt: str, system_prompt: str = None,
                          task_type: str = "general", max_tokens: int = None) -> Dict[str, Any]:
        """调用Azure OpenAI API

        Args:
            model_name: 模型名称
            prompt: 用户提示
            system_prompt: 系统提示
            task_type: 任务类型（用于动态超时）
            max_tokens: 可选的最大输出token数（覆盖配置）
        """
        cfg = self.models.get(model_name)
        if not cfg or not cfg.api_key:
            return {"error": f"Model {model_name} not configured or missing API key"}

        if not cfg.endpoint:
            return {"error": f"Azure endpoint not configured for {model_name}"}

        # 使用deployment名称（如果配置了），否则使用model名称
        deployment_name = cfg.deployment or cfg.model
        api_version = cfg.api_version or "2024-12-01-preview"

        # Azure OpenAI API格式
        url = f"{cfg.endpoint.rstrip('/')}/openai/deployments/{deployment_name}/chat/completions?api-version={api_version}"

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        # O系列模型(推理模型)不支持max_tokens参数
        # GPT-5.x 系列支持 max_completion_tokens
        is_reasoning_model = cfg.model.startswith('o1') or cfg.model.startswith('o3')
        is_gpt5 = cfg.model.startswith('gpt-5')

        payload = {"messages": messages}

        # 使用传入的 max_tokens 或配置中的值
        output_tokens = max_tokens if max_tokens else cfg.max_tokens

        # 推理模型不设置temperature和max_tokens
        if not is_reasoning_model:
            payload["temperature"] = cfg.temperature
            # GPT-5.x 使用 max_completion_tokens，其他使用 max_tokens
            if is_gpt5:
                payload["max_completion_tokens"] = output_tokens
            else:
                payload["max_tokens"] = output_tokens

        start_time = time.time()
        try:
            # 动态 timeout
            timeout = TIMEOUT_BY_TASK.get(task_type, 120)

            resp = requests.post(
                url,
                json=payload,
                timeout=timeout,
                headers={
                    "api-key": cfg.api_key,
                    "Content-Type": "application/json"
                }
            )
            result = resp.json()
            latency_ms = int((time.time() - start_time) * 1000)

            # === Bug1 Fix: 404/部署名不匹配 显式告警 ===
            if resp.status_code == 404:
                error_msg = (
                    f"[MODEL_404] {model_name} (deployment={deployment_name}) "
                    f"返回 404。请检查 Azure portal 确认实际部署名。"
                    f"\n  URL: {url[:120]}"
                    f"\n  Response: {str(result)[:200]}"
                )
                print(error_msg)
                # 尝试推送飞书告警（best effort）
                try:
                    from scripts.feishu_handlers.text_router import reply_target
                    reply_target(f"⚠️ 模型 404\n{model_name} deployment={deployment_name}\n请检查 Azure 部署名", target="alert")
                except Exception:
                    pass  # 告警失败不影响主流程
                return {
                    "success": False,
                    "error": error_msg,
                    "status_code": 404,
                    "model": model_name,
                    "deployment": deployment_name
                }

            if resp.status_code >= 400 and resp.status_code != 404:
                error_msg = (
                    f"[MODEL_ERROR] {model_name} status={resp.status_code}: "
                    f"{str(result)[:300]}"
                )
                print(error_msg)
                return {
                    "success": False,
                    "error": error_msg,
                    "status_code": resp.status_code,
                    "model": model_name
                }

            # === 诊断日志（定位空响应根因）===
            print(f"  [Azure-Diag] task={task_type}")
            print(f"  [Azure-Diag] status={resp.status_code}")
            if 'usage' in result:
                usage = result['usage']
                print(f"  [Azure-Diag] prompt_tokens={usage.get('prompt_tokens', '?')}")
                print(f"  [Azure-Diag] completion_tokens={usage.get('completion_tokens', '?')}")

            if 'choices' in result:
                text = result['choices'][0]['message']['content']
                finish_reason = result['choices'][0].get('finish_reason', '?')

                # 空/短响应诊断
                if not text or len(text) < 50:
                    print(f"  [Azure-Diag] WARN empty/short response! len={len(text) if text else 0}")
                    print(f"  [Azure-Diag] finish_reason={finish_reason}")
                    # 检查 content_filter_results
                    cfr = result['choices'][0].get('content_filter_results', None)
                    if cfr:
                        # 安全打印，避免编码错误
                        try:
                            print(f"  [Azure-Diag] content_filter={cfr}")
                        except UnicodeEncodeError:
                            print(f"  [Azure-Diag] content_filter=<contains non-ascii chars>")

                # 提取token使用信息
                usage = result.get('usage', {})
                prompt_tokens = usage.get('prompt_tokens', 0)
                completion_tokens = usage.get('completion_tokens', 0)

                # 记录使用情况
                if HAS_TRACKER:
                    get_tracker().record(
                        model=cfg.model,
                        provider="azure_openai",
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        task_type=task_type,
                        success=True,
                        latency_ms=latency_ms
                    )

                return {
                    "success": True,
                    "model": model_name,
                    "response": text,
                    "raw": result,
                    "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
                    "finish_reason": result['choices'][0].get('finish_reason', 'stop')  # Fix 3: 返回 finish_reason
                }
            else:
                if HAS_TRACKER:
                    get_tracker().record(
                        model=cfg.model,
                        provider="azure_openai",
                        prompt_tokens=0,
                        completion_tokens=0,
                        task_type=task_type,
                        success=False,
                        latency_ms=latency_ms
                    )
                return {"success": False, "error": str(result)}

        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            if HAS_TRACKER:
                get_tracker().record(
                    model=cfg.model,
                    provider="azure_openai",
                    prompt_tokens=0,
                    completion_tokens=0,
                    task_type=task_type,
                    success=False,
                    latency_ms=latency_ms
                )
            return {"success": False, "error": str(e)}

    def call_zhipu(self, model_name: str, prompt: str, system_prompt: str = None,
                   task_type: str = "general") -> Dict[str, Any]:
        """调用智谱 AI GLM API"""
        cfg = self.models.get(model_name)
        if not cfg or not cfg.api_key:
            return {"error": f"Model {model_name} not configured or missing API key"}

        url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": cfg.model,
            "messages": messages,
            "temperature": cfg.temperature,
            "max_tokens": cfg.max_tokens
        }

        start_time = time.time()
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
            latency_ms = int((time.time() - start_time) * 1000)

            if 'choices' in result:
                text = result['choices'][0]['message']['content']

                # 提取token使用信息
                usage = result.get('usage', {})
                prompt_tokens = usage.get('prompt_tokens', 0)
                completion_tokens = usage.get('completion_tokens', 0)

                # 记录使用情况
                if HAS_TRACKER:
                    get_tracker().record(
                        model=cfg.model,
                        provider="zhipu",
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        task_type=task_type,
                        success=True,
                        latency_ms=latency_ms
                    )

                return {
                    "success": True,
                    "model": model_name,
                    "response": text,
                    "raw": result,
                    "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens}
                }
            else:
                if HAS_TRACKER:
                    get_tracker().record(
                        model=cfg.model,
                        provider="zhipu",
                        prompt_tokens=0,
                        completion_tokens=0,
                        task_type=task_type,
                        success=False,
                        latency_ms=latency_ms
                    )
                return {"success": False, "error": str(result)}

        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            if HAS_TRACKER:
                get_tracker().record(
                    model=cfg.model,
                    provider="zhipu",
                    prompt_tokens=0,
                    completion_tokens=0,
                    task_type=task_type,
                    success=False,
                    latency_ms=latency_ms
                )
            return {"success": False, "error": str(e)}

    def call_deepseek(self, model_name: str, prompt: str, system_prompt: str = None,
                      task_type: str = "general") -> Dict[str, Any]:
        """调用 DeepSeek API"""
        cfg = self.models.get(model_name)
        if not cfg or not cfg.api_key:
            return {"error": f"Model {model_name} not configured or missing API key"}

        url = "https://api.deepseek.com/chat/completions"

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": cfg.model,
            "messages": messages,
            "temperature": cfg.temperature,
            "max_tokens": cfg.max_tokens
        }

        start_time = time.time()
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
            latency_ms = int((time.time() - start_time) * 1000)

            if 'choices' in result:
                text = result['choices'][0]['message']['content']

                # 提取token使用信息
                usage = result.get('usage', {})
                prompt_tokens = usage.get('prompt_tokens', 0)
                completion_tokens = usage.get('completion_tokens', 0)

                # 记录使用情况
                if HAS_TRACKER:
                    get_tracker().record(
                        model=cfg.model,
                        provider="deepseek",
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        task_type=task_type,
                        success=True,
                        latency_ms=latency_ms
                    )

                return {
                    "success": True,
                    "model": model_name,
                    "response": text,
                    "raw": result,
                    "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens}
                }
            else:
                if HAS_TRACKER:
                    get_tracker().record(
                        model=cfg.model,
                        provider="deepseek",
                        prompt_tokens=0,
                        completion_tokens=0,
                        task_type=task_type,
                        success=False,
                        latency_ms=latency_ms
                    )
                return {"success": False, "error": str(result)}

        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            if HAS_TRACKER:
                get_tracker().record(
                    model=cfg.model,
                    provider="deepseek",
                    prompt_tokens=0,
                    completion_tokens=0,
                    task_type=task_type,
                    success=False,
                    latency_ms=latency_ms
                )
            return {"success": False, "error": str(e)}

    def call_volcengine(self, model_name: str, prompt: str, system_prompt: str = None,
                        task_type: str = "general") -> Dict[str, Any]:
        """调用火山引擎（豆包）API — OpenAI SDK 兼容格式"""
        cfg = self.models.get(model_name)
        if not cfg or not cfg.api_key:
            return {"success": False, "error": f"Model {model_name} not configured or missing API key"}

        endpoint = cfg.endpoint or "https://ark.cn-beijing.volces.com/api/v3"

        # 使用 OpenAI SDK（火山引擎 API 兼容 OpenAI 格式）
        try:
            from openai import OpenAI
            client = OpenAI(api_key=cfg.api_key, base_url=endpoint)
        except ImportError:
            return {"success": False, "error": "OpenAI SDK not installed"}

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        start_time = time.time()
        timeout = TIMEOUT_BY_TASK.get(task_type, 120)

        try:
            resp = client.chat.completions.create(
                model=cfg.model,
                messages=messages,
                max_tokens=cfg.max_tokens,
                temperature=cfg.temperature
            )
            latency_ms = int((time.time() - start_time) * 1000)

            text = resp.choices[0].message.content
            usage = {
                "prompt_tokens": resp.usage.prompt_tokens,
                "completion_tokens": resp.usage.completion_tokens
            }

            if HAS_TRACKER:
                get_tracker().record(
                    model=cfg.model,
                    provider="volcengine",
                    prompt_tokens=usage["prompt_tokens"],
                    completion_tokens=usage["completion_tokens"],
                    task_type=task_type,
                    success=True,
                    latency_ms=latency_ms
                )

            return {
                "success": True,
                "model": model_name,
                "response": text,
                "usage": usage
            }

        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            if HAS_TRACKER:
                get_tracker().record(
                    model=cfg.model,
                    provider="volcengine",
                    prompt_tokens=0,
                    completion_tokens=0,
                    task_type=task_type,
                    success=False,
                    latency_ms=latency_ms
                )
            return {"success": False, "error": str(e)}

    def call(self, model_name: str, prompt: str, system_prompt: str = None,
             task_type: str = "general") -> Dict[str, Any]:
        """统一调用接口"""
        cfg = self.models.get(model_name)
        if not cfg:
            return {"success": False, "error": f"Unknown model: {model_name}"}

        if cfg.provider == "google":
            return self.call_gemini(model_name, prompt, system_prompt, task_type)
        elif cfg.provider == "alibaba":
            return self.call_qwen(model_name, prompt, system_prompt)
        elif cfg.provider == "azure_openai":
            return self.call_azure_openai(model_name, prompt, system_prompt, task_type)
        elif cfg.provider == "zhipu":
            return self.call_zhipu(model_name, prompt, system_prompt, task_type)
        elif cfg.provider == "deepseek":
            return self.call_deepseek(model_name, prompt, system_prompt, task_type)
        elif cfg.provider == "volcengine":
            return self.call_volcengine(model_name, prompt, system_prompt, task_type)
        else:
            return {"success": False, "error": f"Unsupported provider: {cfg.provider}"}

    def dual_review(self, prompt: str, system_prompt: str = None) -> Dict[str, Any]:
        """
        双模型评审 - CPO_Critic专用

        支持任意两个异构模型组合：
        - Gemini + Qwen (理想组合)
        - Gemini + Azure (当前可用)
        - Qwen + Azure (如果Qwen配置后)
        - 单模型降级 (只有一个可用时)
        """
        results = {}

        # 1. Gemini评审
        gemini_result = self.call_gemini("critic_gemini", prompt, system_prompt)
        results["gemini"] = gemini_result

        # 2. Qwen评审（如果配置了API Key）
        if self.models.get("critic_qwen") and self.models["critic_qwen"].api_key:
            results["qwen"] = self.call_qwen("critic_qwen", prompt, system_prompt)
        else:
            results["qwen"] = {"success": False, "error": "Qwen API not configured"}

        # 3. Azure评审（作为第三评审模型）
        if self.models.get("critic_azure") and self.models["critic_azure"].api_key:
            results["azure"] = self.call_azure_openai("critic_azure", prompt, system_prompt)
        else:
            results["azure"] = {"success": False, "error": "Azure API not configured"}

        # 判定各模型是否PASS
        passes = {}
        for model_name, result in results.items():
            success = result.get("success", False)
            response = result.get("response", "")
            # 检查响应中是否包含PASS（评审结果通常是JSON）
            if success:
                response_upper = response.upper()
                passes[model_name] = "PASS" in response_upper or self._extract_score(response) >= 8.0
            else:
                passes[model_name] = False

        # 统计成功和通过数量
        successful_models = [m for m, r in results.items() if r.get("success", False)]
        passing_models = [m for m, p in passes.items() if p]

        # 判定逻辑
        if len(passing_models) >= 2:
            # 任意两个模型通过 = 双模型PASS
            verdict = "PASS"
            mode = "dual_model"
        elif len(passing_models) == 1:
            # 单模型通过 = 单模型降级PASS
            verdict = "PASS"
            mode = "single_model_fallback"
        else:
            verdict = "BLOCK"
            mode = "dual_model" if len(successful_models) >= 2 else "insufficient_models"

        return {
            "gemini": results["gemini"],
            "qwen": results["qwen"],
            "azure": results["azure"],
            "mode": mode,
            "dual_pass": len(passing_models) >= 2,
            "single_pass": len(passing_models) >= 1,
            "verdict": verdict,
            "passing_models": passing_models,
            "successful_models": successful_models
        }

    def _extract_score(self, response: str) -> float:
        """从响应中提取评分（如果存在）"""
        import re
        # 尝试匹配 "score": 8.0 或 score: 8.0 格式
        match = re.search(r'"?score"?\s*[:=]\s*([\d.]+)', response)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                pass
        return 0.0


# 全局实例
_gateway: Optional[ModelGateway] = None


def get_model_gateway() -> ModelGateway:
    """获取全局模型网关"""
    global _gateway
    if _gateway is None:
        _gateway = ModelGateway()
    return _gateway


# === 搜索/提炼模型分工工具函数 ===
def call_for_search(prompt: str, system_prompt: str = "", task_type: str = "search") -> dict:
    """搜索环节：用 Flash（快+便宜），失败时降级到 Azure"""
    gateway = get_model_gateway()
    result = gateway.call_gemini("gemini_2_5_flash", prompt, system_prompt, task_type)
    if not result.get("success"):
        # Flash 失败，降级到 Azure
        result = gateway.call_azure_openai("cpo", prompt, system_prompt, task_type)
        result["degraded_from"] = "gemini_2_5_flash"
    return result


def call_for_refine(prompt: str, system_prompt: str = "", task_type: str = "refine") -> dict:
    """提炼环节：用 GPT-5.4（质量优先）"""
    gateway = get_model_gateway()
    return gateway.call_azure_openai("cpo", prompt, system_prompt, task_type)


# === 测试 ===
if __name__ == "__main__":
    print("=" * 60)
    print("[MODEL GATEWAY TEST]")
    print("=" * 60)

    gateway = get_model_gateway()

    # 测试Azure OpenAI连接
    print("\n[TEST] Testing Azure OpenAI API connection...")
    result = gateway.call_azure_openai(
        "cpo",
        "请回复'Azure OpenAI连接成功'，并说明你是什么模型。",
        "你是一个测试助手。"
    )

    if result.get("success"):
        print(f"[SUCCESS] Azure OpenAI Response:\n{result['response'][:500]}")
    else:
        print(f"[FAILED] Error: {result.get('error')}")

    # 测试Gemini连接（可能失败）
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

    # 测试dual_review（降级模式）
    print("\n[TEST] Testing dual_review with Azure fallback...")
    result = gateway.dual_review(
        "请回复'评审通过'或'评审拒绝'，并说明原因。",
        "你是一个评审助手，必须严格审查内容。"
    )
    print(f"[RESULT] Mode: {result.get('mode')}, Verdict: {result.get('verdict')}")

    print("\n" + "=" * 60)