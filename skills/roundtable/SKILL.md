---
name: roundtable
description: Use when executing multi-role collaborative decision making, design review, or complex task requiring structured deliberation with proposer/reviewers/critic roles
metadata:
  author: leo
  version: "1.0"
---

# Roundtable Skill

## Overview

圆桌系统是多角色协作决策引擎，通过 Proposer-Reviewers-Critic 三层飞轮收敛方案，确保验收标准逐条通过。

**核心原则：验收标准是唯一退出条件，没有轮数上限。**

## When to Use

- 需要多角色协作决策的任务（设计评审、技术选型）
- 有明确验收标准的复杂产出（HTML Demo、技术方案）
- 需要置信度标注和冲突裁决的争议性问题
- 单一模型容易陷入单一视角的任务

**When NOT to Use:**
- 简单的单步任务（直接执行）
- 没有明确验收标准的探索性任务
- 紧急任务（圆桌需要多轮迭代）

## Phase Flow

```
Phase 1: 独立思考（并行）→ 所有角色同时输出约束清单/判断/不确定项
Phase 2: 方案生成（Proposer）→ 提出完整方案
Phase 3: 定向审查（Reviewers）→ 按职责审查特定维度
Phase 4: Critic 终审 → 验收标准逐条评分，P0/P1 问题分级
```

**v2 收敛分层:**
- 方案层（最多 3 轮）：Critic 只审查方案覆盖度
- 代码层（Generator + Verifier）：不回方案讨论

**震荡检测:** P0 数量连续 3 轮不下降 → 锁定基线方案

## TaskSpec 必填字段

| 字段 | 说明 | 示例 |
|------|------|------|
| topic | 议题名 | "HUD Demo 生成" |
| goal | 一句话目标 | "生成可双击打开的 HUD Demo" |
| acceptance_criteria | 验收标准（可验证） | ["单 HTML 文件", "零外部依赖"] |
| proposer | 出方案角色 | "CDO" |
| reviewers | 审方案角色 | ["CTO", "CMO"] |
| critic | 终审角色 | "Critic" |
| authority_map | 冲突裁决权威 | {"design":"CDO", "final":"Leo"} |
| output_type | 输出类型 | "html" |
| output_path | 输出路径 | "demo_outputs/hud_demo.html" |

## Known Pitfalls

| 陷阱 | 规避方法 |
|------|----------|
| 验收标准模糊（"做得好看"） | 每条必须可验证：有明确指标或检查方法 |
| 方案层震荡（P0 不下降） | 3 轩后锁定基线，进入代码层由 Generator 修复 |
| 单次生成超 500 行质量下降 | Generator 分段生成（5 段策略） |
| 置信度标注不诚实 | Critic 审查时质疑"主观臆断标高置信度" |
| TaskSpec 问题未处理 | 预检查发现问题 → 飞书通知人工确认 |

## Verification Criteria

- [ ] 所有验收标准通过（Critic passed=True）
- [ ] P0 问题清零
- [ ] P1 问题可接受（记录但不阻塞）
- [ ] 快照保存完整（input_task_spec.json + phase4_critic_final.md）

## Key Files

```
scripts/roundtable/roundtable.py        # 主流程编排
scripts/roundtable/task_spec.py         # TaskSpec 数据类
scripts/roundtable/generator.py         # 分段生成器
scripts/roundtable/verifier.py          # 三层规则验证
scripts/roundtable/crystallizer.py      # 知识结晶
scripts/roundtable/roles.py             # 角色模型分配
.ai-state/task_specs/*.json             # TaskSpec 定义文件
roundtable_runs/{topic}_{timestamp}/    # 运行快照目录
```

## Quick Reference

```bash
# 通过飞书触发
/roundtable HUD Demo

# 手动运行
python scripts/roundtable/roundtable.py --task HUD_Demo

# 查看 TaskSpec
cat .ai-state/task_specs/HUD_Demo.json

# 查看运行结果
ls roundtable_runs/HUDDemo生成_*/
cat roundtable_runs/HUDDemo生成_*/phase4_critic_final.md
```