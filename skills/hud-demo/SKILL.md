---
name: hud-demo
description: Use when generating HUD Demo HTML files for supplier/investor presentations, involving four-corner layout, state machine, ADAS warnings, and optical mode switching
metadata:
  author: leo
  version: "1.0"
---

# HUD Demo Skill

## Overview

HUD Demo 是智能骑行头盔的核心演示产物，单 HTML 文件零外部依赖，传达"被保护着"的安全感知体验。ADAS 是竞品做不到的差异化。

**核心原则：骑手用余光扫视，信息必须一瞥可读。**

## When to Use

- 给供应商/投资人演示 HUD 体验
- 生成符合技术规格的可运行 Demo
- 视觉验证 ADAS 预警效果
- A/B 光学方案对比展示

**When NOT to Use:**
- 非 HUD 相关的 UI 开发
- 需要外部依赖的 Web 应用

## DOM ID Contract

| ID | 用途 | 所属模块 |
|----|------|---------|
| #hud-root | 最外层容器 | M1 |
| #zone-lt | 左上角（速度） | M1 |
| #zone-rt | 右上角（设备状态） | M1 |
| #zone-lb | 左下角（通知） | M1 |
| #zone-rb | 右下角（导航） | M1 |
| #center-clear | 中央留空（永远不放内容） | M1 |
| #bottom-bar | 底部信息栏 | M1 |
| #timeline | 时间轴容器 | M4 |
| #sandbox | 沙盒面板 | M5 |
| #boot-overlay | 开机动画覆盖 | M5 |

## State Machine (7 Modes)

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

const PRIORITY = {
  cruise: 0, dvr: 1, music: 2, mesh: 3, nav: 4, call: 5, warn: 6,
};
```

## Warning Direction Mapping

| 方向 | 闪烁区域 |
|------|----------|
| front（前方） | zone-lt + zone-rt |
| left（左后） | zone-lb |
| right（右后） | zone-rb |

## Optical Modes

| 模式 | 配色 | 特点 |
|------|------|------|
| OLED 全彩（默认） | 功能色语义区分 | 速度白/导航蓝/预警红/组队青/音乐紫 |
| 光波导单绿 | 绿色系主题 | 成本低、亮度高、信息降噪 |

## Generator Segments

```
段1: CSS + HTML 骨架（布局、配色变量）
段2: 状态机 JS（7态、优先级栈、setMode API）
段3: 渲染函数（四角内容、预警闪烁）
段4: 自动剧本 + 时间轴（3条剧本、播放控制）
段5: 沙盒面板 + 光学切换 + 开机动画 + 快捷键
```

## Known Pitfalls

| 陷阱 | 规避方法 |
|------|----------|
| 单次生成超 500 行质量下降 | 分段生成，最后拼接 |
| 验收标准遗漏（如开机动画） | TaskSpec 逐条验证 |
| 预警方向映射错误 | 表驱动：front→lt+rt |
| 外部依赖引入 | Verifier 规则：no_external_deps |
| CSS 变量未遵守命名规范 | --c-xxx（颜色）、--s-xxx（尺寸）、--g-xxx（间距） |

## Verification Criteria

- [ ] 14 条验收标准全部通过
- [ ] Verifier 三层规则通过（global + type_html + auto）
- [ ] 7 个页面态全部可触发
- [ ] 预警闪烁方向正确
- [ ] A/B 光学切换视觉差异明显
- [ ] 双击浏览器可直接打开

## Key Files

```
demo_outputs/specs/hud_demo_tech_spec.md       # 技术规格（DOM ID、API）
demo_outputs/specs/hud_demo_test_spec.js       # 测试规格
demo_outputs/specs/hud_demo_visual_criteria.md # 视觉验收标准
demo_outputs/specs/tech_spec_optical_modes.md  # 光学模式定义
demo_outputs/hud_modules/*.js                  # 分段模块
scripts/roundtable/generator.py                # 分段生成器
scripts/roundtable/verifier.py                 # 三层验证
.ai-state/task_specs/HUD_Demo.json             # TaskSpec 定义
```

## Quick Reference

```bash
# 生成 Demo
python scripts/roundtable/roundtable.py --task HUD_Demo

# 直接运行已有 Demo
demo_outputs/hud_demo_final.html

# 视觉验收检查
# 打开 HTML，按 S 键进入沙盒模式，逐个触发事件验证
```