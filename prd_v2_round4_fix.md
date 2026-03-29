# PRD v2 Round 4 修复 — CC 执行文档

> 4 个修复，单终端顺序执行
> 改 structured_doc.py
> ⚠️ 不要重启服务，只做代码修改和 git commit

---

## 修复 1（P0）: 归一化必须真正修改 module 名字段

**当前 bug**: `_normalize_all_rows` 执行了去重和截断，但没有把 row 的 module 字段从旧名改成新名。导致"路线"(48行)没有变成"导航"，"显示队友位置"(49行)没有变成"组队"。

**排查**:
```bash
grep -n "_normalize_all_rows" scripts/feishu_handlers/structured_doc.py
```

找到该函数，确认**第一步是否真的执行了名称替换**。当前代码可能是这样：

```python
def _normalize_all_rows(rows, normalize_map, anchor=None):
    # Step 1: 归一化 module 名  ← 这一步可能缺失或没生效
    for row in rows:
        module = row.get('module', '')
        if module in normalize_map:
            row['module'] = normalize_map[module]
    # ...
```

**三种可能的失败原因和修法**:

### 原因 A: Step 1 代码存在但 row 的 key 不是 'module'

```bash
# 检查 row 中实际用的 key 名
grep -n "row\[.module.\]\|row\.get(.module.\)\|'module'" scripts/feishu_handlers/structured_doc.py | head -20
```

如果实际 key 是 `'L1功能'` 或 `'l1'` 或其他名称，需要改成正确的 key：

```python
# 找到实际的 module 字段名（可能是以下之一）
# row['module'], row['L1功能'], row.get('module'), row.get('l1_module')
# 在替换时用正确的 key
for row in rows:
    for key in ['module', 'L1功能', 'l1_module']:
        val = row.get(key, '')
        if val and val in normalize_map:
            row[key] = normalize_map[val]
```

### 原因 B: normalize_map 没有正确传入

```bash
# 搜索调用处，确认 normalize_map 参数不是空的
grep -B5 "_normalize_all_rows(" scripts/feishu_handlers/structured_doc.py
```

确认调用时传入了 anchor 中的 normalize_map：
```python
normalize_map = anchor.get('module_normalize', {}) if anchor else {}
print(f"[Normalize] normalize_map 有 {len(normalize_map)} 条映射")
# 必须输出 27 条
```

### 原因 C: 函数被调用但作用在了数据的副本上，原始数据没变

Python 的 list 是引用传递，但如果中间有 `copy()` 或 `deepcopy()`，修改就不会反映到原始数据。

```bash
# 搜索是否有 copy/deepcopy
grep -n "copy\(\)\|deepcopy\|\.copy\b" scripts/feishu_handlers/structured_doc.py | head -10
```

如果有，确保归一化作用在最终要写入 Excel/HTML 的那份数据上，不是副本。

**最保险的修法 — 在 3 个写入点前强制归一化**:

```python
# 找到以下 3 个写入点，在每个点之前加一次强制归一化:

# ===== 写入点 1: Excel 写入前 =====
# 搜索: _write_feature_sheet 或写入 HUD/App Sheet 的代码
# 在调用前加:
def _force_normalize(rows, normalize_map):
    """强制重命名 module 字段，确保写入时名称正确"""
    renamed_count = 0
    for row in rows:
        for key in ['module', 'L1功能', 'l1_module', 'name']:
            val = row.get(key, '')
            if val and str(val) in normalize_map:
                row[key] = normalize_map[str(val)]
                renamed_count += 1
    if renamed_count:
        print(f"[ForceNormalize] 重命名 {renamed_count} 个字段")
    return rows

# 在 Excel 写入前:
normalize_map = anchor.get('module_normalize', {}) if anchor else {}
hud_rows = _force_normalize(hud_rows, normalize_map)
app_rows = _force_normalize(app_rows, normalize_map)

# ===== 写入点 2: HTML DATA 构建前 =====
# 搜索: const DATA = 或构建 DATA dict 的代码
# 在构建前对 hud_features 和 app_features 也强制归一化

# ===== 写入点 3: 脑图数据前 =====
# 同上
```

**验证**: 修完后加一个打印：
```python
# 在写入 Excel 前打印模块列表确认
hud_modules = set(r.get('module', r.get('L1功能', '')) for r in hud_rows)
app_modules = set(r.get('module', r.get('L1功能', '')) for r in app_rows)
print(f"[ForceNormalize] HUD 模块: {sorted(hud_modules)}")
print(f"[ForceNormalize] App 模块: {sorted(app_modules)}")
# 不应出现: 路线, 显示队友位置, 简易, 身份认证, 我的首页, 设备连接与管理
```

---

## 修复 2（P0）: HTML 对 flow_diagrams=0 容错

当前 `flow_diagrams: 0` 导致 `buildFlowView()` 报错，JS 执行中断，整个页面空白。

找到 HTML 中的 `buildFlowView` 函数：

```bash
grep -n "buildFlowView\|function buildFlowView" scripts/feishu_handlers/structured_doc.py
```

在函数开头加空数组容错：

```javascript
function buildFlowView() {
    var flows = DATA.flow_diagrams || [];
    if (flows.length === 0) {
        return '<div style="padding:40px;text-align:center;color:#999;">暂无流程图数据。请检查 anchor 中的 flow_diagrams 配置。</div>';
    }
    // ... 原有逻辑 ...
}
```

同时对 `buildTableView` 中所有可能为空的数组加容错：

```javascript
function buildTableView(tabId) {
    var dataMap = {
        'state': DATA.state_scenarios || [],
        'voice': DATA.voice_commands || [],
        'button': DATA.button_mapping || [],
        'light': DATA.light_effects || [],
        'voice_nav': DATA.voice_nav || [],
        'user_stories': DATA.user_stories || [],
        'test_cases': DATA.test_cases || [],
        'page_mapping': DATA.page_mapping || [],
        'dev_tasks': DATA.dev_tasks || [],
        'journey': DATA.user_journeys || [],
        'ai_scenarios': DATA.ai_scenarios || [],
    };
    var rows = dataMap[tabId];
    if (!rows || rows.length === 0) {
        return '<div style="padding:40px;text-align:center;color:#999;">暂无数据</div>';
    }
    // ... 原有表格渲染逻辑 ...
}
```

同时确保 `buildTabs` 中的 count 计算也有容错：

```javascript
// 找到 count 计算逻辑，确保有 || []
if (tab.id === 'flow') count = (DATA.flow_diagrams || []).length;
```

---

## 修复 3（P1）: 流程图生成静默失败 — 诊断并修复

从日志看流程图完全没有输出（0 条）。需要找到失败原因。

```bash
# Step 1: 确认 _generate_flow_diagrams 函数是否存在
grep -n "_generate_flow_diagrams\|FlowDiagram" scripts/feishu_handlers/structured_doc.py

# Step 2: 确认是否被调用
grep -n "flow_diagram\|flow_future\|generate_flow" scripts/feishu_handlers/structured_doc.py

# Step 3: 确认 anchor 中 flow_diagrams 是否被读取
grep -n "flow_diagrams" scripts/feishu_handlers/structured_doc.py
```

**可能的失败原因**:

### A: 函数存在但没被调用（被提速优化跳过了）

如果 Speed 2 优化把流程图放到了独立 Sheet 提前并行，但 executor 没有正确提交：

```python
# 确认独立 Sheet 提交代码中包含流程图:
if anchor and anchor.get('flow_diagrams'):
    flow_future = executor.submit(_generate_flow_diagrams, anchor)
    print(f"[FastTrack] 流程图任务已提交")
else:
    print(f"[FastTrack] ⚠️ anchor 无 flow_diagrams 配置，跳过")
```

### B: LLM 调用函数名仍然错误

之前修过 `_call_llm` 改成实际函数名，但可能没改全：

```bash
grep -n "_call_llm\b" scripts/feishu_handlers/structured_doc.py
```

如果还有 `_call_llm`，替换为实际的 LLM 调用函数。

### C: 函数执行了但结果没被收集

```python
# 确认 flow_future.result() 被正确收集并写入 sheets_data:
try:
    flow_diagrams = flow_future.result(timeout=300)
    print(f"[FlowDiagram] 收集到 {len(flow_diagrams)} 个流程图")
except Exception as e:
    print(f"[FlowDiagram] ❌ 收集失败: {e}")
    import traceback
    traceback.print_exc()
    flow_diagrams = []

# 确认 flow_diagrams 被写入 sheets_data 和 HTML DATA:
sheets_data['flow_diagrams'] = flow_diagrams
```

### D: _clean_mermaid_code 函数不存在导致 NameError

```bash
grep -n "_clean_mermaid_code" scripts/feishu_handlers/structured_doc.py
```

如果返回 0，说明上一轮的 Bug 2（Mermaid 清洗函数）没有被添加。需要重新添加该函数（参考 prd_v2_final_combined_fix.md 中的 Bug 2 代码）。

**兜底**: 如果以上都排查不出来，在流程图生成处加详细日志：

```python
async def _generate_flow_diagrams(anchor):
    flow_configs = anchor.get('flow_diagrams', [])
    print(f"[FlowDiagram] anchor 中有 {len(flow_configs)} 个流程图配置")
    
    if not flow_configs:
        print("[FlowDiagram] ⚠️ 无流程图配置!")
        return []
    
    results = []
    for i, flow in enumerate(flow_configs):
        name = flow.get('name', f'流程{i}')
        print(f"[FlowDiagram] 开始生成 [{i+1}/{len(flow_configs)}] {name}")
        try:
            # ... LLM 调用 ...
            print(f"[FlowDiagram] ✅ [{i+1}] {name}: 成功")
        except Exception as e:
            print(f"[FlowDiagram] ❌ [{i+1}] {name}: {e}")
            import traceback
            traceback.print_exc()
    
    return results
```

---

## 修复 4（P1）: 用户旅程 Sheet 改为结构化表格

当前用户旅程 Sheet 直接放了原始 Mermaid 代码，Excel 中不可用。

找到 `_write_journey_sheet` 函数：

```bash
grep -n "_write_journey_sheet\|write.*journey\|journey.*sheet" scripts/feishu_handlers/structured_doc.py
```

**替换为展开式表格**（每个触点一行）:

```python
def _write_journey_sheet(wb, user_journeys_raw, anchor):
    """写入用户旅程 Sheet — 结构化表格，每个触点一行"""
    if not anchor:
        return
    
    journey_configs = anchor.get('user_journeys', [])
    if not journey_configs:
        return
    
    from openpyxl.utils import get_column_letter
    from openpyxl.styles import Font, PatternFill, Alignment
    
    ws = wb.create_sheet('用户旅程')
    
    # 表头
    headers = ['角色', '画像', '阶段', '触点', '阶段序号', '触点序号']
    header_fill = PatternFill('solid', fgColor='5A67D8')
    header_font = Font(bold=True, color='FFFFFF', size=11)
    
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center')
    
    # 数据行 — 从 anchor 直接读取结构化数据
    row_idx = 2
    for j in journey_configs:
        role = j.get('role', '')
        persona = j.get('persona', '')
        stages = j.get('journey', [])
        
        first_row_of_role = row_idx  # 记录角色起始行，用于合并单元格
        
        for s_idx, stage in enumerate(stages, 1):
            stage_name = stage.get('stage', '')
            touchpoints = stage.get('touchpoints', [])
            
            for t_idx, tp in enumerate(touchpoints, 1):
                ws.cell(row=row_idx, column=1, value=role)
                ws.cell(row=row_idx, column=2, value=persona)
                ws.cell(row=row_idx, column=3, value=stage_name)
                ws.cell(row=row_idx, column=4, value=tp)
                ws.cell(row=row_idx, column=5, value=s_idx)
                ws.cell(row=row_idx, column=6, value=t_idx)
                
                # 每行设置对齐
                for col in range(1, 7):
                    ws.cell(row=row_idx, column=col).alignment = Alignment(vertical='top', wrap_text=True)
                
                row_idx += 1
    
    # 列宽
    ws.column_dimensions['A'].width = 25
    ws.column_dimensions['B'].width = 35
    ws.column_dimensions['C'].width = 15
    ws.column_dimensions['D'].width = 45
    ws.column_dimensions['E'].width = 8
    ws.column_dimensions['F'].width = 8
    
    total_rows = row_idx - 2
    print(f"  ✅ 用户旅程 Sheet: {len(journey_configs)} 角色, {total_rows} 行")

# 调用方式（在 Excel 导出处）:
# _write_journey_sheet(wb, user_journeys, anchor)
# 注意: 第二个参数（旧的 Mermaid 数据）可以忽略，直接从 anchor 读取结构化数据
```

同时在 HTML DATA 中，用户旅程也改为结构化数据（而不是 Mermaid 代码）：

```python
# 构建 HTML DATA 的 user_journeys 时:
journey_data = []
for j in anchor.get('user_journeys', []):
    role = j.get('role', '')
    persona = j.get('persona', '')
    stages = []
    for stage in j.get('journey', []):
        stages.append({
            'stage': stage.get('stage', ''),
            'touchpoints': stage.get('touchpoints', [])
        })
    journey_data.append({
        'role': role,
        'persona': persona,
        'stages': stages
    })

# DATA['user_journeys'] = journey_data
```

---

## 执行顺序

1. 修复 1: 在 3 个写入点前加 `_force_normalize`
2. 修复 2: HTML buildFlowView + buildTableView 加空数组容错
3. 修复 3: 排查流程图失败原因并修复（按 A→B→C→D 顺序排查）
4. 修复 4: 替换 `_write_journey_sheet` 为结构化表格版本

```bash
git add scripts/feishu_handlers/structured_doc.py
git commit --no-verify -m "fix: Round 4 - 归一化改名+HTML容错+流程图+旅程表格"
```

⚠️ **不要重启服务**。Leo 会手动重启。

---

## 验证清单

- [ ] Excel 中"导航"有 20+ 行内容（不再只有 1 行空壳）
- [ ] Excel 中"组队"有 20+ 行内容
- [ ] Excel 中不存在"路线"、"显示队友位置"、"简易"、"身份认证"、"我的首页"、"设备连接与管理"这些旧模块名
- [ ] PRD HTML 打开后有内容（不再空白）
- [ ] HTML 关键流程 Tab 有流程图或显示"暂无数据"（不报 JS 错误）
- [ ] Excel 有"关键流程" Sheet（8 个流程图）或日志显示明确的失败原因
- [ ] 用户旅程 Sheet 是结构化表格（角色/阶段/触点 每行一个触点），不是 Mermaid 代码
- [ ] 日志输出 `[ForceNormalize] HUD 模块: [...]` 确认无旧名称
