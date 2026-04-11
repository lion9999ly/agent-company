/**
 * HUD Demo 测试脚本 v2
 *
 * 用法：node test_spec.js path/to/hud_demo.html
 * 依赖：npm install jsdom
 *
 * 修复 v1 问题：
 * - 函数匹配兼容 function 声明和箭头函数
 * - 超时改为 5 秒（开机动画 3 秒）
 * - 新增弹栈恢复测试
 * - 新增主题切换测试
 * - 内容有意义性检查（不只检查 length > 0）
 */

const fs = require('fs');
const { JSDOM } = require('jsdom');

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
  assert(actual === expected, `${name}: expected="${expected}", actual="${actual}"`);
}

function assertGreater(actual, threshold, name) {
  assert(actual > threshold, `${name}: ${actual} should be > ${threshold}`);
}

function assertIncludes(str, substr, name) {
  assert(typeof str === 'string' && str.includes(substr), `${name}: should include "${substr}"`);
}

function section(name) {
  console.log(`\n--- ${name} ---`);
}

function report() {
  console.log(`\n${'='.repeat(50)}`);
  console.log(`结果: ${passed} passed, ${failed} failed, 总计 ${passed + failed}`);
  if (errors.length > 0) {
    console.log(`\n失败项:`);
    errors.forEach(e => console.log(`  - ${e}`));
  }
  console.log(`${'='.repeat(50)}`);
  process.exit(failed > 0 ? 1 : 0);
}

// 加载 HTML
const htmlPath = process.argv[2];
if (!htmlPath) {
  console.error('用法: node test_spec.js <html_file>');
  process.exit(1);
}

if (!fs.existsSync(htmlPath)) {
  console.error(`文件不存在: ${htmlPath}`);
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

// 等 JS 执行完（开机动画 3 秒 + 缓冲 2 秒）
setTimeout(() => {
  try {
    runAllTests();
  } catch (e) {
    console.error(`\n测试执行出错: ${e.message}`);
    console.error(e.stack);
    failed++;
    errors.push(`测试执行异常: ${e.message}`);
  }
  report();
}, 5000);

function runAllTests() {

  // ============================================================
  section('T1: HTML 基础结构');
  // ============================================================

  assert(htmlContent.includes('<!DOCTYPE html'), 'DOCTYPE 存在');
  assert(htmlContent.includes('<html'), 'html 标签');
  assert(htmlContent.includes('</html>'), 'html 闭合');
  assert(htmlContent.includes('<head>') || htmlContent.includes('<head '), 'head 标签');
  assert(htmlContent.includes('</head>'), 'head 闭合');
  assert(htmlContent.includes('<body') , 'body 标签');
  assert(htmlContent.includes('</body>'), 'body 闭合');

  // script 标签配对
  const scriptOpens = (htmlContent.match(/<script/g) || []).length;
  const scriptCloses = (htmlContent.match(/<\/script>/g) || []).length;
  assertEqual(scriptOpens, scriptCloses, `script 标签配对 (${scriptOpens} 开 ${scriptCloses} 闭)`);

  // ============================================================
  section('T2: DOM 结构（契约 ID）');
  // ============================================================

  const requiredIds = [
    'hud-root', 'zone-lt', 'zone-rt', 'zone-lb', 'zone-rb',
    'center-clear', 'bottom-bar', 'timeline', 'sandbox', 'boot-overlay'
  ];
  requiredIds.forEach(id => {
    assertExists(document.getElementById(id), `#${id} 存在`);
  });

  // 中央留空
  const cc = document.getElementById('center-clear');
  if (cc) {
    assertEqual(cc.children.length, 0, '中央区域无子元素');
  }

  // zone 内部结构
  ['zone-lt', 'zone-rt', 'zone-lb', 'zone-rb'].forEach(id => {
    const zone = document.getElementById(id);
    if (zone) {
      const hasLabel = zone.querySelector('.zone-label');
      const hasContent = zone.querySelector('.zone-content');
      assert(hasLabel || hasContent, `#${id} 有 .zone-label 或 .zone-content`);
    }
  });

  // ============================================================
  section('T3: CSS 变量');
  // ============================================================

  const requiredVars = [
    '--bg', '--c-speed', '--c-nav', '--c-warn', '--c-mesh',
    '--c-music', '--c-call', '--c-dvr', '--c-text', '--c-muted',
    '--s-font-xl', '--s-font-lg',
  ];
  requiredVars.forEach(v => {
    assert(htmlContent.includes(v), `CSS 变量 ${v} 存在`);
  });

  assert(htmlContent.includes('.theme-green'), '.theme-green 定义存在');

  // 单绿模式变量覆盖（不只是 class 存在，要有变量重定义）
  const greenSection = htmlContent.match(/\.theme-green\s*\{([^}]+)\}/s);
  if (greenSection) {
    assert(greenSection[1].includes('--c-speed'), '.theme-green 覆盖了 --c-speed');
    assert(greenSection[1].includes('--c-warn'), '.theme-green 覆盖了 --c-warn');
  } else {
    assert(false, '.theme-green 块存在且包含变量覆盖');
  }

  // ============================================================
  section('T4: JS 全局 API');
  // ============================================================

  const requiredFns = [
    'MODE', 'PRIORITY', 'setMode', 'getMode', 'getPriority',
    'popMode', 'emitEvent', 'emitWarning', 'setSpeed',
    'getSpeedLevel', 'renderAll',
  ];
  requiredFns.forEach(fn => {
    assertExists(window[fn], `window.${fn} 存在`);
  });

  // ============================================================
  section('T5: 状态枚举完整性');
  // ============================================================

  if (window.MODE) {
    const expected = ['cruise', 'nav', 'call', 'music', 'mesh', 'warn', 'dvr'];
    const actual = Object.values(window.MODE);
    expected.forEach(m => {
      assert(actual.includes(m), `MODE 包含 '${m}'`);
    });
    assertEqual(actual.length, 7, 'MODE 恰好 7 个');
  }

  // ============================================================
  section('T6: 优先级正确性');
  // ============================================================

  if (window.PRIORITY) {
    assert(window.PRIORITY.warn > window.PRIORITY.call, 'warn > call');
    assert(window.PRIORITY.call > window.PRIORITY.nav, 'call > nav');
    assert(window.PRIORITY.nav > window.PRIORITY.mesh, 'nav > mesh');
    assert(window.PRIORITY.mesh > window.PRIORITY.music, 'mesh > music');
    assert(window.PRIORITY.music > window.PRIORITY.dvr, 'music > dvr');
    assert(window.PRIORITY.dvr > window.PRIORITY.cruise, 'dvr > cruise');
  }

  // ============================================================
  section('T7: 状态机行为');
  // ============================================================

  if (window.setMode && window.getMode && window.popMode) {
    // 7a: 基本切换
    window.setMode('cruise');
    assertEqual(window.getMode(), 'cruise', '初始 cruise');

    window.setMode('nav');
    assertEqual(window.getMode(), 'nav', 'cruise→nav');

    // 7b: 高优先级抢占
    window.setMode('warn');
    assertEqual(window.getMode(), 'warn', 'nav→warn 抢占');

    // 7c: 低优先级被拒
    const result = window.setMode('music');
    assertEqual(window.getMode(), 'warn', 'warn 下 music 被拒');
    assertEqual(result, false, 'setMode 返回 false');

    // 7d: 弹栈恢复
    window.popMode();
    assertEqual(window.getMode(), 'nav', 'popMode 恢复到 nav');

    window.popMode();
    assertEqual(window.getMode(), 'cruise', '再次 popMode 恢复到 cruise');

    // 7e: 栈空时 popMode 恢复到 cruise
    window.popMode();
    assertEqual(window.getMode(), 'cruise', '栈空 popMode 保持 cruise');

    // 7f: 无效 mode
    const invalid = window.setMode('xxx');
    assertEqual(window.getMode(), 'cruise', '无效 mode 不改变状态');
    assertEqual(invalid, false, '无效 mode 返回 false');

    // 7g: cruise 总是成功（重置）
    window.setMode('warn');
    window.setMode('cruise');
    assertEqual(window.getMode(), 'cruise', 'setMode cruise 总是成功');
  }

  // ============================================================
  section('T8: 速度分级');
  // ============================================================

  if (window.setSpeed && window.getSpeedLevel) {
    window.setSpeed(0);
    assertEqual(window.getSpeedLevel(), 'S0', '0→S0');

    window.setSpeed(20);
    assertEqual(window.getSpeedLevel(), 'S0', '20→S0');

    window.setSpeed(30);
    assertEqual(window.getSpeedLevel(), 'S0', '30→S0（边界）');

    window.setSpeed(31);
    assertEqual(window.getSpeedLevel(), 'S1', '31→S1');

    window.setSpeed(60);
    assertEqual(window.getSpeedLevel(), 'S1', '60→S1（边界）');

    window.setSpeed(61);
    assertEqual(window.getSpeedLevel(), 'S2', '61→S2');

    window.setSpeed(100);
    assertEqual(window.getSpeedLevel(), 'S2', '100→S2（边界）');

    window.setSpeed(101);
    assertEqual(window.getSpeedLevel(), 'S3', '101→S3');

    // 边界值
    window.setSpeed(-10);
    assertEqual(window.getSpeedLevel(), 'S0', '负数→S0');

    window.setSpeed(999);
    assertEqual(window.getSpeedLevel(), 'S3', '超大值→S3');

    window.setSpeed(0);
  }

  // ============================================================
  section('T9: 渲染行为（DOM 更新）');
  // ============================================================

  if (window.setMode && window.renderAll) {
    window.setSpeed(40);

    // cruise 状态
    window.setMode('cruise');
    const lt = document.getElementById('zone-lt');
    const ltContent = lt ? (lt.querySelector('.zone-content') || lt) : null;
    if (ltContent) {
      const text = ltContent.textContent.trim();
      assertGreater(text.length, 0, 'cruise LT 有内容');
      // 内容有意义性：应包含数字（速度）或中文
      assert(/\d/.test(text) || /[\u4e00-\u9fff]/.test(text), 'cruise LT 内容有意义（含数字或中文）');
    }

    // warn 状态
    window.setMode('warn');
    const rt = document.getElementById('zone-rt');
    const rtContent = rt ? (rt.querySelector('.zone-content') || rt) : null;
    if (rtContent) {
      const text = rtContent.textContent.trim();
      assertGreater(text.length, 0, 'warn RT 有内容');
      assert(/[\u4e00-\u9fff]/.test(text) || /warn|alert|danger/i.test(text),
        'warn RT 内容有预警含义');
    }

    // nav 状态
    window.setMode('cruise');
    window.setMode('nav');
    const rb = document.getElementById('zone-rb');
    const rbContent = rb ? (rb.querySelector('.zone-content') || rb) : null;
    if (rbContent) {
      const text = rbContent.textContent.trim();
      assertGreater(text.length, 0, 'nav RB 有内容');
    }

    // S3 下信息隐藏
    window.setMode('cruise');
    window.setSpeed(120);
    const rtElement = document.getElementById('zone-rt');
    if (rtElement) {
      const isHidden = rtElement.style.display === 'none' ||
                       window.getComputedStyle(rtElement).display === 'none';
      assert(isHidden, 'S3 下 zone-rt 隐藏');
    }

    window.setSpeed(0);
    window.setMode('cruise');
  }

  // ============================================================
  section('T10: 函数体非空（防 console.log 空壳）');
  // ============================================================

  const allScripts = htmlContent.match(/<script[^>]*>([\s\S]*?)<\/script>/gi) || [];
  const allJS = allScripts.map(s => s.replace(/<\/?script[^>]*>/gi, '')).join('\n');

  // 兼容 function 声明和箭头函数
  function findFnBody(name) {
    // function name(...) { ... }
    const fnDecl = new RegExp(`function\\s+${name}\\s*\\([^)]*\\)\\s*\\{([\\s\\S]*?)\\n\\}`, 'm');
    let match = allJS.match(fnDecl);
    if (match) return match[1];
    // const name = (...) => { ... }
    const arrow = new RegExp(`(?:const|let|var)\\s+${name}\\s*=\\s*(?:\\([^)]*\\)|[^=]+)\\s*=>\\s*\\{([\\s\\S]*?)\\n\\}`, 'm');
    match = allJS.match(arrow);
    if (match) return match[1];
    // window.name = function(...) { ... }
    const winFn = new RegExp(`window\\.${name}\\s*=\\s*function\\s*\\([^)]*\\)\\s*\\{([\\s\\S]*?)\\n\\}`, 'm');
    match = allJS.match(winFn);
    if (match) return match[1];
    return null;
  }

  const criticalFns = ['setMode', 'renderAll', 'emitWarning', 'emitEvent', 'setSpeed'];
  criticalFns.forEach(fn => {
    const body = findFnBody(fn);
    if (body !== null) {
      const lines = body.split('\n').filter(l => l.trim().length > 0);
      assertGreater(lines.length, 2, `${fn} 函数体 > 2 行（实际 ${lines.length} 行）`);

      // 不能只有 console.log
      const nonLogLines = lines.filter(l => !l.trim().startsWith('console.') && !l.trim().startsWith('//'));
      assertGreater(nonLogLines.length, 1, `${fn} 有实际逻辑（非 console/注释行 ${nonLogLines.length} 行）`);
    } else {
      assert(false, `${fn} 函数体可被解析`);
    }
  });

  // renderAll 必须包含 DOM 操作
  const renderBody = findFnBody('renderAll');
  if (renderBody) {
    assert(
      renderBody.includes('getElementById') || renderBody.includes('querySelector') ||
      renderBody.includes('textContent') || renderBody.includes('innerHTML') ||
      renderBody.includes('.innerText'),
      'renderAll 包含 DOM 操作'
    );
  }

  // ============================================================
  section('T11: 剧本');
  // ============================================================

  assertExists(window.SCENARIOS || window.playScenario, '剧本系统存在');

  if (window.SCENARIOS) {
    assert('commute' in window.SCENARIOS || 'emergency' in window.SCENARIOS,
      'SCENARIOS 有命名剧本');
    const keys = Object.keys(window.SCENARIOS);
    assertGreater(keys.length, 2, `至少 3 个剧本（实际 ${keys.length}）`);

    // 每个剧本有事件
    keys.forEach(k => {
      const s = window.SCENARIOS[k];
      assert(s.events && s.events.length > 3, `剧本 ${k} 有 >3 个事件`);
      assert(s.duration && s.duration > 10, `剧本 ${k} 时长 >10s`);
    });
  }

  assertExists(window.playScenario, 'playScenario 函数存在');
  assertExists(window.pauseScenario, 'pauseScenario 函数存在');

  // ============================================================
  section('T12: 沙盒面板');
  // ============================================================

  const sandbox = document.getElementById('sandbox');
  if (sandbox) {
    const buttons = sandbox.querySelectorAll('button, [data-event]');
    assertGreater(buttons.length, 10, `沙盒有 >10 个按钮（实际 ${buttons.length}）`);

    const groups = sandbox.querySelectorAll('section, [data-group], .sandbox-group');
    assertGreater(groups.length, 3, `沙盒有 >3 个分组（实际 ${groups.length}）`);

    // 检查 ADAS 分组存在
    const adasGroup = sandbox.querySelector('[data-group="adas"]') ||
                      sandbox.querySelector('section:first-of-type');
    assertExists(adasGroup, '沙盒有 ADAS 分组');
  }

  // ============================================================
  section('T13: 键盘快捷键');
  // ============================================================

  assert(allJS.includes('keydown'), 'keydown 监听存在');

  // 检查按键处理覆盖度
  const keyChecks = [
    { key: 'Space', desc: '空格' },
    { key: 'Escape', desc: 'Esc' },
  ];
  const keyStrings = ["'t'", "'T'", "'s'", "'S'", "'w'", "'W'", "'a'", "'A'", "'d'", "'D'",
                      "'1'", "'2'", "'3'", '"t"', '"T"', '"s"', '"S"', '"w"', '"W"',
                      'key === "t"', 'key === "T"', "key === 't'", "key === 'T'"];

  let keyHits = 0;
  // Space/Escape
  if (allJS.includes('Space') || allJS.includes(' ')) keyHits++;
  if (allJS.includes('Escape')) keyHits++;
  // 字母键
  ['t', 's', 'w', 'a', 'd', '1', '2', '3'].forEach(k => {
    if (allJS.includes(`'${k}'`) || allJS.includes(`"${k}"`) ||
        allJS.includes(`'${k.toUpperCase()}'`) || allJS.includes(`"${k.toUpperCase()}"`)) {
      keyHits++;
    }
  });
  assertGreater(keyHits, 6, `至少 7 个快捷键被处理（找到 ${keyHits}）`);

  // ============================================================
  section('T14: 开机自检');
  // ============================================================

  assertExists(document.getElementById('boot-overlay'), '#boot-overlay 存在');
  assert(allJS.includes('bootSequence') || allJS.includes('boot_sequence'),
    '开机自检函数存在');

  // ============================================================
  section('T15: 主题切换');
  // ============================================================

  assert(allJS.includes('theme-green'), 'JS 中有 theme-green 引用');
  assert(allJS.includes('classList.toggle') || allJS.includes('classList.add'),
    '主题切换使用 classList 操作');

  // ============================================================
  section('T16: 代码质量');
  // ============================================================

  const sizeKB = htmlContent.length / 1024;
  assert(sizeKB > 8, `文件 > 8KB（实际 ${sizeKB.toFixed(1)}KB）`);
  assert(sizeKB < 200, `文件 < 200KB（实际 ${sizeKB.toFixed(1)}KB）`);

  const lineCount = htmlContent.split('\n').length;
  assert(lineCount > 150, `行数 > 150（实际 ${lineCount}）`);
  assert(lineCount < 2000, `行数 < 2000（实际 ${lineCount}）`);

  // 无外部依赖
  assert(!htmlContent.includes('cdn.jsdelivr.net'), '无 jsdelivr');
  assert(!htmlContent.includes('unpkg.com'), '无 unpkg');
  assert(!htmlContent.includes('cdnjs.cloudflare.com'), '无 cdnjs');

  // Style Guide 遵守：无 var 声明（CSS 变量的 var() 除外）
  const jsOnly = allJS;
  const varDeclarations = (jsOnly.match(/\bvar\s+\w/g) || []).length;
  assert(varDeclarations === 0, `JS 无 var 声明（发现 ${varDeclarations} 处）`);
}
