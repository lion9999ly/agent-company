"""
深度研究 — 核心管道 (Layer 1-4)
职责: deep_research_one（五层管道主流程）、deep_drill（深钻）、Agent辩论
被调用方: runner.py
依赖: models.py, extraction.py, critic.py, learning.py, night_watch.py
搜索层: smolagents 工具（TavilySearchTool, DoubaoSearchTool）
"""
import json
import re
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from scripts.litellm_gateway import call_for_search
from src.tools.knowledge_base import add_knowledge, KB_ROOT
from src.tools.tool_registry import ToolRegistry
from src.utils.progress_heartbeat import ProgressHeartbeat
from scripts.meta_capability import (
    CAPABILITY_GAP_INSTRUCTION, scan_capability_gaps,
    resolve_all_gaps,
)

# === smolagents 搜索工具导入 ===
from scripts.smolagents_research.tavily_search_tool import TavilySearchTool
from scripts.smolagents_research.doubao_search_tool import DoubaoSearchTool

from scripts.deep_research.models import (
    call_model, call_with_backoff, get_model_for_role, get_model_for_task, gateway
)
from scripts.deep_research.extraction import extract_structured_data
from scripts.deep_research.critic import run_critic_challenge
from scripts.deep_research.learning import (
    get_related_findings, save_task_findings, match_expert_framework,
    get_agent_prompt_with_lessons,
)
from scripts.deep_research.night_watch import diagnose as night_watch_diagnose
from scripts.deep_research.health_monitor import (
    record_model_404, record_l2_result, record_search_empty
)

registry = ToolRegistry()

REPORT_DIR = Path(__file__).resolve().parent.parent.parent / ".ai-state" / "reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# SearchRouter - 多通道搜索分流（smolagents 工具版）
# ============================================================

class SearchRouter:
    """搜索路由器：按语言和内容类型分流到不同搜索通道

    通道：
    - Tavily：英文搜索首选（smolagents Tool）
    - doubao：中文搜索首选（smolagents Tool）
    - Gemini：备用通道
    - Grok：备用通道

    关键：不要用 Claude Code WebSearch（harness 配置问题）
    """

    def __init__(self):
        self._last_search_time = 0
        # 初始化 smolagents 搜索工具
        self._tavily_tool = TavilySearchTool()
        self._doubao_tool = DoubaoSearchTool()

    def search(self, query: str, language: str = 'auto') -> str:
        """执行搜索，返回结果文本

        Args:
            query: 搜索词
            language: 'auto'（自动检测）/'zh'/'en'

        Returns:
            搜索结果文本（失败返回空字符串）
        """
        # 搜索间隔防限流
        elapsed = time.time() - self._last_search_time
        if elapsed < 2:
            time.sleep(2 - elapsed)
        self._last_search_time = time.time()

        if language == 'auto':
            language = self._detect_language(query)

        if language == 'zh':
            # 中文查询：doubao 优先
            result = self._search_doubao(query)
            if result:
                return result
            return self._search_tavily(query)
        else:
            # 英文查询：Tavily 优先
            result = self._search_tavily(query)
            if result:
                return result
            return self._search_gemini(query)

    def _detect_language(self, text: str) -> str:
        """简单语言检测：含中文字符则返回 zh"""
        for char in text:
            if '\u4e00' <= char <= '\u9fff':
                return 'zh'
        return 'en'

    def _search_tavily(self, query: str) -> str:
        """Tavily 搜索（smolagents Tool）"""
        try:
            result = self._tavily_tool.forward(
                query=query,
                search_depth="advanced",
                max_results=5,
                include_raw_content=False
            )
            if result and len(result) > 100:
                return result
        except Exception as e:
            print(f"  [SearchRouter] Tavily 失败: {e}")
        return ''

    def _search_doubao(self, query: str) -> str:
        """豆包搜索（smolagents Tool）"""
        try:
            result = self._doubao_tool.forward(query=query, num_results=5)
            if result and len(result) > 100:
                return result
        except Exception as e:
            print(f"  [SearchRouter] doubao 失败: {e}")
        return ''

    def _search_gemini(self, query: str) -> str:
        """Gemini 2.5 Flash 搜索增强"""
        try:
            result = call_model('gemini_2_5_flash', query,
                system_prompt="搜索并返回相关信息。",
                task_type='search')
            if result and result.get('success'):
                return result.get('response', '')
        except Exception as e:
            print(f"  [SearchRouter] Gemini 失败: {e}")
        return ''

    def _search_grok(self, query: str) -> str:
        """Grok 4 搜索（备用）"""
        try:
            result = call_model('grok_4', query,
                system_prompt="搜索并返回相关信息。",
                task_type='search')
            if result and result.get('success'):
                return result.get('response', '')
        except Exception as e:
            print(f"  [SearchRouter] Grok 失败: {e}")
        return ''


# 全局 SearchRouter 实例
search_router = SearchRouter()


# ============================================================
# 三原则
# ============================================================
THINKING_PRINCIPLES = """
## 思维准则（所有分析必须遵循）

1. **第一性原理**：拒绝经验主义和路径盲从。从原始需求和本质问题出发。

2. **奥卡姆剃刀**：如无必要，勿增实体。暴力删除所有不影响核心交付的冗余。

3. **苏格拉底追问**：对每个方案连续追问——
   - 这个方案解决的是真正的问题，还是 XY 问题？
   - 当前选择的路径有什么弊端？
   - 有没有更优雅、成本更低的替代方案？
   - 如果失败，最可能的原因是什么？
"""


# ============================================================
# Agent 辩论
# ============================================================
def _run_agent_debate(agent_outputs: dict, goal: str, evidence: str) -> dict:
    """检测 Agent 间分歧，触发交锋，生成裁决"""
    combined = "\n\n".join([f"[{role}]\n{output[:1500]}"
                           for role, output in agent_outputs.items()])
    detect_prompt = (
        f"以下是不同 Agent 对同一研究任务的分析：\n\n{combined}\n\n"
        f"找出观点分歧。\n"
        f"输出 JSON: {{\"has_conflict\": true/false, \"conflicts\": ["
        f"{{\"topic\": \"分歧主题\", \"side_a\": {{\"agent\": \"CTO\", \"position\": \"观点\"}}, "
        f"\"side_b\": {{\"agent\": \"CMO\", \"position\": \"观点\"}}}}]}}\n"
        f"只输出 JSON。"
    )
    detect_result = call_model("gemini_2_5_flash", detect_prompt, task_type="data_extraction")
    if not detect_result.get("success"):
        return agent_outputs

    try:
        resp = detect_result["response"].strip()
        resp = re.sub(r'^```json\s*', '', resp)
        resp = re.sub(r'\s*```$', '', resp)
        conflicts = json.loads(resp)
    except:
        return agent_outputs

    if not conflicts.get("has_conflict") or not conflicts.get("conflicts"):
        print("  [Debate] 无实质分歧")
        return agent_outputs

    print(f"  [Debate] 发现 {len(conflicts['conflicts'])} 个分歧点，开始交锋...")

    debate_record = []
    for conflict in conflicts["conflicts"][:2]:
        topic = conflict.get("topic", "")
        side_a = conflict.get("side_a", {})
        side_b = conflict.get("side_b", {})

        rebuttal_a = call_model(
            get_model_for_role(side_a.get("agent", "CTO")),
            f"你之前的观点是：{side_a.get('position', '')}\n"
            f"{side_b.get('agent', 'CMO')} 的反对观点是：{side_b.get('position', '')}\n"
            f"请用具体数据反驳或承认对方有道理。\n参考数据:\n{evidence[:2000]}",
            task_type="debate"
        )
        rebuttal_b = call_model(
            get_model_for_role(side_b.get("agent", "CMO")),
            f"你之前的观点是：{side_b.get('position', '')}\n"
            f"{side_a.get('agent', 'CTO')} 的反驳是：{rebuttal_a.get('response', '')[:500]}\n"
            f"请用具体数据回应。\n参考数据:\n{evidence[:2000]}",
            task_type="debate"
        )

        debate_record.append({
            "topic": topic,
            "side_a": {"agent": side_a.get("agent"),
                       "rebuttal": rebuttal_a.get("response", "")[:500]},
            "side_b": {"agent": side_b.get("agent"),
                       "rebuttal": rebuttal_b.get("response", "")[:500]},
        })

    debate_text = json.dumps(debate_record, ensure_ascii=False, indent=2)
    agent_outputs["_debate"] = (
        f"\n## Agent 辩论记录\n\n"
        f"以下分歧经过交锋后的记录，synthesis 请重点关注并裁决：\n\n"
        f"{debate_text[:3000]}"
    )
    print(f"  [Debate] 交锋完成，{len(debate_record)} 个分歧点记录已注入 synthesis")
    return agent_outputs


# ============================================================
# 深钻模式
# ============================================================
def deep_drill(topic: str, max_rounds: int = 4, progress_callback=None) -> str:
    all_findings = []

    for round_num in range(1, max_rounds + 1):
        round_type = {1: "广搜", 2: "追问", 3: "验证", 4: "结论"}
        print(f"\n  [DeepDrill] 第 {round_num} 轮: {round_type.get(round_num, '深入')}")

        if progress_callback:
            progress_callback(f"深钻 [{round_num}/{max_rounds}] {topic}: {round_type.get(round_num, '深入')}")

        if round_num == 1:
            task = {
                "id": f"drill_{topic[:20]}_{round_num}",
                "title": f"深钻-{topic}-广搜",
                "goal": f"全面搜索关于 {topic} 的信息",
                "searches": _generate_drill_queries(topic, "broad"),
            }
        elif round_num == 2:
            gaps = _extract_gaps_from_findings(all_findings[-1] if all_findings else "")
            task = {
                "id": f"drill_{topic[:20]}_{round_num}",
                "title": f"深钻-{topic}-追问",
                "goal": f"针对以下疑点深入调查:\n{gaps}",
                "searches": _generate_drill_queries(topic, "deep",
                    context=all_findings[-1] if all_findings else ""),
            }
        elif round_num == 3:
            contradictions = _extract_contradictions(all_findings)
            if not contradictions:
                print(f"  [DeepDrill] 无矛盾数据，跳过验证轮")
                continue
            task = {
                "id": f"drill_{topic[:20]}_{round_num}",
                "title": f"深钻-{topic}-验证",
                "goal": f"验证以下矛盾数据:\n{contradictions}",
                "searches": _generate_drill_queries(topic, "verify", context=contradictions),
            }
        else:
            conclusion_prompt = (
                f"基于以下 {len(all_findings)} 轮深钻研究，"
                f"形成关于 {topic} 的最终结论报告。\n\n"
                + "\n\n---\n\n".join([f"## 第{i + 1}轮\n{f[:2000]}"
                                     for i, f in enumerate(all_findings)])
            )
            result = call_model("gpt_5_4", conclusion_prompt,
                "你是高级分析师，输出结构化的结论报告。", "deep_drill_conclusion")
            if result.get("success"):
                all_findings.append(result["response"])
            break

        if round_num < 4:
            report = deep_research_one(task, progress_callback=progress_callback)
            all_findings.append(report)

    final_report = "\n\n".join([f"## 第{i + 1}轮\n{f}"
                                for i, f in enumerate(all_findings)])
    add_knowledge(
        title=f"[深钻] {topic}", domain="lessons",
        content=final_report[:2000], tags=["deep_drill", topic],
        source="deep_drill", confidence="high"
    )
    return final_report


def _generate_drill_queries(topic: str, mode: str, context: str = "") -> list:
    prompt = f"为主题 '{topic}' 生成 6-8 个搜索关键词。"
    if mode == "broad":
        prompt += "\n搜索方向: 全面覆盖（技术、市场、供应商、竞品、用户）"
    elif mode == "deep":
        prompt += f"\n搜索方向: 针对以下发现中的疑点追问:\n{context[:1000]}"
    elif mode == "verify":
        prompt += f"\n搜索方向: 验证以下矛盾数据点:\n{context[:1000]}"
    prompt += "\n只输出搜索词列表，每行一个。"

    result = call_model("gemini_2_5_flash", prompt, task_type="query_generation")
    if result.get("success"):
        queries = [q.strip() for q in result["response"].strip().split("\n") if q.strip()]
        return queries[:8]
    return [topic]


def _extract_gaps_from_findings(findings: str) -> str:
    result = call_model("gemini_2_5_flash",
        f"从以下研究发现中，提取 3-5 个疑点或缺口:\n\n{findings[:2000]}\n\n只输出疑点列表。",
        task_type="query_generation")
    return result.get("response", "") if result.get("success") else ""


def _extract_contradictions(all_findings: list) -> str:
    combined = "\n---\n".join([f[:1000] for f in all_findings])
    result = call_model("gemini_2_5_flash",
        f"从以下多轮研究中，找出数据矛盾的地方:\n\n{combined}\n\n如果没有矛盾，输出'无矛盾'。",
        task_type="query_generation")
    resp = result.get("response", "") if result.get("success") else ""
    if "无矛盾" in resp:
        return ""
    return resp


# ============================================================
# 核心: deep_research_one
# ============================================================
def deep_research_one(task: dict, progress_callback=None,
                      constraint_context: str = None) -> str:
    """对一个任务做深度研究，返回完整报告"""
    task_id = task.get("id", f"task_{int(time.time())}")
    title = task.get("title", "")
    goal = task.get("goal", "")
    searches_raw = task.get("searches", [])

    # === BUG FIX: 防御 searches 为 int 的情况 ===
    if isinstance(searches_raw, int):
        print(f"  [WARN] searches 是 int({searches_raw})，转为空 list 后自动生成")
        searches = []
    elif isinstance(searches_raw, list):
        searches = searches_raw
    else:
        searches = []

    if constraint_context:
        goal = f"{goal}\n\n【研究约束】\n{constraint_context}"

    print(f"\n{'=' * 60}")
    print(f"[Deep Research] {title}")
    print(f"[Goal] {goal[:200]}...")
    print(f"[Sources] {len(searches)} searches")
    print(f"{'=' * 60}")

    # 注入历史发现
    prior_findings = get_related_findings(title, goal)
    if prior_findings:
        print(f"  [Knowledge Transfer] 发现相关历史发现")
        goal = goal + prior_findings

    if progress_callback:
        progress_callback(f"Researching: {title[:20]}...")

    # 自动生成搜索词
    if not searches:
        gen_prompt = (
            f"你是智能骑行头盔项目的研究规划师。\n"
            f"研究主题：{title}\n目标：{goal}\n\n"
            f"请生成 6-8 个搜索词。具体、含品牌名/型号、中英文混合。\n"
            f"只输出 JSON 数组。"
        )
        gen_result = call_for_search(gen_prompt, "只输出 JSON 数组。", "gen_searches")
        if gen_result.get("success"):
            try:
                resp = gen_result["response"].strip()
                resp = re.sub(r'^```json\s*', '', resp)
                resp = re.sub(r'\s*```$', '', resp)
                parsed = json.loads(resp)
                if isinstance(parsed, list):
                    searches = parsed
                    print(f"  [Auto] Generated {len(searches)} search queries")
            except:
                pass
        if not searches:
            searches = [title + " 2026", title + " analysis report"]
            print(f"  [Fallback] Using {len(searches)} default searches")

    # Step 0: 发现层
    discovery_query = f"{title} 2026 完整供应商名单 对比"
    print(f"  [Discovery] {discovery_query[:50]}...")
    disc_result = registry.call("deep_research", discovery_query)
    if disc_result.get("success") and len(disc_result.get("data", "")) > 200:
        discover_prompt = (
            f"以下是关于「{title}」的搜索结果。\n"
            f"我们正在做智能骑行头盔项目的研究。\n\n"
            f"请提取与头盔/声学/光学/通讯/电池/芯片/ODM/JDM 相关的公司/品牌/产品。\n"
            f"严格排除无关公司。\n"
            f"输出 JSON 数组，最多 5 个搜索词。\n\n"
            f"{disc_result['data'][:3000]}"
        )
        disc_llm = call_model(get_model_for_task("discovery"), discover_prompt,
                              "只输出 JSON 数组。", "discovery")
        if disc_llm.get("success"):
            resp = disc_llm["response"].strip()
            resp = re.sub(r'^```json\s*', '', resp)
            resp = re.sub(r'\s*```$', '', resp)
            try:
                extra_searches = json.loads(resp)
                if isinstance(extra_searches, list):
                    searches = searches + extra_searches[:5]
                    print(f"  [Discovery] 补充 {len(extra_searches[:5])} 个搜索词")
            except:
                pass

    # === Layer 1: 并发四通道搜索 ===
    all_sources = []
    source_lock = threading.Lock()

    # 展平 searches
    flat_searches = []
    for s in searches:
        if isinstance(s, list):
            flat_searches.extend([str(item) for item in s])
        else:
            flat_searches.append(str(s))
    searches = flat_searches

    hb = ProgressHeartbeat(
        f"深度研究:{title[:20]}",
        total=len(searches),
        feishu_callback=progress_callback,
        log_interval=3, feishu_interval=5, feishu_time_interval=180
    )

    def _search_one_query(i: int, query: str) -> dict:
        source_text = ""
        channel_results = {}

        # === 使用 SearchRouter 替代原有搜索逻辑 ===
        # 原因：Claude Code WebSearch 在 harness 配置下不可用
        # SearchRouter 内部有 sleep(2) 防限流

        # 使用 SearchRouter 获取搜索结果
        router_result = search_router.search(query, language='auto')
        if router_result and len(router_result) > 100:
            source_text = router_result[:5000]
            channel_results["router"] = router_result[:3000]
            print(f"    [{i}] SearchRouter: {len(router_result)} 字")

        # 补充通道：o3-deep-research（深度研究，慢但全面）
        o3_result = call_with_backoff("o3_deep_research", query,
            "Search for technical specifications, patents, and research papers.",
            "deep_research_search")
        if o3_result.get("success") and len(o3_result.get("response", "")) > 200:
            channel_results["o3"] = o3_result["response"][:3000]
        elif "404" in str(o3_result.get("error", "")):
            record_model_404("o3_deep_research")

        # 合并 + 去重
        seen_hashes = set()
        for channel, text in channel_results.items():
            text_hash = hash(text[:200])
            if text_hash in seen_hashes:
                continue
            seen_hashes.add(text_hash)
            if source_text:
                source_text += f"\n--- [{channel}] ---\n"
            source_text += text

        # 最终兜底：如果所有 channel 都失败，返回空
        if not source_text:
            print(f"    [{i}] 全通道失败: {query[:50]}")

        return {"index": i, "query": query, "content": source_text,
                "channels": list(channel_results.keys())}

    print(f"  [L1] 并发四通道搜索 {len(searches)} 个 query...")
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(_search_one_query, i, q): i
                   for i, q in enumerate(searches, 1)}
        for future in as_completed(futures):
            result = future.result()
            if result["content"]:
                with source_lock:
                    all_sources.append({
                        "query": result["query"],
                        "content": result["content"][:6000]
                    })
                hb.tick(detail=result["query"][:40], success=True)
            else:
                hb.tick(detail=f"失败: {result['query'][:40]}", success=False)

    hb.finish(f"搜索完成，{len(all_sources)}/{len(searches)} 有效")

    # W1: 记录搜索效果
    try:
        learning_path = Path(__file__).resolve().parent.parent.parent / ".ai-state" / "search_learning.jsonl"
        learning_path.parent.mkdir(parents=True, exist_ok=True)
        for src in all_sources:
            with open(learning_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps({
                    "query": str(src.get("query", ""))[:200],
                    "task": title,
                    "chars_returned": len(src.get("content", "")),
                    "timestamp": time.strftime('%Y-%m-%d %H:%M')
                }, ensure_ascii=False) + "\n")
        print(f"  [W1] 搜索学习已记录: {len(all_sources)} 条")
    except Exception as e:
        print(f"  [W1] 学习记录失败: {e}")

    if not all_sources:
        record_search_empty()
        night_watch_diagnose("L1_搜索", f"全部搜索失败，{len(searches)} 个查询无结果",
                             f"任务: {title}")
        return f"# {title}\n\n调研失败：所有搜索均无结果"

    # === Layer 2: 并发结构化提炼 ===
    print(f"  [L2] 并发提炼 {len(all_sources)} 条...")
    structured_data_list = []
    struct_lock = threading.Lock()
    task_type_hint = task.get("goal", "") + " " + title

    def _extract_one(src: dict) -> dict:
        return extract_structured_data(
            raw_text=src["content"], task_type=task_type_hint, topic=src["query"])

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(_extract_one, src): src for src in all_sources}
        for future in as_completed(futures):
            extracted = future.result()
            record_l2_result(bool(extracted))
            if extracted:
                with struct_lock:
                    structured_data_list.append(extracted)

    print(f"  [L2] 提炼完成: {len(structured_data_list)}/{len(all_sources)} 成功")

    if not structured_data_list and all_sources:
        night_watch_diagnose("L2_提炼",
            f"全部提炼失败，{len(all_sources)} 条搜索结果无法提取",
            f"任务: {title}")

    structured_dump = json.dumps(structured_data_list, ensure_ascii=False, indent=2) if structured_data_list else ""

    # KB 上下文
    kb_context = ""
    internal_context = ""
    keywords = title.split() + goal.split()[:5]
    kb_entries = []
    for f in KB_ROOT.rglob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            content = data.get("content", "")
            t = data.get("title", "")
            tags = data.get("tags", [])
            source = data.get("source", "")
            confidence = data.get("confidence", "")

            is_internal = (
                "internal" in tags or "prd" in tags or "product_definition" in tags
                or "anchor" in tags or "user_upload" in source
                or confidence == "authoritative"
            )

            matched = any(kw in t or kw in content[:300] for kw in keywords)
            if not matched:
                matched = any(kw in t or kw in content[:200] for kw in [
                    "歌尔", "Goertek", "立讯", "Luxshare", "JDM", "ODM",
                    "光波导", "waveguide", "MEMS", "骨传导", "BOM", "供应商",
                    "光学", "声学", "摄像头", "模组", "PRD", "产品定义"
                ])
            if matched:
                kb_entries.append({"title": t, "content": content, "is_internal": is_internal})
        except:
            continue

    kb_entries.sort(key=lambda x: -x["is_internal"])
    for entry in kb_entries[:10]:
        if entry["is_internal"]:
            internal_context += f"\n[内部产品定义] {entry['title']}:\n{entry['content'][:2000]}\n"
        else:
            kb_context += f"\n[KB] {entry['title']}: {entry['content'][:300]}"
    kb_context = (internal_context + kb_context)[:5000]

    # === Layer 3: Agent 并行分析 ===
    # CPO 判断角色
    role_prompt = (
        f"你是智能骑行头盔项目的CPO。\n任务：{title}\n目标：{goal}\n\n"
        f"判断需要哪些角色参与: CTO/CMO/CDO\n"
        f"默认全部三个。只输出 JSON 数组。"
    )
    role_result = call_model(get_model_for_task("role_assign"), role_prompt,
                             "只输出 JSON 数组。", "role_assign")
    roles = ["CTO", "CMO", "CDO"]
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

    # 产品锚点
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

    anchor_instruction = (
        f"\n\n## 产品定义锚点（不可违背）\n"
        f"以下是用户已确定的产品定义，你的分析必须在此框架内。\n"
        f"可以建议分阶段（V1/V2），但不能替用户更换产品品类。\n\n"
        f"{product_anchor[:2500] if product_anchor else '无内部产品定义文档。'}\n"
    )

    # 专家框架
    expert_fw = match_expert_framework(goal, title)
    expert_injection = ""
    if expert_fw.get("role"):
        expert_injection += f"\n## 你的专家背景\n{expert_fw['role']}\n"
    for key, label in [("known_pitfalls", "已知陷阱"), ("evaluation_criteria", "评估标准")]:
        items = expert_fw.get(key, [])
        if items:
            expert_injection += f"\n## {label}\n"
            for i, item in enumerate(items, 1):
                expert_injection += f"{i}. {item}\n"

    distilled_material = structured_dump[:8000] if structured_dump else ""
    kb_material = kb_context[:2000]

    # 构建 Agent prompts
    agent_prompts = {
        "CTO": (
            f"你是智能骑行头盔项目的技术合伙人（CTO）。\n"
            f"{expert_injection}\n"
            f"## 调研数据\n{distilled_material}\n\n## 已有知识库\n{kb_material}\n\n"
            f"{anchor_instruction}\n{THINKING_PRINCIPLES}\n"
            f"## 研究任务\n{title}\n## 目标\n{goal}\n\n"
            f"从技术角度分析。要求：参数对比、可行性评估、明确推荐、标注不确定项、1000-1500字\n"
            f"{CAPABILITY_GAP_INSTRUCTION}",
            "你是资深技术合伙人。"
        ),
        "CMO": (
            f"你是智能骑行头盔项目的市场合伙人（CMO）。\n"
            f"{expert_injection}\n"
            f"## 调研数据\n{distilled_material}\n\n## 已有知识库\n{kb_material}\n\n"
            f"{anchor_instruction}\n{THINKING_PRINCIPLES}\n"
            f"## 研究任务\n{title}\n## 目标\n{goal}\n\n"
            f"从市场和商业角度分析。要求：竞品、用户需求、定价、明确判断、1000-1500字\n"
            f"{CAPABILITY_GAP_INSTRUCTION}",
            "你是资深市场合伙人。"
        ),
        "CDO": (
            f"你是智能骑行头盔项目的设计合伙人（CDO）。\n"
            f"{expert_injection}\n"
            f"## 调研数据\n{distilled_material}\n\n## 已有知识库\n{kb_material}\n\n"
            f"{anchor_instruction}\n{THINKING_PRINCIPLES}\n"
            f"## 研究任务\n{title}\n## 目标\n{goal}\n\n"
            f"从产品设计和用户体验角度分析。要求：形态约束、设计取舍、800-1200字\n"
            f"{CAPABILITY_GAP_INSTRUCTION}",
            "你是资深设计合伙人。"
        ),
    }

    agent_outputs = {}
    agent_lock = threading.Lock()

    def _run_agent(role: str) -> tuple:
        prompt, sys_prompt = agent_prompts[role]
        prompt = get_agent_prompt_with_lessons(role, prompt)
        model = get_model_for_role(role)
        result = call_with_backoff(model, prompt, sys_prompt,
                                   f"deep_research_{role.lower()}")
        if result.get("success"):
            return (role, result["response"])
        return (role, None)

    print(f"  [L3] 并行运行 {len(roles)} 个 Agent...")
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(_run_agent, role): role for role in roles}
        for future in as_completed(futures):
            role, output = future.result()
            if output:
                with agent_lock:
                    agent_outputs[role] = output
                print(f"  [{role}] {len(output)} chars")
            else:
                print(f"  [{role}] ❌ failed")

    # 元能力层
    if agent_outputs:
        all_gaps = []
        for role, output in agent_outputs.items():
            gaps = scan_capability_gaps(output)
            for g in gaps:
                g["source_agent"] = role
            all_gaps.extend(gaps)

        if all_gaps:
            resolved_tools = resolve_all_gaps(all_gaps, gateway, max_resolve=3)
            if resolved_tools:
                print(f"  [Meta] 补齐 {len(resolved_tools)} 个能力")

    # Agent 辩论
    if len(agent_outputs) >= 2:
        agent_outputs = _run_agent_debate(agent_outputs, goal, distilled_material)

    if not agent_outputs:
        night_watch_diagnose("L3_Agent", f"全部 Agent 分析失败", f"任务: {title}")
        fallback = call_model("gpt_5_4",
            f"## 研究任务\n{title}\n## 目标\n{goal}\n## 知识库\n{kb_material}\n"
            f"写一份 2000-3000 字的研究报告。",
            "你是资深研发顾问。", "deep_research_fallback")
        report = fallback.get("response", "报告生成失败") if fallback.get("success") else "报告生成失败"
    else:
        # === Layer 4: CPO 整合 ===
        agent_section = ""
        for role, output in agent_outputs.items():
            agent_section += f"\n\n### {role} 分析\n{output}"

        synthesis_prompt = (
            f"你是智能骑行头盔项目的高级技术整合分析师。\n\n"
            f"{THINKING_PRINCIPLES}\n"
            f"## 研究任务\n{title}\n## 目标\n{goal}\n\n"
            f"## 团队各视角分析\n{agent_section}\n\n"
            f"## 输出要求\n"
            f"一、数据对比表（含来源和confidence）\n"
            f"二、候选方案（2-3个，量化pros/cons）\n"
            f"三、关键分歧点（不超过5个）\n"
            f"四、需要决策者判断的问题（3-5个）\n"
            f"五、数据缺口\n\n"
            f"你不要替用户做最终选择。"
        )

        synthesis_result = call_model(get_model_for_task("synthesis"), synthesis_prompt,
            "你是产品VP，整合团队分析并裁决。", "deep_research_synthesis")

        if not synthesis_result.get("success"):
            retry_prompt = (
                f"请整合以下团队分析，写一份 2000-3000 字的研究报告。\n"
                f"任务：{title}\n目标：{goal}\n\n{agent_section[:8000]}"
            )
            retry_result = call_model(get_model_for_task("synthesis"), retry_prompt,
                "整合团队分析。", "synthesis_retry")
            if retry_result.get("success"):
                report = retry_result["response"]
            else:
                synthesis_model = get_model_for_task("synthesis")
                watch_result = night_watch_diagnose(
                    "L4_整合", f"整合失败", f"任务: {title}",
                    retry_fn=call_model,
                    retry_args={"model_name": synthesis_model, "prompt": retry_prompt,
                                "system_prompt": "整合团队分析。", "task_type": "synthesis_retry_v2"}
                )
                if watch_result.get("retry_result", {}).get("success"):
                    report = watch_result["retry_result"]["response"]
                else:
                    longest_role = max(agent_outputs.keys(), key=lambda r: len(agent_outputs[r]))
                    report = agent_outputs[longest_role]
        else:
            report = synthesis_result["response"]

    # === Layer 4.5: 护栏 ===
    try:
        from scripts.guardrail_engine import check_guardrails
        triggered = check_guardrails(report, source="deep_research")
        if triggered:
            for g in triggered[:3]:
                if g.get("action") == "warn":
                    report += f"\n\n⚠️ **注意**: {g.get('message', '')}"
    except ImportError:
        pass

    # === Layer 5: Critic ===
    report = run_critic_challenge(report, goal, agent_outputs,
        structured_data=structured_dump,
        progress_callback=progress_callback, task_title=title)

    # 保存报告
    report_path = REPORT_DIR / f"{task_id}_{time.strftime('%Y%m%d_%H%M')}.md"
    report_path.write_text(
        f"# {title}\n\n> 目标: {goal}\n> 生成时间: {time.strftime('%Y-%m-%d %H:%M')}\n"
        f"> 来源数: {len(all_sources)}\n\n{report}",
        encoding="utf-8")
    print(f"\n[Saved] {report_path}")

    # 完整报告入 KB
    try:
        from src.tools.knowledge_base import add_report
        add_report(title=f"[研究报告] {title}", domain="components",
            content=report, tags=["deep_research", "report", task_id],
            source=f"deep_research:{task_id}", confidence="high")
    except Exception as e:
        print(f"  [KB Report] {e}")

    # C-5: 回流决策树
    try:
        import yaml as _yaml
        dt_path = Path(__file__).resolve().parent.parent.parent / ".ai-state" / "product_decision_tree.yaml"
        if dt_path.exists():
            dt = _yaml.safe_load(dt_path.read_text(encoding='utf-8'))
            report_lower = (report or "").lower()
            for d in dt.get("decisions", []):
                q = d.get("question", "")
                kws = [w for w in q.replace("？", "").replace("?", "").split() if len(w) > 1]
                match_count = sum(1 for kw in kws if kw.lower() in report_lower)
                if match_count >= 2:
                    d["resolved_knowledge"] = d.get("resolved_knowledge", 0) + 1
                    print(f"  [DecisionTree] {d.get('id')}: +1 -> {d['resolved_knowledge']}")
            dt_path.write_text(_yaml.dump(dt, allow_unicode=True, default_flow_style=False),
                               encoding='utf-8')
    except Exception as e:
        print(f"  [DecisionTree] 回流失败: {e}")

    # W3: 模型效果记录
    try:
        meff_path = Path(__file__).resolve().parent.parent.parent / ".ai-state" / "model_effectiveness.jsonl"
        with open(meff_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps({
                "task": title, "report_chars": len(report or ""),
                "sources_count": len(all_sources),
                "timestamp": time.strftime('%Y-%m-%d %H:%M')
            }, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"  [W3] 记录失败: {e}")

    # 知识提取入 KB
    extract_prompt = (
        f"从以下研究报告中提取 3-5 条最有价值的知识条目。\n"
        f"输出 JSON 数组：[{{\"title\": \"标题\", \"domain\": \"components\", "
        f"\"summary\": \"200字摘要\", \"tags\": [\"标签\"]}}]\n\n报告：\n{report[:6000]}"
    )
    extract_result = call_model(get_model_for_task("knowledge_extract"),
        extract_prompt, "只输出 JSON 数组。", "deep_research_extract")

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

                title_text = item.get("title", "")[:80]
                content_text = item.get("summary", "")[:800]

                # 质量过滤
                is_low_quality = False
                if len(content_text) < 150:
                    is_low_quality = True
                has_data = bool(re.search(r'\d+\.?\d*\s*(mm|cm|g|kg|mAh|W|V|Hz|dB|美元|元|USD|\$|%|nits)', content_text))
                has_model = bool(re.search(r'[A-Z]{2,}\d{2,}|IMX\d|QCC\d|BES\d', content_text))
                if not has_data and not has_model:
                    is_low_quality = True
                generic_titles = ["智能头盔", "骑行头盔", "头盔方案", "技术方案", "市场分析"]
                if any(title_text.strip() == g for g in generic_titles):
                    is_low_quality = True

                if is_low_quality:
                    skipped_count += 1
                    continue

                add_knowledge(title=title_text, domain=domain, content=content_text,
                    tags=item.get("tags", []) + ["deep_research", task_id],
                    source=f"deep_research:{task_id}", confidence="high")
                added_count += 1
            print(f"[KB] 提取 {added_count} 条知识，跳过 {skipped_count} 条低质量")
        except:
            print("[KB] 提取失败")

    # 保存关键发现
    save_task_findings(title, report)

    return report
