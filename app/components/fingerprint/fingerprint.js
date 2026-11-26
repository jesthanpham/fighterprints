// Fingerprint renderer: turns one fighter's stats + fight history into a generated, inked fingerprint.
// Ported from spike/fingerprint-spike.html. The algorithm and constants are unchanged; only the inputs
// now come from the pipeline's marts (fighter_print_params + fighter_fight_timeline).
//
// How a print is grown:
//   1. A ridge-direction field from "cores" and "deltas" (Sherlock-Monro model). Their layout = pattern type.
//   2. Seeded random noise, filtered ~12 times with oriented Gabor filters along that field. Ridges grow
//      out of the noise with natural splits and endings.
//   3. Inking: pressure, wear, pores, rough edges, creases, edge falloff.

// ---------------- helpers ----------------
export function hashStr(s) {
  let h = 2166136261;
  for (const c of String(s)) { h ^= c.charCodeAt(0); h = Math.imul(h, 16777619); }
  return h >>> 0;
}
function rng32(a) {
  return () => {
    a |= 0; a = a + 0x6D2B79F5 | 0;
    let t = Math.imul(a ^ a >>> 15, 1 | a);
    t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
    return ((t ^ t >>> 14) >>> 0) / 4294967296;
  };
}
function makeNoise(rand) {
  const N = 64, g = new Float32Array(N * N);
  for (let i = 0; i < g.length; i++) g[i] = rand() * 2 - 1;
  const at = (i, j) => g[(j & 63) * N + (i & 63)];
  const sm = t => t * t * (3 - 2 * t);
  return (x, y) => {
    const i = Math.floor(x), j = Math.floor(y), fx = sm(x - i), fy = sm(y - j);
    const a = at(i, j), b = at(i + 1, j), c = at(i, j + 1), d = at(i + 1, j + 1);
    return a + (b - a) * fx + (c - a) * fy + (a - b - c + d) * fx * fy;
  };
}
const clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));
const smooth = (e0, e1, x) => { const t = clamp((x - e0) / (e1 - e0)); return t * t * (3 - 2 * t); };
const lerp = (a, b, t) => a + (b - a) * t;

// ---------------- stats -> print knobs ----------------
export const PATTERNS = {
  Striker: "whorl", Wrestler: "loop", Grappler: "double_loop", Brawler: "tented_arch", Balanced: "plain_arch",
};
export const DEFAULTS = { reach_in: 72, stance: "Orthodox", pace: 3.5, absorbed: 3.0, head_pct: 0.6 };

/** Decide every visual knob from the fighter's stats. Pure; the tests pin this. */
export function printPlan(params, fights) {
  const flags = [];
  let reach = params.reach_in;
  if (reach == null || !Number.isFinite(Number(reach))) { reach = DEFAULTS.reach_in; flags.push("reach_missing"); }
  let stance = params.stance;
  if (!["Orthodox", "Southpaw", "Switch"].includes(stance)) { stance = DEFAULTS.stance; flags.push("stance_missing"); }
  let pace = params.sig_landed_per_min, absorbed = params.sig_absorbed_per_min;
  if (pace == null || absorbed == null) {
    pace = pace ?? DEFAULTS.pace; absorbed = absorbed ?? DEFAULTS.absorbed; flags.push("no_stats");
  }
  const head = params.head_pct ?? DEFAULTS.head_pct;
  return {
    pattern: PATTERNS[params.archetype] ?? "plain_arch",
    spacing: lerp(7.4, 5.0, clamp((Number(pace) - 1) / 7)),
    pressure: clamp(Number(params.finish_rate ?? 0)),
    wear: clamp((Number(absorbed) - 1) / 6),
    size: lerp(0.84, 1.04, clamp((Number(reach) - 64) / 20)),
    mirror: stance === "Southpaw",
    tilt: stance === "Switch" ? 0 : -0.14,
    coreShift: lerp(16, -16, clamp((Number(head) * 100 - 30) / 60)),
    creaseCount: Math.max(0, Math.round(Number(params.ko_losses ?? 0))),
    markCount: fights.length,
    seed: String(params.fighter_id),
    flags,
  };
}

// ---------------- ridge growth ----------------
const GW = 200, GH = 250, SCALE = 4; // simulation grid, upscaled 4x so large prints stay sharp

function grow(plan, rand) {
  const { spacing } = plan;
  const freq = 1 / spacing;
  const cx = GW / 2 + (rand() - 0.5) * 6;
  const cy = GH * 0.5 + plan.coreShift;
  const jit = () => (rand() - 0.5) * 6;

  let cores = [], deltas = [], arch = false;
  switch (plan.pattern) {
    case "whorl":       cores = [[cx + jit(), cy - 6], [cx + jit(), cy + 6]]; deltas = [[cx - 78, cy + 64], [cx + 78, cy + 66]]; break;
    case "double_loop": cores = [[cx - 11, cy - 9], [cx + 11, cy + 9]];       deltas = [[cx - 80, cy + 58], [cx + 74, cy + 70]]; break;
    case "loop":        cores = [[cx + 10 + jit(), cy - 10]];                 deltas = [[cx - 56, cy + 56]]; break;
    case "tented_arch": cores = [[cx, cy - 8]];                                deltas = [[cx, cy + 26]]; break;
    default: arch = true;
  }

  // orientation field, quantised into NB bins
  const NB = 64, bin = new Uint8Array(GW * GH);
  for (let y = 0; y < GH; y++) for (let x = 0; x < GW; x++) {
    let t;
    if (arch) {
      const dx = x - cx, A = lerp(44, 12, clamp(y / GH)), sg = 46;
      t = Math.atan(A * dx / (sg * sg) * Math.exp(-dx * dx / (2 * sg * sg)));
    } else {
      t = 0;
      for (const [px, py] of cores) t += Math.atan2(y - py, x - px);
      for (const [px, py] of deltas) t -= Math.atan2(y - py, x - px);
      t *= 0.5;
    }
    t = ((t % Math.PI) + Math.PI) % Math.PI;
    bin[y * GW + x] = Math.floor(t / Math.PI * NB) % NB;
  }

  // Gabor kernels per orientation bin
  const R = Math.ceil(spacing * 1.25), PW = GW + 2 * R, PH = GH + 2 * R;
  const sn = spacing * 0.42, st = spacing * 0.62;
  const OFF = [], WT = [];
  for (let b = 0; b < NB; b++) {
    const th = (b + 0.5) / NB * Math.PI, c = Math.cos(th), s = Math.sin(th);
    const offs = [], ws = []; let norm = 0;
    for (let dy = -R; dy <= R; dy++) for (let dx = -R; dx <= R; dx++) {
      const along = dx * c + dy * s, across = -dx * s + dy * c;
      const g = Math.exp(-(along * along) / (2 * st * st) - (across * across) / (2 * sn * sn));
      if (g < 0.02) continue;
      const wave = Math.cos(2 * Math.PI * freq * across);
      offs.push(dy * PW + dx); ws.push(g * wave); norm += g * wave * wave;
    }
    OFF.push(Int32Array.from(offs)); WT.push(Float32Array.from(ws.map(v => v / norm)));
  }

  // one minutia per fight, spiralling out from the core like tree rings
  const rx = GW * 0.40, ry = GH * 0.42, n = plan.markCount;
  const minutiae = [];
  for (let i = 0; i < n; i++) {
    const r = n > 1 ? 0.12 + 0.78 * Math.sqrt(i / (n - 1)) : 0.3, a = i * 2.39996 + rand() * 0.4;
    minutiae.push({ i, x: clamp(cx + Math.cos(a) * rx * r, 4, GW - 5), y: clamp(cy + Math.sin(a) * ry * r, 4, GH - 5) });
  }

  // grow ridges out of noise
  let I = new Float32Array(PW * PH), J = new Float32Array(PW * PH);
  for (let y = 0; y < GH; y++) for (let x = 0; x < GW; x++) I[(y + R) * PW + x + R] = rand() * 2 - 1;
  for (let it = 0; it < 12; it++) {
    if (it === 6) for (const m of minutiae) { // seed a ridge defect at every fight
      const th = (bin[(m.y | 0) * GW + (m.x | 0)] + 0.5) / NB * Math.PI, c = Math.cos(th), s = Math.sin(th);
      for (let dy = -4; dy <= 4; dy++) for (let dx = -4; dx <= 4; dx++) {
        if (dx * dx + dy * dy > 16) continue;
        const p = ((m.y | 0) + dy + R) * PW + (m.x | 0) + dx + R;
        if (dx * c + dy * s > 0) I[p] = -I[p];
      }
    }
    for (let y = 0; y < GH; y++) {
      const row = (y + R) * PW + R;
      for (let x = 0; x < GW; x++) {
        const p = row + x, b = bin[y * GW + x], o = OFF[b], w = WT[b];
        let acc = 0;
        for (let k = 0; k < o.length; k++) acc += w[k] * I[p + o[k]];
        J[p] = clamp(acc * 1.7, -1, 1);
      }
    }
    [I, J] = [J, I];
  }
  return { I, PW, R, minutiae };
}

// ---------------- stroke tracing (for the pen-drawing animation) ----------------
// Marching squares: follow every place the field crosses `level`, then chain the little segments into
// continuous lines. On the ridge field, those lines are the ridge edges, so the pen traces real ridges.
export function traceContours(field, w, h, level, inside = () => true) {
  const pts = new Map(), adj = new Map();
  const point = (key, x0, y0, v0, x1, y1, v1) => {
    if (!pts.has(key)) { const t = (level - v0) / (v1 - v0); pts.set(key, [x0 + (x1 - x0) * t, y0 + (y1 - y0) * t]); }
    return key;
  };
  const link = (k1, k2) => {
    const p = pts.get(k1), q = pts.get(k2);
    if (!inside((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)) return;
    if (!adj.has(k1)) adj.set(k1, []);
    if (!adj.has(k2)) adj.set(k2, []);
    adj.get(k1).push(k2); adj.get(k2).push(k1);
  };
  for (let y = 0; y < h - 1; y++) for (let x = 0; x < w - 1; x++) {
    const a = field[y * w + x], b = field[y * w + x + 1], c = field[(y + 1) * w + x + 1], d = field[(y + 1) * w + x];
    const A = a > level, B = b > level, C = c > level, D = d > level;
    if (A === B && B === C && C === D) continue;
    const T = A !== B ? point(`h${x},${y}`, x, y, a, x + 1, y, b) : null;
    const Rt = B !== C ? point(`v${x + 1},${y}`, x + 1, y, b, x + 1, y + 1, c) : null;
    const Bm = D !== C ? point(`h${x},${y + 1}`, x, y + 1, d, x + 1, y + 1, c) : null;
    const L = A !== D ? point(`v${x},${y}`, x, y, a, x, y + 1, d) : null;
    const cross = [T, Rt, Bm, L].filter(k => k !== null);
    if (cross.length === 2) link(cross[0], cross[1]);
    else if (cross.length === 4) {
      const center = (a + b + c + d) / 4 > level;
      if (center === A) { link(T, Rt); link(Bm, L); } else { link(T, L); link(Rt, Bm); }
    }
  }
  const used = new Set(), lines = [];
  const edge = (k1, k2) => (k1 < k2 ? `${k1}|${k2}` : `${k2}|${k1}`);
  const walk = start => {
    const line = [start];
    let cur = start;
    for (;;) {
      const next = (adj.get(cur) || []).find(n => !used.has(edge(cur, n)));
      if (next === undefined) break;
      used.add(edge(cur, next));
      line.push(next);
      cur = next;
      if (next === start) break;
    }
    if (line.length > 1) lines.push(line.map(k => pts.get(k)));
  };
  for (const [k, ns] of adj) if (ns.length === 1 && !used.has(edge(k, ns[0]))) walk(k);
  for (const [k, ns] of adj) if (ns.some(n => !used.has(edge(k, n)))) walk(k);
  return lines;
}

/** Order strokes so the pen starts at the core and works outward. */
export function orderStrokes(lines, cx, cy) {
  const nearest = line => Math.min(...line.map(([x, y]) => Math.hypot(x - cx, y - cy)));
  return lines.map(l => [nearest(l), l]).sort((p, q) => p[0] - q[0]).map(p => p[1]);
}

// ---------------- inking + overlay ----------------
const MARK_COLOR = { KO_TKO: "#d62828", SUB: "#2563eb", DEC: "#6b7280", OTHER: "#6b7280" };
const RESULT_WORD = { W: "Win", L: "Loss", D: "Draw", NC: "No contest" };
const METHOD_WORD = { KO_TKO: "KO/TKO", SUB: "Submission", DEC: "Decision", OTHER: "Other" };

/** Draw the print onto `canvas`, and the forensic overlay (one mark per fight) into `svg`. */
/**
 * Draw the print onto `canvas`, and the forensic overlay (one mark per fight) into `svg`.
 * With options.strokes (a second canvas on top) and options.animate, a pen first traces the ridges
 * from the core outward, then the finished ink fades in underneath.
 */
export function drawPrint(canvas, svg, params, fights, { strokes = null, animate = false, duration = 1800 } = {}) {
  const plan = printPlan(params, fights);
  const rand = rng32(hashStr(plan.seed));
  const g = grow(plan, rand);
  const { I, PW, R } = g;
  const DW = GW * SCALE, DH = GH * SCALE;
  canvas.width = DW; canvas.height = DH;
  const ctx = canvas.getContext("2d");
  const img = ctx.createImageData(DW, DH);
  const nEdge = makeNoise(rand), nWear = makeNoise(rand), nFine = makeNoise(rand), nPore = makeNoise(rand), nPress = makeNoise(rand);

  const ct = Math.cos(plan.tilt), st = Math.sin(plan.tilt);
  const ecx = GW / 2, ecy = GH * 0.52;

  // creases: one per KO/TKO loss
  const creases = [];
  for (let i = 0; i < plan.creaseCount; i++) {
    const x0 = ecx + (rand() - 0.5) * 130, y0 = ecy + (rand() - 0.5) * 170;
    const a = -0.4 + (rand() - 0.5) * 1.4, len = 40 + rand() * 70;
    creases.push({ x0: x0 - Math.cos(a) * len / 2, y0: y0 - Math.sin(a) * len / 2,
      dx: Math.cos(a) * len, dy: Math.sin(a) * len, w: 0.7 + rand() * 0.8 });
  }
  const segDist = (px, py, c) => {
    const t = clamp(((px - c.x0) * c.dx + (py - c.y0) * c.dy) / (c.dx * c.dx + c.dy * c.dy));
    return Math.hypot(px - c.x0 - t * c.dx, py - c.y0 - t * c.dy);
  };

  // display <-> grid mapping (mirror for southpaw, then tilt)
  const toGrid = (X, Y) => {
    let x = X / SCALE; const y = Y / SCALE;
    if (plan.mirror) x = GW - x;
    const dx = x - ecx, dy = y - ecy;
    return [ecx + dx * ct - dy * st, ecy + dx * st + dy * ct];
  };
  const toDisplay = (gx, gy) => {
    const dx = gx - ecx, dy = gy - ecy;
    let x = ecx + dx * ct + dy * st; const y = ecy - dx * st + dy * ct;
    if (plan.mirror) x = GW - x;
    return [x / GW * 300, y / GH * 375];
  };
  const sample = (x, y) => {
    x = clamp(x, 0, GW - 1.001) + R; y = clamp(y, 0, GH - 1.001) + R;
    const i = x | 0, j = y | 0, fx = x - i, fy = y - j, p = j * PW + i;
    return lerp(lerp(I[p], I[p + 1], fx), lerp(I[p + PW], I[p + PW + 1], fx), fy);
  };

  const erx = GW * 0.44 * plan.size, ery = GH * 0.46 * plan.size;
  for (let Y = 0; Y < DH; Y++) for (let X = 0; X < DW; X++) {
    const [gx, gy] = toGrid(X, Y);
    const ex = (gx - ecx) / erx, ey = (gy - ecy) / ery;
    const d = Math.hypot(ex, ey * (ey > 0 ? 1.06 : 0.97)) + 0.06 * nEdge(gx / 9, gy / 9) + 0.025 * nFine(gx / 2.5, gy / 2.5);
    if (d > 1.02) continue;
    const v = sample(gx, gy);
    let thr = lerp(0.32, -0.22, plan.pressure);                              // ink pressure (finish rate)
    thr += 0.22 * nPress(gx / 38, gy / 38);                                  // uneven pressure across the pad
    thr += smooth(0.72, 1.0, d) * 0.95;                                      // pressure falls off at the edge
    thr += plan.wear * 1.1 * Math.max(0, nWear(gx / 6, gy / 6) - 0.05);     // worn ridges (damage absorbed)
    thr += 0.16 * nFine(gx / 1.4, gy / 1.4);                                 // rough ridge edges
    let a = smooth(thr - 0.1, thr + 0.1, v);
    if (nPore(gx / 0.9, gy / 0.9) > 0.72) a *= 0.1;                          // sweat pores
    for (const c of creases) { const cd = segDist(gx, gy, c); if (cd < c.w + 0.8) a *= smooth(c.w * 0.4, c.w + 0.8, cd); }
    if (a < 0.02) continue;
    const i = (Y * DW + X) * 4;
    img.data[i] = 16; img.data[i + 1] = 16; img.data[i + 2] = 18; img.data[i + 3] = Math.round(a * 255);
  }
  ctx.putImageData(img, 0, 0);

  if (strokes && animate) {
    const field = new Float32Array(GW * GH);
    for (let y = 0; y < GH; y++) for (let x = 0; x < GW; x++) field[y * GW + x] = I[(y + R) * PW + x + R];
    const inPrint = (gx, gy) => Math.hypot((gx - ecx) / erx, (gy - ecy) / ery) < 0.93;
    const px = DW / 300;
    const toCanvas = ([gx, gy]) => { const [x, y] = toDisplay(gx, gy); return [x * px, y * px]; };
    const [coreX, coreY] = toCanvas([GW / 2, GH * 0.5 + plan.coreShift]);
    const lines = traceContours(field, GW, GH, lerp(0.32, -0.22, plan.pressure), inPrint).map(l => l.map(toCanvas));
    animateStrokes(strokes, canvas, orderStrokes(lines, coreX, coreY), duration);
  } else {
    canvas.style.transition = "none";
    canvas.style.opacity = "1";
    if (strokes) { strokes.getContext("2d").clearRect(0, 0, strokes.width, strokes.height); strokes.style.opacity = "0"; }
  }

  // forensic overlay (shown by the host page when Forensic view is on)
  if (svg) {
    svg.setAttribute("viewBox", "0 0 300 375");
    svg.innerHTML = g.minutiae.map(m => {
      const f = fights[m.i], [x, y] = toDisplay(m.x, m.y), c = MARK_COLOR[f.method_group] ?? "#6b7280";
      const shape = f.result === "W"
        ? `<circle cx="${x}" cy="${y}" r="6" fill="none" stroke="${c}" stroke-width="2"/>`
        : f.result === "L"
          ? `<rect x="${x - 5.5}" y="${y - 5.5}" width="11" height="11" fill="none" stroke="${c}" stroke-width="2"/>`
          : `<path d="M${x} ${y - 7} L${x + 7} ${y} L${x} ${y + 7} L${x - 7} ${y} Z" fill="none" stroke="${c}" stroke-width="2"/>`;
      const title = `Fight ${m.i + 1} of ${fights.length} · ${RESULT_WORD[f.result] ?? f.result} · ${METHOD_WORD[f.method_group] ?? f.method_group}`;
      const esc = s => String(s).replace(/[&<>"]/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[ch]));
      return `<g class="m"><title>${esc(title)}</title>${shape}<text x="${x + 8}" y="${y - 6}" font-size="9" font-weight="700" fill="${c}" font-family="system-ui">${m.i + 1}</text></g>`;
    }).join("");
  }
  return plan;
}

// Trace `lines` onto the stroke canvas like a pen, then fade the finished ink in and the pen lines out.
function animateStrokes(strokeCanvas, inkCanvas, lines, duration) {
  const token = (inkCanvas._fpAnimation = (inkCanvas._fpAnimation || 0) + 1);  // a newer call cancels this one
  strokeCanvas.width = inkCanvas.width;
  strokeCanvas.height = inkCanvas.height;
  const sctx = strokeCanvas.getContext("2d");
  sctx.lineWidth = 1.6;
  sctx.lineCap = "round";
  sctx.lineJoin = "round";
  sctx.strokeStyle = "rgba(16, 16, 18, 0.9)";
  for (const [el, opacity] of [[inkCanvas, "0"], [strokeCanvas, "1"]]) { el.style.transition = "none"; el.style.opacity = opacity; }

  let total = 0;
  for (const line of lines) for (let i = 1; i < line.length; i++) total += Math.hypot(line[i][0] - line[i - 1][0], line[i][1] - line[i - 1][1]);
  let li = 0, pi = 1, drawn = 0, start = null;
  const step = now => {
    if (inkCanvas._fpAnimation !== token) return;
    if (start === null) start = now;
    const t = Math.min(1, (now - start) / duration);
    const target = total * t * t * (3 - 2 * t);  // ease in and out
    sctx.beginPath();
    while (li < lines.length && drawn < target) {
      const line = lines[li];
      if (pi >= line.length) { li++; pi = 1; continue; }
      const [x0, y0] = line[pi - 1], [x1, y1] = line[pi];
      sctx.moveTo(x0, y0);
      sctx.lineTo(x1, y1);
      drawn += Math.hypot(x1 - x0, y1 - y0);
      pi++;
    }
    sctx.stroke();
    if (t < 1) { requestAnimationFrame(step); return; }
    inkCanvas.style.transition = "opacity 600ms ease";
    strokeCanvas.style.transition = "opacity 900ms ease";
    inkCanvas.style.opacity = "1";
    strokeCanvas.style.opacity = "0";
  };
  requestAnimationFrame(step);
}
