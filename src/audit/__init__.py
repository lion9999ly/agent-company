# 📋 审计模块 (Audit Module)
"""
审计模块：包含行为边界审计、日志记录等审计组件。

模块结构：
- behavior_logger.py: 行为边界审计日志
"""

from .behavior_logger import (
    BehaviorLogger,
    get_behavior_logger,
    log_behavior,
    BehaviorCategory,
    BehaviorSeverity,
    BehaviorLogEntry,
    BehaviorAuditReport
)

__all__ = [
    "BehaviorLogger",
    "get_behavior_logger",
    "log_behavior",
    "BehaviorCategory",
    "BehaviorSeverity",
    "BehaviorLogEntry",
    "BehaviorAuditReport"
]