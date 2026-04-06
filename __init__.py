"""
scripts/deep_research — 深度研究管道（重构自 tonight_deep_research.py）

公开接口:
    run_all()                 — 运行内置 JDM 研究任务
    run_deep_learning()       — 深度学习主调度器（7h 窗口）
    run_research_from_file()  — 从 markdown 文件运行研究
    deep_research_one()       — 单任务研究（五层管道）
    deep_drill()              — 深钻模式
    stress_test_product()     — 压力测试
    sandbox_what_if()         — 沙盘推演
"""
from scripts.deep_research.runner import (
    run_all,
    run_deep_learning,
    run_research_from_file,
    parse_research_tasks_from_md,
    RESEARCH_TASKS,
)
from scripts.deep_research.pipeline import (
    deep_research_one,
    deep_drill,
)
from scripts.deep_research.learning import (
    stress_test_product,
    sandbox_what_if,
)
from scripts.deep_research.models import FALLBACK_MAP

__all__ = [
    "run_all",
    "run_deep_learning",
    "run_research_from_file",
    "parse_research_tasks_from_md",
    "deep_research_one",
    "deep_drill",
    "stress_test_product",
    "sandbox_what_if",
    "RESEARCH_TASKS",
    "FALLBACK_MAP",
]
