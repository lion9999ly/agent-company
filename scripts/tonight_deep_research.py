"""
@description: JDM供应商选型深度研究 - 完整研究报告生成
@dependencies: src.utils.model_gateway, src.tools.knowledge_base, src.tools.tool_registry
@last_modified: 2026-03-26
"""
import json
import time
import re
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.model_gateway import get_model_gateway, call_for_search, call_for_refine
from src.tools.knowledge_base import add_knowledge, get_knowledge_stats, KB_ROOT
from src.tools.tool_registry import ToolRegistry
from src.utils.progress_heartbeat import ProgressHeartbeat

registry = ToolRegistry()
gateway = get_model_gateway()

# ==========================================
# 三原则：所有 Agent 必须遵循的思维准则
# ==========================================
THINKING_PRINCIPLES = """
## 思维准则（所有分析必须遵循）

1. **第一性原理**：拒绝经验主义和路径盲从。不要假设目标已清楚，若目标模糊，先停下来澄清。从原始需求和本质问题出发，若路径不是最优，直接建议更短、更低成本的办法。

2. **奥卡姆剃刀**：如无必要，勿增实体。暴力删除所有不影响核心交付的冗余。多余的功能、多余的步骤、多余的复杂度，都要砍。

3. **苏格拉底追问**：对每个方案进行连续追问——
   - 这个方案解决的是真正的问题，还是一个 XY 问题？
   - 当前选择的路径有什么弊端？
   - 有没有更优雅、成本更低的替代方案？
   - 如果这个方案失败，最可能的原因是什么？
"""

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
            # 发现层：先让搜索引擎告诉我们有哪些供应商
            "smart wearable device JDM ODM supplier list 2026 China",
            "智能穿戴 JDM ODM 供应商 完整名单 龙旗 瑞声 歌尔 立讯",
            # 已知大厂
            "Luxshare Precision smart wearable ODM capability customer 2026",
            "立讯精密 智能穿戴 代工 客户 苹果 Meta 产能 报价",
            "BYD Electronics smart device ODM wearable helmet 2026",
            "Longcheer 龙旗控股 智能穿戴 ODM JDM 能力 客户 2026",
            "AAC Technologies 瑞声科技 声学 光学 触觉 智能穿戴 2026",
            "Flex Jabil smart wearable contract manufacturing capability 2026",
            "Pegatron Compal Inventec smart wearable ODM 2026",
            "深圳 东莞 智能头盔 中小型方案商 ODM 案例 2026",
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
            "AAC Technologies acoustic module smart glasses helmet speaker microphone specs",
            "瑞声科技 声学模组 智能眼镜 骨传导 参数 价格 2026",
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
            "Goertek vs AAC Technologies vs Luxshare smart wearable comparison",
            "歌尔 vs 瑞声 vs 龙旗 vs 立讯 智能穿戴 ODM 综合对比",
        ]
    }
]


def deep_research_one(task: dict, progress_callback=None) -> str:
    """对一个任务做深度研究，返回完整报告"""
    task_id = task["id"]
    title = task["title"]
    goal = task["goal"]
    searches = task.get("searches", [])

    print(f"\n{'='*60}")
    print(f"[Deep Research] {title}")
    print(f"[Goal] {goal}")
    print(f"[Sources] {len(searches)} searches")
    print(f"{'='*60}")

    if progress_callback:
        progress_callback(f"Researching: {title[:20]}...")

    # 如果 searches 为空，自动生成搜索词
    if not searches:
        gen_prompt = (
            f"你是智能骑行头盔项目的研究规划师。\n"
            f"研究主题：{title}\n目标：{goal}\n\n"
            f"请生成 6-8 个搜索词用于调研这个主题。\n"
            f"要求：具体、含品牌名/公司名/型号、中英文混合。\n"
            f"只输出 JSON 数组。"
        )
        # === Phase 2.3: 搜索词生成用 Flash ===
        gen_result = call_for_search(gen_prompt, "只输出 JSON 数组。", "gen_searches")
        if gen_result.get("success"):
            try:
                resp = gen_result["response"].strip()
                resp = re.sub(r'^```json\s*', '', resp)
                resp = re.sub(r'\s*```$', '', resp)
                searches = json.loads(resp)
                if isinstance(searches, list):
                    task["searches"] = searches
                    print(f"  [Auto] Generated {len(searches)} search queries")
            except:
                pass
        if not searches:
            searches = [title + " 2026", title + " analysis report"]
            task["searches"] = searches
            print(f"  [Fallback] Using {len(searches)} default searches")

    # Step 0: 发现层——先搜一轮开放性问题，补充我们可能遗漏的供应商/方案
    discovery_query = f"{title} 2026 完整供应商名单 对比"
    print(f"  [Discovery] {discovery_query[:50]}...")
    disc_result = registry.call("deep_research", discovery_query)
    if disc_result.get("success") and len(disc_result.get("data", "")) > 200:
        # 让 LLM 从发现结果中提取我们可能遗漏的搜索词（限定骑行头盔领域）
        discover_prompt = (
            f"以下是关于「{title}」的搜索结果。\n"
            f"我们正在做智能骑行头盔（摩托车/自行车）项目的研究。\n\n"
            f"请从搜索结果中提取与以下领域直接相关的公司/品牌/产品/技术：\n"
            f"- 头盔制造商、头盔配件供应商\n"
            f"- 声学/光学/摄像头/通讯/电池/芯片方案商\n"
            f"- 智能穿戴ODM/JDM供应商\n"
            f"- 骑行装备品牌和竞品\n\n"
            f"严格排除与骑行头盔无关的公司（如Gartner、Netflix、Adobe、IBM、Salesforce等咨询/软件公司）。\n\n"
            f"只输出 JSON 数组，每个元素是一个搜索词：[\"公司A 产品 能力\", \"公司B 参数 对比\"]\n"
            f"最多 5 个。不要输出与骑行头盔无关的搜索词。\n\n"
            f"{disc_result['data'][:3000]}"
        )
        disc_llm = gateway.call_azure_openai("cpo", discover_prompt, "只输出 JSON 数组。", "discovery")
        if disc_llm.get("success"):
            resp = disc_llm["response"].strip()
            resp = re.sub(r'^```json\s*', '', resp)
            resp = re.sub(r'\s*```$', '', resp)
            try:
                extra_searches = json.loads(resp)
                if isinstance(extra_searches, list):
                    searches = searches + extra_searches[:5]
                    print(f"  [Discovery] 补充 {len(extra_searches[:5])} 个搜索词: {extra_searches[:3]}")
            except:
                pass

    # Step 1: 多源搜索，收集原始材料
    all_sources = []

    # === 心跳初始化 ===
    hb = ProgressHeartbeat(
        f"深度研究:{title[:20]}",
        total=len(searches),
        feishu_callback=progress_callback,
        log_interval=3,
        feishu_interval=5,
        feishu_time_interval=180
    )

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
            hb.tick(detail=query[:40], success=True)
        else:
            print(f"    ❌ 无有效结果")
            hb.tick(detail=f"失败: {query[:40]}", success=False)

        time.sleep(2)  # 避免限流

    hb.finish(f"搜索完成，{len(all_sources)}/{len(searches)} 有效")

    if not all_sources:
        return f"# {title}\n\n调研失败：所有搜索均无结果"

    # Step 2: 读取知识库中已有的相关知识（内部文档优先）
    kb_context = ""
    internal_context = ""
    keywords = title.split() + goal.split()[:5]

    # 先收集所有匹配条目
    kb_entries = []
    for f in KB_ROOT.rglob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            content = data.get("content", "")
            t = data.get("title", "")
            tags = data.get("tags", [])
            source = data.get("source", "")
            confidence = data.get("confidence", "")

            # 判断是否为内部文档
            is_internal = (
                "internal" in tags
                or "prd" in tags
                or "product_definition" in tags
                or "anchor" in tags
                or "user_upload" in source
                or confidence == "authoritative"
            )

            # 关键词匹配
            matched = any(kw in t or kw in content[:300] for kw in keywords)
            if not matched:
                # 也匹配常见领域关键词
                matched = any(kw in t or kw in content[:200] for kw in [
                    "歌尔", "Goertek", "立讯", "Luxshare", "JDM", "ODM",
                    "光波导", "waveguide", "MEMS", "骨传导", "BOM", "供应商", "代工",
                    "光学", "声学", "摄像头", "模组", "PRD", "产品定义", "规格", "参数"
                ])

            if matched:
                kb_entries.append({
                    "title": t,
                    "content": content,
                    "is_internal": is_internal
                })
        except:
            continue

    # 内部文档排在最前面
    kb_entries.sort(key=lambda x: -x["is_internal"])

    for entry in kb_entries[:10]:
        if entry["is_internal"]:
            internal_context += f"\n[内部产品定义] {entry['title']}:\n{entry['content'][:2000]}\n"
        else:
            kb_context += f"\n[KB] {entry['title']}: {entry['content'][:300]}"

    # 内部文档在最前面
    kb_context = internal_context + kb_context
    kb_context = kb_context[:5000]

    # 合并搜索材料
    source_dump = ""
    for s in all_sources:
        source_dump += f"\n\n### 搜索: {s['query']}\n{s['content']}"

    # Step 3: CPO 判断需要哪些 Agent 参与
    role_prompt = (
        f"你是智能骑行头盔项目的产品VP（CPO）。\n"
        f"研究任务：{title}\n目标：{goal}\n\n"
        f"判断这个任务需要以下哪些角色参与分析：\n"
        f"- CTO：技术可行性、参数对比、芯片/模组选型、风险评估\n"
        f"- CMO：市场验证、竞争格局、定价策略、商业模式、用户画像\n"
        f"- CDO：产品形态、用户体验、工业设计、外观约束\n\n"
        f"只输出 JSON 数组，如 [\"CTO\", \"CMO\"] 或 [\"CTO\", \"CMO\", \"CDO\"]\n"
        f"如果任务偏技术，CDO 可以不参与。如果任务偏商业/用户，CTO 可以精简参与。"
    )

    role_result = gateway.call_azure_openai("cpo", role_prompt, "只输出 JSON 数组。", "role_assign")
    roles = ["CTO", "CMO"]  # 默认
    if role_result.get("success"):
        try:
            resp = role_result["response"].strip()
            resp = re.sub(r'^```json\s*', '', resp)
            resp = re.sub(r'\s*```$', '', resp)
            parsed = json.loads(resp)
            if isinstance(parsed, list) and all(r in ("CTO", "CMO", "CDO") for r in parsed):
                roles = parsed
        except:
            pass

    print(f"  [Roles] {roles}")
    if progress_callback:
        progress_callback(f"  Participants: {', '.join(roles)}")

    # 构建产品定义锚点（不可违背的约束）
    product_anchor = ""
    for f in KB_ROOT.rglob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            tags = data.get("tags", [])
            if "internal" in tags and ("prd" in tags or "product_definition" in tags):
                product_anchor = data.get("content", "")[:3000]
                break
        except:
            continue

    # 产品定义硬约束（注入每个 Agent 的 prompt）
    anchor_instruction = (
        f"\n\n## 产品定义锚点（不可违背）\n"
        f"以下是用户已确定的产品定义，你的所有分析必须在此框架内进行。\n"
        f"你可以建议功能分阶段（V1/V2），可以指出风险，可以建议优先级调整，\n"
        f"但**绝不能替用户更换产品品类、目标用户群或核心产品方向**。\n"
        f"如果你认为某个方向风险很高，应该说\"建议V1先做XX，V2再做YY\"，\n"
        f"而不是说\"不应该做XX\"。产品愿景的最终决定权在用户。\n\n"
        f"{product_anchor[:2500] if product_anchor else '无内部产品定义文档。'}\n"
    )

    # Step 3.5: 各 Agent 并行分析
    agent_outputs = {}

    source_material = source_dump[:12000]  # 搜索材料
    kb_material = kb_context[:2000]  # 知识库

    if "CTO" in roles:
        cto_prompt = (
            f"你是智能骑行头盔项目的技术合伙人（CTO）。\n"
            f"你拥有顶尖的技术判断力，不会泛泛而谈，每个判断都有具体数据支撑。\n"
            f"{anchor_instruction}\n"
            f"{THINKING_PRINCIPLES}\n"
            f"## 研究任务\n{title}\n\n## 目标\n{goal}\n\n"
            f"## 已有知识库\n{kb_material}\n\n"
            f"## 调研材料\n{source_material}\n\n"
            f"## 你的任务\n"
            f"从技术角度分析这个问题。要求：\n"
            f"1. 给出具体的技术参数对比（型号、规格、价格区间）\n"
            f"2. 评估技术可行性和风险\n"
            f"3. 给出明确的技术推荐（不要模棱两可）\n"
            f"4. 标注你不确定的信息\n"
            f"5. 如果某些功能风险高，建议分阶段实现，而不是砍掉\n"
            f"6. 输出 1000-1500 字\n"
        )
        cto_result = gateway.call_azure_openai("cto", cto_prompt,
            "你是资深技术合伙人，输出专业的技术分析。", "deep_research_cto")
        if cto_result.get("success"):
            agent_outputs["CTO"] = cto_result["response"]
            print(f"  [CTO] {len(cto_result['response'])} chars")

    if "CMO" in roles:
        cmo_prompt = (
            f"你是智能骑行头盔项目的市场合伙人（CMO）。\n"
            f"你拥有敏锐的商业判断力，能识别伪需求，每个判断都基于数据或逻辑推演。\n"
            f"{anchor_instruction}\n"
            f"{THINKING_PRINCIPLES}\n"
            f"## 研究任务\n{title}\n\n## 目标\n{goal}\n\n"
            f"## 已有知识库\n{kb_material}\n\n"
            f"## 调研材料\n{source_material}\n\n"
            f"## 你的任务\n"
            f"从市场和商业角度分析这个问题。要求：\n"
            f"1. 竞品是怎么做的？成功还是失败？为什么？\n"
            f"2. 用户真正在意什么？购买决策的关键因素？\n"
            f"3. 定价和商业模式建议\n"
            f"4. 给出明确的市场判断（不要两边讨好）\n"
            f"5. 如果市场风险高，建议如何分阶段验证，而不是放弃方向\n"
            f"6. 输出 1000-1500 字\n"
        )
        cmo_result = gateway.call_azure_openai("cmo", cmo_prompt,
            "你是资深市场合伙人，输出专业的商业分析。", "deep_research_cmo")
        if cmo_result.get("success"):
            agent_outputs["CMO"] = cmo_result["response"]
            print(f"  [CMO] {len(cmo_result['response'])} chars")

    if "CDO" in roles:
        cdo_prompt = (
            f"你是智能骑行头盔项目的设计合伙人（CDO）。\n"
            f"你懂工程约束，用设计语言表达品牌战略。\n"
            f"{anchor_instruction}\n"
            f"{THINKING_PRINCIPLES}\n"
            f"## 研究任务\n{title}\n\n## 目标\n{goal}\n\n"
            f"## 已有知识库\n{kb_material}\n\n"
            f"## 调研材料\n{source_material}\n\n"
            f"## 你的任务\n"
            f"从产品设计和用户体验角度分析。要求：\n"
            f"1. 产品形态和用户体验的关键约束\n"
            f"2. 设计上的取舍建议（重量、体积、外观、佩戴感）\n"
            f"3. 竞品的设计优劣势\n"
            f"4. 如果设计约束导致某些功能难以首代实现，建议分阶段路径\n"
            f"5. 输出 800-1200 字\n"
        )
        cdo_result = gateway.call_azure_openai("cdo", cdo_prompt,
            "你是资深设计合伙人，输出专业的设计分析。", "deep_research_cdo")
        if cdo_result.get("success"):
            agent_outputs["CDO"] = cdo_result["response"]
            print(f"  [CDO] {len(cdo_result['response'])} chars")

    if not agent_outputs:
        # 全部失败，fallback 到单 CPO 模式
        print("  [WARN] All agents failed, fallback to single CPO")
        synthesis_prompt_fallback = (
            f"## 研究任务\n{title}\n## 目标\n{goal}\n"
            f"## 知识库\n{kb_material}\n## 材料\n{source_material}\n"
            f"写一份 2000-3000 字的完整研究报告。"
        )
        fallback = gateway.call_azure_openai("cpo", synthesis_prompt_fallback,
            "你是资深研发顾问。", "deep_research_fallback")
        report = fallback.get("response", "报告生成失败") if fallback.get("success") else "报告生成失败"
    else:
        # Step 4: CPO 整合多视角
        agent_section = ""
        for role, output in agent_outputs.items():
            agent_section += f"\n\n### {role} 分析\n{output}"

        synthesis_prompt = (
            f"你是智能骑行头盔项目的产品VP（CPO），负责整合团队各视角并做最终裁决。\n\n"
            f"{THINKING_PRINCIPLES}\n"
            f"特别注意：如果团队某个角色在解决 XY 问题（表面问题而非真正问题），你必须指出并纠正。\n\n"
            f"## 产品定义锚点（最高优先级）\n"
            f"用户已确定的产品方向不可更改。你可以建议功能分V1/V2，但不能替用户换产品品类。\n"
            f"如果团队某个角色的分析偏离了用户的产品定义（比如用户定义的是摩托车头盔，"
            f"某角色建议改做自行车头盔），你必须纠正这个偏差。\n\n"
            f"## 研究任务\n{title}\n\n"
            f"## 目标\n{goal}\n\n"
            f"## 团队各视角分析\n{agent_section}\n\n"
            f"## 你的任务\n"
            f"1. 整合以上 {len(agent_outputs)} 个角色的分析，写一份 2500-3500 字的综合研究报告\n"
            f"2. 如果各角色观点有冲突，明确标注冲突点并给出你的裁决和理由\n"
            f"3. 如果某角色的分析偏离了用户的产品定义，指出来并纠正\n"
            f"4. 报告结构：执行摘要 → 核心分析 → 冲突与裁决 → 明确结论与行动建议\n"
            f"5. 保留各角色分析中的所有具体数据（型号、参数、价格）\n"
            f"6. 最后必须有一个明确的'一句话决策'\n"
        )

        synthesis_result = gateway.call_azure_openai("cpo", synthesis_prompt,
            "你是产品VP，整合团队分析并裁决。", "deep_research_synthesis")

        if not synthesis_result.get("success"):
            # 重试一次，用更精简的 prompt
            retry_prompt = (
                f"请整合以下团队分析，写一份 2000-3000 字的研究报告。\n"
                f"任务：{title}\n目标：{goal}\n\n"
                f"{agent_section[:8000]}\n\n"
                f"要求：有执行摘要、有明确结论、保留所有具体数据。"
            )
            retry_result = gateway.call_azure_openai("cpo", retry_prompt,
                "整合团队分析。", "synthesis_retry")
            if retry_result.get("success"):
                report = retry_result["response"]
                print(f"  [Synthesis Retry] OK {len(report)} chars")
            else:
                # 最终 fallback：让 CPO 基于最长的 Agent 输出扩写
                longest_role = max(agent_outputs.keys(), key=lambda r: len(agent_outputs[r]))
                longest_output = agent_outputs[longest_role]
                other_highlights = ""
                for role, output in agent_outputs.items():
                    if role != longest_role:
                        other_highlights += f"\n{role} 要点：{output[:500]}\n"

                expand_prompt = (
                    f"以下是 {longest_role} 对「{title}」的分析，以及其他角色的要点摘要。\n"
                    f"请在此基础上写一份完整的 2000-3000 字研究报告。\n\n"
                    f"## {longest_role} 完整分析\n{longest_output}\n\n"
                    f"## 其他角色要点\n{other_highlights}\n\n"
                    f"要求：有执行摘要、有明确结论。"
                )
                expand_result = gateway.call_azure_openai("cpo", expand_prompt,
                    "写研究报告。", "synthesis_expand")
                report = expand_result.get("response", agent_section) if expand_result.get("success") else agent_section
                print(f"  [Synthesis Expand] {len(report)} chars")
        else:
            report = synthesis_result["response"]

            # Step 5: Critic 评审
            critic_prompt = (
                f"你是研发质量评审专家。你的评审方法是苏格拉底追问，而不是简单打分。\n\n"
                f"## 思维准则\n"
                f"1. 第一性原理：这个报告是否从用户的真正需求出发？还是在解决一个 XY 问题？\n"
                f"2. 奥卡姆剃刀：报告中有没有不必要的复杂度？能不能更简洁直接？\n"
                f"3. 苏格拉底追问：每个关键结论，追问一层——证据充分吗？有替代方案吗？失败风险是什么？\n\n"
                f"## 任务目标\n{goal}\n\n"
                f"## 报告（{len(report)}字）\n{report[:8000]}\n\n"
                f"## 评审要求\n"
                f"对每个参与角色（{', '.join(agent_outputs.keys())}）回答：\n"
                f"1. 这个角色是否在解决真正的问题？还是跑偏了？\n"
                f"2. 分析中有没有可以砍掉的冗余？\n"
                f"3. 关键结论的证据是否充分？缺了什么具体数据？\n"
                f"4. 有没有被忽略的更优替代方案？\n\n"
                f"输出 JSON：\n"
                f'{{\"overall\": \"PASS或NEEDS_FIX\", '
                f'\"issues\": [{{\"role\": \"CTO/CMO/CDO\", \"problem\": \"具体问题\", \"fix\": \"具体修复建议\"}}]}}\n'
                f"如果报告有具体数据和明确结论且回答了核心问题，overall 为 PASS。\n"
                f"只有在发现 XY 问题、关键数据缺失、或结论无法支撑决策时才 NEEDS_FIX。"
            )

            critic_result = gateway.call_azure_openai("cpo", critic_prompt, "只输出 JSON。", "critic_review")

            needs_fix = False
            fix_instructions = {}

            if critic_result.get("success"):
                try:
                    resp = critic_result["response"].strip()
                    resp = re.sub(r'^```json\s*', '', resp)
                    resp = re.sub(r'\s*```$', '', resp)
                    critic_data = json.loads(resp)

                    if critic_data.get("overall") == "NEEDS_FIX" and critic_data.get("issues"):
                        needs_fix = True
                        for issue in critic_data["issues"]:
                            role = issue.get("role", "")
                            if role in agent_outputs:
                                fix_instructions[role] = {
                                    "problem": issue.get("problem", ""),
                                    "fix": issue.get("fix", ""),
                                    "previous_output": agent_outputs[role]
                                }
                        print(f"  [Critic] NEEDS_FIX: {list(fix_instructions.keys())}")
                        if progress_callback:
                            progress_callback(f"  Critic: needs fix for {list(fix_instructions.keys())}")
                    else:
                        print(f"  [Critic] PASS")

                except Exception as e:
                    print(f"  [Critic] Parse failed: {e}")

            # Step 6: 定向修复（最多 1 轮）
            if needs_fix and fix_instructions:
                fixed_outputs = dict(agent_outputs)  # 复制，保留合格的

                for role, instruction in fix_instructions.items():
                    fix_prompt = (
                        f"你是智能骑行头盔项目的{role}。\n"
                        f"你上一版分析被评审发现以下问题：\n"
                        f"问题：{instruction['problem']}\n"
                        f"修复建议：{instruction['fix']}\n\n"
                        f"你的上一版输出：\n{instruction['previous_output']}\n\n"
                        f"请修复上述问题，输出改进后的完整分析（1000-1500字）。\n"
                        f"重点补充评审指出的缺失内容，保留上一版中没问题的部分。"
                    )

                    role_key = role.lower()
                    fix_result = gateway.call_azure_openai(role_key, fix_prompt,
                        f"你是{role}，修复评审指出的问题。", f"deep_research_fix_{role_key}")

                    if fix_result.get("success"):
                        fixed_outputs[role] = fix_result["response"]
                        print(f"  [Fix {role}] {len(fix_result['response'])} chars")

                # 重新整合
                fixed_section = ""
                for role, output in fixed_outputs.items():
                    fixed_section += f"\n\n### {role} 分析（修复后）\n{output}"

                re_synthesis_prompt = (
                    f"你是产品VP（CPO）。以下是团队修复后的分析。\n"
                    f"请重新整合为一份 2500-3500 字的综合报告。\n"
                    f"保留所有具体数据，给出明确结论。\n\n"
                    f"## 任务\n{title}\n## 目标\n{goal}\n\n"
                    f"## 团队分析{fixed_section}\n"
                )

                re_result = gateway.call_azure_openai("cpo", re_synthesis_prompt,
                    "整合修复后的团队分析。", "deep_research_re_synthesis")

                if re_result.get("success"):
                    report = re_result["response"]
                    print(f"  [Re-Synthesis] {len(report)} chars")

            # 附加 Critic 评审意见到报告末尾
            if critic_result.get("success"):
                report += f"\n\n---\n## Critic Review\n{critic_result['response'][:1000]}"

    # Step 4: 保存报告到文件
    report_path = REPORT_DIR / f"{task_id}_{time.strftime('%Y%m%d_%H%M')}.md"
    report_path.write_text(f"# {title}\n\n> 目标: {goal}\n> 生成时间: {time.strftime('%Y-%m-%d %H:%M')}\n> 来源数: {len(all_sources)}\n\n{report}", encoding="utf-8")
    print(f"\n[Saved] {report_path}")

    # Step 4.5: 完整报告存入知识库
    from src.tools.knowledge_base import add_report
    report_kb_path = add_report(
        title=f"[研究报告] {title}",
        domain="components",
        content=report,  # 全文
        tags=["deep_research", "report", task_id],
        source=f"deep_research:{task_id}",
        confidence="high"
    )
    print(f"[KB Report] {report_kb_path}")

    # Step 5: 从报告中提取关键知识条目存入知识库（作为索引）
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
            added_count = 0
            skipped_count = 0
            for item in items:
                domain = item.get("domain", "components")
                if domain not in ("competitors", "components", "standards", "lessons"):
                    domain = "components"

                # === 29a: 自主质量评估——入库前过滤 ===
                title_text = item.get("title", "")[:80]
                content_text = item.get("summary", "")[:800]

                is_low_quality = False
                quality_reasons = []

                # 规则1：内容太短（<150字）
                if len(content_text) < 150:
                    is_low_quality = True
                    quality_reasons.append("内容<150字")

                # 规则2：没有任何具体数据（数字、型号、价格、百分比）
                has_data = bool(re.search(r'\d+\.?\d*\s*(mm|cm|g|kg|mAh|W|V|Hz|dB|美元|元|USD|\$|%|nits|lux|fps|°|μm)', content_text))
                has_model = bool(re.search(r'[A-Z]{2,}\d{2,}|[A-Z]\d{4,}|IMX\d|QCC\d|BES\d|nRF\d|AR\d|ECE\s*\d|SN\d|KS\d', content_text))
                if not has_data and not has_model:
                    is_low_quality = True
                    quality_reasons.append("无具体数据或型号")

                # 规则3：标题是泛泛的描述
                generic_titles = ["智能头盔", "骑行头盔", "头盔方案", "技术方案", "市场分析", "智能摩托车头盔", "摩托车头盔"]
                if any(title_text.strip() == g for g in generic_titles):
                    is_low_quality = True
                    quality_reasons.append("标题太泛")

                if is_low_quality:
                    print(f"  [SKIP] {title_text[:40]}... — 质量不足: {', '.join(quality_reasons)}")
                    skipped_count += 1
                    continue

                add_knowledge(
                    title=title_text,
                    domain=domain,
                    content=content_text,
                    tags=item.get("tags", []) + ["deep_research", task_id],
                    source=f"deep_research:{task_id}",
                    confidence="high"
                )
                added_count += 1
            print(f"[KB] 提取 {added_count} 条知识，跳过 {skipped_count} 条低质量")
        except:
            print("[KB] 提取失败")

    return report


def run_all(progress_callback=None):
    """运行所有深度研究任务

    注意：夜间（23:00-07:00）不推送进度，只打印
    """
    from datetime import datetime

    # 白天/夜间模式检测
    current_hour = datetime.now().hour
    is_night = current_hour >= 23 or current_hour < 7

    print(f"\n{'#'*60}")
    print(f"# 智能骑行头盔 JDM 供应商选型 — 深度研究")
    print(f"# 共 {len(RESEARCH_TASKS)} 个任务")
    print(f"# 开始时间: {time.strftime('%Y-%m-%d %H:%M')}")
    if is_night:
        print("# [夜间模式] 进度不推送，仅本地打印")
    print(f"{'#'*60}")

    # 夜间模式：不推送进度
    effective_callback = None if is_night else progress_callback

    if effective_callback:
        effective_callback(f"🚀 开始深度研究（{len(RESEARCH_TASKS)} 个任务）")

    reports = []
    for idx, task in enumerate(RESEARCH_TASKS, 1):
        if effective_callback:
            effective_callback(f"🔍 [{idx}/{len(RESEARCH_TASKS)}] 开始: {task['title']}")

        report = deep_research_one(task, progress_callback=effective_callback)
        reports.append({"title": task["title"], "report": report})
        print(f"\n✅ {task['title']} 完成 ({len(report)} 字)")

        if effective_callback:
            effective_callback(f"✅ [{idx}/{len(RESEARCH_TASKS)}] {task['title']} ({len(report)}字)")

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

    # 任务完成提示音
    try:
        from src.utils.notifier import notify
        notify("success")
    except:
        print('\a')  # ASCII bell fallback

    return str(summary_path)


def parse_research_tasks_from_md(md_path: str) -> list:
    """从 markdown 文件解析研究任务

    支持的格式：
    - # 研究 A：标题 -> 解析为任务
    - ## A.1 子任务标题 -> 解析为 searches
    - goal 从 "研究目标" 部分提取
    """
    content = Path(md_path).read_text(encoding="utf-8")
    tasks = []

    # 匹配研究标题：# 研究 A：XXX 或 # 研究 B：XXX
    research_pattern = re.compile(r'^# 研究 ([A-Z])：(.+)$', re.MULTILINE)

    for match in research_pattern.finditer(content):
        task_id = f"research_{match.group(1).lower()}"
        title = match.group(2).strip()

        # 提取该研究的完整内容（到下一个 # 研究 或文件结束）
        start_pos = match.end()
        next_match = research_pattern.search(content, start_pos)
        end_pos = next_match.start() if next_match else len(content)
        section_content = content[start_pos:end_pos]

        # 提取目标（从 ## X.0 研究目标 部分）
        goal_match = re.search(r'## [A-Z]\.0\s*(?:研究目标|分析目标)\s*\n([^\n]+(?:\n(?![#])[^\n]+)*)', section_content)
        goal = goal_match.group(1).strip() if goal_match else f"深度研究：{title}"

        # 提取 searches（从子任务标题 ## A.1.1 等）
        searches = []

        # 匹配子任务：### A.1.1 标题 或 ## A.1 标题
        subtask_pattern = re.compile(r'^#{2,3}\s+[A-Z]\.\d+(?:\.\d+)?\s+(.+)$', re.MULTILINE)
        for sub_match in subtask_pattern.finditer(section_content):
            sub_title = sub_match.group(1).strip()
            # 将子任务标题转换为搜索关键词
            search_query = f"{sub_title} motorcycle helmet HUD specs parameters 2025 2026"
            searches.append(search_query)

        # 添加默认搜索词
        if not searches:
            searches = [
                f"{title} motorcycle helmet HUD 2025 2026",
                f"{title} optical display specifications",
            ]

        tasks.append({
            "id": task_id,
            "title": title,
            "goal": goal,
            "searches": searches[:10],  # 最多 10 个搜索
            "source_file": str(md_path),
        })

    return tasks


def run_research_from_file(md_path: str, progress_callback=None, task_ids: list = None):
    """从 markdown 文件运行研究任务

    Args:
        md_path: 任务定义文件路径
        progress_callback: 进度回调函数
        task_ids: 指定运行的任务 ID 列表，如 ['research_a', 'research_b']；None 表示全部运行
    """
    tasks = parse_research_tasks_from_md(md_path)

    if not tasks:
        print(f"[Warning] 未从 {md_path} 解析到任务")
        return None

    # 过滤指定任务
    if task_ids:
        tasks = [t for t in tasks if t["id"] in task_ids]

    if not tasks:
        print(f"[Warning] 指定的 task_ids {task_ids} 未在文件中找到")
        return None

    print(f"\n{'#'*60}")
    print(f"# 从文件运行深度研究: {md_path}")
    print(f"# 共 {len(tasks)} 个任务")
    print(f"# 开始时间: {time.strftime('%Y-%m-%d %H:%M')}")
    print(f"{'#'*60}")

    reports = []
    for idx, task in enumerate(tasks, 1):
        if progress_callback:
            progress_callback(f"🔍 [{idx}/{len(tasks)}] 开始: {task['title']}")

        report = deep_research_one(task, progress_callback=progress_callback)
        reports.append({"id": task["id"], "title": task["title"], "report": report})
        print(f"\n✅ {task['title']} 完成 ({len(report)} 字)")

        if progress_callback:
            progress_callback(f"✅ [{idx}/{len(tasks)}] {task['title']} ({len(report)}字)")

        time.sleep(3)

    # 汇总保存
    md_name = Path(md_path).stem
    summary_path = REPORT_DIR / f"{md_name}_summary_{time.strftime('%Y%m%d_%H%M')}.md"
    summary = f"# {md_name} — 深度研究汇总\n\n"
    summary += f"> 来源文件: {md_path}\n"
    summary += f"> 生成时间: {time.strftime('%Y-%m-%d %H:%M')}\n\n"
    for r in reports:
        summary += f"\n---\n\n## {r['title']}\n\n{r['report']}\n"
    summary_path.write_text(summary, encoding="utf-8")

    print(f"\n{'#'*60}")
    print(f"# 全部完成！")
    print(f"# 报告: {summary_path}")
    print(f"# 完成时间: {time.strftime('%Y-%m-%d %H:%M')}")
    print(f"{'#'*60}")

    return str(summary_path)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        # 支持命令行参数：python tonight_deep_research.py path/to/tasks.md [task_ids...]
        md_path = sys.argv[1]
        task_ids = sys.argv[2:] if len(sys.argv) > 2 else None
        run_research_from_file(md_path, task_ids=task_ids)
    else:
        # 默认运行内置任务
        run_all()