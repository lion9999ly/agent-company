# CLAUDE.md 版本号（每次修改必须更新此版本号）

**VERSION: 20260331.1**

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

**导航提示:**
- 修改状态结构 → 编辑 `src/schema/state.py`
- 修改流转逻辑 → 编辑 `src/graph/router.py`
- 修改模型选型 → 编辑 `src/config/model_registry.yaml`
- 修改深度研究管道 → 编辑 `scripts/tonight_deep_research.py`
- 安全增强 → 编辑 `src/security/` 模块
- 行为审计 → 编辑 `src/audit/` 模块

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

*本文档由 Claude Code 自动生成，遵循 `.ai-architecture/` 架构规范*