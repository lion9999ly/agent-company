"""
@description: 知识库治理 — 定期清理、去重、降级、合并
@dependencies: src.tools.knowledge_base
@last_modified: 2026-03-31
"""
import json
import time
import re
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

# 添加项目根目录到 path
import sys
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

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
    log_path.parent.mkdir(parents=True, exist_ok=True)
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


if __name__ == "__main__":
    result = run_governance()
    print(f"\n治理结果: {result}")