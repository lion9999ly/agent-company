"""
@description: Echo长期记忆管理器 - 项目上下文、用户偏好、历史决策
@dependencies: json, yaml, datetime, uuid
@last_modified: 2026-03-17

Echo(CPO)重新定位：从"调度中枢"转型为"基础设施守护者"
核心职责：长期记忆管家、跨会话协调器、行为审计官、模型路由守门
"""

import os
import json
import yaml
import time
import hashlib
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum


class MemoryType(Enum):
    PROJECT_CONTEXT = "project_context"
    USER_PREFERENCE = "user_preference"
    DECISION_LOG = "decision_log"
    TASK_STATE = "task_state"
    BEHAVIOR_LOG = "behavior_log"


@dataclass
class MemoryEntry:
    id: str
    type: MemoryType
    key: str
    value: Any
    created_at: str
    updated_at: str
    ttl: Optional[int] = None  # 秒，None表示永久
    metadata: Dict[str, Any] = None


class EchoMemoryManager:
    """
    Echo长期记忆管理器

    职责：
    1. 项目上下文管理：维护项目背景、技术栈、团队信息
    2. 用户偏好管理：记录用户习惯、关注点、决策风格
    3. 历史决策管理：记录重要决策及其上下文
    4. 跨会话状态：支持任务中断后恢复

    存储：
    - 默认存储在 .ai-state/memory/ 目录
    - 支持JSON和YAML格式
    - 支持TTL过期清理
    """

    def __init__(self, memory_dir: str = None):
        if memory_dir is None:
            memory_dir = Path(__file__).parent.parent.parent / ".ai-state" / "memory"

        self.memory_dir = Path(memory_dir)
        self.memory_dir.mkdir(parents=True, exist_ok=True)

        # 子目录
        self.context_dir = self.memory_dir / "context"
        self.preference_dir = self.memory_dir / "preference"
        self.decision_dir = self.memory_dir / "decision"
        self.state_dir = self.memory_dir / "state"
        self.behavior_dir = self.memory_dir / "behavior"

        for d in [self.context_dir, self.preference_dir, self.decision_dir,
                  self.state_dir, self.behavior_dir]:
            d.mkdir(parents=True, exist_ok=True)

        # 内存缓存
        self._cache: Dict[str, MemoryEntry] = {}

    def save(self, memory_type: MemoryType, key: str, value: Any,
             ttl: Optional[int] = None, metadata: Dict = None) -> str:
        """
        保存记忆

        Args:
            memory_type: 记忆类型
            key: 键名
            value: 值
            ttl: 过期时间（秒），None表示永久
            metadata: 元数据

        Returns:
            记忆ID
        """
        now = datetime.now().isoformat()
        entry_id = self._generate_id(memory_type, key)

        entry = MemoryEntry(
            id=entry_id,
            type=memory_type,
            key=key,
            value=value,
            created_at=now,
            updated_at=now,
            ttl=ttl,
            metadata=metadata or {}
        )

        # 保存到文件
        file_path = self._get_file_path(memory_type, key)
        with open(file_path, 'w', encoding='utf-8') as f:
            # 将MemoryType枚举转换为字符串值
            entry_dict = asdict(entry)
            entry_dict['type'] = entry_dict['type'].value
            json.dump(entry_dict, f, ensure_ascii=False, indent=2)

        # 更新缓存
        self._cache[entry_id] = entry

        return entry_id

    def load(self, memory_type: MemoryType, key: str) -> Optional[Any]:
        """
        加载记忆

        Returns:
            记忆值，不存在或过期返回None
        """
        entry = self._load_entry(memory_type, key)

        if entry is None:
            return None

        # 检查过期
        if entry.ttl and self._is_expired(entry):
            self.delete(memory_type, key)
            return None

        return entry.value

    def _load_entry(self, memory_type: MemoryType, key: str) -> Optional[MemoryEntry]:
        """加载记忆条目"""
        entry_id = self._generate_id(memory_type, key)

        # 检查缓存
        if entry_id in self._cache:
            return self._cache[entry_id]

        # 从文件加载
        file_path = self._get_file_path(memory_type, key)
        if not file_path.exists():
            return None

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # 将字符串type转换回MemoryType枚举
                data['type'] = MemoryType(data['type'])
                entry = MemoryEntry(**data)
                self._cache[entry_id] = entry
                return entry
        except Exception:
            return None

    def delete(self, memory_type: MemoryType, key: str) -> bool:
        """删除记忆"""
        entry_id = self._generate_id(memory_type, key)

        # 从缓存删除
        if entry_id in self._cache:
            del self._cache[entry_id]

        # 从文件删除
        file_path = self._get_file_path(memory_type, key)
        if file_path.exists():
            file_path.unlink()
            return True

        return False

    def list_keys(self, memory_type: MemoryType) -> List[str]:
        """列出某类型下所有键"""
        dir_map = {
            MemoryType.PROJECT_CONTEXT: self.context_dir,
            MemoryType.USER_PREFERENCE: self.preference_dir,
            MemoryType.DECISION_LOG: self.decision_dir,
            MemoryType.TASK_STATE: self.state_dir,
            MemoryType.BEHAVIOR_LOG: self.behavior_dir
        }

        target_dir = dir_map.get(memory_type)
        if not target_dir or not target_dir.exists():
            return []

        keys = []
        for f in target_dir.glob("*.json"):
            # 从文件名提取key
            key = f.stem
            keys.append(key)

        return keys

    # === 项目上下文管理 ===

    def set_project_context(self, key: str, value: Any):
        """设置项目上下文"""
        return self.save(MemoryType.PROJECT_CONTEXT, key, value)

    def get_project_context(self, key: str) -> Optional[Any]:
        """获取项目上下文"""
        return self.load(MemoryType.PROJECT_CONTEXT, key)

    def get_all_project_context(self) -> Dict[str, Any]:
        """获取所有项目上下文"""
        result = {}
        for key in self.list_keys(MemoryType.PROJECT_CONTEXT):
            value = self.load(MemoryType.PROJECT_CONTEXT, key)
            if value is not None:
                result[key] = value
        return result

    # === 用户偏好管理 ===

    def set_user_preference(self, key: str, value: Any):
        """设置用户偏好"""
        return self.save(MemoryType.USER_PREFERENCE, key, value)

    def get_user_preference(self, key: str, default: Any = None) -> Any:
        """获取用户偏好"""
        value = self.load(MemoryType.USER_PREFERENCE, key)
        return value if value is not None else default

    # === 决策日志 ===

    def log_decision(self, decision: str, context: Dict, outcome: str = None):
        """记录决策"""
        import uuid
        decision_id = f"decision_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

        self.save(
            MemoryType.DECISION_LOG,
            decision_id,
            {
                "decision": decision,
                "context": context,
                "outcome": outcome,
                "timestamp": datetime.now().isoformat()
            }
        )

        return decision_id

    def get_recent_decisions(self, limit: int = 10) -> List[Dict]:
        """获取最近的决策"""
        keys = self.list_keys(MemoryType.DECISION_LOG)
        # 按时间排序
        keys.sort(reverse=True)

        decisions = []
        for key in keys[:limit]:
            value = self.load(MemoryType.DECISION_LOG, key)
            if value:
                decisions.append(value)

        return decisions

    # === 跨会话状态 ===

    def save_task_state(self, task_id: str, state: Dict):
        """保存任务状态"""
        return self.save(MemoryType.TASK_STATE, task_id, state)

    def load_task_state(self, task_id: str) -> Optional[Dict]:
        """加载任务状态"""
        return self.load(MemoryType.TASK_STATE, task_id)

    def list_pending_tasks(self) -> List[str]:
        """列出未完成的任务"""
        return self.list_keys(MemoryType.TASK_STATE)

    # === 行为日志 ===

    def log_behavior(self, agent: str, action: str, details: Dict = None):
        """记录Agent行为"""
        import uuid
        log_id = f"behavior_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

        self.save(
            MemoryType.BEHAVIOR_LOG,
            log_id,
            {
                "agent": agent,
                "action": action,
                "details": details or {},
                "timestamp": datetime.now().isoformat()
            },
            ttl=86400 * 7  # 行为日志保留7天
        )

    # === 工具方法 ===

    def _generate_id(self, memory_type: MemoryType, key: str) -> str:
        """生成记忆ID"""
        return f"{memory_type.value}:{key}"

    def _get_file_path(self, memory_type: MemoryType, key: str) -> Path:
        """获取记忆文件路径"""
        safe_key = self._sanitize_key(key)

        dir_map = {
            MemoryType.PROJECT_CONTEXT: self.context_dir,
            MemoryType.USER_PREFERENCE: self.preference_dir,
            MemoryType.DECISION_LOG: self.decision_dir,
            MemoryType.TASK_STATE: self.state_dir,
            MemoryType.BEHAVIOR_LOG: self.behavior_dir
        }

        return dir_map.get(memory_type, self.memory_dir) / f"{safe_key}.json"

    def _sanitize_key(self, key: str) -> str:
        """清理键名，确保可做文件名"""
        # 替换特殊字符
        safe = key.replace("/", "_").replace("\\", "_").replace(":", "_")
        return safe[:100]  # 限制长度

    def _is_expired(self, entry: MemoryEntry) -> bool:
        """检查记忆是否过期"""
        if not entry.ttl:
            return False

        created = datetime.fromisoformat(entry.created_at)
        now = datetime.now()
        elapsed = (now - created).total_seconds()

        return elapsed > entry.ttl

    def cleanup_expired(self) -> int:
        """清理过期记忆"""
        count = 0
        for memory_type in MemoryType:
            for key in self.list_keys(memory_type):
                entry = self._load_entry(memory_type, key)
                if entry and self._is_expired(entry):
                    self.delete(memory_type, key)
                    count += 1
        return count

    def export_memory(self, output_path: str = None) -> Dict:
        """导出所有记忆"""
        if output_path is None:
            output_path = self.memory_dir / "memory_export.json"

        export = {
            "exported_at": datetime.now().isoformat(),
            "memories": {}
        }

        for memory_type in MemoryType:
            export["memories"][memory_type.value] = {}
            for key in self.list_keys(memory_type):
                value = self.load(memory_type, key)
                if value is not None:
                    export["memories"][memory_type.value][key] = value

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(export, f, ensure_ascii=False, indent=2)

        return export


# 全局实例
_memory_manager: Optional[EchoMemoryManager] = None


def get_memory_manager() -> EchoMemoryManager:
    """获取全局记忆管理器"""
    global _memory_manager
    if _memory_manager is None:
        _memory_manager = EchoMemoryManager()
    return _memory_manager


# === 测试 ===
if __name__ == "__main__":
    print("=" * 60)
    print("[ECHO MEMORY MANAGER TEST]")
    print("=" * 60)

    mm = get_memory_manager()

    # 测试项目上下文
    print("\n[TEST] Setting project context...")
    mm.set_project_context("project_name", "智能骑行头盔虚拟研发中心")
    mm.set_project_context("tech_stack", ["Python", "LangGraph", "Azure OpenAI"])

    # 测试用户偏好
    print("[TEST] Setting user preferences...")
    mm.set_user_preference("language", "zh-CN")
    mm.set_user_preference("detail_level", "high")

    # 测试决策日志
    print("[TEST] Logging decision...")
    mm.log_decision(
        "选择Azure GPT-4o作为主力模型",
        {"reason": "Gemini IP受限, Qwen API无效"},
        "所有Agent统一使用Azure"
    )

    # 测试导出
    print("\n[RESULT] Project context:")
    print(json.dumps(mm.get_all_project_context(), ensure_ascii=False, indent=2))

    print("\n[RESULT] User preferences:")
    print(f"  language: {mm.get_user_preference('language')}")
    print(f"  detail_level: {mm.get_user_preference('detail_level')}")

    print("\n[RESULT] Recent decisions:")
    for d in mm.get_recent_decisions(3):
        print(f"  - {d['decision']}")

    print("\n" + "=" * 60)