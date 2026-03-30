# 修复文档 2/2: HTML 模板修复（PRD + 功能框架脑图）

> 目标: PRD HTML 和脑图 HTML 达到 9.5 分的专业呈现
> 可与修复文档 1（structured_doc.py 逻辑）并行执行
> 修改位置: structured_doc.py 中的 HTML 生成模板字符串

---

## 修复 A: PRD HTML — 标题导航栏永久固定置顶

**问题**: 顶部标题栏、搜索框、Tab 导航在滚动时会被推走。

**根因**: `position: sticky` 在有 `overflow` 的父容器中失效。

找到 PRD HTML 模板中的 `<style>` 部分，做以下修改：

```css
/* ===== 修改 1: 整体布局改为 fixed header + scrollable content ===== */

/* 删除或注释掉原有的 sticky 相关样式 */
/* 原: .header { position: sticky; top: 0; z-index: 100; } */
/* 原: .tabs { position: sticky; z-index: 99; } */

/* 新的布局方案: header 用 fixed，content 用 padding-top 腾出空间 */
html, body {
    margin: 0;
    padding: 0;
    height: 100%;
    overflow: hidden; /* body 不滚动 */
}

.page-wrapper {
    display: flex;
    flex-direction: column;
    height: 100vh;
}

.header {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    z-index: 1000;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    /* 保留原有的背景色和样式 */
}

.controls {
    padding: 12px 24px;
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
}

.tabs {
    position: fixed;
    top: var(--header-height, 110px); /* 动态计算 header 高度 */
    left: 0;
    right: 0;
    z-index: 999;
    background: #fff;
    border-bottom: 1px solid #e0e0e0;
    display: flex;
    overflow-x: auto;
    padding: 0 24px;
    box-shadow: 0 2px 4px rgba(0,0,0,0.05);
}

.content {
    /* 用 margin-top 腾出 header + tabs 的空间 */
    margin-top: var(--total-header-height, 160px);
    padding: 16px 24px;
    max-width: 1600px;
    margin-left: auto;
    margin-right: auto;
    overflow-y: auto;
    height: calc(100vh - var(--total-header-height, 160px));
}
```

同时在 HTML 模板的 `<script>` 部分，添加动态计算 header 高度的逻辑：

```javascript
// 在 DOMContentLoaded 或 window.onload 中：
function updateHeaderHeight() {
    const header = document.querySelector('.header');
    const tabs = document.querySelector('.tabs');
    if (header && tabs) {
        const headerH = header.offsetHeight;
        const tabsH = tabs.offsetHeight;
        document.documentElement.style.setProperty('--header-height', headerH + 'px');
        document.documentElement.style.setProperty('--total-header-height', (headerH + tabsH) + 'px');
        
        // 更新 content 的 margin-top
        const content = document.querySelector('.content');
        if (content) {
            content.style.marginTop = (headerH + tabsH) + 'px';
            content.style.height = `calc(100vh - ${headerH + tabsH}px)`;
        }
        
        // 更新 tabs 的 top
        tabs.style.top = headerH + 'px';
    }
}

// 初始化和窗口变化时都要更新
window.addEventListener('load', updateHeaderHeight);
window.addEventListener('resize', updateHeaderHeight);
```

---

## 修复 B: PRD HTML — 表格表头错位修复（语音指令表等）

**问题**: 表头行的列宽与表格内容列宽不一致，且上下位置偏移。

**根因**: 表头使用了 `position: sticky` 但表格是 `display: block; overflow-x: auto`，导致 thead 和 tbody 的列宽脱节。

### 方案: 用 table-layout: fixed + 统一列宽

```css
/* ===== 修改 2: 表格布局统一 ===== */

/* 所有数据表格统一样式 */
.table-wrapper {
    width: 100%;
    overflow-x: auto;
    border-radius: 8px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    margin-bottom: 16px;
}

table {
    width: 100%;
    min-width: 900px; /* 防止过度压缩 */
    border-collapse: collapse;
    table-layout: fixed; /* 关键: 固定布局让 thead 和 tbody 列宽一致 */
}

thead {
    position: sticky;
    top: 0;
    z-index: 50;
}

thead th {
    background: #4a5568;
    color: #fff;
    font-weight: 600;
    font-size: 13px;
    padding: 10px 12px;
    text-align: left;
    white-space: nowrap;
    border-bottom: 2px solid #2d3748;
    /* 不要单独设置 width，用 colgroup 统一管理 */
}

tbody td {
    padding: 8px 12px;
    font-size: 13px;
    border-bottom: 1px solid #edf2f7;
    vertical-align: top;
    word-wrap: break-word;
    overflow-wrap: break-word;
}

/* 保证横向滚动时 thead 和 tbody 同步 */
.table-wrapper {
    position: relative;
}
```

### 同时在 HTML 模板中，为每种表格添加 `<colgroup>` 定义列宽比例

```html
<!-- 语音指令表的 colgroup -->
<colgroup>
    <col style="width: 10%">  <!-- 指令分类 -->
    <col style="width: 8%">   <!-- 唤醒方式 -->
    <col style="width: 14%">  <!-- 用户说法 -->
    <col style="width: 14%">  <!-- 常见变体 -->
    <col style="width: 14%">  <!-- 系统动作 -->
    <col style="width: 12%">  <!-- 成功语音反馈 -->
    <col style="width: 10%">  <!-- 成功HUD反馈 -->
    <col style="width: 12%">  <!-- 失败反馈 -->
    <col style="width: 6%">   <!-- 优先级 -->
</colgroup>

<!-- 按键映射表的 colgroup -->
<colgroup>
    <col style="width: 10%">
    <col style="width: 12%">
    <col style="width: 14%">
    <col style="width: 14%">
    <col style="width: 14%">
    <col style="width: 14%">
    <col style="width: 14%">
    <col style="width: 8%">
</colgroup>
```

找到 HTML 模板中生成表格的代码，在每个 `<table>` 标签后、`<thead>` 前插入对应的 `<colgroup>`。

### 确保表格外层包裹 `.table-wrapper`

```html
<!-- 原: <table>...</table> -->
<!-- 改为: -->
<div class="table-wrapper">
    <table>
        <colgroup>...</colgroup>
        <thead>...</thead>
        <tbody>...</tbody>
    </table>
</div>
```

---

## 修复 C: PRD HTML — 功能简述空白行修复

**问题**: App 端某些模块（App-我的、App-社区等）的行只显示模块名，右侧简述为空。

这个问题会被修复文档 1 的"修复 2: 消灭[待生成]"解决。但 HTML 模板也需要加一个前端防御：

```css
/* ===== 修改 3: 空内容行样式降级 ===== */
.l1.empty-content {
    opacity: 0.6;
    border-left: 3px solid #ffd700;
}

.l1.empty-content::after {
    content: '待补充';
    position: absolute;
    right: 16px;
    top: 50%;
    transform: translateY(-50%);
    font-size: 11px;
    color: #999;
    background: #fff3cd;
    padding: 2px 8px;
    border-radius: 4px;
}
```

同时在 JS 渲染逻辑中：

```javascript
// 渲染 L1 模块时检查是否有实质内容
function renderL1(module) {
    const hasContent = module.children && module.children.length > 0 
        && !module.description?.includes('待生成');
    
    const className = hasContent ? 'l1' : 'l1 empty-content';
    
    // 如果是空模块，显示一行概括性说明而非留白
    const desc = hasContent 
        ? module.description 
        : `${module.name}模块功能规划中，将在下一版本迭代补充。`;
    
    // ... 渲染 HTML ...
}
```

---

## 修复 D: 功能框架 HTML 脑图 — 右侧空白 + 节点裁剪

**问题**: 
1. 页面右侧大面积空白，画布内容偏左
2. 节点移到右侧会被裁剪，平移缩放无法访问

**根因**: SVG 的 viewBox 或 canvas 尺寸固定，没有根据节点分布自适应。同时可能有 `overflow: hidden` 裁剪了超出区域的节点。

找到脑图 HTML 模板中的 `<style>` 和 D3/力导向图初始化代码：

### CSS 修复

```css
/* ===== 脑图 CSS 修复 ===== */

/* 1. SVG 容器充满整个视口，无 overflow 裁剪 */
svg {
    width: 100vw;
    height: 100vh;
    display: block;
    /* 删除任何 overflow: hidden */
}

/* 2. 确保 body/html 无 overflow 限制 */
html, body {
    margin: 0;
    padding: 0;
    width: 100%;
    height: 100%;
    overflow: hidden; /* 页面本身不滚动，由 D3 zoom 控制 */
}

/* 3. 控制按钮浮在左上角 */
.controls {
    position: fixed;
    top: 10px;
    left: 10px;
    z-index: 100;
    display: flex;
    gap: 8px;
}
```

### JS 修复 — 渲染完成后 fit-to-content

```javascript
// 在 D3 力导向图的 simulation.on('end') 或 tick 计数达到稳定后：

function fitToContent() {
    // 获取所有节点的边界
    const nodes = d3.selectAll('.node');
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    
    nodes.each(function(d) {
        const x = d.x || 0;
        const y = d.y || 0;
        minX = Math.min(minX, x);
        maxX = Math.max(maxX, x);
        minY = Math.min(minY, y);
        maxY = Math.max(maxY, y);
    });
    
    // 加 padding
    const padding = 100;
    minX -= padding;
    maxX += padding;
    minY -= padding;
    maxY += padding;
    
    const contentWidth = maxX - minX;
    const contentHeight = maxY - minY;
    const svgWidth = window.innerWidth;
    const svgHeight = window.innerHeight;
    
    // 计算缩放比例，使内容适应视口
    const scale = Math.min(
        svgWidth / contentWidth,
        svgHeight / contentHeight,
        1.5  // 最大缩放不超过 1.5x
    ) * 0.9;  // 留 10% 呼吸空间
    
    // 计算居中偏移
    const centerX = (minX + maxX) / 2;
    const centerY = (minY + maxY) / 2;
    const translateX = svgWidth / 2 - centerX * scale;
    const translateY = svgHeight / 2 - centerY * scale;
    
    // 应用 transform（通过 D3 zoom）
    const svg = d3.select('svg');
    const zoomBehavior = d3.zoom()
        .scaleExtent([0.1, 5])
        .on('zoom', (event) => {
            svg.select('g').attr('transform', event.transform);
        });
    
    svg.call(zoomBehavior);
    
    // 动画过渡到目标视图
    svg.transition()
        .duration(750)
        .call(
            zoomBehavior.transform,
            d3.zoomIdentity
                .translate(translateX, translateY)
                .scale(scale)
        );
}

// 在力导向模拟稳定后调用
simulation.on('end', () => {
    fitToContent();
});

// 也绑定到"重置缩放"按钮
document.querySelector('.btn-reset-zoom')?.addEventListener('click', fitToContent);

// 窗口大小变化时也重新适配
window.addEventListener('resize', fitToContent);
```

### 确保 D3 zoom 范围不受限

```javascript
// 确保 zoom 行为的 translateExtent 足够大或不设限
const zoomBehavior = d3.zoom()
    .scaleExtent([0.05, 10])
    // 不设 translateExtent，允许无限平移
    .on('zoom', (event) => {
        container.attr('transform', event.transform);
    });
```

---

## 修复 E: PRD HTML — 全局样式提升（向 9.5 分迈进）

这些是非 bug 修复的美观度提升：

```css
/* ===== 修改 5: 整体质感提升 ===== */

/* 1. 优先级标签样式统一 */
.priority-tag {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.5px;
}
.priority-tag.p0 { background: #fed7d7; color: #c53030; }
.priority-tag.p1 { background: #fefcbf; color: #b7791f; }
.priority-tag.p2 { background: #c6f6d5; color: #276749; }
.priority-tag.p3 { background: #e2e8f0; color: #4a5568; }

/* 2. L1 模块卡片悬浮效果 */
.l1 {
    transition: box-shadow 0.2s ease, transform 0.2s ease;
}
.l1:hover {
    box-shadow: 0 4px 12px rgba(0,0,0,0.12);
    transform: translateY(-1px);
}

/* 3. L3 功能行交替背景 */
.l3:nth-child(odd) {
    background: #fafbfc;
}
.l3:hover {
    background: #f0f4ff;
}

/* 4. 验收标准中的数字高亮 */
.acc-value {
    color: #2b6cb0;
    font-weight: 600;
}

/* 5. 搜索高亮 */
.search-highlight {
    background: #fff3cd;
    padding: 0 2px;
    border-radius: 2px;
}

/* 6. 导出统计栏 */
.stats-bar {
    display: flex;
    gap: 16px;
    padding: 8px 24px;
    background: rgba(255,255,255,0.1);
    font-size: 12px;
    color: rgba(255,255,255,0.85);
}
.stats-bar .stat {
    display: flex;
    align-items: center;
    gap: 4px;
}
.stats-bar .stat-value {
    font-weight: 700;
    color: #fff;
}
```

在 header 区域添加统计栏：

```html
<div class="stats-bar">
    <div class="stat">功能总数 <span class="stat-value">{total_features}</span></div>
    <div class="stat">P0 <span class="stat-value">{p0_count}</span></div>
    <div class="stat">P1 <span class="stat-value">{p1_count}</span></div>
    <div class="stat">模块数 <span class="stat-value">{module_count}</span></div>
    <div class="stat">一致性问题 <span class="stat-value">{audit_count}</span></div>
    <div class="stat">版本 <span class="stat-value">{version}</span></div>
</div>
```

---

## 验证清单

- [ ] 滚动页面时，标题+搜索框+Tab 栏始终固定在视口顶部
- [ ] 语音指令表的表头列与数据列完全对齐，表头紧贴在数据上方
- [ ] 按键映射表、灯效定义表等所有表格的表头都正确对齐
- [ ] App 端没有空白的简述单元格（失败模块有降级显示）
- [ ] 脑图 HTML 打开后内容居中，无右侧空白
- [ ] 脑图节点可以平移到任意位置，不被裁剪
- [ ] "重置缩放"按钮点击后内容回到居中适配状态
- [ ] 窗口大小变化时脑图自动重新适配
- [ ] P0/P1/P2/P3 标签颜色统一且清晰
- [ ] header 区域有功能统计栏
