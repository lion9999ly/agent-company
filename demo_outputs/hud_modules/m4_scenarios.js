// M4: 剧本
// 职责：3 条自动剧本 + 时间轴控制

// 剧本定义
const SCENARIOS = {
  1: {
    name: '日常通勤',
    duration: 45000,
    events: [
      { time: 0, action: () => { setMode(MODE.CRUISE); setSpeed(0); } },
      { time: 3000, action: () => setSpeed(40) },
      { time: 8000, action: () => { setMode(MODE.NAV); window._navDistance = '3200'; window._navETA = '8分钟'; } },
      { time: 12000, action: () => setSpeed(65) },
      { time: 18000, action: () => { window._navDistance = '200'; renderAll(); } },
      { time: 22000, action: () => { setSpeed(35); window._navDistance = '50'; } },
      { time: 25000, action: () => { setMode(MODE.CALL); window._callName = '张三'; } },
      { time: 30000, action: () => { setMode(MODE.NAV); } },
      { time: 35000, action: () => { window._navDistance = '0'; renderAll(); } },
      { time: 40000, action: () => { setSpeed(0); setMode(MODE.CRUISE); } }
    ]
  },
  2: {
    name: '紧急场景',
    duration: 40000,
    events: [
      { time: 0, action: () => { setMode(MODE.CRUISE); setSpeed(60); } },
      { time: 5000, action: () => emitWarning('front') },
      { time: 12000, action: () => emitWarning('left') },
      { time: 18000, action: () => setSpeed(80) },
      { time: 22000, action: () => emitWarning('right') },
      { time: 28000, action: () => emitWarning('front') },
      { time: 35000, action: () => { setSpeed(50); setMode(MODE.CRUISE); } }
    ]
  },
  3: {
    name: '组队骑行',
    duration: 50000,
    events: [
      { time: 0, action: () => { setMode(MODE.CRUISE); setSpeed(45); } },
      { time: 5000, action: () => { setMode(MODE.MESH); window._meshCount = 3; window._meshDistance = '120'; } },
      { time: 8000, action: () => { setMode(MODE.DVR); window._dvrTime = '00:00'; } },
      { time: 12000, action: () => setSpeed(70) },
      { time: 18000, action: () => { window._navDistance = '山路入口'; } },
      { time: 26000, action: () => emitWarning('front') },
      { time: 38000, action: () => { setSpeed(40); setMode(MODE.MESH); } },
      { time: 45000, action: () => { setSpeed(0); setMode(MODE.CRUISE); } }
    ]
  }
};

// 播放状态
let currentScenario = null;
let scenarioTimer = null;
let scenarioStartTime = 0;
let isPaused = false;
let eventIndex = 0;

// 播放剧本
function playScenario(num) {
  stopScenario();
  currentScenario = SCENARIOS[num];
  if (!currentScenario) return;

  scenarioStartTime = Date.now();
  eventIndex = 0;
  isPaused = false;

  // 更新标签
  const labelEl = document.getElementById('timeline-label');
  if (labelEl) labelEl.textContent = currentScenario.name;

  // 开始播放
  runScenario();
}

function runScenario() {
  if (!currentScenario || isPaused) return;

  const elapsed = Date.now() - scenarioStartTime;
  const events = currentScenario.events;

  // 执行到时间的 event
  while (eventIndex < events.length && events[eventIndex].time <= elapsed) {
    events[eventIndex].action();
    eventIndex++;
  }

  // 更新进度条
  const progress = Math.min(elapsed / currentScenario.duration * 100, 100);
  const bar = document.getElementById('progress-bar');
  if (bar) bar.style.width = progress + '%';

  // 检查结束
  if (elapsed >= currentScenario.duration) {
    stopScenario();
    return;
  }

  scenarioTimer = setTimeout(runScenario, 100);
}

function pauseScenario() {
  isPaused = !isPaused;
  if (!isPaused) {
    runScenario();
  }
}

function stopScenario() {
  if (scenarioTimer) {
    clearTimeout(scenarioTimer);
    scenarioTimer = null;
  }
  currentScenario = null;
  isPaused = false;

  const bar = document.getElementById('progress-bar');
  if (bar) bar.style.width = '0%';

  const labelEl = document.getElementById('timeline-label');
  if (labelEl) labelEl.textContent = '就绪';
}

// 时间轴点击跳转
function setupTimelineClick() {
  const progress = document.getElementById('timeline-progress');
  if (!progress) return;

  progress.addEventListener('click', (e) => {
    if (!currentScenario) return;

    const rect = progress.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const percent = clickX / rect.width;
    const targetTime = percent * currentScenario.duration;

    // 重置播放位置
    scenarioStartTime = Date.now() - targetTime;
    eventIndex = 0;

    // 重新执行
    runScenario();
  });
}

// 初始化
document.addEventListener('DOMContentLoaded', setupTimelineClick);

// 导出
window.SCENARIOS = SCENARIOS;
window.playScenario = playScenario;
window.pauseScenario = pauseScenario;
window.stopScenario = stopScenario;