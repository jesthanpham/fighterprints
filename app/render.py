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

# Only what the drawing needs goes to the browser: no record, weight, opponents or events.
DRAW_PARAMS = [
    "fighter_id", "fighter_name", "archetype", "sig_landed_per_min", "sig_absorbed_per_min",
    "head_pct", "reach_in", "stance", "finish_rate", "ko_losses",
]
DRAW_FIGHT_FIELDS = ["result", "method_group"]
FRAME_HEIGHT = 510


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
  .row { display: flex; align-items: center; justify-content: center; gap: 16px; padding: 8px 0; }
  figure { margin: 0; width: min(300px, calc((100vw - 170px) / 2)); text-align: center; }
  .print { position: relative; width: 100%; aspect-ratio: 300 / 375; }
  .print canvas, .print svg { position: absolute; inset: 0; width: 100%; height: 100%; }
  .print svg { display: none; }
  body.forensic .print svg { display: block; }
  .tools { text-align: center; padding: 4px 0 2px; }
  #forensic { font: inherit; font-size: 13px; color: #6b675f; background: none; cursor: pointer;
              border: 1px solid #d6d2c8; border-radius: 999px; padding: 4px 14px; }
  #forensic:hover { color: #1c1b19; border-color: #b9b4a8; }
  #forensic[aria-pressed="true"] { color: #f6f4ef; background: #1c1b19; border-color: #1c1b19; }
  figcaption { margin-top: 10px; font-weight: 600; font-size: 17px; min-height: 1.4em; }
  .score { flex: 0 0 auto; min-width: 104px; text-align: center; }
  .score .pct { font-size: clamp(34px, 7vw, 56px); font-weight: 700; letter-spacing: -0.02em;
                font-variant-numeric: tabular-nums; }
  .score .label { color: #6b675f; font-size: 14px; text-transform: uppercase; letter-spacing: 0.08em; }
  @media (max-width: 560px) {
    .row { flex-direction: column; gap: 8px; }
    figure { width: min(300px, 78vw); }
  }
</style></head>
<body>
<div class="row">
  <figure id="a"><div class="print"><canvas class="ink"></canvas><canvas class="strokes"></canvas><svg></svg></div><figcaption></figcaption></figure>
  <div class="score"><div class="pct" id="score"></div><div class="label">style match</div></div>
  <figure id="b"><div class="print"><canvas class="ink"></canvas><canvas class="strokes"></canvas><svg></svg></div><figcaption></figcaption></figure>
</div>
<div class="tools"><button id="forensic" type="button" aria-pressed="false">Forensic view</button></div>
<script type="module">
import { drawPrint } from "./fingerprint.js";

const send = (type, data = {}) => window.parent.postMessage({ isStreamlitMessage: true, type, ...data }, "*");
const calm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const shown = { a: null, b: null };
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
    if (shown[slot] === params.fighter_id) continue;
    shown[slot] = params.fighter_id;
    const fig = document.getElementById(slot);
    fig.querySelector("figcaption").textContent = params.fighter_name;
    drawPrint(fig.querySelector("canvas.ink"), fig.querySelector("svg"), params, fights,
              { strokes: fig.querySelector("canvas.strokes"), animate: !calm });
  }
  send("streamlit:setFrameHeight", { height: document.body.scrollHeight });
});
document.getElementById("forensic").addEventListener("click", event => {
  const on = document.body.classList.toggle("forensic");
  event.currentTarget.setAttribute("aria-pressed", String(on));
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
