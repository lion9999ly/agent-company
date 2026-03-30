# 📁 Plan 持久化目录

此目录用于存储 Plan 模式的持久化文件。

## 目录结构

```
.ai-plans/
├── active_plan.json       # 当前活动的Plan
├── plan_YYYYMMDD_HHMMSS.json  # Plan文件
└── history/               # 已完成的Plan归档
    └── plan_*.json
```

## Plan 文件格式

```json
{
  "metadata": {
    "plan_id": "plan_20260316_120000",
    "title": "Plan标题",
    "description": "Plan描述",
    "created_at": "2026-03-16T12:00:00",
    "updated_at": "2026-03-16T13:00:00",
    "status": "in_progress",
    "total_phases": 3,
    "completed_phases": 1,
    "overall_progress": 45.5
  },
  "phases": [
    {
      "phase_id": "plan_20260316_120000_phase_0",
      "name": "Phase 1: 准备阶段",
      "description": "阶段描述",
      "checklist": [
        {
          "id": "plan_20260316_120000_p0_c0",
          "description": "检查项描述",
          "completed": true,
          "completed_at": "2026-03-16T12:30:00",
          "notes": "备注"
        }
      ],
      "status": "completed",
      "progress": 100.0
    }
  ],
  "context": {},
  "decisions": [],
  "blockers": []
}
```

## 使用方式

```python
from scripts.plan_manager import get_plan_manager

manager = get_plan_manager()

# 创建Plan
plan = manager.create_plan(
    title="任务标题",
    description="任务描述",
    phases=[{"name": "阶段1", "checklist": ["任务1", "任务2"]}]
)

# 获取活动Plan
active_plan = manager.load_active_plan()

# 更新进度
manager.update_checklist_item(plan_id, phase_index, item_index, completed=True)

# 添加决策记录
manager.add_decision(plan_id, "决策内容", "决策原因")

# 归档Plan
manager.archive_plan(plan_id)
```

## Plan 状态

| 状态 | 说明 |
|------|------|
| draft | 草稿，尚未开始执行 |
| in_progress | 执行中 |
| paused | 暂停（有阻塞项） |
| completed | 已完成 |
| archived | 已归档 |

---

*此目录由 Plan Manager 自动维护*