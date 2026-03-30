# PRD v2 Round 3 修复 — CC 执行文档

> 5 个 bug，其中 Bug 1-2 阻塞输出，必须先修
> 全部修改位于 structured_doc.py，可在单终端顺序执行

---

## Bug 1（P0 一行修）: Excel 崩溃 — get_column_letter 未导入

```bash
# 方法1: sed 追加
grep -q "get_column_letter" scripts/feishu_handlers/structured_doc.py || \
  sed -i '1,/from openpyxl/s/from openpyxl/from openpyxl.utils import get_column_letter\nfrom openpyxl/' scripts/feishu_handlers/structured_doc.py

# 方法2: 如果方法1不生效，直接在文件最顶部的 import 区域手动加:
# from openpyxl.utils import get_column_letter
```

验证：`grep "get_column_letter" scripts/feishu_handlers/structured_doc.py` 应出现 import 行。

---

## Bug 2（P0）: HTML 完全没有 Tab 系统

从 HTML 分析看：`tabs` class 出现 0 次，`tab-content` 出现 0 次。整个 HTML 是一个无 Tab 的连续长页，只有 HUD 功能列表。

**根因**: HTML 模板的 Tab 生成逻辑可能在 Placement 分流改动后被破坏——原来只有 HUD/App 两个 tab，现在要支持 HUD/App/状态场景/语音指令/按键映射/灯效/导航场景/关键流程/用户旅程/主动AI场景 等多个 tab，但模板没有适配。

**修法**: 搜索 HTML 模板生成函数（通常是 `_generate_prd_html` 或 `_export_html`），找到生成 HTML 结构的位置。

需要确保 HTML 模板包含以下结构：

```python
def _generate_prd_html(hud_rows, app_rows, sheets_data, flow_diagrams, user_journeys, stats):
    """生成完整的 PRD HTML，包含所有 Tab"""
    
    # Tab 定义列表
    tabs = [
        ('hud', 'HUD及头盔端'),
        ('app', 'App端'),
        ('state', '状态场景对策'),
        ('voice', '语音指令表'),
        ('button', '按键映射表'),
        ('light', '灯效定义表'),
        ('voice_nav', 'AI语音导航场景'),
        ('flow', '关键流程'),
        ('journey', '用户旅程'),
        ('user_story', '用户故事'),
        ('test_case', '测试用例'),
        ('page_map', '页面映射表'),
        ('dev_task', '开发任务'),
    ]
    
    # 生成 Tab 按钮 HTML
    tabs_html = ''
    for i, (tab_id, tab_name) in enumerate(tabs):
        active = ' active' if i == 0 else ''
        tabs_html += f'<div class="tab{active}" data-tab="{tab_id}" onclick="switchTab(\'{tab_id}\')">{tab_name}</div>\n'
    
    # 生成各 Tab 的内容区域
    # ... HUD 功能列表 (已有逻辑)
    # ... App 功能列表 (需要确保 app_rows 被渲染)
    # ... 表格类 Sheet (state/voice/button/light/voice_nav)
    # ... 流程图 (flow_diagrams)
    # ... 用户旅程 (user_journeys)
    # ... 用户故事/测试用例/页面映射/开发任务
    
    # 每个 tab-content 都需要:
    # <div class="tab-content" data-tab="{tab_id}" style="display:{'block' if i==0 else 'none'}">
    #   ... 内容 ...
    # </div>
```

**具体操作步骤（CC 执行）**:

1. 搜索 HTML 生成函数：
```bash
grep -n "def.*html\|def.*export.*html\|def.*generate.*html\|def.*prd.*html" scripts/feishu_handlers/structured_doc.py
```

2. 在该函数中，找到生成 HTML 的主体部分，确认是否有 tabs 的 HTML 代码。如果没有，需要将整个 HTML 模板重构为 Tab 结构：

```python
# HTML 模板的核心骨架（替换或插入到 HTML 生成函数中）:

html_template = '''<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>智能骑行头盔 V1 PRD 规格书</title>
<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
<style>
html, body {{ margin: 0; padding: 0; height: 100%; overflow: hidden; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
.header {{ position: fixed; top: 0; left: 0; right: 0; z-index: 1000; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: #fff; padding: 16px 24px; }}
.header h1 {{ margin: 0; font-size: 20px; }}
.stats {{ display: flex; gap: 20px; margin-top: 8px; }}
.stat {{ text-align: center; }}
.stat-val {{ font-size: 22px; font-weight: 700; }}
.stat-label {{ font-size: 11px; opacity: 0.8; }}
.controls {{ display: flex; gap: 10px; margin-top: 8px; align-items: center; }}
.controls input {{ padding: 6px 12px; border: none; border-radius: 4px; width: 240px; font-size: 13px; }}
.controls select {{ padding: 6px; border: none; border-radius: 4px; font-size: 13px; }}
.controls button {{ padding: 6px 12px; border: none; border-radius: 4px; background: rgba(255,255,255,0.2); color: #fff; cursor: pointer; font-size: 13px; }}
.tabs {{ position: fixed; left: 0; right: 0; z-index: 999; background: #fff; display: flex; overflow-x: auto; padding: 0; border-bottom: 1px solid #e0e0e0; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }}
.tab {{ padding: 10px 16px; cursor: pointer; white-space: nowrap; font-size: 13px; color: #666; border-bottom: 2px solid transparent; flex-shrink: 0; transition: all 0.2s; }}
.tab:hover {{ color: #667eea; background: #f7f8ff; }}
.tab.active {{ color: #667eea; border-bottom-color: #667eea; font-weight: 600; }}
.content {{ overflow-y: auto; padding: 16px 24px; max-width: 1600px; margin: 0 auto; }}
.tab-content {{ display: none; }}
.tab-content.active {{ display: block; }}

/* L1/L2/L3 功能行样式 */
.l1 {{ background: #fff; margin-bottom: 8px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); overflow: hidden; }}
.l1-header {{ display: flex; align-items: center; padding: 12px 16px; cursor: pointer; gap: 12px; }}
.l1-header:hover {{ background: #f8f9ff; }}
.priority {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 700; }}
.p0 {{ background: #fed7d7; color: #c53030; }}
.p1 {{ background: #fefcbf; color: #b7791f; }}
.p2 {{ background: #c6f6d5; color: #276749; }}
.p3 {{ background: #e2e8f0; color: #4a5568; }}
.l1-name {{ font-weight: 600; font-size: 15px; color: #2d3748; }}
.l1-body {{ padding: 0 16px 12px 16px; }}
.l2 {{ margin-bottom: 6px; }}
.l2-name {{ font-weight: 600; font-size: 13px; color: #4a5568; padding: 6px 0; }}
.l3 {{ display: flex; gap: 12px; padding: 6px 12px; border-bottom: 1px solid #f0f0f0; font-size: 13px; align-items: flex-start; }}
.l3:hover {{ background: #f0f4ff; }}
.l3 .name {{ min-width: 160px; max-width: 220px; font-weight: 500; color: #333; flex-shrink: 0; }}
.l3 .desc {{ flex: 1; min-width: 200px; color: #666; }}
.l3 .acc {{ flex: 1; min-width: 200px; color: #4a9; font-size: 12px; }}
.l3 .extra {{ display: flex; gap: 8px; flex-shrink: 0; }}
.l3 .extra span {{ font-size: 11px; color: #888; min-width: 70px; }}

/* 表格样式 */
.table-wrapper {{ width: 100%; overflow-x: auto; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); margin-bottom: 16px; }}
table {{ width: 100%; min-width: 800px; border-collapse: collapse; table-layout: auto; background: #fff; }}
thead th {{ background: #4a5568; color: #fff; font-weight: 600; font-size: 13px; padding: 10px 12px; text-align: left; position: sticky; top: 0; z-index: 10; }}
tbody td {{ padding: 8px 12px; font-size: 13px; border-bottom: 1px solid #edf2f7; vertical-align: top; }}
tbody tr:hover {{ background: #f7fafc; }}

/* 流程图/旅程图卡片 */
.flow-card, .journey-card {{ background: #fff; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); margin-bottom: 16px; overflow: hidden; }}
.flow-header, .journey-header {{ display: flex; align-items: center; padding: 12px 20px; cursor: pointer; background: #f7fafc; border-bottom: 1px solid #e2e8f0; gap: 16px; }}
.flow-header:hover, .journey-header:hover {{ background: #edf2f7; }}
.flow-title, .journey-role {{ font-weight: 600; font-size: 15px; color: #2d3748; min-width: 150px; }}
.flow-meta, .journey-persona {{ flex: 1; font-size: 12px; color: #718096; }}
.flow-body, .journey-body {{ padding: 20px; overflow-x: auto; }}
.journey-card {{ border-left: 4px solid #5a67d8; }}
</style>
</head>
<body>
<div class="header">
    <h1>智能骑行头盔 V1 PRD 规格书</h1>
    <div class="stats">{stats_html}</div>
    <div class="controls">
        <input type="text" placeholder="搜索功能名称..." id="searchInput" oninput="filterFeatures()">
        <select id="priorityFilter" onchange="filterFeatures()">
            <option value="">全部优先级</option>
            <option value="P0">P0</option>
            <option value="P1">P1</option>
            <option value="P2">P2</option>
            <option value="P3">P3</option>
        </select>
        <button onclick="toggleAll(true)">全部展开</button>
        <button onclick="toggleAll(false)">全部折叠</button>
    </div>
</div>
<div class="tabs" id="tabsBar">{tabs_html}</div>
<div class="content" id="mainContent">
    {all_tab_contents}
</div>
<script>
mermaid.initialize({{ startOnLoad: false, theme: 'neutral' }});

function updateLayout() {{
    var header = document.querySelector('.header');
    var tabs = document.getElementById('tabsBar');
    var content = document.getElementById('mainContent');
    if (header && tabs && content) {{
        var h = header.offsetHeight;
        var t = tabs.offsetHeight;
        tabs.style.top = h + 'px';
        content.style.marginTop = (h + t) + 'px';
        content.style.height = (window.innerHeight - h - t) + 'px';
    }}
}}

function switchTab(tabId) {{
    document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === tabId));
    document.querySelectorAll('.tab-content').forEach(c => {{
        var isActive = c.dataset.tab === tabId;
        c.classList.toggle('active', isActive);
        c.style.display = isActive ? 'block' : 'none';
    }});
    document.getElementById('mainContent').scrollTop = 0;
    if (['flow','journey'].includes(tabId)) {{
        setTimeout(function() {{ mermaid.run(); }}, 200);
    }}
}}

function toggleAll(expand) {{
    document.querySelectorAll('.l1-body').forEach(b => b.style.display = expand ? 'block' : 'none');
}}

function toggleL1(el) {{
    var body = el.nextElementSibling;
    body.style.display = body.style.display === 'none' ? 'block' : 'none';
}}

function filterFeatures() {{
    var search = document.getElementById('searchInput').value.toLowerCase();
    var priority = document.getElementById('priorityFilter').value;
    document.querySelectorAll('.l1').forEach(function(l1) {{
        var text = l1.textContent.toLowerCase();
        var matchSearch = !search || text.includes(search);
        var matchPriority = !priority || l1.querySelector('.priority.' + priority.toLowerCase());
        l1.style.display = (matchSearch && matchPriority) ? 'block' : 'none';
    }});
}}

window.addEventListener('load', function() {{ setTimeout(updateLayout, 100); }});
window.addEventListener('resize', updateLayout);
</script>
</body>
</html>'''
```

**关键**: 在生成 `all_tab_contents` 时，每个 Sheet 的内容都要包裹在 `<div class="tab-content" data-tab="xxx">` 中，第一个 tab 加 `class="tab-content active"` 和 `style="display:block"`，其余 `style="display:none"`。

CC 需要找到当前的 HTML 生成代码，确认它是否在生成 tab-content 包裹。如果不是，需要将所有 Sheet 的 HTML 内容都包裹到对应的 tab-content div 中。

---

## Bug 3（P1）: 归一化未生效

搜索 `_normalize_all_rows` 和 `normalize_map` 的调用位置：

```bash
grep -n "normalize_all_rows\|normalize_map\|NormalizeAll\|Normalize-Pre\|Normalize-Post" scripts/feishu_handlers/structured_doc.py
```

**可能的问题**:
- 函数定义了但没被调用
- normalize_map 变量名和实际传入的不一致
- 调用时机在分流（Placement）之后，但分流代码在归一化之前

**修法**: 确保在以下 3 个位置都调用归一化：

```python
# 位置 1: _gen_one 结果收集完毕后、去重前
all_rows = _normalize_all_rows(all_rows, normalize_map)
print(f"[Normalize-1] 生成后归一化: {len(all_rows)} 条")

# 位置 2: 去重后、Placement 分流前
all_rows = _normalize_all_rows(all_rows, normalize_map)
print(f"[Normalize-2] 去重后归一化: {len(all_rows)} 条")

# 位置 3: 分流后，对 hud_rows 和 app_rows 分别归一化（防止分流带入旧名称）
hud_rows = _normalize_all_rows(hud_rows, normalize_map)
app_rows = _normalize_all_rows(app_rows, normalize_map)
print(f"[Normalize-3] 分流后归一化: HUD {len(hud_rows)}, App {len(app_rows)}")
```

同时确认 normalize_map 包含这些映射（在调用前打印确认）：

```python
print(f"[Normalize] 映射表: {normalize_map}")
# 必须包含:
# '简易' → '简易路线'
# '用户学习' → '用户学习与新手引导'
# '我的' → '我的Tab'  等
```

---

## Bug 4（P1）: 深度模块首轮全部失败 — anchor 注入过长

**根因分析**: 标记 depth:deep 的 7 个模块（主动安全/AI Tab/生命体征/场景模式/部件识别/SOS/佩戴检测）在 anchor 注入后 prompt 超长 → 撞 4096 → 精简重试丢掉所有 anchor → 产出变成无锚点的泛化内容。

这是"越重要的模块越容易失败"的悖论。

**修法（两层）**:

### Layer 1: depth:deep 的模块强制走 AutoSplit（不等失败后再拆）

在 `_gen_one` 提交到 ThreadPoolExecutor 之前的循环中：

```python
for module_name in modules:
    # 检查是否是 depth:deep 模块
    is_deep = False
    if anchor:
        for section in ['hud_modules', 'app_modules', 'cross_cutting']:
            for mod in anchor.get(section, []):
                if mod.get('name') == module_name and mod.get('depth') == 'deep':
                    is_deep = True
                    break
    
    # depth:deep 模块直接走拆解，不等失败
    if is_deep:
        print(f"  [AutoSplit] {module_name} 是深度模块，主动拆解")
        sub_modules = [
            f"{module_name}-核心功能",
            f"{module_name}-交互与状态",
            f"{module_name}-异常与边界",
        ]
        sub_futures = []
        for sub_name in sub_modules:
            sf = executor.submit(_gen_one, sub_name, ...)
            sub_futures.append(sf)
        futures.append((module_name, True, sub_futures))
    else:
        # 正常提交
        futures.append((module_name, False, executor.submit(_gen_one, module_name, ...)))
```

### Layer 2: 精简重试也注入 anchor 的必须功能点（精简版）

找到 Retry 的精简模式代码（`structured_doc_minimal`），在精简 prompt 中也加入 anchor 的 sub_features（但只要功能名，不要详细说明）：

```python
# 在 Retry 精简模式中:
def _build_minimal_prompt_with_anchor(module_name, anchor):
    """精简 prompt 也带上 anchor 的核心功能点（仅名称）"""
    base_prompt = f"请为智能骑行头盔的「{module_name}」模块生成功能列表..."  # 原有精简 prompt
    
    # 从 anchor 中提取该模块的 sub_features 名称（精简为逗号分隔的短列表）
    if anchor:
        anchor_hint = _get_anchor_sub_features(anchor, module_name)
        if anchor_hint:
            # 只取功能名（去掉括号里的说明），限 200 字
            import re
            names_only = re.sub(r'（[^）]+）|\([^)]+\)', '', anchor_hint)
            names_only = names_only[:200]
            base_prompt += f"\n\n必须包含以下功能: {names_only}"
    
    return base_prompt
```

---

## Bug 5（P2）: 开发任务/用户故事偏少

全量重生成后 dev_tasks 220 条（之前 852），偏少。

**根因**: 开发任务的 prompt 可能是按功能条目数量动态决定批次的，958 条功能分 N 批生成，但批次太少。

**修法**: 在开发任务生成逻辑中，确保每个功能模块至少生成 3 条开发任务：

```python
# 找到 DevTask 生成逻辑:
# 原来可能是把所有功能分批发给 LLM 生成
# 改为: 按模块分组，每组独立生成

# 确保 dev_task 的 prompt 中明确要求:
dev_task_requirement = """
每个 L1 模块至少生成 5 条开发任务，每个 L2 功能至少 1 条。
每条开发任务包含: 任务ID、功能名、任务描述、负责角色、预估工时(天)、前置依赖、建议迭代、优先级。
"""
```

---

# 验证清单

修完后重启 + 用同一个 prompt（带"全量重生成"）再跑一次：

- [ ] Excel 成功生成并发送（不再报 get_column_letter 错误）
- [ ] PRD HTML 有完整的 Tab 栏（HUD/App/状态场景/语音指令/按键/灯效/导航场景/流程/旅程/用户故事/测试用例/页面映射/开发任务）
- [ ] 点击每个 Tab 可以切换到对应内容
- [ ] App 端 Tab 有内容（400+ 条功能）
- [ ] 搜索 "简易" 只出现 "简易路线" 不出现独立的 "简易"
- [ ] 搜索 "用户学习" 只出现 "用户学习与新手引导"
- [ ] 深度模块（主动安全/AI Tab/SOS/场景模式等）首轮成功或主动拆解成功，不再进入精简重试
- [ ] 开发任务 > 400 条
- [ ] 流程图 8/8 ✅
- [ ] 用户旅程 4/4 ✅
