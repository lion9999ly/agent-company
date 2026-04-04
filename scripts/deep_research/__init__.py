"""
@description: 深度研究管道 v2 — 模块包
@dependencies: 各子模块
@last_modified: 2026-04-04

拆分自 scripts/tonight_deep_research.py（2168行）
"""
# 从各子模块导入并重新导出，保持向后兼容
from scripts.deep_research.config import (
    PROVIDER_SEMAPHORES,
    FALLBACK_MAP,
    _get_sem_key,
    _get_model_for_role,
    _get_model_for_task,
    _call_model,
    _call_with_backoff,
    gateway,
)

from scripts.deep_research.schemas import (
    OPTICAL_BENCHMARK_SCHEMA,
    LAYOUT_ANALYSIS_SCHEMA,
    HARDWARE_LAYOUT_SCHEMA,
    GENERAL_SCHEMA,
)

# 注意：以下函数仍在主文件中定义，通过主入口文件暴露
# - _match_expert_framework
# - _get_kb_context_enhanced
# - _extract_structured_data
# - _run_critic_challenge
# - deep_research_one
# - run_deep_learning
# - run_research_from_file
# - run_all
# - 等其他函数

__all__ = [
    # config
    "PROVIDER_SEMAPHORES",
    "FALLBACK_MAP",
    "_get_sem_key",
    "_get_model_for_role",
    "_get_model_for_task",
    "_call_model",
    "_call_with_backoff",
    "gateway",
    # schemas
    "OPTICAL_BENCHMARK_SCHEMA",
    "LAYOUT_ANALYSIS_SCHEMA",
    "HARDWARE_LAYOUT_SCHEMA",
    "GENERAL_SCHEMA",
]