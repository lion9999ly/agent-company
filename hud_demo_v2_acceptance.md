# HUD Demo v2 验收清单

> 每一条都是可测试的断言。CC 交付前必须逐条自证 PASS，scorer 逐条机器验证。
> 任何一条 FAIL = 不可提交。

---

## A. 物理布局（7条）

A1. 左右各一条竖向显示带，中央区域无任何 HUD 元素（检查方法：中央区域 DOM 子元素数 = 0）
A2. 显示带位于面镜高度中偏上（strip-top-offset 默认值使显示带上边缘在视口上方 1/4 位置）
A3. 中央间距满足辐辏约束（默认 ≥ 400px，可通过 sandbox 调节）
A4. 竖条宽度、高度、位置通过 sandbox 滑块实时可调（改变滑块值后 100ms 内 DOM 样式更新）
A5. 路面背景默认可见（opacity > 0），三种模式均为半透明叠加
A6. sandbox 提供背景图片上传按钮（input type=file），上传后替换默认背景
A7. zone 之间有明确间隔，非活跃 zone 不填充背景色——不是从上到下铺满

## B. 光学模式（8条）

B1. F1 切换 FreeForm：全彩、背景 opacity 默认 ~50%
B2. F2 切换全彩波导：全彩、整体亮度比 FreeForm 降低 30-40%、背景 opacity 默认 ~70%（透过率更高）
B3. F3 切换单绿：所有可见元素颜色为 #00FF00，无例外
B4. 单绿模式下 HTML 渲染路径中不含任何 emoji Unicode 字符（U+1F000-U+1FFFF）
B5. 单绿模式信息区分仅通过 opacity 属性值（不用 rgba alpha 通道），检查方法：CSS 中 .optics-green 相关规则不含 rgba(0,255,0, 非1值)
B6. 单绿模式亮度分级可通过 sandbox 调节（紧急/主要/次要/背景四个输入框）
B7. FOV 滑块改变实际显示区域宽度（FOV 38° 时竖条宽度 > FOV 28° 时竖条宽度）
B8. 同一个 ADAS 预警在 FreeForm（全彩+高亮）、全彩波导（全彩+低亮）、单绿（绿色+opacity）下有明显可见的视觉差异

## C. ADAS 预警（10条）

C1. 6种预警类型全部可通过 sandbox 按钮触发：FCW、BSD、Dooring、行人、LDW左、LDW右
C2. 每个预警同时显示：威胁类型、方向、距离(m)、关闭速度(km/h)、TTC(s)——五项全部可见
C3. 所有预警内容在 zone 可视区域内完整显示，无溢出（检查：zone 无 overflow:visible，内容底部 ≤ zone 底部）
C4. BSD 触发时：左侧竖条外边缘（左边）4px 闪烁
C5. Dooring 触发时：右侧竖条外边缘（右边）4px 闪烁
C6. LDW 左侧压线：左侧竖条内边缘（右边）虚线闪烁
C7. LDW 右侧压线：右侧竖条内边缘（左边）虚线闪烁
C8. 多重预警并发时：TTC 最短的预警占主要区域（大字），其他预警弱化但仍可见（小字，不消失）
C9. activeWarnings 数组长度上限 2，超出时自动移除 TTC 最长的
C10. 预警方向用 SVG 箭头图形表示，不使用纯文字 "front/left/right"

## D. 状态机（5条）

D1. 7种模式全部可触发：cruise/nav/call/music/mesh/warn/dvr
D2. 优先级抢占：高优先级触发时，低优先级信息缩小（scale ≤ 0.7, opacity ≤ 0.6）但不从 DOM 移除
D3. 预警结束后自动恢复之前状态（warn 结束 → 回到 nav/music/cruise 等之前模式）
D4. S2（61-100km/h）时：导航降级为箭头或简易地图，音乐/组队只保留小图标
D5. S3（>100km/h）时：只显示速度 + ADAS 预警 + 简化导航箭头，其他全部隐藏

## E. 导航（4条）

E1. 三级显示均有实际视觉内容——箭头模式：SVG 转向箭头+距离；简易地图：SVG 路口简图；全信息地图：SVG 路线折线图
E2. S2/S3 速度时自动降级（sandbox 拖速度滑块到 80+，导航自动切到箭头模式）
E3. 导航地图显示在左侧竖条中段
E4. 用户可通过 sandbox 按钮手动切换三级

## F. 通信与媒体（4条）

F1. 来电时：来电人名称 + 接听/拒绝按钮占据左侧竖条主要区域，导航缩小到角落
F2. 交通标志识别：RT zone 持续显示标志值（如"限速 60"），直到 setTrafficSign 被新值调用才替换
F3. Mesh 组队：RB zone 用 SVG 简图显示队友相对位置（2-3个点+距离标注），不只是文字
F4. DVR 录像：显示 REC 指示灯（SVG 红点+闪烁），语音标记时显示 "Moment saved!"

## G. 剧本（8条）

G1. 4个剧本全部可播放：commute(50s)/emergency(45s)/group(55s)/touring(60s)
G2. 每个剧本包含 ≥ 2 次 showVoiceSubtitle 调用（语音交互字幕）
G3. emergency 剧本包含 LDW 场景（左侧或右侧压线）
G4. emergency 剧本包含至少 1 次两个预警同时存在的并发场景
G5. touring 剧本包含 ≥ 2 次 setTrafficSign 调用（如 limit60 → limit80）
G6. touring 剧本包含语音标记精彩瞬间（showMomentSaved 调用）
G7. touring 剧本事件总数 ≥ 15（体现摩旅丰富体验）
G8. 语音字幕出现在底部非 HUD 可视区域（#bottom-bar 或类似位置）

## H. 图标与视觉（4条）

H1. 全部图标使用 SVG 线条图标，不使用任何 emoji（检查：HTML 中不含 U+1F000-U+1FFFF 范围字符）
H2. 预警边框使用脉冲 glow 效果（box-shadow 动画），不只是简单 border-color 切换
H3. 图标风格统一：细线条、无填充、统一描边宽度，HUD 科技感
H4. 整体视觉风格是产品原型级别，不是调试工具

## I. Sandbox 控件（5条）

I1. 光学模式切换（F1/F2/F3 快捷键 + 按钮）
I2. FOV 滑块（28-50°范围，实时改变显示区域宽度）
I3. 显示区域调节（竖条宽度、中央间距、背景透明度）
I4. 单绿亮度分级调节（四级百分比输入框）
I5. 背景图片上传（file input，上传后立即替换）

## J. 技术约束（4条）

J1. 单文件 HTML，总行数 ≤ 2500
J2. window 上暴露：setMode, getMode, setSpeed, setOptics, emitWarning, emitEvent, playScenario
J3. 所有可调参数存储在全局 CONFIG 对象，sandbox 修改后实时生效
J4. CSS 变量使用 clamp() 响应式

---

## 总计：59 条验收标准

通过门槛：59/59 全部 PASS
任何 FAIL = 打回重做对应模块
