# Phase 1.3 + 1.4 — Critic 注入规则 + 数据校验能力

## 改动文件: src/graph/router.py
## 改动: `_run_critic_review` 和 `cpo_critic_node` 两个函数重写

---

### 改动 1: `_run_critic_review` 完整替换（约第 412-434 行）

把整个 `_run_critic_review` 函数替换为以下版本。
核心变化：加入规则注入 + 知识库数据交叉校验。

```python
def _run_critic_review(task_goal: str, cto_output: str, cmo_output: str, cdo_output: str = "",
                       rules_text: str = "", kb_verification_text: str = "") -> dict:
    """执行主从评审逻辑，返回 {"decision": "PASS"/"REJECT", "feedback": str}

    Phase 1 升级：三层评审体系
    1. 结构化规则检查（rules_text）
    2. 知识库数据交叉校验（kb_verification_text）
    3. LLM 自由评审（原有逻辑）
    """
    gateway = get_model_gateway()

    # === 构建评审 prompt ===
    review_input = (
        f"## 原始任务\n{task_goal}\n\n"
        f"## CTO技术方案\n{cto_output[:3000]}\n\n"
        f"## CMO市场策略\n{cmo_output[:3000]}\n\n"
    )
    if cdo_output:
        review_input += f"## CDO设计方案\n{cdo_output[:3000]}\n\n"

    # === Layer 1: 结构化规则检查 ===
    if rules_text:
        review_input += f"{rules_text}\n\n"

    # === Layer 2: 知识库数据交叉校验 ===
    if kb_verification_text:
        review_input += (
            f"## 知识库参考数据（用于交叉校验）\n"
            f"以下是项目知识库中与本任务相关的技术档案。请用这些数据交叉验证 Agent 输出中的关键声明。\n"
            f"如果 Agent 声明的参数（芯片型号、功耗、价格、性能指标）与知识库数据矛盾，必须指出。\n"
            f"如果知识库中没有相关数据可验证，标记为 [UNVERIFIED]。\n\n"
            f"{kb_verification_text}\n\n"
        )

    # === Layer 3: 自由评审 ===
    review_input += (
        "## 评审要求\n"
        "请按以下顺序输出评审结论：\n\n"
    )

    if rules_text:
        review_input += (
            "### 一、规则检查\n"
            "逐项检查上面的规则清单，每条给出 ✅ PASS / ❌ FAIL / ⚠️ UNVERIFIED + 理由\n\n"
        )

    if kb_verification_text:
        review_input += (
            "### 二、数据校验\n"
            "对比 Agent 输出中的关键数据与知识库参考数据，列出：\n"
            "- [VERIFIED] 与知识库一致的数据点\n"
            "- [CONFLICT] 与知识库矛盾的数据点（必须具体说明差异）\n"
            "- [UNVERIFIED] 知识库中无法验证的数据点\n\n"
        )

    review_input += (
        "### 三、综合评审\n"
        "评审方案的可行性、完整性和风险。\n"
        "特别关注：技术方案与设计方案之间是否存在冲突（如散热空间、天线布局、重量预算）。\n"
        "第一行只写 PASS 或 REJECT。\n"
        "如果 REJECT，用 <Modify_Action> 标签包裹具体修改指令。"
    )

    system_prompt = get_agent_prompt("critic")

    # === 主从评审（原有逻辑不变） ===
    primary = gateway.call_gemini("critic_gemini", review_input, system_prompt, "review")
    if primary.get("success") and "PASS" in primary["response"].upper():
        return {"decision": "PASS", "feedback": primary["response"]}

    secondary = gateway.call_azure_openai("cpo", review_input, system_prompt, "review")
    if not primary.get("success") and secondary.get("success"):
        decision = "PASS" if "PASS" in secondary["response"].upper() else "REJECT"
        return {"decision": decision, "feedback": secondary.get("response", "")}

    if secondary.get("success") and "PASS" in secondary["response"].upper():
        return {"decision": "PASS", "feedback": f"[有条件通过]\n主评审建议:\n{primary.get('response', '')[:2000]}"}

    feedback = primary.get("response", "") + "\n---\n" + secondary.get("response", "")
    return {"decision": "REJECT", "feedback": feedback[:4000]}
```

---

### 改动 2: `cpo_critic_node` 完整替换（约第 437-476 行）

把整个 `cpo_critic_node` 函数替换为以下版本。
核心变化：评审前获取规则 + 检索知识库做数据校验。

```python
def cpo_critic_node(state: AgentGlobalState) -> dict:
    """CPO 评审节点：结构化规则检查 + 知识库数据校验 + 主从双模型评审

    Phase 1 升级：三层评审体系
    幂等性保护：确保只执行一次评审
    """
    execution = state.get("execution", {})

    # 【幂等性检查】如果已经评审过，直接返回
    if execution.get("critic_decision"):
        print(f"[CPO_Critic] 已评审过: {execution.get('critic_decision')}")
        return {}

    # 【保险】在评审前检查 retry_count 是否超限
    retry_count = state.get("control", {}).get("retry_counts", {}).get("cpo_plan", 0)
    if retry_count >= 2:
        print(f"[CPO_Critic] 重试已达上限 ({retry_count} 次)，强制 PASS")
        synthesis_output = execution.get("synthesis_output", "")
        return {"execution": {**execution,
            "critic_decision": "PASS",
            "critic_feedback": "[重试上限，自动通过]"}}

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

    # === Phase 1.3: 获取相关检查规则 ===
    rules_text = ""
    try:
        from src.utils.critic_rules import get_relevant_rules, format_rules_for_critic
        relevant_rules = get_relevant_rules(task_goal)
        if relevant_rules:
            rules_text = format_rules_for_critic(relevant_rules)
            print(f"[CPO_Critic] 注入 {len(relevant_rules)} 条检查规则")
        else:
            print(f"[CPO_Critic] 无相关检查规则")
    except Exception as e:
        print(f"[CPO_Critic] 规则加载失败: {e}")

    # === Phase 1.4: 知识库数据校验 ===
    kb_verification_text = ""
    try:
        # 检索与任务相关的技术档案（侧重有具体数据的条目）
        kb_entries = search_knowledge(task_goal, limit=10)
        if kb_entries:
            parts = []
            for entry in kb_entries:
                title = entry.get("title", "")
                content = entry.get("content", "")
                confidence = entry.get("confidence", "")
                tags = entry.get("tags", [])

                # 优先选择有硬数据的条目（anchor、internal、decision_tree）
                is_high_value = (
                    "anchor" in tags or "internal" in tags or
                    "decision_tree" in tags or confidence == "authoritative"
                )

                # 跳过 speculative 条目（不适合做数据校验基准）
                if "speculative" in tags:
                    continue

                if is_high_value:
                    parts.append(f"### [高可信] {title}\n{content[:1500]}")
                elif len(content) > 200:
                    parts.append(f"### {title}\n{content[:800]}")

            if parts:
                kb_verification_text = "\n\n".join(parts[:8])  # 最多 8 条
                print(f"[CPO_Critic] 知识库数据校验: {len(parts)} 条参考")
            else:
                print(f"[CPO_Critic] 知识库无高质量参考数据")
        else:
            print(f"[CPO_Critic] 知识库检索无结果")
    except Exception as e:
        print(f"[CPO_Critic] 知识库检索失败: {e}")

    print(f"[CPO_Critic] 启动三层评审... (CTO:{bool(cto_text)}, CMO:{bool(cmo_text)}, CDO:{bool(cdo_text)}, Rules:{bool(rules_text)}, KB:{bool(kb_verification_text)})")
    review = _run_critic_review(task_goal, str(cto_text), str(cmo_text), str(cdo_text),
                                 rules_text=rules_text, kb_verification_text=kb_verification_text)
    print(f"[CPO_Critic] 结果: {review['decision']}")
    return {"execution": {**execution,
        "critic_decision": review["decision"],
        "critic_feedback": review["feedback"][:4000]}}
```

---

## 验证方法

1. 先入库至少一条规则（用于测试）：
```python
python -c "
from src.utils.critic_rules import add_critic_rule
add_critic_rule(
    check_description='mesh 对讲方案必须以 Cardo DMC 性能指标为对标基准',
    trigger_context='mesh 对讲 intercom 通讯方案 Mesh 蓝牙',
    severity='must_check',
    source='manual_anchor'
)
print('Done')
"
```

2. 发一个 mesh 相关的研发任务，观察终端日志：
   - `[CriticRules] 匹配完成: N 条规则中 M 条相关`
   - `[CPO_Critic] 注入 M 条检查规则`
   - `[CPO_Critic] 知识库数据校验: K 条参考`
   - `[CPO_Critic] 启动三层评审... (CTO:True, CMO:True, CDO:True, Rules:True, KB:True)`

3. 在 Critic 的输出中应该能看到：
   - 规则逐项检查结论（✅/❌/⚠️）
   - 数据校验结论（VERIFIED/CONFLICT/UNVERIFIED）
   - 综合评审意见
