"""信任指数 — 按领域追踪系统可信度
@description: 领域级别的信任度追踪，低于阈值需寻求确认
@dependencies: 无
@last_modified: 2026-04-04
"""
import json, time
from pathlib import Path
from collections import defaultdict

PROJECT_ROOT = Path(__file__).parent.parent
TRUST_PATH = PROJECT_ROOT / ".ai-state" / "trust_index.json"

DOMAINS = ["光学方案", "成本估算", "供应商评价", "技术参数", "市场分析", "用户洞察", "竞品分析"]


def load_trust() -> dict:
    """加载信任指数"""
    if TRUST_PATH.exists():
        try:
            return json.loads(TRUST_PATH.read_text(encoding='utf-8'))
        except json.JSONDecodeError:
            pass
    return {d: {"score": 0.5, "samples": 0, "correct": 0} for d in DOMAINS}


def update_trust(domain: str, is_accurate: bool):
    """更新某领域的信任分数"""
    trust = load_trust()
    if domain not in trust:
        trust[domain] = {"score": 0.5, "samples": 0, "correct": 0}
    t = trust[domain]
    t["samples"] += 1
    if is_accurate:
        t["correct"] += 1
    t["score"] = t["correct"] / max(t["samples"], 1)
    TRUST_PATH.write_text(json.dumps(trust, ensure_ascii=False, indent=2), encoding='utf-8')


def get_trust_report() -> str:
    """生成信任指数报告"""
    trust = load_trust()
    lines = ["🎯 信任指数\n"]
    for domain, t in sorted(trust.items(), key=lambda x: x[1]["score"], reverse=True):
        bar = "█" * int(t["score"] * 10) + "░" * (10 - int(t["score"] * 10))
        lines.append(f"  {bar} {t['score']:.0%} {domain} ({t['samples']} 样本)")
    return "\n".join(lines)


def should_seek_confirmation(domain: str) -> bool:
    """信任度低于 60% 的领域需要寻求确认"""
    trust = load_trust()
    return trust.get(domain, {}).get("score", 0.5) < 0.6


def get_low_confidence_domains() -> list:
    """获取低置信度领域"""
    trust = load_trust()
    return [d for d, t in trust.items() if t.get("score", 0.5) < 0.6]


def reset_trust():
    """重置信任指数"""
    trust = {d: {"score": 0.5, "samples": 0, "correct": 0} for d in DOMAINS}
    TRUST_PATH.write_text(json.dumps(trust, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == "__main__":
    # 初始化
    trust = load_trust()
    TRUST_PATH.write_text(json.dumps(trust, ensure_ascii=False, indent=2), encoding='utf-8')
    print(get_trust_report())