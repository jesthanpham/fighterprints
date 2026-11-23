from pathlib import Path

from dbt.cli.main import dbtRunner

from tests.helpers import load_fixture_csvs
from ufc.identity.job import build_identity

DBT_DIR = str(Path(__file__).resolve().parents[1] / "dbt")


def dbt(*args: str) -> bool:
    result = dbtRunner().invoke([*args, "--target", "test", "--project-dir", DBT_DIR, "--profiles-dir", DBT_DIR])
    return result.success


def test_staging_on_fixtures(db):
    load_fixture_csvs(db)
    build_identity(db)
    assert dbt("build", "--select", "staging")
    db.rollback()
    assert db.execute("select count(*) from staging.stg_fights").fetchone()[0] == 4
    method, elapsed = db.execute(
        "select method_group, elapsed_s from staging.stg_fights where fight_id = 'f1'"
    ).fetchone()
    assert (method, elapsed) == ("KO_TKO", 150)
    # f4's stats are listed under the "Noche UFC" event name: still one row per fighter per round
    assert db.execute(
        "select count(*) from staging.stg_fight_round_stats where fight_id = 'f4'"
    ).fetchone()[0] == 6
    # the blank upstream row is dropped; 18 real rows remain
    assert db.execute("select count(*) from staging.stg_fight_round_stats").fetchone()[0] == 18
