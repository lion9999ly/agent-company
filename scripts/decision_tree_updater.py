"""
@description: 研究结果自动回流到决策树
@dependencies: yaml, json, re, time, pathlib
@last_modified: 2026-04-04
"""
import yaml
import json
import re
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
DT_PATH = PROJECT_ROOT / ".ai-state" / "product_decision_tree.yaml"


def update_decision_tree_from_report(report: str, task_title: str) -> bool:
    """检查报告中的关键发现是否填充了决策树的 blocking_knowledge

    Args:
        report: 研究报告全文
        task_title: 任务标题

    Returns:
        是否有更新
    """
    if not DT_PATH.exists():
        return False

    try:
        dt = yaml.safe_load(DT_PATH.read_text(encoding='utf-8'))
    except:
        return False

    updated = False

    for decision in dt.get("decisions", []):
        if decision.get("status") != "open":
            continue

        for bk in decision.get("blocking_knowledge", []):
            # 检查报告中是否包含相关信息
            # 提取关键词：中文词组 + 英文单词
            bk_keywords = set(re.findall(r'[\u4e00-\u9fff]{2,4}|[A-Z][a-z]+|[A-Z]{2,}', bk))
            report_lower = report.lower()
            matches = sum(1 for kw in bk_keywords if kw.lower() in report_lower)

            if matches >= 2:  # 至少匹配 2 个关键词
                # 检查是否已 resolved
                existing = decision.get("resolved_knowledge", [])
                already = any(bk[:20].lower() in r.get("knowledge", "").lower() for r in existing)
                if not already:
                    if "resolved_knowledge" not in decision:
                        decision["resolved_knowledge"] = []
                    # 从报告中提取相关摘要
                    decision["resolved_knowledge"].append({
                        "knowledge": f"来自研究 '{task_title}' 的相关发现（自动匹配）",
                        "source": f"deep_learn_{task_title}",
                        "resolved_at": time.strftime('%Y-%m-%d'),
                    })
                    updated = True
                    print(f"  [DT-Update] {decision['id']}: resolved '{bk[:40]}...'")

    if updated:
        DT_PATH.write_text(yaml.dump(dt, allow_unicode=True, default_flow_style=False), encoding='utf-8')

    return updated


def get_blocking_status(decision_id: str) -> dict:
    """获取单个决策的阻塞状态

    Args:
        decision_id: 决策 ID（如 'v1_display'）

    Returns:
        dict with blocking_knowledge, resolved_knowledge, ratio
    """
    if not DT_PATH.exists():
        return {}

    try:
        dt = yaml.safe_load(DT_PATH.read_text(encoding='utf-8'))
    except:
        return {}

    for d in dt.get("decisions", []):
        if d.get("id") == decision_id:
            total = len(d.get("blocking_knowledge", []))
            resolved = len(d.get("resolved_knowledge", []))
            return {
                "id": decision_id,
                "status": d.get("status"),
                "blocking_knowledge": d.get("blocking_knowledge", []),
                "resolved_knowledge": d.get("resolved_knowledge", []),
                "total": total,
                "resolved": resolved,
                "ratio": resolved / max(total, 1)
            }

    return {}


if __name__ == "__main__":
    # 测试用例
    test_report = """
    OLED 微显示面板供应商分析:
    Sony ECX 系列交期约 8 周，MOQ 1000 片。
    京东方 OLED 微显示面板交期约 6 周，MOQ 500 片。
    """
    result = update_decision_tree_from_report(test_report, "test_task")
    print(f"Updated: {result}")