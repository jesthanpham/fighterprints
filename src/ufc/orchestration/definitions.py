"""Dagster definitions: the whole pipeline as assets, a freshness check and a weekly schedule.

raw_snapshots -> src/<file> (x6) -> src/fighter_identity -> dbt models (staging -> intermediate -> marts)
The src/* keys match dagster-dbt's names for the dbt sources, so the lineage graph connects end to end.
"""

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import psycopg
from dagster import (
    AssetCheckResult,
    AssetCheckSeverity,
    AssetExecutionContext,
    AssetKey,
    AssetSelection,
    AssetSpec,
    ConfigurableResource,
    DefaultScheduleStatus,
    Definitions,
    MaterializeResult,
    ScheduleDefinition,
    asset,
    asset_check,
    define_asset_job,
    multi_asset,
)
from dagster_dbt import DbtCliResource, DbtProject, dbt_assets

from ufc.config import FILES, database_url
from ufc.db import connect, ensure_schemas
from ufc.identity.job import build_identity
from ufc.ingest.fetch import fetch_file, latest_commit, save_snapshot
from ufc.ingest.load import load_latest

ROOT = Path(__file__).resolve().parents[3]
FRESHNESS_LIMIT = timedelta(days=7)


class GitHubSource(ConfigurableResource):
    """Where the upstream CSVs come from. Tests swap in a subclass that serves fixtures."""

    def client(self) -> httpx.Client:
        return httpx.Client(headers={"User-Agent": "ufc-fingerprints-pipeline"}, follow_redirects=True)


class PostgresResource(ConfigurableResource):
    url: str = database_url()

    def connect(self) -> psycopg.Connection:
        conn = connect(self.url)
        ensure_schemas(conn)
        return conn


@asset(group_name="ingest", description="Download the 6 upstream CSVs; keep each distinct version as a snapshot.")
def raw_snapshots(source: GitHubSource, db: PostgresResource) -> MaterializeResult:
    with source.client() as client, db.connect() as conn:
        commit_sha, committed_at = latest_commit(client)
        new = sum(save_snapshot(conn, fetch_file(client, name, commit_sha)) for name in FILES)
    return MaterializeResult(metadata={
        "new_snapshots": new,
        "source_commit": commit_sha,
        "source_committed_at": committed_at.isoformat(),
    })


SRC_KEYS = {name: AssetKey(["src", name]) for name in FILES}


@multi_asset(
    specs=[AssetSpec(key, deps=[raw_snapshots], group_name="ingest",
                     description=f"Latest snapshot of {name}.csv, loaded as all-text columns.")
           for name, key in SRC_KEYS.items()],
    description="Load each file's latest snapshot into src.<file>, behind the header contract and shrink guard.",
)
def src_tables(context: AssetExecutionContext, db: PostgresResource):
    with db.connect() as conn:
        results = [load_latest(conn, name) for name in FILES]  # raises (and fails the run) on drift or shrink
    for r in results:
        context.log.info(f"{r.file_name}: {'unchanged' if r.skipped else f'{r.row_count} rows'}")
        yield MaterializeResult(asset_key=SRC_KEYS[r.file_name], metadata={
            "rows": r.row_count, "skipped": r.skipped, "sha256": r.sha256,
        })


@asset(key=AssetKey(["src", "fighter_identity"]), deps=list(SRC_KEYS.values()), group_name="ingest",
       description="Resolve every fighter name in every fight to a fighter_id, recording how each was matched.")
def fighter_identity(db: PostgresResource) -> MaterializeResult:
    with db.connect() as conn:
        counts = build_identity(conn)
    return MaterializeResult(metadata={f"matched_{k}": v for k, v in sorted(counts.items())})


def freshness_result(committed_at: datetime, now: datetime) -> AssetCheckResult:
    age = now - committed_at
    return AssetCheckResult(
        passed=age <= FRESHNESS_LIMIT,
        severity=AssetCheckSeverity.WARN,
        metadata={"upstream_age_days": round(age.total_seconds() / 86400, 1)},
        description="Upstream repo should update at least weekly.",
    )


@asset_check(asset=raw_snapshots, description="Warn if the upstream repo hasn't updated in 7 days.")
def source_freshness(source: GitHubSource) -> AssetCheckResult:
    with source.client() as client:
        _, committed_at = latest_commit(client)
    return freshness_result(committed_at, datetime.now(UTC))


dbt_project = DbtProject(
    project_dir=ROOT / "dbt",
    profiles_dir=ROOT / "dbt",
    target=os.environ.get("UFC_DBT_TARGET", "dev"),
)
dbt_project.prepare_if_dev()  # under `dagster dev`, re-parse so the manifest matches the models
if not dbt_project.manifest_path.exists():  # first run on a fresh checkout: parse the dbt project
    from dbt.cli.main import dbtRunner

    dbtRunner().invoke(["parse", "--project-dir", str(dbt_project.project_dir),
                        "--profiles-dir", str(dbt_project.profiles_dir)])


@dbt_assets(manifest=dbt_project.manifest_path)
def ufc_dbt_models(context: AssetExecutionContext, dbt: DbtCliResource):
    yield from dbt.cli(["build"], context=context).stream()


refresh_everything = define_asset_job("refresh_everything", selection=AssetSelection.all())

weekly_refresh = ScheduleDefinition(
    name="weekly_refresh",
    job=refresh_everything,
    cron_schedule="0 10 * * 0",  # Sundays 10:00, after Saturday-night events
    execution_timezone="America/Toronto",
    default_status=DefaultScheduleStatus.RUNNING,  # Dagster schedules start stopped unless told otherwise
)

defs = Definitions(
    assets=[raw_snapshots, src_tables, fighter_identity, ufc_dbt_models],
    asset_checks=[source_freshness],
    jobs=[refresh_everything],
    schedules=[weekly_refresh],
    resources={
        "source": GitHubSource(),
        "db": PostgresResource(),
        "dbt": DbtCliResource(project_dir=dbt_project),
    },
)
