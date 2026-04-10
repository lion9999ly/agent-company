# HUD Demo 技术规格

## 产品上下文

给供应商和投资人演示智能骑行座舱 HUD 体验。核心传达："被保护着"的安全感知，不是花哨的信息展示板。ADAS 是竞品做不到的差异化。

单 HTML 文件，零外部依赖，双击浏览器打开。

---

## 全局契约（所有模块必须遵守）

### DOM ID 表

| ID | 元素类型 | 用途 | 所属模块 |
|----|---------|------|---------|
| `#hud-root` | div | 最外层容器，全屏 | M1 |
| `#zone-lt` | div | 左上角区域 | M1 |
| `#zone-rt` | div | 右上角区域 | M1 |
| `#zone-lb` | div | 左下角区域 | M1 |
| `#zone-rb` | div | 右下角区域 | M1 |
| `#center-clear` | div | 中央留空区域（不放任何内容）| M1 |
| `#bottom-bar` | div | 底部信息栏（速度、导航简要）| M1 |
| `#timeline` | div | 时间轴容器 | M4 |
| `#timeline-progress` | div | 时间轴进度条 | M4 |
| `#timeline-label` | span | 当前剧本名称 | M4 |
| `#sandbox` | div | 右侧沙盒面板 | M5 |
| `#boot-overlay` | div | 开机自检动画覆盖层 | M5 |

### 状态枚举

```javascript
const MODE = {
  CRUISE: 'cruise',     // 骑行主界面（默认）
  NAV: 'nav',           // 导航
  CALL: 'call',         // 来电
  MUSIC: 'music',       // 音乐
  MESH: 'mesh',         // Mesh 组队通信
  WARN: 'warn',         // ADAS 预警
  DVR: 'dvr',           // 行车记录/录制
};
```

### 优先级（数字越大越高，高优先级抢占低优先级）

```javascript
const PRIORITY = {
  cruise: 0,
  dvr: 1,
  music: 2,
  mesh: 3,
  nav: 4,
  call: 5,
  warn: 6,  // 预警永远最高，不可被抢占
};
```

### CSS 变量表

```css
:root {
  /* 背景 */
  --bg: #050607;
  --bg-zone: rgba(255,255,255,0.04);

  /* 功能色 */
  --c-speed: #ffffff;      /* 速度 - 白 */
  --c-nav: #4A90E2;        /* 导航 - 蓝 */
  --c-warn: #FF3B30;       /* 预警 - 红 */
  --c-mesh: #5AC8FA;        /* 组队 - 青 */
  --c-music: #AF52DE;      /* 音乐 - 紫 */
  --c-call: #34C759;       /* 来电 - 绿 */
  --c-dvr: #FF9500;        /* 录制 - 橙 */
  --c-text: #ffffff;
  --c-muted: rgba(255,255,255,0.58);
  --c-dim: rgba(255,255,255,0.18);
}

/* 单绿光波导模式 */
.theme-green {
  --bg: #010a02;
  --c-speed: #8CFF7A;
  --c-nav: #6dff6d;
  --c-warn: #b8ff7a;
  --c-mesh: #7dff9d;
  --c-music: #56d856;
  --c-call: #8fff8f;
  --c-dvr: #a0ff60;
  --c-text: #9dff9d;
  --c-muted: rgba(157,255,157,0.58);
  --c-dim: rgba(157,255,157,0.18);
}
```

### JS 全局 API（M2 定义，M3-M5 调用）

```javascript
// 状态控制
function setMode(mode)        // 切换状态（自动处理优先级抢占）
function getMode()            // 获取当前状态
function getPriority(mode)    // 获取状态优先级数值
function pushMode(mode)       // 压入优先级栈
function popMode(mode)        // 弹出（恢复之前的状态）

// 事件触发
function emitEvent(event)     // 触发事件（event 对象含 type, data, direction）
function emitWarning(direction) // 便捷方法：触发 ADAS 预警，direction='front'|'left'|'right'

// 速度分级
function setSpeed(kmh)        // 设置当前速度，自动计算 S0-S3
function getSpeedLevel()      // 返回 'S0'|'S1'|'S2'|'S3'

// 渲染触发（M2 调用 M3）
function renderAll()          // 根据当前状态重新渲染所有区域
```

### S0-S3 速度分级规则

| 等级 | 速度范围 | 信息密度 | 显示内容 |
|------|---------|---------|---------|
| S0 | 0-30 km/h | 全量 | 四角全部显示 + 底部完整信息 |
| S1 | 31-60 km/h | 标准 | 四角显示 + 底部精简 |
| S2 | 61-100 km/h | 精简 | 仅速度 + 导航 + 预警 |
| S3 | 101+ km/h | 最简 | 仅速度 + 预警 |

---

## 模块规格

### M1 骨架（skeleton.css + skeleton.html）

**职责：** HTML 结构 + CSS 变量定义 + 四角布局 + 全屏黑色背景

**产出文件：**
- `m1_skeleton.css` — 所有 CSS（变量 + 布局 + 动画关键帧）
- `m1_skeleton.html` — body 内的 HTML 结构（不含 `<html>` `<head>` 标签）

**要求：**
- 全屏黑色背景模拟护目镜视角
- 四角绝对定位，中央完全留空
- 底部信息栏固定在底部
- 预警闪烁动画 `@keyframes warn-flash` 定义在 CSS 里
- `.theme-green` 类实现单绿模式变量覆盖
- 每个 zone 有 `.zone-label`（区域标题）和 `.zone-content`（动态内容区）
- 响应式：最小支持 1024x768

**预警闪烁规则：**
- 前方预警：zone-lt + zone-rt 同时红色边框脉冲
- 左后预警：zone-lb 红色边框脉冲
- 右后预警：zone-rb 红色边框脉冲
- 脉冲频率：500ms 一次，持续 3 秒后自动消退

### M2 状态机（state_machine.js）

**职责：** 7 状态定义、优先级栈、状态切换逻辑、速度分级

**产出文件：** `m2_state_machine.js` — 纯 JS，不操作 DOM

**要求：**
- 实现上述 JS 全局 API 的所有函数
- 优先级栈：高优先级状态进入时压栈，退出时弹栈恢复之前状态
- `setMode('warn')` 必须立即切换，无论当前状态是什么
- `setMode('music')` 在当前为 `nav` 时被拒绝（优先级不够）
- `setSpeed()` 改变速度后自动调用 `renderAll()` 更新信息密度
- 每次状态变化都调用 `renderAll()`

### M3 渲染器（renderers.js）

**职责：** 根据当前状态和速度等级，更新四角 + 底部的 DOM 内容

**产出文件：** `m3_renderers.js` — JS，操作 DOM

**要求：**
- `renderAll()` 实现：读取 `getMode()` 和 `getSpeedLevel()`，更新所有 zone 的 textContent/innerHTML
- 每个状态的四角内容定义：

| 状态 | LT | RT | LB | RB | 底部 |
|------|----|----|----|----|------|
| cruise | 速度+骑行状态 | 电量+信号+温度 | — | — | 时间+里程 |
| nav | 速度 | 下一路口距离 | 转向箭头 | ETA | 路线名称 |
| call | 速度 | 来电人名 | 接听/挂断提示 | — | 通话时长 |
| music | 速度 | — | 曲名+歌手 | 上一首/下一首 | 播放进度 |
| mesh | 速度 | 队友数量 | 队友距离 | 队伍状态 | 频道名 |
| warn | 速度 | 威胁类型 | 方向指示 | 距离 | "注意安全" |
| dvr | 速度 | 录制状态红点 | — | — | 录制时长 |

- `emitWarning(direction)` 时，给对应 zone 添加 `.warn-flash` class，3 秒后移除
- S2/S3 速度等级下，只渲染表格中有内容的区域，其他区域隐藏

### M4 剧本（scenarios.js）

**职责：** 3 条自动剧本 + 时间轴控制

**产出文件：** `m4_scenarios.js` — JS，调用 M2 的 emitEvent API

**三条剧本：**

**剧本 1：日常通勤（45 秒）**
```
0s  — 开机自检完成，进入 cruise，速度 0
3s  — 速度升到 40（S1）
8s  — 收到导航：目的地"公司"，3.2km
12s — 速度升到 65（S2），信息自动精简
18s — 导航提示："前方 200m 左转"
22s — 速度降到 35（S1），信息恢复
25s — 来电："张三"，持续 5 秒
30s — 挂断，恢复导航
35s — 导航提示："到达目的地"
40s — 速度降到 0，回到 cruise
45s — 剧本结束
```

**剧本 2：紧急场景（40 秒）**
```
0s  — cruise，速度 60（S2）
5s  — 前方预警：FCW（前碰撞预警），LT+RT 红色闪烁
8s  — 预警消退，恢复
12s — 左后预警：BSD（盲区检测），LB 红色闪烁
15s — 预警消退
18s — 速度升到 80（S2）
22s — 右后预警：开门预警（dooring），RB 红色闪烁
25s — 预警消退
28s — 连续前方预警：行人检测，LT+RT 闪烁
31s — 预警消退
35s — 速度降到 50，恢复正常
40s — 剧本结束
```

**剧本 3：组队骑行（50 秒）**
```
0s  — cruise，速度 45（S1）
5s  — Mesh 组队：加入"周末骑行群"，3 人
8s  — 启动 DVR 录制
12s — 速度升到 70（S2）
18s — 导航提示："前方进入山路"
22s — 队友消息："前面有弯道注意"
26s — 前方预警抢占：弯道预警
29s — 预警消退，恢复 mesh
33s — 音乐自动播放（低优先级叠加）
38s — 速度降到 40（S1），全量信息恢复
42s — Mesh 通知："到达集合点"
45s — 停止录制
48s — 速度 0，cruise
50s — 剧本结束
```

**时间轴要求：**
- 底部进度条显示当前剧本进度
- 可播放/暂停（空格键）
- 可点击跳转到任意时间点
- 剧本名称显示在时间轴旁边
- 数字键 1/2/3 切换剧本

### M5 控制（controls.html + controls.js）

**职责：** 沙盒面板、键盘快捷键、A/B 主题切换、开机自检

**产出文件：**
- `m5_controls.html` — 沙盒面板的 HTML 片段
- `m5_controls.js` — 键盘事件 + 面板交互 + 开机动画

**沙盒面板分组：**
```
ADAS 预警
  [前方碰撞] [左后盲区] [右后盲区] [开门预警] [行人检测]
通信
  [来电：张三] [来电：李四] [Mesh 加入] [Mesh 离开]
媒体
  [音乐播放] [音乐暂停] [下一首]
导航
  [导航开始] [左转提示] [到达目的地]
录制
  [开始录制] [停止录制] [标记精彩]
系统
  [速度 0] [速度 40] [速度 80] [速度 120]
```

**键盘快捷键：**
| 按键 | 功能 |
|------|------|
| 1/2/3 | 切换剧本 |
| 空格 | 播放/暂停剧本 |
| T | 切换 OLED/单绿主题 |
| S | 切换沙盒面板显示/隐藏 |
| W | 触发前方预警 |
| A | 触发左后预警 |
| D | 触发右后预警 |
| Esc | 重置到 cruise |

**开机自检动画（3 秒）：**
- 0-1s：黑屏，logo 淡入
- 1-2s：四角区域逐个亮起（LT→RT→RB→LB）
- 2-3s：底部信息栏滑入，覆盖层淡出
- 3s：进入 cruise 默认状态

---

## 拼装规则

```python
# assemble.py
output = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Smart Riding HUD Demo</title>
<style>
{read('m1_skeleton.css')}
</style>
</head>
<body>
{read('m1_skeleton.html')}
{read('m5_controls.html')}
<script>
// === M2: State Machine ===
{read('m2_state_machine.js')}
// === M3: Renderers ===
{read('m3_renderers.js')}
// === M4: Scenarios ===
{read('m4_scenarios.js')}
// === M5: Controls ===
{read('m5_controls.js')}
// === Boot ===
document.addEventListener('DOMContentLoaded', bootSequence);
</script>
</body>
</html>"""
```

JS 加载顺序固定：M2 → M3 → M4 → M5。后加载的模块可以调用先加载的 API。
