from datetime import UTC, datetime, timedelta

import httpx
from dagster import AssetCheckSeverity, AssetKey, DefaultScheduleStatus, materialize

from tests.conftest import TEST_DATABASE_URL
from tests.helpers import fixture_bytes
from ufc.config import FILES
from ufc.orchestration.definitions import (
    GitHubSource,
    PostgresResource,
    defs,
    fighter_identity,
    freshness_result,
    raw_snapshots,
    src_tables,
)


class FixtureSource(GitHubSource):
    """Serves the fixture CSVs and a fake GitHub commit instead of the network."""

    def client(self) -> httpx.Client:
        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "api.github.com" in url:
                return httpx.Response(200, json=[{"sha": "fixturesha", "commit": {"committer": {"date": "2026-11-22T18:02:59Z"}}}])
            name = url.rsplit("/", 1)[-1].removesuffix(".csv")
            return httpx.Response(200, content=fixture_bytes(name))

        return httpx.Client(transport=httpx.MockTransport(handler))


def test_definitions_load():
    keys = {spec.key.to_user_string() for spec in defs.resolve_all_asset_specs()}
    assert {
        "raw_snapshots", "src/ufc_fight_stats", "src/ufc_fighter_tott", "src/fighter_identity",
        "marts/fighter_print_params", "marts/fighter_fight_timeline",
    } <= keys
    schedule = defs.resolve_schedule_def("weekly_refresh")
    assert schedule.cron_schedule == "0 10 * * 0"
    assert schedule.execution_timezone == "America/Toronto"
    # schedules start stopped unless told otherwise; this one must actually run
    assert schedule.default_status == DefaultScheduleStatus.RUNNING


def test_dbt_sources_hang_off_the_python_assets():
    graph = defs.resolve_asset_graph()
    parents = {k.to_user_string() for k in graph.get(AssetKey(["staging", "stg_fights"])).parent_keys}
    assert parents == {"src/ufc_fight_results", "src/ufc_fight_details", "staging/stg_events"}
    identity_parents = {k.to_user_string() for k in graph.get(AssetKey(["src", "fighter_identity"])).parent_keys}
    assert identity_parents == {f"src/{name}" for name in FILES}


def test_ingest_assets_with_mock_source(db):
    resources = {"source": FixtureSource(), "db": PostgresResource(url=TEST_DATABASE_URL)}
    first = materialize([raw_snapshots, src_tables, fighter_identity], resources=resources)
    assert first.success
    assert db.execute("select count(*) from src.fighter_identity").fetchone()[0] == 8

    second = materialize([raw_snapshots, src_tables, fighter_identity], resources=resources)
    assert second.success
    meta = {e.asset_key.to_user_string(): e.materialization.metadata
            for e in second.get_asset_materialization_events()}
    assert meta["raw_snapshots"]["new_snapshots"].value == 0
    assert all(meta[f"src/{name}"]["skipped"].value for name in FILES)


def test_freshness_warns_when_stale():
    now = datetime(2026, 11, 23, tzinfo=UTC)
    stale = freshness_result(now - timedelta(days=10), now)
    assert stale.passed is False
    assert stale.severity == AssetCheckSeverity.WARN
    fresh = freshness_result(now - timedelta(days=1), now)
    assert fresh.passed is True
