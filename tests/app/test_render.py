from app.render import prints_html


def payload(name):
    return {
        "params": {"fighter_id": "x1", "fighter_name": name, "archetype": "Striker", "sig_landed_per_min": 4.0,
                   "sig_absorbed_per_min": 3.0, "head_pct": 0.6, "reach_in": 72, "stance": "Orthodox",
                   "finish_rate": 0.5, "ko_losses": 0, "wins": 1, "losses": 0, "draws": 0, "no_contests": 0},
        "fights": [{"fight_seq": 1, "result": "W", "method_group": "KO_TKO"}],
    }


def test_prints_html_escapes_script_close():
    html = prints_html(payload("</script><b>x"), payload("Normal Name"))
    assert "</script><b>x" not in html
    assert "Normal Name" in html


def test_prints_html_inlines_the_renderer():
    html = prints_html(payload("A"), payload("B"))
    assert "function drawPrint" in html
    assert 'type="module"' in html
