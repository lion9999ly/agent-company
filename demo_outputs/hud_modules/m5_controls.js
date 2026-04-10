// M5: 控制
// 职责：沙盒面板交互、键盘快捷键、A/B 主题切换、开机自检

// 开机自检动画
function bootSequence() {
  const overlay = document.getElementById('boot-overlay');
  if (!overlay) return;

  // 隐藏沙盒面板
  const sandbox = document.getElementById('sandbox');
  if (sandbox) sandbox.classList.remove('open');

  // 初始化渲染
  setMode(MODE.CRUISE);
  setSpeed(0);
  renderAll();

  // 1s: 四角区域逐个亮起
  setTimeout(() => {
    const zones = ['zone-lt', 'zone-rt', 'zone-rb', 'zone-lb'];
    zones.forEach((id, i) => {
      setTimeout(() => {
        const el = document.getElementById(id);
        if (el) el.style.opacity = '1';
      }, i * 300);
    });
  }, 1000);

  // 2.5s: 底部信息栏滑入
  setTimeout(() => {
    const bottom = document.getElementById('bottom-bar');
    if (bottom) bottom.style.opacity = '1';
  }, 2500);

  // 3s: 覆盖层淡出
  setTimeout(() => {
    overlay.style.opacity = '0';
    setTimeout(() => {
      overlay.style.display = 'none';
    }, 500);
  }, 3000);
}

// 沙盒面板交互
function setupSandboxEvents() {
  const sandbox = document.getElementById('sandbox');
  if (!sandbox) return;

  sandbox.addEventListener('click', (e) => {
    const btn = e.target.closest('button[data-event]');
    if (!btn) return;

    const event = btn.dataset.event;
    handleSandboxEvent(event);
  });
}

function handleSandboxEvent(event) {
  switch (event) {
    case 'warn-front': emitWarning('front'); break;
    case 'warn-left': emitWarning('left'); break;
    case 'warn-right': emitWarning('right'); break;
    case 'call-zhang': setMode(MODE.CALL); window._callName = '张三'; renderAll(); break;
    case 'call-li': setMode(MODE.CALL); window._callName = '李四'; renderAll(); break;
    case 'mesh-join': setMode(MODE.MESH); window._meshCount = 3; renderAll(); break;
    case 'music-play': setMode(MODE.MUSIC); window._musicTrack = '追梦人'; renderAll(); break;
    case 'music-pause': setMode(MODE.CRUISE); break;
    case 'nav-start': setMode(MODE.NAV); window._navDistance = '3200'; renderAll(); break;
    case 'nav-left': window._navDistance = '200 左转'; renderAll(); break;
    case 'nav-arrive': window._navDistance = '0 已到达'; renderAll(); break;
    case 'dvr-start': setMode(MODE.DVR); window._dvrTime = '00:00'; renderAll(); break;
    case 'dvr-stop': setMode(MODE.CRUISE); break;
    case 'speed-0': setSpeed(0); break;
    case 'speed-40': setSpeed(40); break;
    case 'speed-80': setSpeed(80); break;
    case 'speed-120': setSpeed(120); break;
    case 'scenario-1': playScenario(1); break;
    case 'scenario-2': playScenario(2); break;
    case 'scenario-3': playScenario(3); break;
  }
}

// 键盘快捷键
function setupKeyboardShortcuts() {
  document.addEventListener('keydown', (e) => {
    // 空格：播放/暂停
    if (e.code === 'Space') {
      e.preventDefault();
      if (currentScenario) {
        pauseScenario();
      } else {
        playScenario(1);
      }
    }

    // 数字键：切换剧本
    if (e.key === '1') playScenario(1);
    if (e.key === '2') playScenario(2);
    if (e.key === '3') playScenario(3);

    // T：切换主题
    if (e.key === 't' || e.key === 'T') {
      document.body.classList.toggle('theme-green');
    }

    // S：切换沙盒面板
    if (e.key === 's' || e.key === 'S') {
      const sandbox = document.getElementById('sandbox');
      if (sandbox) sandbox.classList.toggle('open');
    }

    // W：前方预警
    if (e.key === 'w' || e.key === 'W') {
      emitWarning('front');
    }

    // A：左后预警
    if (e.key === 'a' || e.key === 'A') {
      emitWarning('left');
    }

    // D：右后预警
    if (e.key === 'd' || e.key === 'D') {
      emitWarning('right');
    }

    // Esc：重置
    if (e.key === 'Escape') {
      stopScenario();
      setMode(MODE.CRUISE);
      setSpeed(0);
      renderAll();
    }
  });
}

// 初始化
document.addEventListener('DOMContentLoaded', () => {
  setupSandboxEvents();
  setupKeyboardShortcuts();
});

// 导出
window.bootSequence = bootSequence;