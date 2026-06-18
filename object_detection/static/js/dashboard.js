/* ─── VisionIQ Dashboard Controller ─── */

let activeSource = '0';

window.selectSource = function(el, src) {
  document.querySelectorAll('.src-btn').forEach(b => b.classList.remove('active'));
  el.classList.add('active');
  activeSource = src;
  
  const badge = document.getElementById('srcBadge');
  if (badge) {
    badge.textContent = src === 'phone' ? 'ip-stream' : `channel:${src}`;
  }
  
  const ir = document.getElementById('ipRow');
  const pg = document.getElementById('phoneGuide');
  
  if (src === 'phone') {
    if (ir) ir.style.display = 'flex';
    if (pg) pg.style.display = 'block';
  } else {
    if (ir) ir.style.display = 'none';
    if (pg) pg.style.display = 'none';
    sendSource(src);
  }
};

window.applyIP = function() {
  const input = document.getElementById('ipInput');
  if (!input) return;
  const u = input.value.trim();
  if (!u) {
    alert('Please enter a valid camera stream URL.');
    return;
  }
  
  const badge = document.getElementById('srcBadge');
  if (badge) {
    badge.textContent = 'ip-stream';
  }
  sendSource(u);
};

function sendSource(src) {
  if (typeof window.toast === 'function') {
    window.toast('Connecting to camera...', 'warn');
  }
  fetch('/api/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ source: String(src) })
  }).then(r => r.json()).then(data => {
    if (typeof window.toast === 'function') {
      window.toast('Connected! Launching monitor...');
    }
    setTimeout(() => {
      window.location.href = "/detect";
    }, 800);
  }).catch(() => {
    if (typeof window.toast === 'function') {
      window.toast('Failed to connect to input source', 'err');
    }
  });
}

// ─── Stats polling ───
function fetchStats() {
  fetch('/api/stats')
    .then(r => r.json())
    .then(d => {
      const on = d.cap_ok;
      
      const ring = document.getElementById('statusRing');
      if (ring) ring.className = 'status-ring ' + (on ? 'on' : 'off');
      
      const hero = document.getElementById('heroStatus');
      if (hero) hero.textContent = on ? 'System Active' : 'System Ready';
      
      const lbl = document.getElementById('statusLabel');
      if (lbl) lbl.textContent = on ? 'Connected' : 'Camera Off';
      
      const fps = document.getElementById('sFps');
      if (fps) fps.textContent = d.fps > 0 ? d.fps + ' fps' : '—';
      
      const inf = document.getElementById('sInf');
      if (inf) inf.textContent = d.inf_ms > 0 ? d.inf_ms + ' ms' : '—';
      
      const cam = document.getElementById('sCamVal');
      if (cam) {
        cam.textContent = on ? 'Live ●' : 'Idle';
        cam.style.color = on ? 'var(--green)' : 'var(--text3)';
      }
      
      const pill = document.getElementById('confPill');
      if (pill && d.conf !== undefined) {
        pill.textContent = `CONF: ${d.conf.toFixed(2)}`;
      }
    })
    .catch(() => {
      const ring = document.getElementById('statusRing');
      if (ring) ring.className = 'status-ring off';
      
      const hero = document.getElementById('heroStatus');
      if (hero) hero.textContent = 'System Ready';
      
      const lbl = document.getElementById('statusLabel');
      if (lbl) lbl.textContent = 'Camera Off';
      
      const cam = document.getElementById('sCamVal');
      if (cam) {
        cam.textContent = 'Idle';
        cam.style.color = 'var(--text3)';
      }
    });
}

// Start polling
setInterval(fetchStats, 1800);
fetchStats();


// ─── Card 3D Tilt Parallax Effect ───
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.card, .src-btn, .status-widget').forEach(card => {
    card.addEventListener('mousemove', e => {
      const r = card.getBoundingClientRect();
      const x = (e.clientX - r.left) / r.width - 0.5;
      const y = (e.clientY - r.top) / r.height - 0.5;
      card.style.transform = `perspective(800px) rotateY(${(x * 4.5).toFixed(2)}deg) rotateX(${(-y * 4.5).toFixed(2)}deg) translateZ(4px)`;
      card.style.transition = 'transform 0.05s ease';
    });
    
    card.addEventListener('mouseleave', () => {
      card.style.transform = '';
      card.style.transition = 'transform 0.3s ease';
    });
  });
});
