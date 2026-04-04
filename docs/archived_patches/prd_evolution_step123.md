# PRD 输出进化 — 数据修复 + 高清脑图 + 交互版 HTML

> 全部在 scripts/feishu_handlers/structured_doc.py 中修改
> 目标：Excel(7 Sheet) + .mm 脑图 + PNG 高清图 + HTML 交互版，四件套一起发飞书

---

## Step 1: 修复数据问题

### 1.1 失败模块自动重试

在并行生成完成后、去重之前，检测失败模块并重试：

```python
    # 检测哪些 L1 没有生成成功
    generated_modules = set()
    for item in all_items:
        if item.get("level") == "L1":
            generated_modules.add(item.get("name", ""))
    
    failed_features = [f for f in l1_features if f["name"] not in generated_modules]
    
    if failed_features:
        print(f"[FastTrack] {len(failed_features)} 个模块失败，逐个重试...")
        for feature in failed_features:
            try:
                batch = _gen_one(feature)
                if batch:
                    all_items.extend(batch)
                    print(f"  ✅ [重试] {feature['name']}: +{len(batch)} 条")
                else:
                    print(f"  ❌ [重试] {feature['name']}: 仍然失败")
            except Exception as e:
                print(f"  ❌ [重试] {feature['name']}: {e}")
```

### 1.2 Sheet 分组逻辑改为按功能归属

当前只看 `module.startswith("App-")` 分组，导致身份认证、用户学习等归入 HUD。

改为三组：

```python
    # 按功能归属分三组
    HUD_MODULES = {
        "导航", "来电", "音乐", "消息", "AI语音助手", "Ai语音助手",
        "简易", "简易路线", "路线", "主动安全预警提示", "组队",
        "摄像状态", "胎温胎压", "开机动画", "速度", "设备状态",
        "显示队友位置", "头盔HUD"
    }
    
    APP_MODULES = {
        "App-设备", "App-社区", "App-商城", "App-我的"
    }
    
    # 系统/交互模块归 HUD Sheet（因为主要在头盔端执行）
    SYSTEM_MODULES = {
        "实体按键交互", "氛围灯交互", "AI功能", "语音交互",
        "视觉交互", "多模态交互"
    }
    
    # 用户侧模块归 App Sheet
    USER_MODULES = {
        "身份认证", "用户学习", "产品介绍", "设备互联", "设备配对流程"
    }
    
    hud_items = [i for i in items if i.get("module", "") in HUD_MODULES or i.get("module", "") in SYSTEM_MODULES]
    app_items = [i for i in items if i.get("module", "") in APP_MODULES or i.get("module", "") in USER_MODULES]
    
    # 兜底：未匹配的按名称判断
    matched = set(i.get("name") for i in hud_items + app_items)
    for i in items:
        if i.get("name") not in matched:
            if "App" in i.get("module", ""):
                app_items.append(i)
            else:
                hud_items.append(i)
```

### 1.3 去重加强

当前去重 key 是 (module, name, level)，但并行生成时同名功能可能在不同模块下出现。改为更严格的去重：

```python
    # 去重：同名+同层级只保留第一条（不管模块名）
    seen_names = set()
    unique = []
    for item in all_items:
        key = (item.get("name", "").strip(), item.get("level", ""))
        if key not in seen_names:
            seen_names.add(key)
            unique.append(item)
        else:
            print(f"  [去重] {item.get('name')}")
    
    if len(unique) < len(all_items):
        print(f"[FastTrack] 去重: {len(all_items)} → {len(unique)}")
    all_items = unique
```

### 1.4 脑图去掉冗余同名层

当前脑图结构是 "模块名 → L1功能名"，但如果模块名和 L1 名一样（如 "来电 → 来电 [P0]"），就多了一层。

在 _generate_mindmap_mm 中修改：

```python
def _generate_mindmap_mm(items, title="智能骑行头盔 V1 功能框架"):
    """生成 FreeMind .mm 格式脑图，无冗余层"""
    import xml.etree.ElementTree as ET
    
    root = ET.Element("map", version="1.0.1")
    root_node = ET.SubElement(root, "node", TEXT=title)
    
    # 按 L1 分组，跳过模块中间层
    current_l1_node = None
    current_l2_node = None
    
    # 先按大类分组：HUD端 / App端 / 系统交互
    hud_group = ET.SubElement(root_node, "node", TEXT="HUD及头盔端")
    app_group = ET.SubElement(root_node, "node", TEXT="App端")
    system_group = ET.SubElement(root_node, "node", TEXT="系统与交互")
    
    HUD_MODULES = {"导航", "来电", "音乐", "消息", "AI语音助手", "Ai语音助手",
        "简易", "简易路线", "路线", "主动安全预警提示", "组队", "摄像状态",
        "胎温胎压", "开机动画", "速度", "设备状态", "显示队友位置", "头盔HUD"}
    APP_MODULES = {"App-设备", "App-社区", "App-商城", "App-我的"}
    
    for item in items:
        level = item.get("level", "")
        name = item.get("name", "")
        module = item.get("module", "")
        priority = item.get("priority", "")
        label = f"{name} [{priority}]" if priority else name
        
        # 选择父组
        if module in HUD_MODULES:
            parent_group = hud_group
        elif module in APP_MODULES:
            parent_group = app_group
        else:
            parent_group = system_group
        
        if level == "L1":
            current_l1_node = ET.SubElement(parent_group, "node", TEXT=label)
            current_l2_node = None
        elif level == "L2" and current_l1_node is not None:
            current_l2_node = ET.SubElement(current_l1_node, "node", TEXT=label)
        elif level == "L3" and current_l2_node is not None:
            ET.SubElement(current_l2_node, "node", TEXT=label)
    
    import io
    tree = ET.ElementTree(root)
    buf = io.BytesIO()
    tree.write(buf, encoding="utf-8", xml_declaration=True)
    return buf.getvalue().decode("utf-8")
```

---

## Step 2: 高清脑图 PNG/SVG 输出

用 Python graphviz 库生成高清图。如果 graphviz 不可用，降级用 matplotlib 树状图。

### 2.1 安装依赖

```bash
pip install graphviz --break-system-packages
# 如果系统没有 graphviz 二进制，用 matplotlib 替代
```

### 2.2 生成 SVG 高清脑图

```python
def _generate_mindmap_svg(items, title="智能骑行头盔 V1 功能框架"):
    """生成 SVG 高清脑图（纯 Python，不依赖外部工具）"""
    
    # 构建树结构
    tree = {"name": title, "children": []}
    
    HUD_MODULES = {"导航", "来电", "音乐", "消息", "AI语音助手", "Ai语音助手",
        "简易", "简易路线", "路线", "主动安全预警提示", "组队", "摄像状态",
        "胎温胎压", "开机动画", "速度", "设备状态", "显示队友位置", "头盔HUD"}
    APP_MODULES = {"App-设备", "App-社区", "App-商城", "App-我的"}
    
    groups = {
        "HUD及头盔端": {"name": "HUD及头盔端", "children": []},
        "App端": {"name": "App端", "children": []},
        "系统与交互": {"name": "系统与交互", "children": []},
    }
    
    current_l1 = None
    current_l2 = None
    
    for item in items:
        level = item.get("level", "")
        name = item.get("name", "")
        module = item.get("module", "")
        priority = item.get("priority", "")
        
        if module in HUD_MODULES:
            group = groups["HUD及头盔端"]
        elif module in APP_MODULES:
            group = groups["App端"]
        else:
            group = groups["系统与交互"]
        
        node = {"name": f"{name} [{priority}]", "priority": priority, "children": []}
        
        if level == "L1":
            group["children"].append(node)
            current_l1 = node
            current_l2 = None
        elif level == "L2" and current_l1:
            current_l1["children"].append(node)
            current_l2 = node
        elif level == "L3" and current_l2:
            current_l2["children"].append(node)
    
    tree["children"] = [g for g in groups.values() if g["children"]]
    
    # 生成 HTML+SVG 可交互脑图（用 D3.js）
    # 这个比静态 SVG 好得多——可以展开折叠、缩放、拖拽
    import json as _json
    tree_json = _json.dumps(tree, ensure_ascii=False)
    
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>{title}</title>
<style>
body {{ margin: 0; font-family: 'Microsoft YaHei', Arial, sans-serif; }}
.node circle {{ fill: #fff; stroke: #2F5496; stroke-width: 2px; cursor: pointer; }}
.node text {{ font-size: 12px; fill: #333; }}
.link {{ fill: none; stroke: #ccc; stroke-width: 1.5px; }}
.p0 {{ fill: #FF4444 !important; color: #fff; }}
.p1 {{ fill: #FF8C00 !important; }}
.p2 {{ fill: #4CAF50 !important; }}
.p3 {{ fill: #9E9E9E !important; }}
#controls {{ position: fixed; top: 10px; left: 10px; z-index: 100; background: #fff; 
    padding: 8px 12px; border-radius: 6px; box-shadow: 0 2px 8px rgba(0,0,0,0.15); }}
button {{ margin: 0 4px; padding: 4px 10px; cursor: pointer; border: 1px solid #ccc; 
    border-radius: 4px; background: #f5f5f5; }}
button:hover {{ background: #e0e0e0; }}
</style>
<script src="https://d3js.org/d3.v7.min.js"></script>
</head><body>
<div id="controls">
    <button onclick="expandAll()">全部展开</button>
    <button onclick="collapseAll()">全部折叠</button>
    <button onclick="resetZoom()">重置缩放</button>
    <span style="margin-left:10px;color:#999;font-size:12px;">滚轮缩放 | 拖拽平移 | 点击展开/折叠</span>
</div>
<script>
const treeData = {tree_json};

const width = Math.max(window.innerWidth, 1400);
const height = Math.max(window.innerHeight, 900);
const margin = {{top: 40, right: 200, bottom: 40, left: 120}};

const svg = d3.select("body").append("svg")
    .attr("width", width).attr("height", height)
    .call(d3.zoom().scaleExtent([0.2, 3]).on("zoom", (e) => g.attr("transform", e.transform)));

const g = svg.append("g").attr("transform", `translate(${{margin.left}},${{height/2}})`);

const tree = d3.tree().nodeSize([22, 220]);
const root = d3.hierarchy(treeData);

// 初始只展开到第2层
root.descendants().forEach(d => {{
    if (d.depth >= 2) {{ d._children = d.children; d.children = null; }}
}});

const priorityColor = {{"P0":"#FF4444","P1":"#FF8C00","P2":"#4CAF50","P3":"#9E9E9E"}};

function update(source) {{
    const treeLayout = tree(root);
    const nodes = root.descendants();
    const links = root.links();
    
    // 节点
    const node = g.selectAll("g.node").data(nodes, d => d.data.name);
    
    const nodeEnter = node.enter().append("g").attr("class", "node")
        .attr("transform", d => `translate(${{d.y}},${{d.x}})`)
        .on("click", (e, d) => {{ toggle(d); update(d); }});
    
    nodeEnter.append("circle").attr("r", 5)
        .style("fill", d => {{
            const p = (d.data.priority || "").toUpperCase();
            return priorityColor[p] || (d._children ? "#ddd" : "#fff");
        }});
    
    nodeEnter.append("text")
        .attr("dy", 3).attr("x", d => d.children || d._children ? -10 : 10)
        .attr("text-anchor", d => d.children || d._children ? "end" : "start")
        .text(d => d.data.name)
        .style("font-size", d => d.depth === 0 ? "16px" : d.depth === 1 ? "14px" : "12px")
        .style("font-weight", d => d.depth <= 1 ? "bold" : "normal");
    
    node.merge(nodeEnter).transition().duration(300)
        .attr("transform", d => `translate(${{d.y}},${{d.x}})`);
    
    node.exit().remove();
    
    // 连线
    const link = g.selectAll("path.link").data(links, d => d.target.data.name);
    
    link.enter().insert("path", "g").attr("class", "link")
        .attr("d", d3.linkHorizontal().x(d => d.y).y(d => d.x));
    
    link.transition().duration(300)
        .attr("d", d3.linkHorizontal().x(d => d.y).y(d => d.x));
    
    link.exit().remove();
}}

function toggle(d) {{
    if (d.children) {{ d._children = d.children; d.children = null; }}
    else {{ d.children = d._children; d._children = null; }}
}}

function expandAll() {{
    root.descendants().forEach(d => {{
        if (d._children) {{ d.children = d._children; d._children = null; }}
    }});
    update(root);
}}

function collapseAll() {{
    root.descendants().forEach(d => {{
        if (d.depth >= 1 && d.children) {{ d._children = d.children; d.children = null; }}
    }});
    update(root);
}}

function resetZoom() {{
    svg.transition().duration(500).call(
        d3.zoom().transform, d3.zoomIdentity.translate(margin.left, height/2)
    );
}}

update(root);
</script></body></html>"""
    
    return html
```

### 2.3 主流程中生成三种脑图格式

```python
    # 生成脑图三件套
    try:
        # 1. .mm 文件（XMind/FreeMind 可编辑）
        mm_content = _generate_mindmap_mm(all_items, "智能骑行头盔 V1 功能框架")
        mm_path = export_dir / f"mindmap_{task_id}.mm"
        mm_path.write_text(mm_content, encoding="utf-8")
        _send_file_to_feishu(reply_target, str(mm_path), id_type)
        print(f"[FastTrack] 脑图 .mm 已发送")
        
        # 2. 交互式 HTML（可展开折叠、缩放、拖拽）
        html_content = _generate_mindmap_svg(all_items, "智能骑行头盔 V1 功能框架")
        html_path = export_dir / f"mindmap_{task_id}.html"
        html_path.write_text(html_content, encoding="utf-8")
        _send_file_to_feishu(reply_target, str(html_path), id_type)
        print(f"[FastTrack] 交互式脑图 .html 已发送")
        
    except Exception as e:
        print(f"[FastTrack] 脑图失败: {e}")
        import traceback
        traceback.print_exc()
```

---

## Step 3: 交互式 HTML PRD 规格书

生成一个 HTML 文件，包含所有 7 个 Sheet 的内容，可搜索、可按优先级筛选、可展开折叠。适合投屏讨论。

```python
def _generate_interactive_prd_html(items, extra_sheets=None, title="智能骑行头盔 V1 PRD 规格书"):
    """生成交互式 HTML PRD（可搜索、可筛选、可展开）"""
    import json as _json
    
    # 准备数据
    all_data = {
        "features": items,
        "state_scenarios": extra_sheets.get("state", []) if extra_sheets else [],
        "voice_commands": extra_sheets.get("voice", []) if extra_sheets else [],
        "button_mapping": extra_sheets.get("button", []) if extra_sheets else [],
        "light_effects": extra_sheets.get("light", []) if extra_sheets else [],
        "voice_nav": extra_sheets.get("voice_nav", []) if extra_sheets else [],
    }
    
    data_json = _json.dumps(all_data, ensure_ascii=False)
    
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>{title}</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: 'Microsoft YaHei', Arial, sans-serif; background: #f5f6fa; color: #333; }}
.header {{ background: #2F5496; color: #fff; padding: 20px 30px; position: sticky; top: 0; z-index: 100; }}
.header h1 {{ font-size: 22px; margin-bottom: 10px; }}
.controls {{ display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }}
.controls input {{ padding: 6px 12px; border: none; border-radius: 4px; width: 300px; font-size: 14px; }}
.controls select {{ padding: 6px 10px; border: none; border-radius: 4px; font-size: 13px; }}
.controls button {{ padding: 6px 14px; border: none; border-radius: 4px; cursor: pointer; 
    background: rgba(255,255,255,0.2); color: #fff; font-size: 13px; }}
.controls button:hover {{ background: rgba(255,255,255,0.35); }}
.tabs {{ display: flex; background: #1a3a6c; padding: 0 30px; }}
.tab {{ padding: 12px 20px; color: rgba(255,255,255,0.7); cursor: pointer; font-size: 14px; 
    border-bottom: 3px solid transparent; }}
.tab.active {{ color: #fff; border-bottom-color: #fff; }}
.tab .badge {{ background: rgba(255,255,255,0.2); padding: 1px 8px; border-radius: 10px; 
    font-size: 11px; margin-left: 6px; }}
.content {{ padding: 20px 30px; max-width: 1400px; margin: 0 auto; }}
.section {{ display: none; }}
.section.active {{ display: block; }}
.stats {{ display: flex; gap: 15px; margin-bottom: 20px; flex-wrap: wrap; }}
.stat {{ background: #fff; padding: 12px 20px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
.stat .num {{ font-size: 24px; font-weight: bold; color: #2F5496; }}
.stat .label {{ font-size: 12px; color: #999; }}
.tree-item {{ margin-left: 0; }}
.l1 {{ background: #fff; margin-bottom: 8px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); overflow: hidden; }}
.l1-header {{ padding: 12px 16px; cursor: pointer; display: flex; align-items: center; gap: 10px;
    background: #e8edf5; font-weight: bold; font-size: 15px; }}
.l1-header:hover {{ background: #dce3f0; }}
.l1-body {{ padding: 0 16px 12px; display: none; }}
.l1-body.open {{ display: block; }}
.l2 {{ margin: 8px 0 4px 12px; }}
.l2-title {{ font-weight: bold; font-size: 14px; color: #2F5496; padding: 6px 0; cursor: pointer; }}
.l3 {{ margin-left: 24px; padding: 4px 0; font-size: 13px; color: #555; border-bottom: 1px solid #f0f0f0; display: flex; gap: 12px; }}
.l3:last-child {{ border-bottom: none; }}
.l3 .name {{ min-width: 180px; }}
.l3 .desc {{ flex: 1; color: #888; font-size: 12px; }}
.l3 .acc {{ flex: 1; color: #6a9; font-size: 12px; }}
.tag {{ display: inline-block; padding: 2px 8px; border-radius: 3px; font-size: 11px; color: #fff; }}
.tag-P0 {{ background: #FF4444; }}
.tag-P1 {{ background: #FF8C00; }}
.tag-P2 {{ background: #4CAF50; }}
.tag-P3 {{ background: #9E9E9E; }}
table {{ width: 100%; border-collapse: collapse; background: #fff; border-radius: 8px; overflow: hidden;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08); margin-bottom: 20px; }}
th {{ background: #2F5496; color: #fff; padding: 10px 12px; text-align: left; font-size: 13px; 
    position: sticky; top: 100px; }}
td {{ padding: 8px 12px; border-bottom: 1px solid #f0f0f0; font-size: 13px; vertical-align: top; }}
tr:hover {{ background: #f8f9fc; }}
.hidden {{ display: none !important; }}
</style>
</head><body>

<div class="header">
    <h1>{title}</h1>
    <div class="controls">
        <input type="text" id="search" placeholder="搜索功能名称..." oninput="filterAll()">
        <select id="priorityFilter" onchange="filterAll()">
            <option value="">全部优先级</option>
            <option value="P0">P0 必做</option>
            <option value="P1">P1 应有</option>
            <option value="P2">P2 规划</option>
            <option value="P3">P3 远期</option>
        </select>
        <button onclick="expandAllTrees()">全部展开</button>
        <button onclick="collapseAllTrees()">全部折叠</button>
    </div>
</div>

<div class="tabs" id="tabBar"></div>
<div class="content" id="contentArea"></div>

<script>
const DATA = {data_json};

const TAB_CONFIG = [
    {{id: "hud", label: "HUD及头盔端", type: "tree"}},
    {{id: "app", label: "App端", type: "tree"}},
    {{id: "state", label: "状态场景对策", type: "table"}},
    {{id: "voice", label: "语音指令表", type: "table"}},
    {{id: "button", label: "按键映射表", type: "table"}},
    {{id: "light", label: "灯效定义表", type: "table"}},
    {{id: "voice_nav", label: "AI语音导航场景", type: "table"}},
];

// 分组功能清单
const HUD_MODULES = new Set(["导航","来电","音乐","消息","AI语音助手","Ai语音助手",
    "简易","简易路线","路线","主动安全预警提示","组队","摄像状态","胎温胎压",
    "开机动画","速度","设备状态","显示队友位置","头盔HUD",
    "实体按键交互","氛围灯交互","AI功能","语音交互","视觉交互","多模态交互"]);

const hudFeatures = DATA.features.filter(f => HUD_MODULES.has(f.module));
const appFeatures = DATA.features.filter(f => !HUD_MODULES.has(f.module));

function buildTabs() {{
    const bar = document.getElementById('tabBar');
    const content = document.getElementById('contentArea');
    
    TAB_CONFIG.forEach((tab, idx) => {{
        const el = document.createElement('div');
        el.className = 'tab' + (idx === 0 ? ' active' : '');
        el.dataset.target = tab.id;
        
        let count = 0;
        if (tab.id === 'hud') count = hudFeatures.length;
        else if (tab.id === 'app') count = appFeatures.length;
        else if (tab.id === 'state') count = DATA.state_scenarios.length;
        else if (tab.id === 'voice') count = DATA.voice_commands.length;
        else if (tab.id === 'button') count = DATA.button_mapping.length;
        else if (tab.id === 'light') count = DATA.light_effects.length;
        else if (tab.id === 'voice_nav') count = DATA.voice_nav.length;
        
        el.innerHTML = `${{tab.label}}<span class="badge">${{count}}</span>`;
        el.onclick = () => switchTab(tab.id);
        bar.appendChild(el);
        
        const section = document.createElement('div');
        section.id = 'section-' + tab.id;
        section.className = 'section' + (idx === 0 ? ' active' : '');
        
        if (tab.type === 'tree') {{
            section.innerHTML = buildTreeView(tab.id === 'hud' ? hudFeatures : appFeatures);
        }} else {{
            section.innerHTML = buildTableView(tab.id);
        }}
        content.appendChild(section);
    }});
}}

function switchTab(id) {{
    document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.target === id));
    document.querySelectorAll('.section').forEach(s => s.classList.toggle('active', s.id === 'section-' + id));
}}

function buildTreeView(features) {{
    let html = '<div class="stats">';
    const counts = {{}};
    features.forEach(f => {{ counts[f.priority] = (counts[f.priority]||0) + 1; }});
    Object.entries(counts).sort().forEach(([p,c]) => {{
        html += `<div class="stat"><div class="num">${{c}}</div><div class="label">${{p}}</div></div>`;
    }});
    html += `<div class="stat"><div class="num">${{features.length}}</div><div class="label">总计</div></div></div>`;
    
    let currentL1 = null, currentL2 = null;
    let l1Html = '';
    
    features.forEach(f => {{
        const tag = `<span class="tag tag-${{f.priority}}">${{f.priority}}</span>`;
        if (f.level === 'L1') {{
            if (currentL1) l1Html += '</div></div>';
            l1Html += `<div class="l1" data-name="${{f.name}}" data-priority="${{f.priority}}">
                <div class="l1-header" onclick="this.nextElementSibling.classList.toggle('open')">
                    ${{tag}} ${{f.name}} <span style="color:#999;font-size:12px;margin-left:auto">${{f.interaction||''}}</span>
                </div><div class="l1-body">`;
            currentL1 = f; currentL2 = null;
        }} else if (f.level === 'L2') {{
            l1Html += `<div class="l2"><div class="l2-title" data-name="${{f.name}}" data-priority="${{f.priority}}">${{tag}} ${{f.name}}</div>`;
            currentL2 = f;
        }} else if (f.level === 'L3') {{
            l1Html += `<div class="l3" data-name="${{f.name}}" data-priority="${{f.priority}}">
                <span class="name">${{tag}} ${{f.name}}</span>
                <span class="desc">${{f.description||''}}</span>
                <span class="acc">${{f.acceptance||''}}</span></div>`;
        }}
    }});
    if (currentL1) l1Html += '</div></div>';
    
    return html + l1Html;
}}

function buildTableView(id) {{
    let data, headers, keys;
    if (id === 'state') {{
        data = DATA.state_scenarios; 
        headers = ['前置状态','场景/操作','执行状态','HUD提示','灯光','语音','App提示','周期'];
        keys = ['pre_state','current','exec_state','hud','light','voice','app','cycle'];
    }} else if (id === 'voice') {{
        data = DATA.voice_commands;
        headers = ['分类','唤醒','用户说法','变体','系统动作','成功反馈','HUD反馈','失败反馈','优先级'];
        keys = ['category','wake','user_says','variants','action','success_voice','success_hud','fail_feedback','priority'];
    }} else if (id === 'button') {{
        data = DATA.button_mapping;
        headers = ['按键','单击','双击','长按','组合键','场景','备注'];
        keys = ['button','single_click','double_click','long_press','combo','scene','note'];
    }} else if (id === 'light') {{
        data = DATA.light_effects;
        headers = ['场景','颜色','模式','频率','时长','优先级','备注'];
        keys = ['trigger','color','mode','frequency','duration','priority','note'];
    }} else if (id === 'voice_nav') {{
        data = DATA.voice_nav;
        headers = ['场景','触发','用户输入','AI动作','HUD','语音','灯光','兜底','优先级'];
        keys = ['scene','trigger','user_input','ai_action','hud_display','voice_output','light_effect','fallback','priority'];
    }}
    
    if (!data || data.length === 0) return '<p style="padding:20px;color:#999;">暂无数据</p>';
    
    let html = '<table><thead><tr>';
    headers.forEach(h => {{ html += `<th>${{h}}</th>`; }});
    html += '</tr></thead><tbody>';
    data.forEach(row => {{
        html += '<tr>';
        keys.forEach(k => {{
            let val = row[k] || '';
            if (k === 'priority' && val) val = `<span class="tag tag-${{val}}">${{val}}</span>`;
            html += `<td>${{val}}</td>`;
        }});
        html += '</tr>';
    }});
    html += '</tbody></table>';
    return html;
}}

function filterAll() {{
    const q = document.getElementById('search').value.toLowerCase();
    const p = document.getElementById('priorityFilter').value;
    
    document.querySelectorAll('.l1, .l2, .l3, tbody tr').forEach(el => {{
        const name = (el.dataset.name || el.textContent || '').toLowerCase();
        const priority = el.dataset.priority || '';
        const matchQ = !q || name.includes(q);
        const matchP = !p || priority === p || el.textContent.includes(p);
        el.classList.toggle('hidden', !(matchQ && matchP));
    }});
}}

function expandAllTrees() {{
    document.querySelectorAll('.l1-body').forEach(b => b.classList.add('open'));
}}
function collapseAllTrees() {{
    document.querySelectorAll('.l1-body').forEach(b => b.classList.remove('open'));
}}

buildTabs();
</script>
</body></html>""";
    
    return html
```

### 在主流程中生成交互式 HTML PRD

```python
    # 生成交互式 HTML PRD
    try:
        prd_html = _generate_interactive_prd_html(all_items, extra_sheets, "智能骑行头盔 V1 PRD 规格书")
        prd_html_path = export_dir / f"prd_interactive_{task_id}.html"
        prd_html_path.write_text(prd_html, encoding="utf-8")
        _send_file_to_feishu(reply_target, str(prd_html_path), id_type)
        print(f"[FastTrack] 交互式 PRD HTML 已发送")
    except Exception as e:
        print(f"[FastTrack] 交互式 HTML 失败: {e}")
        import traceback
        traceback.print_exc()
```

---

## 最终发送顺序

用户发一条消息后，收到以下文件（按顺序）：

1. 📊 Excel 文件（7 个 Sheet）
2. 🗺️ .mm 脑图文件（XMind 可编辑）
3. 🖼️ 交互式脑图 HTML（D3.js，可展开折叠缩放）
4. 📋 交互式 PRD HTML（7 个 Tab，可搜索筛选）
5. 📝 树形文本摘要（飞书消息内预览）

---

## 验证

```bash
python -c "
from scripts.feishu_handlers.structured_doc import (
    _generate_mindmap_mm, _generate_mindmap_svg, 
    _generate_interactive_prd_html, _export_to_excel,
    try_structured_doc_fast_track
)
print('所有函数存在 OK')
"
```
