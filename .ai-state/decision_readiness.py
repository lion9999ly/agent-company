"""
@description: 决策就绪检测 - 扫描决策树各决策点的知识充分度
@dependencies: yaml, pathlib
@last_modified: 2026-04-04
"""
import yaml
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent


def check_decision_readiness() -> str:
    """扫描决策树，返回各决策点的知识充分度

    Returns:
        格式化的决策就绪度文本，若无决策则返回空字符串
    """
    dt_path = PROJECT_ROOT / ".ai-state" / "product_decision_tree.yaml"
    if not dt_path.exists():
        return ""

    try:
        dt = yaml.safe_load(dt_path.read_text(encoding='utf-8'))
    except:
        return ""

    lines = []
    for d in dt.get("decisions", []):
        if d.get("status") != "open":
            continue

        total = len(d.get("blocking_knowledge", []))
        resolved = len(d.get("resolved_knowledge", []))

        if total == 0:
            continue

        ratio = resolved / total
        icon = "🟢" if ratio >= 0.8 else "🟡" if ratio >= 0.5 else "🔴"

        question = d.get("question", "")
        line = f"  {icon} {question[:50]} — {resolved}/{total}"
        if ratio >= 0.8:
            line += " ← 建议做决定"
        lines.append(line)

    if lines:
        return "📌 决策就绪度\n" + "\n".join(lines)
    return ""


def get_decision_summary() -> dict:
    """获取决策树摘要数据

    Returns:
        dict with open_count, ready_count, blocked_count
    """
    dt_path = PROJECT_ROOT / ".ai-state" / "product_decision_tree.yaml"
    if not dt_path.exists():
        return {"open_count": 0, "ready_count": 0, "blocked_count": 0}

    try:
        dt = yaml.safe_load(dt_path.read_text(encoding='utf-8'))
    except:
        return {"open_count": 0, "ready_count": 0, "blocked_count": 0}

    open_count = 0
    ready_count = 0  # resolved >= 80%
    blocked_count = 0  # resolved < 50%

    for d in dt.get("decisions", []):
        if d.get("status") != "open":
            continue

        open_count += 1
        total = len(d.get("blocking_knowledge", []))
        resolved = len(d.get("resolved_knowledge", []))

        if total == 0:
            ready_count += 1
            continue

        ratio = resolved / total
        if ratio >= 0.8:
            ready_count += 1
        elif ratio < 0.5:
            blocked_count += 1

    return {
        "open_count": open_count,
        "ready_count": ready_count,
        "blocked_count": blocked_count
    }


if __name__ == "__main__":
    print(check_decision_readiness())
    print("\nSummary:", get_decision_summary())