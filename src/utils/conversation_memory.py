"""
@description: 飞书对话记忆管理 - 维护每个用户/群的最近对话上下文
@dependencies: json, pathlib, datetime
@last_modified: 2026-03-25
"""
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional

MEMORY_DIR = Path(__file__).resolve().parent.parent.parent / ".ai-state" / "conversations"


class ConversationMemory:
    """管理飞书对话的短期记忆"""

    def __init__(self, max_turns: int = 20, expire_minutes: int = 60):
        """
        max_turns: 保留最近多少轮对话
        expire_minutes: 超过多少分钟算过期（新对话）
        """
        self.max_turns = max_turns
        self.expire_minutes = expire_minutes
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)

    def _get_file(self, session_id: str) -> Path:
        """每个用户/群一个对话文件"""
        safe_id = "".join(c for c in session_id if c.isalnum() or c in "_-")
        return MEMORY_DIR / f"{safe_id}.json"

    def _load(self, session_id: str) -> dict:
        f = self._get_file(session_id)
        if not f.exists():
            return {"messages": [], "updated": None, "context": {}}
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            # 检查是否过期
            updated = data.get("updated")
            if updated:
                last_time = datetime.fromisoformat(updated)
                if datetime.now() - last_time > timedelta(minutes=self.expire_minutes):
                    # 过期了，开新对话但保留上一轮摘要
                    old_summary = self._summarize_old(data.get("messages", []))
                    return {
                        "messages": [],
                        "updated": None,
                        "context": {"previous_session_summary": old_summary}
                    }
            return data
        except:
            return {"messages": [], "updated": None, "context": {}}

    def _save(self, session_id: str, data: dict):
        data["updated"] = datetime.now().isoformat()
        self._get_file(session_id).write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _summarize_old(self, messages: list) -> str:
        """简单摘要过期的对话历史"""
        if not messages:
            return ""
        user_msgs = [m["content"][:100] for m in messages if m["role"] == "user"][-5:]
        return f"上一轮对话涉及: {'; '.join(user_msgs)}"

    def add_user_message(self, session_id: str, content: str):
        """记录用户消息"""
        data = self._load(session_id)
        data["messages"].append({
            "role": "user",
            "content": content,
            "time": datetime.now().isoformat()
        })
        # 保持最大轮次
        data["messages"] = data["messages"][-self.max_turns * 2:]
        self._save(session_id, data)

    def add_bot_message(self, session_id: str, content: str, action: str = "reply"):
        """记录机器人回复"""
        data = self._load(session_id)
        data["messages"].append({
            "role": "assistant",
            "content": content[:2000],  # 限制长度
            "action": action,
            "time": datetime.now().isoformat()
        })
        data["messages"] = data["messages"][-self.max_turns * 2:]
        self._save(session_id, data)

    def set_context(self, session_id: str, key: str, value):
        """设置对话上下文变量（如：等待图片prompt、等待确认等）"""
        data = self._load(session_id)
        data.setdefault("context", {})[key] = value
        self._save(session_id, data)

    def get_context(self, session_id: str, key: str, default=None):
        """获取对话上下文变量"""
        data = self._load(session_id)
        return data.get("context", {}).get(key, default)

    def clear_context(self, session_id: str, key: str = None):
        """清除上下文变量"""
        data = self._load(session_id)
        if key:
            data.get("context", {}).pop(key, None)
        else:
            data["context"] = {}
        self._save(session_id, data)

    def get_history_for_prompt(self, session_id: str, max_chars: int = 4000) -> str:
        """获取格式化的对话历史，用于注入 LLM prompt"""
        data = self._load(session_id)
        messages = data.get("messages", [])
        prev_summary = data.get("context", {}).get("previous_session_summary", "")

        if not messages and not prev_summary:
            return ""

        parts = []
        if prev_summary:
            parts.append(f"[上轮对话摘要] {prev_summary}")

        total_chars = 0
        # 从最近的开始，往前取
        for msg in reversed(messages):
            role = "用户" if msg["role"] == "user" else "助手"
            content = msg["content"][:500]
            line = f"{role}: {content}"
            if total_chars + len(line) > max_chars:
                break
            parts.insert(-1 if prev_summary else 0, line)  # 插到摘要之后
            total_chars += len(line)

        # 正序排列
        return "\n".join(parts)

    def get_last_bot_action(self, session_id: str) -> Optional[str]:
        """获取机器人上一次的动作类型"""
        data = self._load(session_id)
        for msg in reversed(data.get("messages", [])):
            if msg["role"] == "assistant":
                return msg.get("action", "reply")
        return None


_memory = None

def get_conversation_memory() -> ConversationMemory:
    global _memory
    if _memory is None:
        _memory = ConversationMemory()
    return _memory