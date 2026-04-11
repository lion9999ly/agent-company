# HUD Demo 技术规格 v2

## 产品上下文

给供应商和投资人演示智能骑行座舱 HUD 体验。核心传达："被保护着"的安全感知，不是花哨的信息展示板。ADAS 是竞品做不到的差异化。

单 HTML 文件，零外部依赖，双击浏览器打开。

---

## Style Guide（所有模块必须遵守）

```
CSS：
- 变量命名：颜色 --c-xxx，尺寸 --s-xxx，间距 --g-xxx
- 类名 kebab-case：.zone-lt, .warn-flash, .theme-green
- 缩进 2 空格

JS：
- const/let 优先，禁止 var
- 函数声明用 function 关键字（不用箭头函数），保证 hoisting
- 函数名 camelCase：setMode, emitWarning, renderAll
- 常量全大写：MODE, PRIORITY, SCENARIOS
- 每个函数开头一行注释说明职责
- 缩进 2 空格

HTML：
- 语义化标签优先（section, nav, button）
- ID 用 kebab-case：zone-lt, bottom-bar
- 按钮必须用 <button> 不用 <div onclick>
```

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
| `#center-clear` | div | 中央留空区域（永远不放子元素）| M1 |
| `#bottom-bar` | div | 底部信息栏 | M1 |
| `#timeline` | div | 时间轴容器 | M1（结构）M4（逻辑）|
| `#timeline-progress` | div | 时间轴进度条 | M4 |
| `#timeline-label` | span | 当前剧本名称 | M4 |
| `#sandbox` | div | 右侧沙盒面板（默认隐藏）| M5 |
| `#boot-overlay` | div | 开机自检动画覆盖层 | M5 |

每个 zone 内部结构：
```html
<div id="zone-lt" class="hud-zone">
  <div class="zone-label">区域标题</div>
  <div class="zone-content">动态内容区</div>
</div>
```

### 状态枚举

```javascript
const MODE = {
  CRUISE: 'cruise',
  NAV: 'nav',
  CALL: 'call',
  MUSIC: 'music',
  MESH: 'mesh',
  WARN: 'warn',
  DVR: 'dvr',
};
```

### 优先级

```javascript
const PRIORITY = {
  cruise: 0, dvr: 1, music: 2, mesh: 3, nav: 4, call: 5, warn: 6,
};
```

### CSS 变量表

```css
:root {
  --bg: #050607;
  --bg-zone: rgba(255,255,255,0.04);
  --bg-zone-border: rgba(255,255,255,0.08);
  --c-speed: #ffffff;
  --c-nav: #4A90E2;
  --c-warn: #FF3B30;
  --c-mesh: #5AC8FA;
  --c-music: #AF52DE;
  --c-call: #34C759;
  --c-dvr: #FF9500;
  --c-text: #ffffff;
  --c-muted: rgba(255,255,255,0.58);
  --c-dim: rgba(255,255,255,0.18);
  --s-font-xl: clamp(32px, 4vw, 48px);
  --s-font-lg: clamp(18px, 2vw, 24px);
  --s-font-md: clamp(14px, 1.4vw, 18px);
  --s-font-sm: clamp(11px, 1vw, 14px);
  --g-zone-pad: clamp(12px, 1.5vw, 20px);
  --g-zone-gap: 8px;
}

.theme-green {
  --bg: #010a02;
  --bg-zone: rgba(0,255,0,0.04);
  --bg-zone-border: rgba(0,255,0,0.08);
  --c-speed: #8CFF7A;
  --c-nav: #6dff6d;
  --c-warn: #ccff66;
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

**setMode(mode) → boolean**
- mode 不在 MODE 枚举中 → console.warn，返回 false，不改变状态
- PRIORITY[mode] < PRIORITY[当前状态] → 拒绝，返回 false
- PRIORITY[mode] >= PRIORITY[当前状态] → 压栈当前状态，切换，调用 renderAll()，返回 true
- 特例：setMode('cruise') 总是成功，清空栈

**getMode() → string**

**getPriority(mode) → number**
- mode 无效返回 -1

**popMode()**
- 弹出栈顶恢复上一个状态，调用 renderAll()
- 栈空时恢复到 'cruise'

**emitEvent(event)**
- event: { type: string, data?: object, direction?: 'front'|'left'|'right' }
- 内部调用 setMode(event.type)
- type='warn' 时同时调用 flashWarning(event.direction)
- event.data 存入 window._lastEventData[event.type]

**emitWarning(direction)**
- 便捷方法，等同于 emitEvent({ type: 'warn', direction })

**flashWarning(direction)**
- direction='front' → zone-lt + zone-rt 加 .warn-flash
- direction='left' → zone-lb 加 .warn-flash
- direction='right' → zone-rb 加 .warn-flash
- 3 秒后移除 .warn-flash + popMode()

**setSpeed(kmh)**
- 负数视为 0，>300 视为 300
- 计算速度等级后调用 renderAll()

**getSpeedLevel() → 'S0'|'S1'|'S2'|'S3'**
- S0: 0-30, S1: 31-60, S2: 61-100, S3: 101+

**renderAll()**
- M2 定义空壳，M3 覆盖

### S0-S3 可见区域

| 等级 | 可见 | 隐藏方式 |
|------|------|---------|
| S0 | 全部 | — |
| S1 | 全部，底部精简 | — |
| S2 | LT + 当前状态最关键角 + 底部仅速度 | 其他 style.display='none' |
| S3 | LT（仅速度数字）+ 预警 | 其他 style.display='none' |

---

## 模块规格

### M1 骨架（m1_skeleton.css + m1_skeleton.html）

**产出：** `m1_skeleton.css`（CSS 变量+布局+动画）+ `m1_skeleton.html`（body 内 HTML，不含 doctype/html/head）

- body: background var(--bg), color var(--c-text), margin 0, overflow hidden
- #hud-root: position relative, 100vw × 100vh
- 四角: position absolute, 对应 top/bottom/left/right
- #center-clear: 居中，永远无子元素
- #bottom-bar: 底部固定
- #timeline: 底部固定，高 40px，包含 #timeline-progress + #timeline-label
- #sandbox: 空壳 div，默认 display:none
- @keyframes warn-flash: 红色边框脉冲，500ms 循环
- .warn-flash: 应用动画 + border-color var(--c-warn)
- .theme-green: 变量覆盖

### M2 状态机（m2_state_machine.js）

**产出：** `m2_state_machine.js`（纯逻辑，不操作 DOM）

- 定义 MODE, PRIORITY 挂到 window
- 内部状态：_currentMode, _modeStack, _currentSpeed, _speedLevel
- 实现所有 API 函数，挂到 window
- renderAll() 定义为空函数（M3 覆盖）
- window._lastEventData = {} 存储各类型最近事件数据

### M3 渲染器（m3_renderers.js）

**产出：** `m3_renderers.js`（DOM 操作）

- 覆盖 window.renderAll
- 渲染内容表：

| 状态 | LT | RT | LB | RB | bottom-bar |
|------|----|----|----|----|------|
| cruise | 速度+"巡航中" | 电量·信号·温度 | (清空) | (清空) | 时间·里程 |
| nav | 速度 | 距路口距离 | 转向箭头 | ETA | 路线名 |
| call | 速度 | 来电人 | 接听提示 | (清空) | 通话时长 |
| music | 速度 | (清空) | 曲名·歌手 | 控制按钮 | 播放进度 |
| mesh | 速度 | 队友数·距离 | 队伍状态 | 频道名 | 信号 |
| warn | 速度 | 威胁类型 | 方向 | 距离 | "注意安全" |
| dvr | 速度 | 🔴 REC | (清空) | (清空) | 录制时长 |

- "(清空)" = zone-content innerHTML 设为 ''
- S2/S3 隐藏规则见上方表格

### M4 剧本（m4_scenarios.js）

**产出：** `m4_scenarios.js`

- SCENARIOS 对象包含 commute(45s), emergency(40s), group(50s)
- 详细时序见下方
- playScenario(name), pauseScenario(), resumeScenario(), seekScenario(s)
- 用 setInterval(1000) 驱动
- 更新 #timeline-progress 宽度 + #timeline-label 文字

**剧本 1 日常通勤（45s）：** 0s 启动→3s 加速40→8s 导航→12s 加速65(S2)→18s 左转提示→22s 减速35(S1)→25s 来电→30s 挂断→35s 到达→40s 停车→45s 结束

**剧本 2 紧急场景（40s）：** 0s 速度60→5s 前方FCW→8s 恢复→12s 左后BSD→15s 恢复→18s 加速80→22s 右后dooring→25s 恢复→28s 前方行人→31s 恢复→35s 减速50→40s 结束

**剧本 3 组队骑行（50s）：** 0s 速度45→5s Mesh加入→8s DVR开始→12s 加速70→18s 导航山路→22s 队友消息→26s 弯道预警→29s 恢复→33s 音乐→38s 减速40→42s 集合点→45s 停DVR→48s 停车→50s 结束

### M5 控制（m5_controls.html + m5_controls.js）

**产出：** `m5_controls.html`（沙盒面板+boot overlay HTML）+ `m5_controls.js`（交互逻辑）

- 沙盒面板分 6 组（ADAS/通信/媒体/导航/录制/系统），每组用 section + h4
- 所有按钮用 data-event 属性，JS 统一绑定
- 键盘快捷键：1/2/3 剧本, Space 播放暂停, T 主题, S 沙盒, W/A/D 预警, Esc 重置
- bootSequence(): 0-1s logo淡入, 1-2s 四角逐个亮, 2-2.5s 底部滑入, 2.5-3s overlay淡出

---

## 拼装脚本

CC 创建 `demo_outputs/assemble.py`，内容：

```python
#!/usr/bin/env python3
"""拼装 HUD Demo 模块为单 HTML 文件"""
import sys
from pathlib import Path

MODULES_DIR = Path(__file__).parent / "hud_modules"
OUTPUT_FILE = Path(__file__).parent / "hud_demo_final.html"

def read(filename):
    path = MODULES_DIR / filename
    if not path.exists():
        print(f"错误: {path} 不存在")
        sys.exit(1)
    return path.read_text(encoding="utf-8")

html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0,viewport-fit=cover">
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
document.addEventListener('DOMContentLoaded', function() {{
  bootSequence();
}});
</script>
</body>
</html>"""

OUTPUT_FILE.write_text(html, encoding="utf-8")
print(f"拼装完成: {OUTPUT_FILE}")
print(f"文件大小: {len(html) / 1024:.1f} KB, 行数: {len(html.splitlines())}")
```
