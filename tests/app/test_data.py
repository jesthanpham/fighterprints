import json

from app.data import default_pair, list_fighters, match_score, print_payload, style_match


def test_print_payload_shape(built_marts):
    payload = print_payload(built_marts, "aa01")
    assert set(payload) == {"params", "fights"}
    assert payload["params"]["fighter_name"] == "Alan Alpha"
    assert [f["fight_seq"] for f in payload["fights"]] == [1, 2]
    assert payload["fights"][0]["event_date"] == "2024-04-13"
    json.dumps(payload)  # everything is JSON-safe


def test_duplicate_names_are_distinguishable(built_marts):
    labels = dict(list_fighters(built_marts))
    assert labels["294aa73dbf37d281"] == "Bruno Silva (125 lbs) (0-1-0)"
    assert labels["12ebd7d157e91701"] == "Bruno Silva (185 lbs) (1-0-0)"
    assert labels["aa01"] == "Alan Alpha (1-0-1)"


def vector(value, archetype="Striker", **overrides):
    dims = ["pace_pct", "absorbed_pct", "accuracy_pct", "defense_pct",
            "takedown_pct", "control_pct", "submission_pct", "finish_pct"]
    return {"archetype": archetype, **dict.fromkeys(dims, value), **overrides}


def test_identical_styles_score_100():
    assert match_score(vector(0.4), vector(0.4)) == 100


def test_different_archetype_costs_10_points():
    assert match_score(vector(0.4), vector(0.4, archetype="Wrestler")) == 90


def test_opposite_styles_score_0():
    assert match_score(vector(0.0), vector(1.0, archetype="Wrestler")) == 0


def test_score_is_100_minus_average_gap():
    # gaps: 0.2 on all 8 dimensions -> 80
    assert match_score(vector(0.3), vector(0.5)) == 80


def test_only_shared_dimensions_count():
    a = vector(0.5, pace_pct=None, absorbed_pct=None)
    b = vector(0.5, pace_pct=0.0, absorbed_pct=0.0)
    assert match_score(a, b) == 100


def test_too_few_shared_dimensions_gives_no_score():
    a = vector(None, pace_pct=0.5, absorbed_pct=0.5, finish_pct=0.5)
    assert match_score(a, vector(0.5)) is None


def test_style_match_without_established_fighters_is_none(built_marts):
    # every fixture fighter is a small sample, so there's no distribution to place them on
    assert style_match(built_marts, "aa01", "dd01") is None


def test_default_pair_is_two_different_fighters(built_marts):
    a, b = default_pair(built_marts)
    assert a != b
