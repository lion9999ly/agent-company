"""
@description: 知识自完整性检测 - 自动发现和填补知识家族缺口
@dependencies: src.utils.model_gateway, src.tools.knowledge_base
@last_modified: 2026-03-25
"""
import json
import re
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.model_gateway import get_model_gateway
from src.tools.knowledge_base import search_knowledge, get_knowledge_stats, KB_ROOT


def detect_gaps() -> list:
    """扫描知识库，检测家族性缺口"""
    gateway = get_model_gateway()

    # 收集知识库中提到的所有"系列型号"模式
    all_titles = []
    all_content_snippets = []

    for f in KB_ROOT.rglob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            title = data.get("title", "")
            content = data.get("content", "")[:300]
            all_titles.append(title)
            all_content_snippets.append(f"{title}: {content[:200]}")
        except:
            continue

    # 让 LLM 分析知识库中的"家族缺口"
    sample = "\n".join(all_content_snippets[:100])  # 采样前 100 条

    gap_prompt = (
        f"你是智能摩托车全盔项目的知识管理专家。\n\n"
        f"以下是我们知识库中 {len(all_titles)} 条知识的采样（前 100 条标题和摘要）。\n\n"
        f"请分析知识库中的'家族性缺口'——即我们知道某个产品/技术的一个型号，但不知道同系列的其他型号。\n\n"
        f"例如：\n"
        f"- 我们知道 AR1 Gen1 但不知道 AR1+、AR2（高通 AR 芯片家族缺口）\n"
        f"- 我们知道 BES2800 但不知道 BES2700/2600/2900（恒玄芯片家族缺口）\n"
        f"- 我们知道 Sena Packtalk 但不知道 Sena 50S/50R/Spider（Sena 产品线缺口）\n"
        f"- 我们知道 ECE 22.06 但不知道它和 ECE 22.05 的具体差异（标准版本缺口）\n\n"
        f"请找出 5-8 个最重要的家族缺口。\n\n"
        f"输出 JSON 数组：\n"
        f'[{{"known": "我们已知的型号/产品", "missing": ["缺失的型号1", "缺失的型号2"], '
        f'"domain": "components/competitors/standards", '
        f'"priority": "high/medium", '
        f'"reason": "为什么这个缺口重要"}}]\n\n'
        f"知识库采样：\n{sample}"
    )

    result = gateway.call_azure_openai("cpo", gap_prompt, "只输出 JSON 数组。", "completeness_check")

    if not result.get("success"):
        return []

    try:
        resp = result["response"].strip()
        resp = re.sub(r'^```json\s*', '', resp)
        resp = re.sub(r'\s*```$', '', resp)
        gaps = json.loads(resp)
        if isinstance(gaps, list):
            print(f"[Completeness] 发现 {len(gaps)} 个家族缺口")
            for gap in gaps:
                print(f"  - 已知 {gap.get('known', '?')}, 缺失 {gap.get('missing', [])}")
            return gaps
    except:
        pass

    return []


def fill_gap(gap: dict, progress_callback=None) -> str:
    """填补一个家族缺口"""
    from src.tools.tool_registry import get_tool_registry
    from src.tools.knowledge_base import add_knowledge
    import time

    gateway = get_model_gateway()
    registry = get_tool_registry()

    known = gap.get("known", "")
    missing = gap.get("missing", [])
    domain = gap.get("domain", "components")

    filled = 0
    for item in missing:
        # 搜索
        queries = [
            f"{item} datasheet specifications features 2026",
            f"{item} 参数 规格 价格 对比 {known}",
        ]

        search_data = ""
        for q in queries:
            result = registry.call("deep_research", q)
            if result.get("success") and len(result.get("data", "")) > 200:
                search_data += f"\n{result['data'][:3000]}"

        if len(search_data) < 300:
            continue

        # 提炼
        refine_prompt = (
            f"请输出关于 {item} 的技术档案。\n"
            f"重点和已知的 {known} 做对比：哪些方面更好、哪些更差、适用场景有何不同。\n"
            f"必须包含具体参数、价格、已知客户。\n\n"
            f"搜索结果：\n{search_data[:6000]}"
        )

        refine_result = gateway.call_azure_openai("cpo", refine_prompt,
            "输出完整技术档案。", "gap_fill")

        if refine_result.get("success") and len(refine_result["response"]) > 200:
            add_knowledge(
                title=f"[技术档案] {item}（对比 {known}）",
                domain=domain,
                content=refine_result["response"][:1200],
                tags=["knowledge_graph", "gap_fill", "auto_completeness"],
                source="completeness_check",
                confidence="high"
            )
            filled += 1
            print(f"  [OK] 填补: {item}")

        time.sleep(2)

    return f"已知 {known} -> 填补 {filled}/{len(missing)} 个缺失"


def run_completeness_check(progress_callback=None) -> str:
    """完整性检测 + 自动填补"""
    print("\n[Completeness] 开始知识自完整性检测...")

    gaps = detect_gaps()
    if not gaps:
        return "[Completeness] 未发现明显家族缺口"

    # 按优先级排序
    gaps.sort(key=lambda x: 0 if x.get("priority") == "high" else 1)

    report_lines = [f"[Completeness] 发现 {len(gaps)} 个缺口，开始填补"]

    for i, gap in enumerate(gaps[:5], 1):  # 每次最多填 5 个
        if progress_callback:
            progress_callback(f"[Completeness] 填补缺口 [{i}/{min(len(gaps), 5)}]: {gap.get('known', '?')}")

        result = fill_gap(gap, progress_callback)
        report_lines.append(f"  {result}")

    report = "\n".join(report_lines)
    print(report)
    return report


if __name__ == "__main__":
    run_completeness_check()