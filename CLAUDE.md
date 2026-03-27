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

**自动加载机制:**
Claude Code 会在会话开始时自动读取此文件。如需深度上下文，请按需阅读上述文档。

---

## 核心代码清单

| 文件路径 | 核心职责 |
|----------|----------|
| `src/schema/state.py` | 全局状态树定义（TypedDict + Enum） |
| `src/graph/router.py` | LangGraph 状态机流转拓扑 |
| `src/config/agents.yaml` | 异构模型路由配置 |

**导航提示:**
- 修改状态结构 → 编辑 `src/schema/state.py`
- 修改流转逻辑 → 编辑 `src/graph/router.py`
- 修改模型选型 → 编辑 `src/config/agents.yaml`

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

### Codex 交叉评审
- **评审模型:** OpenAI GPT-4o
- **触发时机:** 代码写入前、架构变更时
- **通过标准:** score ≥ 8/10，无 blocker

### Hook 渐进式拦截
- **第 1-2 次违规:** 警告，允许通过
- **第 3 次违规:** 硬性拦截，必须修复
- **违规记录:** `.ai-state/violation_counts.json`

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
```

---

## 更新日志

| 日期 | 变更内容 |
|------|----------|
| 2026-03-16 | 初始化播种文档，建立上下文入口 |

---

*本文档由 Claude Code 自动生成，遵循 `.ai-architecture/` 架构规范*