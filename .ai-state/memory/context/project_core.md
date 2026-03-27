---
name: project_context
description: 智能骑行头盔虚拟研发中心项目核心上下文
type: reference
---

# 项目核心上下文

## 项目身份
- **名称**: 智能骑行头盔虚拟研发中心
- **阶段**: 开发中
- **架构**: Multi-Agent虚拟组织

## 技术栈
- **语言**: Python 3.11+
- **框架**: LangGraph (状态机)
- **模型阵列**: Azure GPT-5.4 + Gemini 3.1 Pro + Claude Opus 4.6

## Agent组织架构
| Agent | 职责 | 主力模型 |
|-------|------|----------|
| CPO (Echo) | 意图拆解、契约生成、基础设施守护 | GPT-5.4 |
| CTO | 软硬件研发、代码生成 | GPT-5.4 |
| CMO | 市场调研、竞品分析 | o3-deep-research |
| CPO_Critic | 评审把关、质量审查 | Gemini 3.1 Pro + Claude Opus 4.6 |
| CRO | 代码审查、质量把控 | Claude Sonnet 4.6 |

## 质量红线
- 文件体积: ≤800行
- 函数体积: ≤30行
- 圈复杂度: 嵌套≤3层, 分支≤3个
- 强类型: 100% Type Hints

## 安全黑名单
- eval(), exec(), os.system(), subprocess.Popen(shell=True)
- 硬编码密钥

## 核心文档路径
- 全局架构: `.ai-architecture/00-global-architecture.md`
- 质量红线: `.ai-architecture/01-quality-redlines.md`
- Agent职责: `.ai-architecture/AGENTS.md`
- 持续改进: `.ai-architecture/07-continuous-improvement.md`

## 分层记忆系统
- 短期记忆: `.ai-state/layered_memory/session/`
- 中期记忆: `.ai-state/layered_memory/working/`
- 长期记忆: `.ai-state/layered_memory/longterm/`
- 检查点: `.ai-state/layered_memory/checkpoints/`