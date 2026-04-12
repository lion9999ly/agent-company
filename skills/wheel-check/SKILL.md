---
name: wheel-check
description: 轮子检查 - 开发新组件前必须先搜索开源方案
type: skill
version: 2026-04-12.1
---

# Wheel Check Skill

## 核心原则

> **先找轮子，再考虑造。**

开发任何新组件或新流程前，必须先搜索是否有成熟开源方案。

---

## 检查标准

| 指标 | 阈值 | 说明 |
|------|------|------|
| **Stars 数** | ≥100 | 社区认可度 |
| **最近更新** | ≤6 个月 | 项目活跃度 |
| **需求覆盖** | ≥70% | 功能匹配度 |

**整合条件**：三个指标全部满足时，优先整合而非自建。

---

## 搜索渠道

| 渠道 | 用途 | 搜索方式 |
|------|------|----------|
| **GitHub** | 代码库、框架 | 关键词 + language filter |
| **Awesome Lists** | 领域精选 | awesome-xxx 仓库 |
| **npm** | JavaScript 包 | npm search |
| **PyPI** | Python 包 | pip search 或 pypi.org |
| **Hacker News** | 新兴项目 | 搜索讨论热度 |

---

## 检查流程

```
开始开发新组件/流程
    │
    ▼
搜索开源方案（≥3 个关键词）
    │
    ▼
评估候选方案
    │
    ├─ 有 >100 star + 近6月更新 + 70%覆盖 ──→ 整合
    │                                          │
    │                                          ▼
    │                                         验证整合可行性
    │                                          │
    │                                          ├─ 可行 ──→ 整合方案
    │                                          │
    │                                          └─ 不可行 ──→ 继续检查
    │
    ▼
确认无合适轮子
    │
    ▼
记录搜索结果
    │
    ▼
开始自建
```

---

## 搜索关键词技巧

```bash
# GitHub 搜索示例
# 1. 基础搜索
github.com/search?q=模型网关+language:Python

# 2. Star 过滤
github.com/search?q=模型网关+stars:>100

# 3. 组合搜索
github.com/search?q=model+gateway+litellm+stars:>100+language:Python

# 4. Awesome Lists
github.com/search?q=awesome+ai+tools
github.com/search?q=awesome+llm
```

---

## 评估模板

每个候选方案记录：

| 项目 | Stars | 最后更新 | 首页 | 功能覆盖 | 结论 |
|------|-------|----------|------|----------|------|
| LiteLLM | 42k | 今日 | github.com/BerriAI/litellm | 95% | ✅ 整合 |
| open_deep_research | 11k | 今日 | LangChain | 70% | ⚠️ 部分覆盖 |
| X 项目 | 50 | 2年前 | ... | 80% | ❌ 不活跃 |

---

## 记录要求

每次轮子检查必须记录在：

1. **GitHub Issue** - 关联任务
2. **Commit Message** - 开发自建时声明
3. **`.ai-state/wheel_check_log.jsonl`** - 长期积累

**记录格式**：
```json
{
  "date": "2026-04-12",
  "task": "模型网关替换",
  "candidates": [
    {"name": "LiteLLM", "stars": 42000, "last_update": "2026-04-12", "coverage": 95}
  ],
  "decision": "整合 LiteLLM",
  "reason": "42k star，今日活跃，95% 功能覆盖"
}
```

---

## 已有轮子检查结果

| 组件 | 决策 | 轮子 | 原因 |
|------|------|------|------|
| 模型网关 | 整合 | LiteLLM | 42k star, 95% 覆盖 |
| 深度研究搜索层 | 整合 | smolagents | Tool 可插拔 + LiteLLM 原生对接 |
| MetaBot | 整合 | MetaBot | 开源 WebSocket 桥接 |
| open_deep_research | 暂缓 | LangChain | 搜索层硬编码，仅 70% 覆盖 |
| OpenSpace | 整合 | HKUDS | Skill 自进化能力 |

---

## 违反规则后果

- **代码不予合并**
- **必须重新评估**
- **记录违规事件**

---

## 快速检查脚本

```python
def wheel_check(component_type: str, keywords: list) -> dict:
    """轮子检查"""
    results = search_github(keywords, min_stars=100)
    
    for r in results:
        if r['stars'] >= 100 and r['updated_within_6mo'] and r['coverage'] >= 70:
            return {
                "decision": "integrate",
                "candidate": r,
                "reason": f"{r['stars']} stars, {r['coverage']}% coverage"
            }
    
    return {
        "decision": "build",
        "reason": "No suitable wheel found after checking",
        "searched": keywords
    }
```

---

## 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| 2026-04-12.1 | 2026-04-12 | 初始版本，基于 CLAUDE.md 轮子检查规则 |