"""
@description: 分层记忆系统 - 解决Claude Code上下文压缩导致的信息丢失
@dependencies: json, datetime, hashlib
@last_modified: 2026-03-17

核心设计：
1. 短期记忆 (Session Memory) - 当前会话关键信息，实时更新
2. 中期记忆 (Working Memory) - 任务相关上下文，任务结束归档
3. 长期记忆 (Long-term Memory) - 项目知识库，永久存储
4. 检查点机制 (Checkpoint) - 定期生成摘要，防止压缩丢失

使用场景：
- 会话开始：加载长期记忆 + 恢复未完成任务
- 任务执行：更新短期记忆，定期检查点
- 任务结束：归档到中期记忆，更新长期记忆
- 会话结束：生成会话摘要，持久化关键信息
"""

import os
import json
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict, field
from enum import Enum


class MemoryLayer(Enum):
    """记忆层级"""
    SESSION = "session"        # 短期：当前会话
    WORKING = "working"        # 中期：任务相关
    LONGTERM = "longterm"      # 长期：项目知识


class InfoType(Enum):
    """信息类型"""
    DECISION = "decision"      # 决策
    DISCOVERY = "discovery"    # 发现
    CONSTRAINT = "constraint"  # 约束
    TODO = "todo"              # 待办
    CONTEXT = "context"        # 上下文
    ERROR = "error"            # 错误记录
    INSIGHT = "insight"        # 洞见


@dataclass
class MemoryItem:
    """记忆条目"""
    id: str
    layer: MemoryLayer
    info_type: InfoType
    content: str
    importance: int  # 1-10, 10最重要
    created_at: str
    expires_at: Optional[str] = None
    source_session: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SessionCheckpoint:
    """会话检查点"""
    checkpoint_id: str
    session_id: str
    created_at: str
    summary: str                          # 摘要
    key_decisions: List[str]              # 关键决策
    key_discoveries: List[str]            # 关键发现
    active_tasks: List[str]               # 活跃任务
    pending_todos: List[str]              # 待办事项
    context_state: Dict[str, Any]         # 上下文状态
    token_count: int                      # 检查点时的token数


class LayeredMemorySystem:
    """分层记忆系统"""

    def __init__(self, memory_dir: str = None):
        if memory_dir is None:
            memory_dir = Path(__file__).parent.parent.parent / ".ai-state" / "layered_memory"

        self.memory_dir = Path(memory_dir)
        self.memory_dir.mkdir(parents=True, exist_ok=True)

        # 各层目录
        self.session_dir = self.memory_dir / "session"
        self.working_dir = self.memory_dir / "working"
        self.longterm_dir = self.memory_dir / "longterm"
        self.checkpoint_dir = self.memory_dir / "checkpoints"

        for d in [self.session_dir, self.working_dir, self.longterm_dir, self.checkpoint_dir]:
            d.mkdir(parents=True, exist_ok=True)

        # 当前会话ID
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        # 内存缓存
        self._session_cache: List[MemoryItem] = []
        self._checkpoint_counter = 0

    # === 短期记忆 (Session) ===

    def add_session_memory(self, info_type: InfoType, content: str,
                           importance: int = 5, tags: List[str] = None,
                           metadata: Dict = None) -> str:
        """
        添加短期记忆

        Args:
            info_type: 信息类型
            content: 内容
            importance: 重要性 1-10
            tags: 标签
            metadata: 元数据

        Returns:
            记忆ID
        """
        item_id = self._generate_id(info_type)

        item = MemoryItem(
            id=item_id,
            layer=MemoryLayer.SESSION,
            info_type=info_type,
            content=content,
            importance=importance,
            created_at=datetime.now().isoformat(),
            source_session=self.session_id,
            tags=tags or [],
            metadata=metadata or {}
        )

        self._session_cache.append(item)
        self._save_item(item)

        return item_id

    def record_decision(self, decision: str, reason: str, importance: int = 7):
        """记录决策"""
        return self.add_session_memory(
            InfoType.DECISION,
            decision,
            importance=importance,
            metadata={"reason": reason}
        )

    def record_discovery(self, discovery: str, source: str = None, importance: int = 6):
        """记录发现"""
        return self.add_session_memory(
            InfoType.DISCOVERY,
            discovery,
            importance=importance,
            metadata={"source": source}
        )

    def record_constraint(self, constraint: str, scope: str = "global", importance: int = 8):
        """记录约束"""
        return self.add_session_memory(
            InfoType.CONSTRAINT,
            constraint,
            importance=importance,
            tags=[scope],
            metadata={"scope": scope}
        )

    def record_error(self, error: str, context: str = None, importance: int = 5):
        """记录错误"""
        return self.add_session_memory(
            InfoType.ERROR,
            error,
            importance=importance,
            metadata={"context": context, "resolved": False}
        )

    def add_todo(self, task: str, priority: str = "medium"):
        """添加待办"""
        return self.add_session_memory(
            InfoType.TODO,
            task,
            importance={"high": 8, "medium": 5, "low": 3}.get(priority, 5),
            tags=[priority]
        )

    def get_session_summary(self) -> Dict[str, Any]:
        """获取当前会话摘要"""
        summary = {
            "session_id": self.session_id,
            "total_items": len(self._session_cache),
            "by_type": {},
            "by_importance": {"high": 0, "medium": 0, "low": 0},
            "key_items": []
        }

        for item in self._session_cache:
            # 按类型统计
            type_name = item.info_type.value
            summary["by_type"][type_name] = summary["by_type"].get(type_name, 0) + 1

            # 按重要性统计
            if item.importance >= 7:
                summary["by_importance"]["high"] += 1
                summary["key_items"].append({
                    "type": type_name,
                    "content": item.content[:100],
                    "importance": item.importance
                })
            elif item.importance >= 4:
                summary["by_importance"]["medium"] += 1
            else:
                summary["by_importance"]["low"] += 1

        return summary

    # === 检查点机制 ===

    def create_checkpoint(self, summary: str = None, token_count: int = 0) -> SessionCheckpoint:
        """
        创建检查点

        Args:
            summary: 会话摘要（可由大模型生成）
            token_count: 当前token数

        Returns:
            检查点对象
        """
        self._checkpoint_counter += 1
        checkpoint_id = f"ckpt_{self.session_id}_{self._checkpoint_counter:03d}"

        # 提取关键信息
        key_decisions = [item.content for item in self._session_cache
                        if item.info_type == InfoType.DECISION and item.importance >= 7]

        key_discoveries = [item.content for item in self._session_cache
                          if item.info_type == InfoType.DISCOVERY and item.importance >= 6]

        active_tasks = [item.content for item in self._session_cache
                       if item.info_type == InfoType.TODO]

        pending_todos = [item.content for item in self._session_cache
                        if item.info_type == InfoType.TODO]

        # 上下文状态
        context_state = {
            "model_config": "GPT-5.4 + Gemini 3.1 Pro",
            "active_agents": ["CPO", "CTO", "CMO", "CPO_Critic", "CRO"],
            "session_items": len(self._session_cache)
        }

        checkpoint = SessionCheckpoint(
            checkpoint_id=checkpoint_id,
            session_id=self.session_id,
            created_at=datetime.now().isoformat(),
            summary=summary or f"检查点 #{self._checkpoint_counter}",
            key_decisions=key_decisions,
            key_discoveries=key_discoveries,
            active_tasks=active_tasks,
            pending_todos=pending_todos,
            context_state=context_state,
            token_count=token_count
        )

        # 保存检查点
        self._save_checkpoint(checkpoint)

        return checkpoint

    def restore_from_checkpoint(self, checkpoint_id: str = None) -> Optional[SessionCheckpoint]:
        """
        从检查点恢复

        Args:
            checkpoint_id: 检查点ID，None则恢复最新

        Returns:
            检查点对象
        """
        if checkpoint_id:
            path = self.checkpoint_dir / f"{checkpoint_id}.json"
        else:
            # 找最新的检查点
            checkpoints = sorted(self.checkpoint_dir.glob("ckpt_*.json"))
            if not checkpoints:
                return None
            path = checkpoints[-1]

        if not path.exists():
            return None

        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        return SessionCheckpoint(**data)

    # === 中期记忆 (Working) ===

    def archive_to_working(self, task_id: str, task_summary: Dict):
        """
        归档任务到中期记忆

        Args:
            task_id: 任务ID
            task_summary: 任务摘要
        """
        item = MemoryItem(
            id=f"task_{task_id}",
            layer=MemoryLayer.WORKING,
            info_type=InfoType.CONTEXT,
            content=json.dumps(task_summary, ensure_ascii=False),
            importance=7,
            created_at=datetime.now().isoformat(),
            source_session=self.session_id
        )

        self._save_item(item)

    # === 长期记忆 (Long-term) ===

    def promote_to_longterm(self, item_id: str):
        """
        将重要记忆提升为长期记忆

        Args:
            item_id: 记忆ID
        """
        item = self._load_item(item_id)
        if not item:
            return False

        # 创建长期记忆
        longterm_item = MemoryItem(
            id=f"longterm_{item.id}",
            layer=MemoryLayer.LONGTERM,
            info_type=item.info_type,
            content=item.content,
            importance=item.importance,
            created_at=item.created_at,
            source_session=item.source_session,
            tags=item.tags,
            metadata=item.metadata
        )

        self._save_item(longterm_item)
        return True

    def get_longterm_context(self) -> Dict[str, Any]:
        """获取长期记忆上下文"""
        context = {
            "decisions": [],
            "constraints": [],
            "insights": []
        }

        for path in self.longterm_dir.glob("*.json"):
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                item = MemoryItem(
                    id=data["id"],
                    layer=MemoryLayer(data["layer"]),
                    info_type=InfoType(data["info_type"]),
                    content=data["content"],
                    importance=data["importance"],
                    created_at=data["created_at"],
                    source_session=data.get("source_session"),
                    tags=data.get("tags", []),
                    metadata=data.get("metadata", {})
                )

                if item.info_type == InfoType.DECISION:
                    context["decisions"].append(item.content)
                elif item.info_type == InfoType.CONSTRAINT:
                    context["constraints"].append(item.content)
                elif item.info_type == InfoType.INSIGHT:
                    context["insights"].append(item.content)

        return context

    # === 会话管理 ===

    def generate_session_summary_for_llm(self) -> str:
        """
        生成供大模型使用的会话摘要

        Returns:
            格式化的摘要文本
        """
        summary = self.get_session_summary()
        checkpoint = self.restore_from_checkpoint()

        lines = [
            "# 当前会话上下文摘要",
            "",
            f"**会话ID**: {self.session_id}",
            f"**记忆条目**: {summary['total_items']}",
            "",
            "## 关键决策",
        ]

        for item in summary.get("key_items", []):
            if item["type"] == "decision":
                lines.append(f"- {item['content']}")

        lines.extend([
            "",
            "## 重要发现",
        ])

        for item in summary.get("key_items", []):
            if item["type"] == "discovery":
                lines.append(f"- {item['content']}")

        if checkpoint:
            lines.extend([
                "",
                "## 最近检查点",
                f"- 时间: {checkpoint.created_at}",
                f"- 待办: {len(checkpoint.pending_todos)} 项",
            ])

            if checkpoint.key_decisions:
                lines.append("- 决策: " + "; ".join(checkpoint.key_decisions[:3]))

        return "\n".join(lines)

    def export_for_claude_md(self) -> str:
        """
        导出为 CLAUDE.md 格式的上下文

        Returns:
            Markdown格式的上下文
        """
        longterm = self.get_longterm_context()
        summary = self.get_session_summary()

        lines = [
            "# 项目上下文 (自动生成)",
            "",
            "## 长期决策",
        ]

        for d in longterm["decisions"][:10]:
            lines.append(f"- {d}")

        lines.extend([
            "",
            "## 项目约束",
        ])

        for c in longterm["constraints"][:10]:
            lines.append(f"- {c}")

        lines.extend([
            "",
            "## 本次会话",
            f"- 会话ID: {self.session_id}",
            f"- 关键条目: {len(summary['key_items'])}",
        ])

        return "\n".join(lines)

    # === 工具方法 ===

    def _generate_id(self, info_type: InfoType) -> str:
        """生成唯一ID"""
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
        return f"{info_type.value}_{timestamp}"

    def _save_item(self, item: MemoryItem):
        """保存记忆条目"""
        dir_map = {
            MemoryLayer.SESSION: self.session_dir,
            MemoryLayer.WORKING: self.working_dir,
            MemoryLayer.LONGTERM: self.longterm_dir
        }

        target_dir = dir_map.get(item.layer, self.session_dir)
        path = target_dir / f"{item.id}.json"

        data = asdict(item)
        data["layer"] = item.layer.value
        data["info_type"] = item.info_type.value

        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _load_item(self, item_id: str) -> Optional[MemoryItem]:
        """加载记忆条目"""
        for layer_dir in [self.session_dir, self.working_dir, self.longterm_dir]:
            path = layer_dir / f"{item_id}.json"
            if path.exists():
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return MemoryItem(
                        id=data["id"],
                        layer=MemoryLayer(data["layer"]),
                        info_type=InfoType(data["info_type"]),
                        content=data["content"],
                        importance=data["importance"],
                        created_at=data["created_at"],
                        expires_at=data.get("expires_at"),
                        source_session=data.get("source_session"),
                        tags=data.get("tags", []),
                        metadata=data.get("metadata", {})
                    )
        return None

    def _save_checkpoint(self, checkpoint: SessionCheckpoint):
        """保存检查点"""
        path = self.checkpoint_dir / f"{checkpoint.checkpoint_id}.json"
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(asdict(checkpoint), f, ensure_ascii=False, indent=2)

    def cleanup_session(self, keep_important: bool = True):
        """
        清理会话记忆

        Args:
            keep_important: 是否保留重要条目
        """
        if keep_important:
            # 将重要条目提升为长期记忆
            for item in self._session_cache:
                if item.importance >= 8:
                    self.promote_to_longterm(item.id)

        # 清理会话缓存
        self._session_cache.clear()

        # 清理会话文件（保留检查点）
        for f in self.session_dir.glob("*.json"):
            f.unlink()


# === 全局实例 ===

_layered_memory: Optional[LayeredMemorySystem] = None


def get_layered_memory() -> LayeredMemorySystem:
    """获取分层记忆系统实例"""
    global _layered_memory
    if _layered_memory is None:
        _layered_memory = LayeredMemorySystem()
    return _layered_memory


# === 便捷函数 ===

def remember_decision(decision: str, reason: str, importance: int = 7):
    """记录决策"""
    return get_layered_memory().record_decision(decision, reason, importance)

def remember_discovery(discovery: str, source: str = None, importance: int = 6):
    """记录发现"""
    return get_layered_memory().record_discovery(discovery, source, importance)

def remember_constraint(constraint: str, scope: str = "global", importance: int = 8):
    """记录约束"""
    return get_layered_memory().record_constraint(constraint, scope, importance)

def checkpoint(summary: str = None, token_count: int = 0):
    """创建检查点"""
    return get_layered_memory().create_checkpoint(summary, token_count)


# === 测试 ===

if __name__ == "__main__":
    print("=" * 60)
    print("[LAYERED MEMORY SYSTEM TEST]")
    print("=" * 60)

    mem = get_layered_memory()

    # 测试短期记忆
    print("\n[TEST] Adding session memories...")
    mem.record_decision("使用GPT-5.4作为主力模型", "Azure API已连通", importance=9)
    mem.record_discovery("Gemini 3.1 Pro 可用", "Google AI Studio", importance=7)
    mem.record_constraint("上下文压缩会导致信息丢失", "system", importance=10)
    mem.add_todo("实现分层记忆系统", "high")
    mem.add_todo("更新CLAUDE.md上下文入口", "medium")

    # 测试摘要
    print("\n[RESULT] Session Summary:")
    summary = mem.get_session_summary()
    print(f"  Total items: {summary['total_items']}")
    print(f"  By type: {summary['by_type']}")
    print(f"  High importance: {summary['by_importance']['high']}")

    # 测试检查点
    print("\n[TEST] Creating checkpoint...")
    ckpt = mem.create_checkpoint("初始记忆系统测试完成", token_count=5000)
    print(f"  Checkpoint ID: {ckpt.checkpoint_id}")
    print(f"  Key decisions: {len(ckpt.key_decisions)}")
    print(f"  Pending todos: {len(ckpt.pending_todos)}")

    # 测试LLM摘要
    print("\n[RESULT] LLM Summary:")
    print(mem.generate_session_summary_for_llm()[:500])

    print("\n" + "=" * 60)