"""
Phase 0.3 — 大修后基线快照
运行方式: python scripts/kb_baseline_snapshot.py

功能：扫描知识库，记录所有质量指标，保存为基线 JSON。
后续可用于对比改善幅度。
"""

import json
from pathlib import Path
from datetime import datetime
from collections import Counter

ROOT = Path(__file__).resolve().parent.parent
KB_ROOT = ROOT / ".ai-state" / "knowledge"
OUTPUT = ROOT / ".ai-state" / "baseline_20260326.json"


def scan():
    stats = {
        "timestamp": datetime.now().isoformat(),
        "label": "post_overhaul_day10",
        "total": 0,
        "by_domain": {},
        "by_confidence": Counter(),
        "by_source_type": Counter(),
        "depth": {"shallow_lt50": 0, "thin_50_150": 0, "medium_150_300": 0, "deep_gt300": 0},
        "tags_summary": Counter(),
        "speculative_count": 0,
        "anchor_count": 0,
        "internal_count": 0,
        "decision_tree_count": 0,
        "pending_research_count": 0,
        "report_count": 0,
        "critic_rule_count": 0,
        "evolution_count": 0,
    }

    if not KB_ROOT.exists():
        print("[ERROR] KB not found")
        return stats

    for jf in KB_ROOT.rglob("*.json"):
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
        except Exception:
            continue

        stats["total"] += 1
        domain = jf.parent.name
        stats["by_domain"][domain] = stats["by_domain"].get(domain, 0) + 1

        content = data.get("content", "")
        clen = len(content.strip())
        conf = data.get("confidence", "unknown")
        tags = data.get("tags", [])
        source = data.get("source", "unknown").split(":")[0]

        stats["by_confidence"][conf] += 1
        stats["by_source_type"][source] += 1

        if clen < 50:
            stats["depth"]["shallow_lt50"] += 1
        elif clen < 150:
            stats["depth"]["thin_50_150"] += 1
        elif clen < 300:
            stats["depth"]["medium_150_300"] += 1
        else:
            stats["depth"]["deep_gt300"] += 1

        for t in tags:
            stats["tags_summary"][t] += 1

        if "speculative" in tags:
            stats["speculative_count"] += 1
        if "anchor" in tags:
            stats["anchor_count"] += 1
        if "internal" in tags:
            stats["internal_count"] += 1
        if "decision_tree" in tags:
            stats["decision_tree_count"] += 1
        if "pending_research" in tags:
            stats["pending_research_count"] += 1
        if "critic_rule" in tags:
            stats["critic_rule_count"] += 1
        if "evolution" in tags:
            stats["evolution_count"] += 1
        if data.get("type") == "report" or "REPORT_" in jf.name:
            stats["report_count"] += 1

    # Counter → dict for JSON
    stats["by_confidence"] = dict(stats["by_confidence"])
    stats["by_source_type"] = dict(stats["by_source_type"])
    stats["tags_summary"] = dict(stats["tags_summary"].most_common(30))

    return stats


def main():
    print("=" * 50)
    print("[Phase 0.3] 基线快照")
    print("=" * 50)

    stats = scan()

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n总量: {stats['total']}")
    print(f"分布: {json.dumps(stats['by_domain'], ensure_ascii=False)}")
    print(f"\n深度:")
    print(f"  <50字:   {stats['depth']['shallow_lt50']}")
    print(f"  50-150:  {stats['depth']['thin_50_150']}")
    print(f"  150-300: {stats['depth']['medium_150_300']}")
    print(f"  >300:    {stats['depth']['deep_gt300']}")
    print(f"\n可信度: {json.dumps(stats['by_confidence'], ensure_ascii=False)}")
    print(f"\n特殊标记:")
    print(f"  anchor:           {stats['anchor_count']}")
    print(f"  internal:         {stats['internal_count']}")
    print(f"  decision_tree:    {stats['decision_tree_count']}")
    print(f"  speculative:      {stats['speculative_count']}")
    print(f"  evolution:        {stats['evolution_count']}")
    print(f"  critic_rule:      {stats['critic_rule_count']}")
    print(f"  pending_research: {stats['pending_research_count']}")
    print(f"  report:           {stats['report_count']}")
    print(f"\n[已保存] {OUTPUT}")


if __name__ == "__main__":
    main()
