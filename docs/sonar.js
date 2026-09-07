/* A dot field that answers pings with expanding rings.
 *
 * Ported from a React/Tailwind component to plain canvas. React contributed
 * nothing to what this draws, and the page it lives in has no build step, no
 * bundler and no dependencies on purpose: the verification code on this page
 * can be read in view-source and cannot be swapped underneath a viewer. That
 * property is worth more than a framework.
 *
 * Idles when no ring is alive, pauses off-screen and in hidden tabs, and draws
 * a still grid when the viewer has asked for reduced motion.
 */
(function () {
  "use strict";

  const TAU = Math.PI * 2;
  const MAX_DPR = 2;

  function mount(host, options) {
    const o = Object.assign({
      spacing: 30,
      dotRadius: 1.3,
      baseOpacity: 0.16,
      color: "#bcff2f",
      pingEvery: 3.2,
      speed: 240,
      ringWidth: 100,
      amplitude: 2.4,
      interactive: true,
      maxRings: 5,
      pingArea: [0.15, 0.2, 0.85, 0.8],
    }, options || {});

    const canvas = document.createElement("canvas");
    canvas.setAttribute("aria-hidden", "true");
    canvas.style.cssText =
      "position:absolute;inset:0;width:100%;height:100%;pointer-events:none;z-index:0";
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    if (getComputedStyle(host).position === "static") host.style.position = "relative";
    host.insertBefore(canvas, host.firstChild);
    // Everything already in the host must sit above the field.
    for (const child of host.children) {
      if (child === canvas) continue;
      if (getComputedStyle(child).position === "static") child.style.position = "relative";
      if (!child.style.zIndex) child.style.zIndex = "1";
    }

    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)");
    let rings = [];
    let width = 0, height = 0, raf = 0, timer = 0, visible = true, seeded = false;
    let nextPing = performance.now() + o.pingEvery * 1000;

    function addRing(x, y, born) {
      rings.push({ x, y, born });
      while (rings.length > o.maxRings) rings.shift();
    }

    function draw(now) {
      // How long a ring takes to leave the canvas entirely.
      const lifetime = (Math.hypot(width, height) + o.ringWidth) / o.speed;
      rings = rings.filter((r) => (now - r.born) / 1000 < lifetime);
      const live = rings.map((r) => {
        const age = (now - r.born) / 1000;
        const radius = age * o.speed;
        return { x: r.x, y: r.y, radius, reach: radius + o.ringWidth, fade: 1 - age / lifetime };
      });

      ctx.clearRect(0, 0, width, height);
      ctx.fillStyle = o.color;

      const cols = Math.ceil(width / o.spacing) + 1;
      const rows = Math.ceil(height / o.spacing) + 1;
      const offsetX = (width - (cols - 1) * o.spacing) / 2;
      const offsetY = (height - (rows - 1) * o.spacing) / 2;

      // Pass one: every resting dot in a single path and a single fill.
      const hot = [];
      ctx.globalAlpha = o.baseOpacity;
      ctx.beginPath();
      for (let i = 0; i < cols; i++) {
        const cx = offsetX + i * o.spacing;
        for (let j = 0; j < rows; j++) {
          const cy = offsetY + j * o.spacing;
          let energy = 0;
          for (const r of live) {
            // Cheap rejection before the expensive hypot.
            if (Math.abs(cx - r.x) > r.reach || Math.abs(cy - r.y) > r.reach) continue;
            const dist = Math.abs(Math.hypot(cx - r.x, cy - r.y) - r.radius);
            if (dist >= o.ringWidth) continue;
            const t = 1 - dist / o.ringWidth;
            const k = t * t * (3 - 2 * t) * r.fade; // smoothstep, fading with age
            if (k > energy) energy = k;
          }
          if (energy < 0.01) {
            ctx.moveTo(cx + o.dotRadius, cy);
            ctx.arc(cx, cy, o.dotRadius, 0, TAU);
          } else {
            hot.push(cx, cy, energy);
          }
        }
      }
      ctx.fill();

      // Pass two: only dots on a wavefront need their own alpha and radius.
      for (let k = 0; k < hot.length; k += 3) {
        const energy = hot[k + 2];
        ctx.globalAlpha = o.baseOpacity + (1 - o.baseOpacity) * energy;
        ctx.beginPath();
        ctx.arc(hot[k], hot[k + 1], o.dotRadius * (1 + o.amplitude * energy), 0, TAU);
        ctx.fill();
      }
      ctx.globalAlpha = 1;
    }

    function resize() {
      const rect = host.getBoundingClientRect();
      width = Math.max(1, Math.round(rect.width));
      height = Math.max(1, Math.round(rect.height));
      const dpr = Math.min(window.devicePixelRatio || 1, MAX_DPR);
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      if (!seeded) {
        seeded = true;
        const a = o.pingArea;
        if (!reduce.matches) {
          // One ring already mid-flight, so the first paint shows the idea.
          addRing(width * (a[0] + (a[2] - a[0]) * 0.68),
                  height * (a[1] + (a[3] - a[1]) * 0.34),
                  performance.now() - 500);
        }
      }
      draw(performance.now());
    }

    function tick(now) {
      raf = 0;
      if (!visible || document.hidden) return;
      if (reduce.matches) { rings = []; draw(now); return; }
      if (o.pingEvery > 0 && now >= nextPing) {
        const a = o.pingArea;
        addRing(width * (a[0] + Math.random() * (a[2] - a[0])),
                height * (a[1] + Math.random() * (a[3] - a[1])), now);
        nextPing = now + o.pingEvery * 1000;
      }
      draw(now);
      if (rings.length > 0) {
        raf = requestAnimationFrame(tick);
      } else if (o.pingEvery > 0) {
        // Nothing moving: sleep until the next ping instead of burning frames.
        window.clearTimeout(timer);
        timer = window.setTimeout(() => tick(performance.now()), Math.max(16, nextPing - now));
      }
    }

    function wake() {
      if (!raf) { window.clearTimeout(timer); raf = requestAnimationFrame(tick); }
    }

    new ResizeObserver(resize).observe(host);
    new IntersectionObserver((entries) => {
      visible = entries[0] ? entries[0].isIntersecting : true;
      if (visible) wake();
    }, { threshold: 0 }).observe(host);

    if (o.interactive) {
      host.addEventListener("pointerdown", (e) => {
        if (reduce.matches) return;
        const rect = host.getBoundingClientRect();
        addRing(e.clientX - rect.left, e.clientY - rect.top, performance.now());
        wake();
      });
    }
    document.addEventListener("visibilitychange", () => { if (!document.hidden) wake(); });
    reduce.addEventListener("change", wake);

    resize();
    wake();
  }

  window.mountSonarGrid = mount;
})();
