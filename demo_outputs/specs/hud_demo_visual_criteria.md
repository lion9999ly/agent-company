# HUD Demo 视觉验收标准 v2

> CC 用 puppeteer 截图，每张截图 + 对应标准发给多模态 LLM 审查。

---

## 截图实现说明

CC 创建 `demo_outputs/screenshot.js`，使用 puppeteer：

```javascript
const puppeteer = require('puppeteer');
// npm install puppeteer（首次）

// 打开 HTML，等 DOMContentLoaded + 额外 4 秒（开机动画 3s + 缓冲 1s）
// 然后按以下清单逐个截图
```

**状态触发方式：** 通过 `page.evaluate()` 调用 JS API
**等待方式：** 每次触发后 `await page.waitForTimeout(1000)` 等渲染完成
**截图分辨率：** 1280×720（模拟骑行头盔 HUD 比例）
**截图保存：** `demo_outputs/screenshots/S{编号}_{场景名}.png`

**开机动画截帧：** 不截。开机动画用 setTimeout 驱动，headless 下时序可能不准确。改为等 5 秒后验证最终状态。

---

## 截图清单

### S1: 骑行主界面（cruise，S1 速度）

**触发：**
```javascript
await page.waitForTimeout(5000); // 等开机动画完成
await page.evaluate(() => { setSpeed(40); setMode('cruise'); });
await page.waitForTimeout(1000);
```

**验收（给 LLM 的标准）：**
1. 背景为全黑或极深色（不是灰色、不是白色）
2. 屏幕四角各有一个信息区域，带有半透明背景区分
3. 左上角显示速度数字（应可见"40"或类似数字）和状态文字
4. 右上角显示设备信息（电量/信号/温度等）
5. 屏幕正中央完全留空，无任何文字或图形
6. 底部有一行信息栏
7. 文字主色调为白色，字号足够大（速度数字应为屏幕上最大的文字）
8. 整体视觉干净，信息量不多，一瞥可读

### S2: 导航状态（nav）

**触发：**
```javascript
await page.evaluate(() => {
  setSpeed(40);
  setMode('cruise');
  emitEvent({type:'nav', data:{dest:'公司', dist:'3.2km'}});
});
await page.waitForTimeout(1000);
```

**验收：**
1. 左上角仍有速度显示
2. 至少一个角落显示导航相关信息（距离、方向、目的地等）
3. 导航信息文字带有蓝色调（不是白色）
4. 中央区域仍然留空
5. 与 S1 对比，明显看出"进入了不同的模式"

### S3: ADAS 前方预警（warn, front）

**触发：**
```javascript
await page.evaluate(() => {
  setSpeed(60);
  setMode('cruise');
  emitWarning('front');
});
await page.waitForTimeout(500); // 在闪烁过程中截图
```

**验收：**
1. 左上角和右上角有红色高亮效果（红色边框、红色背景、或红色闪烁）
2. 红色醒目且有紧迫感（不是浅粉、不是暗红）
3. 有预警文字提示（"碰撞"、"前方"、"注意"等关键词）
4. 速度信息仍然可见
5. **这是整个 demo 最重要的画面——必须一眼传达危险感**
6. 与 S1/S2 对比，视觉冲击力明显更强

### S4: ADAS 左后预警（warn, left）

**触发：**
```javascript
await page.evaluate(() => {
  setSpeed(60);
  setMode('cruise');
  emitWarning('left');
});
await page.waitForTimeout(500);
```

**验收：**
1. 左下角有红色高亮效果
2. 右上角和右下角**没有**红色高亮（方向性正确）
3. 预警信息出现在左侧区域

### S5: ADAS 右后预警（warn, right）

**触发：**
```javascript
await page.evaluate(() => {
  setSpeed(60);
  setMode('cruise');
  emitWarning('right');
});
await page.waitForTimeout(500);
```

**验收：**
1. 右下角有红色高亮效果
2. 左侧区域**没有**红色高亮（方向性正确）
3. 预警信息出现在右侧区域

### S6: 来电状态（call）

**触发：**
```javascript
await page.evaluate(() => {
  setSpeed(40);
  setMode('cruise');
  emitEvent({type:'call', data:{name:'张三'}});
});
await page.waitForTimeout(1000);
```

**验收：**
1. 有来电人名称显示（"张三"或类似文字）
2. 有接听/操作提示
3. 来电相关文字带有绿色调
4. 速度信息仍然可见

### S7: 音乐状态（music）

**触发：**
```javascript
await page.evaluate(() => {
  setSpeed(40);
  setMode('cruise');
  emitEvent({type:'music', data:{track:'梦中的额吉', artist:'布仁巴雅尔'}});
});
await page.waitForTimeout(1000);
```

**验收：**
1. 有曲名/歌手信息显示
2. 有播放控制提示（上一首/暂停/下一首等）
3. 音乐相关文字带有紫色调
4. 信息量少，视觉低调

### S8: Mesh 组队（mesh）

**触发：**
```javascript
await page.evaluate(() => {
  setSpeed(40);
  setMode('cruise');
  emitEvent({type:'mesh', data:{team:'周末骑行群', members:3}});
});
await page.waitForTimeout(1000);
```

**验收：**
1. 有队友数量信息
2. 组队相关文字带有青色调
3. 信息布局清晰

### S9: DVR 录制（dvr）

**触发：**
```javascript
await page.evaluate(() => {
  setSpeed(40);
  setMode('cruise');
  emitEvent({type:'dvr'});
});
await page.waitForTimeout(1000);
```

**验收：**
1. 某个角落有小红点或"REC"标识
2. 有录制时长显示
3. 视觉降噪——录制指示器很小，不抢主要信息

### S10: 单绿光波导模式

**触发：**
```javascript
await page.evaluate(() => {
  setSpeed(40);
  setMode('cruise');
  document.body.classList.add('theme-green');
});
await page.waitForTimeout(1000);
```

**验收：**
1. 所有文字和信息变为绿色系（不是白色、不是其他颜色）
2. 背景变为深绿黑色（不是纯黑）
3. 不同区域的绿色有明度差异（不是所有绿色都一样亮）
4. 整体与 S1 全彩模式有明显视觉区别

### S11: 高速精简（S3，120km/h）

**触发：**
```javascript
await page.evaluate(() => {
  document.body.classList.remove('theme-green');
  setMode('cruise');
  setSpeed(120);
});
await page.waitForTimeout(1000);
```

**验收：**
1. 屏幕上信息极少（明显比 S1 少很多）
2. 速度数字突出且很大
3. 右上角、左下角、右下角的信息应隐藏或极度精简
4. 只有速度 + 预警相关内容可见

### S12: 沙盒面板

**触发：**
```javascript
await page.evaluate(() => {
  setSpeed(40);
  setMode('cruise');
  const sb = document.getElementById('sandbox');
  if (sb) sb.style.display = 'flex';
});
await page.waitForTimeout(500);
```

**验收：**
1. 右侧出现一个控制面板
2. 面板有分组标题（至少 3 组，如 ADAS/通信/媒体等）
3. 每组下有可见的按钮
4. 面板的视觉风格与 HUD 主界面有区分（面板是操作工具，不是 HUD）
5. 面板不遮挡屏幕中央区域

### S13: 剧本播放中

**触发：**
```javascript
await page.evaluate(() => {
  const sb = document.getElementById('sandbox');
  if (sb) sb.style.display = 'none';
  playScenario('emergency');
});
await page.waitForTimeout(6000); // 等剧本跑到第 6 秒（刚好在预警中）
```

**验收：**
1. 底部时间轴有进度条（进度 > 0）
2. 时间轴旁有剧本名称文字
3. HUD 显示的内容与 cruise 默认状态不同（说明剧本在驱动变化）

---

## 多模态 LLM 审查

**模型选择：** 优先 gemini_3_1_pro（视觉理解强），降级 gpt_5_4

**调用方式：** CC 通过 model_gateway 或直接 API 调用

**prompt 模板：**
```
你是智能骑行头盔 HUD demo 的视觉审查官。

以下是 HUD 界面在「{scenario_name}」场景下的截图。

【视觉验收标准】
{criteria_text}

请逐条判断：
1. 每条标准是否满足？✅ 满足 / ❌ 不满足
2. 不满足的给出具体原因（描述你在截图中看到了什么 vs 期望看到什么）
3. 整体评价：这个画面能否在 3 秒内让观看者理解当前状态？

输出格式（严格遵守）：
RESULT:
- 1: PASS
- 2: FAIL | 原因描述
- 3: PASS
OVERALL: PASS 或 FAIL | 一句话原因
```

**结果解析：**
CC 解析 `RESULT:` 之后的内容：
- 含 `FAIL` 的行 → 该项不通过，提取原因
- `OVERALL: FAIL` → 整个场景不通过
- 所有场景 OVERALL: PASS → 进入交付

**不通过时的处理：**
CC 收集所有 FAIL 项 → 按模块归类（布局问题归 M1，状态显示问题归 M3，闪烁问题归 M3 等）→ 回到对应模块修改 → 重新拼装 → 重新截图 → 重新审查。最多 5 轮视觉迭代。
