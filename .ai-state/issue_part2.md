# Day 17 系统状态审计 - Part 2: 状态文件 & 目录

## 6. .ai-state/system_status.md（完整）

```markdown
# 系统状态

> 最后更新：2026-04-08 (由 Claude Code 自动维护)

## 当前状态
- **阶段**：方案论证
- **Git 分支**：main
- **最近提交**：feat: generator retry, snapshots, verdict parser

## 最近变更
- 2026-04-08: 圆桌 v2 核心重构（收敛分层、因果链、动态输入、规则库）
- 2026-04-08: Generator 重试机制、过程快照保留、评判解析器
- 2026-04-07: HUD Demo Segment 5 完成 + 视觉打磨

## 能力清单
- `圆桌` - 多角色讨论引擎（Phase 1-4）
- `深度学习` - 五层管道（7h）
- `自学习` - 周期知识补强（30min）
- `KB治理` - 知识库清洗
- `竞品监控` - 竞品动态追踪
- `GitHub Issue` - 指令通道

## 模型可用性
| 模型 | 角色 | 状态 |
|------|------|------|
| o3-deep-research | 深度研究主力 | ✅ 可用 |
| gpt_5_4 | 高级降级 | ✅ 可用 |
| gpt-4o | 通用降级 | ✅ 可用 |
| doubao_seed_pro | 中文搜索+Critic | ✅ 可用 |
| gemini_3_1_pro | 备选 | ✅ 可用 |

## 已知问题
- roundtable.py 超过 800 行（已豁免，待独立重构）
- text_router.py 约 2292 行（待拆分）

## 待执行改进
见 `.ai-state/improvement_backlog_complete.md`
```

---

## 7. .ai-state/system_architecture_digest.md（完整）

```markdown
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
```

---

## 8. ls -la roundtable_runs/ 输出

```
total 20
drwxr-xr-x 1 uih00653 1049089 0 Apr  8 15:40 .
drwxr-xr-x 1 uih00653 1049089 0 Apr  8 16:20 ..
drwxr-xr-x 1 uih00653 1049089 0 Apr  8 11:23 HUDDemo生成_20260408_112335
drwxr-xr-x 1 uih00653 1049089 0 Apr  8 14:55 HUDDemo生成_20260408_144049
drwxr-xr-x 1 uih00653 1049089 0 Apr  8 15:52 HUDDemo生成_20260408_154038
```

**分析**：3 个圆桌运行记录，全部是 HUD Demo 生成任务，最新在 15:52。

---

## 9. ls -la .ai-state/verifier_rules/ 输出

```
total 43
drwxr-xr-x 1 uih00653 1049089   0 Apr  8 10:38 .
drwxr-xr-x 1 uih00653 1049089   0 Apr  8 17:43 ..
-rw-r--r-- 1 uih00653 1049089 111 Apr  8 10:38 evolution_log.jsonl
-rw-r--r-- 1 uih00653 1049089 161 Apr  8 10:38 global.json
-rw-r--r-- 1 uih00653 1049089 370 Apr  8 10:38 type_html.json
```

**分析**：
- `global.json` - 全局规则（161 bytes）
- `type_html.json` - HTML 类型规则（370 bytes）
- `evolution_log.jsonl` - 规则演进日志（111 bytes）

---

## 10. .env 非敏感配置项

```bash
# Azure OpenAI
AZURE_OPENAI_ENDPOINT=https://ai-share01ai443564620477.openai.azure.com/

# Azure OpenAI (Norway East - o3-deep-research)
AZURE_OPENAI_NORWAY_ENDPOINT=https://admin-me1ed2lc-norwayeast.services.ai.azure.com/

# Feishu
FEISHU_APP_ID=cli_a9326fa6ba389cc5
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/b3ecb9ca-53d3-4b9d-bc81-1f15bf9e402d

# GitHub (for Issue instruction channel)
GITHUB_TOKEN=<已移除>
```

---

## 诊断摘要

### 健康状态

| 模块 | 状态 | 备注 |
|------|------|------|
| Agent 消息处理 | ✅ | 快速通道 + Claude Code CLI 双轨 |
| 圆桌系统 | ✅ | v2 收敛分层，3个运行记录 |
| 自学习 | ✅ | 30min周期，决策树优先级加权 |
| 飞书输出 | ✅ | 云文档/多维表格统一 |
| Verifier 规则库 | ⚠️ | 只有 html 类型规则，缺少其他类型 |

### 待改进

1. **Verifier 规则库扩展**：缺少 python、markdown 等类型规则
2. **text_router.py 拆分**：559 行已拆分到 handler 模块，但仍有冗余
3. **roundtable.py 拆分**：超过 800 行，需独立重构 Issue

---

*本报告由 Claude Code 生成，用于 Day 17 系统诊断*