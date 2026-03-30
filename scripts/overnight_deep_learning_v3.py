# -*- coding: utf-8 -*-
"""
@description: 深度学习 v3 - 广度扫盲 + 精准深挖两阶段
@dependencies: src.utils.model_gateway, src.tools.knowledge_base, src.tools.tool_registry
@last_modified: 2026-03-28
"""
import json
import re
import gc
import sys
import time
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from src.utils.model_gateway import get_model_gateway
from src.tools.knowledge_base import add_knowledge, add_report, get_knowledge_stats, KB_ROOT
from src.tools.tool_registry import get_tool_registry


def log(msg, notify_func=None):
    ts = datetime.now().strftime("%H:%M")
    full = f"[{ts}] {msg}"
    print(full)
    if notify_func:
        try:
            notify_func(full)
        except:
            pass


def phase_done(name, stats, notify_func=None):
    msg = (
        f"Phase A Done: {name}\n"
        f"searched: {stats.get('searched', 0)} | added: {stats.get('added', 0)} | "
        f"skipped: {stats.get('skipped', 0)} | shallow: {stats.get('shallow', 0)} | "
        f"time: {stats.get('minutes', 0):.0f}min"
    )
    print(f"\n{'='*50}\n{msg}\n{'='*50}")
    if notify_func:
        try:
            notify_func(msg)
        except:
            pass


# ==========================================
# Quality Check
# ==========================================
def _quality_check(content: str, title: str) -> dict:
    """Check entry quality, return {pass, reason, is_speculative, has_data}"""

    # Speculative detection
    spec_signals = ["假设", "推测", "推演", "预计将", "可能采用",
                    "尚未公开", "暂无公开", "目前尚无", "理论上可以"]
    is_spec = any(s in content for s in spec_signals)

    # Specific data detection
    has_number = bool(re.search(
        r'\d+\.?\d*\s*(mm|cm|g|kg|mAh|W|V|Hz|dB|USD|\$|%|nits|lux|fps|TOPS|nm|GHz|MB|GB)',
        content
    ))
    has_model = bool(re.search(
        r'[A-Z]{2,}\d{2,}|IMX\d|QCC\d|BES\d|nRF\d|AR[12]|ECE\s*\d|BMI\d|ICM-\d|STM32|ESP32|MT\d{4}',
        content
    ))
    has_brand = bool(re.search(
        r'(Qualcomm|Sony|Bosch|TI|Nordic|Himax|JBD|'
        r'Sena|Cardo|Forcite|LIVALL|EyeRide|CrossHelmet|GoPro|Insta360|'
        r'TUV|DEKRA|SGS|Intertek|UL|BV)',
        content
    ))

    has_data = has_number or has_model or has_brand

    # Length check
    too_short = len(content) < 300

    # Verdict
    if too_short:
        return {"pass": False, "reason": "content too short(<300)", "is_speculative": is_spec, "has_data": has_data}
    if is_spec and not has_data:
        return {"pass": False, "reason": "pure speculation no data", "is_speculative": True, "has_data": False}
    if not has_data and not is_spec:
        return {"pass": True, "reason": "no data but not speculative", "is_speculative": False, "has_data": False, "shallow": True}

    return {"pass": True, "reason": "OK", "is_speculative": is_spec, "has_data": has_data, "shallow": False}


# ==========================================
# Phase A: Breadth Scan
# ==========================================
def _breadth_search_one(topic, registry):
    """Breadth mode: single topic quick search"""
    title = topic["title"]
    searches = topic.get("searches", [])

    search_data = ""
    def _do(q):
        r = registry.call("deep_research", q)
        if r.get("success") and len(r.get("data", "")) > 200:
            return r["data"][:3000]
        return ""

    with ThreadPoolExecutor(max_workers=3) as pool:
        futs = {pool.submit(_do, q): q for q in searches[:3]}
        for f in as_completed(futs):
            d = f.result()
            if d:
                search_data += f"\n---\n{d}"

    return {"topic": topic, "search_data": search_data, "search_len": len(search_data)}


def _breadth_refine_one(topic, search_data, gateway):
    """Breadth mode: single refinement"""
    title = topic["title"]
    domain = topic.get("domain", "components")
    tags = topic.get("tags", [])

    if len(search_data) < 300:
        return {"success": False, "title": title, "reason": "insufficient search", "quality": None}

    prompt = (
        f"Based on the following search results, output a knowledge entry about '{title}'.\n"
        f"Must include specific data (models, parameters, prices, brand names).\n"
        f"If no specific data found, mark 'not found', do not fabricate.\n"
        f"Output 400-800 words.\n\n"
        f"Search results:\n{search_data[:4000]}"
    )

    result = gateway.call_azure_openai("cpo", prompt,
        "Output detailed knowledge entry with specific data.", "deep_learn_refine")

    if not result.get("success") or len(result.get("response", "")) < 200:
        return {"success": False, "title": title, "reason": "refine failed", "quality": None}

    content = result["response"]
    quality = _quality_check(content, title)

    # Store in KB
    final_tags = tags.copy()
    if quality["is_speculative"]:
        final_tags.append("speculative")
    if quality.get("shallow"):
        final_tags.append("shallow_breadth")

    # 修复 3: 默认使用 medium，避免 KB_GUARD 降级噪声
    # 只有 speculative 才用 low，其他一律 medium
    confidence = "low" if quality["is_speculative"] else "medium"

    if quality["pass"]:
        add_knowledge(
            title=title,
            domain=domain,
            content=content[:1500],
            tags=final_tags + ["breadth_v3"],
            source="overnight_deep_v3_breadth",
            confidence=confidence
        )

    return {
        "success": quality["pass"],
        "title": title,
        "reason": quality["reason"],
        "quality": quality,
        "content_len": len(content),
        "has_data": quality["has_data"],
        "is_speculative": quality["is_speculative"],
        "shallow": quality.get("shallow", False)
    }


def run_phase_a(topics, notify_func=None):
    """Phase A: Breadth Scan"""
    start = time.time()
    log(f"Phase A: Breadth scan starting ({len(topics)} topics)", notify_func)

    registry = get_tool_registry()
    gateway = get_model_gateway()

    # Parallel search
    log("  Stage A1: Parallel searching (4 workers)...")
    search_results = []
    done = 0

    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = {pool.submit(_breadth_search_one, t, registry): t for t in topics}
        for f in as_completed(futs):
            search_results.append(f.result())
            done += 1
            if done % 10 == 0:
                print(f"  Search progress: {done}/{len(topics)}")

    log(f"  Search complete: {len(search_results)}/{len(topics)}")

    # Serial refinement
    log("  Stage A2: Serial refinement...")
    results = []
    added = 0
    skipped = 0
    shallow = 0
    speculative = 0

    for i, item in enumerate(search_results, 1):
        topic = item["topic"]
        search_data = item["search_data"]

        result = _breadth_refine_one(topic, search_data, gateway)
        results.append(result)

        if result["success"]:
            added += 1
            if result.get("shallow"):
                shallow += 1
                print(f"  [{i}/{len(search_results)}] {result['title'][:40]} -- shallow(no data)")
            elif result.get("is_speculative"):
                speculative += 1
                print(f"  [{i}/{len(search_results)}] {result['title'][:40]} -- speculative")
            else:
                print(f"  OK [{i}/{len(search_results)}] {result['title'][:40]} ({result.get('content_len', 0)} chars)")
        else:
            skipped += 1
            print(f"  SKIP [{i}/{len(search_results)}] {result['title'][:40]} -- {result['reason']}")

        if i % 20 == 0:
            gc.collect()

    minutes = (time.time() - start) / 60
    stats = {
        "searched": len(topics), "added": added, "skipped": skipped,
        "shallow": shallow, "speculative": speculative, "minutes": minutes
    }
    phase_done("Phase A: Breadth Scan", stats, notify_func)

    gc.collect()
    return results, stats


# ==========================================
# Auto-select Weak Topics
# ==========================================
def _select_deep_dive_topics(breadth_results, topics, max_count=25):
    """Select topics needing deep dive from breadth results"""

    candidates = []

    for result in breadth_results:
        score = 0
        title = result["title"]

        # Find matching original topic
        topic = None
        for t in topics:
            if t["title"] == title:
                topic = t
                break

        if not topic:
            continue

        # Score: higher means more need for deep dive
        if not result["success"]:
            score += 10  # Complete failure, needs deep dive most
        elif result.get("shallow"):
            score += 8   # Shallow entry, missing data
        elif result.get("is_speculative"):
            score += 6   # Speculative, needs verification
        elif not result.get("has_data"):
            score += 5   # No specific data
        else:
            score += 1   # Has data, low priority

        # Core domain bonus (these are more important)
        core_tags = {"bom", "cost", "thermal", "power", "certification", "voice",
                     "hw_teardown", "market_data", "user_research"}
        if any(tag in topic.get("tags", []) for tag in core_tags):
            score += 3

        # Custom refine_prompt means complex topic
        if topic.get("refine_prompt"):
            score += 2

        candidates.append({
            "topic": topic,
            "score": score,
            "reason": result.get("reason", ""),
            "breadth_quality": result.get("quality", {})
        })

    # Sort by score, take top max_count
    candidates.sort(key=lambda x: -x["score"])
    selected = candidates[:max_count]

    print(f"\n[DeepDive] Selected {len(selected)} topics for deep dive from {len(breadth_results)} breadth results:")
    for i, c in enumerate(selected, 1):
        print(f"  {i}. [score:{c['score']}] {c['topic']['title'][:50]} -- {c['reason']}")

    return selected


def _generate_extension_topics(gateway, existing_topics: set, count: int = 30) -> list:
    """
    基于当前知识库的薄弱环节，自动生成延伸学习主题（新机制）
    """
    extension_strategies = [
        {
            "name": "竞品纵深",
            "prompt": """基于以下已有知识主题列表，找出尚未覆盖的竞品分析角度。
重点关注：
1. 已有品牌（Sena/Cardo/LIVALL/Forcite/CrossHelmet）的未覆盖维度（售后/定价/渠道/用户评价）
2. 尚未研究的竞品品牌（Ruroc/Bell/Schuberth/Nolan 的智能化尝试）
3. 跨行业参考（滑雪头盔/自行车头盔/工业安全帽的智能化）

输出具体研究主题，每行一个，不要编号。"""
        },
        {
            "name": "技术深挖",
            "prompt": """基于以下已有知识主题列表，找出技术领域的盲区。
重点关注：
1. 已有技术条目中提到但未展开的子技术（如"BLE GATT"提到了但没有详细协议设计）
2. 产品目标要求但知识库尚未覆盖的技术（4G/5G蜂窝、疲劳检测、全彩HUD、可换电池）
3. 制造工艺细节（注塑/喷涂/装配/检测工序）

输出具体研究主题，每行一个，不要编号。"""
        },
        {
            "name": "用户场景",
            "prompt": """基于以下已有知识主题列表，找出用户研究和场景设计的盲区。
重点关注：
1. 极端场景（暴雨/夜间/隧道/高原/严寒）下的产品行为
2. 特殊用户群体（女性骑手/新手/外卖骑手/赛道用户）
3. 用户旅程中未覆盖的环节（购买决策/开箱/学习曲线/维修/二手转卖）

输出具体研究主题，每行一个，不要编号。"""
        }
    ]

    # 获取现有知识主题列表（用于去重和找盲区）
    existing_titles = '\n'.join(list(existing_topics)[:200])

    all_new_topics = []
    for strategy in extension_strategies:
        prompt = strategy["prompt"] + f"\n\n已有主题列表:\n{existing_titles}"

        try:
            result = gateway.call_azure_openai("cpo", prompt,
                "输出研究主题列表，每行一个。", "generate_extension_topics", max_tokens=1500)

            if result.get("success"):
                response = result.get("response", "")
                topics = [line.strip() for line in response.split('\n') if line.strip() and len(line.strip()) > 5]
                # 去重
                topics = [t for t in topics if t not in existing_topics]
                all_new_topics.extend(topics)
                print(f"  [AutoExtend] {strategy['name']}: 生成 {len(topics)} 个新主题")
        except Exception as e:
            print(f"  [AutoExtend] {strategy['name']} 生成失败: {e}")

    return all_new_topics[:count]


# ==========================================
# Phase B: Precision Deep Dive
# ==========================================
def _deep_search_one(topic_info, registry):
    """Depth mode: multi-round multi-angle search"""
    topic = topic_info["topic"]
    title = topic["title"]
    base_searches = topic.get("searches", [])

    all_data = ""
    sources_count = 0

    # Round 1: Original search terms (mainly Chinese)
    def _do(q):
        r = registry.call("deep_research", q)
        if r.get("success") and len(r.get("data", "")) > 200:
            return r["data"][:4000]
        return ""

    with ThreadPoolExecutor(max_workers=3) as pool:
        futs = {pool.submit(_do, q): q for q in base_searches[:3]}
        for f in as_completed(futs):
            d = f.result()
            if d:
                all_data += f"\n---[Round1]---\n{d}"
                sources_count += 1

    # Round 2: English supplementary search
    en_queries = [
        f"{title} specifications datasheet 2025 2026",
        f"{title} comparison benchmark review",
    ]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futs = {pool.submit(_do, q): q for q in en_queries}
        for f in as_completed(futs):
            d = f.result()
            if d:
                all_data += f"\n---[Round2-EN]---\n{d}"
                sources_count += 1

    # Round 3: Industry report/academic search
    report_queries = [
        f"{title} market report industry analysis forecast",
        f"{title} industry report whitepaper research data",
    ]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futs = {pool.submit(_do, q): q for q in report_queries}
        for f in as_completed(futs):
            d = f.result()
            if d:
                all_data += f"\n---[Round3-Report]---\n{d}"
                sources_count += 1

    return {
        "topic_info": topic_info,
        "search_data": all_data,
        "sources_count": sources_count
    }


def _deep_refine_chunked(topic_info, search_data, sources_count, gateway):
    """
    三步精炼：框架 → 逐段填充 → 合并
    每步 max_tokens <= 2000，避免截断（修复 80% 失败的根因）
    """
    topic = topic_info["topic"]
    title = topic["title"]
    domain = topic.get("domain", "components")
    tags = topic.get("tags", [])
    custom_prompt = topic.get("refine_prompt", "")

    if len(search_data) < 500:
        return {"success": False, "title": title, "reason": f"insufficient search(only {sources_count} sources)"}

    # === Step 1: 生成框架（要点骨架） ===
    framework_prompt = f"""你是智能骑行头盔领域的高级研究员。
针对主题「{title}」，基于以下搜索数据，输出一份结构化框架。

要求：
- 列出 3-5 个核心要点（每个要点一行，格式: "## 要点N: 标题"）
- 每个要点下列出需要填充的关键数据项（格式: "- 数据项: [待填充]"）
- 不要展开写正文，只给骨架
- 总输出控制在 500 字以内

搜索数据:
{search_data[:3000]}
"""

    framework_result = gateway.call_azure_openai("cpo", framework_prompt,
        "只输出框架，不要正文。", "deep_refine_framework", max_tokens=1500)

    framework = framework_result.get("response", "") if framework_result.get("success") else ""

    if not framework or len(framework) < 100:
        print(f"  [DeepRefine] {title}: 框架生成失败，退回单步模式")
        # Fallback: use original single-step method with reduced tokens
        return _deep_refine_single(topic_info, search_data, sources_count, gateway, custom_prompt)

    # === Step 2: 逐要点展开 ===
    sections = re.findall(r'##\s*要点\d+[：:]\s*(.+)', framework)
    if not sections:
        # 兜底：按换行分段
        sections = [line.strip() for line in framework.split('\n') if line.strip() and len(line.strip()) > 5][:5]

    filled_sections = []
    for i, section_title in enumerate(sections):
        fill_prompt = f"""你是智能骑行头盔领域的高级研究员。
针对主题「{title}」的子要点「{section_title}」，基于搜索数据写一段详细分析。

要求：
- 必须包含具体数字/型号/参数（不能只有定性描述）
- 引用数据时标注来源
- 输出 200-400 字
- 直接输出正文，不要重复标题

搜索数据:
{search_data[:3000]}

整体框架（参考上下文）:
{framework[:1000]}
"""

        section_result = gateway.call_azure_openai("cpo", fill_prompt,
            "直接输出正文内容。", "deep_refine_fill", max_tokens=1500)

        section_content = section_result.get("response", "") if section_result.get("success") else ""

        if section_content and len(section_content) > 50:
            filled_sections.append(f"## {section_title}\n{section_content}")
        else:
            print(f"  [DeepRefine] {title} 要点 {i+1}/{len(sections)} 填充失败，跳过")

    if not filled_sections:
        print(f"  [DeepRefine] {title}: 所有要点填充失败，退回单步模式")
        return _deep_refine_single(topic_info, search_data, sources_count, gateway, custom_prompt)

    # === Step 3: 合并成完整条目 ===
    merged = f"# {title}\n\n" + "\n\n".join(filled_sections)

    # 可选：最终做一次精简合并（如果段落间有重复）
    if len(filled_sections) >= 3:
        merge_prompt = f"""将以下分段内容合并为一篇连贯的知识条目。
- 去除重复内容
- 保留所有具体数据和来源
- 输出 800-1500 字
- confidence 标记为 medium

{merged[:4000]}
"""
        final_result = gateway.call_azure_openai("cpo", merge_prompt,
            "输出合并后的知识条目。", "deep_refine_merge", max_tokens=2000)

        content = final_result.get("response", "") if final_result.get("success") else ""
        if not content or len(content) < 300:
            content = merged
    else:
        content = merged

    # Quality check and store
    quality = _quality_check(content, title)

    final_tags = tags.copy() + ["depth_v3"]
    if quality["is_speculative"]:
        final_tags.append("speculative")

    confidence = "medium"  # Default to medium (修复 3)

    # Delete matching breadth entry first
    for f in KB_ROOT.rglob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if data.get("title") == title and "breadth_v3" in data.get("tags", []):
                f.unlink()
                break
        except:
            continue

    add_knowledge(
        title=f"[Deep] {title}",
        domain=domain,
        content=content[:3000],
        tags=final_tags,
        source="overnight_deep_v3_depth",
        confidence=confidence
    )

    return {
        "success": True,
        "title": title,
        "content_len": len(content),
        "sources": sources_count,
        "has_data": quality["has_data"],
        "is_speculative": quality["is_speculative"],
        "method": "chunked"
    }


def _deep_refine_single(topic_info, search_data, sources_count, gateway, custom_prompt=""):
    """Fallback: 原有的单步精炼（max_tokens=2000 避免截断）"""
    topic = topic_info["topic"]
    title = topic["title"]
    domain = topic.get("domain", "components")
    tags = topic.get("tags", [])

    if custom_prompt:
        final_prompt = custom_prompt.format(search_data=search_data[:5000], title=title)
    else:
        final_prompt = (
            f"Based on the following search data, output a knowledge entry about '{title}'.\n\n"
            f"Requirements:\n"
            f"1. Start with one sentence summarizing the core conclusion\n"
            f"2. Organize by dimensions (technical params/market data/competitor comparison)\n"
            f"3. Mark source credibility for each data point\n"
            f"4. Output 800-1200 words\n"
            f"5. confidence 一律标 medium\n\n"
            f"Search data:\n{search_data[:5000]}"
        )

    result = gateway.call_azure_openai("cpo", final_prompt,
        "Output knowledge entry.", "deep_learn_deep_refine", max_tokens=2000)

    if not result.get("success") or len(result.get("response", "")) < 300:
        return {"success": False, "title": title, "reason": "deep refine failed"}

    content = result["response"]
    quality = _quality_check(content, title)

    final_tags = tags.copy() + ["depth_v3"]
    if quality["is_speculative"]:
        final_tags.append("speculative")

    add_knowledge(
        title=f"[Deep] {title}",
        domain=domain,
        content=content[:3000],
        tags=final_tags,
        source="overnight_deep_v3_depth",
        confidence="medium"
    )

    return {
        "success": True,
        "title": title,
        "content_len": len(content),
        "sources": sources_count,
        "has_data": quality["has_data"],
        "is_speculative": quality["is_speculative"],
        "method": "single"
    }


def _deep_refine(topic_info, search_data, sources_count, gateway):
    """Depth mode: 使用三步精炼替代原有单次调用（修复 80% 失败问题）"""
    # 直接调用三步法
    return _deep_refine_chunked(topic_info, search_data, sources_count, gateway)


def run_phase_b(selected_topics, notify_func=None):
    """Phase B: Precision Deep Dive"""
    start = time.time()
    total = len(selected_topics)
    log(f"Phase B: Precision deep dive starting ({total} topics, 3-round search + 2-step refine each)", notify_func)

    registry = get_tool_registry()
    gateway = get_model_gateway()

    added = 0
    skipped = 0

    # Batch process: 5 parallel search, serial refine
    batch_size = 5
    for batch_start in range(0, total, batch_size):
        batch = selected_topics[batch_start:batch_start + batch_size]
        batch_num = batch_start // batch_size + 1
        total_batches = (total + batch_size - 1) // batch_size

        log(f"  Batch {batch_num}/{total_batches}: parallel search {len(batch)} topics...")

        # Parallel search
        search_results = []
        with ThreadPoolExecutor(max_workers=4) as pool:
            futs = {pool.submit(_deep_search_one, t, registry): t for t in batch}
            for f in as_completed(futs):
                search_results.append(f.result())

        # Serial refinement
        for item in search_results:
            topic_info = item["topic_info"]
            title = topic_info["topic"]["title"]

            result = _deep_refine(topic_info, item["search_data"], item["sources_count"], gateway)

            if result["success"]:
                added += 1
                spec_mark = " [speculative]" if result.get("is_speculative") else ""
                print(f"  OK [{added+skipped}/{total}] {title[:45]} "
                      f"({result['content_len']} chars, {result['sources']} sources){spec_mark}")
            else:
                skipped += 1
                print(f"  FAIL [{added+skipped}/{total}] {title[:45]} -- {result['reason']}")

            time.sleep(2)  # Rate control

        gc.collect()

        # Report progress every 2 batches
        if notify_func and batch_num % 2 == 0:
            try:
                notify_func(f"Phase B progress: {added+skipped}/{total}, added {added}")
            except:
                pass

    minutes = (time.time() - start) / 60
    stats = {"searched": total, "added": added, "skipped": skipped, "shallow": 0, "minutes": minutes}
    phase_done("Phase B: Precision Deep Dive", stats, notify_func)
    gc.collect()
    return stats


# ==========================================
# Topic List (reuse v2's 109 topics)
# ==========================================
def _load_all_topics():
    """Load all topics (import from v2 or redefine)"""
    try:
        # Try importing from v2
        from scripts.overnight_deep_learning_v2 import (
            PHASE1_TOPICS, PHASE2_TOPICS, PHASE3_TOPICS, PHASE4_TOPICS,
            PHASE5_TOPICS, PHASE6_TOPICS, PHASE7_TOPICS, PHASE8_TOPICS,
            PHASE9_TOPICS, PHASE10_TOPICS, PHASE11_TOPICS, PHASE12_TOPICS,
            PHASE13_TOPICS
        )
        all_topics = (
            PHASE1_TOPICS + PHASE2_TOPICS + PHASE3_TOPICS + PHASE4_TOPICS +
            PHASE5_TOPICS + PHASE6_TOPICS + PHASE7_TOPICS + PHASE8_TOPICS +
            PHASE9_TOPICS + PHASE10_TOPICS + PHASE11_TOPICS + PHASE12_TOPICS +
            PHASE13_TOPICS
        )
        return all_topics
    except ImportError:
        print("[Warning] Cannot import v2 topics, using empty list")
        return []


# ==========================================
# Main Flow
# ==========================================
def run_all(notify_func=None, deep_count=25, target_hours=7.0):
    start = time.time()
    start_stats = get_knowledge_stats()
    start_total = sum(start_stats.values())

    topics = _load_all_topics()

    log(f"{'#'*60}", notify_func)
    log(f"# Deep Learning v3 Starting (Two-Phase Mode)", notify_func)
    log(f"# Knowledge Base: {start_total} entries", notify_func)
    log(f"# Breadth Topics: {len(topics)}", notify_func)
    log(f"# Deep Dive Count: {deep_count} (auto-selected)", notify_func)
    log(f"{'#'*60}", notify_func)

    # Phase A: Breadth Scan
    breadth_results, a_stats = run_phase_a(topics, notify_func)
    time.sleep(10)

    # Phase A+: Self-test after breadth scan
    log("Phase A+: Self-test after breadth scan...", notify_func)

    # === 修复 2: 自测前 reload 知识库 ===
    log("[SelfTest] Reloading knowledge base to include new entries...", notify_func)
    try:
        import importlib
        import src.tools.knowledge_base as kb_module
        importlib.reload(kb_module)
        log("[SelfTest] Knowledge base reloaded successfully", notify_func)
    except Exception as reload_err:
        log(f"[SelfTest] Knowledge base reload failed: {reload_err}", notify_func)

    try:
        from scripts.self_test import run_self_test

        test_result = run_self_test(
            topics=[t["title"] for t in topics],
            count=15  # Nighttime can test more questions
        )

        log(f"Self-test result: avg {test_result['avg_score']}/10, "
            f"pass rate {test_result['pass_rate']}%, "
            f"weak areas {len(test_result['weak_areas'])}", notify_func)
    except Exception as e:
        log(f"Self-test failed: {e}", notify_func)
        test_result = {"avg_score": 0, "weak_areas": []}

    # Auto-select weak topics
    selected = _select_deep_dive_topics(breadth_results, topics, max_count=deep_count)

    # Add self-test weak areas to deep dive queue
    # 修复 4: 自测选题逻辑修正 - 混合策略
    self_test_avg = test_result.get("avg_score", 0)

    if self_test_avg < 3.0:
        log(f"[DeepDive] 自测平均分 {self_test_avg} 过低，可能是检索问题，采用混合选题策略", notify_func)
        # 50% 来自自测失败题（仍可能有真盲区）
        failed_topics = test_result.get("weak_areas", [])[:12]
        # 50% 来自广度阶段标记为 shallow/speculative 的条目（确定需要深挖的）
        from_quality = [r for r in breadth_results if r.get("shallow") or r.get("is_speculative")]
        from_quality = sorted(from_quality, key=lambda x: -x.get("score", 0))[:13]

        # 合并选题
        selected = []
        existing_titles = set()
        for weak in failed_topics:
            weak_topic = {
                "title": weak["question"][:80],
                "domain": weak.get("domain", "components"),
                "searches": weak.get("suggested_searches", []),
                "tags": ["self_test_weak"]
            }
            if weak_topic["title"] not in existing_titles:
                existing_titles.add(weak_topic["title"])
                selected.append({
                    "topic": weak_topic,
                    "score": 15,
                    "reason": f"Self-test {weak.get('score', 0)}/10: {weak.get('reason', '')}"
                })

        for r in from_quality:
            title = r.get("title", "")
            if title and title not in existing_titles:
                existing_titles.add(title)
                # Find matching topic
                matching_topic = next((t for t in topics if t["title"] == title), None)
                if matching_topic:
                    selected.append({
                        "topic": matching_topic,
                        "score": 10,
                        "reason": f"Breadth {r.get('reason', 'shallow/speculative')}"
                    })

        # Truncate
        selected = selected[:deep_count]

    elif test_result.get("weak_areas"):
        # 正常逻辑：自测分数正常，主要用自测失败题
        for weak in test_result["weak_areas"]:
            # Build a topic format
            weak_topic = {
                "title": weak["question"][:80],
                "domain": weak.get("domain", "components"),
                "searches": weak.get("suggested_searches", []),
                "tags": ["self_test_weak"]
            }
            # If not already in selected, append
            existing_titles = {s["topic"]["title"] for s in selected}
            if weak_topic["title"] not in existing_titles:
                selected.append({
                    "topic": weak_topic,
                    "score": 15,  # Self-test weak = highest priority deep dive
                    "reason": f"Self-test {weak['score']}/10: {weak['reason']}"
                })

        # Re-sort, self-test weak areas first
        selected.sort(key=lambda x: -x["score"])
        selected = selected[:deep_count]  # Truncate to target count

    if selected:
        log(f"\nSelected {len(selected)} topics for deep dive", notify_func)
    else:
        log(f"\nNo topics need deep dive, all breadth results are high quality", notify_func)

    # Phase B: Precision Deep Dive
    b_stats = {"searched": 0, "added": 0, "skipped": 0, "minutes": 0}
    if selected:
        b_stats = run_phase_b(selected, notify_func)

    # Final Summary
    end_stats = get_knowledge_stats()
    end_total = sum(end_stats.values())
    total_min = (time.time() - start) / 60

    # Quality Audit
    depth_count = 0
    breadth_count = 0
    spec_count = 0
    for f in KB_ROOT.rglob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            tags = data.get("tags", [])
            if "depth_v3" in tags:
                depth_count += 1
            if "breadth_v3" in tags:
                breadth_count += 1
            if "speculative" in tags:
                spec_count += 1
        except:
            continue

    final = (
        f"\n{'#'*60}\n"
        f"# Deep Learning v3 Complete\n"
        f"{'#'*60}\n\n"
        f"Total Time: {total_min:.0f} minutes\n"
        f"Knowledge Base: {start_total} -> {end_total} (+{end_total - start_total})\n\n"
        f"Phase A Breadth Scan:\n"
        f"  Added {a_stats['added']} | Skipped {a_stats['skipped']} | "
        f"Shallow {a_stats.get('shallow', 0)} | Speculative {a_stats.get('speculative', 0)} | "
        f"{a_stats['minutes']:.0f}min\n\n"
        f"Phase B Precision Deep Dive:\n"
        f"  Added {b_stats['added']} | Skipped {b_stats['skipped']} | "
        f"{b_stats.get('minutes', 0):.0f}min\n\n"
        f"Quality Metrics:\n"
        f"  Depth Entries: {depth_count}\n"
        f"  Breadth Entries: {breadth_count}\n"
        f"  Speculative Entries: {spec_count}\n"
    )

    print(final)
    if notify_func:
        try:
            notify_func(final)
        except:
            pass

    # Save Report
    report_dir = Path(__file__).parent.parent / ".ai-state" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / f"deep_learn_v3_{datetime.now().strftime('%Y%m%d_%H%M')}.md").write_text(final, encoding="utf-8")

    # 任务完成提示音
    try:
        import platform
        if platform.system() == "Windows":
            import winsound
            winsound.Beep(1000, 300)
            winsound.Beep(1200, 300)
        else:
            print('\a')  # ASCII bell
    except:
        print('\a')

    # === 新机制: 自动撑满目标时长 ===
    elapsed_hours = (time.time() - start) / 3600
    remaining_hours = target_hours - elapsed_hours

    if remaining_hours >= 0.5:  # 剩余时间 >= 30分钟，启动延伸学习
        log(f"\n[AutoExtend] 提前完成！已用 {elapsed_hours:.1f}h / 目标 {target_hours}h", notify_func)
        log(f"[AutoExtend] 剩余 {remaining_hours:.1f}h，自动启动延伸学习", notify_func)

        if notify_func:
            try:
                notify_func(f"⏰ 提前完成 ({elapsed_hours:.1f}h/{target_hours}h)，自动启动延伸学习")
            except:
                pass

        # 收集已有主题（用于去重）
        existing_topics = set()
        for f in KB_ROOT.rglob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                existing_topics.add(data.get("title", ""))
            except:
                continue

        round_num = 0
        gateway = get_model_gateway()

        while True:
            # 检查剩余时间
            elapsed_hours = (time.time() - start) / 3600
            remaining_hours = target_hours - elapsed_hours

            if remaining_hours < 0.3:  # 少于 18 分钟就收工
                log(f"[AutoExtend] 剩余 {remaining_hours:.1f}h < 0.3h，收工", notify_func)
                break

            round_num += 1
            log(f"\n[AutoExtend] === Round {round_num} (剩余 {remaining_hours:.1f}h) ===", notify_func)

            # 动态决定本轮主题数量
            topics_this_round = min(30, max(10, int(remaining_hours * 20)))

            # 生成延伸主题
            new_topics = _generate_extension_topics(gateway, existing_topics, count=topics_this_round)

            if not new_topics:
                log(f"[AutoExtend] 无法生成更多主题，结束", notify_func)
                break

            log(f"[AutoExtend] 本轮 {len(new_topics)} 个主题", notify_func)

            # 复用 Phase A 的广度扫描流程
            added = 0
            for i, topic_title in enumerate(new_topics):
                # 时间保护
                elapsed_hours = (time.time() - start) / 3600
                if target_hours - elapsed_hours < 0.2:
                    log(f"[AutoExtend] 时间到，停止", notify_func)
                    break

                try:
                    topic = {"title": topic_title, "domain": "components", "tags": ["auto_extend"]}
                    result = _breadth_refine_one(topic, "", gateway)
                    if result.get("success"):
                        added += 1
                        existing_topics.add(topic_title)
                except Exception as e:
                    pass

                # 每 10 个主题输出心跳
                if (i + 1) % 10 == 0:
                    elapsed_hours = (time.time() - start) / 3600
                    log(f"  [AutoExtend] 进度 {i+1}/{len(new_topics)}，已用时 {elapsed_hours:.1f}h", notify_func)

            log(f"[AutoExtend] Round {round_num} 完成: +{added} 条", notify_func)

            # 更新最终统计
            end_stats = get_knowledge_stats()
            end_total = sum(end_stats.values())

            if notify_func:
                try:
                    notify_func(f"✅ 延伸 Round {round_num}: +{added} 条，知识库 {end_total} 条")
                except:
                    pass

            # 每 2 轮做一次自测
            if round_num % 2 == 0:
                log(f"[AutoExtend] 中间自测...", notify_func)
                try:
                    # reload kb
                    import importlib
                    import src.tools.knowledge_base as kb_module
                    importlib.reload(kb_module)

                    from scripts.self_test import run_self_test
                    test_result = run_self_test(topics=list(existing_topics)[:30], count=10)
                    log(f"[AutoExtend] 自测结果: avg {test_result['avg_score']}/10", notify_func)
                except Exception as e:
                    log(f"[AutoExtend] 自测失败: {e}", notify_func)

        # 最终汇报
        elapsed_hours = (time.time() - start) / 3600
        end_stats = get_knowledge_stats()
        end_total = sum(end_stats.values())
        final_extend = (
            f"\n🏁 延伸学习完成\n"
            f"总用时: {elapsed_hours:.1f}h / 目标 {target_hours}h\n"
            f"延伸轮次: {round_num}\n"
            f"知识库: {end_total} 条"
        )
        log(final_extend, notify_func)

    # 更新全局统计（供最终报告使用）
    total_min = (time.time() - start) / 60
    end_stats = get_knowledge_stats()
    end_total = sum(end_stats.values())


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Deep Learning v3 (Two-Phase)")
    parser.add_argument("--all", action="store_true", help="Run all (breadth + depth)")
    parser.add_argument("--breadth-only", action="store_true", help="Only run breadth scan")
    parser.add_argument("--depth-only", type=int, help="Skip breadth, directly deep dive N weak topics")
    parser.add_argument("--deep-count", type=int, default=25, help="Deep dive topic count (default 25)")
    parser.add_argument("--target-hours", type=float, default=7.0,
                        help="目标运行时长（小时），提前完成会自动加活")
    args = parser.parse_args()

    notify = None
    try:
        from scripts.feishu_sdk_client import send_reply
        TARGET = "ou_8e5e4f183e9eca4241378e96bac3a751"
        def feishu_notify(msg):
            try:
                send_reply(TARGET, msg)
            except:
                pass
        notify = feishu_notify
        print("[DeepLearn v3] Feishu notification connected")
    except:
        print("[DeepLearn v3] Feishu notification unavailable")

    if args.all:
        run_all(notify, deep_count=args.deep_count, target_hours=args.target_hours)
    elif args.breadth_only:
        topics = _load_all_topics()
        run_phase_a(topics, notify)
    elif args.depth_only:
        # Find shallow entries from KB and deep dive directly
        topics = _load_all_topics()
        # Simulate breadth results: mark all shallow/speculative as needing deep dive
        fake_results = []
        for t in topics:
            # Check if depth version already exists
            has_depth = False
            for f in KB_ROOT.rglob("*.json"):
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    if t["title"] in data.get("title", "") and "depth_v3" in data.get("tags", []):
                        has_depth = True
                        break
                except:
                    continue

            if not has_depth:
                fake_results.append({
                    "title": t["title"], "success": True,
                    "shallow": True, "has_data": False, "is_speculative": False,
                    "reason": "no depth version"
                })

        selected = _select_deep_dive_topics(fake_results, topics, max_count=args.depth_only)
        if selected:
            run_phase_b(selected, notify)
    else:
        run_all(notify, deep_count=args.deep_count, target_hours=args.target_hours)