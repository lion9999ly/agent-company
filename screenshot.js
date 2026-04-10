/**
 * HUD Demo 截图脚本
 *
 * 用法：
 *   node screenshot.js
 *
 * 截图清单按 visual_criteria.md
 */
const puppeteer = require('puppeteer');
const path = require('path');
const fs = require('fs');

// 项目根目录
const ROOT = path.resolve(__dirname);
const HTML_PATH = path.join(ROOT, 'demo_outputs', 'hud_demo_final.html');
const OUTPUT_DIR = path.join(ROOT, 'demo_outputs', 'screenshots');

// 确保输出目录存在
if (!fs.existsSync(OUTPUT_DIR)) {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
}

// 截图清单
const SCREENSHOTS = [
  { name: 'S1_boot_0.5s', action: async (page) => { /* 刚打开，开机动画中 */ }, delay: 500 },
  { name: 'S1_boot_1.5s', action: async (page) => { }, delay: 1500 },
  { name: 'S2_cruise', action: async (page) => {
    await page.evaluate(() => { window.setMode('cruise'); window.setSpeed(40); });
  }},
  { name: 'S3_nav', action: async (page) => {
    await page.evaluate(() => { window.setMode('nav'); });
  }},
  { name: 'S4_warn_front', action: async (page) => {
    await page.evaluate(() => { window.emitWarning('front'); });
  }},
  { name: 'S5_warn_left', action: async (page) => {
    await page.evaluate(() => { window.setMode('cruise'); });
    await new Promise(r => setTimeout(r, 500));
    await page.evaluate(() => { window.emitWarning('left'); });
  }},
  { name: 'S6_warn_right', action: async (page) => {
    await page.evaluate(() => { window.setMode('cruise'); });
    await new Promise(r => setTimeout(r, 500));
    await page.evaluate(() => { window.emitWarning('right'); });
  }},
  { name: 'S7_call', action: async (page) => {
    await page.evaluate(() => { window.setMode('call'); window._callName = '张三'; window.renderAll(); });
  }},
  { name: 'S8_music', action: async (page) => {
    await page.evaluate(() => { window.setMode('music'); window._musicTrack = '追梦人'; window.renderAll(); });
  }},
  { name: 'S9_mesh', action: async (page) => {
    await page.evaluate(() => { window.setMode('mesh'); window._meshCount = 3; window.renderAll(); });
  }},
  { name: 'S10_dvr', action: async (page) => {
    await page.evaluate(() => { window.setMode('dvr'); window._dvrTime = '02:30'; window.renderAll(); });
  }},
  { name: 'S11_theme_green', action: async (page) => {
    await page.evaluate(() => {
      document.body.classList.add('theme-green');
      window.setMode('cruise');
      window.setSpeed(40);
    });
  }},
  { name: 'S12_speed_120', action: async (page) => {
    await page.evaluate(() => {
      document.body.classList.remove('theme-green');
      window.setMode('cruise');
      window.setSpeed(120);
    });
  }},
  { name: 'S13_sandbox', action: async (page) => {
    await page.evaluate(() => {
      window.setMode('cruise');
      window.setSpeed(40);
      document.getElementById('sandbox').classList.add('open');
    });
  }},
  { name: 'S14_scenario_playing', action: async (page) => {
    await page.evaluate(() => {
      document.getElementById('sandbox').classList.remove('open');
      window.playScenario(1);
    });
    await new Promise(r => setTimeout(r, 2000));
  }},
];

async function main() {
  console.log('启动浏览器...');
  const browser = await puppeteer.launch({
    headless: 'new',
    executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });

  const page = await browser.newPage();
  await page.setViewport({ width: 1920, height: 1080 });

  console.log(`打开 ${HTML_PATH}`);
  await page.goto(`file://${HTML_PATH}`, { waitUntil: 'networkidle0' });

  // 等待开机动画完成
  console.log('等待开机动画...');
  await new Promise(r => setTimeout(r, 3500));

  // 截图
  for (const shot of SCREENSHOTS) {
    console.log(`截图: ${shot.name}`);

    if (shot.action) {
      await shot.action(page);
      await new Promise(r => setTimeout(r, shot.delay || 500));
    }

    const outputPath = path.join(OUTPUT_DIR, `${shot.name}.png`);
    await page.screenshot({ path: outputPath, fullPage: false });
    console.log(`  保存: ${outputPath}`);
  }

  await browser.close();
  console.log('\n截图完成！');
  console.log(`共 ${SCREENSHOTS.length} 张，保存在 ${OUTPUT_DIR}`);
}

main().catch(console.error);