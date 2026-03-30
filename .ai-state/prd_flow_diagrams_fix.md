# 补充修复：流程图生成能力 — CC 执行文档

> 在 prd_v2_upgrade.md 的轨道 A/B 完成后执行
> 修改文件: structured_doc.py
> 产出: PRD HTML 中嵌入 Mermaid 流程图 + Excel 新增"关键流程"Sheet

---

## 修复 1: 读取 anchor 中的 flow_diagrams 配置

在 A2 已添加的 `_load_anchor()` 返回的 anchor dict 中，`flow_diagrams` 字段已经可用。
确认可以通过 `anchor.get('flow_diagrams', [])` 获取流程图列表。

---

## 修复 2: 添加流程图生成函数

在 `structured_doc.py` 中添加以下函数（放在额外 Sheet 生成逻辑附近）：

```python
async def _generate_flow_diagrams(anchor: dict) -> list:
    """
    基于 anchor 中的 flow_diagrams 配置，调用 LLM 生成 Mermaid 流程图代码。
    返回 [{name, mermaid_code, description}, ...]
    """
    flow_configs = anchor.get('flow_diagrams', [])
    if not flow_configs:
        print("[FlowDiagram] anchor 中无流程图配置，跳过")
        return []
    
    print(f"[FlowDiagram] 开始生成 {len(flow_configs)} 个流程图...")
    
    results = []
    
    for i, flow in enumerate(flow_configs):
        name = flow.get('name', f'流程{i+1}')
        trigger = flow.get('trigger', '')
        scope = flow.get('scope', '')
        must_include = flow.get('must_include', [])
        exceptions = flow.get('exceptions', [])
        
        prompt = f"""你是智能骑行头盔产品的交互设计师。请为以下流程生成 Mermaid 流程图代码。

【流程名称】{name}
【触发条件】{trigger}
【涉及范围】{scope}

【必须包含的步骤】
{chr(10).join(f'- {s}' for s in must_include)}

【异常分支（每个异常必须有对应的处理路径）】
{chr(10).join(f'- {e}' for e in exceptions)}

【输出要求】
1. 输出纯 Mermaid flowchart 代码（用 graph TD 纵向布局）
2. 主流程用实线，异常分支用虚线
3. 每个步骤标注属于哪端（HUD/App/头盔/手机），用方括号标注如 [App]
4. 异常处理节点用红色标注：style nodeId fill:#fee,stroke:#c00
5. 成功结束节点用绿色标注：style nodeId fill:#efe,stroke:#0a0
6. 不要输出任何解释，只输出 Mermaid 代码块
7. 节点文字简洁，每个节点最多 15 个字
8. 确保语法正确，可以直接被 Mermaid 渲染引擎解析
"""
        
        try:
            result = await _call_llm(
                prompt=prompt,
                task_name="flow_diagram",
                max_tokens=3000
            )
            
            if result:
                # 提取 mermaid 代码（去掉可能的 ```mermaid ``` 包裹）
                code = result.strip()
                if code.startswith('```'):
                    code = code.split('\n', 1)[1] if '\n' in code else code
                if code.endswith('```'):
                    code = code.rsplit('```', 1)[0]
                code = code.replace('```mermaid', '').replace('```', '').strip()
                
                results.append({
                    'name': name,
                    'trigger': trigger,
                    'scope': scope,
                    'mermaid_code': code,
                    'steps_count': len(must_include),
                    'exceptions_count': len(exceptions),
                })
                print(f"  ✅ [{i+1}/{len(flow_configs)}] {name}: {len(code)} 字符")
            else:
                print(f"  ❌ [{i+1}/{len(flow_configs)}] {name}: LLM 返回空")
        except Exception as e:
            print(f"  ❌ [{i+1}/{len(flow_configs)}] {name}: {e}")
    
    print(f"[FlowDiagram] 完成: {len(results)}/{len(flow_configs)} 个流程图")
    return results
```

---

## 修复 3: 在 PRD 生成主流程中调用

找到 `_process_in_background` 中 **额外 Sheet 生成** 的位置（`[FastTrack] 完整规格书模式:并行生成所有额外 Sheet` 附近），添加流程图生成调用：

```python
# 在额外 Sheet 并行生成的 futures 中，加入流程图生成任务
# 流程图可以和其他 Sheet 并行生成

flow_diagrams = []
if anchor and anchor.get('flow_diagrams'):
    # 和其他 Sheet 一起并行
    flow_future = asyncio.create_task(_generate_flow_diagrams(anchor))
    # ... 其他 Sheet 的 futures ...
    
    # 在所有 futures 完成后收集结果
    flow_diagrams = await flow_future

# 如果不是 async 环境，用线程:
# from concurrent.futures import ThreadPoolExecutor
# flow_future = executor.submit(_generate_flow_diagrams_sync, anchor)
# flow_diagrams = flow_future.result()
```

---

## 修复 4: 写入 Excel "关键流程" Sheet

在 Excel 导出逻辑中，增加一个新 Sheet：

```python
def _write_flow_sheet(wb, flow_diagrams: list):
    """写入关键流程 Sheet"""
    if not flow_diagrams:
        return
    
    ws = wb.create_sheet('关键流程')
    
    # 表头
    headers = ['流程名称', '触发条件', '涉及范围', '步骤数', '异常分支数', 'Mermaid代码']
    from openpyxl.styles import Font, PatternFill, Alignment
    
    header_fill = PatternFill('solid', fgColor='4A5568')
    header_font = Font(bold=True, color='FFFFFF', size=11)
    
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center')
    
    # 数据行
    for i, flow in enumerate(flow_diagrams, 2):
        ws.cell(row=i, column=1, value=flow['name'])
        ws.cell(row=i, column=2, value=flow['trigger'])
        ws.cell(row=i, column=3, value=flow['scope'])
        ws.cell(row=i, column=4, value=flow['steps_count'])
        ws.cell(row=i, column=5, value=flow['exceptions_count'])
        # Mermaid 代码放在单元格中，用户可以复制到 Mermaid 编辑器渲染
        cell = ws.cell(row=i, column=6, value=flow['mermaid_code'])
        cell.alignment = Alignment(wrap_text=True)
    
    # 列宽
    ws.column_dimensions['A'].width = 20
    ws.column_dimensions['B'].width = 25
    ws.column_dimensions['C'].width = 15
    ws.column_dimensions['D'].width = 8
    ws.column_dimensions['E'].width = 10
    ws.column_dimensions['F'].width = 80
    
    print(f"  ✅ 关键流程 Sheet: {len(flow_diagrams)} 个流程")

# 在 Excel 导出主逻辑中调用:
# _write_flow_sheet(wb, flow_diagrams)
# 确保 '关键流程' 出现在 Export 日志的 Sheet 列表中
```

---

## 修复 5: 在 PRD HTML 中嵌入可渲染的流程图

找到 PRD HTML 模板生成逻辑，增加一个 "关键流程" Tab 页：

### HTML 模板中增加 Tab

```python
# 在生成 tabs 的逻辑中，增加:
# tabs_list.append('关键流程')
```

### Tab 内容 — 用 Mermaid.js 渲染流程图

```python
def _generate_flow_tab_html(flow_diagrams: list) -> str:
    """生成关键流程 Tab 的 HTML 内容，内嵌 Mermaid 渲染"""
    if not flow_diagrams:
        return '<div class="content-empty">暂无流程图数据</div>'
    
    html_parts = []
    
    for i, flow in enumerate(flow_diagrams):
        html_parts.append(f'''
        <div class="flow-card" id="flow-{i}">
            <div class="flow-header" onclick="toggleFlow({i})">
                <span class="flow-title">{flow['name']}</span>
                <span class="flow-meta">触发: {flow['trigger']} | 范围: {flow['scope']} | {flow['steps_count']}步骤 {flow['exceptions_count']}异常分支</span>
                <span class="flow-toggle">▼</span>
            </div>
            <div class="flow-body" id="flow-body-{i}">
                <div class="mermaid">
{flow['mermaid_code']}
                </div>
            </div>
        </div>
        ''')
    
    return '\n'.join(html_parts)
```

### 在 HTML `<head>` 中引入 Mermaid.js

```html
<!-- 在 PRD HTML 模板的 <head> 或 </body> 前添加 -->
<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
<script>
    mermaid.initialize({ 
        startOnLoad: false,
        theme: 'neutral',
        flowchart: {
            useMaxWidth: true,
            htmlLabels: true,
            curve: 'basis'
        }
    });
    
    // 切换到"关键流程"Tab 时渲染 Mermaid
    function renderFlowDiagrams() {
        mermaid.run({
            querySelector: '.mermaid'
        });
    }
    
    // Tab 切换时触发渲染
    // 在已有的 Tab 切换函数中，当 activeTab === '关键流程' 时调用 renderFlowDiagrams()
    
    function toggleFlow(index) {
        const body = document.getElementById('flow-body-' + index);
        const toggle = body.previousElementSibling.querySelector('.flow-toggle');
        if (body.style.display === 'none') {
            body.style.display = 'block';
            toggle.textContent = '▼';
            // 展开后重新渲染该流程图
            mermaid.run({ nodes: body.querySelectorAll('.mermaid') });
        } else {
            body.style.display = 'none';
            toggle.textContent = '▶';
        }
    }
</script>
```

### 流程图卡片的 CSS

```css
.flow-card {
    background: #fff;
    border-radius: 8px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    margin-bottom: 16px;
    overflow: hidden;
}
.flow-header {
    display: flex;
    align-items: center;
    padding: 12px 20px;
    cursor: pointer;
    background: #f7fafc;
    border-bottom: 1px solid #e2e8f0;
    gap: 16px;
}
.flow-header:hover {
    background: #edf2f7;
}
.flow-title {
    font-weight: 600;
    font-size: 15px;
    color: #2d3748;
    min-width: 150px;
}
.flow-meta {
    flex: 1;
    font-size: 12px;
    color: #718096;
}
.flow-toggle {
    font-size: 12px;
    color: #a0aec0;
    transition: transform 0.2s;
}
.flow-body {
    padding: 20px;
    overflow-x: auto;
}
.flow-body .mermaid {
    display: flex;
    justify-content: center;
}
.flow-body svg {
    max-width: 100%;
    height: auto;
}
```

---

## 修复 6: 离线兜底 — Mermaid CDN 不可用时的降级

```javascript
// 在 Mermaid 加载后检测是否成功
window.addEventListener('load', function() {
    if (typeof mermaid === 'undefined') {
        // CDN 加载失败，显示原始代码
        document.querySelectorAll('.mermaid').forEach(el => {
            el.style.background = '#f7f7f7';
            el.style.padding = '16px';
            el.style.fontFamily = 'monospace';
            el.style.fontSize = '12px';
            el.style.whiteSpace = 'pre-wrap';
            el.style.border = '1px solid #ddd';
            el.style.borderRadius = '4px';
            // 在代码前加提示
            const tip = document.createElement('div');
            tip.style.color = '#999';
            tip.style.marginBottom = '8px';
            tip.textContent = '⚠️ 流程图渲染需要联网（Mermaid.js），当前显示原始代码。可复制到 mermaid.live 在线渲染。';
            el.parentNode.insertBefore(tip, el);
        });
    }
});
```

---

## 修复 8: 主动AI场景表生成

anchor 中的 `ai_proactive_scenarios` 已结构化，不需要调 LLM，直接写入 Excel + HTML。

### 写入 Excel "主动AI场景" Sheet

```python
def _write_ai_scenarios_sheet(wb, anchor: dict):
    """写入主动AI场景 Sheet"""
    scenarios = anchor.get('ai_proactive_scenarios', [])
    if not scenarios:
        return
    
    ws = wb.create_sheet('主动AI场景')
    
    headers = ['场景名称', '触发条件', '系统动作', '所需数据', '用户控制']
    from openpyxl.styles import Font, PatternFill, Alignment
    
    header_fill = PatternFill('solid', fgColor='38A169')
    header_font = Font(bold=True, color='FFFFFF', size=11)
    
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center')
    
    for i, s in enumerate(scenarios, 2):
        ws.cell(row=i, column=1, value=s.get('scenario', ''))
        ws.cell(row=i, column=2, value=s.get('trigger', ''))
        ws.cell(row=i, column=3, value=s.get('action', ''))
        data_needed = s.get('data_needed', [])
        ws.cell(row=i, column=4, value=', '.join(data_needed) if isinstance(data_needed, list) else str(data_needed))
        ws.cell(row=i, column=5, value=s.get('user_control', ''))
        # 每列自动换行
        for col in range(1, 6):
            ws.cell(row=i, column=col).alignment = Alignment(wrap_text=True, vertical='top')
    
    ws.column_dimensions['A'].width = 22
    ws.column_dimensions['B'].width = 45
    ws.column_dimensions['C'].width = 45
    ws.column_dimensions['D'].width = 30
    ws.column_dimensions['E'].width = 30
    
    print(f"  ✅ 主动AI场景 Sheet: {len(scenarios)} 个场景")

# 在 Excel 导出主逻辑中调用:
# _write_ai_scenarios_sheet(wb, anchor)
```

### PRD HTML 增加 "主动AI场景" Tab

```python
def _generate_ai_scenarios_tab_html(anchor: dict) -> str:
    """生成主动AI场景 Tab 的 HTML 内容"""
    scenarios = anchor.get('ai_proactive_scenarios', [])
    if not scenarios:
        return '<div class="content-empty">暂无主动AI场景数据</div>'
    
    # 按类别分组（从场景名推断）
    categories = {
        '导航类': [],
        '安全类': [],
        '设备管理类': [],
        '社交类': [],
    }
    
    for s in scenarios:
        name = s.get('scenario', '')
        if any(kw in name for kw in ['导航', '返航', '日程', '上班', '下班']):
            categories['导航类'].append(s)
        elif any(kw in name for kw in ['疲劳', 'SOS', '夜间', '温度']):
            categories['安全类'].append(s)
        elif any(kw in name for kw in ['电量', '存储', 'OTA', '部件']):
            categories['设备管理类'].append(s)
        else:
            categories['社交类'].append(s)
    
    html_parts = []
    for cat_name, cat_scenarios in categories.items():
        if not cat_scenarios:
            continue
        html_parts.append(f'<div class="ai-cat-header">{cat_name}</div>')
        for s in cat_scenarios:
            data_str = ', '.join(s.get('data_needed', [])) if isinstance(s.get('data_needed'), list) else ''
            html_parts.append(f'''
            <div class="ai-scenario-card">
                <div class="ai-scenario-name">{s.get('scenario', '')}</div>
                <div class="ai-scenario-row">
                    <span class="ai-label">触发条件</span>
                    <span class="ai-value">{s.get('trigger', '')}</span>
                </div>
                <div class="ai-scenario-row">
                    <span class="ai-label">系统动作</span>
                    <span class="ai-value">{s.get('action', '')}</span>
                </div>
                <div class="ai-scenario-row">
                    <span class="ai-label">所需数据</span>
                    <span class="ai-value">{data_str}</span>
                </div>
                <div class="ai-scenario-row">
                    <span class="ai-label">用户控制</span>
                    <span class="ai-value">{s.get('user_control', '')}</span>
                </div>
            </div>
            ''')
    
    return '\n'.join(html_parts)
```

### AI场景卡片 CSS

```css
.ai-cat-header {
    font-size: 16px; font-weight: 700; color: #2d3748;
    padding: 12px 0 6px 0; border-bottom: 2px solid #38a169; margin: 20px 0 10px 0;
}
.ai-scenario-card {
    background: #fff; border-radius: 8px; padding: 14px 20px; margin-bottom: 10px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06); border-left: 3px solid #38a169;
}
.ai-scenario-name { font-weight: 600; font-size: 14px; color: #2d3748; margin-bottom: 8px; }
.ai-scenario-row { display: flex; gap: 12px; margin-bottom: 4px; font-size: 13px; }
.ai-label { min-width: 70px; color: #718096; font-weight: 500; flex-shrink: 0; }
.ai-value { color: #4a5568; flex: 1; }
```

### 在主流程中调用

```python
# 和流程图、旅程图一起：
# _write_ai_scenarios_sheet(wb, anchor)
# HTML tabs 列表增加 '主动AI场景'
# Tab 内容用 _generate_ai_scenarios_tab_html(anchor)
```

---

## 验证清单

- [ ] Excel 中出现"关键流程" Sheet，包含 8 个流程图
- [ ] 每个流程的 Mermaid 代码列非空，语法正确
- [ ] PRD HTML 中出现"关键流程" Tab
- [ ] 点击 Tab 后流程图正确渲染为可视化图表
- [ ] 首次配对流程包含所有异常分支（蓝牙未开启/扫描超时/权限拒绝等）
- [ ] 照片视频传输流程包含完整的异常处理（断连/低电量/空间不足/文件损坏）
- [ ] 流程图中主流程用实线，异常用虚线，节点有颜色区分
- [ ] 离线环境下显示原始代码 + 提示去 mermaid.live 渲染
- [ ] Excel 中出现"用户旅程" Sheet，包含 4 个角色旅程图
- [ ] PRD HTML 中出现"用户旅程" Tab，4 个角色卡片：摩旅/领队/周末聚会/日常通勤
- [ ] 每个角色的旅程图用 Mermaid journey 语法正确渲染
- [ ] Excel 中出现"主动AI场景" Sheet，包含 15 个场景
- [ ] PRD HTML 中出现"主动AI场景" Tab，按导航/安全/设备/社交分类展示
- [ ] 每个场景有完整的 触发条件/系统动作/所需数据/用户控制 四列

---

## 修复 7: 用户故事旅程图生成

anchor 中的 `user_journeys` 定义了 5 个角色、每个角色有多阶段故事线。需要为每个角色生成 Mermaid journey 图。

### 添加旅程图生成函数

```python
async def _generate_user_journeys(anchor: dict) -> list:
    """
    基于 anchor 中的 user_journeys 配置，生成 Mermaid journey 图。
    不需要调 LLM — 数据已经在 anchor 中结构化了，直接拼 Mermaid 语法。
    """
    journey_configs = anchor.get('user_journeys', [])
    if not journey_configs:
        print("[UserJourney] anchor 中无用户旅程配置，跳过")
        return []
    
    print(f"[UserJourney] 开始生成 {len(journey_configs)} 个角色旅程图...")
    
    results = []
    
    for j in journey_configs:
        role = j.get('role', '')
        persona = j.get('persona', '')
        stages = j.get('journey', [])
        
        # 拼 Mermaid journey 语法
        lines = [f'journey', f'    title {role}']
        
        for stage in stages:
            stage_name = stage.get('stage', '')
            touchpoints = stage.get('touchpoints', [])
            lines.append(f'    section {stage_name}')
            
            for i, tp in enumerate(touchpoints):
                # journey 语法: 任务名: 满意度(1-5): 角色
                # 用阶段位置模拟满意度递增（前期低=学习成本，后期高=获得价值）
                score = min(5, 3 + (i // 2))
                # 简化触点文本（去掉括号内容，限长）
                tp_short = tp.split('（')[0].split('(')[0][:25]
                lines.append(f'        {tp_short}: {score}: {role.split("（")[0]}')
        
        mermaid_code = '\n'.join(lines)
        
        total_touchpoints = sum(len(s.get('touchpoints', [])) for s in stages)
        
        results.append({
            'role': role,
            'persona': persona,
            'mermaid_code': mermaid_code,
            'stages_count': len(stages),
            'touchpoints_count': total_touchpoints,
        })
        
        print(f"  ✅ {role}: {len(stages)} 阶段, {total_touchpoints} 触点")
    
    print(f"[UserJourney] 完成: {len(results)} 个角色旅程")
    return results
```

### 写入 Excel "用户旅程" Sheet

```python
def _write_journey_sheet(wb, journeys: list):
    """写入用户旅程 Sheet"""
    if not journeys:
        return
    
    ws = wb.create_sheet('用户旅程')
    
    headers = ['角色', '画像', '阶段数', '触点数', 'Mermaid代码']
    from openpyxl.styles import Font, PatternFill, Alignment
    
    header_fill = PatternFill('solid', fgColor='5A67D8')
    header_font = Font(bold=True, color='FFFFFF', size=11)
    
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center')
    
    for i, j in enumerate(journeys, 2):
        ws.cell(row=i, column=1, value=j['role'])
        ws.cell(row=i, column=2, value=j['persona'])
        ws.cell(row=i, column=3, value=j['stages_count'])
        ws.cell(row=i, column=4, value=j['touchpoints_count'])
        cell = ws.cell(row=i, column=5, value=j['mermaid_code'])
        cell.alignment = Alignment(wrap_text=True)
    
    ws.column_dimensions['A'].width = 25
    ws.column_dimensions['B'].width = 40
    ws.column_dimensions['C'].width = 8
    ws.column_dimensions['D'].width = 8
    ws.column_dimensions['E'].width = 80
    
    print(f"  ✅ 用户旅程 Sheet: {len(journeys)} 个角色")

# 在 Excel 导出主逻辑中调用:
# _write_journey_sheet(wb, user_journeys)
```

### PRD HTML 增加 "用户旅程" Tab

```python
def _generate_journey_tab_html(journeys: list) -> str:
    """生成用户旅程 Tab 的 HTML 内容"""
    if not journeys:
        return '<div class="content-empty">暂无用户旅程数据</div>'
    
    html_parts = []
    
    for i, j in enumerate(journeys):
        html_parts.append(f'''
        <div class="journey-card" id="journey-{i}">
            <div class="journey-header" onclick="toggleJourney({i})">
                <span class="journey-role">{j['role']}</span>
                <span class="journey-persona">{j['persona']}</span>
                <span class="journey-stats">{j['stages_count']}阶段 · {j['touchpoints_count']}触点</span>
                <span class="journey-toggle">▼</span>
            </div>
            <div class="journey-body" id="journey-body-{i}">
                <div class="mermaid">
{j['mermaid_code']}
                </div>
            </div>
        </div>
        ''')
    
    return '\\n'.join(html_parts)
```

### 旅程图卡片 CSS

```css
.journey-card {
    background: #fff;
    border-radius: 8px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    margin-bottom: 16px;
    overflow: hidden;
    border-left: 4px solid #5a67d8;
}
.journey-header {
    display: flex;
    align-items: center;
    padding: 14px 20px;
    cursor: pointer;
    background: #f7fafc;
    border-bottom: 1px solid #e2e8f0;
    gap: 16px;
}
.journey-header:hover { background: #edf2f7; }
.journey-role {
    font-weight: 700;
    font-size: 15px;
    color: #2d3748;
    min-width: 180px;
}
.journey-persona {
    flex: 1;
    font-size: 13px;
    color: #718096;
    font-style: italic;
}
.journey-stats {
    font-size: 12px;
    color: #a0aec0;
    white-space: nowrap;
}
.journey-toggle { font-size: 12px; color: #a0aec0; }
.journey-body { padding: 20px; overflow-x: auto; }
```

### JS 切换逻辑

```javascript
function toggleJourney(index) {
    const body = document.getElementById('journey-body-' + index);
    const toggle = body.previousElementSibling.querySelector('.journey-toggle');
    if (body.style.display === 'none') {
        body.style.display = 'block';
        toggle.textContent = '▼';
        mermaid.run({ nodes: body.querySelectorAll('.mermaid') });
    } else {
        body.style.display = 'none';
        toggle.textContent = '▶';
    }
}
```

### 在主流程中调用（和流程图并行）

```python
# 和 _generate_flow_diagrams 一起并行生成
user_journeys = []
if anchor and anchor.get('user_journeys'):
    user_journeys = await _generate_user_journeys(anchor)  # 纯拼接，不调LLM，瞬间完成

# Excel
_write_journey_sheet(wb, user_journeys)

# HTML tabs 列表中增加 '用户旅程'
```

