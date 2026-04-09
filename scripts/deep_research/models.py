"""
深度研究 — 模型路由层
职责: 降级链、并发信号量、统一模型调用入口
被调用方: pipeline.py, extraction.py, critic.py, learning.py, night_watch.py
"""
import threading
import time

from src.utils.model_gateway import get_model_gateway

gateway = get_model_gateway()


# ============================================================
# 并发控制: 按 provider 限制并发数
# ============================================================
PROVIDER_SEMAPHORES = {
    "o3_deep":      threading.Semaphore(3),
    "o3":           threading.Semaphore(3),
    "o3_mini":      threading.Semaphore(5),
    "grok":         threading.Semaphore(3),
    "gemini_deep":  threading.Semaphore(2),
    "doubao":       threading.Semaphore(8),
    "flash":        threading.Semaphore(8),
    "gemini_pro":   threading.Semaphore(3),
    "gpt54":        threading.Semaphore(4),
    "gpt53":        threading.Semaphore(4),
    "gpt4o":        threading.Semaphore(4),
    "deepseek_r1":  threading.Semaphore(3),
    "qwen":         threading.Semaphore(4),
    "llama":        threading.Semaphore(3),
    "glm":          threading.Semaphore(4),
}


def _get_sem_key(model_name: str) -> str:
    """模型名 → 信号量 key"""
    m = model_name.lower()
    if "o3" in m and "deep" in m:      return "o3_deep"
    if "o3_mini" in m or "o3-mini" in m: return "o3_mini"
    if "o3" in m:                        return "o3"
    if "grok" in m:                      return "grok"
    if "gemini" in m and "deep" in m:    return "gemini_deep"
    if "doubao" in m:                    return "doubao"
    if "flash" in m:                     return "flash"
    if "gemini" in m and "pro" in m:     return "gemini_pro"
    if "gpt_5_4" in m or "gpt-5.4" in m: return "gpt54"
    if "gpt_5_3" in m or "gpt-5.3" in m: return "gpt53"
    if "4o" in m:                        return "gpt4o"
    if "deepseek_r1" in m or "deepseek-r1" in m: return "deepseek_r1"
    if "qwen" in m:                      return "qwen"
    if "llama" in m:                     return "llama"
    if "glm" in m:                       return "glm"
    return "gpt54"


# ============================================================
# 降级映射表
# ============================================================
FALLBACK_MAP = {
    # Azure 模型失败 → 优先降到非 Azure 模型
    "gpt_5_4":               "doubao_seed_pro",      # Azure → 火山引擎
    "gpt_4o_norway":         "doubao_seed_pro",      # Azure → 火山引擎
    "gpt_5_3":               "deepseek_v3_volcengine",  # Azure → 火山引擎
    "o3_deep_research":      "gpt_5_4",
    "o3":                    "deepseek_r1_volcengine",
    "o3_mini":               "doubao_seed_lite",
    # 非Azure模型保持原有降级链
    "doubao_seed_pro":       "doubao_seed_lite",
    "doubao_seed_lite":      "glm_4_7",
    "deepseek_v3_volcengine":"deepseek_r1_volcengine",
    "deepseek_r1_volcengine":"glm_4_7",
    "glm_4_7":               "doubao_seed_pro",
    "doubao_vision_pro":     "gpt_4o_norway",
    "grok_4":                "doubao_seed_pro",
    "gemini_3_1_pro":        "gemini_2_5_pro",
    "gemini_2_5_pro":        "doubao_seed_pro",
    "gemini_2_5_flash":      "doubao_seed_lite",
    "gemini_deep_research":  "o3_deep_research",
    "qwen_3_32b":            "doubao_seed_pro",
    "llama_4_maverick":      "doubao_seed_lite",
    "deepseek_v3_2":         "deepseek_v3_volcengine",
    "deepseek_r1":           "deepseek_r1_volcengine",
}


# ============================================================
# 角色 → 模型映射
# ============================================================
ROLE_MODEL_MAP = {
    "CTO":            "gpt_5_4",
    "CMO":            "gpt_4o_norway",
    "CDO":            "deepseek_v3_volcengine",
    "CPO":            "gpt_5_4",
    "VERIFIER":       "deepseek_r1_volcengine",
    "CHINESE_CROSS":  "doubao_seed_pro",
}


def get_model_for_role(role: str) -> str:
    return ROLE_MODEL_MAP.get(role.upper(), "gpt_5_4")


# ============================================================
# 任务 → 模型映射（支持 W3 学习覆盖）
# ============================================================
TASK_MODEL_MAP = {
    "discovery":             "gemini_2_5_flash",
    "query_generation":      "gemini_2_5_flash",
    "data_extraction":       "gemini_2_5_flash",
    "role_assign":           "gemini_2_5_flash",
    "synthesis":             "gemini_2_5_pro",
    "re_synthesis":          "gemini_2_5_pro",
    "final_synthesis":       "gemini_2_5_pro",
    "critic_challenge":      "gemini_3_1_pro",
    "critic_cross":          "deepseek_r1_volcengine",
    "consistency_check":     "gemini_3_1_pro",
    "knowledge_extract":     "gemini_2_5_flash",
    "fix":                   "gpt_5_4",
    "cdo_fix":               "gpt_5_4",
    "chinese_search":        "doubao_seed_pro",
    "deep_research_search":  "o3_deep_research",
    "grok_search":           "gpt_4o_norway",
    "gemini_deep_search":    "o3_deep_research",
    "deep_drill_conclusion": "gpt_5_4",
    "debate":                "deepseek_v3_volcengine",
    "analogy":               "gemini_2_5_flash",
    "sandbox":               "deepseek_r1_volcengine",
}

# 延迟导入的学习函数引用（避免循环依赖）
_learned_model_fn = None


def set_learned_model_fn(fn):
    """由 learning.py 注册回调，避免循环 import"""
    global _learned_model_fn
    _learned_model_fn = fn


def get_model_for_task(task_type: str) -> str:
    if _learned_model_fn:
        learned = _learned_model_fn(task_type)
        if learned:
            return learned
    return TASK_MODEL_MAP.get(task_type, "gpt_5_4")


# ============================================================
# 运行时禁用列表 — pre-flight 失败的模型直接跳过，不浪费网络往返
# ============================================================
_disabled_models: set = set()


def disable_model(model_name: str):
    """标记模型为本轮不可用（pre-flight 发现 404/不可用时调用）"""
    _disabled_models.add(model_name)
    print(f"  [Models] 禁用 {model_name}（本轮运行期间跳过）")


def reset_disabled_models():
    """每次 run_deep_learning 开始时重置"""
    _disabled_models.clear()


def is_model_disabled(model_name: str) -> bool:
    return model_name in _disabled_models


# ============================================================
# 统一模型调用
# ============================================================
def call_model(model_name: str, prompt: str,
               system_prompt: str = None, task_type: str = "general") -> dict:
    """调用模型，失败时自动降级一次。已禁用的模型直接走降级。"""
    # 如果模型已被 pre-flight 禁用，直接走降级链，不浪费网络往返
    if model_name in _disabled_models:
        fallback = FALLBACK_MAP.get(model_name)
        if fallback and fallback not in _disabled_models:
            result2 = gateway.call(fallback, prompt, system_prompt, task_type)
            result2["degraded_from"] = model_name
            result2["skip_reason"] = "disabled_by_preflight"
            return result2
        return {"success": False, "error": f"{model_name} disabled, no fallback available"}

    result = gateway.call(model_name, prompt, system_prompt, task_type)
    if result.get("success"):
        return result

    fallback = FALLBACK_MAP.get(model_name)
    if fallback and fallback in gateway.models and fallback not in _disabled_models:
        print(f"  [Degrade] {model_name} failed, trying {fallback}")
        result2 = gateway.call(fallback, prompt, system_prompt, task_type)
        result2["degraded_from"] = model_name
        return result2

    return result


def call_with_backoff(model_name: str, prompt: str,
                      system_prompt: str = None, task_type: str = "general",
                      max_retries: int = 3) -> dict:
    """带限流退避的模型调用（用于 L1/L2/L3 并发场景）"""
    # 已禁用的模型直接走 call_model 的降级逻辑，不重试
    if model_name in _disabled_models:
        return call_model(model_name, prompt, system_prompt, task_type)

    sem_key = _get_sem_key(model_name)
    sem = PROVIDER_SEMAPHORES.get(sem_key)

    result = None
    for attempt in range(max_retries + 1):
        if sem:
            sem.acquire()
        try:
            result = call_model(model_name, prompt, system_prompt, task_type)

            error = result.get("error", "")
            is_rate_limit = ("429" in str(error) or "rate" in str(error).lower()
                             or "quota" in str(error).lower()
                             or "RESOURCE_EXHAUSTED" in str(error))

            if is_rate_limit and attempt < max_retries:
                wait = (2 ** attempt) * 10
                print(f"  [RateLimit] {model_name} attempt {attempt+1}, waiting {wait}s...")
                time.sleep(wait)
                continue

            return result
        finally:
            if sem:
                sem.release()

    return result
