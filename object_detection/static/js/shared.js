/* ─── VisionIQ Shared JS Library ─── */

// ─── Theme Management (Dark/Light Mode) ───
(function() {
  const savedTheme = localStorage.getItem('visioniq-theme');
  const systemPrefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  
  if (savedTheme === 'dark' || (!savedTheme && systemPrefersDark)) {
    document.documentElement.setAttribute('data-theme', 'dark');
  } else {
    document.documentElement.setAttribute('data-theme', 'light');
  }
})();

window.toggleTheme = function() {
  const currentTheme = document.documentElement.getAttribute('data-theme');
  const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', newTheme);
  localStorage.setItem('visioniq-theme', newTheme);
  updateThemeToggleIcon();
  
  // Custom toast notification if toast function is loaded
  if (typeof window.toast === 'function') {
    window.toast(`Switched to ${newTheme} mode`);
  }
};

function updateThemeToggleIcon() {
  const btn = document.getElementById('themeToggle');
  if (!btn) return;
  const currentTheme = document.documentElement.getAttribute('data-theme');
  btn.innerHTML = currentTheme === 'dark'
    ? '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>'
    : '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
}

// Ensure toggle button icon aligns on page load
document.addEventListener('DOMContentLoaded', updateThemeToggleIcon);


// ─── Particles connection network ───
(function() {
  const c = document.getElementById('particles');
  if (!c) return;
  const ctx = c.getContext('2d');
  let W, H, pts;
  
  // Track mouse for particle interaction
  let mouseX = null, mouseY = null;
  document.addEventListener('mousemove', e => {
    mouseX = e.clientX;
    mouseY = e.clientY;
  });
  document.addEventListener('mouseleave', () => {
    mouseX = null;
    mouseY = null;
  });

  function resize() {
    W = c.width = window.innerWidth;
    H = c.height = window.innerHeight;
    init();
  }

  function init() {
    const density = (W * H) / 22000;
    pts = Array.from({ length: Math.floor(density) }, () => ({
      x: Math.random() * W,
      y: Math.random() * H,
      vx: (Math.random() - .5) * .32,
      vy: (Math.random() - .5) * .32,
      r: Math.random() * 1.8 + .5
    }));
  }

  function draw() {
    ctx.clearRect(0, 0, W, H);
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    const fillStyle = isDark ? 'rgba(59,130,246,.25)' : 'rgba(37,99,235,.16)';
    const strokeRgb = isDark ? '59,130,246' : '37,99,235';

    pts.forEach(p => {
      p.x += p.vx;
      p.y += p.vy;
      if (p.x < 0) p.x = W;
      if (p.x > W) p.x = 0;
      if (p.y < 0) p.y = H;
      if (p.y > H) p.y = 0;
      
      // Dynamic attraction if mouse is near
      if (mouseX !== null && mouseY !== null) {
        const dx = mouseX - p.x;
        const dy = mouseY - p.y;
        const d = Math.sqrt(dx * dx + dy * dy);
        if (d < 180) {
          p.x += dx * 0.005;
          p.y += dy * 0.005;
        }
      }

      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fillStyle = fillStyle;
      ctx.fill();
    });

    for (let i = 0; i < pts.length; i++) {
      for (let j = i + 1; j < pts.length; j++) {
        const dx = pts[i].x - pts[j].x;
        const dy = pts[i].y - pts[j].y;
        const d = Math.sqrt(dx * dx + dy * dy);
        if (d < 110) {
          ctx.beginPath();
          ctx.moveTo(pts[i].x, pts[i].y);
          ctx.lineTo(pts[j].x, pts[j].y);
          ctx.strokeStyle = `rgba(${strokeRgb}, ${.08 * (1 - d / 110)})`;
          ctx.lineWidth = .75;
          ctx.stroke();
        }
      }
    }
    requestAnimationFrame(draw);
  }

  window.addEventListener('resize', resize);
  resize();
  draw();
})();


// ─── Global Cursor Ambient Glow Aura ───
(function() {
  const glow = document.createElement('div');
  glow.style.cssText = 'position:fixed;width:400px;height:400px;border-radius:50%;pointer-events:none;z-index:0;transition:transform 0.08s cubic-bezier(0.2, 0.8, 0.2, 1);transform:translate(-50%,-50%);opacity:0.85;';
  
  // Set theme dynamic gradient
  function updateGlowStyle() {
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    glow.style.background = isDark
      ? 'radial-gradient(circle, rgba(59, 130, 246, 0.055) 0%, transparent 70%)'
      : 'radial-gradient(circle, rgba(37, 99, 235, 0.045) 0%, transparent 70%)';
  }
  
  updateGlowStyle();
  document.body.appendChild(glow);
  
  document.addEventListener('mousemove', e => {
    glow.style.left = e.clientX + 'px';
    glow.style.top = e.clientY + 'px';
  });
  
  // Keep theme updated when switched
  const observer = new MutationObserver(updateGlowStyle);
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
})();
