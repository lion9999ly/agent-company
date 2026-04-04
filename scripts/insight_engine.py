"""主动洞察 — 发现异常/风险/机会时推送飞书
@description: 从研究报告中自动检测值得主动推送的洞察
@dependencies: 无
@last_modified: 2026-04-04
"""
import json, re, time
from pathlib import Path


def scan_for_insights(report: str, task_title: str) -> list:
    """从研究报告中检测值得主动推送的洞察"""
    insights = []

    # 检测关键词模式
    alert_patterns = [
        (r"(?:新品|发布|上市|推出).*(?:Cardo|Sena|LIVALL|Jarvish|Shoei)", "竞品动态"),
        (r"(?:涨价|降价|缺货|停产|召回)", "供应链风险"),
        (r"(?:专利|侵权|诉讼|禁令)", "知产风险"),
        (r"(?:突破|革新|新技术|首次|全球首)", "技术机会"),
        (r"(?:矛盾|不一致|与.*不符)", "数据矛盾"),
    ]

    for pattern, category in alert_patterns:
        matches = re.findall(pattern, report)
        if matches:
            insights.append({
                "category": category,
                "matches": matches[:3],
                "task": task_title,
                "timestamp": time.strftime('%Y-%m-%d %H:%M'),
            })

    return insights


def format_insight_alert(insight: dict) -> str:
    """格式化洞察为飞书消息"""
    icons = {
        "竞品动态": "🏁", "供应链风险": "⚠️", "知产风险": "⚖️",
        "技术机会": "💡", "数据矛盾": "🔄"
    }
    icon = icons.get(insight["category"], "📢")
    return f"{icon} 主动洞察 [{insight['category']}]\n来源: {insight['task']}\n详情: {', '.join(insight['matches'][:3])}"


def process_report_for_insights(report: str, task_title: str, send_reply=None, reply_target=None):
    """处理报告并发送洞察通知"""
    insights = scan_for_insights(report, task_title)
    if insights and send_reply and reply_target:
        for insight in insights[:3]:  # 最多发 3 条
            alert = format_insight_alert(insight)
            send_reply(reply_target, alert)
    return insights


if __name__ == "__main__":
    # 测试
    test_report = "Cardo发布了新款Packtalk Edge，采用了新技术突破，但与之前数据矛盾。"
    insights = scan_for_insights(test_report, "竞品分析")
    for i in insights:
        print(format_insight_alert(i))