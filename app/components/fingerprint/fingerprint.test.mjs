import { test } from "node:test";
import assert from "node:assert/strict";
import { printPlan, markNote, markSvg, explainRows } from "./fingerprint.js";

const base = {
  fighter_id: "aa01",
  fighter_name: "Alan Alpha",
  archetype: "Striker",
  sig_landed_per_min: 5.0,
  sig_absorbed_per_min: 3.0,
  head_pct: 0.6,
  reach_in: 72,
  stance: "Orthodox",
  finish_rate: 0.5,
  ko_losses: 1,
};
const fights = [
  { fight_seq: 1, result: "W", method_group: "KO_TKO" },
  { fight_seq: 2, result: "L", method_group: "DEC" },
];
const lerp = (a, b, t) => a + (b - a) * t;

test("pattern mapping", () => {
  const expected = {
    Striker: "whorl", Wrestler: "loop", Grappler: "double_loop",
    Brawler: "tented_arch", Balanced: "plain_arch",
  };
  for (const [archetype, pattern] of Object.entries(expected)) {
    assert.equal(printPlan({ ...base, archetype }, fights).pattern, pattern);
  }
});

test("missing reach and stance use defaults", () => {
  const plan = printPlan({ ...base, reach_in: null, stance: null }, fights);
  assert.equal(plan.size, lerp(0.84, 1.04, 0.4));
  assert.equal(plan.mirror, false);
  assert.ok(plan.flags.includes("reach_missing"));
  assert.ok(plan.flags.includes("stance_missing"));
});

test("no stats does not produce NaN", () => {
  const plan = printPlan(
    { ...base, sig_landed_per_min: null, sig_absorbed_per_min: null, head_pct: null, finish_rate: 0 },
    [],
  );
  for (const key of ["spacing", "pressure", "wear", "size", "tilt", "coreShift", "creaseCount", "markCount"]) {
    assert.ok(Number.isFinite(plan[key]), `${key} = ${plan[key]}`);
  }
  assert.ok(plan.flags.includes("no_stats"));
  assert.equal(plan.markCount, 0);
});

test("southpaw mirrors, switch is upright", () => {
  const southpaw = printPlan({ ...base, stance: "Southpaw" }, fights);
  assert.equal(southpaw.mirror, true);
  assert.equal(southpaw.tilt, -0.14);
  const sw = printPlan({ ...base, stance: "Switch" }, fights);
  assert.equal(sw.mirror, false);
  assert.equal(sw.tilt, 0);
});

test("same input, same plan", () => {
  assert.deepEqual(printPlan(base, fights), printPlan(base, fights));
});

test("stats drive the knobs", () => {
  const plan = printPlan(base, fights);
  assert.equal(plan.spacing, lerp(7.4, 5.0, 4 / 7));
  assert.equal(plan.pressure, 0.5);
  assert.equal(plan.wear, 2 / 6);
  assert.equal(plan.creaseCount, 1);
  assert.equal(plan.markCount, 2);
  assert.equal(plan.seed, "aa01");
  assert.equal(plan.coreShift, lerp(16, -16, 0.5));
});

// ---------- stroke tracing ----------
import { traceContours, orderStrokes } from "./fingerprint.js";

const circleField = (w, h, cx, cy) => {
  const f = new Float32Array(w * h);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) f[y * w + x] = Math.hypot(x - cx, y - cy);
  return f;
};

test("a circle traces as one closed loop at the right radius", () => {
  const lines = traceContours(circleField(40, 40, 20, 20), 40, 40, 8);
  assert.equal(lines.length, 1);
  const pts = lines[0];
  assert.ok(pts.length > 20);
  for (const [x, y] of pts) assert.ok(Math.abs(Math.hypot(x - 20, y - 20) - 8) < 0.6);
  const [first, last] = [pts[0], pts[pts.length - 1]];
  assert.ok(Math.hypot(first[0] - last[0], first[1] - last[1]) < 1.5, "loop closes");
});

test("two separate rings trace as two lines", () => {
  const w = 60, h = 30, f = new Float32Array(w * h);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++)
    f[y * w + x] = Math.min(Math.hypot(x - 15, y - 15), Math.hypot(x - 45, y - 15));
  assert.equal(traceContours(f, w, h, 6).length, 2);
});

test("an inside() filter drops lines outside the print", () => {
  const lines = traceContours(circleField(40, 40, 20, 20), 40, 40, 8, (x) => x < 0);
  assert.equal(lines.length, 0);
});

test("strokes are ordered from the core outward", () => {
  const near = [[11, 10], [12, 10]], far = [[30, 30], [31, 30]], mid = [[15, 15], [16, 15]];
  assert.deepEqual(orderStrokes([far, near, mid], 10, 10), [near, mid, far]);
});

test("forensic marks carry no number labels and are hoverable", () => {
  const svg = markSvg({ result: "W", method_group: "KO_TKO" }, 4, 10, 20);
  assert.ok(!svg.includes("<text"));
  assert.ok(svg.includes('class="m"') && svg.includes('data-i="4"'));
});

test("a mark's note says which fight put it there", () => {
  const fight = { result: "L", method_group: "SUB", opponent_name: "Bea Beta", event_name: "UFC 300",
                  event_date: "2024-04-13", end_round: 2, end_time_s: 95 };
  const note = markNote(fight, 2, 7);
  assert.equal(note.heading, "Loss by submission");
  const text = note.lines.join(" ");
  for (const bit of ["Bea Beta", "UFC 300", "2024-04-13", "Round 2, 1:35", "Fight 3 of 7"]) assert.ok(text.includes(bit), bit);
});

test("a mark's note copes with missing fight details", () => {
  const note = markNote({ result: "NC", method_group: "OTHER" }, 0, 1);
  assert.equal(note.heading, "No contest");
  assert.ok(!note.lines.join(" ").includes("undefined"));
});

test("explainer lists every stat that shapes the print, with its value", () => {
  const rows = explainRows(base, fights);
  const byFeature = Object.fromEntries(rows.map(r => [r.feature, r.value]));
  assert.equal(byFeature["Pattern"], "Striker → whorl");
  assert.equal(byFeature["Ridge spacing"], "5.0");
  assert.equal(byFeature["Ink darkness"], "50%");
  assert.equal(byFeature["Worn ridges"], "3.0");
  assert.equal(byFeature["Print size"], '72"');
  assert.equal(byFeature["Orientation"], "Orthodox → tilted");
  assert.equal(byFeature["Core height"], "60%");
  assert.equal(byFeature["Creases"], "1");
  assert.equal(byFeature["Marks"], "2");
  for (const r of rows) assert.ok(r.source && r.effect, r.feature);
});

test("explainer says when a default stood in for a missing stat", () => {
  const rows = explainRows({ ...base, reach_in: null, stance: null }, fights);
  const byFeature = Object.fromEntries(rows.map(r => [r.feature, r.value]));
  assert.equal(byFeature["Print size"], 'unknown (72" used)');
  assert.equal(byFeature["Orientation"], "unknown (Orthodox used)");
});
