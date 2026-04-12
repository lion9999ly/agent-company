"""
@description: 一夜知识库质量大修 - 去伪存真、补深补全、重建决策树
@dependencies: src.tools.knowledge_base, src.utils.model_gateway, scripts.knowledge_graph_expander
@last_modified: 2026-03-26
"""
import json
import re
import gc
import sys
import time
import hashlib
import psutil
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, str(Path(__file__).parent.parent))

# 加载环境变量
from dotenv import load_dotenv
load_dotenv()

from scripts.litellm_gateway import get_model_gateway, call_for_search, call_for_refine
from src.tools.knowledge_base import (
    add_knowledge, add_report, search_knowledge,
    get_knowledge_stats, KB_ROOT
)
from src.tools.tool_registry import get_tool_registry
from src.utils.progress_heartbeat import ProgressHeartbeat


# ==========================================
# 动态并行度（Phase 2.4）
# ==========================================
def _get_optimal_workers() -> int:
    """根据系统负载动态调整并行度"""
    try:
        cpu_pct = psutil.cpu_percent(interval=0.5)
        mem_pct = psutil.virtual_memory().percent
        if cpu_pct < 50 and mem_pct < 70:
            return 8   # 空闲：跑满
        elif cpu_pct < 80 and mem_pct < 85:
            return 4   # 中等负载：正常
        else:
            return 2   # 高负载：保守
    except Exception:
        return 4  # psutil 不可用时默认 4


def log(msg: str, notify_func=None):
    """打印 + 可选飞书通知"""
    timestamp = datetime.now().strftime("%H:%M")
    full_msg = f"[{timestamp}] {msg}"
    print(full_msg)
    if notify_func:
        notify_func(full_msg)


def phase_summary(phase_name: str, stats: dict, notify_func=None):
    """阶段完成总结（一定推送飞书）"""
    msg = (
        f"[OK] {phase_name} 完成\n"
        f"处理: {stats.get('processed', 0)} 条\n"
        f"改善: {stats.get('improved', 0)} 条\n"
        f"删除: {stats.get('deleted', 0)} 条\n"
        f"耗时: {stats.get('duration_min', 0):.0f} 分钟"
    )
    print(f"\n{'='*50}\n{msg}\n{'='*50}")
    if notify_func:
        notify_func(msg)


# ==========================================
# Phase 1: 深度去重（模糊匹配）
# ==========================================
def phase1_deep_dedup(notify_func=None) -> dict:
    """去除标题和内容高度相似的重复条目，保留最长最新的"""
    start = time.time()
    log("Phase 1: 深度去重开始", notify_func)

    from collections import defaultdict

    # 收集所有条目
    entries = []
    for f in KB_ROOT.rglob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            entries.append({
                "path": f,
                "title": data.get("title", ""),
                "content": data.get("content", ""),
                "tags": data.get("tags", []),
                "confidence": data.get("confidence", "medium"),
                "mtime": f.stat().st_mtime,
                "size": len(data.get("content", ""))
            })
        except:
            continue

    log(f"  扫描到 {len(entries)} 条知识")

    # 按标题清洗后分组
    groups = defaultdict(list)
    for entry in entries:
        # 清洗标题：去掉日期前缀、方括号标记、标点
        title = entry["title"]
        clean = re.sub(r'^[\d_]+', '', title)  # 去 0324_ 前缀
        clean = re.sub(r'^\[.*?\]\s*', '', clean)  # 去 [技术档案] [浅档案] 前缀
        clean = re.sub(r'深化[:：]', '', clean)  # 去 深化: 前缀
        clean = re.sub(r'跨界[:：]', '', clean)  # 去 跨界: 前缀
        clean = ''.join(c for c in clean[:40].lower() if c.isalnum() or '\u4e00' <= c <= '\u9fff')

        if len(clean) > 5:
            groups[clean].append(entry)

    deleted = 0
    for key, group in groups.items():
        if len(group) <= 1:
            continue

        # 排序：高置信度 > 内容更长 > 更新
        group.sort(key=lambda x: (
            -({'authoritative': 3, 'high': 2, 'medium': 1, 'low': 0}.get(x['confidence'], 1)),
            -x['size'],
            -x['mtime']
        ))

        # 保留第一个，删除其余
        for entry in group[1:]:
            try:
                entry["path"].unlink()
                deleted += 1
            except:
                pass

    duration = (time.time() - start) / 60
    stats = {"processed": len(entries), "improved": 0, "deleted": deleted, "duration_min": duration}
    phase_summary("Phase 1: 深度去重", stats, notify_func)
    gc.collect()
    return stats


# ==========================================
# Phase 2: 推测性内容降级/清理
# ==========================================
def phase2_speculative_cleanup(notify_func=None) -> dict:
    """处理推测性内容：有真实数据的保留但标注，纯假想的降级"""
    start = time.time()
    log("Phase 2: 推测性内容清理开始", notify_func)

    gateway = get_model_gateway()
    processed = 0
    improved = 0
    deleted = 0

    speculative_entries = []
    for f in KB_ROOT.rglob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if "speculative" in data.get("tags", []):
                speculative_entries.append({"path": f, "data": data})
        except:
            continue

    log(f"  发现 {len(speculative_entries)} 条推测性条目")

    for entry in speculative_entries:
        data = entry["data"]
        content = data.get("content", "")
        title = data.get("title", "")
        processed += 1

        # 快速判断：有真实数据的保留，纯假想的删除
        has_real_data = bool(re.search(
            r'\d+\.?\d*\s*(mm|cm|g|kg|mAh|W|V|Hz|dB|美元|元|USD|\$|%|nits|lux|fps|°|μm|TOPS|nm|GHz|MB|GB)',
            content
        ))
        has_real_model = bool(re.search(
            r'[A-Z]{2,}\d{2,}|IMX\d|QCC\d|BES\d|nRF\d|AR[12]|ECE\s*\d|BMI\d|ICM-\d',
            content
        ))

        if has_real_data or has_real_model:
            # 有真实数据但混了推测——保留，但在内容前加标注
            if "【注意：以下部分内容为推测】" not in content:
                data["content"] = "【注意：以下部分内容基于趋势推测，非官方确认数据】\n\n" + content
                entry["path"].write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                improved += 1
        else:
            # 纯假想内容，没有任何真实数据——删除
            try:
                entry["path"].unlink()
                deleted += 1
            except:
                pass

        if processed % 50 == 0:
            print(f"  进度: {processed}/{len(speculative_entries)}")

    duration = (time.time() - start) / 60
    stats = {"processed": processed, "improved": improved, "deleted": deleted, "duration_min": duration}
    phase_summary("Phase 2: 推测性内容清理", stats, notify_func)
    gc.collect()
    return stats


# ==========================================
# Phase 3: 浅条目批量深化（并行版 + 多Agent深度研究）
# ==========================================
def _deepen_one(entry, registry, gateway):
    """深化单条浅条目（子线程运行）"""
    data = entry["data"]
    title = data.get("title", "")
    content = data.get("content", "")

    if not title or len(title) < 5:
        return None

    # 并行搜索多个维度
    queries = [
        f"{title} 详细参数 技术规格 datasheet 2026",
        f"{title} specifications features comparison",
    ]

    search_data = ""
    for q in queries:
        result = registry.call("deep_research", q)
        if result.get("success") and len(result.get("data", "")) > 200:
            search_data += f"\n---\n{result['data'][:3000]}"

    if len(search_data) < 300:
        return None

    return {"entry": entry, "search_data": search_data}


def phase3_deepen_shallow(notify_func=None) -> dict:
    """浅条目（<200字）批量深化：并行搜索 + 分级处理"""
    start = time.time()
    log("Phase 3: 浅条目深化开始（并行搜索 + 多Agent分级）", notify_func)

    gateway = get_model_gateway()
    registry = get_tool_registry()

    shallow_entries = []
    for f in KB_ROOT.rglob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            content = data.get("content", "")
            tags = data.get("tags", [])

            if (len(content) < 200
                and data.get("type") != "report"
                and "night_deepened" not in tags
                and "speculative" not in tags):
                shallow_entries.append({"path": f, "data": data})
        except:
            continue

    log(f"  发现 {len(shallow_entries)} 条浅条目")

    # 不再限制数量，处理全部
    batch = shallow_entries
    log(f"  本轮处理 {len(batch)} 条")

    PARALLEL_WORKERS = 4
    improved = 0

    # 阶段 A：并行搜索
    log("  阶段A: 并行搜索中...")
    search_results = []
    with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as pool:
        futures = {pool.submit(_deepen_one, entry, registry, gateway): entry for entry in batch}
        for future in as_completed(futures):
            result = future.result()
            if result:
                search_results.append(result)

    log(f"  搜索完成: {len(search_results)}/{len(batch)} 条有结果")

    # 阶段 B：串行提炼（LLM 推理质量要求高）
    log("  阶段B: 串行提炼中...")
    for i, item in enumerate(search_results):
        entry = item["entry"]
        search_data = item["search_data"]
        data = entry["data"]
        title = data.get("title", "")
        content = data.get("content", "")
        tags = data.get("tags", [])

        # 分级：技术档案/芯片/方案 走多Agent，其他走单LLM
        is_deep_topic = any(kw in title.lower() or kw in ' '.join(tags).lower()
                           for kw in ["技术档案", "tech_profile", "knowledge_graph", "芯片", "soc",
                                      "传感器", "光学", "决策树", "方案"])

        if is_deep_topic and len(content) < 100:
            # 走多Agent深度研究
            try:
                from scripts.tonight_deep_research import deep_research_one
                task = {
                    "id": f"deepen_{i}",
                    "title": f"深化: {title}",
                    "goal": f"补充 {title} 的完整技术参数、竞品对比、适配度评估",
                    "searches": [
                        f"{title} datasheet specifications 2026",
                        f"{title} vs comparison alternatives",
                        f"{title} 参数 价格 供应商 2026",
                    ]
                }
                report = deep_research_one(task)
                if len(report) > len(content) + 200:
                    data["content"] = report[:2000]
                    data["tags"] = list(set(tags + ["night_deepened", "overhaul_deepened", "multi_agent"]))
                    data["confidence"] = "high"
                    entry["path"].write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                    improved += 1
                    print(f"  ✅ [多Agent] {title[:40]} ({len(report)}字)")
                    continue
            except Exception as e:
                print(f"  ⚠️ [多Agent失败] {title[:40]}: {e}，降级到单LLM")

        # 单LLM快速补充（原有逻辑作为fallback）
        deepen_prompt = (
            f"以下知识条目内容太浅（仅{len(content)}字），请深化到 400-800 字。\n"
            f"必须补充具体数据（型号、参数、价格、供应商名）。\n"
            f"如果搜索结果中没有具体数据，保持原文不要编造。\n\n"
            f"当前标题：{title}\n当前内容：{content}\n\n"
            f"搜索结果：\n{search_data[:4000]}"
        )
        # === Phase 2.3: 提炼用 GPT-5.4 ===
        result = call_for_refine(deepen_prompt, "深化知识条目，补充具体数据。", "kb_deepen")
        if result.get("success") and len(result.get("response", "")) > len(content) + 100:
            data["content"] = result["response"][:1200]
            data["tags"] = list(set(tags + ["night_deepened", "overhaul_deepened"]))
            entry["path"].write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            improved += 1

        if (i + 1) % 20 == 0:
            print(f"  进度: {i+1}/{len(search_results)}, 成功: {improved}")
            gc.collect()

        time.sleep(0.5)  # 减少等待时间

    duration = (time.time() - start) / 60
    stats = {"processed": len(batch), "improved": improved, "deleted": 0, "duration_min": duration}
    phase_summary("Phase 3: 浅条目深化", stats, notify_func)
    gc.collect()
    return stats


# ==========================================
# Phase 4: 无数据条目补充（并行版 + 多Agent深度研究）
# ==========================================
def _enrich_one(entry, registry, gateway):
    """补充单条无数据条目（子线程运行）"""
    data = entry["data"]
    title = data.get("title", "")

    if not title or len(title) < 5:
        return None

    # 并行搜索多个维度
    queries = [
        f"{title} 具体参数 型号 规格 价格 供应商",
        f"{title} specifications datasheet 2026",
    ]

    search_data = ""
    for q in queries:
        result = registry.call("deep_research", q)
        if result.get("success") and len(result.get("data", "")) > 200:
            search_data += f"\n---\n{result['data'][:3000]}"

    if len(search_data) < 300:
        return None

    return {"entry": entry, "search_data": search_data}


def phase4_enrich_no_data(notify_func=None) -> dict:
    """给没有具体数据（型号/参数/价格）的条目补充数据：并行搜索 + 分级处理"""
    start = time.time()
    log("Phase 4: 无数据条目补充开始（并行搜索 + 多Agent分级）", notify_func)

    gateway = get_model_gateway()
    registry = get_tool_registry()

    no_data_entries = []
    for f in KB_ROOT.rglob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            content = data.get("content", "")
            tags = data.get("tags", [])

            if "overhaul_enriched" in tags or "speculative" in tags:
                continue
            if data.get("type") == "report":
                continue
            if len(content) < 100:
                continue

            has_data = bool(re.search(
                r'\d+\.?\d*\s*(mm|cm|g|kg|mAh|W|V|Hz|dB|美元|元|USD|\$|%|nits|lux|fps|°|μm|TOPS|GHz)',
                content
            ))
            has_model = bool(re.search(
                r'[A-Z]{2,}\d{2,}|IMX\d|QCC\d|BES\d|nRF\d|AR[12]|ECE\s*\d|BMI\d',
                content
            ))

            if not has_data and not has_model:
                no_data_entries.append({"path": f, "data": data})
        except:
            continue

    log(f"  发现 {len(no_data_entries)} 条无数据条目")

    # 删除200条限制，处理全部
    batch = no_data_entries
    log(f"  本轮处理 {len(batch)} 条")

    PARALLEL_WORKERS = 4
    improved = 0

    # 阶段 A：并行搜索
    log("  阶段A: 并行搜索中...")
    search_results = []
    with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as pool:
        futures = {pool.submit(_enrich_one, entry, registry, gateway): entry for entry in batch}
        for future in as_completed(futures):
            result = future.result()
            if result:
                search_results.append(result)

    log(f"  搜索完成: {len(search_results)}/{len(batch)} 条有结果")

    # 阶段 B：串行提炼（LLM 推理质量要求高）
    log("  阶段B: 串行提炼中...")
    for i, item in enumerate(search_results):
        entry = item["entry"]
        search_data = item["search_data"]
        data = entry["data"]
        title = data.get("title", "")
        content = data.get("content", "")
        tags = data.get("tags", [])

        # 分级：技术档案/芯片/方案 走多Agent，其他走单LLM
        is_deep_topic = any(kw in title.lower() or kw in ' '.join(tags).lower()
                           for kw in ["技术档案", "tech_profile", "knowledge_graph", "芯片", "soc",
                                      "传感器", "光学", "决策树", "方案"])

        if is_deep_topic and len(content) < 150:
            # 走多Agent深度研究
            try:
                from scripts.tonight_deep_research import deep_research_one
                task = {
                    "id": f"enrich_{i}",
                    "title": f"补充数据: {title}",
                    "goal": f"为 {title} 补充具体型号、参数、价格、供应商信息",
                    "searches": [
                        f"{title} datasheet specifications 2026",
                        f"{title} 价格 供应商 采购",
                    ]
                }
                report = deep_research_one(task)
                # 验证确实补充了数据
                has_new_data = bool(re.search(
                    r'\d+\.?\d*\s*(mm|cm|g|kg|mAh|W|V|Hz|dB|美元|元|USD|\$|%|nits)',
                    report
                ))
                if has_new_data and len(report) > len(content) + 200:
                    data["content"] = report[:2000]
                    data["tags"] = list(set(tags + ["overhaul_enriched", "multi_agent"]))
                    data["confidence"] = "high"
                    entry["path"].write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                    improved += 1
                    print(f"  ✅ [多Agent] {title[:40]} ({len(report)}字)")
                    continue
            except Exception as e:
                print(f"  ⚠️ [多Agent失败] {title[:40]}: {e}，降级到单LLM")

        # 单LLM快速补充（原有逻辑作为fallback）
        enrich_prompt = (
            f"以下知识条目缺少具体数据。请基于搜索结果补充：\n"
            f"- 具体型号（如 IMX678、BES2800、QCC5181）\n"
            f"- 具体参数（如 3000nits、42dB、1.65kg）\n"
            f"- 具体价格（如 $15-25/颗）\n"
            f"- 具体公司/品牌名\n\n"
            f"标题：{title}\n原内容：{content[:500]}\n\n"
            f"搜索结果：\n{search_data[:3000]}\n\n"
            f"输出补充数据后的完整内容（500-800字），不要编造数据。"
        )

        # === Phase 2.3: 提炼用 GPT-5.4 ===
        result = call_for_refine(enrich_prompt, "补充具体数据，不要编造。", "kb_enrich")

        if result.get("success") and len(result.get("response", "")) > len(content):
            # 验证确实补充了数据
            new_content = result["response"]
            has_new_data = bool(re.search(
                r'\d+\.?\d*\s*(mm|cm|g|kg|mAh|W|V|Hz|dB|美元|元|USD|\$|%|nits)',
                new_content
            ))

            if has_new_data:
                data["content"] = new_content[:1200]
                data["tags"] = list(set(data.get("tags", []) + ["overhaul_enriched"]))
                entry["path"].write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                improved += 1

        if (i + 1) % 30 == 0:
            print(f"  进度: {i+1}/{len(search_results)}, 成功补充: {improved}")
            gc.collect()

        time.sleep(0.5)

    duration = (time.time() - start) / 60
    stats = {"processed": len(batch), "improved": improved, "deleted": 0, "duration_min": duration}
    phase_summary("Phase 4: 无数据条目补充", stats, notify_func)
    gc.collect()
    return stats


# ==========================================
# Phase 5: 自完整性检测 + 缺口填补
# ==========================================
def phase5_completeness(notify_func=None) -> dict:
    """检测家族缺口并自动填补"""
    start = time.time()
    log("Phase 5: 自完整性检测开始", notify_func)

    try:
        from scripts.knowledge_completeness_checker import run_completeness_check
        report = run_completeness_check()

        # 统计填补了多少
        filled = report.count("✅")

        duration = (time.time() - start) / 60
        stats = {"processed": 1, "improved": filled, "deleted": 0, "duration_min": duration}
        phase_summary("Phase 5: 自完整性检测", stats, notify_func)
    except Exception as e:
        log(f"  Phase 5 失败: {e}")
        stats = {"processed": 0, "improved": 0, "deleted": 0, "duration_min": 0}

    gc.collect()
    return stats


# ==========================================
# Phase 6: 自主深挖（选择薄弱方向）
# ==========================================
def phase6_deep_dive(notify_func=None) -> dict:
    """自主深挖薄弱领域"""
    start = time.time()
    log("Phase 6: 自主深挖开始", notify_func)

    try:
        from scripts.knowledge_graph_expander import run_autonomous_deep_dive
        report = run_autonomous_deep_dive(progress_callback=None)  # 不推中间进度

        new_entries = report.count("✅")

        duration = (time.time() - start) / 60
        stats = {"processed": 1, "improved": new_entries, "deleted": 0, "duration_min": duration}
        phase_summary("Phase 6: 自主深挖", stats, notify_func)
    except Exception as e:
        log(f"  Phase 6 失败: {e}")
        import traceback
        traceback.print_exc()
        stats = {"processed": 0, "improved": 0, "deleted": 0, "duration_min": 0}

    gc.collect()
    return stats


# ==========================================
# Phase 7: 决策树重建（多Agent讨论版）
# ==========================================
def phase7_rebuild_decision_trees(notify_func=None) -> dict:
    """基于清理后的知识库重建所有决策树（多Agent讨论）"""
    start = time.time()
    log("Phase 7: 决策树重建开始（多Agent讨论）", notify_func)

    gateway = get_model_gateway()

    # 按领域分组知识
    domain_profiles = {}
    for f in KB_ROOT.rglob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            tags = data.get("tags", [])
            if "knowledge_graph" not in tags and "tech_profile" not in tags:
                continue
            if "speculative" in tags:
                continue

            # 找到领域 key
            domain_key = None
            for tag in tags:
                if tag in ("ar_xr_soc", "audio_soc", "optical_hud", "sensor_imu",
                          "connector", "battery_bms", "mesh_intercom"):
                    domain_key = tag
                    break

            if domain_key:
                if domain_key not in domain_profiles:
                    domain_profiles[domain_key] = []
                domain_profiles[domain_key].append(
                    f"{data.get('title', '')}: {data.get('content', '')[:400]}"
                )
        except:
            continue

    trees_built = 0

    for domain_key, profiles in domain_profiles.items():
        if len(profiles) < 3:
            continue

        log(f"  生成决策树: {domain_key} ({len(profiles)} 份档案)")

        # 用多Agent流程生成决策树
        try:
            from scripts.tonight_deep_research import deep_research_one

            profiles_text = "\n---\n".join(profiles[:15])
            task = {
                "id": f"tree_{domain_key}",
                "title": f"{domain_key} 选型决策树",
                "goal": (
                    f"基于以下 {len(profiles)} 份技术档案，生成智能摩托车全盔项目的 {domain_key} 选型决策树。"
                    f"按场景分支推荐，每个推荐要有参数依据和风险标注。"
                ),
                "searches": []  # 不需要额外搜索，直接用已有档案
            }

            # 调用多Agent讨论生成决策树
            report = deep_research_one(task)

            if len(report) > 500:
                # 先删除旧的决策树
                for f in KB_ROOT.rglob("*.json"):
                    try:
                        d = json.loads(f.read_text(encoding="utf-8"))
                        if "decision_tree" in d.get("tags", []) and domain_key in d.get("tags", []):
                            f.unlink()
                    except:
                        continue

                # 存新的
                add_report(
                    title=f"[决策树] {domain_key} 选型指南（多Agent讨论）",
                    domain="components",
                    content=report,
                    tags=["knowledge_graph", "decision_tree", domain_key, "multi_agent", "overhaul_rebuilt"],
                    source=f"overhaul:rebuild_tree:{domain_key}",
                    confidence="high"
                )
                trees_built += 1
                print(f"  ✅ [多Agent] {domain_key} 决策树生成完成 ({len(report)}字)")
                continue
        except Exception as e:
            print(f"  ⚠️ [多Agent失败] {domain_key}: {e}，降级到单LLM")

        # 降级：单LLM生成（原有逻辑）
        decision_prompt = (
            f"你是智能摩托车全盔项目的技术总监。\n"
            f"以下是 {domain_key} 领域的 {len(profiles)} 份技术档案。\n\n"
            f"请生成一份【选型决策树】。\n\n"
            f"格式：\n"
            f"1. 关键决策维度（算力/功耗/接口/成本）\n"
            f"2. 按场景分支推荐，每个推荐说明理由和风险\n"
            f"3. 标注不确定的地方\n"
            f"4. 简洁实用，1500-2500字\n\n"
            f"技术档案：\n" + "\n---\n".join(profiles[:15])
        )

        # === Phase 2.3: 决策树用 GPT-5.4 ===
        result = call_for_refine(decision_prompt, "生成简洁实用的选型决策树。", "rebuild_decision_tree")

        if result.get("success") and len(result.get("response", "")) > 500:
            # 先删除旧的决策树
            for f in KB_ROOT.rglob("*.json"):
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    if "decision_tree" in data.get("tags", []) and domain_key in data.get("tags", []):
                        f.unlink()
                except:
                    continue

            # 存新的
            add_report(
                title=f"[决策树] {domain_key} 选型指南（大修后重建）",
                domain="components",
                content=result["response"],
                tags=["knowledge_graph", "decision_tree", domain_key, "overhaul_rebuilt"],
                source=f"overhaul:rebuild_tree:{domain_key}",
                confidence="high"
            )
            trees_built += 1

        time.sleep(3)

    duration = (time.time() - start) / 60
    stats = {"processed": len(domain_profiles), "improved": trees_built, "deleted": 0, "duration_min": duration}
    phase_summary("Phase 7: 决策树重建", stats, notify_func)
    gc.collect()
    return stats


# ==========================================
# 主流程
# ==========================================
def run_overnight_overhaul(notify_func=None):
    """一夜知识库质量大修主流程"""

    start_time = time.time()
    start_stats = get_knowledge_stats()
    start_total = sum(start_stats.values())

    log(f"\n{'#'*60}", notify_func)
    log(f"# 知识库质量大修启动", notify_func)
    log(f"# 起始: {start_total} 条", notify_func)
    log(f"# 时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}", notify_func)
    log(f"{'#'*60}", notify_func)

    all_stats = {}

    # Phase 1: 去重
    all_stats["dedup"] = phase1_deep_dedup(notify_func)
    time.sleep(5)

    # Phase 2: 推测性内容清理
    all_stats["speculative"] = phase2_speculative_cleanup(notify_func)
    time.sleep(5)

    # Phase 3: 浅条目深化
    all_stats["deepen"] = phase3_deepen_shallow(notify_func)
    time.sleep(5)

    # Phase 4: 无数据补充
    all_stats["enrich"] = phase4_enrich_no_data(notify_func)
    time.sleep(5)

    # Phase 5: 自完整性检测
    all_stats["completeness"] = phase5_completeness(notify_func)
    time.sleep(5)

    # Phase 6: 自主深挖
    all_stats["deep_dive"] = phase6_deep_dive(notify_func)
    time.sleep(5)

    # Phase 7: 决策树重建
    all_stats["decision_trees"] = phase7_rebuild_decision_trees(notify_func)

    # 最终总结
    end_stats = get_knowledge_stats()
    end_total = sum(end_stats.values())
    total_duration = (time.time() - start_time) / 60

    # 最终审计
    shallow_count = 0
    no_data_count = 0
    spec_count = 0
    for f in KB_ROOT.rglob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            content = data.get("content", "")
            tags = data.get("tags", [])
            if len(content) < 200:
                shallow_count += 1
            has_data = bool(re.search(r'\d+\.?\d*\s*(mm|cm|g|kg|mAh|W|V|Hz|dB|美元|元|\$|%|nits)', content))
            has_model = bool(re.search(r'[A-Z]{2,}\d{2,}|IMX\d|QCC\d|BES\d', content))
            if not has_data and not has_model:
                no_data_count += 1
            if "speculative" in tags:
                spec_count += 1
        except:
            continue

    shallow_pct = round(shallow_count / end_total * 100, 1) if end_total > 0 else 0
    no_data_pct = round(no_data_count / end_total * 100, 1) if end_total > 0 else 0

    final_report = (
        f"\n{'#'*60}\n"
        f"# 知识库质量大修完成报告\n"
        f"{'#'*60}\n\n"
        f"⏱️ 总耗时: {total_duration:.0f} 分钟\n\n"
        f"📊 知识库变化:\n"
        f"  修前: {start_total} 条\n"
        f"  修后: {end_total} 条\n"
        f"  分布: {json.dumps(end_stats, ensure_ascii=False)}\n\n"
        f"📈 质量指标:\n"
        f"  浅条目: {shallow_count} ({shallow_pct}%)\n"
        f"  无数据: {no_data_count} ({no_data_pct}%)\n"
        f"  推测性: {spec_count}\n\n"
        f"🔧 各阶段:\n"
    )

    for phase_name, stats in all_stats.items():
        final_report += (
            f"  {phase_name}: "
            f"处理{stats['processed']} 改善{stats['improved']} 删除{stats['deleted']} "
            f"({stats['duration_min']:.0f}min)\n"
        )

    print(final_report)

    if notify_func:
        notify_func(final_report)

    # 保存报告到文件
    report_dir = Path(__file__).parent.parent / ".ai-state" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"overhaul_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
    report_path.write_text(final_report, encoding="utf-8")

    return final_report


# ==========================================
# 分阶段执行入口（用于逐步验证）
# ==========================================
def run_phase(phase_num: int, notify_func=None):
    """单独执行某个阶段"""
    phases = {
        1: phase1_deep_dedup,
        2: phase2_speculative_cleanup,
        3: phase3_deepen_shallow,
        4: phase4_enrich_no_data,
        5: phase5_completeness,
        6: phase6_deep_dive,
        7: phase7_rebuild_decision_trees,
    }

    if phase_num not in phases:
        print(f"无效的阶段号: {phase_num}，应为 1-7")
        return None

    return phases[phase_num](notify_func)


def verify_phase(phase_num: int):
    """验证阶段执行结果"""
    print(f"\n{'='*50}")
    print(f"验证 Phase {phase_num} 结果")
    print(f"{'='*50}")

    stats = get_knowledge_stats()
    total = sum(stats.values())
    print(f"知识库总量: {total} 条")
    print(f"分布: {json.dumps(stats, ensure_ascii=False)}")

    # 统计质量指标
    shallow_count = 0
    no_data_count = 0
    spec_count = 0

    for f in KB_ROOT.rglob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            content = data.get("content", "")
            tags = data.get("tags", [])

            if len(content) < 200:
                shallow_count += 1

            has_data = bool(re.search(
                r'\d+\.?\d*\s*(mm|cm|g|kg|mAh|W|V|Hz|dB|美元|元|\$|%|nits)',
                content
            ))
            has_model = bool(re.search(r'[A-Z]{2,}\d{2,}|IMX\d|QCC\d|BES\d', content))

            if not has_data and not has_model:
                no_data_count += 1

            if "speculative" in tags:
                spec_count += 1
        except:
            continue

    print(f"\n质量指标:")
    print(f"  浅条目 (<200字): {shallow_count}")
    print(f"  无数据条目: {no_data_count}")
    print(f"  推测性条目: {spec_count}")

    return {
        "total": total,
        "shallow": shallow_count,
        "no_data": no_data_count,
        "speculative": spec_count
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="知识库质量大修")
    parser.add_argument("--phase", type=int, help="单独执行某个阶段 (1-7)")
    parser.add_argument("--verify", type=int, help="验证某个阶段结果 (1-7)")
    parser.add_argument("--all", action="store_true", help="执行全部阶段")

    args = parser.parse_args()

    # 尝试连接飞书推送
    notify = None
    try:
        from scripts.feishu_sdk_client import send_reply
        NOTIFY_TARGET = "ou_8e5e4f183e9eca4241378e96bac3a751"

        def feishu_notify(msg):
            try:
                send_reply(NOTIFY_TARGET, msg)
            except:
                pass

        notify = feishu_notify
        print("[Overhaul] 飞书推送已连接")
    except:
        print("[Overhaul] 飞书推送不可用，仅终端输出")

    if args.phase:
        run_phase(args.phase, notify)
        verify_phase(args.phase)
    elif args.verify:
        verify_phase(args.verify)
    elif args.all:
        run_overnight_overhaul(notify_func=notify)
    else:
        # 默认显示帮助
        parser.print_help()