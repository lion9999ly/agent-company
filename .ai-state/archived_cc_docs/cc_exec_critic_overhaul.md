# CC 执行文档: Critic 五维改进

> 日期: 2026-03-31
> 依赖: Part 3（元能力层）已完成
> 涉及文件: `scripts/tonight_deep_research.py`
> 提交: `git add -A && git commit -m "feat: Critic overhaul — graded P0/P1/P2, decision anchor, data-backed, few-shot calibration, capability-verified"`
> **不要重启服务，Leo 手动重启。**

---

## 一、改造目标

Critic 当前问题：挑战质量低，"建议加强分析"式废话多，真正影响决策的 P0 级挑战少。五个改进：

1. **分级挑战** — P0 阻断 / P1 改进 / P2 备注，只有 P0 触发重整合
2. **决策锚定** — 挑战标准锚定到具体决策问题
3. **数据说话** — P0 必须引用 Layer 2 结构化数据作反证
4. **对标校准** — few-shot 示例区分好/差挑战
5. **能力验证** — 元能力层补齐工具后，Critic 用工具重新验证质疑点

---

## 二、新增常量

在 `_run_critic_challenge()` 函数之前定义：

```python
CRITIC_FEW_SHOT = """
## 挑战质量对标（严格学习这个标准）

❌ 差的 P0（实际应为 P2，没有反证数据）:
"歌尔的产能数据可能不够准确，建议进一步核实。"
→ 无具体反证数据，只是泛泛质疑。降为 P2。

✅ 好的 P0（有反证数据，直接影响决策）:
{
  "issue": "报告结论'歌尔产能不足以独家供货（500万台/年）'可能已过时",
  "evidence": "Layer 2 数据: Goertek Weifang 二期 2025Q3 投产（source: 歌尔2025半年报, confidence: high），实际产能可能已达 800万台/年",
  "fix_required": "用最新产能数据重新评估独家供货可行性"
}
→ 为什么是 P0：产能数据错误会推翻"需要双供应商"的结论，直接影响选型决策。

❌ 差的 P0（不影响决策方向，应降为 P1）:
"BOM 成本估算中，OLED 面板价格引用的是 Q1 数据，Q2 可能有 5% 波动。"
→ 5% 波动不改变 OLED vs Micro LED 的成本对比方向。降为 P1。

✅ 好的 P1（有依据，标记即可）:
{
  "issue": "声学方案对比缺少风噪实测数据，当前结论基于厂商标称值",
  "evidence": "Layer 2 中所有扬声器参数的 confidence 均为 medium（厂商标称）"
}

✅ P2 示例:
{
  "issue": "如能补充 Cardo Packtalk 的拆机 BOM 数据，成本对比会更有说服力"
}
"""
```

---

## 三、重写 `_run_critic_challenge()` 函数

找到现有的 `_run_critic_challenge()` 函数，**整体替换**为以下版本。保留函数签名（Part 3 已添加 structured_data 参数）：

```python
def _run_critic_challenge(report: str, goal: str, agent_outputs: dict,
                          structured_data: str = "",
                          progress_callback=None) -> str:
    """Layer 5: Critic 五维挑战

    改进:
    1. 分级: P0（阻断）/ P1（改进）/ P2（备注）
    2. 决策锚定: 挑战标准锚定到具体决策
    3. 数据说话: P0 必须引用 Layer 2 数据
    4. 对标校准: few-shot 示例
    5. 能力验证: 元能力层集成
    """
    if len(report) < 500:
        print("  [Critic] 报告太短，跳过")
        return report

    print("  [L5] 开始 Critic 挑战...")

    # === 构建 prompt ===

    # 决策锚定
    decision_anchor = (
        f"\n## 决策锚定\n"
        f"这份报告要支撑的核心决策是：{goal[:300]}\n\n"
        f"P0 判定标准：报告中的某个错误会导致这个决策做错 → P0。\n"
        f"某个估算偏差 10% 以内但不改变结论方向 → P1。\n"
        f"'有了更好但没有也行' → P2。\n"
        f"严格按此标准分级。P0 应该很少（0-2 个才正常）。\n"
    )

    # Layer 2 数据引用
    data_section = ""
    if structured_data:
        data_section = (
            f"\n## 原始结构化数据（用于交叉验证和引用）\n"
            f"以下是 Layer 2 提炼的结构化数据点，每个字段附有 source 和 confidence。\n"
            f"P0 挑战必须引用这些数据中的具体数据点作为反证。\n"
            f"找不到具体反证 → 该挑战最多 P1。\n\n"
            f"{structured_data[:4000]}\n"
        )

    # 能力缺口标记指引（元能力层集成）
    capability_instruction = ""
    try:
        from scripts.meta_capability import CAPABILITY_GAP_INSTRUCTION
        capability_instruction = CAPABILITY_GAP_INSTRUCTION
    except ImportError:
        pass

    critic_prompt = (
        f"你是独立审查员。你的职责不是打分，而是找出会导致决策失误的致命问题。\n\n"
        f"## 任务目标\n{goal}\n"
        f"{decision_anchor}\n"
        f"## 报告（{len(report)}字）\n{report[:8000]}\n"
        f"{data_section}\n"
        f"{CRITIC_FEW_SHOT}\n\n"
        f"## 挑战规则（强制）\n"
        f"1. 每个 P0 必须引用 Layer 2 数据中的具体数据点作为反证。\n"
        f"   格式: \"Layer 2 数据显示 [产品X] 的 [参数Y] 为 [值Z]"
        f"（source: [来源], confidence: [级别]），但报告结论为 [矛盾内容]。\"\n"
        f"2. 找不到具体反证数据点 → 最多 P1，不能是 P0。\n"
        f"3. \"建议进一步调研\"、\"建议加强分析\"等无反证表述 → P2 或不输出。\n"
        f"4. P0 超过 2 个时，重新检查是否真的每个都会导致决策做错。\n\n"
        f"{capability_instruction}\n\n"
        f"## 输出格式（严格 JSON）\n"
        f'{{\n'
        f'  "p0_blocking": [\n'
        f'    {{"issue": "结论与数据矛盾的具体描述",\n'
        f'     "evidence": "引用 Layer 2 具体数据点",\n'
        f'     "fix_required": "需要修正什么"}}\n'
        f'  ],\n'
        f'  "p1_improvement": [\n'
        f'    {{"issue": "可改进但不影响结论", "evidence": "数据来源"}}\n'
        f'  ],\n'
        f'  "p2_note": [\n'
        f'    {{"issue": "建议未来补充的方向"}}\n'
        f'  ],\n'
        f'  "overall": "PASS 或 NEEDS_FIX"\n'
        f'}}\n\n'
        f"判定: p0_blocking 非空 → NEEDS_FIX，否则 → PASS。\n"
        f"只输出 JSON。"
    )

    critic_result = _call_model(
        _get_model_for_task("critic_challenge"), critic_prompt,
        "你是独立审查员。只输出 JSON。", "critic_review"
    )

    if not critic_result.get("success"):
        print(f"  [Critic] 调用失败: {critic_result.get('error', '')[:100]}")
        return report

    # === 解析分级结果 ===
    try:
        resp = critic_result["response"].strip()
        resp = re.sub(r'^```json\s*', '', resp)
        resp = re.sub(r'\s*```$', '', resp)
        critic_data = json.loads(resp)

        p0_list = critic_data.get("p0_blocking", [])
        p1_list = critic_data.get("p1_improvement", [])
        p2_list = critic_data.get("p2_note", [])

        print(f"  [Critic] P0: {len(p0_list)}, P1: {len(p1_list)}, P2: {len(p2_list)}")

        needs_fix = len(p0_list) > 0

        if needs_fix:
            print(f"  [Critic] NEEDS_FIX: {len(p0_list)} 个 P0 挑战")
            if progress_callback:
                progress_callback(f"  Critic: {len(p0_list)} P0 challenges")
        else:
            print(f"  [Critic] PASS (P1: {len(p1_list)}, P2: {len(p2_list)})")

    except Exception as e:
        print(f"  [Critic] 解析失败: {e}")
        report += f"\n\n---\n## Critic Review\n{critic_result['response'][:1000]}"
        return report

    # === 元能力层: Critic 缺口扫描 ===
    try:
        from scripts.meta_capability import scan_capability_gaps, resolve_capability_gap
        critic_gaps = scan_capability_gaps(critic_result.get("response", ""))
        resolved_tools = []
        if critic_gaps:
            print(f"  [Meta-Critic] 发现 {len(critic_gaps)} 个验证能力缺口")
            for gap in critic_gaps[:2]:
                result = resolve_capability_gap(gap, gateway)
                if result.get("success"):
                    resolved_tools.append(result)

            # 补齐工具后重新验证 P0
            if resolved_tools and p0_list:
                tool_info = "\n".join([
                    f"[新增工具] {t['tool_name']}: {t['invoke']}"
                    for t in resolved_tools
                ])
                reverify_prompt = (
                    f"你之前提出了以下 P0 挑战但缺乏验证工具。\n"
                    f"现在系统已补齐以下工具:\n{tool_info}\n\n"
                    f"原始 P0 挑战:\n"
                    f"{json.dumps(p0_list, ensure_ascii=False, indent=2)}\n\n"
                    f"请用新工具重新验证每个 P0：\n"
                    f"- 确认 P0 成立 → 保留\n"
                    f"- 发现 P0 不成立 → 降级为 P1 或 P2\n"
                    f"- 发现新问题 → 补充\n\n"
                    f"输出更新后的 p0_blocking JSON 数组。只输出 JSON。"
                )
                reverify = _call_model(
                    _get_model_for_task("critic_challenge"),
                    reverify_prompt, "重新验证 P0 挑战。只输出 JSON。",
                    "critic_reverify"
                )
                if reverify.get("success"):
                    try:
                        r = reverify["response"].strip()
                        r = re.sub(r'^```json\s*', '', r)
                        r = re.sub(r'\s*```$', '', r)
                        updated_p0 = json.loads(r)
                        if isinstance(updated_p0, list):
                            print(f"  [Meta-Critic] P0 重验证: {len(p0_list)} → {len(updated_p0)}")
                            p0_list = updated_p0
                            needs_fix = len(p0_list) > 0
                    except:
                        pass
    except ImportError:
        pass  # 元能力层未安装，跳过

    # === P0 挑战回应循环（仅 P0 触发）===
    if needs_fix and p0_list:
        challenge_responses = []

        for i, p0 in enumerate(p0_list[:3]):
            challenge_text = (
                f"P0 挑战: {p0.get('issue', '')}\n"
                f"反证: {p0.get('evidence', '')}\n"
                f"要求修正: {p0.get('fix_required', '')}"
            )

            # 判断是否需要额外搜索
            needs_search = any(kw in challenge_text for kw in
                             ["数据", "证据", "来源", "补充", "最新", "更新"])
            extra_data = ""
            if needs_search:
                kw_result = _call_model("gemini_2_5_flash",
                    f"从以下挑战中提取 1-2 个搜索关键词:\n{challenge_text}\n只输出关键词，空格分隔",
                    task_type="query_generation")
                if kw_result.get("success"):
                    extra_query = kw_result["response"].strip()
                    if extra_query:
                        search_result = registry.call("tavily_search", extra_query)
                        if search_result.get("success") and len(search_result.get("data", "")) > 100:
                            extra_data = f"\n\n## 补充搜索结果\n{search_result['data'][:2000]}"

            # 让主角色回应
            primary_role = list(agent_outputs.keys())[0] if agent_outputs else "CTO"
            response_model = _get_model_for_role(primary_role)
            response_result = _call_model(response_model,
                f"Critic 对你的分析提出了 P0 级挑战（会导致决策失误的问题）:\n\n"
                f"{challenge_text}\n{extra_data}\n\n"
                f"请直接回应。如果 Critic 说得对，承认并给出修正后的结论。"
                f"如果不对，用数据反驳。",
                task_type=f"challenge_response_{i}")

            if response_result.get("success"):
                challenge_responses.append({
                    "p0": p0,
                    "response": response_result["response"],
                    "extra_search": bool(extra_data)
                })
                print(f"  [P0 Challenge {i+1}] responded")

        # 最终重整合
        if challenge_responses:
            dialogue = ""
            for r in challenge_responses:
                dialogue += (
                    f"\n[P0 挑战] {r['p0'].get('issue', '')}\n"
                    f"[反证] {r['p0'].get('evidence', '')}\n"
                    f"[回应] {r['response']}\n"
                )

            final_result = _call_model(
                _get_model_for_task("final_synthesis"),
                f"以下是研究报告经过 Critic P0 挑战后的完整对话:\n\n"
                f"## 初始报告\n{report[:6000]}\n\n"
                f"## P0 挑战与回应\n{dialogue}\n\n"
                f"请输出最终版报告:\n"
                f"1. P0 挑战中被证实的问题必须修正\n"
                f"2. 补充的新数据必须整合\n"
                f"3. 保持决策支撑格式\n"
                f"4. 末尾添加 'Critic 挑战记录' 小节\n\n"
                f"任务目标: {goal}",
                task_type="final_synthesis"
            )
            if final_result.get("success"):
                report = final_result["response"]
                print(f"  [Final Synthesis] {len(report)} chars")

    # === 附加 Critic 审查结果到报告末尾 ===
    critic_appendix = "\n\n---\n## Critic Review\n\n"

    if p0_list:
        critic_appendix += "### P0 阻断级\n"
        for p0 in p0_list:
            critic_appendix += (
                f"- **{p0.get('issue', '')}**\n"
                f"  反证: {p0.get('evidence', '')}\n"
                f"  处理: {'已修正' if needs_fix else '待修正'}\n\n"
            )

    if p1_list:
        critic_appendix += "### P1 改进级\n"
        for p1 in p1_list:
            critic_appendix += f"- {p1.get('issue', '')} ({p1.get('evidence', '')})\n"

    if p2_list:
        critic_appendix += "\n### P2 备注\n"
        for p2 in p2_list:
            critic_appendix += f"- {p2.get('issue', '')}\n"

    report += critic_appendix

    return report
```

---

## 四、验证

改完后在飞书触发一次深度研究，观察日志:

```
[L5] 开始 Critic 挑战...
[Critic] P0: 0, P1: 2, P2: 1        ← 正常: P0 少
[Critic] PASS (P1: 2, P2: 1)         ← 只有 P1/P2，不触发重整合
```

或:

```
[Critic] P0: 1, P1: 1, P2: 2
[Critic] NEEDS_FIX: 1 个 P0 挑战
[P0 Challenge 1] responded
[Final Synthesis] 3500 chars           ← P0 触发了重整合
```

关键检查:
- P0 挑战是否附带了具体的 Layer 2 数据引用（不是泛泛质疑）
- P1/P2 是否直接附在报告末尾（不触发重整合循环）
- 报告末尾的 Critic Review 是否按 P0/P1/P2 分级展示
