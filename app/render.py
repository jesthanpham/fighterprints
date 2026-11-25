"""Build the self-contained HTML that draws two fingerprints and their similarity score."""

import json
import re
from pathlib import Path

RENDERER = Path(__file__).parent / "components" / "fingerprint" / "fingerprint.js"

# Only what the drawing needs goes to the browser: no record, weight, opponents or events.
DRAW_PARAMS = [
    "fighter_id", "fighter_name", "archetype", "sig_landed_per_min", "sig_absorbed_per_min",
    "head_pct", "reach_in", "stance", "finish_rate", "ko_losses",
]
DRAW_FIGHT_FIELDS = ["result", "method_group"]


def _for_drawing(payload: dict) -> dict:
    return {
        "params": {k: payload["params"].get(k) for k in DRAW_PARAMS},
        "fights": [{k: f.get(k) for k in DRAW_FIGHT_FIELDS} for f in payload["fights"]],
    }


def _without_comments(js: str) -> str:
    """Drop comments so the page source doesn't narrate how stats shape the print."""
    js = re.sub(r"/\*.*?\*/\n?", "", js, flags=re.DOTALL)  # block comments
    js = re.sub(r"(?m)^[ \t]*//[^\n]*\n", "", js)  # whole-line comments
    return re.sub(r"(?m)[ \t]+//[^\n]*$", "", js)   # trailing comments


def _safe_json(data) -> str:
    # Inside <script>, "</" could close the tag early (e.g. a name containing "</script>").
    return json.dumps(data).replace("</", "<\\/").replace("<!--", "<\\!--")


# Streamlit rebuilds the frame on every change, so the page remembers (sessionStorage) which fighter
# was in each slot and only re-draws, pen-first, the print that actually changed. Reduced-motion
# users get the finished print straight away.
TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8">
<style>
  body { margin: 0; background: transparent; color: #1c1b19;
         font: 15px/1.4 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
  /* print | score | print on one line; the prints shrink to fit narrow windows */
  .row { display: flex; align-items: center; justify-content: center; gap: 16px; padding: 8px 0; }
  figure { margin: 0; width: min(300px, calc((100vw - 170px) / 2)); text-align: center; }
  .print { position: relative; width: 100%; aspect-ratio: 300 / 375; }
  .print canvas, .print svg { position: absolute; inset: 0; width: 100%; height: 100%; }
  .print svg { display: none; }
  figcaption { margin-top: 10px; font-weight: 600; font-size: 17px; }
  .score { flex: 0 0 auto; min-width: 104px; text-align: center; }
  .score .pct { font-size: clamp(34px, 7vw, 56px); font-weight: 700; letter-spacing: -0.02em; font-variant-numeric: tabular-nums; }
  .score .label { color: #6b675f; font-size: 14px; text-transform: uppercase; letter-spacing: 0.08em; }
</style></head>
<body>
<div class="row" id="row">
  <figure id="a"><div class="print"><canvas class="ink"></canvas><canvas class="strokes"></canvas><svg></svg></div><figcaption></figcaption></figure>
  <div class="score"><div class="pct">__SCORE__</div><div class="label">similar</div></div>
  <figure id="b"><div class="print"><canvas class="ink"></canvas><canvas class="strokes"></canvas><svg></svg></div><figcaption></figcaption></figure>
</div>
<script type="application/json" id="payloads">__PAYLOADS__</script>
<script type="module">
__RENDERER__

const payloads = JSON.parse(document.getElementById("payloads").textContent);
const calm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const shown = slot => { try { return sessionStorage.getItem("fighterprints-" + slot); } catch { return null; } };
const remember = (slot, id) => { try { sessionStorage.setItem("fighterprints-" + slot, id); } catch {} };
["a", "b"].forEach((slot, i) => {
  const fig = document.getElementById(slot), { params, fights } = payloads[i];
  fig.querySelector("figcaption").textContent = params.fighter_name;
  const animate = !calm && shown(slot) !== params.fighter_id;
  drawPrint(fig.querySelector("canvas.ink"), fig.querySelector("svg"), params, fights,
            { strokes: fig.querySelector("canvas.strokes"), animate });
  remember(slot, params.fighter_id);
});
</script>
</body></html>
"""


def prints_html(a: dict, b: dict, similarity: int | None) -> str:
    score = f"{similarity}%" if similarity is not None else "–"
    return (
        TEMPLATE.replace("__SCORE__", score)
        .replace("__RENDERER__", _without_comments(RENDERER.read_text()))
        .replace("__PAYLOADS__", _safe_json([_for_drawing(a), _for_drawing(b)]))
    )
