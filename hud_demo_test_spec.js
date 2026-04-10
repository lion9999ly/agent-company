/**
 * HUD Demo 测试脚本
 * 
 * 用法：
 *   npm install jsdom（首次）
 *   node test_spec.js path/to/hud_demo.html
 * 
 * 两级测试：
 *   --module m2  只跑 M2 模块级测试（传入单个 JS 文件）
 *   无参数       跑集成测试（传入完整 HTML）
 */

const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

// ============================================================
// 测试框架（极简，不依赖 jest/mocha）
// ============================================================

let passed = 0;
let failed = 0;
let errors = [];

function assert(condition, name) {
  if (condition) {
    passed++;
    console.log(`  ✅ ${name}`);
  } else {
    failed++;
    errors.push(name);
    console.log(`  ❌ ${name}`);
  }
}

function assertExists(value, name) {
  assert(value !== null && value !== undefined, name);
}

function assertEqual(actual, expected, name) {
  assert(actual === expected, `${name}: expected=${expected}, actual=${actual}`);
}

function assertGreater(actual, threshold, name) {
  assert(actual > threshold, `${name}: ${actual} should be > ${threshold}`);
}

function section(name) {
  console.log(`\n--- ${name} ---`);
}

function report() {
  console.log(`\n${'='.repeat(50)}`);
  console.log(`结果: ${passed} passed, ${failed} failed`);
  if (errors.length > 0) {
    console.log(`\n失败项:`);
    errors.forEach(e => console.log(`  - ${e}`));
  }
  console.log(`${'='.repeat(50)}`);
  process.exit(failed > 0 ? 1 : 0);
}

// ============================================================
// 加载 HTML
// ============================================================

const htmlPath = process.argv[2];
if (!htmlPath) {
  console.error('用法: node test_spec.js <html_file>');
  process.exit(1);
}

const htmlContent = fs.readFileSync(htmlPath, 'utf-8');
const dom = new JSDOM(htmlContent, {
  runScripts: 'dangerously',
  resources: 'usable',
  pretendToBeVisual: true,
});
const { window } = dom;
const { document } = window;

// 等 JS 执行完
setTimeout(() => {
  runAllTests();
  report();
}, 1000);

// ============================================================
// 集成测试
// ============================================================

function runAllTests() {

  // ----------------------------------------------------------
  section('T1: HTML 基础结构');
  // ----------------------------------------------------------

  assert(htmlContent.includes('<!DOCTYPE html'), 'DOCTYPE 存在');
  assert(htmlContent.includes('<html'), 'html 标签存在');
  assert(htmlContent.includes('</html>'), 'html 闭合');
  assert(htmlContent.includes('<head>'), 'head 标签存在');
  assert(htmlContent.includes('</head>'), 'head 闭合');
  assert(htmlContent.includes('<body'), 'body 标签存在');
  assert(htmlContent.includes('</body>'), 'body 闭合');

  // ----------------------------------------------------------
  section('T2: DOM 结构（契约 ID）');
  // ----------------------------------------------------------

  assertExists(document.getElementById('hud-root'), '#hud-root 存在');
  assertExists(document.getElementById('zone-lt'), '#zone-lt 存在');
  assertExists(document.getElementById('zone-rt'), '#zone-rt 存在');
  assertExists(document.getElementById('zone-lb'), '#zone-lb 存在');
  assertExists(document.getElementById('zone-rb'), '#zone-rb 存在');
  assertExists(document.getElementById('center-clear'), '#center-clear 存在');
  assertExists(document.getElementById('bottom-bar'), '#bottom-bar 存在');
  assertExists(document.getElementById('timeline'), '#timeline 存在');
  assertExists(document.getElementById('sandbox'), '#sandbox 存在');

  // 中央留空检查
  const centerClear = document.getElementById('center-clear');
  if (centerClear) {
    assertEqual(centerClear.children.length, 0, '中央区域无子元素');
  }

  // ----------------------------------------------------------
  section('T3: CSS 变量');
  // ----------------------------------------------------------

  const requiredVars = [
    '--bg', '--c-speed', '--c-nav', '--c-warn', '--c-mesh',
    '--c-music', '--c-call', '--c-dvr', '--c-text', '--c-muted',
  ];
  requiredVars.forEach(v => {
    assert(htmlContent.includes(v), `CSS 变量 ${v} 定义存在`);
  });

  // 单绿模式
  assert(htmlContent.includes('.theme-green') || htmlContent.includes('theme-green'),
    '单绿模式 .theme-green 定义存在');

  // ----------------------------------------------------------
  section('T4: JS 全局 API 存在性');
  // ----------------------------------------------------------

  assertExists(window.MODE, 'MODE 枚举存在');
  assertExists(window.PRIORITY, 'PRIORITY 定义存在');
  assertExists(window.setMode, 'setMode 函数存在');
  assertExists(window.getMode, 'getMode 函数存在');
  assertExists(window.getPriority, 'getPriority 函数存在');
  assertExists(window.emitEvent, 'emitEvent 函数存在');
  assertExists(window.emitWarning, 'emitWarning 函数存在');
  assertExists(window.setSpeed, 'setSpeed 函数存在');
  assertExists(window.getSpeedLevel, 'getSpeedLevel 函数存在');
  assertExists(window.renderAll, 'renderAll 函数存在');

  // ----------------------------------------------------------
  section('T5: 状态枚举完整性');
  // ----------------------------------------------------------

  if (window.MODE) {
    const expectedModes = ['cruise', 'nav', 'call', 'music', 'mesh', 'warn', 'dvr'];
    expectedModes.forEach(m => {
      assert(Object.values(window.MODE).includes(m), `MODE 包含 ${m}`);
    });
    assertEqual(Object.keys(window.MODE).length, 7, 'MODE 恰好 7 个状态');
  }

  // ----------------------------------------------------------
  section('T6: 优先级正确性');
  // ----------------------------------------------------------

  if (window.PRIORITY) {
    assert(window.PRIORITY.warn > window.PRIORITY.call, 'warn > call');
    assert(window.PRIORITY.call > window.PRIORITY.nav, 'call > nav');
    assert(window.PRIORITY.nav > window.PRIORITY.mesh, 'nav > mesh');
    assert(window.PRIORITY.mesh > window.PRIORITY.music, 'mesh > music');
    assert(window.PRIORITY.music > window.PRIORITY.dvr, 'music > dvr');
    assert(window.PRIORITY.dvr > window.PRIORITY.cruise, 'dvr > cruise');
  }

  // ----------------------------------------------------------
  section('T7: 状态机行为');
  // ----------------------------------------------------------

  if (window.setMode && window.getMode) {
    // 默认状态
    window.setMode('cruise');
    assertEqual(window.getMode(), 'cruise', '初始状态 cruise');

    // 正常切换
    window.setMode('nav');
    assertEqual(window.getMode(), 'nav', 'cruise → nav 切换成功');

    // 高优先级抢占
    window.setMode('warn');
    assertEqual(window.getMode(), 'warn', 'nav → warn 抢占成功');

    // 低优先级被拒绝（warn 时不能切到 music）
    window.setMode('music');
    assertEqual(window.getMode(), 'warn', 'warn 状态下 music 被拒绝');

    // 重置
    window.setMode('cruise');
  }

  // ----------------------------------------------------------
  section('T8: 速度分级');
  // ----------------------------------------------------------

  if (window.setSpeed && window.getSpeedLevel) {
    window.setSpeed(20);
    assertEqual(window.getSpeedLevel(), 'S0', '20km/h → S0');

    window.setSpeed(45);
    assertEqual(window.getSpeedLevel(), 'S1', '45km/h → S1');

    window.setSpeed(80);
    assertEqual(window.getSpeedLevel(), 'S2', '80km/h → S2');

    window.setSpeed(120);
    assertEqual(window.getSpeedLevel(), 'S3', '120km/h → S3');

    window.setSpeed(0);
  }

  // ----------------------------------------------------------
  section('T9: 渲染行为（DOM 实际更新）');
  // ----------------------------------------------------------

  if (window.setMode && window.renderAll) {
    // 切到 cruise，检查 LT 区域有速度信息
    window.setMode('cruise');
    const lt = document.getElementById('zone-lt');
    if (lt) {
      assertGreater(lt.textContent.trim().length, 0, 'cruise 状态 LT 区域有内容');
    }

    // 切到 warn，检查有预警相关内容
    window.setMode('warn');
    const rt = document.getElementById('zone-rt');
    if (rt) {
      assertGreater(rt.textContent.trim().length, 0, 'warn 状态 RT 区域有内容');
    }

    // 切到 nav，检查有导航相关内容
    window.setMode('nav');
    const rb = document.getElementById('zone-rb');
    if (rb) {
      assertGreater(rb.textContent.trim().length, 0, 'nav 状态 RB 区域有内容');
    }

    window.setMode('cruise');
  }

  // ----------------------------------------------------------
  section('T10: 函数体非空检查（防 console.log 空壳）');
  // ----------------------------------------------------------

  // 检查关键函数的实现不是只有 console.log
  const scriptContent = htmlContent.match(/<script[^>]*>([\s\S]*?)<\/script>/gi);
  if (scriptContent) {
    const allJS = scriptContent.map(s => s.replace(/<\/?script[^>]*>/gi, '')).join('\n');

    // setMode 函数体应该包含实际逻辑
    const setModeMatch = allJS.match(/function\s+setMode\s*\([^)]*\)\s*\{([\s\S]*?)\n\}/);
    if (setModeMatch) {
      const body = setModeMatch[1];
      assertGreater(body.split('\n').length, 2, 'setMode 函数体超过 2 行');
      assert(!body.match(/^\s*console\.log/m) || body.split('\n').length > 3,
        'setMode 不只是 console.log');
    }

    // renderAll 函数体
    const renderMatch = allJS.match(/function\s+renderAll\s*\([^)]*\)\s*\{([\s\S]*?)\n\}/);
    if (renderMatch) {
      const body = renderMatch[1];
      assertGreater(body.split('\n').length, 2, 'renderAll 函数体超过 2 行');
      assert(body.includes('getElementById') || body.includes('querySelector') || body.includes('textContent') || body.includes('innerHTML'),
        'renderAll 包含 DOM 操作');
    }

    // emitWarning 函数体
    const warnMatch = allJS.match(/function\s+emitWarning\s*\([^)]*\)\s*\{([\s\S]*?)\n\}/);
    if (warnMatch) {
      const body = warnMatch[1];
      assertGreater(body.split('\n').length, 2, 'emitWarning 函数体超过 2 行');
      assert(body.includes('classList') || body.includes('className') || body.includes('style'),
        'emitWarning 包含样式操作');
    }
  }

  // ----------------------------------------------------------
  section('T11: 剧本存在性');
  // ----------------------------------------------------------

  assert(htmlContent.includes('日常通勤') || htmlContent.includes('commute') || htmlContent.includes('scenario1') || htmlContent.includes('SCENARIO_1'),
    '剧本 1（日常通勤）存在');
  assert(htmlContent.includes('紧急场景') || htmlContent.includes('emergency') || htmlContent.includes('scenario2') || htmlContent.includes('SCENARIO_2'),
    '剧本 2（紧急场景）存在');
  assert(htmlContent.includes('组队骑行') || htmlContent.includes('group') || htmlContent.includes('scenario3') || htmlContent.includes('SCENARIO_3'),
    '剧本 3（组队骑行）存在');

  // ----------------------------------------------------------
  section('T12: 沙盒面板');
  // ----------------------------------------------------------

  const sandbox = document.getElementById('sandbox');
  if (sandbox) {
    // 沙盒面板应该有多个按钮
    const buttons = sandbox.querySelectorAll('button, [onclick], [data-event]');
    assertGreater(buttons.length, 5, '沙盒面板有 >5 个交互元素');

    // 应该有分组
    const groups = sandbox.querySelectorAll('[class*="group"], [data-group], h3, h4, .section-title');
    assertGreater(groups.length, 2, '沙盒面板有 >2 个分组');
  }

  // ----------------------------------------------------------
  section('T13: 键盘快捷键');
  // ----------------------------------------------------------

  // 检查 addEventListener('keydown') 存在
  assert(htmlContent.includes('keydown'), '键盘事件监听存在');

  // 检查关键按键处理
  const keyMappings = ['Space', 'Escape', "'t'", "'T'", "'s'", "'S'", "'w'", "'W'"];
  let keyCount = 0;
  keyMappings.forEach(k => {
    if (htmlContent.includes(k)) keyCount++;
  });
  assertGreater(keyCount, 4, `至少 5 个快捷键被处理（找到 ${keyCount} 个）`);

  // ----------------------------------------------------------
  section('T14: 开机自检');
  // ----------------------------------------------------------

  assertExists(document.getElementById('boot-overlay'), '#boot-overlay 存在');
  assert(htmlContent.includes('bootSequence') || htmlContent.includes('boot_sequence') || htmlContent.includes('bootAnimation'),
    '开机自检函数存在');

  // ----------------------------------------------------------
  section('T15: 代码质量');
  // ----------------------------------------------------------

  // 文件大小合理范围
  const sizeKB = htmlContent.length / 1024;
  assert(sizeKB > 5, `文件大小 > 5KB（实际 ${sizeKB.toFixed(1)}KB）`);
  assert(sizeKB < 200, `文件大小 < 200KB（实际 ${sizeKB.toFixed(1)}KB）`);

  // 行数合理范围
  const lineCount = htmlContent.split('\n').length;
  assert(lineCount > 100, `行数 > 100（实际 ${lineCount}）`);
  assert(lineCount < 2000, `行数 < 2000（实际 ${lineCount}）`);

  // 无外部依赖（字体除外）
  assert(!htmlContent.includes('cdn.jsdelivr.net'), '无 jsdelivr CDN');
  assert(!htmlContent.includes('unpkg.com'), '无 unpkg CDN');
  assert(!htmlContent.includes('cdnjs.cloudflare.com'), '无 cdnjs CDN');
}
