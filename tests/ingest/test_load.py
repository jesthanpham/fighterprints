import pytest

from tests.helpers import fixture_bytes, snapshot
from ufc.ingest.load import SchemaDriftError, ShrinkGuardError, column_name, load_latest, validate_header


def test_column_name_examples():
    assert column_name("SIG.STR.") == "sig_str"
    assert column_name("SIG.STR. %") == "sig_str_pct"
    assert column_name("TOTAL STR.") == "total_str"
    assert column_name("SUB.ATT") == "sub_att"
    assert column_name("REV.") == "rev"
    assert column_name("TIME FORMAT") == "time_format"
    assert column_name("TD %") == "td_pct"


def test_header_drift_lists_columns():
    with pytest.raises(SchemaDriftError) as err:
        validate_header("ufc_fighter_tott", ["FIGHTER", "HEIGHT", "WEIGHT", "REACH_IN", "STANCE", "DOB", "URL"])
    assert "REACH" in str(err.value)
    assert "REACH_IN" in str(err.value)


def test_correct_header_passes():
    validate_header("ufc_event_details", ["EVENT", "URL", "DATE", "LOCATION"])


def test_load_creates_text_table(db):
    snapshot(db, "ufc_fight_stats", fixture_bytes("ufc_fight_stats"))
    result = load_latest(db, "ufc_fight_stats")
    assert result.skipped is False
    assert result.row_count == 19
    columns = [r[0] for r in db.execute(
        "select column_name from information_schema.columns "
        "where table_schema = 'src' and table_name = 'ufc_fight_stats' order by ordinal_position"
    ).fetchall()]
    assert "sig_str_pct" in columns and "_snapshot_sha" in columns and "_row_num" in columns
    count = db.execute("select count(*) from src.ufc_fight_stats").fetchone()[0]
    assert count == 19
    # trailing spaces are kept: cleaning is dbt's job
    snapshot(db, "ufc_fight_results", fixture_bytes("ufc_fight_results"))
    load_latest(db, "ufc_fight_results")
    method = db.execute("select method from src.ufc_fight_results where _row_num = 1").fetchone()[0]
    assert method == "KO/TKO "


def test_unchanged_snapshot_is_skipped(db):
    snapshot(db, "ufc_event_details", fixture_bytes("ufc_event_details"))
    load_latest(db, "ufc_event_details")
    logs_before = db.execute("select count(*) from src.load_log").fetchone()[0]
    snapshot(db, "ufc_event_details", fixture_bytes("ufc_event_details"))  # same content re-fetched
    result = load_latest(db, "ufc_event_details")
    assert result.skipped is True
    assert db.execute("select count(*) from src.load_log").fetchone()[0] == logs_before


def test_shrink_guard_keeps_previous_table(db):
    full = fixture_bytes("ufc_fighter_tott")
    snapshot(db, "ufc_fighter_tott", full)
    load_latest(db, "ufc_fighter_tott")
    truncated = b"\n".join(full.splitlines()[:5]) + b"\n"  # header + 4 of 7 rows
    snapshot(db, "ufc_fighter_tott", truncated)
    with pytest.raises(ShrinkGuardError):
        load_latest(db, "ufc_fighter_tott")
    assert db.execute("select count(*) from src.ufc_fighter_tott").fetchone()[0] == 7


def test_revert_to_previous_version_loads_it(db):
    full = fixture_bytes("ufc_fight_details")
    snapshot(db, "ufc_fight_details", full)
    load_latest(db, "ufc_fight_details")
    changed = full.replace(b"Alan Alpha vs. Ben Beta", b"Alan Alpha vs. Benjamin Beta")  # an upstream edit
    snapshot(db, "ufc_fight_details", changed)
    assert load_latest(db, "ufc_fight_details").skipped is False
    snapshot(db, "ufc_fight_details", full)  # upstream reverts
    result = load_latest(db, "ufc_fight_details")
    assert result.skipped is False
    assert result.row_count == 5


def test_drifted_header_does_not_load(db):
    bad = b"EVENT,LINK,DATE,LOCATION\nUFC 1,x,y,z\n"
    snapshot(db, "ufc_event_details", fixture_bytes("ufc_event_details"))
    load_latest(db, "ufc_event_details")
    snapshot(db, "ufc_event_details", bad)
    with pytest.raises(SchemaDriftError):
        load_latest(db, "ufc_event_details")
    assert db.execute("select count(*) from src.ufc_event_details").fetchone()[0] == 2
