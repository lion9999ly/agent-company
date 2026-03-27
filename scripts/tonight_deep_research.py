"""
@description: JDM供应商选型深度研究 - 完整研究报告生成
@dependencies: src.utils.model_gateway, src.tools.knowledge_base, src.tools.tool_registry
@last_modified: 2026-03-22
"""
import json
import time
import re
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.model_gateway import get_model_gateway
from src.tools.knowledge_base import add_knowledge, get_knowledge_stats, KB_ROOT
from src.tools.tool_registry import ToolRegistry

registry = ToolRegistry()
gateway = get_model_gateway()

REPORT_DIR = Path(__file__).parent.parent / ".ai-state" / "reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

# 5 个深度研究任务
RESEARCH_TASKS = [
    {
        "id": "goertek_profile",
        "title": "歌尔股份完整画像",
        "goal": "回答：歌尔做智能头盔JDM的核心能力、已有客户案例、产能规模、大致报价水平、优势和风险",
        "searches": [
            "Goertek smart wearable ODM JDM capability 2025 2026 annual report",
            "歌尔股份 2025年报 智能穿戴 营收 客户",
            "Goertek Meta Ray-Ban smart glasses ODM manufacturing details",
            "歌尔 Alpha Labs 智能眼镜 研发能力 团队规模",
            "Goertek XR headset production capacity Weifang factory",
            "歌尔 智能穿戴 代工报价 NRE 模具费 单价",
            "Goertek smart glasses helmet acoustic optical module capability",
            "歌尔股份 竞争优势 劣势 风险 分析师报告 2025",
        ]
    },
    {
        "id": "alternative_jdm",
        "title": "替代JDM供应商对比",
        "goal": "回答：除歌尔外还有哪些供应商能做智能头盔JDM？各自的能力、客户、规模、报价水平如何？",
        "searches": [
            "Luxshare Precision smart wearable ODM capability customer list 2026",
            "立讯精密 智能穿戴 代工 客户 苹果 Meta 产能",
            "BYD Electronics smart device ODM wearable 2026 capability",
            "比亚迪电子 智能穿戴 代工 能力 报价",
            "Flex Jabil wearable device contract manufacturing 2026",
            "Pegatron Compal Inventec smart wearable ODM comparison",
            "深圳 东莞 智能头盔 小型方案商 ODM 代工 案例",
            "智能骑行头盔 JDM 供应商 选型 对比 报告 2026",
        ]
    },
    {
        "id": "optical_suppliers",
        "title": "光学方案商深度对比",
        "goal": "回答：HUD/AR显示用什么光学方案？每种方案的供应商、参数、成本、成熟度如何？推荐哪个？",
        "searches": [
            "AR HUD optical engine comparison waveguide birdbath freeform prism 2026",
            "Lumus waveguide supplier pricing motorcycle helmet HUD",
            "DigiLens waveguide smart glasses cost volume production 2026",
            "珑璟光电 灵犀微光 谷东科技 光波导 参数 价格 对比",
            "Micro OLED display Sony JBD BOE Kopin comparison specs price 2026",
            "BirdBath optical solution smart helmet HUD cost weight analysis",
            "motorcycle helmet HUD optical module supplier BOM cost breakdown",
            "光学模组 良率 交期 最小起订量 MOQ 供应商 2026",
        ]
    },
    {
        "id": "audio_camera_suppliers",
        "title": "声学与摄像头方案商对比",
        "goal": "回答：头盔用什么扬声器/麦克风/摄像头？每种方案的供应商、参数、成本对比？",
        "searches": [
            "骨传导扬声器 供应商 韶音 歌尔 瑞声 参数 价格 对比 2026",
            "MEMS microphone Knowles InvenSense Goertek specs price comparison",
            "ANC active noise cancellation chipset BES2700 QCC5181 comparison wearable",
            "微型摄像头 模组 OmniVision Sony IMX 舜宇 丘钛 specs comparison",
            "smart helmet speaker driver waterproof IP67 supplier",
            "helmet intercom microphone wind noise cancellation solution 2026",
        ]
    },
    {
        "id": "why_goertek",
        "title": "综合对比：为什么选歌尔（或为什么不选）",
        "goal": "基于前4份研究，给出歌尔 vs 替代方案的综合评估。明确回答：选歌尔的理由、风险、备选方案",
        "searches": [
            "Goertek vs Luxshare smart wearable ODM comparison advantage disadvantage",
            "歌尔 vs 立讯 vs 比亚迪电子 智能穿戴 综合对比 选型建议",
            "smart helmet ODM supplier selection criteria evaluation framework",
            "智能穿戴 JDM 供应商 选型 决策矩阵 权重",
        ]
    }
]


def deep_research_one(task: dict) -> str:
    """对一个任务做深度研究，返回完整报告"""
    task_id = task["id"]
    title = task["title"]
    goal = task["goal"]
    searches = task["searches"]

    print(f"\n{'='*60}")
    print(f"[Deep Research] {title}")
    print(f"[Goal] {goal}")
    print(f"[Sources] {len(searches)} 个搜索")
    print(f"{'='*60}")

    # Step 1: 多源搜索，收集原始材料
    all_sources = []
    for i, query in enumerate(searches, 1):
        print(f"  [{i}/{len(searches)}] 搜索: {query[:50]}...")

        # 先用 deep_research（Gemini），再用 tavily 补充
        source_text = ""

        result = registry.call("deep_research", query)
        if result.get("success") and len(result.get("data", "")) > 200:
            source_text += result["data"][:3000]
            print(f"    deep_research: {len(result['data'])} 字")

        result2 = registry.call("tavily_search", query)
        if result2.get("success") and len(result2.get("data", "")) > 200:
            source_text += "\n---\n" + result2["data"][:2000]
            print(f"    tavily: {len(result2['data'])} 字")

        if source_text:
            all_sources.append({"query": query, "content": source_text[:4000]})
        else:
            print(f"    ❌ 无有效结果")

        time.sleep(2)  # 避免限流

    if not all_sources:
        return f"# {title}\n\n调研失败：所有搜索均无结果"

    # Step 2: 读取知识库中已有的相关知识
    kb_context = ""
    keywords = title.split() + goal.split()[:5]
    for f in KB_ROOT.rglob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            content = data.get("content", "")
            t = data.get("title", "")
            # 简单关键词匹配
            if any(kw in t or kw in content[:200] for kw in ["歌尔", "Goertek", "立讯", "Luxshare", "JDM", "ODM",
                "光波导", "waveguide", "MEMS", "骨传导", "BOM", "供应商", "代工",
                "光学", "声学", "摄像头", "模组"]):
                kb_context += f"\n[KB] {t}: {content[:200]}"
        except:
            continue
    kb_context = kb_context[:3000]

    # Step 3: 合并所有材料，让强模型写完整报告
    source_dump = ""
    for s in all_sources:
        source_dump += f"\n\n### 搜索: {s['query']}\n{s['content']}"

    synthesis_prompt = (
        f"你是智能骑行头盔项目的高级研发顾问。\n\n"
        f"## 研究任务\n{title}\n\n"
        f"## 研究目标\n{goal}\n\n"
        f"## 已有知识库\n{kb_context[:2000]}\n\n"
        f"## 本次调研原始材料（{len(all_sources)} 个来源）\n{source_dump[:15000]}\n\n"
        f"## 输出要求\n"
        f"1. 写一份 2000-3000 字的完整研究报告\n"
        f"2. 必须包含：具体公司名、具体产品型号、具体参数数字、具体价格范围\n"
        f"3. 信息来源不一致时要标注，不要编造\n"
        f"4. 最后给出明确的结论和建议（不要模棱两可）\n"
        f"5. 用中文撰写\n"
    )

    result = gateway.call_azure_openai(
        "cpo", synthesis_prompt,
        "你是资深研发顾问，输出完整的研究报告。",
        "deep_research_synthesis"
    )

    if not result.get("success"):
        return f"# {title}\n\n综合报告生成失败"

    report = result["response"]

    # Step 4: 保存报告到文件
    report_path = REPORT_DIR / f"{task_id}_{time.strftime('%Y%m%d_%H%M')}.md"
    report_path.write_text(f"# {title}\n\n> 目标: {goal}\n> 生成时间: {time.strftime('%Y-%m-%d %H:%M')}\n> 来源数: {len(all_sources)}\n\n{report}", encoding="utf-8")
    print(f"\n[Saved] {report_path}")

    # Step 5: 从报告中提取关键知识条目存入知识库
    extract_prompt = (
        f"从以下研究报告中提取 3-5 条最有价值的知识条目。\n"
        f"每条应该是一个可以直接用于决策的具体事实或数据点。\n"
        f"输出 JSON 数组：[{{\"title\": \"标题(含公司名/型号)\", \"domain\": \"components\", "
        f"\"summary\": \"200字摘要，保留所有数字\", \"tags\": [\"标签\"]}}]\n\n"
        f"报告：\n{report[:6000]}"
    )

    extract_result = gateway.call_azure_openai(
        "cpo", extract_prompt,
        "只输出 JSON 数组。",
        "deep_research_extract"
    )

    if extract_result.get("success"):
        resp = extract_result["response"].strip()
        resp = re.sub(r'^```json\s*', '', resp)
        resp = re.sub(r'\s*```$', '', resp)
        try:
            items = json.loads(resp)
            for item in items:
                domain = item.get("domain", "components")
                if domain not in ("competitors", "components", "standards", "lessons"):
                    domain = "components"
                add_knowledge(
                    title=item.get("title", "")[:80],
                    domain=domain,
                    content=item.get("summary", "")[:800],
                    tags=item.get("tags", []) + ["deep_research", task_id],
                    source=f"deep_research:{task_id}",
                    confidence="high"
                )
            print(f"[KB] 提取 {len(items)} 条知识")
        except:
            print("[KB] 提取失败")

    return report


def run_all():
    """运行所有深度研究任务"""
    print(f"\n{'#'*60}")
    print(f"# 智能骑行头盔 JDM 供应商选型 — 深度研究")
    print(f"# 共 {len(RESEARCH_TASKS)} 个任务")
    print(f"# 开始时间: {time.strftime('%Y-%m-%d %H:%M')}")
    print(f"{'#'*60}")

    reports = []
    for task in RESEARCH_TASKS:
        report = deep_research_one(task)
        reports.append({"title": task["title"], "report": report})
        print(f"\n✅ {task['title']} 完成 ({len(report)} 字)")
        time.sleep(5)

    # 汇总保存
    summary_path = REPORT_DIR / f"jdm_summary_{time.strftime('%Y%m%d_%H%M')}.md"
    summary = "# JDM 供应商选型 — 深度研究汇总\n\n"
    summary += f"> 生成时间: {time.strftime('%Y-%m-%d %H:%M')}\n\n"
    for r in reports:
        summary += f"\n---\n\n# {r['title']}\n\n{r['report']}\n"
    summary_path.write_text(summary, encoding="utf-8")

    stats = get_knowledge_stats()
    total = sum(stats.values())

    print(f"\n{'#'*60}")
    print(f"# 全部完成！")
    print(f"# 报告: {summary_path}")
    print(f"# 知识库: {total} 条")
    print(f"# 完成时间: {time.strftime('%Y-%m-%d %H:%M')}")
    print(f"{'#'*60}")

    return str(summary_path)


if __name__ == "__main__":
    run_all()