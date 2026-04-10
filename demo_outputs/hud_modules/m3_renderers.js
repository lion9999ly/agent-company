// M3: 渲染器
// 职责：根据当前状态和速度等级，更新四角 + 底部的 DOM 内容

// 各状态的内容模板
const CONTENT_TEMPLATES = {
  cruise: {
    lt: () => `<div class="value">${currentSpeed}</div><div class="unit">km/h</div><div style="margin-top:8px;font-size:12px;color:var(--c-muted);">骑行中</div>`,
    rt: () => `<span style="color:var(--c-call)">●</span> 电量 87%<br><span style="color:var(--c-nav)">●</span> 信号 良好`,
    lb: () => '',
    rb: () => '',
    bottom: '就绪'
  },
  nav: {
    lt: () => `<div class="value">${currentSpeed}</div><div class="unit">km/h</div>`,
    rt: () => `<div style="color:var(--c-nav)">下一路口</div><div style="font-size:24px;font-weight:600;">${window._navDistance || '200'}m</div>`,
    lb: () => `<div style="font-size:32px;color:var(--c-nav);">←</div><div style="font-size:12px;">左转</div>`,
    rb: () => `<div style="color:var(--c-muted)">ETA</div><div style="font-size:18px;">${window._navETA || '5分钟'}</div>`,
    bottom: '导航中'
  },
  call: {
    lt: () => `<div class="value">${currentSpeed}</div><div class="unit">km/h</div>`,
    rt: () => `<div style="color:var(--c-call)">📞 来电</div><div style="font-size:20px;font-weight:600;">${window._callName || '张三'}</div>`,
    lb: () => `<div style="color:var(--c-call)">接听</div><div style="color:var(--c-muted)">按任意键</div>`,
    rb: () => `<div style="color:var(--c-warn)">挂断</div><div style="font-size:12px;">长按</div>`,
    bottom: '来电'
  },
  music: {
    lt: () => `<div class="value">${currentSpeed}</div><div class="unit">km/h</div>`,
    rt: () => '',
    lb: () => `<div style="font-size:14px;">${window._musicTrack || '未知歌曲'}</div><div style="font-size:12px;color:var(--c-muted);">${window._musicArtist || '未知歌手'}</div>`,
    rb: () => `<span style="color:var(--c-muted)">◀</span> <span style="color:var(--c-music)">▶</span> <span style="color:var(--c-muted)">▶</span>`,
    bottom: '音乐'
  },
  mesh: {
    lt: () => `<div class="value">${currentSpeed}</div><div class="unit">km/h</div>`,
    rt: () => `<div style="color:var(--c-mesh)">👥 组队</div><div style="font-size:24px;">${window._meshCount || 3}人</div>`,
    lb: () => `<div style="font-size:12px;">最近队友</div><div style="font-size:18px;">${window._meshDistance || '50'}m</div>`,
    rb: () => `<div style="color:var(--c-mesh)">已连接</div>`,
    bottom: '组队中'
  },
  warn: {
    lt: () => `<div class="value" style="color:var(--c-warn);">${currentSpeed}</div><div class="unit">km/h</div>`,
    rt: () => `<div style="color:var(--c-warn);font-size:18px;font-weight:600;">⚠ ${window._warnData?.type || '预警'}</div>`,
    lb: () => `<div style="font-size:14px;">方向</div><div style="font-size:18px;">${window._warnData?.direction || '前方'}</div>`,
    rb: () => `<div style="font-size:14px;">距离</div><div style="font-size:18px;">${window._warnData?.distance || '30m'}</div>`,
    bottom: '⚠ 注意安全'
  },
  dvr: {
    lt: () => `<div class="value">${currentSpeed}</div><div class="unit">km/h</div>`,
    rt: () => `<div style="color:var(--c-dvr)">● REC</div><div style="font-size:12px;">录制中</div>`,
    lb: () => '',
    rb: () => `<div style="font-size:14px;">时长</div><div style="font-size:18px;">${window._dvrTime || '00:00'}</div>`,
    bottom: '录制中'
  }
};

// 主渲染函数
function renderAll() {
  const mode = getMode();
  const level = getSpeedLevel();
  const template = CONTENT_TEMPLATES[mode] || CONTENT_TEMPLATES.cruise;

  // 更新速度显示
  const speedEl = document.getElementById('speed-value');
  if (speedEl) {
    speedEl.textContent = currentSpeed;
  }

  // 更新时间
  const timeEl = document.getElementById('current-time');
  if (timeEl) {
    const now = new Date();
    timeEl.textContent = now.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
  }

  // 根据速度等级决定渲染策略
  const zones = ['lt', 'rt', 'lb', 'rb'];

  zones.forEach(zone => {
    const contentEl = document.getElementById(`content-${zone}`);
    if (!contentEl) return;

    // S2/S3 精简模式
    if ((level === 'S2' || level === 'S3') && zone !== 'lt') {
      // 只保留速度和预警相关
      if (mode === 'warn' || zone === 'rt') {
        contentEl.innerHTML = template[zone] ? template[zone]() : '';
      } else {
        contentEl.innerHTML = '';
      }
    } else {
      contentEl.innerHTML = template[zone] ? template[zone]() : '';
    }
  });

  // 更新底部状态
  const bottomEl = document.getElementById('mode-label');
  if (bottomEl) {
    bottomEl.textContent = template.bottom || '骑行';
  }

  // 更新颜色主题
  const modeColors = {
    cruise: 'var(--c-speed)',
    nav: 'var(--c-nav)',
    call: 'var(--c-call)',
    music: 'var(--c-music)',
    mesh: 'var(--c-mesh)',
    warn: 'var(--c-warn)',
    dvr: 'var(--c-dvr)'
  };

  const speedValue = document.querySelector('#speed-value');
  if (speedValue) {
    speedValue.style.color = modeColors[mode] || 'var(--c-speed)';
  }
}

// 初始化时钟
setInterval(() => {
  const timeEl = document.getElementById('current-time');
  if (timeEl) {
    const now = new Date();
    timeEl.textContent = now.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
  }
}, 1000);

// 导出到 window
window.renderAll = renderAll;