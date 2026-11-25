import json
import re

from app.render import prints_html


def payload(name):
    return {
        "params": {"fighter_id": "x1", "fighter_name": name, "weight_lbs": 155, "archetype": "Striker",
                   "sig_landed_per_min": 4.0, "sig_absorbed_per_min": 3.0, "head_pct": 0.6, "reach_in": 72,
                   "stance": "Orthodox", "finish_rate": 0.5, "ko_losses": 0, "wins": 1, "losses": 0, "draws": 0,
                   "no_contests": 0, "small_sample": True},
        "fights": [{"fight_seq": 1, "fight_id": "f1", "event_name": "UFC 1", "event_date": "2024-01-01",
                    "opponent_name": "Somebody", "result": "W", "method_group": "KO_TKO", "end_round": 1,
                    "end_time_s": 90}],
    }


def embedded(html):
    return json.loads(re.search(r'id="payloads">(.*?)</script>', html, re.DOTALL).group(1).replace("<\\/", "</"))


def test_prints_html_escapes_script_close():
    html = prints_html(payload("</script><b>x"), payload("Normal Name"), 73)
    assert "</script><b>x" not in html
    assert "Normal Name" in html


def test_prints_html_inlines_the_renderer():
    html = prints_html(payload("A"), payload("B"), 73)
    assert "function drawPrint" in html
    assert 'type="module"' in html


def test_shows_the_similarity_percentage():
    assert "73%" in prints_html(payload("A"), payload("B"), 73)


def test_no_score_shows_a_dash():
    html = prints_html(payload("A"), payload("B"), None)
    assert "–" in html and "None%" not in html


def test_visible_page_explains_nothing():
    html = prints_html(payload("A"), payload("B"), 73)
    visible = re.sub(r"<script.*?</script>|<style.*?</style>", "", html, flags=re.DOTALL)
    for tell in ("ridge", "finish", "crease", "absorbed", "hand", "Striker", "→", "pattern"):
        assert tell not in visible


def test_embedded_code_has_no_comments():
    html = prints_html(payload("A"), payload("B"), 73)
    code = re.search(r'<script type="module">(.*?)</script>', html, re.DOTALL).group(1)
    assert "/*" not in code
    assert not re.search(r"(?m)(^|\s)//", code)
    for tell in ("finish rate", "damage absorbed", "Sherlock", "KO/TKO loss"):
        assert tell not in code


def test_browser_only_gets_what_the_drawing_needs():
    fighter = embedded(prints_html(payload("A"), payload("B"), 73))[0]
    assert set(fighter["fights"][0]) == {"result", "method_group"}
    for hidden in ("wins", "losses", "weight_lbs", "small_sample"):
        assert hidden not in fighter["params"]


def _css_block(html, selector):
    return re.search(re.escape(selector) + r"\s*\{(.*?)\}", html, re.DOTALL).group(1)


def test_prints_sit_on_the_page_without_a_card():
    css = _css_block(prints_html(payload("A"), payload("B"), 73), ".print")
    assert "background" not in css
    assert "box-shadow" not in css


def test_each_print_has_a_pen_layer_for_the_animation():
    assert prints_html(payload("A"), payload("B"), 73).count('class="strokes"') == 2


def test_only_a_changed_print_redraws_and_reduced_motion_skips_it():
    html = prints_html(payload("A"), payload("B"), 73)
    assert "sessionStorage" in html
    assert "prefers-reduced-motion" in html
