# ⚖️ CPO_Critic 双模型评审流程规范

> **版本**: 1.0
> **创建时间**: 2026-03-16
> **用途**: 定义关键任务前的双模型评审触发机制，确保Gemini+Qwen双PASS机制自动执行

---

## 一、评审触发点定义

### 1.1 强制触发场景

以下场景**必须**触发CPO_Critic双模型评审，不可跳过：

| 场景ID | 场景名称 | 触发时机 | 评审模型 |
|--------|----------|----------|----------|
| TRG-001 | 竞品分析报告 | 生成报告后、提交用户前 | Gemini + Qwen |
| TRG-002 | 架构决策变更 | DECISION记录前 | Gemini + Qwen |
| TRG-003 | 规则变更(RULES.md) | 提交Git前 | Gemini + Qwen |
| TRG-004 | 核心代码变更 | 核心模块提交前 | Gemini + Qwen |
| TRG-005 | 任务契约下发 | CTO/CMO执行前 | Gemini + Qwen |
| TRG-006 | 产品识别验证 | 竞品筛选前 | Gemini (单模型) |

### 1.2 可选触发场景

以下场景**建议**触发评审，可由Agent自主判断：

| 场景ID | 场景名称 | 触发条件 |
|--------|----------|----------|
| OPT-001 | 数据置信度验证 | 大量推断数据时 |
| OPT-002 | 工具降级决策 | 主工具连续失败3次时 |
| OPT-003 | 用户指令歧义检测 | 检测到歧义词汇时 |

---

## 二、双模型评审流程

### 2.1 标准流程图

```
┌─────────────────────────────────────────────────────────────┐
│                    CPO_Critic 双模型评审流程                   │
└─────────────────────────────────────────────────────────────┘

                    ┌──────────────┐
                    │   触发事件    │
                    └──────┬───────┘
                           │
                           ▼
              ┌────────────────────────┐
              │  生成评审请求JSON文件    │
              │  .ai-state/review_request.json
              └────────────┬───────────┘
                           │
           ┌───────────────┼───────────────┐
           │               │               │
           ▼               ▼               ▼
    ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
    │   Gemini    │ │    Qwen     │ │   (可选)    │
    │  1.5 Pro    │ │    Max      │ │   Claude    │
    │   评审      │ │    评审     │ │   评审      │
    └──────┬──────┘ └──────┬──────┘ └──────┬──────┘
           │               │               │
           ▼               ▼               ▼
    ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
    │ 评分 + 建议  │ │ 评分 + 建议  │ │ 评分 + 建议  │
    └──────┬──────┘ └──────┬──────┘ └──────┬──────┘
           │               │               │
           └───────────────┼───────────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │     汇总评审结果        │
              │   review_logs.jsonl    │
              └────────────┬───────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │  双模型都PASS? (≥8分)   │
              └────────────┬───────────┘
                           │
              ┌────────────┴────────────┐
              │                         │
              ▼                         ▼
        ┌──────────┐             ┌──────────┐
        │   PASS   │             │   BLOCK  │
        │  放行执行 │             │  打回修改 │
        └──────────┘             └──────────┘
```

### 2.2 评审请求格式

```json
{
  "request_id": "auto-generated-uuid",
  "trigger_id": "TRG-001",
  "trigger_name": "竞品分析报告",
  "review_type": "post_execution",
  "target_files": [
    ".ai-state/competitive_analysis/competitive_analysis_v5_full.md"
  ],
  "review_dimensions": [
    "competitor_accuracy",
    "data_completeness",
    "process_compliance",
    "documentation"
  ],
  "context": {
    "product_name": "INMO Air3",
    "analysis_type": "competitive_analysis",
    "rules_file": ".ai-architecture/RULES.md"
  },
  "timestamp": "2026-03-16T12:00:00"
}
```

### 2.3 评审结果格式

```json
{
  "request_id": "auto-generated-uuid",
  "reviewer_model": "gemini-1.5-pro",
  "score": 8.5,
  "passed": true,
  "dimensions": {
    "competitor_accuracy": {
      "score": 9,
      "issues": [],
      "suggestions": ["建议补充竞品价格区间分析"]
    },
    "data_completeness": {
      "score": 7,
      "issues": ["UI截图待采集"],
      "suggestions": []
    }
  },
  "blockers": [],
  "warnings": ["部分数据标注待采集"],
  "timestamp": "2026-03-16T12:01:00"
}
```

---

## 三、评审维度定义

### 3.1 竞品分析评审维度

| 维度ID | 维度名称 | 权重 | 检查内容 |
|--------|----------|------|----------|
| CA-01 | 竞品准确性 | 高 | 竞品选择是否正确？是否遗漏核心竞品？ |
| CA-02 | 数据完整性 | 高 | 30维度是否全覆盖？待采集项是否列出？ |
| CA-03 | 数据置信度 | 中 | 每项数据是否标注来源和置信度？ |
| CA-04 | 产品识别验证 | 高 | 是否进行了产品识别验证？(Rule 10.1) |
| CA-05 | 流程合规性 | 中 | 是否遵循AGENTS.md任务承接流程？ |

### 3.2 代码变更评审维度

| 维度ID | 维度名称 | 权重 | 检查内容 |
|--------|----------|------|----------|
| CD-01 | 质量红线合规 | 高 | 文件行数、函数行数、嵌套层级 |
| CD-02 | 安全合规 | 高 | 是否包含黑名单函数？密钥硬编码？ |
| CD-03 | 文档同构 | 中 | 代码变更是否有对应文档更新？ |
| CD-04 | 类型注解 | 中 | 是否100% Type Hints？ |

### 3.3 架构决策评审维度

| 维度ID | 维度名称 | 权重 | 检查内容 |
|--------|----------|------|----------|
| AD-01 | 决策合理性 | 高 | 决策是否有充分背景(Why)？ |
| AD-02 | 影响范围评估 | 高 | 是否评估对现有系统的影响？ |
| AD-03 | 可逆性分析 | 中 | 是否有回滚方案？ |

---

## 四、双模型通过标准

### 4.1 PASS 条件

必须**同时满足**以下条件：

1. **Gemini 评分 ≥ 8.0**
2. **Qwen 评分 ≥ 8.0**
3. **无 Blocker 级问题**
4. **至少 3 轮评审循环**（首次评审如有问题）

### 4.2 BLOCK 条件

**任一**以下情况触发 BLOCK：

1. 任一模型评分 < 8.0
2. 任一模型发现 Blocker 级问题
3. 竞品识别错误（产品识别验证失败）
4. 规则违反（如安全黑名单、质量红线）

### 4.3 评审循环规则

```
评审轮次 1:
  - Gemini PASS 且 Qwen PASS → 最终 PASS
  - 任一模型 BLOCK → 修改后进入轮次 2

评审轮次 2:
  - Gemini PASS 且 Qwen PASS → 最终 PASS
  - 任一模型 BLOCK → 修改后进入轮次 3

评审轮次 3:
  - Gemini PASS 且 Qwen PASS → 最终 PASS
  - 任一模型 BLOCK → 触发 HITL（人类介入）
```

---

## 五、自动化集成方案

### 5.1 任务契约前置检查

在 `src/graph/router.py` 中添加评审触发节点：

```python
def cpo_critic_review_node(state: AgentGlobalState) -> dict:
    """
    CPO_Critic 双模型评审节点

    触发条件:
    - 任务类型为竞品分析
    - 任务类型为架构决策
    - 任务类型为核心代码变更
    """
    task_type = state.get("current_task", {}).get("type")

    # 检查是否需要评审
    if task_type in TRIGGER_TASKS:
        # 生成评审请求
        request = create_review_request(state)

        # 调用双模型评审
        gemini_result = call_gemini_review(request)
        qwen_result = call_qwen_review(request)

        # 判断结果
        if gemini_result.passed and qwen_result.passed:
            return {"review_status": "PASSED", "next_node": "execute"}
        else:
            return {"review_status": "BLOCKED", "next_node": "revise"}

    # 无需评审
    return {"review_status": "SKIPPED", "next_node": "execute"}
```

### 5.2 状态机集成位置

```
当前状态机拓扑:

用户指令 → InstructionGuard → CPO_Plan → CPO_Critic → CTO/CMO

修改后:

用户指令 → InstructionGuard → CPO_Plan → CPO_Critic → [双模型评审] → CTO/CMO
                                                    ↑
                                            新增评审触发点
```

### 5.3 Hook 集成

在 `~/.claude/settings.json` 中添加：

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": ["python scripts/hooks/critic_trigger.py"]
      }
    ]
  }
}
```

---

## 六、评审日志与追溯

### 6.1 日志存储位置

```
.ai-state/
├── review_logs.jsonl          # 所有评审记录
├── review_request.json        # 当前评审请求
└── review_results/            # 评审结果归档
    ├── 2026-03-16/
    │   ├── competitive_analysis.json
    │   └── architecture_change.json
    └── ...
```

### 6.2 评审报告生成

每次评审完成后，自动生成报告：

```
📊 CPO_Critic 双模型评审报告

请求ID: abc123def456
触发场景: TRG-001 竞品分析报告
评审时间: 2026-03-16 12:00:00

┌─────────────┬─────────────┐
│   Gemini    │    Qwen     │
│   8.5/10    │   8.0/10    │
│    PASS     │    PASS     │
└─────────────┴─────────────┘

最终结果: ✅ PASS

维度得分:
  - 竞品准确性: 9/10
  - 数据完整性: 7/10
  - 流程合规性: 9/10

建议改进:
  - 补充UI截图采集
  - 标注数据置信度
```

---

## 七、异常处理

### 7.1 API 不可用处理

```python
def handle_api_unavailable(model: str) -> dict:
    """
    当某个模型API不可用时的处理策略
    """
    if model == "gemini":
        # 尝试备用：Claude
        return try_claude_review()
    elif model == "qwen":
        # 尝试备用：GPT-4o
        return try_gpt4_review()
    else:
        # 触发HITL
        return {"status": "HITL_REQUIRED", "reason": "双模型API均不可用"}
```

### 7.2 评分不一致处理

当 Gemini 和 Qwen 评分差距 ≥ 2 分时：

```python
def handle_score_discrepancy(gemini_score: float, qwen_score: float) -> dict:
    """
    评分不一致时的处理
    """
    if abs(gemini_score - qwen_score) >= 2:
        # 启动第三模型仲裁
        return {
            "action": "ARBITRATION",
            "arbitrator": "claude-opus-4-6",
            "reason": f"评分差距过大: Gemini={gemini_score}, Qwen={qwen_score}"
        }
    return {"action": "CONTINUE"}
```

---

*文档版本: 1.0*
*最后更新: 2026-03-16*
*维护者: CPO_Critic 团队*