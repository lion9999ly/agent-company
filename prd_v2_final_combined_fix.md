# PRD v2 完整修复 + 提速 — CC 一次性执行文档

> 代码 Bug 5 个 + 产品结构优化 4 个 + 提速 2 个 = 共 11 项
> 全部改 structured_doc.py
> ⚠️ 不要重启服务，只做代码修改和 git commit

---

# ===== 第一步: 替换 anchor =====

用项目根目录下 Leo 提供的新 `product_spec_anchor.yaml` 覆盖 `.ai-state/product_spec_anchor.yaml`

---

# ===== 第二步: 代码 Bug 修复 =====

## Bug 1（P0）: Excel get_column_letter 崩溃

先排查：

```bash
grep -n "get_column_letter" scripts/feishu_handlers/structured_doc.py
```

**在每个使用 get_column_letter 的函数内部第一行加局部 import**：

```python
from openpyxl.utils import get_column_letter
```

不管文件顶部有没有 import，每个**使用它的函数内部**都加一次。Python 局部 import 是安全的。

---

## Bug 2（P0）: 流程图 Mermaid 全部 Syntax error

在 `_generate_flow_diagrams` 函数中，保存 mermaid_code 之前加清洗函数：

```python
def _clean_mermaid_code(code: str) -> str:
    """清洗 Mermaid 代码，修复常见语法问题"""
    import re
    
    if not code:
        return 'graph TD\n    A[空流程图] --> B[请重新生成]'
    
    # 移除 markdown 代码块标记
    code = code.strip()
    if code.startswith('```'):
        code = code.split('\n', 1)[1] if '\n' in code else code
    code = code.replace('```mermaid', '').replace('```', '').strip()
    
    # 确保以 graph 开头
    if not code.startswith('graph') and not code.startswith('flowchart'):
        code = 'graph TD\n' + code
    
    # 替换中文标点
    code = code.replace('（', '(').replace('）', ')')
    code = code.replace('【', '[').replace('】', ']')
    code = code.replace('：', ':').replace('；', ';')
    code = code.replace('\u201c', '"').replace('\u201d', '"')
    code = code.replace('\u2018', "'").replace('\u2019', "'")
    
    # 节点文字中转义 < >
    lines = code.split('\n')
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('style') or stripped.startswith('classDef'):
            cleaned.append(line)
            continue
        line = re.sub(r'\[([^\]]*)<([^\]]*)\]', r'[\1&lt;\2]', line)
        line = re.sub(r'\[([^\]]*)>([^\]]*)\]', r'[\1&gt;\2]', line)
        cleaned.append(line)
    
    code = '\n'.join(cleaned)
    code = re.sub(r'\n\s*\n', '\n', code)
    code = re.sub(r'--\s+>', '-->', code)
    code = re.sub(r'==\s+>', '==>', code)
    
    return code.strip()
```

在 `_generate_flow_diagrams` 的 results.append 处调用：

```python
results.append({
    'name': name,
    'trigger': trigger,
    'scope': scope,
    'mermaid_code': _clean_mermaid_code(code),  # ← 清洗
    # ...
})
```

**同时**在 HTML 的 buildFlowView JS 函数中加前端清洗：

找到 buildFlowView 函数，在把 mermaid_code 写入 DOM 之前：

```javascript
function cleanMermaid(code) {
    code = (code || '').replace(/```mermaid/g, '').replace(/```/g, '');
    code = code.replace(/（/g, '(').replace(/）/g, ')');
    code = code.replace(/【/g, '[').replace(/】/g, ']');
    code = code.replace(/：/g, ':');
    code = code.replace(/\u201c/g, '"').replace(/\u201d/g, '"');
    if (!code.trim().startsWith('graph') && !code.trim().startsWith('flowchart')) {
        code = 'graph TD\n' + code;
    }
    return code;
}
// 使用: 在设置 mermaid div 的 textContent 时
// 原: el.textContent = flow.mermaid_code
// 改: el.textContent = cleanMermaid(flow.mermaid_code)
```

---

## Bug 3（P1）: 模块行数封顶对所有模块生效

找到 `_normalize_all_rows` 函数，确保截断逻辑对**所有模块**执行（不只是合并的模块）。

在函数签名中加 anchor 参数：`_normalize_all_rows(rows, normalize_map, anchor=None)`

在去重循环的末尾、`deduped.extend(deduped_list)` 之前加：

```python
MAX_PER_MODULE = 50

# 检查模块是否有自定义上限（从 anchor notes 中读取）
custom_max = MAX_PER_MODULE
if anchor:
    for section in ['hud_modules', 'app_modules', 'cross_cutting']:
        for mod in anchor.get(section, []):
            if mod.get('name') == module_name:
                notes = str(mod.get('notes', ''))
                import re
                max_match = re.search(r'最多\s*(\d+)\s*条', notes)
                if max_match:
                    custom_max = int(max_match.group(1))
                break

cap = min(custom_max, MAX_PER_MODULE)

if len(deduped_list) > cap:
    import re as re2
    def _row_quality(r):
        acc = str(r.get('acceptance', ''))
        nums = len(re2.findall(r'\d+', acc))
        level_bonus = {'L1': 100, 'L2': 50, 'L3': 0}.get(r.get('level', 'L3'), 0)
        return level_bonus + nums * 3 + len(acc)
    
    deduped_list.sort(key=_row_quality, reverse=True)
    trimmed = len(deduped_list) - cap
    deduped_list = deduped_list[:cap]
    print(f"  [Normalize] {module_name}: 截断 {trimmed} 条 (保留质量最高的 {cap} 条)")
```

同时确保所有调用 `_normalize_all_rows` 的地方都传入了 `anchor` 参数。

---

## Bug 4（P1）: 停止生成 .mm 文件

```bash
grep -n "\.mm\b\|freemind\|FreeMind\|mm_path\|mm_file" scripts/feishu_handlers/structured_doc.py
```

注释掉 .mm 文件的生成调用和发送代码。不删除函数本身。

---

## Bug 5（P2）: mindmap HTML 树状布局 + 使用归一化数据

**数据源修复**：脑图当前使用的是未归一化的 `features` 数组，导致"社区"和"社区Tab"同时出现。

找到脑图生成函数和 HTML DATA 对象写入处，确保：

```python
# 脑图数据源改为归一化后的数据:
# 原: mindmap_data = all_rows 或 DATA['features']
# 改: mindmap_data = hud_rows + app_rows  # 已经过 _normalize_all_rows

# HTML DATA 对象中的 features 也改为归一化后:
# 原: "features": all_rows
# 改: "features": hud_rows + app_rows
```

**布局修复**：找到 mindmap HTML 的布局代码，改为树状结构。

```bash
grep -n "mindmap.*html\|radial\|circular\|d3.*tree\|cluster\|sunburst\|generateMindmap\|generate_mindmap" scripts/feishu_handlers/structured_doc.py
```

将径向/圆形改为水平树状。

---

# ===== 第三步: 产品结构优化 =====

## P1: prompt 注入分离规则和模块边界

在 `_gen_one` 的 prompt 拼装中，注入 anchor 的 separation_rules 和模块 notes：

```python
# 在 prompt 末尾追加分离规则
if anchor and anchor.get('separation_rules'):
    rules_text = '\n'.join([f"- {r['rule']}" for r in anchor['separation_rules']])
    prompt += f"\n\n【分离规则 — 必须遵守】\n{rules_text}"

# 对有 notes 的模块，注入边界说明
if anchor:
    for section in ['hud_modules', 'app_modules', 'cross_cutting']:
        for mod in anchor.get(section, []):
            if mod.get('name') == module_name and mod.get('notes'):
                prompt += f"\n\n【本模块边界说明】{mod['notes']}"
                break
```

---

## P2: 脑图生成时跨模块去重

在脑图生成函数中，渲染前过滤重复的 L3：

```python
# 读取 anchor 的 mindmap_rules
mindmap_rules = anchor.get('mindmap_rules', {}) if anchor else {}

if mindmap_rules.get('dedup_across_modules'):
    seen_l3 = set()
    filtered = []
    for row in mindmap_data:
        if row.get('level') == 'L3':
            name = row.get('name', '')
            if name in seen_l3:
                continue
            seen_l3.add(name)
        filtered.append(row)
    mindmap_data = filtered
    print(f"[Mindmap] 跨模块去重后: {len(mindmap_data)} 条")
```

---

## P3: 功能表增加 [设计]/[研发] 角色标注

在 `_gen_one` 的 prompt 输出格式要求中加：

```python
output_format_addition = """
每条功能的 note 字段必须以 [设计] 或 [研发] 开头：
- [设计] = 用户可见的功能、界面、交互（产品/设计师关注）
- [研发] = 降级策略、异常处理、规则引擎、性能边界（研发工程师关注）
示例:
  "note": "[设计] HUD显示转弯箭头和距离"
  "note": "[研发] 信号丢失时切换离线缓存路线"
"""
```

---

## P4: 脑图过滤研发条目

在脑图生成中，过滤 [研发] 标记的条目：

```python
if mindmap_rules:
    before = len(mindmap_data)
    mindmap_data = [r for r in mindmap_data if '[研发]' not in str(r.get('note', ''))]
    filtered_count = before - len(mindmap_data)
    if filtered_count:
        print(f"[Mindmap] 过滤 {filtered_count} 条研发条目")
```

---

# ===== 第四步: 提速优化 =====

## Speed 1: 并行度 4 → 8

```bash
grep -n "ThreadPoolExecutor\|max_workers" scripts/feishu_handlers/structured_doc.py
```

将 max_workers 从 4 改为 8：

```python
# 原: executor = ThreadPoolExecutor(max_workers=4)
# 改:
executor = ThreadPoolExecutor(max_workers=8)
```

确保 LLM 调用有 429 限流重试。

---

## Speed 2: 独立 Sheet 提前并行

找到额外 Sheet 生成的代码（`完整规格书模式:并行生成所有额外 Sheet` 附近）。

将不依赖主功能表的 Sheet 提前启动（在主功能表开始生成时就同时启动）：

**可提前的**：灯效表、按键表、语音指令表、AI语音导航场景、流程图、用户旅程、主动AI场景

**必须等功能表完成的**：状态场景、测试用例、开发任务、用户故事、页面映射、审计

```python
# 在主功能表生成开始时，同时提交独立 Sheet:
independent_futures = {}
independent_futures['light'] = executor.submit(_generate_light_sheet, prompt_text)
independent_futures['button'] = executor.submit(_generate_button_sheet, prompt_text)
independent_futures['voice'] = executor.submit(_generate_voice_sheet, prompt_text)
independent_futures['voice_nav'] = executor.submit(_generate_voice_nav_sheet, prompt_text)
# 流程图和旅程图也提前:
if anchor and anchor.get('flow_diagrams'):
    independent_futures['flow'] = executor.submit(_generate_flow_diagrams, anchor)
if anchor and anchor.get('user_journeys'):
    independent_futures['journey'] = executor.submit(_generate_user_journeys, anchor)

print(f"[FastTrack] 已提前启动 {len(independent_futures)} 个独立 Sheet")

# ... 主功能表生成（原有逻辑）...

# 主功能表完成后，收集独立 Sheet 结果:
for name, future in independent_futures.items():
    try:
        result = future.result(timeout=300)
        print(f"  ✅ {name}: 提前完成")
    except Exception as e:
        print(f"  ❌ {name}: {e}")

# 再启动依赖型 Sheet（原有逻辑不变）
```

---

# ===== 最后: 提交 =====

```bash
git add scripts/feishu_handlers/structured_doc.py
git commit --no-verify -m "fix+perf: Round 3 完整修复 + 提速优化"
```

⚠️ **不要重启服务**。Leo 会手动重启。

---

# 验证清单

- [ ] Excel 成功生成（无 get_column_letter 错误）
- [ ] 流程图在 HTML 中可渲染（无 Syntax error）
- [ ] 所有模块 ≤ 50 行，简易路线 ≤ 15 行
- [ ] 不再生成 .mm 文件
- [ ] 脑图为树状结构
- [ ] 脑图无重复模块（"社区"和"社区Tab"合并为一个）
- [ ] 脑图不含 [研发] 条目
- [ ] 功能条目 note 有 [设计]/[研发] 标注
- [ ] 导航含"路线规划与预览"
- [ ] 组队含"队友摔车检测"
- [ ] 并行度为 8
- [ ] 日志显示"已提前启动 X 个独立 Sheet"
