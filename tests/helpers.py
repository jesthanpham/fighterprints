"""Test helpers: snapshot and load the fixture CSVs the same way the pipeline does."""

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from ufc.config import FILES
from ufc.ingest.fetch import FetchedFile, count_rows, save_snapshot

FIXTURES = Path(__file__).parent / "fixtures" / "csv"


def snapshot(conn, name: str, content: bytes) -> FetchedFile:
    f = FetchedFile(
        name=name, content=content, sha256=hashlib.sha256(content).hexdigest(),
        row_count=count_rows(content), source_commit="test", fetched_at=datetime.now(UTC),
    )
    save_snapshot(conn, f)
    return f


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES / f"{name}.csv").read_bytes()


def load_fixture_csvs(conn) -> None:
    from ufc.ingest.load import load_latest

    for name in FILES:
        snapshot(conn, name, fixture_bytes(name))
        load_latest(conn, name)


DBT_DIR = str(Path(__file__).resolve().parents[1] / "dbt")


def dbt(*args: str) -> bool:
    """Run a dbt command against the test target; True on success."""
    from dbt.cli.main import dbtRunner

    result = dbtRunner().invoke([*args, "--target", "test", "--project-dir", DBT_DIR, "--profiles-dir", DBT_DIR])
    return result.success
