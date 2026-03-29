# Mermaid 渲染 NaN Bug 修复

> CC 执行文档 — 2026-03-30
> 目标：修复 HTML PRD 中流程图 `translate(undefined, NaN)` 渲染失败
> 文件：`scripts/feishu_handlers/structured_doc.py`
> 完成后：`git add -A && git commit -m "fix: mermaid rendering — htmlLabels false + securityLevel loose"`

---

## 问题

Chrome 打开 PRD HTML 后，所有 8 张 Mermaid 流程图均报错：

```
Error: <g> attribute transform: Expected number, "translate(undefined, NaN)".
Unsafe attempt to load URL file:///... 'file:' URLs are treated as unique security origins.
```

即使 Mermaid 代码语法正确的流程图也无法渲染。

## 根因

1. Mermaid 10.x 的 dagre 布局引擎在 `htmlLabels: true`（默认值）时，对某些节点组合计算坐标返回 `undefined/NaN`
2. `file://` 协议下浏览器安全策略阻止了部分资源访问，`securityLevel: 'strict'`（默认值）加剧了这个问题

## 修复

在 `structured_doc.py` 中搜索 `mermaid.initialize`，应该能找到类似这样的代码：

```javascript
mermaid.initialize({ startOnLoad: false, theme: 'neutral', flowchart: { useMaxWidth: true } });
```

替换为：

```javascript
mermaid.initialize({
    startOnLoad: false,
    theme: 'neutral',
    securityLevel: 'loose',
    flowchart: {
        useMaxWidth: true,
        htmlLabels: false
    }
});
```

改动两个字段：
- `securityLevel: 'loose'` — 允许 `file://` 协议正常渲染
- `htmlLabels: false` — 使用 SVG foreignObject 替代 HTML label，绕过 dagre 的 NaN 坐标 bug

## 注意

`htmlLabels: false` 后，节点标签中的 `<br/>` 不再生效（会显示为文字而非换行）。Round 6 Fix 1 的 `sanitize_mermaid` 已经把 `<br/>[xxx]` 转成了 ` - xxx`，两者配套，无需额外处理。

## 验证

修复后重新生成 PRD，用 Chrome 本地打开 HTML 文件：
1. 切到"关键流程"Tab
2. 展开任意流程图
3. 应该看到 SVG 渲染的流程图，Console 无 `translate(undefined, NaN)` 报错

```bash
git add -A && git commit -m "fix: mermaid rendering — htmlLabels false + securityLevel loose"
```

**不要重启服务，Leo 手动重启。**
