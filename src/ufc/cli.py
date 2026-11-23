"""Run the pipeline without Dagster: python -m ufc.cli {fetch,load,identity,all}."""

import argparse
import sys
from pathlib import Path

import httpx

from ufc.config import FILES
from ufc.db import connect, ensure_schemas
from ufc.identity.job import build_identity
from ufc.ingest.fetch import fetch_file, latest_commit, save_snapshot
from ufc.ingest.load import load_latest

DBT_DIR = Path(__file__).resolve().parents[2] / "dbt"


def fetch(conn) -> None:
    with httpx.Client(headers={"User-Agent": "ufc-fingerprints-pipeline"}, follow_redirects=True) as client:
        sha, when = latest_commit(client)
        print(f"upstream commit {sha[:10]} ({when:%Y-%m-%d})")
        for name in FILES:
            f = fetch_file(client, name, sha)
            print(f"{name}: {f.row_count} rows, {'new snapshot' if save_snapshot(conn, f) else 'unchanged'}")


def load(conn) -> None:
    for name in FILES:
        r = load_latest(conn, name)
        print(f"{name}: {'skipped (unchanged)' if r.skipped else f'loaded {r.row_count} rows'}")


def identity(conn) -> None:
    for method, n in sorted(build_identity(conn).items()):
        print(f"{method}: {n}")


def dbt_build() -> bool:
    from dbt.cli.main import dbtRunner

    return dbtRunner().invoke(["build", "--project-dir", str(DBT_DIR), "--profiles-dir", str(DBT_DIR)]).success


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ufc", description=__doc__)
    parser.add_argument("step", choices=["fetch", "load", "identity", "all"])
    step = parser.parse_args(argv).step
    with connect() as conn:
        ensure_schemas(conn)
        if step in ("fetch", "all"):
            fetch(conn)
        if step in ("load", "all"):
            load(conn)
        if step in ("identity", "all"):
            identity(conn)
    if step == "all" and not dbt_build():
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
