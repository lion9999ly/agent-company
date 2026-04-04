# PRD Round 8 补丁修复文档

> CC 执行文档 — 2026-03-30
> 目标：修复 Mermaid 渲染 + 补回缺失模块 + 修复日志中暴露的问题
> 文件：`scripts/feishu_handlers/structured_doc.py`
> 完成后：`git add -A && git commit -m "fix: Round 8 — mermaid v9 downgrade, AI Tab restore, mall expand, anchor normalize"`

---

## Fix 1：Mermaid 流程图 `translate(undefined, NaN)` 渲染失败（P0）

### 问题

所有 8 张流程图在 Chrome 本地打开时报 `translate(undefined, NaN)`。已尝试 `securityLevel: 'loose'` + `htmlLabels: false`，无效。根因是 Mermaid 10.x 的 dagre 布局引擎在 `file://` 协议下存在坐标计算 bug，与配置无关。

### 修复：降级到 Mermaid 9.4.3

在 `structured_doc.py` 中搜索生成 HTML 的代码段，做以下 3 处替换：

**1) CDN 链接**

搜索：
```
https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js
```
替换为：
```
https://cdn.jsdelivr.net/npm/mermaid@9.4.3/dist/mermaid.min.js
```

**2) mermaid.initialize**

搜索：
```javascript
mermaid.initialize({ startOnLoad: false, theme: 'neutral', securityLevel: 'loose', flowchart: { useMaxWidth: true, htmlLabels: false } });
```
替换为：
```javascript
mermaid.initialize({ startOnLoad: false, theme: 'neutral', securityLevel: 'loose', flowchart: { useMaxWidth: true } });
```

（v9 不需要 `htmlLabels: false`，它的 dagre 没有 NaN bug）

**3) 所有 `mermaid.run(...)` 改为 `mermaid.init(...)`**

v9 没有 `mermaid.run()` API，用 `mermaid.init()` 替代。

搜索所有 `mermaid.run` 出现的位置（应有 4 处），逐个替换：

```javascript
// 替换 1: renderFlows 函数中
// 旧:
mermaid.run({ querySelector: '.mermaid' });
// 新:
mermaid.init(undefined, '.mermaid');

// 替换 2: toggleFlowBody 中 (两处)
// 旧:
mermaid.run({ nodes: body.querySelectorAll('.mermaid') });
// 新:
mermaid.init(undefined, body.querySelectorAll('.mermaid'));

// 替换 3: 如果还有其他 mermaid.run() 调用
// 旧:
mermaid.run()
// 新:
mermaid.init()
```

**4) buildFlowView 中的 mermaid div**

v9 的 `mermaid.init()` 需要 div 内容是原始 mermaid 代码文本，而不是已渲染的 SVG。当前的 `<div class="mermaid">${mermaidCode}</div>` 写法是正确的，不需要改。

但要确保 mermaid div 在 init 时是 **可见的**（`display` 不是 `none`）。当前流程图默认折叠（`display:none`），v9 的 `init` 对隐藏元素可能不生效。

在 `toggleFlowBody` 函数中，展开后调用 init 的逻辑改为：

```javascript
function toggleFlowBody(idx) {
    const body = document.getElementById('flow-body-' + idx);
    const toggle = body.previousElementSibling.querySelector('.flow-toggle');
    if (body.style.display === 'none') {
        body.style.display = 'block';
        toggle.textContent = '折叠';
        // v9: 对未渲染的 .mermaid div 执行 init
        const mermaidDivs = body.querySelectorAll('.mermaid:not([data-processed])');
        if (mermaidDivs.length > 0 && typeof mermaid !== 'undefined') {
            try { mermaid.init(undefined, mermaidDivs); } catch(e) { console.error(e); }
        }
    } else {
        body.style.display = 'none';
        toggle.textContent = '展开';
    }
}
```

关键是 `:not([data-processed])` 选择器——v9 处理过的 div 会被标记 `data-processed`，避免重复渲染。

### 验证

Chrome 本地打开 HTML → 关键流程 Tab → 展开任意流程图 → 应看到 SVG 图 → Console 无 `translate(undefined, NaN)`。

---

## Fix 2：AI Tab 模块缺失（P0）

### 问题

App 端只有 12 个 L1 模块，缺少 AI Tab（AI对话助手、AI剪片、AI内容搜索、AI骑行摘要、AI旅行总结、AI图片增强）。

### 根因分析

日志显示 `✅ [21/44] AI Tab: +18 条` — AI Tab **生成成功了**。但最终 Excel 和 HTML 中 App 只有 12 个 L1，AI Tab 消失了。

检查日志中的 Placement 阶段：
```
[Placement] HUD: 23 模块, App: 13 模块
```
这里 App 是 13 个模块（含 AI Tab），但最终输出只有 12 个。

最可能的原因：在 `[Compare]` 或 `[NormalizeAll]` 阶段，AI Tab 的 18 条功能被去重逻辑误删或被归入了其他模块。日志显示：
```
KEEP+ AI Tab: 旧版更好 + 吸收 6 条新增功能
```
这说明 Compare 选择了旧版 AI Tab，但旧版可能模块名不同（如"AI能力中心"），导致后续归一化时与 HUD 端的"AI功能"模块冲突。

### 修复

在 `structured_doc.py` 的 `module_normalize` 映射表中确认以下条目存在：

```yaml
AI能力中心: AI Tab
AI能力设置: AI Tab
AI能力: AI Tab
```

同时在 Placement 分流逻辑中，确认 "AI Tab" 被分配到 App 端而非 HUD 端。搜索 Placement 相关代码，确认 AI Tab 在 App 端的白名单中。

如果是 Compare 逻辑导致 AI Tab 被丢弃，在 Compare 的 KEEP+ 逻辑中添加保护：

```python
# 在 Compare 函数中，KEEP+ 模式下，如果旧版模块条数为 0（空壳），强制用新版
if old_count == 0 and new_count > 0:
    result = new_features  # 不要 KEEP 空壳
```

**CC 具体操作：**
1. 先搜索 `structured_doc.py` 中 AI Tab 在 Placement 分流时的处理
2. 搜索 Compare 中 AI Tab 的处理逻辑
3. 确认 AI Tab 18 条功能在哪个步骤被丢弃
4. 修复丢弃逻辑

---

## Fix 3：商城模块缩水（P1）

### 问题

Excel 中商城只有 4 行（1个L1 + 3个L3），且 L3 的功能 ID 前缀异常（`HUD-010-14-06` 出现在 App 商城下）。

### 根因分析

日志显示：
```
✅ [35/44] 商城: +19 条
✅ [41/44] App-商城: +18 条
MERGE 商城: 逐条取优 (46条)
[Normalize] 商城: 35 条合并去重为 35 条
```

商城生成了 35 条（去重后），但最终只剩 4 条。大量功能在 Compare 或后续去重中被误删。

同时 `App-商城` 和 `商城` 是两个独立模块，Anchor 中 `App-商城` 应该归一化为 `商城`。检查 `module_normalize` 是否有 `'App-商城': '商城'` 的映射。

### 修复

1. 确认 `module_normalize` 包含 `'App-商城': '商城'`
2. 检查 Compare 的 MERGE 模式下，46 条如何变成最终 4 条——大概率是后续去重把大量条目误判为重复
3. 在去重逻辑中，如果两条功能的 `功能ID` 不同但 `L2功能` 名相同，不应该去重（不同 ID 意味着不同功能点）

---

## Fix 4：Anchor 归一化遗漏（P1）

### 问题

日志显示 Anchor 合并后有 44 个模块，其中 8 个是 Prompt 新增（`简易`, `显示队友位置`, `App-社区`, `App-设备`, `App-商城`, `App-我的`, `路线`, `身份认证`）。这些模块应该被归一化到已有模块：

| Prompt 新增 | 应归一化为 |
|------------|-----------|
| 简易 | 导航 |
| 显示队友位置 | 组队 |
| App-社区 | 社区 |
| App-设备 | 设备Tab |
| App-商城 | 商城 |
| App-我的 | 我的Tab |
| 路线 | 导航 |
| 身份认证 | 我的Tab |

但日志显示它们作为独立模块被生成了（如 `✅ [36/44] 简易: +19 条`），然后在 Normalize 阶段合并。这导致功能重复和模块膨胀。

### 修复

在 `product_spec_anchor.yaml` 的 `module_normalize` 中确认以下映射存在。如果不存在，添加：

```yaml
简易: 导航
简易路线: 导航
简易导航: 导航
路线: 导航
显示队友位置: 组队
App-社区: 社区
App-设备: 设备Tab
App-商城: 商城
App-我的: 我的Tab
身份认证: 我的Tab
```

**关键**：这些映射应在 **Anchor 合并阶段** 就生效（`[Anchor] Prompt 新增 8 个模块` 之前），而不是等到后面的 Normalize 阶段。搜索 `structured_doc.py` 中 Anchor 加载和合并的逻辑，确认 `module_normalize` 在合并时被应用。

---

## Fix 5：开机动画模块错误（P2）

### 问题

开机动画只有 2 行，其中第 2 行 `OTH-008-03-03 开机跳过与快速进入` 功能 ID 属于 `OTH-008`（恢复出厂设置），被错误归类到开机动画。

但日志显示 `✅ [18/44] 开机动画: +16 条`，生成了 16 条。但 Compare 后 `MERGE 开机动画: 逐条取优 (24条)`，最终在去重中只剩 2 条。

### 修复

同 Fix 3 的去重逻辑问题——去重过于激进。这不需要单独修，修好 Fix 3 的去重逻辑后，开机动画也会恢复正常。

---

## Fix 6：TruncGuard 重试后仍失败（P2）

### 问题

日志显示 `[TruncGuard] ⚠️ 主动安全预警提示 输出被截断 (tokens=4096)`，但没有看到重试日志。Round 6 的 TruncGuard 修复要求截断后重试（精简 prompt 再试），但实际没有重试，直接标记失败进入了 AutoSplit。

### 分析

可能原因：TruncGuard 代码被正确添加了截断检测日志，但重试逻辑没有正确串联——检测到截断后直接 return None 进入 AutoSplit，没有先尝试精简重试。

从最终结果看，AutoSplit 成功恢复了（`✅ [Retry] 主动安全预警提示: +48 条`），所以影响不大。但 TruncGuard 的重试逻辑应该修正。

### 修复

检查 `structured_doc.py` 中 TruncGuard 的实现，确认截断检测后是否执行了精简 prompt 重试。如果只是打了日志没重试，补上重试逻辑（参考 Round 6 Fix 3 的代码）。

---

## 执行顺序

1. **Fix 1**（Mermaid v9 降级）— 最紧急，用户可见
2. **Fix 4**（Anchor 归一化）— 根因，修好后 Fix 2/3/5 会自动改善
3. **Fix 2**（AI Tab 恢复）— 检查 Compare 丢弃逻辑
4. **Fix 3**（商城 + 去重）— 检查去重过于激进
5. **Fix 5**（开机动画）— 跟随 Fix 3
6. **Fix 6**（TruncGuard 重试）— 低优先级

全部改完后：

```bash
git add -A && git commit -m "fix: Round 8 — mermaid v9 downgrade, anchor normalize, AI Tab restore, dedup fix"
```

**不要重启服务，Leo 手动重启。**
