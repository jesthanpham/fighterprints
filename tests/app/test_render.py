import re

from app.render import INDEX_HTML, build_component_dir, component_args


def payload(name, fighter_id="x1"):
    return {
        "params": {"fighter_id": fighter_id, "fighter_name": name, "weight_lbs": 155, "archetype": "Striker",
                   "sig_landed_per_min": 4.0, "sig_absorbed_per_min": 3.0, "head_pct": 0.6, "reach_in": 72,
                   "stance": "Orthodox", "finish_rate": 0.5, "ko_losses": 0, "wins": 1, "losses": 0, "draws": 0,
                   "no_contests": 0, "small_sample": True},
        "fights": [{"fight_seq": 1, "fight_id": "f1", "event_name": "UFC 1", "event_date": "2024-01-01",
                    "opponent_name": "Somebody", "result": "W", "method_group": "KO_TKO", "end_round": 1,
                    "end_time_s": 90}],
    }


def test_args_carry_the_score_and_both_fighters():
    args = component_args(payload("A", "a1"), payload("B", "b1"), {"score": 73})
    assert args["score"] == "73%"
    assert args["a"]["params"]["fighter_id"] == "a1" and args["b"]["params"]["fighter_id"] == "b1"


def test_no_score_shows_a_dash():
    assert component_args(payload("A"), payload("B"), None)["score"] == "–"
    assert component_args(payload("A"), payload("B"), {"score": None})["score"] == "–"


def test_browser_only_gets_what_the_drawing_and_forensic_notes_need():
    fighter = component_args(payload("A"), payload("B"), None)["a"]
    assert set(fighter["fights"][0]) == {"result", "method_group", "opponent_name", "event_name", "event_date",
                                         "end_round", "end_time_s"}
    for hidden in ("wins", "losses", "weight_lbs", "small_sample"):
        assert hidden not in fighter["params"]


def test_component_folder_has_the_page_and_a_comment_free_renderer():
    folder = build_component_dir()
    code = (folder / "fingerprint.js").read_text()
    assert "export function drawPrint" in code
    assert "/*" not in code and not re.search(r"(?m)(^|\s)//", code)
    assert (folder / "index.html").read_text() == INDEX_HTML


def test_page_explains_nothing():
    visible = re.sub(r"<script.*?</script>|<style.*?</style>", "", INDEX_HTML, flags=re.DOTALL)
    for tell in ("ridge", "finish", "crease", "absorbed", "Striker", "→", "pattern"):
        assert tell not in visible


def test_prints_sit_on_the_page_without_a_card():
    css = re.search(r"\.print\s*\{(.*?)\}", INDEX_HTML, re.DOTALL).group(1)
    assert "background" not in css and "box-shadow" not in css


def test_frame_stays_alive_and_redraws_only_changed_prints():
    assert INDEX_HTML.count('class="strokes"') == 2
    assert "streamlit:render" in INDEX_HTML          # new picks arrive as messages, no page reload
    assert "streamlit:componentReady" in INDEX_HTML
    assert "prefers-reduced-motion" in INDEX_HTML
    assert "shown[slot]" in INDEX_HTML               # a slot only redraws when its fighter changed


def test_score_counts_up_with_the_drawing():
    assert "countTo(" in INDEX_HTML
    assert "requestAnimationFrame" in INDEX_HTML


def test_score_is_labelled_style_match():
    assert ">style match<" in INDEX_HTML and ">similar<" not in INDEX_HTML


def test_prints_stack_on_phones():
    assert "@media (max-width: 560px)" in INDEX_HTML


def test_forensic_view_is_a_toggle_that_starts_off():
    assert 'id="forensic"' in INDEX_HTML and ">Forensic view<" in INDEX_HTML
    assert "aria-pressed" in INDEX_HTML
    assert re.search(r"\.print svg\s*\{[^}]*display:\s*none", INDEX_HTML)          # off by default
    assert re.search(r"body\.forensic \.print svg\s*\{[^}]*display:\s*block", INDEX_HTML)


def test_explainer_and_tooltip_only_show_in_forensic_view():
    assert 'id="explain"' in INDEX_HTML and 'id="tip"' in INDEX_HTML
    assert re.search(r"#explain\s*\{[^}]*display:\s*none", INDEX_HTML)
    assert re.search(r"body\.forensic #explain\s*\{[^}]*display:\s*block", INDEX_HTML)


def test_forensic_marks_show_a_magnifying_glass():
    assert re.search(r"\.m\b[^{]*\{[^}]*cursor:\s*zoom-in", INDEX_HTML)


def test_score_breakdown_reaches_the_page_and_only_shows_in_forensic_view():
    breakdown = {"rows": [], "shared": 9, "avg_gap": 20.0, "base": 80.0, "archetypes": ["Striker", "Striker"],
                 "penalty": 0, "score": 80}
    args = component_args(payload("A", "a1"), payload("B", "b1"), breakdown)
    assert args["score"] == "80%" and args["match"] == breakdown
    assert component_args(payload("A"), payload("B"), None)["match"] is None
    assert 'id="match"' in INDEX_HTML
    assert re.search(r"#match\s*\{[^}]*display:\s*none", INDEX_HTML)
    assert re.search(r"body\.forensic #match\s*\{[^}]*display:\s*block", INDEX_HTML)
