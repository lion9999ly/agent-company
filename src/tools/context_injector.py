"""
@description: 上下文注入器 - 会话开始时自动加载关键上下文
@dependencies: json, yaml
@last_modified: 2026-03-17

核心功能：
1. 会话启动时注入关键上下文
2. 从分层记忆恢复历史状态
3. 生成上下文种子文档
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional


class ContextInjector:
    """上下文注入器"""

    def __init__(self, project_root: str = None):
        if project_root is None:
            project_root = Path(__file__).parent.parent.parent

        self.project_root = Path(project_root)
        self.memory_dir = self.project_root / ".ai-state" / "layered_memory"
        self.context_file = self.project_root / ".ai-state" / "session_context.json"

    def inject_startup_context(self) -> Dict[str, Any]:
        """
        注入启动上下文

        Returns:
            上下文字典
        """
        context = {
            "injected_at": datetime.now().isoformat(),
            "project": self._load_project_info(),
            "models": self._load_model_status(),
            "recent_decisions": self._load_recent_decisions(),
            "active_constraints": self._load_constraints(),
            "pending_todos": self._load_pending_todos(),
            "last_checkpoint": self._load_last_checkpoint()
        }

        # 保存注入的上下文
        self._save_context(context)

        return context

    def generate_context_seed(self) -> str:
        """
        生成上下文种子文档

        Returns:
            Markdown格式的种子文档
        """
        context = self.inject_startup_context()

        lines = [
            "# 🌱 会话上下文种子",
            "",
            f"> 自动注入时间: {context['injected_at']}",
            "",
            "---",
            "",
            "## 📋 项目信息",
        ]

        project = context.get("project", {})
        lines.append(f"- **项目名称**: {project.get('name', 'N/A')}")
        lines.append(f"- **技术栈**: {', '.join(project.get('tech_stack', []))}")
        lines.append(f"- **当前阶段**: {project.get('phase', 'N/A')}")

        lines.extend([
            "",
            "## 🤖 模型状态",
        ])

        models = context.get("models", {})
        for model_name, status in models.items():
            icon = "✅" if status.get("available") else "❌"
            lines.append(f"- {icon} **{model_name}**: {status.get('purpose', 'N/A')}")

        lines.extend([
            "",
            "## 📌 近期决策",
        ])

        for decision in context.get("recent_decisions", [])[:5]:
            lines.append(f"- {decision.get('content', 'N/A')}")

        lines.extend([
            "",
            "## ⚠️ 活跃约束",
        ])

        for constraint in context.get("active_constraints", [])[:5]:
            lines.append(f"- {constraint.get('content', 'N/A')}")

        pending = context.get("pending_todos", [])
        if pending:
            lines.extend([
                "",
                "## 📝 待办事项",
            ])
            for todo in pending[:5]:
                lines.append(f"- [ ] {todo.get('content', 'N/A')}")

        checkpoint = context.get("last_checkpoint")
        if checkpoint:
            lines.extend([
                "",
                "## 🔄 最近检查点",
                f"- **ID**: {checkpoint.get('checkpoint_id', 'N/A')}",
                f"- **时间**: {checkpoint.get('created_at', 'N/A')}",
                f"- **摘要**: {checkpoint.get('summary', 'N/A')}",
            ])

        return "\n".join(lines)

    def _load_project_info(self) -> Dict:
        """加载项目信息"""
        # 从CLAUDE.md解析
        claude_md = self.project_root / "CLAUDE.md"
        if not claude_md.exists():
            return {"name": "Unknown", "tech_stack": [], "phase": "unknown"}

        # 从memory加载
        project_name_path = self.project_root / ".ai-state" / "memory" / "context" / "project_name.json"
        tech_stack_path = self.project_root / ".ai-state" / "memory" / "context" / "tech_stack.json"

        name = "智能骑行头盔虚拟研发中心"
        tech_stack = ["Python", "LangGraph", "Azure OpenAI", "Gemini"]

        if project_name_path.exists():
            with open(project_name_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                name = data.get("value", name)

        if tech_stack_path.exists():
            with open(tech_stack_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                tech_stack = data.get("value", tech_stack)

        return {
            "name": name,
            "tech_stack": tech_stack,
            "phase": "开发中"
        }

    def _load_model_status(self) -> Dict:
        """加载模型状态"""
        model_registry = self.project_root / "src" / "config" / "model_registry.yaml"
        if not model_registry.exists():
            return {}

        # 返回主要模型状态
        return {
            "GPT-5.4": {"available": True, "purpose": "旗舰模型"},
            "Claude Opus 4.6": {"available": True, "purpose": "深度推理"},
            "Gemini 3.1 Pro": {"available": True, "purpose": "多模态"},
            "o3-deep-research": {"available": True, "purpose": "深度研究"}
        }

    def _load_recent_decisions(self) -> List[Dict]:
        """加载最近决策"""
        decision_dir = self.project_root / ".ai-state" / "memory" / "decision"
        if not decision_dir.exists():
            return []

        decisions = []
        for f in sorted(decision_dir.glob("*.json"), reverse=True)[:5]:
            with open(f, 'r', encoding='utf-8') as fp:
                data = json.load(fp)
                value = data.get("value", {})
                decisions.append({
                    "content": value.get("decision", ""),
                    "reason": value.get("context", {}).get("reason", ""),
                    "outcome": value.get("outcome", "")
                })

        return decisions

    def _load_constraints(self) -> List[Dict]:
        """加载约束"""
        constraint_dir = self.memory_dir / "longterm"
        if not constraint_dir.exists():
            return []

        constraints = []
        for f in constraint_dir.glob("constraint_*.json"):
            with open(f, 'r', encoding='utf-8') as fp:
                data = json.load(fp)
                constraints.append({
                    "content": data.get("content", ""),
                    "scope": data.get("metadata", {}).get("scope", "global")
                })

        return constraints

    def _load_pending_todos(self) -> List[Dict]:
        """加载待办事项"""
        session_dir = self.memory_dir / "session"
        if not session_dir.exists():
            return []

        todos = []
        for f in session_dir.glob("todo_*.json"):
            with open(f, 'r', encoding='utf-8') as fp:
                data = json.load(fp)
                todos.append({
                    "content": data.get("content", ""),
                    "priority": data.get("tags", ["medium"])[0] if data.get("tags") else "medium"
                })

        return todos

    def _load_last_checkpoint(self) -> Optional[Dict]:
        """加载最近检查点"""
        checkpoint_dir = self.memory_dir / "checkpoints"
        if not checkpoint_dir.exists():
            return None

        checkpoints = sorted(checkpoint_dir.glob("ckpt_*.json"))
        if not checkpoints:
            return None

        with open(checkpoints[-1], 'r', encoding='utf-8') as f:
            return json.load(f)

    def _save_context(self, context: Dict):
        """保存上下文"""
        self.context_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.context_file, 'w', encoding='utf-8') as f:
            json.dump(context, f, ensure_ascii=False, indent=2)


# === 全局实例 ===

_injector: Optional[ContextInjector] = None


def get_context_injector() -> ContextInjector:
    """获取上下文注入器"""
    global _injector
    if _injector is None:
        _injector = ContextInjector()
    return _injector


def inject_context() -> Dict[str, Any]:
    """便捷函数：注入上下文"""
    return get_context_injector().inject_startup_context()


def get_context_seed() -> str:
    """便捷函数：获取上下文种子"""
    return get_context_injector().generate_context_seed()


# === 测试 ===

if __name__ == "__main__":
    print("=" * 60)
    print("[CONTEXT INJECTOR TEST]")
    print("=" * 60)

    injector = get_context_injector()

    print("\n[TEST] Injecting startup context...")
    context = injector.inject_startup_context()

    print("\n[RESULT] Injected context:")
    print(f"  Project: {context['project'].get('name')}")
    print(f"  Models: {len(context['models'])} available")
    print(f"  Recent decisions: {len(context['recent_decisions'])}")
    print(f"  Constraints: {len(context['active_constraints'])}")
    print(f"  Pending todos: {len(context['pending_todos'])}")

    print("\n[RESULT] Context seed (first 500 chars):")
    print(injector.generate_context_seed()[:500])

    print("\n" + "=" * 60)