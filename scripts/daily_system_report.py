"""系统运行日报 — 生成系统运行日报
@description: 系统运行日报（KB统计/报告数/学习记录/决策树进度）
@dependencies: knowledge_base, feishu_sdk_client
@last_modified: 2026-04-05
"""
import json
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
LEO_OPEN_ID = "ou_8e5e4f183e9eca4241378e96bac3a751"


def get_kb_stats() -> dict:
    """获取知识库统计"""
    kb_dir = PROJECT_ROOT / ".ai-state" / "knowledge"
    stats = {"total_files": 0, "by_category": {}, "recent_files": []}

    if kb_dir.exists():
        all_files = []
        for category_dir in kb_dir.iterdir():
            if category_dir.is_dir():
                files = list(category_dir.glob("*.json"))
                stats["by_category"][category_dir.name] = len(files)
                stats["total_files"] += len(files)
                all_files.extend(files)

        # 最近文件
        all_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
        stats["recent_files"] = [f.name[:50] for f in all_files[:5]]

    return stats


def get_report_stats() -> dict:
    """获取报告统计"""
    report_dir = PROJECT_ROOT / ".ai-state" / "reports"
    stats = {"total": 0, "today": 0, "recent": []}

    if report_dir.exists():
        files = list(report_dir.glob("*.md"))
        stats["total"] = len(files)

        today = datetime.now().strftime("%Y-%m-%d")
        for f in files:
            if today in f.name:
                stats["today"] += 1

        # 最近报告
        files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
        stats["recent"] = [f.name[:50] for f in files[:5]]

    return stats


def get_learning_stats() -> dict:
    """获取学习记录统计"""
    learning_path = PROJECT_ROOT / ".ai-state" / "search_learning.jsonl"
    stats = {"total": 0, "today": 0}

    if learning_path.exists():
        try:
            lines = learning_path.read_text(encoding='utf-8').strip().split("\n")
            stats["total"] = len(lines)

            today = datetime.now().strftime("%Y-%m-%d")
            for line in lines[-100:]:  # 只检查最近100条
                if today in line:
                    stats["today"] += 1
        except:
            pass

    return stats


def get_decision_tree_progress() -> dict:
    """获取决策树进度"""
    tree_path = PROJECT_ROOT / ".ai-state" / "product_decision_tree.yaml"
    stats = {"exists": False, "nodes": 0, "decisions": 0}

    if tree_path.exists():
        stats["exists"] = True
        try:
            content = tree_path.read_text(encoding='utf-8')
            # 简单统计
            stats["nodes"] = content.count("node:")
            stats["decisions"] = content.count("decision:")
        except:
            pass

    return stats


def get_usage_stats() -> dict:
    """获取用量统计"""
    usage_path = PROJECT_ROOT / ".ai-state" / "usage_logs" / "usage_records.jsonl"
    stats = {"total_calls": 0, "today_calls": 0}

    if usage_path.exists():
        try:
            lines = usage_path.read_text(encoding='utf-8').strip().split("\n")
            stats["total_calls"] = len(lines)

            today = datetime.now().strftime("%Y-%m-%d")
            for line in lines[-200:]:
                if today in line:
                    stats["today_calls"] += 1
        except:
            pass

    return stats


def generate_daily_report() -> str:
    """生成日报"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    kb_stats = get_kb_stats()
    report_stats = get_report_stats()
    learning_stats = get_learning_stats()
    decision_stats = get_decision_tree_progress()
    usage_stats = get_usage_stats()

    lines = [
        f"# 系统运行日报 — {now}",
        "",
        "## 知识库统计",
        f"- 总条目: {kb_stats['total_files']}",
        "",
        "### 分类统计",
    ]

    for cat, count in kb_stats["by_category"].items():
        lines.append(f"- {cat}: {count}")

    lines.extend([
        "",
        "## 报告统计",
        f"- 总报告: {report_stats['total']}",
        f"- 今日新增: {report_stats['today']}",
        "",
        "## 学习记录",
        f"- 总记录: {learning_stats['total']}",
        f"- 今日新增: {learning_stats['today']}",
        "",
        "## 决策树进度",
        f"- 文件存在: {'是' if decision_stats['exists'] else '否'}",
        f"- 节点数: {decision_stats['nodes']}",
        f"- 决策数: {decision_stats['decisions']}",
        "",
        "## API 调用统计",
        f"- 总调用: {usage_stats['total_calls']}",
        f"- 今日调用: {usage_stats['today_calls']}",
        "",
        "---",
        f"*报告生成时间: {now}*"
    ])

    return "\n".join(lines)


def send_daily_report():
    """发送日报到飞书"""
    report = generate_daily_report()

    # 保存到文件
    report_path = PROJECT_ROOT / ".ai-state" / "reports" / f"daily_{datetime.now().strftime('%Y%m%d')}.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding='utf-8')

    # 发送到飞书
    try:
        from scripts.feishu_sdk_client import send_reply
        send_reply(LEO_OPEN_ID, report, id_type="open_id")
        print(f"[DailyReport] 已发送日报到飞书")
    except Exception as e:
        print(f"[DailyReport] 发送失败: {e}")

    return report


if __name__ == "__main__":
    report = send_daily_report()
    print(report)