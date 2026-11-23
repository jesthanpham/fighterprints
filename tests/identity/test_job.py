from tests.helpers import load_fixture_csvs
from ufc.identity.job import build_identity


def test_build_identity_on_fixtures(db):
    load_fixture_csvs(db)
    counts = build_identity(db)
    assert counts.get("unresolved", 0) == 0
    rows = {
        (fight, name): fighter
        for fight, name, fighter in db.execute(
            "select fight_id, name_as_written, fighter_id from src.fighter_identity"
        ).fetchall()
    }
    assert rows[("f2", "Bruno Silva")] == "294aa73dbf37d281"
    assert rows[("f3", "Bruno Silva")] == "12ebd7d157e91701"
    assert rows[("f2", "Rafael Cerquiera")] == "rc01"
    # f4 is listed under two event names upstream, but appears once per fighter here
    assert sorted(k for k in rows if k[0] == "f4") == [("f4", "Alan Alpha"), ("f4", "Dan Delta")]
    assert len(rows) == 8  # 4 fights x 2 fighters


def test_build_identity_is_repeatable(db):
    load_fixture_csvs(db)
    first = build_identity(db)
    second = build_identity(db)
    assert first == second
    assert db.execute("select count(*) from src.fighter_identity").fetchone()[0] == 8
