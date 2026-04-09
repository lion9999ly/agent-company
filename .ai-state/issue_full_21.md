# Day 17 系统全量审计 - scripts/feishu_handlers/notify_rules.py

```python
"""
@description: 飞书通知降噪配置
@dependencies: json, pathlib
@last_modified: 2026-04-08
"""
import json
from pathlib import Path
from typing import Optional

NOTIFY_CONFIG_PATH = Path(".ai-state/notify_config.json")
_notify_config = None


def load_notify_config() -> dict:
    """加载通知配置"""
    global _notify_config
    if _notify_config is not None:
        return _notify_config

    if NOTIFY_CONFIG_PATH.exists():
        try:
            _notify_config = json.loads(NOTIFY_CONFIG_PATH.read_text(encoding="utf-8"))
            return _notify_config
        except:
            pass

    # 默认配置：全部开启
    return {
        "deep_research": {"start": True, "progress": True, "complete": True, "error": True},
        "competitor_monitor": {"start": True, "no_update": True, "has_update": True, "error": True},
        "auto_learn": {"start": True, "progress": True, "complete": True, "error": True},
        "roundtable": {"start": True, "phase_complete": True, "convergence": True, "task_complete": True, "error": True},
        "kb_governance": {"start": True, "complete": True, "error": True},
    }


def should_notify(task_type: str, event: str) -> bool:
    """检查是否应该发送通知

    Args:
        task_type: 任务类型 (deep_research, competitor_monitor, auto_learn, roundtable, kb_governance)
        event: 事件类型 (start, progress, complete, error, no_update, has_update, phase_complete, convergence, task_complete)

    Returns:
        bool: 是否应该发送通知
    """
    config = load_notify_config()
    task_config = config.get(task_type, {})
    return task_config.get(event, True)  # 默认开启


def get_notify_description(task_type: str) -> str:
    """获取任务类型的通知规则描述"""
    config = load_notify_config()
    task_config = config.get(task_type, {})
    return task_config.get("description", "")
```
