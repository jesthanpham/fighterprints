import json

from app.data import default_pair, list_fighters, print_payload, stat_rows


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


def test_stat_rows_edges(built_marts):
    rows = {r["label"]: r for r in stat_rows(built_marts, "aa01", "bb01")}
    # Alan absorbs 61 strikes in 17.5 min (3.49/min); Ben absorbs 11 in 2.5 min (4.4/min): lower is better
    assert rows["Sig. strikes absorbed / min"]["edge"] == "a"
    assert rows["Record"]["a"] == "1-0-1"
    assert rows["Stance"]["edge"] == "even"


def test_default_pair_is_two_different_fighters(built_marts):
    a, b = default_pair(built_marts)
    assert a != b
