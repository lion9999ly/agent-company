"""
深度研究 — Critic 审查层 (Layer 5)
职责: 分级挑战(P0/P1/P2)、双Critic交叉、元能力验证、P0回应循环、校准采样
被调用方: pipeline.py
依赖: models.py, learning.py
"""
import json
import re
import time

from src.tools.tool_registry import ToolRegistry
from src.utils.model_gateway import get_model_gateway
from scripts.deep_research.models import (
    call_model, get_model_for_task, get_model_for_role
)

registry = ToolRegistry()
gateway = get_model_gateway()


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


def run_critic_challenge(report: str, goal: str, agent_outputs: dict,
                         structured_data: str = "",
                         progress_callback=None,
                         task_title: str = "") -> str:
    """Layer 5: Critic 五维挑战"""

    if len(report) < 500:
        print("  [Critic] 报告太短，跳过")
        return report

    print("  [L5] 开始 Critic 挑战...")

    # 决策锚定
    decision_anchor = (
        f"\n## 决策锚定\n"
        f"这份报告要支撑的核心决策是：{goal[:300]}\n\n"
        f"P0 判定标准：报告中的某个错误会导致这个决策做错 → P0。\n"
        f"某个估算偏差 10% 以内但不改变结论方向 → P1。\n"
        f"'有了更好但没有也行' → P2。\n"
        f"严格按此标准分级。P0 应该很少（0-2 个才正常）。\n"
    )

    data_section = ""
    if structured_data:
        data_section = (
            f"\n## 原始结构化数据（用于交叉验证和引用）\n"
            f"P0 挑战必须引用这些数据中的具体数据点作为反证。\n"
            f"找不到具体反证 → 该挑战最多 P1。\n\n"
            f"{structured_data[:4000]}\n"
        )

    capability_instruction = ""
    try:
        from scripts.meta_capability import CAPABILITY_GAP_INSTRUCTION
        capability_instruction = CAPABILITY_GAP_INSTRUCTION
    except ImportError:
        pass

    # 尝试进化版 few-shot
    few_shot_to_use = CRITIC_FEW_SHOT
    try:
        from scripts.critic_calibration import get_evolved_few_shot, get_evolved_rules
        evolved_few_shot = get_evolved_few_shot()
        if evolved_few_shot:
            few_shot_to_use = evolved_few_shot
            print("  [Critic] 使用进化版 few-shot 示例")
        evolved_rules = get_evolved_rules()
        if evolved_rules:
            print(f"  [Critic] 加载 {len(evolved_rules.get('p0_triggers', []))} 条进化规则")
    except ImportError:
        pass

    critic_prompt = (
        f"你是独立审查员。你的职责不是打分，而是找出会导致决策失误的致命问题。\n\n"
        f"## 任务目标\n{goal}\n"
        f"{decision_anchor}\n"
        f"## 报告（{len(report)}字）\n{report[:8000]}\n"
        f"{data_section}\n"
        f"{few_shot_to_use}\n\n"
        f"## 挑战规则（强制）\n"
        f"1. 每个 P0 必须引用 Layer 2 数据中的具体数据点作为反证。\n"
        f"2. 找不到具体反证 → 最多 P1。\n"
        f"3. 无反证表述 → P2 或不输出。\n"
        f"4. P0 超过 2 个时，重新检查。\n\n"
        f"{capability_instruction}\n\n"
        f"## 输出格式（严格 JSON）\n"
        f'{{\n'
        f'  "p0_blocking": [{{"issue": "...", "evidence": "...", "fix_required": "..."}}],\n'
        f'  "p1_improvement": [{{"issue": "...", "evidence": "..."}}],\n'
        f'  "p2_note": [{{"issue": "..."}}],\n'
        f'  "overall": "PASS 或 NEEDS_FIX"\n'
        f'}}\n'
        f"只输出 JSON。"
    )

    critic_result = call_model(
        get_model_for_task("critic_challenge"), critic_prompt,
        "你是独立审查员。只输出 JSON。", "critic_review"
    )

    if not critic_result.get("success"):
        print(f"  [Critic] 调用失败: {critic_result.get('error', '')[:100]}")
        return report

    # 解析分级结果
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

    except Exception as e:
        print(f"  [Critic] 解析失败: {e}")
        report += f"\n\n---\n## Critic Review\n{critic_result['response'][:1000]}"
        return report

    # Dual Critic: o3 交叉审查
    print("  [Critic Cross] o3 开始交叉审查...")
    cross_critic_prompt = (
        f"你是第二独立审查员。\n\n"
        f"## 主审查员结论\nP0: {len(p0_list)}, P1: {len(p1_list)}\n\n"
        f"## 报告目标\n{goal[:300]}\n\n"
        f"## 报告内容\n{report[:6000]}\n\n"
        f"## 你的任务\n1. 主审查员是否漏掉逻辑漏洞\n2. 数值推算是否合理\n"
        f"3. 结论与数据逻辑链是否完整\n\n"
        f"输出 JSON:\n{{\n"
        f'  "additional_p0": [{{"issue": "...", "reason": "..."}}],\n'
        f'  "logic_gaps": ["..."],\n'
        f'  "calculation_concerns": ["..."],\n'
        f'  "agreement": "agree/partially_agree/disagree"\n}}\n'
        f"只输出 JSON。"
    )
    cross_result = call_model("o3", cross_critic_prompt, "你是逻辑审查员。只输出 JSON。", "critic_cross")
    if cross_result.get("success"):
        try:
            cross_resp = cross_result["response"].strip()
            cross_resp = re.sub(r'^```json\s*', '', cross_resp)
            cross_resp = re.sub(r'\s*```$', '', cross_resp)
            cross_data = json.loads(cross_resp)

            additional_p0 = cross_data.get("additional_p0", [])
            if additional_p0:
                print(f"  [Critic Cross] o3 发现 {len(additional_p0)} 个额外 P0")
                for ap0 in additional_p0:
                    p0_list.append({
                        "issue": ap0.get("issue", ""),
                        "evidence": f"[o3 交叉审查] {ap0.get('reason', '')}",
                        "fix_required": "需要验证"
                    })
                needs_fix = True

            logic_gaps = cross_data.get("logic_gaps", [])
            if logic_gaps:
                p2_list.extend([{"issue": f"[逻辑检查] {g}"} for g in logic_gaps])

            report += f"\n\n<!-- Dual Critic: o3 {cross_data.get('agreement', 'unknown')} -->"
        except Exception as e:
            print(f"  [Critic Cross] 解析失败: {e}")

    # 元能力层: Critic 缺口扫描
    try:
        from scripts.meta_capability import scan_capability_gaps, resolve_capability_gap
        resolve_capability_gap._feishu_callback = progress_callback
        critic_gaps = scan_capability_gaps(critic_result.get("response", ""))
        resolved_tools = []
        if critic_gaps:
            print(f"  [Meta-Critic] 发现 {len(critic_gaps)} 个验证能力缺口")
            for gap in critic_gaps[:2]:
                result = resolve_capability_gap(gap, gateway)
                if result.get("success"):
                    resolved_tools.append(result)

            if resolved_tools and p0_list:
                tool_info = "\n".join([
                    f"[新增工具] {t['tool_name']}: {t['invoke']}"
                    for t in resolved_tools
                ])
                reverify_prompt = (
                    f"系统已补齐以下工具:\n{tool_info}\n\n"
                    f"原始 P0 挑战:\n{json.dumps(p0_list, ensure_ascii=False, indent=2)}\n\n"
                    f"请用新工具重新验证每个 P0。\n输出更新后的 p0_blocking JSON 数组。"
                )
                reverify = call_model(get_model_for_task("critic_challenge"),
                    reverify_prompt, "重新验证 P0 挑战。只输出 JSON。", "critic_reverify")
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
        pass

    # P0 挑战回应循环
    if needs_fix and p0_list:
        challenge_responses = []
        for i, p0 in enumerate(p0_list[:3]):
            challenge_text = (
                f"P0 挑战: {p0.get('issue', '')}\n"
                f"反证: {p0.get('evidence', '')}\n"
                f"要求修正: {p0.get('fix_required', '')}"
            )

            needs_search = any(kw in challenge_text for kw in
                               ["数据", "证据", "来源", "补充", "最新", "更新"])
            extra_data = ""
            if needs_search:
                kw_result = call_model("gemini_2_5_flash",
                    f"从以下挑战中提取 1-2 个搜索关键词:\n{challenge_text}\n只输出关键词",
                    task_type="query_generation")
                if kw_result.get("success"):
                    extra_query = kw_result["response"].strip()
                    if extra_query:
                        search_result = registry.call("tavily_search", extra_query)
                        if search_result.get("success") and len(search_result.get("data", "")) > 100:
                            extra_data = f"\n\n## 补充搜索结果\n{search_result['data'][:2000]}"

            primary_role = list(agent_outputs.keys())[0] if agent_outputs else "CTO"
            response_model = get_model_for_role(primary_role)
            response_result = call_model(response_model,
                f"Critic 对你的分析提出了 P0 级挑战:\n\n{challenge_text}\n{extra_data}\n\n"
                f"请直接回应。如果 Critic 说得对，承认并修正。如果不对，用数据反驳。",
                task_type=f"challenge_response_{i}")
            if response_result.get("success"):
                challenge_responses.append({
                    "p0": p0, "response": response_result["response"],
                    "extra_search": bool(extra_data)
                })
                print(f"  [P0 Challenge {i + 1}] responded")

        # 最终重整合
        if challenge_responses:
            dialogue = ""
            for r in challenge_responses:
                dialogue += (
                    f"\n[P0 挑战] {r['p0'].get('issue', '')}\n"
                    f"[反证] {r['p0'].get('evidence', '')}\n"
                    f"[回应] {r['response']}\n"
                )
            final_result = call_model(
                get_model_for_task("final_synthesis"),
                f"以下是研究报告经过 Critic P0 挑战后的完整对话:\n\n"
                f"## 初始报告\n{report[:6000]}\n\n"
                f"## P0 挑战与回应\n{dialogue}\n\n"
                f"请输出最终版报告:\n1. P0 被证实的问题必须修正\n"
                f"2. 新数据必须整合\n3. 末尾添加 'Critic 挑战记录' 小节\n\n"
                f"任务目标: {goal}",
                task_type="final_synthesis"
            )
            if final_result.get("success"):
                report = final_result["response"]
                print(f"  [Final Synthesis] {len(report)} chars")

    # 附加 Critic 审查结果
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

    # 校准采样 + 漂移检测
    try:
        from scripts.critic_calibration import (
            sample_for_calibration, save_pending_samples,
            push_calibration_to_feishu, check_drift
        )
        report_excerpt = report[:500]
        samples = sample_for_calibration(
            {"p0_blocking": p0_list, "p1_improvement": p1_list, "p2_note": p2_list},
            report_excerpt, goal, task_title
        )
        if samples:
            save_pending_samples(samples)
            push_calibration_to_feishu(samples, progress_callback)
        check_drift(
            {"p0_blocking": p0_list, "p1_improvement": p1_list, "p2_note": p2_list},
            progress_callback
        )
    except ImportError:
        pass
    except Exception as e:
        print(f"  [Calibration] 采样/漂移检测异常: {e}")

    return report
