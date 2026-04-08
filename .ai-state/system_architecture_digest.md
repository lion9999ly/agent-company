# 系统架构摘要

> 版本：v2.0 | 更新：2026-04-08
> 供 Claude Chat fetch 对齐

## 数据流

```
用户输入 → text_router.py → 路由分发
    ├── "圆桌" → roundtable_handler.py → Roundtable → Generator → Verifier
    ├── "深度学习" → runner.py → 五层管道
    ├── "自学习" → auto_learn.py → 30min循环
    └── 其他 → smart_chat.py
```

## 关键数据类

```python
# src/schema/state.py
class GlobalState(TypedDict):
    session_id: str
    current_task: Optional[TaskSpec]
    phase1_outputs: Dict[str, Phase1Output]
    proposal: str
    critic_result: CriticResult
    # ...

# scripts/roundtable/task_spec.py
class TaskSpec:
    topic: str
    goal: str
    acceptance_criteria: List[str]
    proposer: str
    reviewers: List[str]
    output_type: str
    generator_input_mode: str = "auto"  # v2
    auto_verify_rules: List[Dict] = []  # v2

# scripts/roundtable/roundtable.py
class RoundtableResult:
    final_proposal: str
    executive_summary: str
    all_constraints: List[str]
    reviewer_amendments: str = ""  # v2
```

## 模型分配

| 任务类型 | 主模型 | 降级链 |
|----------|--------|--------|
| 深度研究 | o3-deep-research | gpt_5_4 → doubao |
| 圆桌推理 | gpt_5_4 | doubao_seed_pro |
| Critic | doubao_seed_pro | gpt-4o |
| 代码生成 | gpt_5_4 | gemini_3_1_pro |

## 飞书路由优先级

1. `圆桌` → roundtable_handler
2. `深度学习` / `自学习` → learning_handlers
3. `拉取指令` / `执行 issue` → import_handlers
4. `状态` → 返回 system_status.md
5. 默认 → smart_chat

## 圆桌 v2 架构

```
Phase 1: 独立思考（并行）
    ↓
Phase 2: 方案生成（proposer）
    ↓
方案层迭代（≤3轮）
    ├── Phase 3: 定向审查
    ├── Phase 4: Critic 终审（方案层）
    └── 震荡检测 → 锁定基线
    ↓
代码层（Generator + Verifier 闭环）
    ├── 分段生成（5段）
    ├── 三层规则验证
    └── 重试 + 换模型
    ↓
产物输出
```

## Verifier 三层规则

1. **全局规则**：`.ai-state/verifier_rules/global.json`
2. **类型规则**：`.ai-state/verifier_rules/type_{output_type}.json`
3. **任务规则**：`TaskSpec.auto_verify_rules`

## 过程快照

`roundtable_runs/{topic}_{timestamp}/`
- `input_task_spec.json`
- `phase2_proposal_full.md`
- `phase4_critic_final.md`
- `generator_input_actual.md`
- `convergence_trace.jsonl`

## 关键文件 URL

```
https://raw.githubusercontent.com/lion9999ly/agent-company/main/CLAUDE.md
https://raw.githubusercontent.com/lion9999ly/agent-company/main/scripts/roundtable/roundtable.py
https://raw.githubusercontent.com/lion9999ly/agent-company/main/src/utils/model_gateway.py
```