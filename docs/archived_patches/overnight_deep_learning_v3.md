# 深度学习 v3 — 广度扫盲 + 精准深挖两阶段

> 生成时间: 2026-03-28
> v2 问题: 60 分钟跑完"10 小时任务"，每主题 35 秒，太浅
> v3 核心改进: 两阶段架构 + 入库质量门槛 + 深度模式多轮搜索

---

## 架构设计

```
Phase A: 广度扫盲（~1 小时）
  109 个主题 × 4 路并行搜索 + 单次提炼
  产出：每主题 400-800 字基础认知
  入库门槛：必须包含具体数据，否则标记 shallow
  
  ↓ 自动筛选最薄弱的 25 个主题 ↓

Phase B: 精准深挖（~8 小时）
  25 个主题 × 每个 3 轮搜索 + 数据提取 + 结构化提炼
  产出：每主题 1500-3000 字深度知识
  多角度搜索：中文 + 英文 + 学术/行业报告
  交叉验证：多源数据不一致时标注冲突
```

---

## 创建 scripts/overnight_deep_learning_v3.py

```python
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
        f"✅ {name}\n"
        f"搜索: {stats.get('searched', 0)} | 入库: {stats.get('added', 0)} | "
        f"跳过: {stats.get('skipped', 0)} | 浅条目: {stats.get('shallow', 0)} | "
        f"耗时: {stats.get('minutes', 0):.0f}min"
    )
    print(f"\n{'='*50}\n{msg}\n{'='*50}")
    if notify_func:
        try:
            notify_func(msg)
        except:
            pass


# ==========================================
# 质量检测
# ==========================================
def _quality_check(content: str, title: str) -> dict:
    """检测条目质量，返回 {pass, reason, is_speculative, has_data}"""
    
    # 推测性检测
    spec_signals = ["假想", "假设", "推测", "推演", "预计将", "可能采用", 
                    "尚未公开", "暂无公开", "目前尚无", "理论上可以"]
    is_spec = any(s in content for s in spec_signals)
    
    # 具体数据检测
    has_number = bool(re.search(
        r'\d+\.?\d*\s*(mm|cm|g|kg|mAh|W|V|Hz|dB|美元|元|USD|\$|%|nits|lux|fps|°|μm|TOPS|nm|GHz|MB|GB|台|件|个月|周|天)',
        content
    ))
    has_model = bool(re.search(
        r'[A-Z]{2,}\d{2,}|IMX\d|QCC\d|BES\d|nRF\d|AR[12]|ECE\s*\d|BMI\d|ICM-\d|STM32|ESP32|MT\d{4}',
        content
    ))
    has_brand = bool(re.search(
        r'(歌尔|立讯|闻泰|舜宇|丘钛|索尼|高通|联发科|Qualcomm|Sony|Bosch|TI|Nordic|Himax|JBD|'
        r'Sena|Cardo|Forcite|LIVALL|EyeRide|CrossHelmet|GoPro|Insta360|'
        r'TÜV|DEKRA|SGS|Intertek|UL|BV)',
        content
    ))
    
    has_data = has_number or has_model or has_brand
    
    # 长度检测
    too_short = len(content) < 300
    
    # 判定
    if too_short:
        return {"pass": False, "reason": "内容太短(<300字)", "is_speculative": is_spec, "has_data": has_data}
    if is_spec and not has_data:
        return {"pass": False, "reason": "纯推测无数据", "is_speculative": True, "has_data": False}
    if not has_data and not is_spec:
        return {"pass": True, "reason": "无具体数据但非推测", "is_speculative": False, "has_data": False, "shallow": True}
    
    return {"pass": True, "reason": "OK", "is_speculative": is_spec, "has_data": has_data, "shallow": False}


# ==========================================
# Phase A: 广度扫盲
# ==========================================
def _breadth_search_one(topic, registry):
    """广度模式：单主题快速搜索"""
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
    """广度模式：单次提炼"""
    title = topic["title"]
    domain = topic.get("domain", "components")
    tags = topic.get("tags", [])
    
    if len(search_data) < 300:
        return {"success": False, "title": title, "reason": "搜索不足", "quality": None}
    
    prompt = (
        f"基于以下搜索结果，输出关于「{title}」的知识条目。\n"
        f"必须包含具体数据（型号、参数、价格、品牌名）。\n"
        f"如果搜不到具体数据，标注'未查到'，不要编造。\n"
        f"输出 400-800 字。\n\n"
        f"搜索结果：\n{search_data[:4000]}"
    )
    
    result = gateway.call_azure_openai("cpo", prompt,
        "输出详细知识条目，包含具体数据。", "deep_learn_refine")
    
    if not result.get("success") or len(result.get("response", "")) < 200:
        return {"success": False, "title": title, "reason": "提炼失败", "quality": None}
    
    content = result["response"]
    quality = _quality_check(content, title)
    
    # 入库
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
    """Phase A: 广度扫盲"""
    start = time.time()
    log(f"Phase A: 广度扫盲开始（{len(topics)} 个主题）", notify_func)
    
    registry = get_tool_registry()
    gateway = get_model_gateway()
    
    # 并行搜索
    log("  阶段 A1: 并行搜索中（4 路）...")
    search_results = []
    done = 0
    
    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = {pool.submit(_breadth_search_one, t, registry): t for t in topics}
        for f in as_completed(futs):
            search_results.append(f.result())
            done += 1
            if done % 10 == 0:
                print(f"  搜索进度: {done}/{len(topics)}")
    
    log(f"  搜索完成: {len(search_results)}/{len(topics)}")
    
    # 串行提炼
    log("  阶段 A2: 串行提炼中...")
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
                print(f"  ⚠️ [{i}/{len(search_results)}] {result['title'][:40]} — 浅条目(无具体数据)")
            elif result.get("is_speculative"):
                speculative += 1
                print(f"  🔮 [{i}/{len(search_results)}] {result['title'][:40]} — 推测性")
            else:
                print(f"  ✅ [{i}/{len(search_results)}] {result['title'][:40]} ({result.get('content_len', 0)}字)")
        else:
            skipped += 1
            print(f"  ⏭️ [{i}/{len(search_results)}] {result['title'][:40]} — {result['reason']}")
        
        if i % 20 == 0:
            gc.collect()
    
    minutes = (time.time() - start) / 60
    stats = {
        "searched": len(topics), "added": added, "skipped": skipped,
        "shallow": shallow, "speculative": speculative, "minutes": minutes
    }
    phase_done("Phase A: 广度扫盲", stats, notify_func)
    
    gc.collect()
    return results, stats


# ==========================================
# 自动筛选薄弱主题
# ==========================================
def _select_deep_dive_topics(breadth_results, topics, max_count=25):
    """从广度结果中筛选需要深挖的主题"""
    
    candidates = []
    
    for result in breadth_results:
        score = 0
        title = result["title"]
        
        # 找到对应的原始 topic
        topic = None
        for t in topics:
            if t["title"] == title:
                topic = t
                break
        
        if not topic:
            continue
        
        # 评分：越需要深挖分越高
        if not result["success"]:
            score += 10  # 完全失败，最需要深挖
        elif result.get("shallow"):
            score += 8   # 浅条目，缺数据
        elif result.get("is_speculative"):
            score += 6   # 推测性，需要验证
        elif not result.get("has_data"):
            score += 5   # 没有具体数据
        else:
            score += 1   # 已有数据，低优先
        
        # 核心领域加分（这些领域更重要）
        core_tags = {"bom", "cost", "thermal", "power", "certification", "voice",
                     "hw_teardown", "market_data", "user_research"}
        if any(tag in topic.get("tags", []) for tag in core_tags):
            score += 3
        
        # 有自定义 refine_prompt 的说明是复杂主题
        if topic.get("refine_prompt"):
            score += 2
        
        candidates.append({
            "topic": topic,
            "score": score,
            "reason": result.get("reason", ""),
            "breadth_quality": result.get("quality", {})
        })
    
    # 按分数排序，取前 max_count 个
    candidates.sort(key=lambda x: -x["score"])
    selected = candidates[:max_count]
    
    print(f"\n[DeepDive] 从 {len(breadth_results)} 个广度结果中筛选 {len(selected)} 个深挖主题：")
    for i, c in enumerate(selected, 1):
        print(f"  {i}. [{c['score']}分] {c['topic']['title'][:50]} — {c['reason']}")
    
    return selected


# ==========================================
# Phase B: 精准深挖
# ==========================================
def _deep_search_one(topic_info, registry):
    """深度模式：多轮多角度搜索"""
    topic = topic_info["topic"]
    title = topic["title"]
    base_searches = topic.get("searches", [])
    
    all_data = ""
    sources_count = 0
    
    # 第 1 轮：原始搜索词（中文为主）
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
    
    # 第 2 轮：英文补充搜索
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
    
    # 第 3 轮：行业报告/学术搜索
    report_queries = [
        f"{title} market report industry analysis forecast",
        f"{title} 行业报告 白皮书 研究 数据",
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
    """深度模式：两步提炼（提取数据 → 结构化输出）"""
    topic = topic_info["topic"]
    title = topic["title"]
    domain = topic.get("domain", "components")
    tags = topic.get("tags", [])
    custom_prompt = topic.get("refine_prompt", "")
    
    if len(search_data) < 500:
        return {"success": False, "title": title, "reason": f"搜索不足(仅{sources_count}源)"}
    
    # Step 1: 提取关键数据点
    extract_prompt = (
        f"从以下 {sources_count} 个来源的搜索结果中，提取关于「{title}」的所有具体数据点。\n"
        f"只输出数据（型号、参数、价格、品牌、日期、来源），每条一行。\n"
        f"如果不同来源数据矛盾，两个都列出并标注[矛盾]。\n"
        f"最多 40 条。\n\n"
        f"搜索结果：\n{search_data[:6000]}"
    )
    
    extract_result = gateway.call_azure_openai("cpo", extract_prompt,
        "只输出数据点，不要分析。", "deep_learn_extract")
    
    extracted = extract_result.get("response", "") if extract_result.get("success") else ""
    
    if len(extracted) < 100:
        # 提取失败，降级到单步提炼
        extracted = search_data[:4000]
    
    # Step 2: 结构化输出
    if custom_prompt:
        final_prompt = custom_prompt.format(search_data=extracted[:4000], title=title)
    else:
        final_prompt = (
            f"基于以下已提取的数据点，输出关于「{title}」的深度知识条目。\n\n"
            f"要求：\n"
            f"1. 开头用一句话总结核心结论\n"
            f"2. 按维度组织（如：技术参数/市场数据/竞品对比/成本区间/风险点）\n"
            f"3. 每个数据点标注来源可信度（公开官方/行业报告/推测估算）\n"
            f"4. 如果数据有矛盾，列出矛盾并给出判断\n"
            f"5. 结尾标注仍缺失的关键数据\n"
            f"6. 输出 1500-2500 字\n\n"
            f"已提取数据点：\n{extracted[:4000]}\n\n"
            f"补充搜索上下文：\n{search_data[:2000]}"
        )
    
    result = gateway.call_azure_openai("cpo", final_prompt,
        "输出深度知识条目，结构化且有数据支撑。", "deep_learn_deep_refine",
        max_tokens=4096)
    
    if not result.get("success") or len(result.get("response", "")) < 500:
        return {"success": False, "title": title, "reason": "深度提炼失败"}
    
    content = result["response"]
    quality = _quality_check(content, title)
    
    # 入库（深度条目替换广度条目）
    final_tags = tags.copy() + ["depth_v3"]
    if quality["is_speculative"]:
        final_tags.append("speculative")
    
    confidence = "low" if quality["is_speculative"] else "high"
    
    # 先删除同名的广度条目
    for f in KB_ROOT.rglob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if data.get("title") == title and "breadth_v3" in data.get("tags", []):
                f.unlink()
                break
        except:
            continue
    
    add_knowledge(
        title=f"[深度] {title}",
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
    """Phase B: 精准深挖"""
    start = time.time()
    total = len(selected_topics)
    log(f"Phase B: 精准深挖开始（{total} 个主题，每个 3 轮搜索 + 两步提炼）", notify_func)
    
    registry = get_tool_registry()
    gateway = get_model_gateway()
    
    added = 0
    skipped = 0
    
    # 分批处理：每批 5 个并行搜索，串行提炼
    batch_size = 5
    for batch_start in range(0, total, batch_size):
        batch = selected_topics[batch_start:batch_start + batch_size]
        batch_num = batch_start // batch_size + 1
        total_batches = (total + batch_size - 1) // batch_size
        
        log(f"  批次 {batch_num}/{total_batches}: 并行搜索 {len(batch)} 个主题...")
        
        # 并行搜索
        search_results = []
        with ThreadPoolExecutor(max_workers=4) as pool:
            futs = {pool.submit(_deep_search_one, t, registry): t for t in batch}
            for f in as_completed(futs):
                search_results.append(f.result())
        
        # 串行提炼
        for item in search_results:
            topic_info = item["topic_info"]
            title = topic_info["topic"]["title"]
            
            result = _deep_refine(topic_info, item["search_data"], item["sources_count"], gateway)
            
            if result["success"]:
                added += 1
                spec_mark = " 🔮" if result.get("is_speculative") else ""
                print(f"  ✅ [{added+skipped}/{total}] {title[:45]} "
                      f"({result['content_len']}字, {result['sources']}源){spec_mark}")
            else:
                skipped += 1
                print(f"  ❌ [{added+skipped}/{total}] {title[:45]} — {result['reason']}")
            
            time.sleep(2)  # 控制频率
        
        gc.collect()
        
        # 每批完成后报告进度
        if notify_func and batch_num % 2 == 0:
            try:
                notify_func(f"Phase B 进度: {added+skipped}/{total}, 入库 {added}")
            except:
                pass
    
    minutes = (time.time() - start) / 60
    stats = {"searched": total, "added": added, "skipped": skipped, "shallow": 0, "minutes": minutes}
    phase_done("Phase B: 精准深挖", stats, notify_func)
    gc.collect()
    return stats


# ==========================================
# 主题列表（复用 v2 的 109 个主题）
# ==========================================
def _load_all_topics():
    """加载所有主题（从 v2 导入或重新定义）"""
    try:
        # 尝试从 v2 导入
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
        print("[Warning] 无法导入 v2 主题，使用空列表")
        return []


# ==========================================
# 主流程
# ==========================================
def run_all(notify_func=None, deep_count=25):
    start = time.time()
    start_stats = get_knowledge_stats()
    start_total = sum(start_stats.values())
    
    topics = _load_all_topics()
    
    log(f"{'#'*60}", notify_func)
    log(f"# 深度学习 v3 启动（两阶段模式）", notify_func)
    log(f"# 知识库: {start_total} 条", notify_func)
    log(f"# 广度主题: {len(topics)} 个", notify_func)
    log(f"# 深挖数量: {deep_count} 个（自动筛选）", notify_func)
    log(f"{'#'*60}", notify_func)
    
    # Phase A: 广度扫盲
    breadth_results, a_stats = run_phase_a(topics, notify_func)
    time.sleep(10)
    
    # 自动筛选薄弱主题
    selected = _select_deep_dive_topics(breadth_results, topics, max_count=deep_count)
    
    if selected:
        log(f"\n筛选出 {len(selected)} 个主题进入深挖", notify_func)
    else:
        log(f"\n无需深挖的主题，所有广度结果质量足够", notify_func)
    
    # Phase B: 精准深挖
    b_stats = {"searched": 0, "added": 0, "skipped": 0, "minutes": 0}
    if selected:
        b_stats = run_phase_b(selected, notify_func)
    
    # 最终总结
    end_stats = get_knowledge_stats()
    end_total = sum(end_stats.values())
    total_min = (time.time() - start) / 60
    
    # 质量审计
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
        f"# 深度学习 v3 完成\n"
        f"{'#'*60}\n\n"
        f"⏱️ 总耗时: {total_min:.0f} 分钟\n"
        f"📊 知识库: {start_total} → {end_total}（+{end_total - start_total}）\n\n"
        f"Phase A 广度扫盲:\n"
        f"  入库 {a_stats['added']} | 跳过 {a_stats['skipped']} | "
        f"浅条目 {a_stats.get('shallow', 0)} | 推测 {a_stats.get('speculative', 0)} | "
        f"{a_stats['minutes']:.0f}min\n\n"
        f"Phase B 精准深挖:\n"
        f"  入库 {b_stats['added']} | 跳过 {b_stats['skipped']} | "
        f"{b_stats.get('minutes', 0):.0f}min\n\n"
        f"质量指标:\n"
        f"  深度条目: {depth_count}\n"
        f"  广度条目: {breadth_count}\n"
        f"  推测性条目: {spec_count}\n"
    )
    
    print(final)
    if notify_func:
        notify_func(final)
    
    # 保存报告
    report_dir = Path(__file__).parent.parent / ".ai-state" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / f"deep_learn_v3_{datetime.now().strftime('%Y%m%d_%H%M')}.md").write_text(final, encoding="utf-8")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="深度学习 v3（两阶段）")
    parser.add_argument("--all", action="store_true", help="执行全部（广度+深挖）")
    parser.add_argument("--breadth-only", action="store_true", help="只跑广度扫盲")
    parser.add_argument("--depth-only", type=int, help="跳过广度，直接深挖 N 个薄弱主题")
    parser.add_argument("--deep-count", type=int, default=25, help="深挖主题数（默认 25）")
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
        print("[DeepLearn v3] 飞书推送已连接")
    except:
        print("[DeepLearn v3] 飞书推送不可用")
    
    if args.all:
        run_all(notify, deep_count=args.deep_count)
    elif args.breadth_only:
        topics = _load_all_topics()
        run_phase_a(topics, notify)
    elif args.depth_only:
        # 从知识库中找 breadth_v3 的浅条目，直接深挖
        topics = _load_all_topics()
        # 模拟广度结果：标记所有 shallow/speculative 的为需要深挖
        fake_results = []
        for t in topics:
            # 检查知识库中是否已有该主题的深度版本
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
                    "reason": "无深度版本"
                })
        
        selected = _select_deep_dive_topics(fake_results, topics, max_count=args.depth_only)
        if selected:
            run_phase_b(selected, notify)
    else:
        run_all(notify, deep_count=args.deep_count)
```

---

## 启动方式

```powershell
# 完整模式（广度 1h + 深挖 8h）
python scripts/overnight_deep_learning_v3.py --all

# 只跑广度（1h，白天快速扫盲）
python scripts/overnight_deep_learning_v3.py --breadth-only

# 只深挖 30 个主题（跳过广度，直接挖）
python scripts/overnight_deep_learning_v3.py --depth-only 30

# 调整深挖数量
python scripts/overnight_deep_learning_v3.py --all --deep-count 35
```

## 预期时间和产出

| 阶段 | 主题数 | 每个耗时 | 总耗时 | 产出 |
|------|--------|---------|--------|------|
| Phase A 广度 | 109 | ~35秒 | ~60min | 80-100 条基础认知(400-800字) |
| 筛选 | — | — | ~1min | 25 个薄弱主题 |
| Phase B 深挖 | 25 | ~18min | ~7.5h | 20-25 条深度知识(1500-3000字) |
| **合计** | | | **~8.5h** | **100-125 条** |
