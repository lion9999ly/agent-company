# 🔄 任务后评审与持续改进机制 (Task Review & Continuous Improvement)

> **版本**: 1.0
> **创建时间**: 2026-03-17
> **用途**: 将每次任务转化为组织能力提升机会，实现自驱式进化

---

## 一、核心理念

**每次任务都是一次提高的机会**

本虚拟公司采用"任务后评审"(Post-Task Review)机制，确保：
1. 每次任务结束后自动触发多模型交叉评审
2. 评审结果转化为具体的改进项
3. 改进项闭环追踪，确保落地执行

---

## 二、评审流程 (Review Workflow)

### 2.1 触发条件

| 场景 | 触发时机 | 评审类型 |
|------|----------|----------|
| 任务完成 | 任务交付后 | 综合评审 |
| 代码提交 | Git commit前 | 质量红线评审 |
| 架构变更 | 架构文档修改后 | 架构合规评审 |
| 用户反馈 | 用户提出改进意见 | 专项评审 |

### 2.2 评审模型阵列

| 角色 | 模型 | 职责 |
|------|------|------|
| 主评审 | Gemini 2.5 Flash | 快速评审，识别明显问题 |
| 交叉评审 | GPT-4o (Azure) | 深度评审，验证结论 |
| 备选评审 | Qwen Max | 中文场景专项 |
| 最终裁定 | CPO (GPT-4o) | 仲裁不一致意见 |

### 2.3 评审维度

```yaml
review_dimensions:
  quality_compliance:
    weight: high
    checklist:
      - 维度覆盖度: 是否覆盖所有规定维度
      - 数据质量: 来源标注、置信度标注
      - 结构规范性: 报告格式、可读性

  methodology:
    weight: high
    checklist:
      - 分析逻辑: 推理是否严谨
      - 证据支撑: 结论是否有数据支撑
      - 对比分析: 是否进行横向对比

  actionability:
    weight: medium
    checklist:
      - 采集指引: 待采集项是否有明确指引
      - 下一步行动: 是否明确后续步骤
      - 可落地性: 建议是否可执行

  architecture_compliance:
    weight: high
    checklist:
      - 流程合规: 是否遵循AGENTS.md规范
      - 模型对齐: 是否使用正确的模型阵列
      - 文档同构: 代码与文档是否同步更新
```

---

## 三、改进闭环机制 (Improvement Loop)

### 3.1 改进项分类

| 类型 | 定义 | 处理方式 |
|------|------|----------|
| **P0-Critical** | 阻塞性问题，影响交付质量 | 立即修复，不得进入下一任务 |
| **P1-High** | 重要问题，影响用户体验 | 48小时内修复 |
| **P2-Medium** | 改进项，提升整体质量 | 纳入下一迭代 |
| **P3-Low** | 建议项，锦上添花 | 记录待评估 |

### 3.2 改进项生命周期

```
发现 → 分类 → 分配 → 执行 → 验证 → 关闭
 ↓                         ↑
 └─────── 不通过 ←─────────┘
```

### 3.3 改进项追踪

所有改进项记录在 `.ai-state/improvement_backlog.md`，包含：
- 发现时间
- 发现来源（任务ID）
- 问题描述
- 改进建议
- 责任Agent
- 状态（待处理/进行中/已完成）
- 验证结果

---

## 四、组织记忆系统 (Organizational Memory)

### 4.1 记忆类型

| 类型 | 存储位置 | 用途 |
|------|----------|------|
| **用户记忆** | `memory/user_*.md` | 用户偏好、角色背景 |
| **反馈记忆** | `memory/feedback_*.md` | 用户纠正、改进要求 |
| **项目记忆** | `memory/project_*.md` | 项目背景、目标、约束 |
| **改进记忆** | `.ai-state/improvement_backlog.md` | 历史改进项、经验教训 |

### 4.2 记忆激活规则

```yaml
activation_rules:
  - trigger: "新任务开始"
    action: "加载相关用户记忆和项目记忆"

  - trigger: "任务后评审"
    action: "更新改进记忆，记录经验教训"

  - trigger: "用户反馈"
    action: "创建反馈记忆，触发改进流程"

  - trigger: "重复错误"
    action: "检索历史改进记忆，避免重犯"
```

---

## 五、自动化工具链 (Automation Toolchain)

### 5.1 评审脚本

```bash
# 执行任务后评审
python scripts/post_task_review.py --task <task_id> --output .ai-state/review_logs.jsonl

# 生成改进报告
python scripts/generate_improvement_report.py --period weekly

# 验证改进项
python scripts/verify_improvements.py --item <improvement_id>
```

### 5.2 集成点

| 集成点 | 触发 | 执行内容 |
|--------|------|----------|
| Git Pre-commit | 代码提交 | 质量红线检查 |
| 任务完成 | 任务交付 | 多模型交叉评审 |
| 每日汇总 | 每日结束 | 生成改进日报 |
| 每周回顾 | 周五 | 生成改进周报 |

---

## 六、评审结果示例 (Review Result Example)

```json
{
  "review_id": "review_20260317_001",
  "task_id": "looki_l1_competitive_analysis",
  "timestamp": "2026-03-17T07:25:19Z",
  "reviewers": [
    {
      "model": "Gemini 2.5 Flash",
      "role": "主评审",
      "score": 4,
      "verdict": "BLOCK"
    },
    {
      "model": "GPT-4o (Azure)",
      "role": "交叉评审",
      "score": 5,
      "verdict": "BLOCK"
    }
  ],
  "aggregated_score": 4.5,
  "final_verdict": "BLOCK",
  "improvements": [
    {
      "id": "IMP-001",
      "category": "P1-High",
      "description": "维度覆盖率仅43%，需补充17项待采集数据",
      "suggestion": "制定数据采集计划，优先补齐关键维度",
      "status": "pending"
    },
    {
      "id": "IMP-002",
      "category": "P1-High",
      "description": "缺少用户评价数据",
      "suggestion": "访问Kickstarter评论区或亚马逊评论采集真实反馈",
      "status": "pending"
    }
  ]
}
```

---

## 七、持续改进指标 (Continuous Improvement Metrics)

| 指标 | 计算方式 | 目标 |
|------|----------|------|
| 评审通过率 | PASS任务数 / 总任务数 | ≥ 80% |
| 改进闭环率 | 已关闭改进项 / 总改进项 | ≥ 90% |
| 重复错误率 | 重复问题数 / 总问题数 | ≤ 10% |
| 平均评分 | 所有任务评审分数均值 | ≥ 7.5 |

---

## 八、与现有系统集成

### 8.1 与CLAUDE.md集成

在 `CLAUDE.md` 中增加：
```markdown
## 任务后评审机制
- 任务完成后自动触发多模型交叉评审
- 评审不通过需修复后方可进入下一任务
- 改进项记录在 `.ai-state/improvement_backlog.md`
```

### 8.2 与AGENTS.md集成

在 `AGENTS.md` 中增加：
```yaml
CPO_Critic:
  post_task_review:
    enabled: true
    models: [gemini_flash, gpt4o]
    threshold: 8.0
    auto_improvement: true
```

### 8.3 与质量红线集成

在 `01-quality-redlines.md` 中增加：
```markdown
## 6. 任务后评审红线
* 所有任务交付前必须经过CPO_Critic评审
* 评审分数低于8.0的任务不得标记为"已完成"
* P0级改进项必须在24小时内关闭
```

---

## 九、实施路线图

| 阶段 | 时间 | 内容 |
|------|------|------|
| Phase 1 | Week 1 | 建立评审脚本，实现自动化触发 |
| Phase 2 | Week 2 | 建立改进项追踪系统 |
| Phase 3 | Week 3 | 集成到CLAUDE.md和AGENTS.md |
| Phase 4 | Week 4 | 完善组织记忆系统 |

---

*文档版本: 1.0*
*最后更新: 2026-03-17*
*维护者: CPO_Critic Agent*