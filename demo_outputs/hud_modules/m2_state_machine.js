// M2: 状态机
// 职责：7 状态定义、优先级栈、状态切换逻辑、速度分级

// 状态枚举
const MODE = {
  CRUISE: 'cruise',
  NAV: 'nav',
  CALL: 'call',
  MUSIC: 'music',
  MESH: 'mesh',
  WARN: 'warn',
  DVR: 'dvr'
};

// 优先级（数字越大越高）
const PRIORITY = {
  cruise: 0,
  dvr: 1,
  music: 2,
  mesh: 3,
  nav: 4,
  call: 5,
  warn: 6
};

// 全局状态
let currentMode = MODE.CRUISE;
let currentSpeed = 0;
let speedLevel = 'S0';
let modeStack = []; // 优先级栈

// 状态控制
function setMode(mode) {
  const newPriority = PRIORITY[mode];
  const currentPriority = PRIORITY[currentMode];

  // warn 必须立即切换，无视当前状态
  if (mode === MODE.WARN) {
    if (currentMode !== MODE.WARN) {
      modeStack.push(currentMode);
    }
    currentMode = mode;
    renderAll();
    return;
  }

  // 低优先级无法抢占高优先级
  if (newPriority < currentPriority) {
    console.log(`[HUD] ${mode} 优先级不足，当前 ${currentMode}`);
    return;
  }

  // 正常切换
  currentMode = mode;
  renderAll();
}

function getMode() {
  return currentMode;
}

function getPriority(mode) {
  return PRIORITY[mode] || 0;
}

function pushMode(mode) {
  modeStack.push(currentMode);
  currentMode = mode;
  renderAll();
}

function popMode() {
  if (modeStack.length > 0) {
    currentMode = modeStack.pop();
    renderAll();
  }
}

// 事件触发
function emitEvent(event) {
  if (!event || !event.type) return;

  switch (event.type) {
    case 'warning':
      if (event.direction) {
        emitWarning(event.direction);
      }
      break;
    case 'speed':
      if (typeof event.data === 'number') {
        setSpeed(event.data);
      }
      break;
    case 'call':
      setMode(MODE.CALL);
      break;
    case 'nav':
      setMode(MODE.NAV);
      break;
    case 'music':
      setMode(MODE.MUSIC);
      break;
    case 'mesh':
      setMode(MODE.MESH);
      break;
    case 'dvr':
      setMode(MODE.DVR);
      break;
  }
}

function emitWarning(direction) {
  // 先进入 warn 状态
  setMode(MODE.WARN);

  // 根据方向添加闪烁
  const zones = {
    front: ['zone-lt', 'zone-rt'],
    left: ['zone-lb'],
    right: ['zone-rb']
  };

  const targetZones = zones[direction] || [];
  targetZones.forEach(id => {
    const el = document.getElementById(id);
    if (el) {
      el.classList.add('warn-flash');
      setTimeout(() => el.classList.remove('warn-flash'), 3000);
    }
  });

  // 更新预警内容
  const warnMessages = {
    front: { type: '前方碰撞', distance: '30m' },
    left: { type: '左后盲区', distance: '车辆接近' },
    right: { type: '开门预警', distance: '右侧有车' }
  };

  const msg = warnMessages[direction] || { type: '未知预警', distance: '' };
  window._warnData = msg;
  renderAll();

  // 3秒后恢复
  setTimeout(() => {
    if (currentMode === MODE.WARN) {
      popMode();
      window._warnData = null;
    }
  }, 3000);
}

// 速度分级
function setSpeed(kmh) {
  currentSpeed = kmh;

  if (kmh <= 30) {
    speedLevel = 'S0';
  } else if (kmh <= 60) {
    speedLevel = 'S1';
  } else if (kmh <= 100) {
    speedLevel = 'S2';
  } else {
    speedLevel = 'S3';
  }

  renderAll();
}

function getSpeedLevel() {
  return speedLevel;
}

// 导出到 window
window.MODE = MODE;
window.PRIORITY = PRIORITY;
window.setMode = setMode;
window.getMode = getMode;
window.getPriority = getPriority;
window.pushMode = pushMode;
window.popMode = popMode;
window.emitEvent = emitEvent;
window.emitWarning = emitWarning;
window.setSpeed = setSpeed;
window.getSpeedLevel = getSpeedLevel;