"""
@description: 每日自学习循环 - Agent 主动追踪行业前沿，更新知识库
@dependencies: src.tools.tool_registry, src.tools.knowledge_base
@last_modified: 2026-03-21
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime
from src.tools.tool_registry import get_tool_registry
from src.tools.knowledge_base import add_knowledge, get_knowledge_stats

# 每日搜索主题
DAILY_TOPICS = [
    {"query": "smart cycling helmet new product launch 2026", "domain": "competitors", "tags": ["竞品", "新品"]},
    {"query": "智能骑行头盔 最新产品 2026", "domain": "competitors", "tags": ["竞品", "新品", "国内"]},
    {"query": "cycling helmet safety technology trend 2026", "domain": "components", "tags": ["技术", "趋势"]},
    {"query": "Multi-Agent LangGraph best practices 2026", "domain": "lessons", "tags": ["AI", "最佳实践", "LangGraph"]},
]


def run_daily_learning() -> str:
    """执行每日学习循环，返回学习简报"""
    registry = get_tool_registry()
    report_lines = [f"📚 每日学习简报 ({datetime.now().strftime('%Y-%m-%d %H:%M')})"]
    new_count = 0

    for topic in DAILY_TOPICS:
        result = registry.call("deep_research", topic["query"])
        if not result.get("success"):
            report_lines.append(f"❌ {topic['query'][:30]}... 搜索失败")
            continue

        data = result["data"]
        if len(data) < 50:
            report_lines.append(f"⚠️ {topic['query'][:30]}... 内容过少，跳过")
            continue

        # 提炼摘要（取前800字作为知识条目）
        summary = data[:800]
        title = f"每日学习_{datetime.now().strftime('%m%d')}_{topic['domain']}_{new_count}"
        filepath = add_knowledge(
            title=title,
            domain=topic["domain"],
            content=summary,
            tags=topic["tags"],
            source="daily_learning",
            confidence="medium"
        )
        new_count += 1
        report_lines.append(f"✅ {topic['query'][:40]}... → {topic['domain']}/{Path(filepath).name}")

    stats = get_knowledge_stats()
    report_lines.append(f"\n📊 知识库现状: {stats}")
    report_lines.append(f"📝 本次新增: {new_count} 条")

    report = "\n".join(report_lines)
    print(report)
    return report


if __name__ == "__main__":
    run_daily_learning()