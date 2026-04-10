"""
HUD Demo 拼装脚本
按照 tech_spec.md 底部的拼装规则
"""
from pathlib import Path

MODULES_DIR = Path(__file__).parent / "hud_modules"
OUTPUT_PATH = Path(__file__).parent / "hud_demo_final.html"

def read(filename):
    path = MODULES_DIR / filename
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""

def assemble():
    m1_css = read("m1_skeleton.css")
    m1_html = read("m1_skeleton.html")
    m2_js = read("m2_state_machine.js")
    m3_js = read("m3_renderers.js")
    m4_js = read("m4_scenarios.js")
    m5_html = read("m5_controls.html")
    m5_js = read("m5_controls.js")

    output = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Smart Riding HUD Demo</title>
<style>
{m1_css}
</style>
</head>
<body>
{m1_html}
<div id="sandbox">
{m5_html}
</div>
<script>
// === M2: State Machine ===
{m2_js}

// === M3: Renderers ===
{m3_js}

// === M4: Scenarios ===
{m4_js}

// === M5: Controls ===
{m5_js}

// === Boot ===
document.addEventListener('DOMContentLoaded', bootSequence);
</script>
</body>
</html>"""

    OUTPUT_PATH.write_text(output, encoding="utf-8")
    print(f"[Assemble] 输出: {OUTPUT_PATH}")
    print(f"[Assemble] 文件大小: {len(output) / 1024:.1f} KB")
    print(f"[Assemble] 行数: {len(output.splitlines())}")

if __name__ == "__main__":
    assemble()