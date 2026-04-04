"""知识库可视化 — 生成 HTML 知识地图
@description: 生成 KB 知识分布的可视化 HTML 报告
@dependencies: knowledge_base
@last_modified: 2026-04-04
"""
import json
from pathlib import Path
from collections import Counter

PROJECT_ROOT = Path(__file__).parent.parent


def generate_knowledge_map() -> str:
    """生成 KB 知识地图 HTML"""
    try:
        from src.tools.knowledge_base import KB_ROOT
    except ImportError:
        KB_ROOT = PROJECT_ROOT / "knowledge_base"

    # 收集数据
    domain_counts = Counter()
    entity_counts = Counter()
    confidence_counts = Counter()

    for f in KB_ROOT.rglob("*.json"):
        try:
            data = json.loads(f.read_text(encoding='utf-8'))
            domain_counts[data.get("domain", "unknown")] += 1
            confidence_counts[data.get("confidence", "unknown")] += 1
            # 提取实体
            title = data.get("title", "")
            for entity in ["歌尔", "立讯", "Cardo", "Sena", "OLED", "MicroLED", "Qualcomm", "JBD"]:
                if entity.lower() in title.lower():
                    entity_counts[entity] += 1
        except Exception:
            continue

    # 生成简单 HTML
    html = _generate_map_html(domain_counts, entity_counts, confidence_counts)

    output_path = PROJECT_ROOT / ".ai-state" / "exports" / "knowledge_map.html"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding='utf-8')

    return str(output_path)


def _generate_map_html(domains: Counter, entities: Counter, confidence: Counter) -> str:
    """生成知识地图 HTML"""
    total = sum(domains.values())

    html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>知识库地图</title>
    <style>
        body { font-family: Arial, sans-serif; padding: 20px; background: #f5f5f5; }
        h1 { color: #333; }
        h2 { color: #666; margin-top: 20px; }
        .bubble-container { display: flex; flex-wrap: wrap; gap: 10px; }
        .bubble {
            padding: 10px 20px;
            border-radius: 50px;
            color: white;
            font-weight: bold;
            text-align: center;
        }
        .domain { background: #4CAF50; }
        .entity { background: #2196F3; }
        .confidence { background: #FF9800; }
        .small { font-size: 12px; }
        .medium { font-size: 14px; }
        .large { font-size: 16px; padding: 15px 30px; }
        .stats { background: white; padding: 15px; border-radius: 8px; margin: 20px 0; }
    </style>
</head>
<body>
    <h1>知识库地图</h1>
    <div class="stats">
        <p>总计: <b>%d</b> 条知识条目</p>
    </div>
""" % total

    # 领域分布
    html += "<h2>领域分布</h2><div class='bubble-container'>"
    for domain, count in domains.most_common(10):
        size = "large" if count > 20 else "medium" if count > 10 else "small"
        html += f"<div class='bubble domain {size}'>{domain} ({count})</div>"
    html += "</div>"

    # 实体分布
    if entities:
        html += "<h2>相关实体</h2><div class='bubble-container'>"
        for entity, count in entities.most_common(8):
            size = "large" if count > 10 else "medium"
            html += f"<div class='bubble entity {size}'>{entity} ({count})</div>"
        html += "</div>"

    # Confidence 分布
    html += "<h2>置信度分布</h2><div class='bubble-container'>"
    for conf, count in confidence.most_common():
        size = "large" if count > 20 else "medium"
        html += f"<div class='bubble confidence {size}'>{conf} ({count})</div>"
    html += "</div>"

    html += "</body></html>"
    return html


if __name__ == "__main__":
    output = generate_knowledge_map()
    print(f"知识地图已生成: {output}")