# CC 执行文档 Part 2: 运营体系 — 自学习 + 深度学习 + KB 治理

> 日期: 2026-03-31
> 依赖: Part 1（五层管道改造）先完成
> 涉及文件:
>   - `scripts/tonight_deep_research.py`（深度学习调度）
>   - `scripts/auto_learn.py`（自学习，改造现有或新建）
>   - `scripts/kb_governance.py`（新建）
>   - `src/tools/knowledge_base.py`（增加治理 API）
>   - 飞书 handler（注册 "深度学习" 指令）
>   - 定时调度配置（cron / scheduler）
> 完成后: `git add -A && git commit -m "feat: learning system — auto-learn 30min, deep-learn 7h, KB governance"`
> **不要重启服务，Leo 手动重启。**

---

## 一、三个运行模式概览

```
┌─────────────────────────────────────────────────────────────┐
│                    知识运营体系                               │
├──────────────┬───────────────────┬──────────────────────────┤
│  自学习 30min │  深度学习 7h       │  KB 治理                 │
│  定时触发     │  每晚1点 或 飞书   │  每周一次 或 随深度学习   │
│              │  "深度学习" 触发    │                          │
├──────────────┼───────────────────┼──────────────────────────┤
│ Layer 1-2    │ Layer 1-5 完整     │ 不调用 LLM               │
│ 搜索+提炼    │ 搜索→提炼→分析→   │ 规则化清理               │
│ 直接入 KB    │ 整合→Critic→KB    │ 去重/合并/降级/淘汰       │
├──────────────┼───────────────────┼──────────────────────────┤
│ ~5-8 个 query│ 任务池 + 自主发现  │ 全库扫描                  │
│ 快进快出     │ 填满 7h 不浪费     │ 产出健康度报告            │
└──────────────┴───────────────────┴──────────────────────────┘
```

---

## 二、自学习 30min（轻量增量）

### 2.1 定位

每 30 分钟自动触发，快速补充增量知识。不走 Agent 分析和 Critic，只做搜索+提炼+入库。相当于"知识库的 heartbeat"。

### 2.2 任务来源: KB 缺口分析

每次触发时，自动分析当前 KB 的薄弱环节:

```python
def _find_kb_gaps() -> list:
    """分析知识库缺口，返回需要补充的搜索词列表

    策略:
    1. 域分布不均: 哪个 domain 条目最少？
    2. 时效性: 哪些条目超过 30 天未更新？
    3. 产品锚点覆盖: PRD 中提到的模块，KB 有没有对应知识？
    4. 低 confidence 高频引用: 被多次引用但 confidence 只有 medium/low 的条目
    """
    from src.tools.knowledge_base import KB_ROOT, get_knowledge_stats
    import json
    from datetime import datetime, timedelta

    gaps = []

    # 1. 域分布
    stats = get_knowledge_stats()
    if stats:
        min_domain = min(stats, key=stats.get)
        if stats[min_domain] < stats.get(max(stats, key=stats.get), 0) * 0.3:
            gaps.append({
                "type": "domain_gap",
                "domain": min_domain,
                "query": f"智能骑行头盔 {min_domain} 最新技术 供应商 2026",
                "priority": 1
            })

    # 2. 时效性（超过 30 天的条目所在领域）
    stale_domains = set()
    cutoff = datetime.now() - timedelta(days=30)
    for f in KB_ROOT.rglob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            created = data.get("created_at", "")
            if created and datetime.fromisoformat(created) < cutoff:
                domain = data.get("domain", "general")
                stale_domains.add(domain)
        except:
            continue

    for domain in list(stale_domains)[:2]:
        gaps.append({
            "type": "stale",
            "domain": domain,
            "query": f"{domain} motorcycle helmet latest update 2026",
            "priority": 2
        })

    # 3. 产品锚点覆盖
    anchor_keywords = [
        "HUD", "光波导", "waveguide", "OLED", "Micro LED",
        "mesh intercom", "Cardo", "骨传导", "ANC",
        "Qualcomm AR1", "主SoC", "胎压", "TPMS",
        "DOT", "ECE", "SNELL", "安全认证"
    ]
    for kw in anchor_keywords:
        # 检查 KB 中是否有足够条目
        count = 0
        for f in KB_ROOT.rglob("*.json"):
            try:
                content = f.read_text(encoding="utf-8")
                if kw.lower() in content.lower():
                    count += 1
            except:
                continue
        if count < 3:
            gaps.append({
                "type": "anchor_gap",
                "keyword": kw,
                "query": f"{kw} motorcycle helmet specs supplier price 2026",
                "priority": 1
            })

    # 按优先级排序，取 top 5-8
    gaps.sort(key=lambda x: x["priority"])
    return gaps[:8]
```

### 2.3 执行流程

```python
def auto_learn_cycle():
    """自学习 30min 周期

    只跑 Layer 1（搜索）+ Layer 2（提炼）+ 直接入库
    不走 Agent 分析，不生成报告
    """
    print(f"\n{'='*40}")
    print(f"[AutoLearn] {time.strftime('%H:%M')} 开始")

    gaps = _find_kb_gaps()
    if not gaps:
        print("[AutoLearn] 无明显缺口，跳过")
        return

    print(f"[AutoLearn] 发现 {len(gaps)} 个缺口")

    added_total = 0
    for gap in gaps:
        query = gap["query"]
        print(f"  搜索: {query[:50]}...")

        # Layer 1: 双搜索（但自学习用轻量模式，豆包为主，o3 只对 priority=1 启用）
        source_text = ""

        if gap["priority"] == 1:
            # 高优先级: 启用 o3
            o3_result = _call_model("o3_deep_research", query, task_type="auto_learn")
            if o3_result.get("success"):
                source_text += o3_result["response"][:2000]

        # 豆包始终启用
        doubao_result = _call_model("doubao_seed_pro", query,
                                    "搜索相关技术和市场信息，提取具体数据。",
                                    "auto_learn")
        if doubao_result.get("success"):
            source_text += "\n" + doubao_result["response"][:2000]

        if not source_text:
            continue

        # Layer 2: 提炼
        extracted = _extract_structured_data(
            raw_text=source_text,
            task_type=gap.get("domain", "general"),
            topic=query
        )

        if extracted:
            # 直接入库（不经过 Agent 分析）
            from src.tools.knowledge_base import add_knowledge
            title = extracted.get("product", extracted.get("topic", query[:40]))
            content = json.dumps(extracted, ensure_ascii=False, indent=2)

            if len(content) > 150:  # 质量门槛
                add_knowledge(
                    title=f"[AutoLearn] {title}",
                    domain=gap.get("domain", "components"),
                    content=content[:800],
                    tags=["auto_learn", gap.get("type", "general")],
                    source="auto_learn",
                    confidence="medium"  # 自学习产出标记为 medium
                )
                added_total += 1

        time.sleep(3)

    print(f"[AutoLearn] 完成: +{added_total} 条知识")
    print(f"{'='*40}")
```

### 2.4 定时触发

找到现有的定时机制（CC 先搜索项目中的 scheduler/cron 配置），然后注册 30min 周期:

```python
# 在调度器中注册（具体方式取决于现有机制）
# 如果用 APScheduler:
scheduler.add_job(auto_learn_cycle, 'interval', minutes=30, id='auto_learn')

# 如果用 threading.Timer 循环:
def auto_learn_loop():
    while True:
        auto_learn_cycle()
        time.sleep(1800)  # 30min
```

CC: 先搜索项目中 `scheduler`、`cron`、`Timer`、`interval` 相关代码，确认现有定时机制，再选择注册方式。

---

## 三、深度学习 7h（完整管道）

### 3.1 触发方式

两种:
1. 飞书发送 "深度学习" → 立即启动
2. 每晚凌晨 1:00 → 自动启动

### 3.2 任务池 + 自主发现

```python
# === 任务池配置 ===
TASK_POOL_PATH = Path(__file__).parent.parent / ".ai-state" / "research_task_pool.yaml"

def _load_task_pool() -> list:
    """加载任务池，返回未完成的任务（按优先级排序）"""
    if not TASK_POOL_PATH.exists():
        return []
    with open(TASK_POOL_PATH, 'r', encoding='utf-8') as f:
        pool = yaml.safe_load(f) or []
    # 过滤已完成的
    return [t for t in pool if not t.get("completed")]

def _save_task_pool(pool: list):
    """保存任务池"""
    with open(TASK_POOL_PATH, 'w', encoding='utf-8') as f:
        yaml.dump(pool, f, allow_unicode=True)

def _mark_task_done(task_id: str):
    """标记任务完成"""
    pool = _load_task_pool()
    for t in pool:
        if t.get("id") == task_id:
            t["completed"] = True
            t["completed_at"] = time.strftime('%Y-%m-%d %H:%M')
    _save_task_pool(pool)

def _discover_new_tasks() -> list:
    """自主发现新研究方向

    基于:
    1. KB 缺口分析（深度版，比自学习更全面）
    2. 产品锚点中未覆盖的技术方向
    3. 竞品动态（最近 KB 中有没有新竞品信息？）
    4. 供应链变化（价格、交期、新供应商）
    """
    # 用 LLM 分析 KB 现状，生成研究建议
    kb_summary = _get_kb_summary()  # 各域条目数、最新/最旧条目、高频关键词

    discover_prompt = (
        f"你是智能骑行头盔项目的研究规划师。\n\n"
        f"## 当前知识库状态\n{kb_summary}\n\n"
        f"## 产品方向\n"
        f"全脸头盔，HUD显示，语音控制，组队骑行，主动安全。\n"
        f"V1 关键技术: OLED+Free Form / Micro LED+树脂衍射光波导（并行路线）\n"
        f"主SoC: Qualcomm AR1 Gen 1\n"
        f"通信: Mesh Intercom\n\n"
        f"## 任务\n"
        f"分析知识库的薄弱环节，生成 3-5 个新研究任务。\n"
        f"每个任务要有明确的研究目标和 6-8 个搜索关键词。\n"
        f"优先级: 1=紧急（影响V1决策）, 2=重要（影响成本/供应链）, 3=储备\n\n"
        f"输出 JSON 数组:\n"
        f'[{{"id": "auto_xxx", "title": "标题", "goal": "研究目标", '
        f'"priority": 1, "searches": ["搜索词1", "搜索词2", ...]}}]\n'
        f"只输出 JSON。"
    )

    result = _call_model("gemini_2_5_flash", discover_prompt,
                          task_type="discovery")
    if result.get("success"):
        try:
            resp = result["response"].strip()
            resp = re.sub(r'^```json\s*', '', resp)
            resp = re.sub(r'\s*```$', '', resp)
            tasks = json.loads(resp)
            if isinstance(tasks, list):
                print(f"  [Discover] 发现 {len(tasks)} 个新方向")
                return tasks
        except:
            pass
    return []
```

### 3.3 7h 窗口调度器

```python
def run_deep_learning(max_hours: float = 7.0, progress_callback=None):
    """深度学习主调度器

    在 max_hours 时间窗口内，持续执行研究任务:
    1. 先从任务池取
    2. 任务池空了 → 自主发现新方向
    3. 每个任务完成后检查剩余时间
    4. 不够跑下一个就收尾
    """
    start_time = time.time()
    deadline = start_time + max_hours * 3600
    completed = []

    print(f"\n{'#'*60}")
    print(f"# 深度学习模式 — {max_hours}h 窗口")
    print(f"# 开始: {time.strftime('%Y-%m-%d %H:%M')}")
    print(f"# 截止: {time.strftime('%Y-%m-%d %H:%M', time.localtime(deadline))}")
    print(f"{'#'*60}")

    if progress_callback:
        progress_callback(f"🎓 深度学习开始 ({max_hours}h 窗口)")

    while True:
        remaining_hours = (deadline - time.time()) / 3600
        if remaining_hours < 0.5:
            print(f"\n[Scheduler] 剩余 {remaining_hours:.1f}h < 0.5h，收尾")
            break

        # 1. 从任务池取
        pool = _load_task_pool()
        task = None
        if pool:
            task = pool[0]  # 取优先级最高的
            print(f"\n[Scheduler] 从任务池取: {task['title']} (剩余 {remaining_hours:.1f}h)")
        else:
            # 2. 自主发现
            print(f"\n[Scheduler] 任务池空，自主发现新方向...")
            new_tasks = _discover_new_tasks()
            if new_tasks:
                # 加入任务池
                existing_pool = _load_task_pool()
                for nt in new_tasks:
                    nt["source"] = "auto_discover"
                    nt["discovered_at"] = time.strftime('%Y-%m-%d %H:%M')
                existing_pool.extend(new_tasks)
                _save_task_pool(existing_pool)
                task = new_tasks[0]
                print(f"  发现 {len(new_tasks)} 个新任务，开始: {task['title']}")
            else:
                print("[Scheduler] 无新任务可发现，结束")
                break

        # 3. 执行（完整五层管道）
        task_start = time.time()

        if progress_callback:
            progress_callback(
                f"📖 [{len(completed)+1}] {task['title']} "
                f"(剩余 {remaining_hours:.1f}h)"
            )

        report = deep_research_one(task, progress_callback=progress_callback)
        task_duration = (time.time() - task_start) / 60

        completed.append({
            "title": task["title"],
            "duration_min": round(task_duration, 1),
            "report_len": len(report)
        })

        _mark_task_done(task.get("id", ""))
        print(f"\n✅ {task['title']} 完成 ({task_duration:.0f}min, {len(report)}字)")

        if progress_callback:
            progress_callback(
                f"✅ {task['title']} ({task_duration:.0f}min)"
            )

        time.sleep(5)

    # 收尾: 运行 KB 治理
    print(f"\n[Scheduler] 任务完成，运行 KB 治理...")
    from scripts.kb_governance import run_governance
    gov_report = run_governance()

    # 汇总
    total_hours = (time.time() - start_time) / 3600
    print(f"\n{'#'*60}")
    print(f"# 深度学习完成")
    print(f"# 耗时: {total_hours:.1f}h / {max_hours}h")
    print(f"# 任务: {len(completed)} 个")
    for c in completed:
        print(f"#   - {c['title']} ({c['duration_min']}min, {c['report_len']}字)")
    print(f"# KB 治理: {gov_report}")
    print(f"{'#'*60}")

    if progress_callback:
        progress_callback(
            f"🎓 深度学习完成: {len(completed)} 个任务, "
            f"{total_hours:.1f}h"
        )
```

### 3.4 飞书触发注册

在飞书 text_router 中注册 "深度学习" 指令:

```python
# 在 text_router.py 的路由逻辑中添加:
if "深度学习" in text or "deep learning" in text.lower():
    # 异步启动（不阻塞飞书回复）
    import threading
    def _run():
        from scripts.tonight_deep_research import run_deep_learning
        run_deep_learning(max_hours=7.0, progress_callback=reply_target)
    threading.Thread(target=_run, daemon=True).start()
    return "🎓 深度学习已启动（7h 窗口），进度将实时推送。"
```

### 3.5 每晚 1:00 自动触发

在调度器中注册（与自学习用同一个调度器）:

```python
# 每晚 1:00 自动启动深度学习
scheduler.add_job(
    lambda: run_deep_learning(max_hours=7.0),
    'cron', hour=1, minute=0, id='deep_learning_nightly'
)
```

---

## 四、KB 治理

### 4.1 新建 `scripts/kb_governance.py`

```python
"""知识库治理 — 定期清理、去重、降级、合并"""

import json
import time
import re
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

from src.tools.knowledge_base import KB_ROOT, get_knowledge_stats

# 治理规则配置
GOVERNANCE_RULES = {
    "stale_days": 60,           # 超过 N 天未更新的条目标记为 stale
    "low_quality_min_chars": 150,  # 内容少于 N 字的条目为低质量
    "dedup_similarity": 0.8,    # 标题相似度超过此值判定为重复
    "max_entries_per_domain": 800,  # 每个 domain 最多 N 条
    "confidence_decay_days": 90,    # medium confidence 超过 N 天降为 low
}


def run_governance() -> str:
    """执行一轮 KB 治理，返回治理报告摘要"""
    print(f"\n{'='*50}")
    print(f"[KB-Gov] 知识库治理开始")

    report = {
        "duplicates_merged": 0,
        "stale_marked": 0,
        "low_quality_removed": 0,
        "confidence_decayed": 0,
        "contradictions_flagged": 0,
    }

    all_entries = _load_all_entries()
    print(f"[KB-Gov] 总条目: {len(all_entries)}")

    # 1. 去重合并
    report["duplicates_merged"] = _deduplicate(all_entries)

    # 2. 低质量清理
    report["low_quality_removed"] = _remove_low_quality(all_entries)

    # 3. 时效性降级
    report["stale_marked"] = _mark_stale(all_entries)
    report["confidence_decayed"] = _decay_confidence(all_entries)

    # 4. 矛盾检测
    report["contradictions_flagged"] = _flag_contradictions(all_entries)

    # 5. 生成健康度报告
    health = _compute_health_score(all_entries)

    summary = (
        f"去重合并 {report['duplicates_merged']} 条 | "
        f"清理低质量 {report['low_quality_removed']} 条 | "
        f"标记过时 {report['stale_marked']} 条 | "
        f"降级 {report['confidence_decayed']} 条 | "
        f"矛盾标记 {report['contradictions_flagged']} 条 | "
        f"健康度 {health}/100"
    )

    print(f"[KB-Gov] {summary}")
    print(f"{'='*50}")

    # 保存治理日志
    log_path = KB_ROOT.parent / "kb_governance_log.jsonl"
    with open(log_path, 'a', encoding='utf-8') as f:
        f.write(json.dumps({
            "timestamp": time.strftime('%Y-%m-%d %H:%M'),
            "report": report,
            "health": health,
            "total_entries": len(all_entries),
        }, ensure_ascii=False) + "\n")

    return summary


def _load_all_entries() -> list:
    """加载所有 KB 条目"""
    entries = []
    for f in KB_ROOT.rglob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            data["_path"] = str(f)
            entries.append(data)
        except:
            continue
    return entries


def _deduplicate(entries: list) -> int:
    """基于标题相似度去重

    策略: 保留 confidence 更高的、更新的那条
    """
    merged = 0
    titles = {}
    for entry in entries:
        title = entry.get("title", "").strip().lower()
        # 简单去重: 完全相同的标题
        if title in titles:
            existing = titles[title]
            # 保留 confidence 更高的
            conf_order = {"authoritative": 4, "high": 3, "medium": 2, "low": 1}
            if conf_order.get(entry.get("confidence"), 0) > conf_order.get(existing.get("confidence"), 0):
                # 新条目更好，删除旧的
                _safe_delete(existing["_path"])
                titles[title] = entry
            else:
                _safe_delete(entry["_path"])
            merged += 1
        else:
            titles[title] = entry
    return merged


def _remove_low_quality(entries: list) -> int:
    """删除低质量条目

    标准:
    - 内容 < 150 字
    - 无任何具体数据（数字、型号、价格）
    - 标题太泛（"智能头盔"、"市场分析"）
    - confidence = "low" 且 > 60 天未更新
    """
    removed = 0
    min_chars = GOVERNANCE_RULES["low_quality_min_chars"]

    generic_titles = {"智能头盔", "骑行头盔", "头盔方案", "技术方案", "市场分析",
                      "智能摩托车头盔", "摩托车头盔"}

    for entry in entries:
        content = entry.get("content", "")
        title = entry.get("title", "").strip()
        confidence = entry.get("confidence", "")

        should_remove = False
        reasons = []

        # 内容太短
        if len(content) < min_chars:
            should_remove = True
            reasons.append(f"内容<{min_chars}字")

        # 标题太泛
        if title in generic_titles:
            should_remove = True
            reasons.append("标题太泛")

        # low confidence + 老旧
        if confidence == "low":
            created = entry.get("created_at", "")
            if created:
                try:
                    age = (datetime.now() - datetime.fromisoformat(created)).days
                    if age > 60:
                        should_remove = True
                        reasons.append(f"low+{age}天")
                except:
                    pass

        if should_remove:
            # 不删除 authoritative 或 internal 标签的条目
            tags = entry.get("tags", [])
            if "internal" in tags or "anchor" in tags or confidence == "authoritative":
                continue
            _safe_delete(entry["_path"])
            removed += 1
            print(f"  [Prune] {title[:40]}... — {', '.join(reasons)}")

    return removed


def _mark_stale(entries: list) -> int:
    """标记过时条目（添加 stale 标签）"""
    stale_days = GOVERNANCE_RULES["stale_days"]
    cutoff = datetime.now() - timedelta(days=stale_days)
    marked = 0

    for entry in entries:
        created = entry.get("created_at", "")
        tags = entry.get("tags", [])

        if "stale" in tags or "internal" in tags or "anchor" in tags:
            continue

        if created:
            try:
                if datetime.fromisoformat(created) < cutoff:
                    tags.append("stale")
                    _update_entry(entry["_path"], {"tags": tags})
                    marked += 1
            except:
                continue

    return marked


def _decay_confidence(entries: list) -> int:
    """confidence 时间衰减: medium 超过 90 天降为 low"""
    decay_days = GOVERNANCE_RULES["confidence_decay_days"]
    cutoff = datetime.now() - timedelta(days=decay_days)
    decayed = 0

    for entry in entries:
        if entry.get("confidence") != "medium":
            continue

        tags = entry.get("tags", [])
        if "internal" in tags or "anchor" in tags:
            continue

        created = entry.get("created_at", "")
        if created:
            try:
                if datetime.fromisoformat(created) < cutoff:
                    _update_entry(entry["_path"], {"confidence": "low"})
                    decayed += 1
            except:
                continue

    return decayed


def _flag_contradictions(entries: list) -> int:
    """检测同一产品/参数的矛盾数据

    简单规则: 同一个产品名出现在多个条目中，
    如果关键参数（价格、重量、分辨率等）不一致，标记矛盾
    """
    # 按产品名分组
    product_entries = defaultdict(list)
    for entry in entries:
        title = entry.get("title", "")
        # 提取产品名（简单启发式）
        for kw in ["Goertek", "歌尔", "Luxshare", "立讯", "Cardo", "Sena",
                    "OLED", "Micro LED", "光波导", "waveguide", "QCC", "BES",
                    "AR1", "nRF"]:
            if kw.lower() in title.lower():
                product_entries[kw].append(entry)

    flagged = 0
    for product, group in product_entries.items():
        if len(group) < 2:
            continue
        # 检查是否有数值矛盾（简化: 检查同一个度量单位的不同值）
        # 完整实现需要用 LLM，这里先做标记
        for entry in group:
            tags = entry.get("tags", [])
            if "needs_reconciliation" not in tags and len(group) >= 3:
                tags.append("needs_reconciliation")
                _update_entry(entry["_path"], {"tags": tags})
                flagged += 1

    return flagged


def _compute_health_score(entries: list) -> int:
    """计算知识库健康度 (0-100)

    维度:
    - 条目数量 (20分): 500-3000 之间得满分
    - 时效性 (20分): stale 占比 < 10% 满分
    - 质量分布 (20分): high+authoritative > 50% 满分
    - 域覆盖 (20分): 5 个主域都有条目满分
    - 矛盾率 (20分): needs_reconciliation < 5% 满分
    """
    total = len(entries)
    if total == 0:
        return 0

    score = 0

    # 数量
    if 500 <= total <= 3000:
        score += 20
    elif total > 3000:
        score += max(0, 20 - (total - 3000) // 100)
    else:
        score += total * 20 // 500

    # 时效性
    stale_count = sum(1 for e in entries if "stale" in e.get("tags", []))
    stale_ratio = stale_count / total
    score += max(0, int(20 * (1 - stale_ratio / 0.2)))

    # 质量分布
    high_count = sum(1 for e in entries
                     if e.get("confidence") in ("high", "authoritative"))
    high_ratio = high_count / total
    score += min(20, int(high_ratio * 40))

    # 域覆盖
    domains = set(e.get("domain", "") for e in entries)
    required_domains = {"components", "competitors", "standards", "lessons"}
    covered = len(required_domains & domains)
    score += covered * 5

    # 矛盾率
    contradiction_count = sum(1 for e in entries
                              if "needs_reconciliation" in e.get("tags", []))
    contra_ratio = contradiction_count / total
    score += max(0, int(20 * (1 - contra_ratio / 0.1)))

    return min(100, score)


def _safe_delete(path: str):
    """安全删除条目文件"""
    try:
        Path(path).unlink(missing_ok=True)
    except:
        pass


def _update_entry(path: str, updates: dict):
    """更新条目的指定字段"""
    try:
        p = Path(path)
        data = json.loads(p.read_text(encoding="utf-8"))
        data.update(updates)
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except:
        pass
```

### 4.2 触发时机

- 每次深度学习结束后自动运行一次
- 每周日凌晨 8:00 独立运行一次
- 飞书发送 "KB治理" 手动触发

```python
# 调度器注册
scheduler.add_job(run_governance, 'cron', day_of_week='sun', hour=8, id='kb_governance')
```

---

## 五、学习方向的广度和深度

### 5.1 任务池初始内容

创建 `.ai-state/research_task_pool.yaml`:

```yaml
# 广度: 覆盖产品各核心模块
- id: "supply_chain_optical"
  title: "光学方案供应链深度调研"
  goal: "OLED+Free Form vs Micro LED+衍射光波导的完整供应链对比，含良率、交期、MOQ、BOM"
  priority: 1
  searches:
    - "motorcycle helmet HUD optical module supplier BOM cost 2026"
    - "OLED micro display free form lens supplier price comparison"
    - "Micro LED resin diffractive waveguide supplier 量产良率 交期"
    - "JBD Micro LED display module specs price MOQ 2026"
    - "Sony ECX 系列 OLED microdisplay specs comparison"
    - "珑璟光电 灵犀微光 谷东科技 光波导 参数 价格"
    - "AR HUD optical engine comparison waveguide birdbath freeform 2026"
    - "helmet HUD display reliability outdoor sunlight brightness nits"

- id: "supply_chain_audio"
  title: "声学方案供应链深度调研"
  goal: "骑行头盔用扬声器/麦克风/ANC方案的供应商对比，含风噪处理能力实测"
  priority: 1
  searches:
    - "骨传导扬声器 头盔 供应商 韶音 歌尔 瑞声 参数 价格 2026"
    - "helmet speaker wind noise cancellation MEMS microphone"
    - "ANC chipset BES2700 QCC5181 comparison motorcycle helmet"
    - "smart helmet audio solution IP67 waterproof speaker"

- id: "supply_chain_soc"
  title: "主SoC选型验证"
  goal: "Qualcomm AR1 Gen 1 的实际性能、功耗、散热、供货情况验证"
  priority: 1
  searches:
    - "Qualcomm AR1 Gen 1 XR platform specs power consumption thermal"
    - "Qualcomm AR1 供货 交期 最小起订量 方案商 2026"
    - "motorcycle helmet SoC alternatives MediaTek Genio Amlogic"

- id: "competitor_deep_dive"
  title: "竞品深度拆解"
  goal: "Cardo Packtalk/Sena/LIVALL/Jarvish 的硬件拆解、BOM估算、用户口碑"
  priority: 2
  searches:
    - "Cardo Packtalk Edge teardown BOM cost analysis"
    - "Sena 50S vs Cardo comparison 2026 user review"
    - "LIVALL smart helmet review problems issues"
    - "Jarvish X-AR helmet review 实测 评价 问题"
    - "智能头盔 小红书 用户评测 吐槽 2026"

- id: "certification_roadmap"
  title: "安全认证路线图"
  goal: "DOT/ECE/SNELL认证流程、周期、成本，以及HUD对认证的影响"
  priority: 2
  searches:
    - "motorcycle helmet DOT ECE certification process cost timeline"
    - "helmet HUD certification impact ECE 22.06"
    - "SNELL认证 费用 周期 测试项目 2026"

# 深度: 技术专题
- id: "mesh_intercom_protocol"
  title: "Mesh Intercom 协议深度分析"
  goal: "Cardo DMC vs 自研Mesh的技术可行性、延迟、功耗、频段限制"
  priority: 2
  searches:
    - "Cardo DMC mesh intercom protocol technical analysis"
    - "Bluetooth mesh vs proprietary mesh motorcycle intercom latency"
    - "mesh network 骑行 对讲 功耗 延迟 频段"

- id: "thermal_management"
  title: "头盔散热方案调研"
  goal: "SoC+显示模组+电池在全封闭头盔内的散热方案"
  priority: 3
  searches:
    - "smart helmet thermal management heat dissipation solution"
    - "AR glasses thermal design copper heat pipe graphene"
    - "头盔内 散热 方案 石墨片 热管 仿真"
```

### 5.2 自主发现的方向引导

在 `_discover_new_tasks()` 的 prompt 中，注入方向引导:

```
研究方向应覆盖:
- 广度: 供应链每个环节（光学、声学、通信、SoC、结构、认证、用户体验）
- 深度: 每个环节的 top 3 供应商的详细参数、价格、交期、良率
- 时效: 关注 2025-2026 年的最新动态（新产品发布、价格变化、技术突破）
- 实用: 每条知识要能直接用于决策（选A还是选B？V1先做什么？）
```

---

## 六、执行顺序

1. 确认现有定时机制（CC 搜索项目中的 scheduler 代码）
2. 创建 `scripts/kb_governance.py`
3. 创建 `.ai-state/research_task_pool.yaml`
4. 改造 `scripts/auto_learn.py`（或新建）
5. 在 `tonight_deep_research.py` 中添加 `run_deep_learning()` 调度器
6. 在飞书 handler 中注册 "深度学习" 指令
7. 注册定时任务（自学习 30min + 深度学习每晚1点 + KB治理每周日）

```bash
git add -A && git commit -m "feat: learning system — auto-learn 30min, deep-learn 7h, KB governance"
```

**不要重启服务，Leo 手动重启。**
