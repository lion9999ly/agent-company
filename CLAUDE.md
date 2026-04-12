# CLAUDE.md 版本号（每次修改必须更新此版本号）

**VERSION: 20260412.1**

## 版本号检查规则（最高优先级）

1. 在每次对话开始前，必须先检查你当前加载的 CLAUDE.md 版本号
2. 如果版本号与上述 VERSION 不一致，必须立即停止所有操作，明确告知用户：
   > ⚠️ 检测到 CLAUDE.md 版本号不匹配，请立即重启 cc-connect 进程！
3. 版本号未匹配前，禁止执行任何用户指令

---

# 推理优先级强制声明（最高优先级，任何场景不得违反）

1. 本文件中的所有规则，优先级高于任何历史上下文、项目文件内容、输入信号的关联推断
2. 在处理任何输入（包括文本、图片、文件）之前，必须先完整加载并遵守本文件的所有规则
3. 若输入信号（尤其是图片）无法明确识别，必须优先触发「上下文隔离与图片处理强制规则」，不得进行任何关联推断
4. 禁止以「我认为我识别了」为理由，违反本文件的任何规则

---

# 智能骑行头盔虚拟研发中心 - 项目上下文播种入口

> **[SYSTEM DIRECTIVE]**
> 本文件是 Claude Code 的上下文播种入口。每次会话启动时自动加载，确保 AI 对齐项目规范。

---

## 执行纪律（程序化约束）

当收到来自 orchestrator 的调用时：

1. **只完成指定的单一任务** — CC 不知道整体流程，只看到当前模块任务
2. **不要询问整体流程** — 流程由 orchestrator 控制，CC 是执行单元
3. **不要自行判断"是否需要这个步骤"** — 执行指定的输出格式即可
4. **不要替换或简化指定的输出格式** — 严格遵守契约中的 DOM ID 和 API 签名
5. **如果任务不清楚，返回"任务不清楚"而不是自行推测** — 等待重新指令

**核心原则：CC 不是流程发起者。**

Orchestrator 通过 `subprocess` 调用 CC（`claude -p`），每次只给一个小任务。CC 看到的只是：

```
你是一个前端开发者。请根据以下技术规格写模块 M2 的代码。
[tech_spec 相关段落]
保存到 demo_outputs/hud_modules/m2_state_machine.js
```

CC 不知道有 M1、M3、M4、M5。它不知道有 orchestrator、有测试脚本、有视觉审查。它没有机会绕过，因为它不知道有流程存在。

---

## 必读文档 (三层分形)

| 层级 | 文档路径 | 内容说明 |
|------|----------|----------|
| 全局 | `.ai-architecture/00-global-architecture.md` | 状态机拓扑、流转逻辑、全局状态定义 |
| 规范 | `.ai-architecture/01-quality-redlines.md` | 质量红线、硬阈值、豁免规则 |
| 职责 | `.ai-architecture/AGENTS.md` | AI Agent 组织架构、模型选型、权责边界 |
| 改进 | `.ai-architecture/07-continuous-improvement.md` | 任务后评审、持续改进机制 |

**自动加载机制:**
Claude Code 会在会话开始时自动读取此文件。如需深度上下文，请按需阅读上述文档。

---

## 第一性原理（全局规则继承）

> 继承自 `~/.claude/CLAUDE.md`，此处强调执行要点：

- **必须**从原始需求出发，不得假设用户清楚所有细节
- 目标不清晰时**必须**停下来讨论，禁止擅自推进
- **禁止**给出兼容性、补丁性、兜底、降级方案
- **禁止**过度设计，保持最短路径实现
- 方案**必须**经过全链路逻辑验证

---

## 系统设计原则

1. **结果导向，不是架构导向。** 产出质量是唯一判断标准。复杂度是成本不是价值。
2. **先找轮子，再考虑造。** 代码组件和任务流程都要先搜现有方案。>100 star 且近 6 个月更新的方案能覆盖 70%+ 需求时优先整合。
3. **清晰的需求 > 复杂的流程。** 时间花在"想清楚要什么"，不是"怎么控制 AI 执行"。
4. **多模型是补丁，不是默认。** 启用条件：上下文占用 >60% 导致降智、输出 >4000 token 导致后半段降智、需要不同工具能力、单模型反复犯同一种错、需要对抗偏见。其他情况用最强单模型直接干。
5. **三角协作是过渡，大脑内化是终局。** 当前 Leo+Claude Chat+CC，终局是本地系统具备分析、设计、搜索、记忆、大局观、质量判断、轮子意识。
6. **MetaBot 做管道，我们做大脑。** 通信、会话、进程交给开源工具。精力集中在产品定义、需求清晰度、决策质量。
7. **中间产出落盘为文件。** 可追溯、可干预、重启安全。
8. **CC 自评不可靠。** 需要交叉验证（换模型审查或程序化测试），不靠 LLM 自己说"通过了"。

---

## 轮子检查（Wheel Check）

开发任何新组件或新功能前，必须先执行轮子检查：

1. 用至少 3 个关键词在 GitHub 搜索是否有成熟开源方案
2. 列出找到的候选方案（名称、star 数、最近更新时间、功能覆盖度）
3. 如果有 >100 star 且近 6 个月有更新的方案能覆盖 70%+ 需求，优先整合而非自建
4. 只有确认没有合适轮子后才开始自己写代码
5. 轮子检查结果记录在对应的 GitHub Issue 或 commit message 中

**违反此规则的代码不予合并。**

---

## 跨端协作架构

本项目通过两种方式访问 Claude Code：

| 调用方式 | 入口 | Session | 上下文 |
|----------|------|---------|--------|
| PyCharm 本地 | IDE 终端 | 独立 | 与飞书端共享规则文件 |
| 飞书端 | cc-connect WebSocket | 独立 | 与 PyCharm 共享规则文件 |

**关键约束：**
- 规则通过 `CLAUDE.md` 两级架构共享（全局 + 项目级）
- 对话历史通过 `context_board.md` 文件流转
- 图片仅用于视觉内容，禁止传递规则或指令

---

## 核心代码清单

| 文件路径 | 核心职责 |
|----------|----------|
| `src/schema/state.py` | 全局状态树定义（TypedDict + Enum） |
| `src/graph/router.py` | LangGraph 状态机流转拓扑 |
| `src/graph/context_slicer.py` | 上下文切片管理器 |
| `src/config/model_registry.yaml` | 异构模型路由配置（v2） |
| `src/utils/model_gateway.py` | 模型网关（14+ 模型、降级链） |
| `src/security/instruction_guard.py` | 指令歧义防护 |
| `src/security/kpi_trap_detector.py` | KPI陷阱检测 |
| `src/audit/behavior_logger.py` | 行为边界审计日志 |
| `scripts/tonight_deep_research.py` | 深度研究五层管道（主力） |
| `scripts/auto_learn.py` | 自学习循环（30min） |
| `scripts/kb_governance.py` | 知识库治理 |
| `scripts/meta_capability.py` | 元能力层（三级扩展） |
| `scripts/critic_calibration.py` | Critic 校准系统 |
| `scripts/doc_sync_validator.py` | 文档同构校验器 |
| `scripts/roundtable/roundtable.py` | 圆桌核心 Phase 1-4 编排 |
| `scripts/roundtable/crystallizer.py` | 知识结晶 |
| `scripts/roundtable/verifier.py` | 审查闭环 |
| `scripts/roundtable/generator.py` | 生成器 |
| `scripts/roundtable/meta_cognition.py` | 元认知层（当前禁用） |
| `scripts/roundtable/resilience.py` | 韧性机制 |
| `scripts/roundtable/task_spec.py` | TaskSpec 定义与加载 |
| `scripts/regression_check.py` | 功能回归验证 |
| `.ai-state/capability_registry.json` | 功能注册表 |
| `.ai-state/task_specs/` | 圆桌 TaskSpec 定义 |
| `.ai-state/demo_specs/` | Demo 产品配置 |

**导航提示:**
- 修改状态结构 → 编辑 `src/schema/state.py`
- 修改流转逻辑 → 编辑 `src/graph/router.py`
- 修改模型选型 → 编辑 `src/config/model_registry.yaml`
- 修改深度研究管道 → 编辑 `scripts/tonight_deep_research.py`
- 安全增强 → 编辑 `src/security/` 模块
- 行为审计 → 编辑 `src/audit/` 模块

---

## 飞书操作能力

你可以通过飞书 CLI (`lark-cli`) 直接操作飞书：

### 常用命令

```bash
# 发消息
lark-cli im +messages-send --chat-id {chat_id} --text "内容" --as bot

# 创建云文档
lark-cli docs +create --title "标题" --markdown "内容" --as bot

# 更新云文档
lark-cli docs +update --document-id {doc_id} --markdown "内容" --as bot

# 读取消息
lark-cli im +chat-messages-list --chat-id {chat_id} --page-size 5 --as bot

# 多维表格写入
lark-cli bitable +records-create --app-token {token} --table-id {id} --fields '{"字段":"值"}' --as bot
```

### 使用原则

- **短回复（<500字）**：直接发消息
- **长内容（报告/代码/分析）**：创建飞书云文档，消息里放链接
- **结构化数据**：写多维表格
- **操作完成后**：告知用户结果

### 报告输出规则（必须创建 GitHub Issue）

以下报告完成后**必须**自动创建 GitHub Issue 并附完整内容：

| 报告类型 | 触发时机 | Issue 标题格式 |
|----------|----------|----------------|
| 圆桌结果 | Phase 4 完成 | `[圆桌] {topic} - {date}` |
| 诊断报告 | 系统诊断完成 | `[诊断] {诊断名称} - {date}` |
| 修复报告 | 修复任务完成 | `[修复] {修复名称} - {date}` |

**原因**：
- Claude Chat 需要从 GitHub fetch 审查
- 飞书通道单向不可达（Claude Chat → CC 可，CC → Claude Chat 不可）
- GitHub Issue 是 Claude Chat 唯一可访问的报告存储

**实现方式**：
```python
import requests
token = os.getenv("GITHUB_TOKEN")
resp = requests.post(
    "https://api.github.com/repos/lion9999ly/agent-company/issues",
    headers={"Authorization": f"token {token}"},
    json={"title": "[圆桌] XXX", "body": report_content, "labels": ["roundtable"]}
)
print(f"Issue created: {resp.json()['html_url']}")
```

**执行步骤**：
1. 创建 GitHub Issue（上述代码）
2. 将摘要追加写入 `.ai-state/claude_chat_inbox.md`
3. `git add .ai-state/claude_chat_inbox.md && git commit -m "docs: 更新 claude_chat_inbox" && git push`

**摘要格式**：
```markdown
## [类型] 标题 - YYYY-MM-DD HH:MM
- 结果：通过/失败/部分通过
- 关键数据：（核心数字和结论）
- 产出文件：（文件路径列表）
- 待决问题：（如有）
```

### 飞书指令对应的执行脚本

用户在飞书说 → 你应该执行的操作：

| 指令 | 执行脚本 |
|------|----------|
| 深度学习 / 夜间学习 | `scripts/tonight_deep_research.py` |
| 自学习 | `scripts/auto_learn.py` |
| KB治理 | `scripts/kb_governance.py` |
| 圆桌:XXX | `scripts/roundtable/` + TaskSpec |
| 导入文档 | `scripts/feishu_handlers/import_handlers.py` |
| 拉取指令 | `scripts/github_instruction_reader.py` |
| 状态 | 读取 `.ai-state/system_status.md` → 云文档 |
| 监控范围 | 读取 `.ai-state/monitor_scope.json` |

### 统一输出工具

```python
from scripts.feishu_output import update_doc, create_doc, get_or_create_bitable

# 更新/创建云文档
doc_url = update_doc("标题", "markdown内容")

# 发消息 + 云文档
from scripts.feishu_output import notify_with_doc
notify_with_doc(reply_target, send_reply, "标题", "内容", "短消息")
```

---

## 深度研究五层管道架构

`scripts/tonight_deep_research.py` 实现五层分层提炼：

| Layer | 名称 | 输入 | 输出 | 模型 |
|-------|------|------|------|------|
| L1 | 并发搜索 | 搜索词列表 | 原始素材 | o3-deep-research → gpt_5_4 → doubao |
| L2 | 要点提炼 | 原始素材 | 结构化要点 | o3-deep-research → gpt_5_4 |
| L3 | 深度分析 | 要点集合 | 分析报告 | o3-deep-research |
| L4 | 整合输出 | 多份分析 | 最终报告 | o3-deep-research |
| L5 | Critic评审 | 最终报告 | P0/P1/P2 评级 | doubao_seed_pro |

**模型路由 v2 角色分配：**
- `o3-deep-research`: 主力推理（Norway East）
- `gpt_5_4`: 高级降级（同 Norway East）
- `doubao_seed_pro`: 中文搜索 + Critic（火山引擎）
- `tavily`: 英文搜索补充

**降级链：**
```
o3-deep-research 404 → gpt_5_4 → doubao_seed_pro → gpt_4o
```

---

## 三个运行模式

| 模式 | 脚本 | 周期 | 用途 |
|------|------|------|------|
| 自学习 | `auto_learn.py` | 30min | KB 缺口补充、轻量探索 |
| 深度学习 | `tonight_deep_research.py` | 7h | 夜间批量、五层管道 |
| KB治理 | `kb_governance.py` | 手动 | 知识库清洗、去重、confidence校准 |

**飞书指令触发：**
- `深度学习` → 启动 7h 管道
- `自学习` → 启动 30min 循环
- `KB治理` → 执行知识库治理

---

## 元能力层

`scripts/meta_capability.py` 实现三级能力扩展：

| 级别 | 名称 | 示例 |
|------|------|------|
| L1 | 内置能力 | 文件读写、搜索、Bash |
| L2 | 工具注册 | `tools/` 目录动态加载 |
| L3 | 动态生成 | LLM 生成新工具代码 |

**禁止列表（硬编码，不可覆盖）：**
```python
FORBIDDEN_PATTERNS = [
    r"rm\s+-rf", r"rmdir", r"shutil\.rmtree",
    r"\.env", r"api_key", r"API_KEY", r"SECRET",
    r"git\s+push",
    r"os\.system\s*\(", r"subprocess\.Popen\s*\([^)]*shell\s*=\s*True",
    r"DROP\s+TABLE", r"DELETE\s+FROM",
    r"eval\s*\(", r"exec\s*\(",
]
```

---

## Critic 五维改进

`scripts/critic_calibration.py` 实现 P0/P1/P2 分级评审：

| 级别 | 定义 | 处理 |
|------|------|------|
| P0 | 阻塞性错误（数据错误、逻辑矛盾） | 必须修复 |
| P1 | 重要改进（缺失引用、格式问题） | 建议修复 |
| P2 | 小问题（措辞优化） | 可忽略 |

**决策锚定：**
- 评审必须引用具体数据/段落
- 禁止模糊判断（"不够详细"等）
- 必须给出可执行修复建议

**校准机制：**
- 飞书按钮打标 → 积累校准数据
- 自动进化 few-shot 示例库
- 漂移检测 + 主动校准请求

---

## 两套系统边界

本项目存在两套并行系统：

| 系统 | 主入口 | 用途 | 特点 |
|------|--------|------|------|
| LangGraph | `src/graph/router.py` | 飞书研发任务 | 交互式、有来有回 |
| 五层管道 | `scripts/tonight_deep_research.py` | 深度学习批量 | 无人值守、自主探索 |

**共享资源：**
- `model_gateway.py`（模型网关）
- `knowledge_base/`（知识库）
- `src/config/model_registry.yaml`（模型配置）

**各自独立：**
- LangGraph: Agent 逻辑、Critic 逻辑、安全检查
- 五层管道: 并发搜索、提炼流程、L5 Critic

**修改注意：**
- 修改共享资源时需考虑两套系统影响
- LangGraph 侧的 Critic 逻辑尚未升级到 P0/P1/P2
- 两边的知识入库逻辑可能不一致

---

## 质量硬阈值 (不可逾越)

```
文件体积红线: 单文件 ≤ 800 行
函数体积红线: 单函数 ≤ 30 行
圈复杂度红线: 嵌套 ≤ 3 层, 分支 ≤ 3 个
强类型红线: 100% Type Hints, 禁止 Any
```

> ⚠️ 已知违规：text_router.py 本地 ~2292 行，structured_doc.py ~5637 行，runner.py ~909 行
> 这三个文件是拆分优先目标，但当前不阻塞功能开发

**验证命令:**
```bash
python scripts/hooks/quality_check.py --file <path>
```

---

## 安全黑名单 (绝对禁止)

```python
# 以下函数禁止出现在任何代码中
eval()           # 代码注入风险
exec()           # 代码注入风险
os.system()      # 命令注入风险
subprocess.Popen(shell=True)  # 命令注入风险
```

**密钥处理:**
- 禁止硬编码密钥
- 必须从环境变量读取: `os.getenv("SECRET_KEY")`

---

## 文档同构规则

```
代码变更 → 必须同步更新文档
新增 .py 文件 → 必须添加标准化头部 Docstring
新增模块目录 → 必须创建 README.md
```

**头部 Docstring 格式:**
```python
"""
@description: 文件核心职责
@dependencies: 依赖的内部模块
@last_modified: YYYY-MM-DD
"""
```

---

## 评审与拦截机制

### 多模型交叉评审
- **评审模型阵列**: Gemini 2.5 Flash (主评审) + GPT-4o (交叉评审)
- **触发时机**: 任务完成时自动触发
- **通过标准**: 双模型均 score ≥ 8/10，无 blocker
- **评审日志**: `.ai-state/review_logs.jsonl`

### Hook 渐进式拦截
- **第 1-2 次违规:** 警告，允许通过
- **第 3 次违规:** 硬性拦截，必须修复
- **违规记录:** `.ai-state/violation_counts.json`

### 任务后评审机制 🔄
- **每次任务都是一次提高的机会**
- 任务完成后自动触发多模型交叉评审
- 评审不通过需修复后方可进入下一任务
- 改进项记录在 `.ai-state/improvement_backlog.md`
- 详细规范: `.ai-architecture/07-continuous-improvement.md`

---

## 快速参考

### 项目状态
- 当前状态: 开发中
- Git 分支: master
- 最近提交: hotfix architecture cleanup

### 常用命令
```bash
# 运行状态机
python -c "from src.graph.router import app; print(app)"

# 深度学习（五层管道）
python scripts/tonight_deep_research.py

# 自学习（30min）
python scripts/auto_learn.py

# KB治理
python scripts/kb_governance.py

# 检查质量
python scripts/hooks/quality_check.py --all

# 文档同构校验
python scripts/doc_sync_validator.py
```

---

## 更新日志

| 日期 | 变更内容 |
|------|----------|
| 2026-04-12 | **系统设计原则**: 新增 8 条核心设计原则，CLAUDE.md v20260412.1 |
| 2026-04-11 | **轮子检查规则**: 开发新组件前必须先搜索GitHub开源方案，CLAUDE.md v20260411.2 |
| 2026-04-09 | **报告输出规则**: 圆桌结果/诊断报告/修复报告必须创建 GitHub Issue，CLAUDE.md v20260409.1 |
| 2026-04-09 | **Day 17 诊断修复**: 21 个断点修复，agent.py stdin 模式，import_handlers 内联 |
| 2026-04-08 | **Thinking Layer**: 新增咨询规则、GitHub Issue 指令通道文档、CLAUDE.md v20260408.2 |
| 2026-04-08 | **Agent模式**: 移除 --no-input 标志修复、SDK重启机制完善 |
| 2026-04-07 | **Bug修复**: Phase1Output默认值、load_task_spec模糊匹配、meta_cognition禁用开关 |
| 2026-04-07 | **文档更新**: CLAUDE.md v20260407.1，新增圆桌系统、已知违规标注 |
| 2026-04-07 | **根目录清理**: 删除垃圾文件、备份文件 |
| 2026-03-31 | **架构大修**: CLAUDE.md v20260331.1，五层管道、元能力层、Critic校准文档化 |
| 2026-03-31 | **根目录清理**: 删除异常文件、归档散落文档、旧版脚本归档 |
| 2026-03-31 | **安全列表统一**: meta_capability.py + CLAUDE.md 合并禁止项 |
| 2026-03-17 | **建立自驱改进机制**: 任务后评审+改进项追踪，机制文档化 |
| 2026-03-17 | **架构共识**: Echo(CPO)重新定位为基础设施守护者 |
| 2026-03-16 | Phase 1: 新增安全模块(instruction_guard, kpi_trap_detector, behavior_logger) |
| 2026-03-16 | 初始化播种文档，建立上下文入口 |

---

## 模型配置状态

| 模型 | 角色 | 状态 |
|------|------|------|
| Azure o3-deep-research | 深度研究主力 | ✅ **主力模型** |
| Azure gpt_5_4 | 高级降级 | ✅ 可用 |
| Azure gpt-4o | 通用降级 | ✅ 可用 |
| doubao_seed_pro | 中文搜索 + Critic | ✅ 可用 |
| Gemini 2.5 Flash | CPO_Critic(设计目标) | ❌ IP受限 |

---

## 核心铁律摘要

1. **SSOT Rule**：`.ai-architecture/` 下文档是唯一真相源
2. **Model Alignment Rule**：强制异构模型阵列，双模型PASS才可下发
3. **Context Boundary Rule**：CTO/CMO禁止读取全局状态，只接收TaskSlice
4. **Fractal Docs Rule**：代码变则文档变，三层分形强制同构
5. **Triple Defense Rule**：Hook → LLM审查 → 全局熔断
6. **HITL Rule**：人类介入必须遵循"术后缝合"序列
7. **Instruction Guard Rule**：歧义指令必须澄清（"越快越好"等）
8. **KPI Trap Rule**：指标必须伴随边界测试，禁止表面达标
9. **Behavior Audit Rule**：Agent必须声明AI身份，禁止闲聊越权
10. **Continuous Improvement Rule**：每次任务都是提高机会，评审改进闭环

---

## 图片处理强制规则

当消息中包含 `.cc-connect\images\` 路径（如 img_xxx.jpg）时，执行以下流程：

**读取 OCR 文字文件**
图片旁边有同名的 .txt 文件，包含 OCR 识别结果。
使用 Read 工具读取 .txt 文件（将路径中的 .jpg 替换为 .txt）：
- 原路径：.cc-connect\images\img_xxx.jpg
- 读取路径：.cc-connect\images\img_xxx.txt

**处理规则**
- .txt 文件存在：以文件内容作为用户意图进行处理
- .txt 文件不存在：告知用户"图片正在处理中，请10秒后重新发送"
- 禁止直接 Read .jpg 文件
- 禁止基于历史上下文推断图片内容

---

## AI身份声明

所有Agent必须声明：
```
【AI身份声明】
我是[角色名]AI，不是人类。
- 我不会被情绪影响，始终保持理性客观
- 我不会闲聊或扯淡，专注于任务目标
- 我理解我的能力边界，不会越权操作
```

---

## 关键文件 URL（供 claude.ai 快速 fetch）

```
https://raw.githubusercontent.com/lion9999ly/agent-company/refs/heads/main/CLAUDE.md
https://raw.githubusercontent.com/lion9999ly/agent-company/refs/heads/main/scripts/tonight_deep_research.py
https://raw.githubusercontent.com/lion9999ly/agent-company/refs/heads/main/src/utils/model_gateway.py
https://raw.githubusercontent.com/lion9999ly/agent-company/refs/heads/main/src/config/model_registry.yaml
https://raw.githubusercontent.com/lion9999ly/agent-company/refs/heads/main/scripts/feishu_handlers/text_router.py
https://raw.githubusercontent.com/lion9999ly/agent-company/refs/heads/main/scripts/meta_capability.py
https://raw.githubusercontent.com/lion9999ly/agent-company/refs/heads/main/scripts/critic_calibration.py
https://raw.githubusercontent.com/lion9999ly/agent-company/refs/heads/main/.ai-state/product_decision_tree.yaml
https://raw.githubusercontent.com/lion9999ly/agent-company/refs/heads/main/.ai-state/system_log_latest.md
https://raw.githubusercontent.com/lion9999ly/agent-company/refs/heads/main/.ai-state/research_task_pool.yaml
https://raw.githubusercontent.com/lion9999ly/agent-company/refs/heads/main/src/tools/knowledge_base.py
https://raw.githubusercontent.com/lion9999ly/agent-company/refs/heads/main/scripts/roundtable/roundtable.py
https://raw.githubusercontent.com/lion9999ly/agent-company/refs/heads/main/scripts/roundtable/task_spec.py
https://raw.githubusercontent.com/lion9999ly/agent-company/refs/heads/main/scripts/roundtable/crystallizer.py
https://raw.githubusercontent.com/lion9999ly/agent-company/refs/heads/main/scripts/roundtable/verifier.py
https://raw.githubusercontent.com/lion9999ly/agent-company/refs/heads/main/scripts/roundtable/generator.py
https://raw.githubusercontent.com/lion9999ly/agent-company/refs/heads/main/scripts/roundtable/meta_cognition.py
https://raw.githubusercontent.com/lion9999ly/agent-company/refs/heads/main/scripts/roundtable/resilience.py
https://raw.githubusercontent.com/lion9999ly/agent-company/refs/heads/main/.ai-state/claude_chat_inbox.md
```

---

## 三系统共享上下文

### 当前项目阶段
方案论证

### 最近 Handoff 决策要点
（由 handoff 处理器自动更新）

### 系统运行统计
（由 system_log_generator 自动更新）

### 待执行改进清单
见 .ai-state/improvement_backlog_complete.md

---

## Thinking Layer 咨询规则

当你遇到以下类型的问题时，应通过 thinking layer（claude_bridge.py）咨询 Claude Chat：

### 需要咨询 Claude Chat 的问题类型
- **架构设计决策**：新增模块怎么设计、模块间接口怎么定义
- **产品判断**：feature 优先级、用户体验取舍
- **竞品分析的深度解读**：需要人类视角的战略洞察
- **任何影响范围大的决定**：不确定但可能影响项目方向的决策

### 不需要咨询 Claude Chat 的问题类型
- **bug 修复**：直接修
- **配置变更**：直接改
- **日常执行任务**：直接跑（如运行脚本、生成报告）

### 咨询流程
1. 查询 `thinking_history.jsonl` 中是否有类似问题的历史记录
2. 如有历史记录，参考历史结论执行
3. 如无历史，调用 `claude_bridge.call_claude_thinking(prompt)` 咨询
4. 咨询结果自动保存到 `thinking_history.jsonl`

### CDP 桥接状态
- CDP 端口（9333）：当前**不可用**
- 启用方法：运行 `powershell -File scripts/chrome_cdp_restart.ps1`
- Fallback：Profile 模式 / Edge 模式

### Claude Chat 指令通道（反向）
Claude Chat → CC 的指令传递通过 GitHub Issue：
- 见 `.ai-state/instruction_channel.md`
- 飞书指令："拉取指令" 执行 GitHub Issue

---

## 重构/拆分规则

任何涉及文件拆分、重命名、模块重组的任务，必须执行以下步骤：

1. **重构前**：运行 `python scripts/regression_check.py`，保存结果为 `pre_refactor_check.txt`
2. **执行重构**
3. **重构后**：再次运行 `python scripts/regression_check.py`，保存结果为 `post_refactor_check.txt`
4. **对比两份结果**：任何从 ✅ 变为 ❌ 或 ⚠️ 的项都是 bug，必须修复后才能 commit
5. **如果新增了功能**：必须同步更新 `.ai-state/capability_registry.json`

违反此规则的 commit 视为不合格。

---

## 能力注册表

所有飞书指令、内部功能、定时任务登记在 `.ai-state/capability_registry.json`。

**验证命令：**
```bash
python scripts/regression_check.py          # 全量检查
python scripts/regression_check.py --quick   # 快速检查
```

---

## 任务完成提示音

每次完成用户在终端直接交给你的任务后，运行 `beep.bat` 发出提示音：

```bash
./beep.bat
```

这使用 Windows 内置扬声器发出两声蜂鸣，通知用户任务已完成。

---

*本文档由 Claude Code 自动生成，遵循 `.ai-architecture/` 架构规范*