"""
@description: 自动检查点脚本 - 定期创建会话摘要检查点
@dependencies: layered_memory, model_gateway
@last_modified: 2026-03-17

使用方式：
1. 任务开始时调用 start_session()
2. 任务进行中调用 checkpoint()
3. 任务结束时调用 end_session()
"""

import json
from datetime import datetime
from typing import Optional, Dict, Any

try:
    from src.tools.layered_memory import get_layered_memory, InfoType
    HAS_LAYERED_MEMORY = True
except ImportError:
    HAS_LAYERED_MEMORY = False

try:
    from src.utils.token_usage_tracker import get_tracker
    HAS_TRACKER = True
except ImportError:
    HAS_TRACKER = False


class SessionManager:
    """会话管理器 - 自动检查点"""

    def __init__(self):
        self.session_start = datetime.now()
        self.checkpoint_count = 0
        self.tasks_completed = 0
        self.current_task: Optional[str] = None

    def start_session(self, task_description: str = None) -> Dict[str, Any]:
        """
        开始会话

        Args:
            task_description: 任务描述

        Returns:
            会话信息
        """
        self.session_start = datetime.now()
        self.current_task = task_description

        if HAS_LAYERED_MEMORY:
            mem = get_layered_memory()
            mem.record_decision(
                f"会话开始: {task_description or '未指定任务'}",
                "用户发起新会话",
                importance=5
            )

        return {
            "session_id": self._get_session_id(),
            "started_at": self.session_start.isoformat(),
            "task": task_description
        }

    def checkpoint(self, summary: str = None, force: bool = False) -> Dict[str, Any]:
        """
        创建检查点

        Args:
            summary: 摘要描述
            force: 强制创建（忽略间隔限制）

        Returns:
            检查点信息
        """
        self.checkpoint_count += 1

        # 获取token使用情况
        token_count = 0
        if HAS_TRACKER:
            try:
                tracker = get_tracker()
                usage = tracker.get_usage_summary()
                token_count = usage.get("total_tokens", 0)
            except Exception:
                pass

        checkpoint_data = {
            "checkpoint_number": self.checkpoint_count,
            "created_at": datetime.now().isoformat(),
            "summary": summary or f"检查点 #{self.checkpoint_count}",
            "token_count": token_count,
            "tasks_completed": self.tasks_completed
        }

        if HAS_LAYERED_MEMORY:
            mem = get_layered_memory()
            mem.create_checkpoint(summary, token_count)

        return checkpoint_data

    def end_session(self, outcome: str = None) -> Dict[str, Any]:
        """
        结束会话

        Args:
            outcome: 会话结果

        Returns:
            会话总结
        """
        end_time = datetime.now()
        duration = (end_time - self.session_start).total_seconds()

        session_summary = {
            "session_id": self._get_session_id(),
            "started_at": self.session_start.isoformat(),
            "ended_at": end_time.isoformat(),
            "duration_seconds": int(duration),
            "checkpoints_created": self.checkpoint_count,
            "tasks_completed": self.tasks_completed,
            "outcome": outcome
        }

        # 归档重要信息到长期记忆
        if HAS_LAYERED_MEMORY and outcome:
            mem = get_layered_memory()
            mem.record_decision(
                f"会话结束: {outcome}",
                f"历时{int(duration)}秒, 完成{self.tasks_completed}个任务",
                importance=6
            )

        return session_summary

    def complete_task(self, task_name: str, result: str = None):
        """
        完成任务

        Args:
            task_name: 任务名称
            result: 任务结果
        """
        self.tasks_completed += 1

        if HAS_LAYERED_MEMORY:
            mem = get_layered_memory()
            mem.add_session_memory(
                InfoType.CONTEXT,
                f"完成任务: {task_name} - {result or '成功'}",
                importance=6,
                tags=["completed"]
            )

    def _get_session_id(self) -> str:
        """获取会话ID"""
        return self.session_start.strftime("%Y%m%d_%H%M%S")


# === 全局实例 ===

_session_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    """获取会话管理器"""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager


# === 便捷函数 ===

def start_session(task: str = None) -> Dict[str, Any]:
    """开始会话"""
    return get_session_manager().start_session(task)

def checkpoint(summary: str = None) -> Dict[str, Any]:
    """创建检查点"""
    return get_session_manager().checkpoint(summary)

def end_session(outcome: str = None) -> Dict[str, Any]:
    """结束会话"""
    return get_session_manager().end_session(outcome)

def complete_task(task: str, result: str = None):
    """完成任务"""
    get_session_manager().complete_task(task, result)


# === CLI入口 ===

if __name__ == "__main__":
    import sys

    print("=" * 60)
    print("[SESSION MANAGER TEST]")
    print("=" * 60)

    # 模拟会话
    sm = get_session_manager()

    print("\n[TEST] Starting session...")
    info = sm.start_session("升级模型配置和记忆系统")
    print(f"  Session ID: {info['session_id']}")

    print("\n[TEST] Creating checkpoints...")
    ckpt1 = sm.checkpoint("模型配置更新完成")
    print(f"  Checkpoint 1: {ckpt1['checkpoint_number']}")

    sm.complete_task("更新model_registry.yaml", "添加GPT-5.4等旗舰模型")
    sm.complete_task("创建layered_memory.py", "实现分层记忆系统")

    ckpt2 = sm.checkpoint("记忆系统实现完成")
    print(f"  Checkpoint 2: {ckpt2['checkpoint_number']}")

    print("\n[TEST] Ending session...")
    summary = sm.end_session("成功升级模型阵列和记忆系统")
    print(f"  Duration: {summary['duration_seconds']}s")
    print(f"  Tasks completed: {summary['tasks_completed']}")
    print(f"  Checkpoints: {summary['checkpoints_created']}")

    print("\n" + "=" * 60)