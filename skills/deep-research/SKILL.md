---
name: deep-research
description: Use when conducting multi-source research requiring parallel search, structured extraction, cross-verification, and synthesis report generation
metadata:
  author: leo
  version: "1.0"
---

# Deep Research Skill

## Overview

深度研究五层管道是无人值守批量研究引擎，通过并发搜索、要点提炼、深度分析、整合输出、Critic 评审实现高质量研究报告。

**核心原则：每个 Layer 有明确职责，模型降级链确保可用性。**

## When to Use

- 需要多源搜索验证的供应链调研
- 竞品深度分析（参数、成本、成熟度对比）
- 技术选型研究（芯片、光学、声学方案）
- 夜间批量研究任务（7h 管道）

**When NOT to Use:**
- 简单的单关键词搜索（直接 WebSearch）
- 已有成熟答案的问题（查 KB）
- 紧急任务（五层管道需要时间）

## Five Layer Pipeline

```
L1: 并发搜索 → 多关键词并行搜索，原始素材收集
L2: 要点提炼 → 结构化提取关键数据、参数、结论
L3: 淞度分析 → 跨源对比、矛盾检测、置信度标注
L4: 整合输出 → 合成最终报告，引用完整
L5: Critic评审 → P0/P1/P2 分级，数据错误检测
```

## Model Routing v2

| 角色 | 首选模型 | 降级链 |
|------|----------|--------|
| 搜索主力 | o3-deep-research | gpt_5_4 → doubao |
| 要点提炼 | o3-deep-research | gpt_5_4 |
| 淞度分析 | o3-deep-research | gpt_5_4 |
| 整合输出 | o3-deep-research | - |
| Critic评审 | doubao_seed_pro | gpt_4o |

## Search Channels

| 通道 | 用途 | 特点 |
|------|------|------|
| Tavily | 英文搜索首选 | API 直接调用 |
| doubao | 中文搜索首选 | 火山引擎中文增强 |
| Gemini/Grok | 备用通道 | Tavily 失败时启用 |

**禁止用 Claude Code WebSearch（harness 配置问题）**

## Known Pitfalls

| 陷阱 | 规避方法 |
|------|----------|
| 搜索结果空 | 多关键词并行，语言检测分流 |
| 模型 404 | 记录 health_monitor，触发降级链 |
| L5 Critic 数据错误 | P0 必须修复，引用具体段落 |
| 报告无引用 | L4 整合时强制引用格式 |
| 知识库重复入库 | KB 治理脚本去重 |

## Verification Criteria

- [ ] L5 Critic passed=True 或 P0 清零
- [ ] 报告有完整引用（每条结论有来源）
- [ ] 知识库入库成功（save_task_findings）
- [ ] 报告保存到 .ai-state/reports/

## Key Files

```
scripts/deep_research/runner.py         # 调度入口
scripts/deep_research/pipeline.py       # L1-L4 核心管道
scripts/deep_research/models.py         # 模型路由
scripts/deep_research/critic.py         # L5 Critic 评审
scripts/deep_research/extraction.py     # 结构化提取
scripts/deep_research/learning.py       # 知识入库
scripts/deep_research/health_monitor.py # 模型健康监控
.ai-state/reports/*.md                  # 研究报告
.ai-state/research_task_pool.yaml       # 任务池
```

## Quick Reference

```bash
# 通过飞书触发
深度学习 / 夜间学习

# 手动运行
python scripts/deep_research/runner.py --run-all

# 查看任务池
cat .ai-state/research_task_pool.yaml

# 查看报告
ls .ai-state/reports/
```

## Built-in Research Tasks

```python
RESEARCH_TASKS = [
    {"id": "goertek_profile", "title": "歌尔股份完整画像"},
    {"id": "alternative_jdm", "title": "替代JDM供应商对比"},
    {"id": "optical_suppliers", "title": "光学方案商深度对比"},
    {"id": "audio_camera_suppliers", "title": "声学与摄像头方案商对比"},
    {"id": "why_goertek", "title": "综合对比：为什么选歌尔"},
]
```