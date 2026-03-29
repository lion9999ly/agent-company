# PRD v2 Round 3 完整修复 — CC 执行文档

> 代码 Bug 5 个 + 产品结构优化 4 个 = 共 9 项
> 改 structured_doc.py + 替换 anchor yaml
> 单终端顺序执行

---

# ========== 代码 Bug 修复 ==========

## Bug 1（P0 阻塞）: Excel 仍然 get_column_letter 崩溃

CC 之前说已导入，但仍然报错。请执行以下排查：

```bash
# Step 1: 找到所有使用位置
grep -n "get_column_letter" scripts/feishu_handlers/structured_doc.py

# Step 2: 确认 import 是否存在
grep -n "from openpyxl.utils import get_column_letter" scripts/feishu_handlers/structured_doc.py
```

**不管 Step 2 结果如何，在以下每个使用 get_column_letter 的函数内部都加局部 import**：

搜索所有包含 `get_column_letter` 调用的函数（不是 import 行），在**每个函数的第一行**加：

```python
from openpyxl.utils import get_column_letter
```

例如如果有 3 个函数用到，就加 3 次。Python 的局部 import 是幂等的，不会有性能问题，但能确保在任何执行路径下都可达。

---

## Bug 2（P0）: 流程图 Mermaid 全部 Syntax error

所有 8 个流程图在 HTML 中显示 "Syntax error in text"。LLM 生成的 Mermaid 代码有语法问题。

**修法**: 在 `_generate_flow_diagrams` 函数中，保存 mermaid_code 之前，加清洗函数：

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
    code = code.replace('"', '"').replace('"', '"')
    code = code.replace(''', "'").replace(''', "'")
    
    # Mermaid 节点中不能有裸的 < > & 字符
    # 但只在节点文字内替换，不动箭头符号
    lines = code.split('\n')
    cleaned = []
    for line in lines:
        stripped = line.strip()
        # 跳过纯箭头行和 style 行
        if stripped.startswith('style') or stripped.startswith('classDef'):
            cleaned.append(line)
            continue
        # 在 [] () {} 内的文字中转义
        line = re.sub(r'\[([^\]]*)<([^\]]*)\]', r'[\1&lt;\2]', line)
        line = re.sub(r'\[([^\]]*)>([^\]]*)\]', r'[\1&gt;\2]', line)
        cleaned.append(line)
    
    code = '\n'.join(cleaned)
    
    # 移除连续空行
    code = re.sub(r'\n\s*\n', '\n', code)
    
    # 修复箭头格式
    code = re.sub(r'--\s+>', '-->', code)
    code = re.sub(r'==\s+>', '==>', code)
    
    return code.strip()
```

**调用位置**: 在 `_generate_flow_diagrams` 的 results.append 处：

```python
results.append({
    'name': name,
    'trigger': trigger,
    'scope': scope,
    'mermaid_code': _clean_mermaid_code(code),  # ← 加这个
    # ...
})
```

**同时**在 HTML 前端的 buildFlowView 中也加 JS 版清洗：

找到 buildFlowView 函数，在渲染 mermaid 代码前加：

```javascript
// 在 buildFlowView 中，把 flow.mermaid_code 传入渲染前：
function cleanMermaid(code) {
    code = (code || '').replace(/```mermaid/g, '').replace(/```/g, '');
    code = code.replace(/（/g, '(').replace(/）/g, ')');
    code = code.replace(/【/g, '[').replace(/】/g, ']');
    code = code.replace(/：/g, ':');
    code = code.replace(/"/g, '"').replace(/"/g, '"');
    if (!code.trim().startsWith('graph') && !code.trim().startsWith('flowchart')) {
        code = 'graph TD\n' + code;
    }
    return code;
}

// 使用: 在 div.innerHTML 赋值 mermaid 代码时
// 原: innerText = flow.mermaid_code
// 改: innerText = cleanMermaid(flow.mermaid_code)
```

---

## Bug 3（P1）: 模块行数封顶对所有模块生效

当前只有归一化合并的模块触发了 50 行截断。需要对所有模块普遍执行。

找到 `_normalize_all_rows` 函数，确保截断逻辑在**去重循环的末尾**对每个模块都执行：

```python
# 在 _normalize_all_rows 函数的 for module_name, group_rows in groups.items(): 循环中
# 去重之后、deduped.extend 之前：

MAX_PER_MODULE = 50

# 检查模块是否有自定义上限（从 notes 中读取）
# 简易路线 notes 里写了"最多 15 条"
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

deduped.extend(deduped_list)
```

注意：`anchor` 变量需要作为参数传入 `_normalize_all_rows`。如果当前函数签名是 `_normalize_all_rows(rows, normalize_map)`，改为 `_normalize_all_rows(rows, normalize_map, anchor=None)`。

---

## Bug 4（P1）: 停止生成 .mm 文件

```bash
# 搜索 .mm 生成代码
grep -n "\.mm\b\|freemind\|FreeMind\|mm_path\|mm_file" scripts/feishu_handlers/structured_doc.py
```

找到后注释掉：
1. .mm 文件的生成函数调用
2. .mm 文件的上传和发送代码
3. 不要删除函数本身（可能其他地方引用），只注释调用

---

## Bug 5（P2）: mindmap HTML 改树状布局

```bash
# 搜索 mindmap HTML 生成
grep -n "mindmap.*html\|radial\|circular\|d3.*tree\|cluster\|sunburst\|generateMindmap\|generate_mindmap" scripts/feishu_handlers/structured_doc.py
```

找到布局相关代码，将径向/圆形布局改为水平树：

如果是 D3.js：
```javascript
// 原: d3.cluster() 或 radialPoint 或 sunburst
// 改为:
const treeLayout = d3.tree()
    .nodeSize([30, 250])  // [垂直间距, 水平间距]
    .separation((a, b) => a.parent === b.parent ? 1 : 1.5);
```

如果是自定义 HTML，将节点排布改为嵌套的 `<ul><li>` 树形结构，加折叠展开。

---

# ========== 产品结构优化 ==========

## P1: anchor yaml 已更新

以下改动已在 `product_spec_anchor.yaml` 中完成，CC 只需替换文件：

| 改动 | 内容 |
|------|------|
| 导航 | 新增"骑行前路线规划与预览" sub_feature |
| 组队 | 新增"队友碰撞/摔车检测"+"全队响应流程" 2 条 sub_feature |
| 简易路线 | 加 notes 标注"最多 15 条，只描述与导航的差异" |
| 显示队友位置 | 加 notes 标注"只关注 HUD 呈现，不重复组队模块" |
| 主动安全预警 | 加 notes 标注"只做碰撞前预警，不含碰撞后 SOS" |
| 分离规则 | 新增 3 条：显示/操作分离、跨模块不重复、降级标记[研发] |
| 脑图规则 | 新增 mindmap_rules 段：tree 布局、不生成 .mm、颜色标记、跨模块去重 |

CC 用新的 `product_spec_anchor.yaml` 覆盖 `.ai-state/product_spec_anchor.yaml`。

---

## P2: _gen_one prompt 注入分离规则

在 `_gen_one` 的 prompt 拼装中，注入 anchor 的 separation_rules：

```python
# 在 prompt 末尾追加分离规则
if anchor and anchor.get('separation_rules'):
    rules_text = '\n'.join([f"- {r['rule']}：{r.get('detail','')}" for r in anchor['separation_rules']])
    prompt += f"\n\n【分离规则 — 必须遵守】\n{rules_text}"
```

特别是"跨模块不重复"规则，需要让 LLM 知道：

```python
# 对有 notes 的模块，把 notes 也注入 prompt
if anchor:
    for section in ['hud_modules', 'app_modules', 'cross_cutting']:
        for mod in anchor.get(section, []):
            if mod.get('name') == module_name and mod.get('notes'):
                prompt += f"\n\n【本模块边界说明】{mod['notes']}"
                break
```

---

## P3: 脑图生成时过滤研发条目

在脑图生成函数中，读取 anchor 的 mindmap_rules：

```python
# 生成脑图前：
mindmap_rules = anchor.get('mindmap_rules', {}) if anchor else {}

if mindmap_rules.get('dedup_across_modules'):
    # 跨模块去重：如果两个模块有同名 L3，只保留第一个出现的
    seen_l3 = set()
    filtered = []
    for row in all_rows:
        if row.get('level') == 'L3':
            name = row.get('name', '')
            if name in seen_l3:
                continue
            seen_l3.add(name)
        filtered.append(row)
    all_rows = filtered

# 过滤[研发]标记的条目（脑图只展示用户可见功能）
if mindmap_rules:
    all_rows = [r for r in all_rows if '[研发]' not in str(r.get('note', ''))]
```

---

## P4: 功能表增加"关注角色"备注列

在 `_gen_one` 的 prompt 中，要求 LLM 在 note 字段标注 `[设计]` 或 `[研发]`：

```python
# 在 prompt 的输出格式要求中加:
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

# ========== 执行顺序 ==========

1. 替换 `.ai-state/product_spec_anchor.yaml`（用 Leo 提供的新文件）
2. Bug 1: get_column_letter 局部 import
3. Bug 2: Mermaid 清洗函数 + JS 清洗
4. Bug 3: 模块行数封顶普遍化
5. Bug 4: 注释 .mm 生成和发送
6. Bug 5: mindmap HTML 树状布局
7. P2: prompt 注入分离规则和 notes
8. P3: 脑图过滤研发条目
9. P4: note 字段标注角色
10. `git commit --no-verify`
11. 重启服务

---

# 验证清单

- [ ] Excel 成功生成并发送
- [ ] 流程图在 HTML 中可渲染（无 Syntax error）
- [ ] 所有模块 ≤ 50 行
- [ ] 简易路线 ≤ 15 行
- [ ] 不再生成 .mm 文件
- [ ] 脑图为树状结构
- [ ] 导航模块含"路线规划与预览"
- [ ] 组队模块含"队友摔车检测"
- [ ] 组队和显示队友位置不重复
- [ ] 导航和简易路线不重复
- [ ] 主动安全和 SOS 不重复
- [ ] 功能条目 note 字段有 [设计]/[研发] 标注
