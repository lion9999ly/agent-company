# CLAUDE.md 版本号（每次修改必须更新此版本号）

**VERSION: 20260318.4**

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
| `src/config/agents.yaml` | 异构模型路由配置 |
| `src/security/instruction_guard.py` | 指令歧义防护 |
| `src/security/kpi_trap_detector.py` | KPI陷阱检测 |
| `src/audit/behavior_logger.py` | 行为边界审计日志 |
| `scripts/doc_sync_validator.py` | 文档同构校验器 |

**导航提示:**
- 修改状态结构 → 编辑 `src/schema/state.py`
- 修改流转逻辑 → 编辑 `src/graph/router.py`
- 修改上下文切片 → 编辑 `src/graph/context_slicer.py`
- 修改模型选型 → 编辑 `src/config/agents.yaml`
- 安全增强 → 编辑 `src/security/` 模块
- 行为审计 → 编辑 `src/audit/` 模块

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

**执行命令:**
```bash
python scripts/post_task_review.py --task <task_id> --files <file1> <file2>
```

---

## 快速参考

### 项目状态
- 当前状态: 开发中
- Git 分支: master
- 最近提交: 更新图结构

### 常用命令
```bash
# 运行状态机
python -c "from src.graph.router import app; print(app)"

# 执行评审
python scripts/codex_reviewer.py --create-request pre_execution CLAUDE.md

# 检查质量
python scripts/hooks/quality_check.py --all

# Plan管理
python scripts/plan_manager.py  # 查看当前Plan
python -c "from scripts.plan_manager import get_plan_manager; print(get_plan_manager().list_plans())"

# 文档同构校验
python scripts/doc_sync_validator.py  # 生成同步报告
```

---

## 更新日志

| 日期 | 变更内容 |
|------|----------|
| 2026-03-17 | **建立自驱改进机制**: 任务后评审+改进项追踪，机制文档化 |
| 2026-03-17 | **架构共识**: Echo(CPO)重新定位为基础设施守护者；所有Agent统一Azure GPT-4o |
| 2026-03-17 | 新增`call_azure_openai()`方法，dual_review支持Azure降级 |
| 2026-03-16 | 配置Gemini API，实现CPO_Critic双模型评审 |
| 2026-03-16 | Phase 4: 增强文档同构校验，集成到router.py |
| 2026-03-16 | Phase 1: 新增安全模块(instruction_guard, kpi_trap_detector, behavior_logger) |
| 2026-03-16 | 初始化播种文档，建立上下文入口 |

---

## 模型配置状态

| 模型 | 角色 | 状态 |
|------|------|------|
| Azure GPT-4o | CPO/CTO/CMO/CPO_Critic(降级)/CRO | ✅ **主力模型** |
| Gemini 2.5 Flash | CPO_Critic(设计目标) | ❌ IP受限 |
| Qwen Max | CPO_Critic(设计目标)/CTO/CMO(原设计) | ❌ API Key无效 |
| Claude | 当前会话 | ✅ 备用 |

**架构共识 (2026-03-17)**：
- 所有Agent统一使用 Azure GPT-4o
- 当 Gemini/Qwen 可用时自动切换为双模型评审
- Echo(CPO) 重新定位为"基础设施守护者"

**测试命令**:
```bash
python src/utils/model_gateway.py  # 测试Gemini连接
python src/agents/cpo_critic.py    # 测试评审功能
```

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

*本文档由 Claude Code 自动生成，遵循 `.ai-architecture/` 架构规范*