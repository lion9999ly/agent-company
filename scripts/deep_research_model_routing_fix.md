# 深度研究管道 — 模型路由修复

> CC 执行文档 — 2026-03-30
> 目标：基于实际可用模型重新分配深度研究管道的模型路由
> 文件：`scripts/tonight_deep_research.py`
> 完成后并入 deep_research_pipeline_fix.md 的 commit 一起提交

---

## 可用模型（已验证）

| 模型 | 特点 | 成本 |
|------|------|------|
| gpt_5_4 | Azure 旗舰，最强推理 | $$$$ |
| gemini_3_1_pro | Google 最新旗舰，长上下文 | $$$ |
| gemini_3_pro | Google 第三代旗舰 | $$ |
| gemini_2_5_pro | Google 稳定版旗舰 | $$ |
| gemini_2_5_flash | Google 快速轻量 | $ |

## 修复

### 1. `_get_model_for_role()` — 约第 30 行

替换整个函数：

```python
def _get_model_for_role(role: str) -> str:
    """深度研究流程中，各角色使用的模型

    分工原则：
    - CTO/CPO 用 gpt_5_4（最强推理，核心决策）
    - CMO 用 gemini_3_pro（独立视角，避免同模型自说自话）
    - CDO 用 gemini_3_1_pro（最新旗舰，多模态强）
    """
    role_model_map = {
        "CTO": "gpt_5_4",
        "CMO": "gemini_3_pro",
        "CDO": "gemini_3_1_pro",
        "CPO": "gpt_5_4",
    }
    return role_model_map.get(role.upper(), "gpt_5_4")
```

### 2. `_get_model_for_task()` — 约第 41 行

替换整个函数：

```python
def _get_model_for_task(task_type: str) -> str:
    """各任务环节使用的模型

    分层原则：
    - 轻量任务 → gemini_2_5_flash（快且便宜）
    - 核心推理/整合 → gpt_5_4（最强可用）
    - 评审/挑战 → gemini_3_1_pro（独立视角，不能用同一个模型审自己）
    - 修复/补充 → gemini_2_5_pro（稳定可靠，成本适中）
    """
    task_model_map = {
        "discovery": "gemini_2_5_flash",
        "query_generation": "gemini_2_5_flash",
        "data_extraction": "gemini_2_5_flash",
        "role_assign": "gemini_2_5_flash",
        "synthesis": "gpt_5_4",
        "re_synthesis": "gpt_5_4",
        "final_synthesis": "gpt_5_4",
        "critic_challenge": "gemini_3_1_pro",
        "knowledge_extract": "gemini_2_5_flash",
        "fix": "gemini_2_5_pro",
        "cdo_fix": "gemini_2_5_pro",
    }
    return task_model_map.get(task_type, "gpt_5_4")
```

### 3. fallback 单 CPO 模式 — 约第 774 行

当前代码：
```python
fallback = _call_model("o3", synthesis_prompt_fallback, ...)
```

改为：
```python
fallback = _call_model("gpt_5_4", synthesis_prompt_fallback, ...)
```

## 设计说明

**为什么 CTO 和 CMO 用不同模型？**
避免"同模型自说自话"——如果 CTO（gpt_5_4）和 CMO（gemini_3_pro）用不同模型，它们的分析会有真正的视角差异。Synthesis 阶段再由 gpt_5_4 整合，形成交叉验证效果。

**为什么 Critic 用 gemini_3_1_pro？**
Critic 不能用 gpt_5_4——因为 Synthesis 也是 gpt_5_4，自己审自己没意义。用 gemini_3_1_pro 做 Critic，确保挑战来自独立模型。

**为什么 fix 用 gemini_2_5_pro 而不是 gpt_5_4？**
fix 是补充性任务，不需要最强模型。gemini_2_5_pro 稳定且便宜，省 gpt_5_4 的 quota 给核心环节。

---

## 与 deep_research_pipeline_fix.md 的关系

本文件替代 deep_research_pipeline_fix.md 中 Bug 1 的 Step 2（原方案是修 deployment 名，现改为换模型）。Bug 1 Step 1（404 告警机制）保留不变。

一起提交：
```bash
git add -A && git commit -m "fix: deep research pipeline — model routing, 404 alert, extract wiring, critic unified, consistency check"
```

**不要重启服务，Leo 手动重启。**
