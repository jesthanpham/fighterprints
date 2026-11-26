"""The two-print display as a Streamlit component that stays alive between picks.

A plain components.html frame is rebuilt on every rerun, so the whole display blinks. This component
is one persistent frame: each pick arrives as a "streamlit:render" message with the new arguments,
and only the print whose fighter changed redraws (pen first, then ink). Reduced-motion users get the
finished print straight away.
"""

import re
import tempfile
from functools import cache
from pathlib import Path

import streamlit.components.v1 as components

RENDERER = Path(__file__).parent / "components" / "fingerprint" / "fingerprint.js"

# Only what the drawing and the forensic notes need goes to the browser: no record or weight.
DRAW_PARAMS = [
    "fighter_id", "fighter_name", "archetype", "sig_landed_per_min", "sig_absorbed_per_min",
    "head_pct", "reach_in", "stance", "finish_rate", "ko_losses",
]
DRAW_FIGHT_FIELDS = ["result", "method_group", "opponent_name", "event_name", "event_date", "end_round", "end_time_s"]
FRAME_HEIGHT = 700


def _for_drawing(payload: dict) -> dict:
    return {
        "params": {k: payload["params"].get(k) for k in DRAW_PARAMS},
        "fights": [{k: f.get(k) for k in DRAW_FIGHT_FIELDS} for f in payload["fights"]],
    }


def _without_comments(js: str) -> str:
    """Drop comments so the page source doesn't narrate how stats shape the print."""
    js = re.sub(r"/\*.*?\*/\n?", "", js, flags=re.DOTALL)
    js = re.sub(r"(?m)^[ \t]*//[^\n]*\n", "", js)
    return re.sub(r"(?m)[ \t]+//[^\n]*$", "", js)


def component_args(a: dict, b: dict, similarity: int | None) -> dict:
    return {
        "a": _for_drawing(a),
        "b": _for_drawing(b),
        "score": f"{similarity}%" if similarity is not None else "–",
    }


INDEX_HTML = """<!doctype html>
<html><head><meta charset="utf-8">
<style>
  body { margin: 0; background: transparent; color: #1c1b19;
         font: 15px/1.4 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
  .row { display: flex; align-items: center; justify-content: center; gap: clamp(16px, 4vw, 56px); padding: 8px 0; }
  figure { margin: 0; width: min(460px, calc((100vw - 200px) / 2)); text-align: center; }
  .print { position: relative; width: 100%; aspect-ratio: 300 / 375; }
  .print canvas, .print svg { position: absolute; inset: 0; width: 100%; height: 100%; }
  .print svg { display: none; }
  body.forensic .print svg { display: block; }
  .tools { text-align: center; padding: 4px 0 2px; }
  #forensic { font: inherit; font-size: 13px; color: #6b675f; background: none; cursor: pointer;
              border: 1px solid #d6d2c8; border-radius: 999px; padding: 4px 14px; }
  #forensic:hover { color: #1c1b19; border-color: #b9b4a8; }
  #forensic[aria-pressed="true"] { color: #f6f4ef; background: #1c1b19; border-color: #1c1b19; }
  .m { cursor: zoom-in; }
  .m * { pointer-events: all; }
  .m:hover * { stroke-width: 3; }
  #tip { position: absolute; display: none; z-index: 5; max-width: 240px; pointer-events: none;
         background: #fffdf8; border: 1px solid #d6d2c8; border-radius: 8px; padding: 8px 10px;
         box-shadow: 0 4px 14px rgba(28, 27, 25, 0.12); font-size: 13px; line-height: 1.35; }
  #tip strong { display: block; margin-bottom: 2px; }
  #tip .fine { color: #6b675f; font-size: 12px; margin-top: 4px; }
  #explain { display: none; margin: 22px auto 4px; max-width: 900px; overflow-x: auto; }
  body.forensic #explain { display: block; }
  #explain table { width: 100%; border-collapse: collapse; font-size: 14px; }
  #explain th, #explain td { text-align: left; padding: 8px 10px; border-bottom: 1px solid #e4e0d6; vertical-align: top; }
  #explain thead th { font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em; color: #6b675f; font-weight: 600; }
  #explain td.val { font-variant-numeric: tabular-nums; white-space: nowrap; }
  #explain .fine { display: block; color: #8a857b; font-size: 12px; }
  #explain .src { display: none; color: #6b675f; font-size: 12px; }
  figcaption { margin-top: 10px; font-weight: 600; font-size: 17px; min-height: 1.4em; }
  .score { flex: 0 0 auto; min-width: 104px; text-align: center; }
  .score .pct { font-size: clamp(34px, 7vw, 56px); font-weight: 700; letter-spacing: -0.02em;
                font-variant-numeric: tabular-nums; }
  .score .label { color: #6b675f; font-size: 14px; text-transform: uppercase; letter-spacing: 0.08em; }
  @media (max-width: 560px) {
    .row { flex-direction: column; gap: 8px; }
    figure { width: min(460px, 92vw); }
    #explain table { font-size: 13px; }
    #explain th, #explain td { padding: 7px 6px; }
    #explain th:nth-child(2), #explain td:nth-child(2) { display: none; }
    #explain .src { display: block; }
    #explain td.val { white-space: normal; }
  }
</style></head>
<body>
<div class="row">
  <figure id="a"><div class="print"><canvas class="ink"></canvas><canvas class="strokes"></canvas><svg></svg></div><figcaption></figcaption></figure>
  <div class="score"><div class="pct" id="score"></div><div class="label">style match</div></div>
  <figure id="b"><div class="print"><canvas class="ink"></canvas><canvas class="strokes"></canvas><svg></svg></div><figcaption></figcaption></figure>
</div>
<div class="tools"><button id="forensic" type="button" aria-pressed="false">Forensic view</button></div>
<div id="explain"></div>
<div id="tip" role="tooltip"></div>
<script type="module">
import { drawPrint, explainRows, markNote } from "./fingerprint.js";

const send = (type, data = {}) => window.parent.postMessage({ isStreamlitMessage: true, type, ...data }, "*");
const calm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const shown = { a: null, b: null };
const current = { a: null, b: null };
const resize = () => send("streamlit:setFrameHeight", { height: document.body.scrollHeight });
const el = (tag, text, cls) => { const e = document.createElement(tag); if (text != null) e.textContent = text; if (cls) e.className = cls; return e; };

function buildExplainer() {
  const box = document.getElementById("explain");
  if (!current.a || !current.b) return;
  const rowsA = explainRows(current.a.params, current.a.fights), rowsB = explainRows(current.b.params, current.b.fights);
  const table = el("table"), head = el("tr");
  for (const h of ["Print feature", "Comes from", current.a.params.fighter_name, current.b.params.fighter_name]) head.append(el("th", h));
  table.append(el("thead")); table.tHead.append(head);
  const body = el("tbody");
  rowsA.forEach((r, k) => {
    const tr = el("tr"), feat = el("td");
    feat.append(el("strong", r.feature), el("span", r.source, "src"), el("span", r.effect, "fine"));
    tr.append(feat, el("td", r.source), el("td", r.value, "val"), el("td", rowsB[k].value, "val"));
    body.append(tr);
  });
  table.append(body);
  box.replaceChildren(table);
}

const tip = document.getElementById("tip");
function showTip(slot, mark, event) {
  const { fights } = current[slot];
  const i = Number(mark.dataset.i), note = markNote(fights[i], i, fights.length);
  const heading = el("strong", note.heading); heading.style.color = note.color;
  const lines = note.lines.map((line, k) => el("div", line, k === note.lines.length - 1 ? "fine" : null));
  tip.replaceChildren(heading, ...lines);
  tip.style.display = "block";
  const x = Math.min(event.clientX + 14, document.body.clientWidth - tip.offsetWidth - 4);
  const y = event.clientY + 14 + tip.offsetHeight > window.innerHeight ? event.clientY - tip.offsetHeight - 10 : event.clientY + 14;
  tip.style.left = Math.max(4, x) + "px";
  tip.style.top = Math.max(4, y) + window.scrollY + "px";
}
for (const slot of ["a", "b"]) {
  const svg = document.querySelector(`#${slot} svg`);
  const onMark = event => { const mark = event.target.closest(".m"); if (mark) showTip(slot, mark, event); else tip.style.display = "none"; };
  svg.addEventListener("pointermove", onMark);
  svg.addEventListener("click", onMark);
  svg.addEventListener("pointerleave", () => { tip.style.display = "none"; });
}
const scoreEl = () => document.getElementById("score");
let scoreRun = 0, scoreNow = 0;

function countTo(score) {
  const target = parseInt(score, 10);
  const run = ++scoreRun;
  if (Number.isNaN(target) || calm) { scoreEl().textContent = score; scoreNow = Number.isNaN(target) ? 0 : target; return; }
  const from = scoreNow, start = performance.now(), duration = 1800;
  const step = now => {
    if (run !== scoreRun) return;
    const t = Math.min(1, (now - start) / duration), eased = t * t * (3 - 2 * t);
    scoreNow = Math.round(from + (target - from) * eased);
    scoreEl().textContent = scoreNow + "%";
    if (t < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

window.addEventListener("message", event => {
  if (!event.data || event.data.type !== "streamlit:render") return;
  const args = event.data.args;
  countTo(args.score);
  for (const slot of ["a", "b"]) {
    const { params, fights } = args[slot];
    current[slot] = args[slot];
    if (shown[slot] === params.fighter_id) continue;
    shown[slot] = params.fighter_id;
    const fig = document.getElementById(slot);
    fig.querySelector("figcaption").textContent = params.fighter_name;
    drawPrint(fig.querySelector("canvas.ink"), fig.querySelector("svg"), params, fights,
              { strokes: fig.querySelector("canvas.strokes"), animate: !calm });
  }
  buildExplainer();
  resize();
});
document.getElementById("forensic").addEventListener("click", event => {
  const on = document.body.classList.toggle("forensic");
  event.currentTarget.setAttribute("aria-pressed", String(on));
  if (!on) tip.style.display = "none";
  resize();
});
send("streamlit:componentReady", { apiVersion: 1 });
</script>
</body></html>
"""


@cache
def build_component_dir() -> Path:
    """Write the component's page and a comment-free copy of the renderer to a folder Streamlit serves."""
    folder = Path(tempfile.mkdtemp(prefix="fighterprints-component-"))
    (folder / "index.html").write_text(INDEX_HTML)
    (folder / "fingerprint.js").write_text(_without_comments(RENDERER.read_text()))
    return folder


@cache
def _component():
    return components.declare_component("fighterprints", path=str(build_component_dir()))


def show_prints(a: dict, b: dict, similarity: int | None) -> None:
    """Draw both prints and the score. The stable key keeps the same frame alive across picks."""
    _component()(**component_args(a, b, similarity), key="prints", default=None, height=FRAME_HEIGHT)
