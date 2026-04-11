# HUD Demo Tech Spec 补充：三种光学模式

> 本文档是 hud_demo_tech_spec.md 的补充，新增三种光学模式的 demo 模拟。
> 基于 optical_constraints_v2.md 的真实硬件参数。

---

## 新增全局状态

```javascript
const OPTICS = {
  FREEFORM: 'freeform',     // 路径 1：OLED + FreeForm 棱镜
  WAVEGUIDE_COLOR: 'wg_color', // 路径 2：MicroLED + 全彩树脂光波导
  WAVEGUIDE_GREEN: 'wg_green', // 路径 3：MicroLED + 单绿树脂光波导
};

let currentOptics = OPTICS.FREEFORM; // 默认

function setOptics(mode) {
  // 切换光学模式，重新布局 + 重新渲染
  currentOptics = mode;
  applyOpticsLayout();
  renderAll();
}

window.OPTICS = OPTICS;
window.setOptics = setOptics;
window.currentOptics = currentOptics; // 供渲染器读取
```

---

## 三种模式的可视区域定义

### 模式 A：FreeForm 棱镜（单目，38° FOV）

**硬件参数：**
- 面板：SeeYA 0.49" 1920×1080
- FOV：38° 对角线
- 眼盒：10×7mm
- 到眼亮度：全彩 900-1,500 nits / 单绿 ~10,000 nits
- 光学效率：~50%
- 虚像距离：~2-3m

**Demo 模拟：**
- 画布 1280×720 上，可视区域为**居中的一个圆角矩形**
- 可视区域尺寸：约 840×480px（占画布 65%×67%）
- 四角布局在可视区域内部
- 可视区域外部为黑色蒙版（模拟护目镜不可见区域）

```css
.optics-freeform #hud-viewport {
  position: absolute;
  top: 50%; left: 50%;
  transform: translate(-50%, -50%);
  width: 840px; height: 480px;
  border-radius: 40px;
  overflow: hidden;
  /* 所有 HUD 信息在此区域内 */
}
.optics-freeform #hud-mask {
  /* 黑色蒙版覆盖可视区域外 */
  position: absolute; inset: 0;
  background: radial-gradient(ellipse 840px 480px at center, transparent 50%, black 51%);
  pointer-events: none;
}
```

### 模式 B：全彩树脂光波导（双目，28-50° FOV）

**硬件参数：**
- 光源：MicroLED（JBD Hummingbird 级别）
- FOV：28-50°（demo 用 35° 模拟中间值）
- 双目独立显示，放在视角两侧
- 到眼亮度：>1,000 nits
- 彩虹效应：存在（demo 可选模拟）

**Demo 模拟：**
- 画布 1280×720 上，**左右各一个独立窗口**
- 左窗口：x=40, y=120, w=360, h=480（左眼）
- 右窗口：x=880, y=120, w=360, h=480（右眼）
- 中间 480px 宽度完全留空（骑手直视道路区域）
- 每个窗口内部有自己的信息布局

```css
.optics-wg-color #hud-viewport-left,
.optics-wg-color #hud-viewport-right {
  position: absolute;
  width: 360px; height: 480px;
  border-radius: 20px;
  overflow: hidden;
}
.optics-wg-color #hud-viewport-left { left: 40px; top: 120px; }
.optics-wg-color #hud-viewport-right { right: 40px; top: 120px; }
.optics-wg-color #hud-center-gap {
  /* 中间留空标注 */
  position: absolute;
  left: 400px; width: 480px; height: 100%;
  border-left: 1px dashed rgba(255,255,255,0.1);
  border-right: 1px dashed rgba(255,255,255,0.1);
}
```

**双目信息分配：**

| 信息 | 左眼 | 右眼 | 原因 |
|------|------|------|------|
| 速度 | ✓ | — | 速度是最常看的，放在左侧（多数人视线偏左） |
| 导航转向 | ✓ | — | 转向箭头放左眼直觉自然 |
| 导航距离/ETA | — | ✓ | 补充信息放右眼 |
| ADAS 预警 | ✓（方向相关）| ✓（方向相关）| 双眼同时闪烁增强警示 |
| 来电/音乐 | — | ✓ | 非安全信息放右眼 |
| Mesh 组队 | — | ✓ | 同上 |
| DVR 录制 | — | ✓（小红点）| 最低优先级信息 |

### 模式 C：单绿树脂光波导（双目，同布局）

**Demo 模拟：**
- 布局与模式 B 完全相同（双目两侧窗口）
- 颜色全部变为绿色系（复用 .theme-green 变量）
- 明度分级区分信息类型：

| 明度等级 | 用途 | CSS |
|---------|------|-----|
| 最亮（100%）| ADAS 预警 | color: #ccff66 |
| 亮（80%）| 速度、导航关键信息 | color: #8CFF7A |
| 中等（60%）| 次要信息、来电 | color: #6dff6d |
| 暗（40%）| 背景信息、标签 | color: rgba(140,255,122,0.4) |

---

## 新增键盘快捷键

| 按键 | 功能 |
|------|------|
| F1 | 切换到模式 A（FreeForm） |
| F2 | 切换到模式 B（全彩光波导） |
| F3 | 切换到模式 C（单绿光波导） |

模式切换时有 0.5s 过渡动画（opacity 渐变）。

---

## 沙盒面板新增

```html
<section data-group="optics" class="sandbox-group">
  <h4>光学模式</h4>
  <button data-event="optics-freeform">FreeForm 棱镜 (38°)</button>
  <button data-event="optics-wg-color">全彩光波导 (35°)</button>
  <button data-event="optics-wg-green">单绿光波导 (35°)</button>
</section>
```

---

## 对模块的影响

### M1 骨架
- 新增三套布局 CSS（.optics-freeform / .optics-wg-color / .optics-wg-green）
- 新增 #hud-viewport（单目模式）和 #hud-viewport-left/#hud-viewport-right（双目模式）
- 新增 #hud-mask（FreeForm 模式的椭圆蒙版）
- 四角 zone 在 FreeForm 模式下保持原位，在光波导模式下重新分配到左右窗口

### M2 状态机
- 新增 OPTICS 枚举和 setOptics 函数
- 新增 applyOpticsLayout() 函数（切换 body class + 移动 zone DOM 位置）

### M3 渲染器
- renderAll() 需要感知 currentOptics
- 光波导双目模式下，按"双目信息分配表"决定信息放左眼还是右眼
- 模式 C 下所有颜色走 .theme-green 变量

### M4 剧本
- 不变（剧本触发的是状态和事件，跟光学模式无关）
- 可在剧本开头加 setOptics() 设定默认光学模式

### M5 控制
- 沙盒面板新增光学模式分组
- 键盘 F1/F2/F3 绑定
- bootSequence 默认用 FreeForm 模式

---

## 新增截图场景（visual_criteria 补充）

### S15: 模式 A FreeForm 全貌
**验收：** 中央有椭圆可视区域，外部为黑色蒙版，四角信息在可视区域内

### S16: 模式 B 全彩光波导全貌
**验收：** 左右各一个独立窗口，中间大面积留空，信息分布在两个窗口中

### S17: 模式 C 单绿光波导全貌
**验收：** 布局同 S16 但全绿色，不同信息有明度差异

### S18: 模式切换过渡
**验收：** 从 FreeForm 切到光波导时有平滑过渡（不是突然跳变）

---

## 新增测试断言（test_spec.js 补充）

```javascript
// T17: 光学模式
assertExists(window.OPTICS, 'OPTICS 枚举存在');
assertExists(window.setOptics, 'setOptics 函数存在');
assertEqual(Object.keys(window.OPTICS).length, 3, 'OPTICS 有 3 种模式');

// T18: 光学模式切换
window.setOptics('freeform');
assert(document.body.classList.contains('optics-freeform'), 'FreeForm 模式 class');
window.setOptics('wg_color');
assert(document.body.classList.contains('optics-wg-color'), '全彩光波导模式 class');
window.setOptics('wg_green');
assert(document.body.classList.contains('optics-wg-green'), '单绿光波导模式 class');

// T19: 双目模式下左右窗口存在
window.setOptics('wg_color');
assertExists(document.getElementById('hud-viewport-left'), '左眼窗口存在');
assertExists(document.getElementById('hud-viewport-right'), '右眼窗口存在');

// T20: FreeForm 模式下蒙版存在
window.setOptics('freeform');
assertExists(document.getElementById('hud-mask'), 'FreeForm 蒙版存在');
```
