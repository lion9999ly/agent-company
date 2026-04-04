"""外部信息源监控 — 竞品动态和行业新闻
@description: 定期扫描竞品和行业关键词获取最新动态
@dependencies: model_gateway
@last_modified: 2026-04-04
"""
import time, json
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

MONITOR_CONFIG = {
    "competitors": ["Cardo Packtalk", "Sena 50S", "LIVALL MC1", "Jarvish X-AR", "Shoei smart helmet"],
    "industry": ["motorcycle helmet technology 2026", "AR HUD helmet", "骑行头盔 智能"],
    "check_interval_hours": 24,
}


def run_external_scan(gateway, progress_callback=None):
    """执行一轮外部信息扫描"""
    findings = []

    for query in MONITOR_CONFIG["competitors"] + MONITOR_CONFIG["industry"]:
        if progress_callback:
            progress_callback(f"扫描: {query}")

        result = gateway.call("doubao_seed_pro", query,
                              "搜索最近一周的最新动态、新品发布、价格变化。只报告新信息。",
                              "external_monitor")
        if result.get("success") and len(result.get("response", "")) > 100:
            findings.append({"query": query, "finding": result["response"][:500]})

    return findings


def save_monitor_results(findings: list):
    """保存扫描结果"""
    monitor_path = PROJECT_ROOT / ".ai-state" / "external_monitor_results.jsonl"
    monitor_path.parent.mkdir(parents=True, exist_ok=True)

    entry = {
        "timestamp": time.strftime('%Y-%m-%d %H:%M'),
        "findings": findings,
    }
    with open(monitor_path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def check_guardrails(findings: list):
    """检查扫描结果是否触发护栏"""
    try:
        from scripts.guardrail_engine import check_guardrails
        alerts = []
        for f in findings:
            alert = check_guardrails(f.get("finding", ""), source="external_monitor")
            if alert:
                alerts.append(alert)
        return alerts
    except ImportError:
        return []


if __name__ == "__main__":
    print("外部监控配置:", MONITOR_CONFIG)