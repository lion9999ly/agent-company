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

    confidence = "low" if quality["is_speculative"] else ("medium" if quality.get("shallow") else "high")

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


def _deep_refine(topic_info, search_data, sources_count, gateway):
    """Depth mode: two-step refinement (extract data -> structured output)"""
    topic = topic_info["topic"]
    title = topic["title"]
    domain = topic.get("domain", "components")
    tags = topic.get("tags", [])
    custom_prompt = topic.get("refine_prompt", "")

    if len(search_data) < 500:
        return {"success": False, "title": title, "reason": f"insufficient search(only {sources_count} sources)"}

    # Step 1: Extract key data points
    extract_prompt = (
        f"From the following {sources_count} source search results, extract all specific data points about '{title}'.\n"
        f"Only output data (models, parameters, prices, brands, dates, sources), one per line.\n"
        f"If different sources contradict, list both and mark [conflict].\n"
        f"Max 40 items.\n\n"
        f"Search results:\n{search_data[:6000]}"
    )

    extract_result = gateway.call_azure_openai("cpo", extract_prompt,
        "Only output data points, no analysis.", "deep_learn_extract")

    extracted = extract_result.get("response", "") if extract_result.get("success") else ""

    if len(extracted) < 100:
        # Extraction failed, fallback to single-step refine
        extracted = search_data[:4000]

    # Step 2: Structured output
    if custom_prompt:
        final_prompt = custom_prompt.format(search_data=extracted[:4000], title=title)
    else:
        final_prompt = (
            f"Based on the following extracted data points, output a deep knowledge entry about '{title}'.\n\n"
            f"Requirements:\n"
            f"1. Start with one sentence summarizing the core conclusion\n"
            f"2. Organize by dimensions (e.g., technical params/market data/competitor comparison/cost range/risk points)\n"
            f"3. Mark source credibility for each data point (official/industry report/speculative estimate)\n"
            f"4. If data conflicts, list conflicts and give judgment\n"
            f"5. End with missing key data\n"
            f"6. Output 1500-2500 words\n\n"
            f"Extracted data points:\n{extracted[:4000]}\n\n"
            f"Supplementary search context:\n{search_data[:2000]}"
        )

    result = gateway.call_azure_openai("cpo", final_prompt,
        "Output deep knowledge entry, structured with data support.", "deep_learn_deep_refine",
        max_tokens=4096)

    if not result.get("success") or len(result.get("response", "")) < 500:
        return {"success": False, "title": title, "reason": "deep refine failed"}

    content = result["response"]
    quality = _quality_check(content, title)

    # Store in KB (depth entry replaces breadth entry)
    final_tags = tags.copy() + ["depth_v3"]
    if quality["is_speculative"]:
        final_tags.append("speculative")

    confidence = "low" if quality["is_speculative"] else "high"

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
        "is_speculative": quality["is_speculative"]
    }


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
def run_all(notify_func=None, deep_count=25):
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
    if test_result.get("weak_areas"):
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


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Deep Learning v3 (Two-Phase)")
    parser.add_argument("--all", action="store_true", help="Run all (breadth + depth)")
    parser.add_argument("--breadth-only", action="store_true", help="Only run breadth scan")
    parser.add_argument("--depth-only", type=int, help="Skip breadth, directly deep dive N weak topics")
    parser.add_argument("--deep-count", type=int, default=25, help="Deep dive topic count (default 25)")
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
        run_all(notify, deep_count=args.deep_count)
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
        run_all(notify, deep_count=args.deep_count)