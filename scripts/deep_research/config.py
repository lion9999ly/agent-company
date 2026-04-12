"""
@description: 深度研究配置 — 并发控制、模型路由、降级映射
@dependencies: src.utils.model_gateway
@last_modified: 2026-04-04
"""
import time
import threading
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.litellm_gateway import get_model_gateway

# 全局网关实例
gateway = get_model_gateway()

# ============================================================
# 并发控制: 按 provider 限制并发数
# ============================================================
PROVIDER_SEMAPHORES = {
    "o3": threading.Semaphore(3),        # o3 慢，3 并发
    "doubao": threading.Semaphore(8),    # 豆包快，8 并发
    "flash": threading.Semaphore(8),     # Flash 提炼，8 并发
    "gemini_pro": threading.Semaphore(3),# 有限额，保守
    "gpt54": threading.Semaphore(4),     # 成本高
    "gpt4o": threading.Semaphore(4),     # 通用
}


def _get_sem_key(model_name: str) -> str:
    """模型名 → 信号量 key"""
    if "o3" in model_name and "deep" in model_name:
        return "o3"
    elif "doubao" in model_name:
        return "doubao"
    elif "flash" in model_name:
        return "flash"
    elif "gemini" in model_name and "pro" in model_name:
        return "gemini_pro"
    elif "gpt_5_4" in model_name or "gpt-5.4" in model_name:
        return "gpt54"
    elif "4o" in model_name:
        return "gpt4o"
    return "gpt54"  # 默认保守


# ============================================================
# 降级映射表
# ============================================================
FALLBACK_MAP = {
    "gpt_5_4": "gpt_4o_norway",
    "doubao_seed_pro": "doubao_seed_lite",
    "gemini_3_1_pro": "gemini_3_pro",
    "gemini_3_pro": "gemini_2_5_pro",
    "o3_deep_research": "gpt_5_4",  # o3 失败降级到 gpt-5.4
}


# ============================================================
# 模型路由辅助函数 —— 深度研究专用模型分层配置
# ============================================================
def _get_model_for_role(role: str) -> str:
    """深度研究 v2: 各角色模型分配

    原则:
    - CTO/CPO: gpt_5_4（最强推理）→ gpt_4o_norway
    - CMO: doubao_seed_pro（中文互联网）→ doubao_seed_lite
    - CDO: gemini_3_1_pro（多模态）→ gemini_3_pro
    """
    role_model_map = {
        "CTO": "gpt_5_4",
        "CMO": "doubao_seed_pro",
        "CDO": "gemini_3_1_pro",
        "CPO": "gpt_5_4",
    }
    return role_model_map.get(role.upper(), "gpt_5_4")


def _get_model_for_task(task_type: str) -> str:
    """深度研究 v2: 各环节模型分配

    分层:
    - 搜索: o3_deep_research + doubao_seed_pro（并行）
    - 提炼: gemini_2_5_flash（便宜无限额）
    - 整合: gpt_5_4（最强推理）
    - Critic: gemini_3_1_pro（独立于 synthesis 模型）
    """
    task_model_map = {
        "discovery": "gemini_2_5_flash",
        "query_generation": "gemini_2_5_flash",
        "data_extraction": "gemini_2_5_flash",    # Layer 2 提炼
        "role_assign": "gemini_2_5_flash",
        "synthesis": "gpt_5_4",                    # Layer 4
        "re_synthesis": "gpt_5_4",
        "final_synthesis": "gpt_5_4",
        "critic_challenge": "gemini_3_1_pro",      # Layer 5
        "consistency_check": "gemini_3_1_pro",
        "knowledge_extract": "gemini_2_5_flash",
        "fix": "gemini_2_5_pro",
        "cdo_fix": "gemini_2_5_pro",
        "chinese_search": "doubao_seed_pro",
        "deep_research_search": "o3_deep_research",
    }
    return task_model_map.get(task_type, "gpt_5_4")


def _call_model(model_name: str, prompt: str, system_prompt: str = None, task_type: str = "general") -> dict:
    """统一模型调用入口，自动降级"""
    result = gateway.call(model_name, prompt, system_prompt, task_type)
    if result.get("success"):
        return result

    # 自动降级
    fallback = FALLBACK_MAP.get(model_name)
    if fallback and fallback in gateway.models:
        print(f"  [Degrade] {model_name} failed, trying {fallback}")
        result2 = gateway.call(fallback, prompt, system_prompt, task_type)
        result2["degraded_from"] = model_name
        return result2

    return result


def _call_with_backoff(model_name: str, prompt: str, system_prompt: str = None,
                        task_type: str = "general", max_retries: int = 3) -> dict:
    """带限流退避的模型调用（用于 Layer 1/2/3 并发场景）"""
    sem_key = _get_sem_key(model_name)
    sem = PROVIDER_SEMAPHORES.get(sem_key)

    result = None
    for attempt in range(max_retries + 1):
        if sem:
            sem.acquire()
        try:
            result = _call_model(model_name, prompt, system_prompt, task_type)

            # 检查限流
            error = result.get("error", "")
            is_rate_limit = ("429" in str(error) or "rate" in str(error).lower()
                            or "quota" in str(error).lower()
                            or "RESOURCE_EXHAUSTED" in str(error))

            if is_rate_limit and attempt < max_retries:
                wait = (2 ** attempt) * 10  # 10s, 20s, 40s
                print(f"  [RateLimit] {model_name} attempt {attempt+1}, "
                      f"waiting {wait}s...")
                time.sleep(wait)
                continue

            return result
        finally:
            if sem:
                sem.release()

    return result  # 最后一次的结果