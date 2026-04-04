# PRD v2 Round 5 修复 — CC 执行文档

> 3 个修复，单终端执行
> ⚠️ 不要重启服务，只做代码修改和 git commit

---

## 修复 1（P0）: HTML 空白页 — buildTabs 中 JS 错误导致整页不渲染

HTML 的 DATA 完整（475+319 条功能、8 个流程图），但页面空白。
根因：`buildTabs()` 在循环中为某个 Tab 生成内容时抛出了 JS 错误（可能是 buildFlowView 或 buildTreeView），
错误未被捕获，导致**整个 buildTabs 中断**，所有 Tab 都不渲染。

**修法**：在 buildTabs 的循环中加 try-catch，确保单个 Tab 出错不影响其他 Tab。

找到 buildTabs 函数：
```bash
grep -n "function buildTabs\|TAB_CONFIG.forEach\|tab\.type" scripts/feishu_handlers/structured_doc.py
```

在 `TAB_CONFIG.forEach` 循环中，把内容生成部分包裹在 try-catch 中：

```javascript
TAB_CONFIG.forEach((tab, idx) => {
    const el = document.createElement('div');
    el.className = 'tab' + (idx === 0 ? ' active' : '');
    el.dataset.target = tab.id;

    // ... count 计算逻辑（保持不变）...

    el.innerHTML = '${tab.label}<span class="badge">${count}</span>';
    el.onclick = () => switchTab(tab.id);
    bar.appendChild(el);

    const section = document.createElement('div');
    section.id = 'section-' + tab.id;
    section.className = 'tab-content' + (idx === 0 ? ' active' : '');
    section.dataset.tab = tab.id;
    section.style.display = idx === 0 ? 'block' : 'none';

    // ★★★ 关键修复：try-catch 包裹，防止单个 Tab 出错导致整页空白 ★★★
    try {
        if (tab.type === 'tree') {
            section.innerHTML = buildTreeView(tab.id === 'hud' ? hudFeatures : appFeatures, tab.id === 'hud');
        } else if (tab.type === 'flow') {
            section.innerHTML = buildFlowView();
        } else {
            section.innerHTML = buildTableView(tab.id);
        }
    } catch(e) {
        console.error('[PRD] Tab "' + tab.id + '" 渲染错误:', e);
        section.innerHTML = '<div style="padding:40px;text-align:center;color:#c00;">⚠️ 渲染错误: ' + e.message + '<br>请按 F12 查看 Console 详情</div>';
    }

    content.appendChild(section);
});
```

同时确保 `buildFlowView` 函数对空数组有兜底：

```javascript
function buildFlowView() {
    var flows = DATA.flow_diagrams;
    if (!flows || !Array.isArray(flows) || flows.length === 0) {
        return '<div style="padding:40px;text-align:center;color:#999;">暂无流程图数据</div>';
    }
    // ... 原有渲染逻辑 ...
}
```

同时确保 `buildTableView` 也有兜底：

```javascript
function buildTableView(tabId) {
    // ... dataMap 定义 ...
    var rows = dataMap[tabId];
    if (!rows || !Array.isArray(rows) || rows.length === 0) {
        return '<div style="padding:40px;text-align:center;color:#999;">暂无数据</div>';
    }
    // ... 原有渲染逻辑 ...
}
```

**额外排查**：如果加了 try-catch 后页面仍然空白，说明错误在 buildTabs 函数本身（不在循环内）。此时需要在 buildTabs 外层也加 try-catch：

```javascript
// 在 HTML 模板的底部，buildTabs() 调用处：
try {
    buildTabs();
} catch(e) {
    console.error('[PRD] buildTabs 失败:', e);
    document.getElementById('contentArea').innerHTML = '<div style="padding:40px;color:red;">页面渲染失败: ' + e.message + '</div>';
}
```

---

## 修复 2（P1）: 去掉 50 行硬截断，改为去重不截断

当前 `_normalize_all_rows` 中有 `MAX_PER_MODULE = 50` 的硬截断，导致"我的Tab"被截到 50 行（实际 66 行是合理的，因为吸收了 6 个子模块）。

**修法**：去掉截断，只保留去重。超过 80 行时打印警告但不截断。

找到 `_normalize_all_rows` 中的截断逻辑：

```bash
grep -n "MAX_PER_MODULE\|截断\|保留质量最高" scripts/feishu_handlers/structured_doc.py
```

将截断逻辑改为：

```python
# 原: 
# MAX_PER_MODULE = 50
# if len(deduped_list) > cap:
#     deduped_list.sort(key=_row_quality, reverse=True)
#     deduped_list = deduped_list[:cap]
#     print(f"  [Normalize] {module_name}: 截断 {trimmed} 条")

# 改为: 只去重，不截断。超 80 行警告。
if len(deduped_list) > 80:
    print(f"  [Normalize] ⚠️ {module_name}: {len(deduped_list)} 条，内容较多，建议人工审视")

# 不再截断
deduped.extend(deduped_list)
```

同时在 `_force_normalize` 之后也去掉任何截断逻辑（如果有的话）。

---

## 修复 3（P1）: normalize_map 补充遗漏映射

日志显示 `[ForceNormalize] App 模块: [..., '社区Tab', ...]` 和 `AI能力中心` 仍未归一化。

**原因 A**: `社区Tab` 在 normalize_map 中映射到 `社区`，但 ForceNormalize 的 key 匹配没生效。可能是因为 ForceNormalize 比较的是 row 的 `module` 字段，但实际存储的 key 不同。

**修法**：在 `_force_normalize` 函数中加调试打印，并确保比较的 key 正确：

```python
def _force_normalize(rows, normalize_map):
    renamed_count = 0
    for row in rows:
        # 检查所有可能包含模块名的字段
        for key in ['module', 'L1功能', 'l1', 'name']:
            val = str(row.get(key, '')).strip()
            if val in normalize_map:
                old_val = val
                row[key] = normalize_map[val]
                renamed_count += 1
                # 调试：打印每次重命名
                # print(f"    [FN] {key}: '{old_val}' → '{normalize_map[val]}'")
    if renamed_count:
        print(f"[ForceNormalize] 重命名 {renamed_count} 个字段")
    return rows
```

**原因 B**: LLM 生成了 normalize_map 中没有的变体名。需要在 anchor yaml 的 normalize_map 中补充：

在 `.ai-state/product_spec_anchor.yaml` 的 `module_normalize` 段追加：

```yaml
  # ---- 补充 LLM 可能生成的变体名 ----
  AI能力中心: AI Tab
  AI能力设置: AI Tab
  AI能力: AI Tab
  App-社区: 社区
  社区Tab: 社区
  App-商城: 商城
  App-设备: 设备Tab
  App-我的: 我的Tab
```

等等——`社区Tab: 社区` 和 `App-社区: 社区` 应该已经在 normalize_map 中了。让 CC 先用 grep 确认：

```bash
grep "社区" .ai-state/product_spec_anchor.yaml
```

如果 normalize_map 中确实有 `社区Tab: 社区`，但 ForceNormalize 没生效，说明 ForceNormalize 中的 key 匹配逻辑有问题。可能是：
- row 的字段值有前后空格
- 或 yaml 读取时 key 类型不对（有的是 str，有的带引号）

**兜底修法**：在 ForceNormalize 中加 strip() 和类型转换：

```python
def _force_normalize(rows, normalize_map):
    # 确保 normalize_map 的 key 都是 stripped string
    clean_map = {str(k).strip(): str(v).strip() for k, v in normalize_map.items()}
    
    renamed_count = 0
    for row in rows:
        for key in ['module', 'L1功能', 'l1', 'name']:
            val = str(row.get(key, '')).strip()
            if val and val in clean_map:
                row[key] = clean_map[val]
                renamed_count += 1
    
    if renamed_count:
        print(f"[ForceNormalize] 重命名 {renamed_count} 个字段")
    return rows
```

同时在 anchor yaml 中补充 `AI能力中心: AI Tab`。CC 执行：

```bash
cd .ai-state
python3 -c "
import yaml
with open('product_spec_anchor.yaml', 'r', encoding='utf-8') as f:
    data = yaml.safe_load(f)

nm = data.get('module_normalize', {})
# 补充遗漏
extras = {
    'AI能力中心': 'AI Tab',
    'AI能力设置': 'AI Tab', 
    'AI能力': 'AI Tab',
}
nm.update(extras)
data['module_normalize'] = nm

with open('product_spec_anchor.yaml', 'w', encoding='utf-8') as f:
    yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

print(f'normalize_map 更新为 {len(nm)} 条')
"
```

---

## 执行顺序

1. 修复 1: buildTabs try-catch + buildFlowView/buildTableView 兜底
2. 修复 2: 去掉 50 行硬截断
3. 修复 3: ForceNormalize 加 strip + anchor 补 AI能力中心 映射

```bash
git add scripts/feishu_handlers/structured_doc.py .ai-state/product_spec_anchor.yaml
git commit --no-verify -m "fix: Round 5 - HTML try-catch + 去掉硬截断 + normalize 补充"
```

⚠️ **不要重启服务**。Leo 会手动重启。

---

## 验证清单

- [ ] HTML 打开后能看到内容（Tab 栏 + 功能列表）
- [ ] 如果某个 Tab 渲染出错，显示红色错误提示而不是整页空白
- [ ] "我的Tab" 保留所有行（不被截断到 50）
- [ ] App 模块中不再有"社区Tab"（应为"社区"）
- [ ] App 模块中不再有"AI能力中心"（应为"AI Tab"）
- [ ] 日志中不再出现"截断 X 条"
