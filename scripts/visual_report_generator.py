"""可视化报告生成 — 从纯文本到 HTML 图表
@description: 生成对比表格、雷达图、象限图等可视化报告
@dependencies: 无
@last_modified: 2026-04-04
"""
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent


def generate_comparison_chart(title: str, items: list, dimensions: list) -> str:
    """生成方案对比 HTML（含表格+简单评分条）

    Args:
        title: 报告标题
        items: [{"name": "OLED", "cost": 85, "brightness": 3000, ...}, ...]
        dimensions: ["cost", "brightness", "supply_chain", ...]

    Returns:
        生成的 HTML 文件路径
    """
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{title}</title>
    <style>
        body { font-family: Arial; padding: 20px; }
        table { border-collapse: collapse; width: 100%; }
        th, td { border: 1px solid #ddd; padding: 10px; text-align: left; }
        th { background: #4CAF50; color: white; }
        tr:nth-child(even) { background: #f9f9f9; }
        .bar { height: 20px; background: #2196F3; border-radius: 4px; }
        .bar-container { width: 100px; background: #eee; border-radius: 4px; }
    </style>
</head>
<body>
    <h1>{title}</h1>
    <table>
        <tr>
            <th>方案</th>
"""

    # 表头
    for dim in dimensions:
        html += f"<th>{dim}</th>"
    html += "</tr>"

    # 数据行
    for item in items:
        html += f"<tr><td><b>{item.get('name', '?')}</b></td>"
        for dim in dimensions:
            value = item.get(dim, "?")
            if isinstance(value, (int, float)):
                bar_width = min(value, 100)
                html += f"<td><div class='bar-container'><div class='bar' style='width:{bar_width}%'></div></div> {value}</td>"
            else:
                html += f"<td>{value}</td>"
        html += "</tr>"

    html += """    </table>
</body>
</html>"""

    output_path = PROJECT_ROOT / ".ai-state" / "exports" / "comparison_chart.html"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding='utf-8')
    return str(output_path)


def generate_supplier_quadrant(suppliers: list) -> str:
    """生成供应商象限图 HTML

    Args:
        suppliers: [{"name": "歌尔", "capability": 8, "cost": 7}, ...]

    Returns:
        生成的 HTML 文件路径
    """
    html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>供应商象限图</title>
    <style>
        body { font-family: Arial; padding: 20px; }
        .quadrant { position: relative; width: 400px; height: 400px; border: 2px solid #333; margin: 20px auto; }
        .quadrant::before { content: ''; position: absolute; top: 50%; left: 0; right: 0; height: 1px; background: #333; }
        .quadrant::after { content: ''; position: absolute; left: 50%; top: 0; bottom: 0; width: 1px; background: #333; }
        .point { position: absolute; width: 20px; height: 20px; border-radius: 50%; background: #4CAF50; text-align: center; font-size: 10px; }
        .label { position: absolute; font-size: 12px; }
        .top-left { top: 10px; left: 10px; }
        .top-right { top: 10px; right: 10px; }
        .bottom-left { bottom: 10px; left: 10px; }
        .bottom-right { bottom: 10px; right: 10px; }
    </style>
</head>
<body>
    <h1>供应商象限图</h1>
    <div class="quadrant">
        <div class="label top-left">高能力 低成本</div>
        <div class="label top-right">高能力 高成本</div>
        <div class="label bottom-left">低能力 低成本</div>
        <div class="label bottom-right">低能力 高成本</div>
"""

    for s in suppliers:
        # 坐标转换：capability 为 y（越高越上），cost 为 x（越低越左）
        x = (s.get("cost", 5) / 10) * 380 + 10  # cost 高则 x 大
        y = 380 - (s.get("capability", 5) / 10) * 380 + 10  # capability 高则 y 小
        html += f"""<div class='point' style='left:{x}px;top:{y}px' title='{s.get("name","?")}'>{s.get("name","?")[:2]}</div>"""

    html += """    </div>
    <p>说明: 纵轴为能力评分，横轴为成本评分</p>
</body>
</html>"""

    output_path = PROJECT_ROOT / ".ai-state" / "exports" / "supplier_quadrant.html"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding='utf-8')
    return str(output_path)


def generate_radar_chart(title: str, data: dict) -> str:
    """生成简单雷达图 HTML

    Args:
        title: 图表标题
        data: {"维度1": 8, "维度2": 7, ...}

    Returns:
        生成的 HTML 文件路径
    """
    dimensions = list(data.keys())
    values = list(data.values())

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{title}</title>
    <style>
        body { font-family: Arial; padding: 20px; }
        .bar-container { margin: 20px 0; }
        .bar-row { display: flex; align-items: center; margin: 10px 0; }
        .bar-label { width: 150px; }
        .bar { height: 25px; background: #FF9800; border-radius: 4px; }
        .bar-bg { background: #ddd; width: 200px; border-radius: 4px; }
    </style>
</head>
<body>
    <h1>{title}</h1>
    <div class="bar-container">
"""

    for dim, val in data.items():
        width = val * 20
        html += f"""<div class="bar-row">
            <div class="bar-label">{dim}</div>
            <div class="bar-bg"><div class="bar" style="width:{width}px"></div></div>
            <span>{val}/10</span>
        </div>"""

    html += """    </div>
</body>
</html>"""

    output_path = PROJECT_ROOT / ".ai-state" / "exports" / "radar_chart.html"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding='utf-8')
    return str(output_path)


if __name__ == "__main__":
    # 测试
    items = [{"name": "OLED", "cost": 85, "brightness": 90, "supply_chain": 80},
             {"name": "MicroLED", "cost": 95, "brightness": 99, "supply_chain": 60}]
    dims = ["cost", "brightness", "supply_chain"]
    print(generate_comparison_chart("显示方案对比", items, dims))