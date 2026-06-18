/* ─── VisionIQ Detection Console Controller ─── */

let paused = false;
let uploadOpen = false;
let theatreMode = false;
let coverFit = false;
let activeView = 'live';

// Cloud Mode State Variables
let isCloudMode = false;
let browserStream = null;
let lastCloudDetections = [];
let cloudInfMs = 0;

// ─── Sci-Fi Sound FX (Web Audio API Synthesizer) ───
let audioCtx = null;
let soundEnabled = true;

function initAudio() {
  if (!audioCtx) {
    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  }
}

function playSynthSound(type) {
  if (!soundEnabled) return;
  try {
    initAudio();
    if (audioCtx.state === 'suspended') {
      audioCtx.resume();
    }
    
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    
    osc.connect(gain);
    gain.connect(audioCtx.destination);
    
    const now = audioCtx.currentTime;
    
    if (type === 'click') {
      osc.type = 'sine';
      osc.frequency.setValueAtTime(600, now);
      osc.frequency.exponentialRampToValueAtTime(100, now + 0.1);
      gain.gain.setValueAtTime(0.08, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.1);
      osc.start(now);
      osc.stop(now + 0.1);
    } else if (type === 'capture') {
      osc.type = 'sawtooth';
      osc.frequency.setValueAtTime(150, now);
      osc.frequency.exponentialRampToValueAtTime(1200, now + 0.15);
      gain.gain.setValueAtTime(0.06, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.2);
      osc.start(now);
      osc.stop(now + 0.2);
    } else if (type === 'lock') {
      osc.type = 'sine';
      osc.frequency.setValueAtTime(880, now);
      osc.frequency.setValueAtTime(1200, now + 0.05);
      gain.gain.setValueAtTime(0.08, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.12);
      osc.start(now);
      osc.stop(now + 0.12);
    } else if (type === 'warn') {
      osc.type = 'triangle';
      osc.frequency.setValueAtTime(330, now);
      osc.frequency.linearRampToValueAtTime(220, now + 0.35);
      gain.gain.setValueAtTime(0.12, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.35);
      osc.start(now);
      osc.stop(now + 0.35);
    }
  } catch (e) {
    console.error("Audio playback error:", e);
  }
}

// ─── Telemetry Console Log ───
function addTelemetryLog(message, type = 'info') {
  const log = document.getElementById('telemetryLog');
  if (!log) return;
  
  const line = document.createElement('div');
  line.className = `log-line ${type}`;
  const timestamp = new Date().toLocaleTimeString();
  line.textContent = `[${timestamp}] ${message}`;
  
  log.appendChild(line);
  log.scrollTop = log.scrollHeight;
  
  while (log.children.length > 30) {
    log.removeChild(log.firstChild);
  }
}

// ─── Toast System ───
window.toast = function(msg, type = '') {
  const t = document.getElementById('toast');
  const m = document.getElementById('toastMsg');
  const i = document.getElementById('toastIcon');
  if (!t || !m || !i) return;

  m.textContent = msg;
  t.className = 'toast' + (type ? ' ' + type : '');
  
  // Icon vector replacement based on toast type
  i.innerHTML = type === 'err'
    ? '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>'
    : type === 'warn'
    ? '<path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>'
    : '<path d="M20 6L9 17l-5-5"/>';
    
  void t.offsetWidth; // Force reflow for CSS animation restart
  t.classList.add('show');
  
  // Auto-hide toast
  setTimeout(() => t.classList.remove('show'), 3500);
};

// ─── Sensitivity Slider ───
const slider = document.getElementById('confSlider');
const confVal = document.getElementById('confVal');

function updateSliderBg() {
  if (!slider) return;
  const pct = ((slider.value - slider.min) / (slider.max - slider.min)) * 100;
  slider.style.background = `linear-gradient(to right, var(--blue) ${pct}%, var(--border2) ${pct}%)`;
}

if (slider) {
  slider.addEventListener('input', () => {
    if (confVal) confVal.textContent = Number(slider.value).toFixed(2);
    updateSliderBg();
  });
  slider.addEventListener('change', () => {
    playSynthSound('click');
    addTelemetryLog(`Sensitivity adjusted to: ${parseFloat(slider.value).toFixed(2)}`, 'info');
    fetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ conf: parseFloat(slider.value) })
    });
  });
  updateSliderBg();
}

// ─── Pause Control ───
window.syncPauseUI = function() {
  const img = document.getElementById('feedImg');
  if (img) {
    img.src = paused ? '' : '/video_feed?' + Date.now();
  }
  if (!paused) {
    activeView = 'live';
    fetchStats();
  }
  
  const overlay = document.getElementById('pauseOverlay');
  if (overlay) overlay.classList.toggle('show', paused);

  const lbl = document.getElementById('pauseLbl');
  const btn = document.getElementById('btnPause');
  const ic = document.getElementById('pauseIcon');
  
  if (lbl) lbl.textContent = paused ? 'Resume' : 'Pause';
  if (btn) btn.classList.toggle('paused', paused);
  if (ic) {
    ic.innerHTML = paused
      ? '<polygon points="5 3 19 12 5 21 5 3"/>'
      : '<rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/>';
  }

  const fLbl = document.getElementById('fullPauseLbl');
  const fIcon = document.getElementById('fullPauseIcon');
  const fBtn = document.getElementById('fullPauseBtn');
  
  if (fLbl) fLbl.textContent = paused ? 'Resume Feed' : 'Pause Feed';
  if (fIcon) {
    fIcon.innerHTML = paused
      ? '<polygon points="5 3 19 12 5 21 5 3"/>'
      : '<rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/>';
  }
  if (fBtn) fBtn.classList.toggle('paused', paused);

  fetch('/api/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ paused })
  });
};

window.togglePause = function() {
  paused = !paused;
  window.syncPauseUI();
};

// ─── File Upload Drawer ───
window.toggleUpload = function() {
  uploadOpen = !uploadOpen;
  const panel = document.getElementById('uploadPanel');
  if (panel) panel.classList.toggle('show', uploadOpen);
};

window.handleDrop = function(e) {
  e.preventDefault();
  const dz = document.getElementById('dropZone');
  if (dz) dz.classList.remove('over');
  if (e.dataTransfer.files[0]) uploadFile(e.dataTransfer.files[0]);
};

window.handleFile = function(e) {
  if (e.target.files[0]) uploadFile(e.target.files[0]);
};

window.openMobileCamera = function() {
  const input = document.getElementById('mobileInput');
  if (input) input.click();
};

window.handleMobilePhoto = function(e) {
  const f = e.target.files[0];
  if (!f) return;
  uploadFile(f, true);
  e.target.value = '';
};

// ─── File Upload Logic ───
async function uploadFile(file, fromMobile = false) {
  const dz = document.getElementById('dropZone');
  if (!dz) return;
  const origHTML = dz.innerHTML;
  dz.innerHTML = '<div class="spin" style="border-top-color:#000;display:inline-block;margin:0 auto"></div><div class="drop-txt" style="margin-top:8px">Analysing…</div>';
  
  if (!uploadOpen) window.toggleUpload();

  const mb = document.getElementById('btnMobile');
  const mfb = document.getElementById('mobileFullBtn');
  if (mb) mb.disabled = true;
  if (mfb) mfb.disabled = true;

  const form = new FormData();
  form.append('file', file);
  
  try {
    const res = await fetch('/api/upload', { method: 'POST', body: form });
    const data = await res.json();
    if (data.error) throw new Error(data.error);

    const uCount = document.getElementById('uCount');
    if (uCount) {
      uCount.textContent = `${data.detections} object${data.detections !== 1 ? 's' : ''} found`;
    }
    
    const med = document.getElementById('uploadMedia');
    if (med) {
      med.innerHTML = data.type === 'image'
        ? `<img src="${data.url}?t=${Date.now()}" alt="Result" style="width:100%;border-radius:8px;display:block;max-height:280px;object-fit:contain;background:#0d1117;border:1px solid var(--border)">`
        : `<video src="${data.url}" controls style="width:100%;border-radius:8px;border:1px solid var(--border)"></video>`;
    }

    const uCrops = document.getElementById('uploadCrops');
    if (uCrops) {
      if (data.type === 'image' && data.crops && data.crops.length > 0) {
        uCrops.innerHTML = data.crops.map((crop, i) => {
          return `<div class="crop-card" onclick="openPreviewModal('${crop.url}', '${crop.class_name}', ${crop.confidence})" title="Click to preview ${crop.class_name}">`
            + `<img src="${crop.url}" class="crop-card-img" alt="${crop.class_name}">`
            + `<div class="crop-card-info">`
            + `<span class="crop-card-name">${crop.class_name}</span>`
            + `<span class="crop-card-conf">${Math.round(crop.confidence * 100)}%</span>`
            + `</div>`
            + `<button class="crop-card-dl" onclick="event.stopPropagation(); downloadFileFromServer('${crop.url}', 'crop_${crop.class_name}.jpg')" title="Download crop">`
            + `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>`
            + `</button>`
            + `</div>`;
        }).join('');
        uCrops.previousElementSibling.style.display = 'block';
        uCrops.style.display = 'flex';
      } else {
        uCrops.innerHTML = '';
        uCrops.previousElementSibling.style.display = 'none';
        uCrops.style.display = 'none';
      }
    }

    const dets = document.getElementById('uploadDets');
    if (data.type === 'image' && data.classes && dets) {
      const entries = Object.entries(data.classes);
      dets.innerHTML = entries.length === 0
        ? '<div class="no-cap">No objects detected.</div>'
        : entries.sort((a, b) => b[1] - a[1]).map(([n, c], i) => {
            return `<div class="cap-row" style="animation-delay:${i * .05}s">`
              + `<span class="cap-row-name">${n}</span>`
              + `<span class="cap-row-cnt">×${c}</span></div>`;
          }).join('');
      dets.style.display = 'flex';
    } else if (dets) {
      dets.style.display = 'none';
    }

    const resDiv = document.getElementById('uploadResult');
    if (resDiv) resDiv.style.display = 'block';

    // Update right sidebar with upload detections
    activeView = 'upload';
    const list = document.getElementById('detList');
    if (list) {
      const entries = Object.entries(data.classes || {});
      if (entries.length === 0) {
        list.innerHTML = '<div class="no-det" style="font-size: 1.15rem; font-weight: 700; color: var(--text3); padding: 30px 0;">No objects detected</div>';
      } else {
        list.innerHTML = entries.sort((a, b) => b[1] - a[1]).map(([n, c], i) => {
          return `<div class="det-item" style="animation-delay:${i * .04}s">`
            + `<span class="det-name">${n}</span>`
            + `<span class="det-cnt">${c}</span></div>`;
        }).join('');
      }
    }
    const dCount = document.getElementById('dCount');
    if (dCount) {
      dCount.textContent = Object.values(data.classes || {}).reduce((s, c) => s + c, 0);
    }

    const dlBtn = document.getElementById('btnDownloadUpload');
    if (dlBtn) {
      if (data.type === 'image') {
        dlBtn.setAttribute('data-url', data.url);
        dlBtn.style.display = 'inline-flex';
      } else {
        dlBtn.style.display = 'none';
      }
    }

    window.toast(fromMobile ? '📱 Mobile snapshot analysed!' : 'File analysed successfully.');
  } catch (err) {
    window.toast('Analysis failed: ' + err.message, 'err');
  } finally {
    dz.innerHTML = origHTML;
    if (mb) mb.disabled = false;
    if (mfb) mfb.disabled = false;
  }
}

// ─── Snapshot Capture and History ───
let snapshotHistory = [];

window.captureAndDetect = async function() {
  if (paused) {
    window.toast('Resume the feed before capturing.', 'warn');
    return;
  }
  
  const btn = document.getElementById('btnCap');
  const orig = btn ? btn.innerHTML : '';
  const flash = document.getElementById('flash');
  if (flash) {
    flash.classList.add('go');
    setTimeout(() => flash.classList.remove('go'), 160);
  }
  
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<div class="spin"></div> Analysing…';
  }
  
  try {
    playSynthSound('capture');
    addTelemetryLog("Initiating frame capture...", "info");

    let res, data;
    if (isCloudMode) {
      const video = document.getElementById('browserVideo');
      const capCanvas = document.createElement('canvas');
      capCanvas.width = video.videoWidth || 640;
      capCanvas.height = video.videoHeight || 480;
      const ctx = capCanvas.getContext('2d');
      ctx.drawImage(video, 0, 0, capCanvas.width, capCanvas.height);
      
      const blob = await new Promise(resolve => capCanvas.toBlob(resolve, 'image/jpeg', 0.9));
      const form = new FormData();
      form.append('file', blob, 'capture.jpg');
      
      res = await fetch('/api/upload', { method: 'POST', body: form });
      const uploadData = await res.json();
      if (uploadData.error) throw new Error(uploadData.error);
      
      data = {
        url: uploadData.url,
        detections: uploadData.detections,
        confidence_warning: uploadData.confidence_warning,
        classes: uploadData.classes || {},
        crops: uploadData.crops || []
      };
    } else {
      res = await fetch('/api/capture', { method: 'POST' });
      data = await res.json();
      if (data.error) throw new Error(data.error);
    }

    const snapshot = {
      id: Date.now(),
      url: data.url + (data.url.includes('?') ? '&' : '?') + 't=' + Date.now(),
      count: data.detections,
      warning: data.confidence_warning,
      classes: data.classes || {},
      crops: data.crops || []
    };
    
    // Add to local history list (up to 5 history items)
    snapshotHistory.unshift(snapshot);
    if (snapshotHistory.length > 5) snapshotHistory.pop();
    
    // Render current snapshot
    renderActiveSnapshot(snapshot);
    
    // Render history sidebar if exists
    renderHistoryGallery();

    const capDiv = document.getElementById('capResult');
    if (capDiv) {
      capDiv.classList.add('show');
      capDiv.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
    
    playSynthSound('lock');
    addTelemetryLog(`Capture complete: detected ${data.detections} objects.`, "detect");
    window.toast('Snapshot captured!');
  } catch (err) {
    window.toast('Capture failed: ' + err.message, 'err');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = orig;
    }
  }
};

function renderActiveSnapshot(snap) {
  const img = document.getElementById('capImg');
  const badge = document.getElementById('capBadge');
  const lowBadge = document.getElementById('capLowBadge');
  const dets = document.getElementById('capDets');
  
  if (img) img.src = snap.url;
  if (badge) badge.textContent = `${snap.count} object${snap.count !== 1 ? 's' : ''} found`;
  if (lowBadge) lowBadge.classList.remove('show');

  const dlBtn = document.getElementById('btnDownloadCap');
  if (dlBtn) {
    dlBtn.setAttribute('data-url', snap.url);
    dlBtn.style.display = 'inline-flex';
  }

  const cCrops = document.getElementById('capCrops');
  if (cCrops) {
    if (snap.crops && snap.crops.length > 0) {
      cCrops.innerHTML = snap.crops.map((crop, i) => {
        return `<div class="crop-card" onclick="openPreviewModal('${crop.url}', '${crop.class_name}', ${crop.confidence})" title="Click to preview ${crop.class_name}">`
          + `<img src="${crop.url}" class="crop-card-img" alt="${crop.class_name}">`
          + `<div class="crop-card-info">`
          + `<span class="crop-card-name">${crop.class_name}</span>`
          + `<span class="crop-card-conf">${Math.round(crop.confidence * 100)}%</span>`
          + `</div>`
          + `<button class="crop-card-dl" onclick="event.stopPropagation(); downloadFileFromServer('${crop.url}', 'crop_${crop.class_name}.jpg')" title="Download crop">`
          + `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>`
          + `</button>`
          + `</div>`;
      }).join('');
      cCrops.previousElementSibling.style.display = 'block';
      cCrops.style.display = 'flex';
    } else {
      cCrops.innerHTML = '';
      cCrops.previousElementSibling.style.display = 'none';
      cCrops.style.display = 'none';
    }
  }

  if (dets) {
    const entries = Object.entries(snap.classes);
      dets.innerHTML = entries.length === 0
      ? '<div class="no-cap">Nothing detected in this snapshot.</div>'
      : entries.sort((a, b) => b[1] - a[1]).map(([n, c], i) => {
          return `<div class="cap-row" style="animation-delay:${i * .05}s">`
            + `<span class="cap-row-name">${n}</span>`
            + `<span class="cap-row-cnt">×${c}</span></div>`;
        }).join('');
  }

  // Update right sidebar with snapshot detections
  activeView = 'snapshot';
  const list = document.getElementById('detList');
  if (list) {
    const entries = Object.entries(snap.classes || {});
    if (entries.length === 0) {
      list.innerHTML = '<div class="no-det" style="font-size: 1.15rem; font-weight: 700; color: var(--text3); padding: 30px 0;">No objects detected</div>';
    } else {
      list.innerHTML = entries.sort((a, b) => b[1] - a[1]).map(([n, c], i) => {
        return `<div class="det-item" style="animation-delay:${i * .04}s">`
          + `<span class="det-name">${n}</span>`
          + `<span class="det-cnt">${c}</span></div>`;
      }).join('');
    }
  }
  const dCount = document.getElementById('dCount');
  if (dCount) {
    dCount.textContent = Object.values(snap.classes || {}).reduce((s, c) => s + c, 0);
  }
}

function renderHistoryGallery() {
  const gallery = document.getElementById('historyGallery');
  if (!gallery) return;
  
  if (snapshotHistory.length <= 1) {
    gallery.innerHTML = '<div style="font-size:.7rem;color:var(--text4);text-align:center;padding:10px 0;">Previous captures appear here</div>';
    return;
  }
  
  // Show past items (excluding the active newest one at index 0)
  gallery.innerHTML = snapshotHistory.slice(1).map(snap => {
    return `<div class="gallery-item" onclick="loadHistoricalSnapshot(${snap.id})" style="display:flex;align-items:center;gap:10px;padding:8px;border:1px solid var(--border);border-radius:6px;cursor:pointer;background:var(--surface2);margin-bottom:6px;transition:all .15s;">
      <img src="${snap.url}" style="width:40px;height:30px;object-fit:cover;border-radius:4px;">
      <div style="flex:1;min-width:0;">
        <div style="font-size:.74rem;font-weight:700;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">Snapshot Captures</div>
        <div style="font-size:.64rem;color:var(--text3);">${snap.count} object${snap.count!==1?'s':''}</div>
      </div>
    </div>`;
  }).join('');
}

window.loadHistoricalSnapshot = function(id) {
  const snap = snapshotHistory.find(s => s.id === id);
  if (snap) {
    renderActiveSnapshot(snap);
    window.toast('Historical snapshot loaded');
  }
};

window.dismissCapture = function() {
  const capDiv = document.getElementById('capResult');
  if (capDiv) capDiv.classList.remove('show');
  const img = document.getElementById('capImg');
  if (img) img.src = '';
  activeView = 'live';
  fetchStats();
};

// ─── Live Metrics & Detections Polling ───
let prevDetsCount = 0;
let initialSyncDone = false;

function syncControlsOnLoad(data) {
  if (initialSyncDone) return;
  initialSyncDone = true;
  
  if (slider) {
    slider.value = data.conf;
    if (confVal) confVal.textContent = Number(data.conf).toFixed(2);
    updateSliderBg();
  }
  
  const iouSlider = document.getElementById('iouSlider');
  const iouVal = document.getElementById('iouVal');
  if (iouSlider) {
    iouSlider.value = data.iou || 0.45;
    if (iouVal) iouVal.textContent = Number(iouSlider.value).toFixed(2);
    const pct = ((iouSlider.value - iouSlider.min) / (iouSlider.max - iouSlider.min)) * 100;
    iouSlider.style.background = `linear-gradient(to right, var(--blue) ${pct}%, var(--border2) ${pct}%)`;
  }
  
  if (data.imgsz) {
    document.querySelectorAll('#imgszSelector button').forEach(b => b.classList.remove('active'));
    const activeBtn = document.getElementById(`btnImgsz${data.imgsz}`);
    if (activeBtn) activeBtn.classList.add('active');
    const imgszValText = document.getElementById('imgszVal');
    if (imgszValText) imgszValText.textContent = `${data.imgsz}px`;
  }
  
  const ttaToggle = document.getElementById('ttaToggle');
  if (ttaToggle) {
    ttaToggle.checked = !!data.augment;
  }

  if (data.width !== undefined) {
    document.querySelectorAll('#widthSelector button').forEach(b => b.classList.remove('active'));
    const activeBtn = document.getElementById(`btnWidth${data.width}`);
    if (activeBtn) activeBtn.classList.add('active');
    const displayWidthValText = document.getElementById('displayWidthVal');
    if (displayWidthValText) displayWidthValText.textContent = data.width === 0 ? "Native" : `${data.width}px`;
  }
  
  addTelemetryLog(`[SYSTEM] VisionIQ configuration synced. Resolution: ${data.imgsz}px, NMS IoU: ${data.iou || 0.45}, Quality: ${data.width === 0 ? 'Native' : data.width + 'px'}`, 'info');
}

let cloudDetectionStarted = false;
async function startCloudDetection() {
  if (cloudDetectionStarted) return;
  cloudDetectionStarted = true;

  const video = document.getElementById('browserVideo');
  const canvas = document.getElementById('detectCanvas');
  const imgWrap = document.getElementById('feedImg');
  const camWrap = document.getElementById('browserCamWrap');

  if (imgWrap) imgWrap.style.display = 'none';
  if (camWrap) camWrap.style.display = 'block';

  if (!browserStream) {
    try {
      browserStream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: "environment" }
      });
      video.srcObject = browserStream;
      addTelemetryLog("[SYSTEM] Browser camera initialized successfully.", "info");
    } catch (err) {
      console.error("Camera access failed:", err);
      addTelemetryLog("[ERROR] Failed to access browser camera: " + err.message, "err");
      window.toast("Camera access failed", "err");
      cloudDetectionStarted = false;
      return;
    }
  }

  // Draw loop for overlay
  function renderCanvas() {
    if (!isCloudMode) return;
    requestAnimationFrame(renderCanvas);

    if (paused || activeView !== 'live') {
      const ctx = canvas.getContext('2d');
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      return;
    }
    
    const videoWidth = video.videoWidth;
    const videoHeight = video.videoHeight;
    if (!videoWidth || !videoHeight) return;

    const elementWidth = video.clientWidth;
    const elementHeight = video.clientHeight;

    const videoRatio = videoWidth / videoHeight;
    const elementRatio = elementWidth / elementHeight;
    let width, height, x, y;
    if (elementRatio > videoRatio) {
      height = elementHeight;
      width = height * videoRatio;
      x = (elementWidth - width) / 2;
      y = 0;
    } else {
      width = elementWidth;
      height = width / videoRatio;
      x = 0;
      y = (elementHeight - height) / 2;
    }

    canvas.style.left = `${x}px`;
    canvas.style.top = `${y}px`;
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    canvas.width = width;
    canvas.height = height;

    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, width, height);

    const scaleX = width / videoWidth;
    const scaleY = height / videoHeight;

    lastCloudDetections.forEach(det => {
      const [x1, y1, x2, y2] = det.bbox;
      const rx1 = x1 * scaleX;
      const ry1 = y1 * scaleY;
      const rx2 = x2 * scaleX;
      const ry2 = y2 * scaleY;
      const rw = rx2 - rx1;
      const rh = ry2 - ry1;

      // Draw box
      ctx.strokeStyle = '#38bdf8';
      ctx.lineWidth = 2.5;
      ctx.shadowBlur = 4;
      ctx.shadowColor = '#38bdf8';
      ctx.strokeRect(rx1, ry1, rw, rh);
      ctx.shadowBlur = 0; // Reset shadow

      // Label background
      ctx.fillStyle = 'rgba(56, 189, 248, 0.9)';
      const label = `${det.class_name} ${Math.round(det.confidence * 100)}%`;
      ctx.font = 'bold 12px "Outfit", "Inter", sans-serif';
      const textWidth = ctx.measureText(label).width;
      ctx.fillRect(rx1, ry1 - 18 > 0 ? ry1 - 18 : ry1, textWidth + 10, 18);

      // Label text
      ctx.fillStyle = '#090d16';
      ctx.fillText(label, rx1 + 5, ry1 - 18 > 0 ? ry1 - 5 : ry1 + 13);
    });
  }
  renderCanvas();

  // Network send loop
  const offscreenCanvas = document.createElement('canvas');
  let isSendingFrame = false;

  async function sendFrame() {
    if (!isCloudMode) return;

    if (paused || activeView !== 'live' || video.readyState < 2 || isSendingFrame) {
      setTimeout(sendFrame, 200);
      return;
    }

    isSendingFrame = true;
    offscreenCanvas.width = video.videoWidth;
    offscreenCanvas.height = video.videoHeight;
    const ctx = offscreenCanvas.getContext('2d');
    ctx.drawImage(video, 0, 0, offscreenCanvas.width, offscreenCanvas.height);

    offscreenCanvas.toBlob(async (blob) => {
      if (!blob) {
        isSendingFrame = false;
        setTimeout(sendFrame, 200);
        return;
      }
      const fd = new FormData();
      fd.append("file", blob, "frame.jpg");

      try {
        const tStart = performance.now();
        const res = await fetch("/api/detect_frame", { method: "POST", body: fd });
        if (!res.ok) throw new Error("Server error");
        const data = await res.json();
        
        lastCloudDetections = data.detections || [];
        cloudInfMs = data.inf_ms || (performance.now() - tStart);

        const currentCount = lastCloudDetections.length;
        if (currentCount > prevDetsCount) {
          playSynthSound('lock');
          const counts = {};
          lastCloudDetections.forEach(d => {
            counts[d.class_name] = (counts[d.class_name] || 0) + 1;
          });
          Object.entries(counts).forEach(([n, c]) => {
            addTelemetryLog(`[DETECT] identified ${n} (x${c})`, 'detect');
          });
        }
        prevDetsCount = currentCount;

        // Update active detections list in sidebar
        const list = document.getElementById('detList');
        if (list) {
          const counts = {};
          lastCloudDetections.forEach(d => {
            counts[d.class_name] = (counts[d.class_name] || 0) + 1;
          });
          const entries = Object.entries(counts);
          if (entries.length === 0) {
            list.innerHTML = '<div class="no-det" style="font-size: 1.15rem; font-weight: 700; color: var(--text3); padding: 30px 0;">Not visible</div>';
          } else {
            list.innerHTML = entries.sort((a, b) => b[1] - a[1]).map(([n, c], i) => {
              return `<div class="det-item" style="animation-delay:${i * .04}s">`
                + `<span class="det-name">${n}</span>`
                + `<span class="det-cnt">${c}</span></div>`;
            }).join('');
          }
        }
      } catch (err) {
        console.error("Frame detection failed:", err);
      } finally {
        isSendingFrame = false;
      }
      setTimeout(sendFrame, 250); // ~4 FPS target
    }, "image/jpeg", 0.7);
  }
  sendFrame();
}

function fetchStats() {
  if (paused || activeView !== 'live') return;
  fetch('/api/stats')
    .then(r => r.json())
    .then(data => {
      if (!initialSyncDone) {
        syncControlsOnLoad(data);
      }

      const dFps = document.getElementById('dFps');
      const dInf = document.getElementById('dInf');
      const dCount = document.getElementById('dCount');

      if (data.mode === 'cloud') {
        isCloudMode = true;
        startCloudDetection();
        if (dFps) dFps.textContent = paused ? '—' : '4 fps';
        if (dInf) dInf.textContent = paused ? '—' : (cloudInfMs > 0 ? Math.round(cloudInfMs) + ' ms' : '—');
        
        const currentCount = lastCloudDetections.length;
        if (dCount) dCount.textContent = currentCount;
        return;
      }

      // Local mode fallback: ensure feed image is shown and browser camera container is hidden
      isCloudMode = false;
      const imgWrap = document.getElementById('feedImg');
      const camWrap = document.getElementById('browserCamWrap');
      if (imgWrap && imgWrap.style.display !== 'block') imgWrap.style.display = 'block';
      if (camWrap && camWrap.style.display !== 'none') camWrap.style.display = 'none';
      // Ensure MJPEG stream source is set on first load (fixes black screen)
      if (imgWrap && !paused && (!imgWrap.src || !imgWrap.src.includes('/video_feed'))) {
        imgWrap.src = '/video_feed?' + Date.now();
      }
      
      if (dFps) dFps.textContent = data.fps > 0 ? data.fps + ' fps' : '—';
      if (dInf) dInf.textContent = data.inf_ms > 0 ? data.inf_ms + ' ms' : '—';
      
      const dets = Object.entries(data.active_detections || {});
      const currentCount = dets.reduce((s, [, c]) => s + c, 0);
      if (dCount) dCount.textContent = currentCount;

      if (currentCount > prevDetsCount) {
        playSynthSound('lock');
        dets.forEach(([n, c]) => {
          addTelemetryLog(`[DETECT] identified ${n} (x${c})`, 'detect');
        });
      }
      prevDetsCount = currentCount;

      const list = document.getElementById('detList');
      if (list) {
        if (dets.length === 0) {
          list.innerHTML = '<div class="no-det" style="font-size: 1.15rem; font-weight: 700; color: var(--text3); padding: 30px 0;">Not visible</div>';
        } else {
          list.innerHTML = dets.sort((a, b) => b[1] - a[1]).map(([n, c], i) => {
            return `<div class="det-item" style="animation-delay:${i * .04}s">`
              + `<span class="det-name">${n}</span>`
              + `<span class="det-cnt">${c}</span></div>`;
          }).join('');
        }
      }
    })
    .catch(() => {});
}

setInterval(fetchStats, 750);
fetchStats();

// ─── Theatre, Fit, Fullscreen Layout toggles ───
window.toggleTheatreMode = function() {
  theatreMode = !theatreMode;
  const grid = document.querySelector('.main-grid');
  const btn = document.getElementById('btnTheatre');
  if (grid) grid.classList.toggle('theatre', theatreMode);
  if (btn) btn.classList.toggle('active', theatreMode);
  
  const wrap = document.getElementById('feedWrap');
  if (wrap) wrap.scrollIntoView({ behavior: 'smooth', block: 'center' });
  
  window.toast(theatreMode ? 'Theatre mode enabled' : 'Theatre mode disabled');
};

window.toggleFocusMode = function() {
  const grid = document.querySelector('.main-grid');
  const btn = document.getElementById('btnFocusMode');
  if (!grid || !btn) return;
  
  const isFocus = grid.classList.toggle('focus-mode');
  btn.classList.toggle('active', isFocus);
  
  const lbl = btn.querySelector('.ctrl-lbl');
  if (lbl) lbl.textContent = isFocus ? 'Normal' : 'Focus';
  
  window.toast(isFocus ? 'Focus Mode: Sidebar hidden for maximum view' : 'Focus Mode: Sidebar visible');
};

window.toggleFullScreen = function() {
  const fw = document.getElementById('feedWrap');
  if (!fw) return;
  if (!document.fullscreenElement) {
    fw.requestFullscreen().catch(err => {
      window.toast("Fullscreen error: " + err.message, "err");
    });
  } else {
    document.exitFullscreen();
  }
};

// ─── Dynamic Model Selection ───
window.changeModel = function(btn, modelName) {
  playSynthSound('click');
  document.querySelectorAll('.model-sel-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  
  window.toast(`Loading model: ${modelName}...`, 'warn');
  addTelemetryLog(`[SYSTEM] Swapping model to ${modelName}...`, 'warn');
  
  fetch('/api/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model: modelName })
  })
  .then(r => r.json())
  .then(data => {
    playSynthSound('lock');
    window.toast(`Successfully loaded ${modelName}`);
    addTelemetryLog(`[SYSTEM] Hot-swapped model successfully: ${modelName}`, 'info');
  })
  .catch(() => {
    playSynthSound('warn');
    window.toast(`Failed to load ${modelName}`, 'err');
    addTelemetryLog(`[ERROR] Model hot-swap failed: ${modelName}`, 'err');
  });
};

// ─── Extra Accuracy & Sound Controller Actions ───
window.changeImgsz = function(btn, size) {
  playSynthSound('click');
  document.querySelectorAll('#imgszSelector button').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  
  const imgszValText = document.getElementById('imgszVal');
  if (imgszValText) imgszValText.textContent = `${size}px`;
  
  addTelemetryLog(`[SYSTEM] Resizing inference window to ${size}px`, 'warn');
  
  fetch('/api/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ imgsz: size })
  })
  .then(r => r.json())
  .then(() => {
    playSynthSound('lock');
    addTelemetryLog(`[SYSTEM] Inference size hot-swapped to ${size}px`, 'info');
  })
  .catch(err => {
    playSynthSound('warn');
    addTelemetryLog(`[ERROR] Failed to switch resolution: ${err.message}`, 'err');
  });
};

window.toggleTTA = function(checkbox) {
  playSynthSound('click');
  const checked = checkbox.checked;
  addTelemetryLog(`[SYSTEM] Setting TTA Accuracy booster to: ${checked ? 'ON' : 'OFF'}`, 'warn');
  
  fetch('/api/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ augment: checked })
  })
  .then(() => {
    playSynthSound('lock');
    addTelemetryLog(`[SYSTEM] TTA Accuracy booster configured: ${checked ? 'ON' : 'OFF'}`, 'info');
  })
  .catch(err => {
    playSynthSound('warn');
    addTelemetryLog(`[ERROR] TTA config failed: ${err.message}`, 'err');
  });
};

window.toggleSound = function(checkbox) {
  soundEnabled = checkbox.checked;
  playSynthSound('click');
  addTelemetryLog(`[AUDIO] Sound effects set to: ${soundEnabled ? 'ENABLED' : 'DISABLED'}`, 'info');
};

window.changeWidth = function(btn, size) {
  playSynthSound('click');
  document.querySelectorAll('#widthSelector button').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  
  const displayWidthValText = document.getElementById('displayWidthVal');
  if (displayWidthValText) displayWidthValText.textContent = size === 0 ? "Native" : `${size}px`;
  
  addTelemetryLog(`[SYSTEM] Adjusting live feed display resolution to: ${size === 0 ? 'Native' : size + 'px'}`, 'warn');
  
  fetch('/api/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ width: size })
  })
  .then(r => r.json())
  .then(() => {
    playSynthSound('lock');
    addTelemetryLog(`[SYSTEM] Live feed resolution updated to: ${size === 0 ? 'Native' : size + 'px'}`, 'info');
  })
  .catch(err => {
    playSynthSound('warn');
    addTelemetryLog(`[ERROR] Failed to switch display resolution: ${err.message}`, 'err');
  });
};

// ─── Spotlight ───
document.addEventListener('DOMContentLoaded', () => {
  const fw = document.getElementById('feedWrap');
  if (fw) {
    fw.addEventListener('mousemove', e => {
      const r = fw.getBoundingClientRect();
      const x = ((e.clientX - r.left) / r.width * 100).toFixed(1) + '%';
      const y = ((e.clientY - r.top) / r.height * 100).toFixed(1) + '%';
      fw.style.setProperty('--mx', x);
      fw.style.setProperty('--my', y);
    });
  }

  const iouSlider = document.getElementById('iouSlider');
  const iouVal = document.getElementById('iouVal');
  if (iouSlider) {
    iouSlider.addEventListener('input', () => {
      if (iouVal) iouVal.textContent = Number(iouSlider.value).toFixed(2);
      const pct = ((iouSlider.value - iouSlider.min) / (iouSlider.max - iouSlider.min)) * 100;
      iouSlider.style.background = `linear-gradient(to right, var(--blue) ${pct}%, var(--border2) ${pct}%)`;
    });
    iouSlider.addEventListener('change', () => {
      playSynthSound('click');
      addTelemetryLog(`[SYSTEM] NMS overlap threshold changed to: ${parseFloat(iouSlider.value).toFixed(2)}`, 'info');
      fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ iou: parseFloat(iouSlider.value) })
      });
    });
  }

  const feedImg = document.getElementById('feedImg');
});

/* High-reliability blob-based download function */
window.downloadFileFromServer = async function(url, filename) {
  if (!url) {
    window.toast('No image URL available for download', 'warn');
    return;
  }
  window.toast('Preparing download...', 'info');
  try {
    const response = await fetch(url);
    if (!response.ok) throw new Error('Network response was not OK');
    const blob = await response.blob();
    const blobUrl = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = blobUrl;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(blobUrl);
    window.toast('Download complete!');
  } catch (err) {
    window.toast('Download failed: ' + err.message, 'err');
  }
};

// ─── Preview Modal Controller ───
window.openPreviewModal = function(imageUrl, className, confidence) {
  const modal = document.getElementById('previewModal');
  const img = document.getElementById('modalImg');
  const title = document.getElementById('modalTitle');
  const meta = document.getElementById('modalMeta');
  const dlBtn = document.getElementById('modalDownloadBtn');
  
  if (!modal || !img) return;
  
  img.src = imageUrl;
  if (title) title.textContent = className;
  if (meta) meta.textContent = `Confidence: ${Math.round(confidence * 100)}%`;
  if (dlBtn) {
    dlBtn.onclick = function() {
      downloadFileFromServer(imageUrl, `crop_${className}.jpg`);
    };
  }
  
  modal.classList.add('show');
  document.body.style.overflow = 'hidden';
};

window.closePreviewModal = function(e) {
  const modal = document.getElementById('previewModal');
  if (modal) {
    modal.classList.remove('show');
    document.body.style.overflow = '';
  }
};

// Close modal on Escape key
document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') {
    closePreviewModal();
  }
});
