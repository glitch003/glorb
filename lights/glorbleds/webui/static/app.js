"use strict";

// ---- 2D flat-view constants ----
const BRISTLE = 110, STEPV = 8, STEPH = 8, MARGIN = 26, PX = 4;

// ---- 3D car geometry (metres) ----
const CAR = { W: 1.8, L: 4.0, H: 3.0 };   // width(X) × length(Y) × body height(Z)
const TUBE_TOP = 2.7, TUBE_LEN = 2.5;      // tubes hang from Z=2.7 down 2.5 m

let layout = null;      // from /layout
let frame = null;       // Uint8Array of current RGB frame
let view = "3d";
let logicalW = 1000, logicalH = 640;

let tube2d = [];        // per-tube {x0,y0,dx,dy,base}
let tubes3d = [];       // per-tube {x,y,base}
let wx, wy, wz;         // per-pixel world coords (Float32Array)

let yaw = -0.7, pitch = 0.34;   // 3D orbit camera

const canvas = document.getElementById("car");
const ctx = canvas.getContext("2d");

async function init() {
  layout = await (await fetch("layout")).json();
  document.getElementById("pxcount").textContent = layout.total_pixels;
  buildGeometry3D();
  buildGeometry2D();
  setView("3d");
  await loadState();
  wireControls();
  wireView();
  openStream();
  requestAnimationFrame(draw);
  setInterval(pollFps, 1000);
}

function sizeCanvas(w, h) {
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = Math.round(w * dpr);
  canvas.height = Math.round(h * dpr);
  canvas.style.aspectRatio = w + " / " + h;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  logicalW = w; logicalH = h;
}

// ---------------------------------------------------------------- 3D geometry
function buildGeometry3D() {
  const s = layout.sides, ppt = layout.px_per_tube, n = layout.total_pixels;
  wx = new Float32Array(n); wy = new Float32Array(n); wz = new Float32Array(n);
  tubes3d = [];
  const hw = CAR.W / 2, hl = CAR.L / 2;
  const cnt = { L: 0, B: 0, R: 0 };
  layout.tubes.forEach((t, ti) => {
    const c = cnt[t.side]++;
    let x, y;
    if (t.side === "L") { x = -hw; y = -hl + (c + 0.5) / s.L * CAR.L; }
    else if (t.side === "R") { x = hw; y = hl - (c + 0.5) / s.R * CAR.L; }
    else { x = -hw + (c + 0.5) / s.B * CAR.W; y = hl; }   // rear
    const base = ti * ppt;
    tubes3d.push({ x, y, base });
    for (let j = 0; j < ppt; j++) {
      const i = base + j;
      wx[i] = x; wy[i] = y;
      wz[i] = TUBE_TOP - (j / (ppt - 1)) * TUBE_LEN;
    }
  });
}

function makeProjector() {
  const w = logicalW, h = logicalH;
  const cx = w * 0.5, cy = h * 0.54;
  const focal = h * 1.25, camDist = 9.5;
  const cY = Math.cos(yaw), sY = Math.sin(yaw);
  const cP = Math.cos(pitch), sP = Math.sin(pitch);
  return function (x, y, z) {
    const rx = x * cY - y * sY;
    const ry = x * sY + y * cY;
    const ry2 = ry * cP - z * sP;
    const rz2 = ry * sP + z * cP;
    const depth = ry2 + camDist;
    const f = focal / depth;
    return [cx + rx * f, cy - rz2 * f, depth, f];
  };
}

function draw3d() {
  const w = logicalW, h = logicalH;
  ctx.globalCompositeOperation = "source-over";
  ctx.globalAlpha = 1;
  ctx.fillStyle = "#05080c";
  ctx.fillRect(0, 0, w, h);

  const proj = makeProjector();
  drawBody(proj);

  ctx.fillStyle = "#3d4f63";
  ctx.font = "12px sans-serif"; ctx.textAlign = "center";
  ctx.fillText("front-left open (driver sightline)", w / 2, h - 12);

  const ppt = layout.px_per_tube;

  // faint tube backbones (structure even when dark)
  ctx.globalCompositeOperation = "source-over";
  ctx.strokeStyle = "rgba(40,55,72,0.5)";
  ctx.lineWidth = 1;
  for (const tb of tubes3d) {
    const a = proj(tb.x, tb.y, TUBE_TOP);
    const b = proj(tb.x, tb.y, TUBE_TOP - TUBE_LEN);
    ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.stroke();
  }

  // lit pixels, far tubes first so near ones layer on top
  const order = tubes3d.map((tb, i) => [i, proj(tb.x, tb.y, TUBE_TOP - TUBE_LEN / 2)[2]]);
  order.sort((p, q) => q[1] - p[1]);

  ctx.globalCompositeOperation = "lighter";
  for (const [ti] of order) {
    const tb = tubes3d[ti];
    let bi = tb.base * 3;
    for (let j = 0; j < ppt; j++, bi += 3) {
      const r = frame ? frame[bi] : 0, gg = frame ? frame[bi + 1] : 0, b = frame ? frame[bi + 2] : 0;
      if (r + gg + b < 10) continue;
      const i = tb.base + j;
      const P = proj(wx[i], wy[i], wz[i]);
      const dim = Math.max(0.4, Math.min(1, (14 - P[2]) / 7));
      const sz = Math.max(1.4, Math.min(6, P[3] * 0.022));
      ctx.globalAlpha = dim;
      ctx.fillStyle = "rgb(" + r + "," + gg + "," + b + ")";
      ctx.fillRect(P[0] - sz / 2, P[1] - sz / 2, sz, sz);
    }
  }
  ctx.globalAlpha = 1;
}

function drawBody(proj) {
  const hw = CAR.W / 2, hl = CAR.L / 2, H = CAR.H;
  const c = [
    [-hw, -hl, 0], [hw, -hl, 0], [hw, hl, 0], [-hw, hl, 0],
    [-hw, -hl, H], [hw, -hl, H], [hw, hl, H], [-hw, hl, H],
  ].map((p) => proj(p[0], p[1], p[2]));

  const faces = [
    [0, 3, 7, 4], // left
    [1, 2, 6, 5], // right
    [3, 2, 6, 7], // rear
    [0, 1, 5, 4], // front
    [4, 5, 6, 7], // top
  ];
  const withDepth = faces.map((f) => {
    const d = (c[f[0]][2] + c[f[1]][2] + c[f[2]][2] + c[f[3]][2]) / 4;
    return [f, d];
  });
  withDepth.sort((a, b) => b[1] - a[1]);

  ctx.globalCompositeOperation = "source-over";
  ctx.globalAlpha = 1;
  for (const [f] of withDepth) {
    ctx.beginPath();
    ctx.moveTo(c[f[0]][0], c[f[0]][1]);
    for (let k = 1; k < f.length; k++) ctx.lineTo(c[f[k]][0], c[f[k]][1]);
    ctx.closePath();
    ctx.fillStyle = "rgba(13,20,31,0.9)";
    ctx.fill();
    ctx.strokeStyle = "rgba(44,62,82,0.9)";
    ctx.lineWidth = 1.2;
    ctx.stroke();
  }

  // roof rail (scaffolding on top deck)
  const rt = [[-hw, -hl, H + 0.35], [hw, -hl, H + 0.35],
              [hw, hl, H + 0.35], [-hw, hl, H + 0.35]].map((p) => proj(p[0], p[1], p[2]));
  ctx.strokeStyle = "rgba(70,90,112,0.85)";
  ctx.lineWidth = 1.4;
  ctx.beginPath();
  ctx.moveTo(rt[0][0], rt[0][1]);
  for (let k = 1; k < 4; k++) ctx.lineTo(rt[k][0], rt[k][1]);
  ctx.closePath();
  ctx.stroke();
  for (let k = 0; k < 4; k++) {
    ctx.beginPath();
    ctx.moveTo(c[4 + k][0], c[4 + k][1]);
    ctx.lineTo(rt[k][0], rt[k][1]);
    ctx.stroke();
  }
}

// ---------------------------------------------------------------- 2D geometry
function buildGeometry2D() {
  const s = layout.sides, ppt = layout.px_per_tube;
  const Hside = STEPV * Math.max(s.L, s.R);
  const Wback = STEPH * s.B;
  const LX = MARGIN + BRISTLE, RX = LX + Wback;
  const TY = MARGIN, BY = TY + Hside;
  const W = RX + BRISTLE + MARGIN, H = BY + BRISTLE + MARGIN;

  const step = { L: 0, B: 0, R: 0 };
  const spacing = BRISTLE / (ppt - 1);
  tube2d = layout.tubes.map((t, ti) => {
    const c = step[t.side]++;
    let x0, y0, dx = 0, dy = 0;
    if (t.side === "L") { x0 = LX; y0 = TY + (c + 0.5) * STEPV; dx = -spacing; }
    else if (t.side === "R") { x0 = RX; y0 = BY - (c + 0.5) * STEPV; dx = spacing; }
    else { x0 = LX + (c + 0.5) * STEPH; y0 = BY; dy = spacing; }
    return { x0, y0, dx, dy, base: ti * ppt, W, H };
  });
  return { W, H };
}

function draw2d() {
  const w = logicalW, h = logicalH;
  ctx.globalCompositeOperation = "source-over";
  ctx.globalAlpha = 1;
  ctx.fillStyle = "#05080c";
  ctx.fillRect(0, 0, w, h);

  ctx.fillStyle = "#3d4f63";
  ctx.font = "12px sans-serif"; ctx.textAlign = "center";
  ctx.fillText("FRONT (open)", w / 2, 18);

  if (frame) {
    ctx.globalCompositeOperation = "lighter";
    const ppt = layout.px_per_tube;
    for (const g of tube2d) {
      let bi = g.base * 3;
      for (let j = 0; j < ppt; j++, bi += 3) {
        const r = frame[bi], gg = frame[bi + 1], b = frame[bi + 2];
        if (r + gg + b < 10) continue;
        ctx.fillStyle = "rgb(" + r + "," + gg + "," + b + ")";
        const x = g.x0 + g.dx * j, y = g.y0 + g.dy * j;
        ctx.fillRect(x - PX / 2, y - PX / 2, PX, PX);
      }
    }
  }
}

function draw() {
  if (view === "3d") draw3d(); else draw2d();
  requestAnimationFrame(draw);
}

// ---------------------------------------------------------------- view switch
function setView(v) {
  view = v;
  if (v === "3d") sizeCanvas(1000, 640);
  else { const d = buildGeometry2D(); sizeCanvas(d.W, d.H); }
  document.getElementById("view3d").classList.toggle("active", v === "3d");
  document.getElementById("view2d").classList.toggle("active", v === "2d");
  document.getElementById("hint").textContent = v === "3d"
    ? "3D view — drag to orbit. Tubes hang around 3 sides; front-left open for the driver."
    : "2D flat view — bristles unrolled from the U. Front (top) is open.";
}

function wireView() {
  document.getElementById("view3d").onclick = () => setView("3d");
  document.getElementById("view2d").onclick = () => setView("2d");

  let dragging = false, lx = 0, ly = 0;
  canvas.addEventListener("pointerdown", (e) => {
    if (view !== "3d") return;
    dragging = true; lx = e.clientX; ly = e.clientY;
    canvas.setPointerCapture(e.pointerId);
  });
  canvas.addEventListener("pointermove", (e) => {
    if (!dragging) return;
    yaw += (e.clientX - lx) * 0.01;
    pitch = Math.max(-0.1, Math.min(0.9, pitch + (e.clientY - ly) * 0.01));
    lx = e.clientX; ly = e.clientY;
  });
  const stop = () => { dragging = false; };
  canvas.addEventListener("pointerup", stop);
  canvas.addEventListener("pointercancel", stop);
}

// ---- controls ----
function post(update) {
  fetch("control", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(update),
  });
}
function hexToRgb(h) {
  return [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16)];
}
function rgbToHex(c) {
  return "#" + c.map((v) => v.toString(16).padStart(2, "0")).join("");
}

async function loadState() {
  const st = await (await fetch("state")).json();
  const pc = document.getElementById("patterns");
  pc.innerHTML = "";
  st.patterns.forEach((name) => {
    const b = document.createElement("button");
    b.textContent = name; b.dataset.name = name;
    b.onclick = () => { setPattern(name); post({ pattern: name }); };
    pc.appendChild(b);
  });
  applyState(st);
}
function applyState(st) {
  const p = st.params;
  setPattern(p.pattern);
  setSlider("brightness", Math.round(p.brightness * 100));
  setSlider("speed", Math.round(p.speed * 100));
  setSlider("density", Math.round(p.density * 100));
  document.getElementById("color1").value = rgbToHex(p.color1);
  document.getElementById("color2").value = rgbToHex(p.color2);
  document.getElementById("hwEnabled").checked = st.hardware.enabled;
  document.getElementById("hwHost").value = st.hardware.host || "";
  document.getElementById("hwOrder").value = st.hardware.color_order || "RGB";
  updateHwStatus(st.hardware, st.fps);
}
function setPattern(name) {
  document.querySelectorAll("#patterns button").forEach((b) =>
    b.classList.toggle("active", b.dataset.name === name));
}
function setSlider(id, val) {
  document.getElementById(id).value = val;
  document.getElementById(id + "Out").textContent = val + "%";
}

let throttle = 0;
function slider(id, key) {
  const el = document.getElementById(id);
  el.addEventListener("input", () => {
    document.getElementById(id + "Out").textContent = el.value + "%";
    const now = Date.now();
    if (now - throttle < 60) return;
    throttle = now;
    post({ [key]: el.value / 100 });
  });
  el.addEventListener("change", () => post({ [key]: el.value / 100 }));
}

function wireControls() {
  slider("brightness", "brightness");
  slider("speed", "speed");
  slider("density", "density");
  document.getElementById("color1").addEventListener("input", (e) =>
    post({ color1: hexToRgb(e.target.value) }));
  document.getElementById("color2").addEventListener("input", (e) =>
    post({ color2: hexToRgb(e.target.value) }));
  ["hwEnabled", "hwHost", "hwOrder"].forEach((id) =>
    document.getElementById(id).addEventListener("change", sendHw));
}
function sendHw() {
  post({ hardware: {
    enabled: document.getElementById("hwEnabled").checked,
    host: document.getElementById("hwHost").value.trim() || null,
    color_order: document.getElementById("hwOrder").value,
  }});
  setTimeout(pollFps, 150);
}
function updateHwStatus(hw, fps) {
  const el = document.getElementById("hwStatus");
  el.className = "hwstatus";
  if (hw.error) { el.textContent = "error: " + hw.error; el.classList.add("err"); }
  else if (hw.enabled) {
    el.textContent = "sending → " + (hw.host || "multicast") + " (" + hw.color_order + ")";
    el.classList.add("on");
  } else el.textContent = "hardware off";
}
async function pollFps() {
  try {
    const st = await (await fetch("state")).json();
    document.getElementById("fps").textContent = st.fps;
    updateHwStatus(st.hardware, st.fps);
  } catch (_) {}
}

function openStream() {
  const es = new EventSource("stream");
  es.onmessage = (e) => {
    const bin = atob(e.data);
    if (!frame || frame.length !== bin.length) frame = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) frame[i] = bin.charCodeAt(i);
  };
  es.onerror = () => {/* EventSource auto-reconnects */};
}

init();
