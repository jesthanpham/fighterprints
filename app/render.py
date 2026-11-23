"""Build the self-contained HTML that draws two fingerprints side by side in the browser."""

import json
from pathlib import Path

RENDERER = Path(__file__).parent / "components" / "fingerprint" / "fingerprint.js"


def _safe_json(data) -> str:
    # Inside <script>, "</" could close the tag early (e.g. a name containing "</script>").
    return json.dumps(data).replace("</", "<\\/").replace("<!--", "<\\!--")


TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8">
<style>
  body { margin: 0; font: 14px/1.4 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; color: #1c1b19; }
  .row { display: flex; flex-wrap: wrap; gap: 16px; justify-content: center; }
  /* Each print sits on its own light card so it reads the same in Streamlit's light and dark themes. */
  figure { margin: 0; width: 300px; padding: 10px; background: #fff; border-radius: 12px; }
  .print { position: relative; width: 300px; aspect-ratio: 300 / 375; background: #fff; border-radius: 8px;
           border: 1px solid #e2ddd3; overflow: hidden; }
  .print canvas, .print svg { position: absolute; inset: 0; width: 100%; height: 100%; }
  .print svg { display: none; }
  h3 { margin: 8px 0 2px; font-size: 16px; }
  .badge { display: inline-block; font-size: 12px; padding: 1px 8px; border-radius: 999px; background: #1c1b19; color: #fff; }
  ul { margin: 6px 0 0; padding-left: 18px; color: #6b675f; font-size: 13px; }
</style></head>
<body>
<div class="row" id="row"></div>
<script type="application/json" id="payloads">__PAYLOADS__</script>
<script type="module">
__RENDERER__

const PATTERN_WORDS = { whorl: "whorl", loop: "loop", double_loop: "double loop", tented_arch: "tented arch", plain_arch: "plain arch" };
const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const payloads = JSON.parse(document.getElementById("payloads").textContent);
const row = document.getElementById("row");
for (const { params, fights } of payloads) {
  const fig = document.createElement("figure");
  fig.innerHTML = `<div class="print"><canvas></canvas><svg></svg></div>
    <h3>${esc(params.fighter_name)}</h3><span class="badge">${esc(params.archetype)}</span><ul></ul>`;
  row.append(fig);
  const plan = drawPrint(fig.querySelector("canvas"), fig.querySelector("svg"), params, fights);
  const pct = v => Math.round(Number(v) * 100) + "%";
  const lines = [
    `${params.archetype} → ${PATTERN_WORDS[plan.pattern]}`,
    `${fights.length} UFC fights → ${fights.length} ridge marks`,
    `${pct(params.finish_rate)} finish rate → ${plan.pressure > 0.6 ? "heavy" : plan.pressure > 0.3 ? "medium" : "light"} ink`,
    `${params.ko_losses} KO loss${params.ko_losses === 1 ? "" : "es"} → ${plan.creaseCount} crease${plan.creaseCount === 1 ? "" : "s"}`,
    `${plan.flags.includes("stance_missing") ? "Stance unknown" : params.stance} → ${plan.mirror ? "left" : "right"}-hand print`,
  ];
  if (plan.flags.includes("reach_missing")) lines.push("Reach unknown → average size");
  if (plan.flags.includes("no_stats")) lines.push("No round stats → average pace and wear");
  fig.querySelector("ul").innerHTML = lines.map(l => `<li>${esc(l)}</li>`).join("");
}
</script>
</body></html>
"""


def prints_html(a: dict, b: dict) -> str:
    return TEMPLATE.replace("__RENDERER__", RENDERER.read_text()).replace("__PAYLOADS__", _safe_json([a, b]))
