# 📋 Plan 持久化管理器 (Plan Persistence Manager)
"""
核心职责：管理Plan文件的持久化存储、恢复和进度跟踪。

功能：
1. 保存plan到项目目录
2. 读取最近的plan恢复上下文
3. Checklist进度跟踪
4. 会话间上下文传递

作者：虚拟研发中心安全团队
创建：2026-03-16
"""

import json
import shutil
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

# === 配置 ===

PROJECT_ROOT = Path(__file__).resolve().parent.parent  # scripts -> project root
PLANS_DIR = PROJECT_ROOT / ".ai-plans"
ACTIVE_PLAN_FILE = PLANS_DIR / "active_plan.json"
PLAN_HISTORY_DIR = PLANS_DIR / "history"


class PlanStatus(Enum):
    """Plan状态"""
    DRAFT = "draft"           # 草稿
    IN_PROGRESS = "in_progress"  # 执行中
    COMPLETED = "completed"    # 已完成
    PAUSED = "paused"          # 暂停
    ARCHIVED = "archived"      # 已归档


@dataclass
class ChecklistItem:
    """检查项"""
    id: str
    description: str
    completed: bool = False
    completed_at: Optional[str] = None
    notes: Optional[str] = None


@dataclass
class PlanPhase:
    """Plan阶段"""
    phase_id: str
    name: str
    description: str
    checklist: list[ChecklistItem] = field(default_factory=list)
    status: str = "pending"  # pending, in_progress, completed

    @property
    def progress(self) -> float:
        if not self.checklist:
            return 0.0
        completed = sum(1 for item in self.checklist if item.completed)
        return completed / len(self.checklist) * 100


@dataclass
class PlanMetadata:
    """Plan元数据"""
    plan_id: str
    title: str
    description: str
    created_at: str
    updated_at: str
    status: PlanStatus
    total_phases: int
    completed_phases: int
    overall_progress: float


@dataclass
class Plan:
    """Plan完整结构"""
    metadata: PlanMetadata
    phases: list[PlanPhase]
    context: dict = field(default_factory=dict)  # 额外上下文
    decisions: list[dict] = field(default_factory=list)  # 决策记录
    blockers: list[dict] = field(default_factory=list)  # 阻塞项

    def to_dict(self) -> dict:
        metadata_dict = asdict(self.metadata)
        metadata_dict["status"] = self.metadata.status.value  # 转换枚举为字符串

        return {
            "metadata": metadata_dict,
            "phases": [
                {
                    "phase_id": p.phase_id,
                    "name": p.name,
                    "description": p.description,
                    "checklist": [asdict(c) for c in p.checklist],
                    "status": p.status,
                    "progress": p.progress
                }
                for p in self.phases
            ],
            "context": self.context,
            "decisions": self.decisions,
            "blockers": self.blockers
        }


class PlanManager:
    """Plan持久化管理器"""

    def __init__(self):
        self.plans_dir = PLANS_DIR
        self.history_dir = PLAN_HISTORY_DIR
        self._ensure_dirs()

    def _ensure_dirs(self):
        """确保目录存在"""
        self.plans_dir.mkdir(parents=True, exist_ok=True)
        self.history_dir.mkdir(parents=True, exist_ok=True)

    def create_plan(self,
                   title: str,
                   description: str,
                   phases: list[dict]) -> Plan:
        """
        创建新Plan

        Args:
            title: Plan标题
            description: Plan描述
            phases: 阶段列表，每个阶段包含name, description, checklist

        Returns:
            Plan: 创建的Plan对象
        """
        plan_id = f"plan_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        now = datetime.now().isoformat()

        plan_phases = []
        for i, phase_data in enumerate(phases):
            checklist = [
                ChecklistItem(
                    id=f"{plan_id}_p{i}_c{j}",
                    description=item
                )
                for j, item in enumerate(phase_data.get("checklist", []))
            ]
            plan_phases.append(PlanPhase(
                phase_id=f"{plan_id}_phase_{i}",
                name=phase_data.get("name", f"Phase {i+1}"),
                description=phase_data.get("description", ""),
                checklist=checklist
            ))

        metadata = PlanMetadata(
            plan_id=plan_id,
            title=title,
            description=description,
            created_at=now,
            updated_at=now,
            status=PlanStatus.DRAFT,
            total_phases=len(plan_phases),
            completed_phases=0,
            overall_progress=0.0
        )

        plan = Plan(metadata=metadata, phases=plan_phases)
        self._save_plan(plan)
        return plan

    def _save_plan(self, plan: Plan):
        """保存Plan到文件"""
        plan_file = self.plans_dir / f"{plan.metadata.plan_id}.json"
        with open(plan_file, "w", encoding="utf-8") as f:
            json.dump(plan.to_dict(), f, ensure_ascii=False, indent=2)

        # 同时更新active_plan
        with open(ACTIVE_PLAN_FILE, "w", encoding="utf-8") as f:
            json.dump(plan.to_dict(), f, ensure_ascii=False, indent=2)

    def load_plan(self, plan_id: str) -> Optional[Plan]:
        """加载指定Plan"""
        plan_file = self.plans_dir / f"{plan_id}.json"
        if not plan_file.exists():
            return None
        return self._load_plan_from_file(plan_file)

    def load_active_plan(self) -> Optional[Plan]:
        """加载当前活动的Plan"""
        if not ACTIVE_PLAN_FILE.exists():
            return None
        return self._load_plan_from_file(ACTIVE_PLAN_FILE)

    def _load_plan_from_file(self, file_path: Path) -> Optional[Plan]:
        """从文件加载Plan"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            metadata = PlanMetadata(**data["metadata"])
            metadata.status = PlanStatus(metadata.status)

            phases = []
            for p in data["phases"]:
                checklist = [ChecklistItem(**c) for c in p["checklist"]]
                phases.append(PlanPhase(
                    phase_id=p["phase_id"],
                    name=p["name"],
                    description=p["description"],
                    checklist=checklist,
                    status=p["status"]
                ))

            return Plan(
                metadata=metadata,
                phases=phases,
                context=data.get("context", {}),
                decisions=data.get("decisions", []),
                blockers=data.get("blockers", [])
            )
        except Exception as e:
            print(f"加载Plan失败: {e}")
            return None

    def update_checklist_item(self,
                              plan_id: str,
                              phase_index: int,
                              item_index: int,
                              completed: bool,
                              notes: Optional[str] = None) -> bool:
        """更新检查项状态"""
        plan = self.load_plan(plan_id)
        if not plan:
            return False

        if phase_index >= len(plan.phases):
            return False

        phase = plan.phases[phase_index]
        if item_index >= len(phase.checklist):
            return False

        item = phase.checklist[item_index]
        item.completed = completed
        item.completed_at = datetime.now().isoformat() if completed else None
        if notes:
            item.notes = notes

        # 更新阶段状态
        all_completed = all(c.completed for c in phase.checklist)
        phase.status = "completed" if all_completed else "in_progress"

        # 更新元数据
        plan.metadata.updated_at = datetime.now().isoformat()
        plan.metadata.completed_phases = sum(1 for p in plan.phases if p.status == "completed")

        total_items = sum(len(p.checklist) for p in plan.phases)
        completed_items = sum(sum(1 for c in p.checklist if c.completed) for p in plan.phases)
        plan.metadata.overall_progress = (completed_items / total_items * 100) if total_items > 0 else 0

        if plan.metadata.overall_progress == 100:
            plan.metadata.status = PlanStatus.COMPLETED
        elif plan.metadata.overall_progress > 0:
            plan.metadata.status = PlanStatus.IN_PROGRESS

        self._save_plan(plan)
        return True

    def add_decision(self, plan_id: str, decision: str, rationale: str):
        """添加决策记录"""
        plan = self.load_plan(plan_id)
        if not plan:
            return False

        plan.decisions.append({
            "timestamp": datetime.now().isoformat(),
            "decision": decision,
            "rationale": rationale
        })
        plan.metadata.updated_at = datetime.now().isoformat()
        self._save_plan(plan)
        return True

    def add_blocker(self, plan_id: str, blocker: str, impact: str):
        """添加阻塞项"""
        plan = self.load_plan(plan_id)
        if not plan:
            return False

        plan.blockers.append({
            "timestamp": datetime.now().isoformat(),
            "blocker": blocker,
            "impact": impact,
            "resolved": False
        })
        plan.metadata.status = PlanStatus.PAUSED
        plan.metadata.updated_at = datetime.now().isoformat()
        self._save_plan(plan)
        return True

    def resolve_blocker(self, plan_id: str, blocker_index: int, resolution: str):
        """解决阻塞项"""
        plan = self.load_plan(plan_id)
        if not plan or blocker_index >= len(plan.blockers):
            return False

        plan.blockers[blocker_index]["resolved"] = True
        plan.blockers[blocker_index]["resolution"] = resolution
        plan.blockers[blocker_index]["resolved_at"] = datetime.now().isoformat()

        # 检查是否所有阻塞项都已解决
        if all(b["resolved"] for b in plan.blockers):
            plan.metadata.status = PlanStatus.IN_PROGRESS

        plan.metadata.updated_at = datetime.now().isoformat()
        self._save_plan(plan)
        return True

    def archive_plan(self, plan_id: str) -> bool:
        """归档Plan"""
        plan = self.load_plan(plan_id)
        if not plan:
            return False

        plan.metadata.status = PlanStatus.ARCHIVED
        plan.metadata.updated_at = datetime.now().isoformat()

        # 移动到历史目录
        src_file = self.plans_dir / f"{plan_id}.json"
        dst_file = self.history_dir / f"{plan_id}.json"
        self._save_plan(plan)
        shutil.move(str(src_file), str(dst_file))

        # 清除active_plan
        if ACTIVE_PLAN_FILE.exists():
            ACTIVE_PLAN_FILE.unlink()

        return True

    def list_plans(self) -> list[dict]:
        """列出所有Plan"""
        plans = []
        for plan_file in self.plans_dir.glob("plan_*.json"):
            plan = self._load_plan_from_file(plan_file)
            if plan:
                plans.append({
                    "plan_id": plan.metadata.plan_id,
                    "title": plan.metadata.title,
                    "status": plan.metadata.status.value,
                    "progress": plan.metadata.overall_progress,
                    "updated_at": plan.metadata.updated_at
                })
        return sorted(plans, key=lambda x: x["updated_at"], reverse=True)

    def format_progress_report(self, plan: Plan) -> str:
        """格式化进度报告"""
        lines = [
            "=" * 60,
            f"[PLAN] {plan.metadata.title}",
            f"   ID: {plan.metadata.plan_id}",
            f"   Status: {plan.metadata.status.value}",
            f"   Progress: {plan.metadata.overall_progress:.1f}%",
            "=" * 60
        ]

        for i, phase in enumerate(plan.phases):
            status_icon = "[DONE]" if phase.status == "completed" else "[...]" if phase.status == "in_progress" else "[ ]"
            lines.append(f"\n{status_icon} Phase {i+1}: {phase.name}")
            lines.append(f"   Progress: {phase.progress:.0f}%")

            for item in phase.checklist:
                check = "[x]" if item.completed else "[ ]"
                lines.append(f"   {check} {item.description}")
                if item.notes:
                    lines.append(f"       Note: {item.notes}")

        if plan.blockers:
            lines.append(f"\n[BLOCKERS]:")
            for b in plan.blockers:
                status = "RESOLVED" if b["resolved"] else "PENDING"
                lines.append(f"   - {b['blocker']} [{status}]")

        if plan.decisions:
            lines.append(f"\n[DECISIONS]:")
            for d in plan.decisions[-3:]:  # 最近3条
                lines.append(f"   - {d['decision']}")

        return "\n".join(lines)


# === 便捷函数 ===

_manager: Optional[PlanManager] = None

def get_plan_manager() -> PlanManager:
    """获取全局Plan管理器"""
    global _manager
    if _manager is None:
        _manager = PlanManager()
    return _manager


def create_plan(title: str, description: str, phases: list[dict]) -> Plan:
    """便捷函数：创建Plan"""
    return get_plan_manager().create_plan(title, description, phases)


def get_active_plan() -> Optional[Plan]:
    """便捷函数：获取当前活动的Plan"""
    return get_plan_manager().load_active_plan()


# === 测试入口 ===

if __name__ == "__main__":
    manager = PlanManager()

    print("=" * 60)
    print("Plan持久化管理器测试")
    print("=" * 60)

    # 创建测试Plan
    plan = manager.create_plan(
        title="上下文熵增治理优化",
        description="根据小红书文章方法论优化Multi-Agent系统",
        phases=[
            {
                "name": "Phase 0: 安全加固",
                "description": "实现安全模块",
                "checklist": [
                    "创建 instruction_guard.py",
                    "创建 kpi_trap_detector.py",
                    "创建 behavior_logger.py",
                    "更新 RULES.md"
                ]
            },
            {
                "name": "Phase 1: Hook集成",
                "description": "实现Hook拦截机制",
                "checklist": [
                    "创建 pre_tool_use.py",
                    "创建 quality_check.py",
                    "配置 settings.json"
                ]
            },
            {
                "name": "Phase 2: Plan持久化",
                "description": "实现Plan管理机制",
                "checklist": [
                    "创建 plan_manager.py",
                    "创建 .ai-plans 目录",
                    "测试Plan创建和更新"
                ]
            }
        ]
    )

    print(f"\n创建Plan: {plan.metadata.plan_id}")
    print(manager.format_progress_report(plan))

    # 模拟更新进度
    manager.update_checklist_item(plan.metadata.plan_id, 0, 0, True, "已完成")
    manager.update_checklist_item(plan.metadata.plan_id, 0, 1, True, "已完成")
    manager.update_checklist_item(plan.metadata.plan_id, 0, 2, True, "已完成")
    manager.update_checklist_item(plan.metadata.plan_id, 0, 3, True, "已完成")

    print("\n更新进度后:")
    updated_plan = manager.load_plan(plan.metadata.plan_id)
    print(manager.format_progress_report(updated_plan))