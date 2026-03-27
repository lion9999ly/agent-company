# Phase 0.4 — Critic 评审盲区修复（CDO 输出纳入评审）

## 改动文件: src/graph/router.py
## 改动量: 2 处，约 15 行

---

### 改动 1: `_run_critic_review` 函数签名 + prompt（约第 412 行）

**原代码:**
```python
def _run_critic_review(task_goal: str, cto_output: str, cmo_output: str) -> dict:
    """执行主从评审逻辑，返回 {"decision": "PASS"/"REJECT", "feedback": str}"""
    gateway = get_model_gateway()
    review_input = (
        f"## 原始任务\n{task_goal}\n\n"
        f"## CTO技术方案\n{cto_output[:3000]}\n\n"
        f"## CMO市场策略\n{cmo_output[:3000]}\n\n"
        "## 评审要求\n请评审以上方案的可行性、完整性和风险。\n"
        "如果方案合格，回复 PASS。\n"
        "如果方案有问题，回复 REJECT 并给出 <Modify_Action> 标签包裹的具体修改指令。"
    )
```

**改为:**
```python
def _run_critic_review(task_goal: str, cto_output: str, cmo_output: str, cdo_output: str = "") -> dict:
    """执行主从评审逻辑，返回 {"decision": "PASS"/"REJECT", "feedback": str}"""
    gateway = get_model_gateway()
    review_input = (
        f"## 原始任务\n{task_goal}\n\n"
        f"## CTO技术方案\n{cto_output[:3000]}\n\n"
        f"## CMO市场策略\n{cmo_output[:3000]}\n\n"
    )
    if cdo_output:
        review_input += f"## CDO设计方案\n{cdo_output[:3000]}\n\n"
    review_input += (
        "## 评审要求\n请评审以上方案的可行性、完整性和风险。\n"
        "特别关注：技术方案与设计方案之间是否存在冲突（如散热空间、天线布局、重量预算）。\n"
        "如果方案合格，回复 PASS。\n"
        "如果方案有问题，回复 REJECT 并给出 <Modify_Action> 标签包裹的具体修改指令。"
    )
```

---

### 改动 2: `cpo_critic_node` 调用处（约第 459-472 行）

**原代码:**
```python
    task_goal = state.get("task_contract", {}).get("task_goal", "未知任务")
    cto_output = execution.get("cto_output", {})
    cmo_output = execution.get("cmo_output", {})

    # 尝试多种字段名获取输出
    cto_text = cto_output.get("protocol_code") or cto_output.get("output") or cto_output.get("result") or ""
    cmo_text = cmo_output.get("market_strategy") or cmo_output.get("output") or cmo_output.get("result") or ""

    if not cto_text and not cmo_text:
        print("[CPO_Critic] 无输出可评审，直接 PASS")
        return {"execution": {**execution, "critic_decision": "PASS"}}

    print("[CPO_Critic] 启动主从双模型评审...")
    review = _run_critic_review(task_goal, str(cto_text), str(cmo_text))
```

**改为:**
```python
    task_goal = state.get("task_contract", {}).get("task_goal", "未知任务")
    cto_output = execution.get("cto_output", {})
    cmo_output = execution.get("cmo_output", {})
    cdo_output = execution.get("cdo_output", {})

    # 尝试多种字段名获取输出
    cto_text = cto_output.get("protocol_code") or cto_output.get("output") or cto_output.get("result") or ""
    cmo_text = cmo_output.get("market_strategy") or cmo_output.get("output") or cmo_output.get("result") or ""
    cdo_text = cdo_output.get("design_proposal") or cdo_output.get("output") or cdo_output.get("result") or ""

    if not cto_text and not cmo_text and not cdo_text:
        print("[CPO_Critic] 无输出可评审，直接 PASS")
        return {"execution": {**execution, "critic_decision": "PASS"}}

    print(f"[CPO_Critic] 启动主从双模型评审... (CTO:{bool(cto_text)}, CMO:{bool(cmo_text)}, CDO:{bool(cdo_text)})")
    review = _run_critic_review(task_goal, str(cto_text), str(cmo_text), str(cdo_text))
```

---

## 验证方法

改完后发一个涉及设计的研发任务（如"设计V1头盔外观方案"），看终端日志：
- 应该能看到 `[CPO_Critic] 启动主从双模型评审... (CTO:True, CMO:True, CDO:True)`
- Critic 的反馈中应该包含对设计方案的评价
