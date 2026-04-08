#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
test_mermaid.py - 测试 Mermaid 流程图渲染

从 anchor 读取 flow_diagrams 配置，生成最小 HTML 测试文件。
使用 mermaid v9.4.3 + mermaid.init API。
"""

import json
import sys
from pathlib import Path

# 添加项目根目录到 path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.feishu_handlers.structured_doc import (
    _load_anchor,
    _generate_flow_diagrams,
    _clean_mermaid_code,
    get_cached_anchor,
)


def generate_test_html(flow_diagrams: list) -> str:
    """生成测试 HTML，只包含流程图 Tab"""

    # 构建 DATA 对象
    data_json = json.dumps({
        "flow_diagrams": flow_diagrams
    }, ensure_ascii=False, indent=2)

    # 生成流程图 HTML 片段
    flow_items_html = ""
    for i, flow in enumerate(flow_diagrams):
        name = flow.get('name', f'流程{i+1}')
        mermaid_code = _clean_mermaid_code(flow.get('mermaid_code', ''))
        trigger = flow.get('trigger', '')
        scope = flow.get('scope', '')
        desc = flow.get('description', '')

        flow_items_html += f'''
        <div class="flow-item">
            <div class="flow-header" onclick="toggleFlow({i})">
                <span class="flow-title">{name}</span>
                <span class="flow-toggle">展开</span>
            </div>
            <div class="flow-meta" style="padding:8px 20px;background:#f8f9fa;font-size:12px;color:#666;">
                <span>触发: {trigger}</span> | <span>范围: {scope}</span>
            </div>
            <div class="flow-body" id="flow-body-{i}" style="display:none;">
                <div class="mermaid">{mermaid_code}</div>
            </div>
        </div>'''

    html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Mermaid v9.4.3 渲染测试</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: 'Microsoft YaHei', Arial, sans-serif; background: #f5f6fa; padding: 20px; }}
        h1 {{ color: #2F5496; margin-bottom: 20px; }}
        .flow-item {{ background: #fff; margin-bottom: 12px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); overflow: hidden; }}
        .flow-header {{ padding: 14px 20px; cursor: pointer; display: flex; justify-content: space-between; align-items: center; }}
        .flow-header:hover {{ background: #f8f9fa; }}
        .flow-title {{ font-weight: 600; color: #333; }}
        .flow-toggle {{ font-size: 12px; color: #a0aec0; transition: transform 0.2s; }}
        .flow-body {{ padding: 20px; overflow-x: auto; }}
        .flow-body .mermaid {{ display: flex; justify-content: center; }}
        .flow-body svg {{ max-width: 100%; height: auto; }}
        .info {{ background: #e8f4fd; padding: 12px 16px; border-radius: 4px; margin-bottom: 16px; font-size: 13px; }}
        .info code {{ background: #fff; padding: 2px 6px; border-radius: 3px; font-family: monospace; }}
    </style>
</head>
<body>
    <h1>Mermaid v9.4.3 渲染测试</h1>
    <div class="info">
        测试配置: <code>mermaid@9.4.3</code> + <code>mermaid.init()</code> API<br>
        共 {len(flow_diagrams)} 个流程图，点击展开查看渲染效果。
    </div>

    <div id="flow-container">
        {flow_items_html}
    </div>

    <!-- Mermaid.js v9.4.3 -->
    <script src="https://cdn.jsdelivr.net/npm/mermaid@9.4.3/dist/mermaid.min.js"></script>
    <script>
    (function() {{
        // Mermaid 初始化
        mermaid.initialize({{
            startOnLoad: false,
            theme: 'neutral',
            securityLevel: 'loose',
            flowchart: {{ useMaxWidth: true }}
        }});

        // 切换流程图展开/折叠
        function toggleFlow(idx) {{
            const body = document.getElementById('flow-body-' + idx);
            const header = body.previousElementSibling;
            const toggle = header.querySelector('.flow-toggle');

            if (body.style.display === 'none') {{
                body.style.display = 'block';
                toggle.textContent = '折叠';

                // 只渲染未处理的 mermaid div
                const mermaidDivs = body.querySelectorAll('.mermaid:not([data-processed])');
                if (mermaidDivs.length > 0) {{
                    try {{
                        mermaid.init(undefined, mermaidDivs);
                    }} catch(e) {{
                        console.error('Mermaid render error:', e);
                    }}
                }}
            }} else {{
                body.style.display = 'none';
                toggle.textContent = '展开';
            }}
        }}

        // 页面加载后自动展开第一个流程图
        window.addEventListener('load', function() {{
            setTimeout(function() {{
                toggleFlow(0);
            }}, 200);
        }});
    }})();
    </script>
</body>
</html>'''

    return html


def main():
    """主函数"""
    print("[Test] 加载 anchor 文件...")
    anchor = _load_anchor()

    if not anchor:
        print("[Error] 无法加载 anchor 文件")
        return 1

    flow_configs = anchor.get('flow_diagrams', [])
    print(f"[Test] 找到 {len(flow_configs)} 个流程图配置")

    if not flow_configs:
        print("[Error] anchor 中没有 flow_diagrams 配置")
        return 1

    # 尝试导入 gateway
    try:
        from src.utils.model_gateway import ModelGateway
        gateway = ModelGateway()
        print("[Test] ModelGateway 初始化成功")
    except Exception as e:
        print(f"[Warn] ModelGateway 初始化失败: {e}")
        gateway = None

    # 生成流程图
    print("\n[Test] 生成流程图...")
    flow_diagrams = _generate_flow_diagrams(anchor, gateway)

    if not flow_diagrams:
        print("[Error] 流程图生成失败")
        return 1

    print(f"[Test] 成功生成 {len(flow_diagrams)} 个流程图")

    # 打印每个流程图的摘要
    for i, flow in enumerate(flow_diagrams):
        name = flow.get('name', 'unknown')
        code_len = len(flow.get('mermaid_code', ''))
        print(f"  {i+1}. {name}: {code_len} 字符")

    # 生成测试 HTML
    print("\n[Test] 生成测试 HTML...")
    html = generate_test_html(flow_diagrams)

    # 保存文件
    output_path = PROJECT_ROOT / ".ai-state" / "exports" / "test_mermaid.html"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding='utf-8')

    print(f"[Test] 测试 HTML 已保存: {output_path}")
    print(f"[Test] 文件大小: {len(html)} 字节")

    # 尝试用浏览器打开
    print("\n[Test] 尝试用浏览器打开...")
    import webbrowser
    webbrowser.open(str(output_path))

    print("[Test] 完成！请检查浏览器中的流程图渲染效果。")
    return 0


if __name__ == "__main__":
    sys.exit(main())