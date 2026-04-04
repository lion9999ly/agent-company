"""ROI 度量 — 追踪系统产出的可量化指标
@description: 记录和生成 ROI 指标报告
@dependencies: 无
@last_modified: 2026-04-04
"""
import json, time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
ROI_PATH = PROJECT_ROOT / ".ai-state" / "roi_metrics.jsonl"


def record_metric(metric_type: str, value: float, description: str = ""):
    """记录一条 ROI 指标"""
    entry = {
        "timestamp": time.strftime('%Y-%m-%d %H:%M'),
        "type": metric_type,
        "value": value,
        "description": description
    }
    ROI_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(ROI_PATH, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def generate_roi_report() -> str:
    """生成 ROI 报告"""
    if not ROI_PATH.exists():
        return "暂无 ROI 数据"

    metrics = {}
    for line in ROI_PATH.read_text(encoding='utf-8').strip().split('\n'):
        try:
            e = json.loads(line)
            t = e["type"]
            if t not in metrics:
                metrics[t] = []
            metrics[t].append(e)
        except Exception:
            continue

    lines = ["📊 ROI 报告\n"]
    # 统计各类指标
    for metric_type, entries in metrics.items():
        latest = entries[-1]
        total = sum(e["value"] for e in entries)
        lines.append(f"- {metric_type}: 最近={latest['value']}, 累计={total}")

    return "\n".join(lines)


def get_latest_metrics() -> dict:
    """获取最近的所有指标"""
    if not ROI_PATH.exists():
        return {}
    metrics = {}
    for line in ROI_PATH.read_text(encoding='utf-8').strip().split('\n'):
        try:
            e = json.loads(line)
            metrics[e["type"]] = e["value"]
        except Exception:
            continue
    return metrics


if __name__ == "__main__":
    print(generate_roi_report())