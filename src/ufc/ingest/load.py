"""Load the latest snapshot of each file into src.<file>, behind a header contract and a shrink guard."""

import csv
import io
import re
from dataclasses import dataclass

import psycopg
from psycopg import sql

from ufc.config import EXPECTED_COLUMNS

SHRINK_LIMIT = 0.90  # refuse a load with fewer than 90% of the previous load's rows


class SchemaDriftError(Exception):
    """The upstream header no longer matches the contract."""


class ShrinkGuardError(Exception):
    """The upstream file lost too many rows; likely truncated or broken."""


@dataclass(frozen=True)
class LoadResult:
    file_name: str
    sha256: str
    row_count: int
    previous_row_count: int | None
    skipped: bool


def column_name(header: str) -> str:
    name = header.lower().replace("%", "pct")
    return re.sub(r"[^a-z0-9]+", "_", name).strip("_")


def validate_header(name: str, header: list[str]) -> None:
    expected = EXPECTED_COLUMNS[name]
    if header != expected:
        missing = [c for c in expected if c not in header]
        unexpected = [c for c in header if c not in expected]
        raise SchemaDriftError(
            f"{name}: header changed. missing={missing} unexpected={unexpected} "
            f"(expected {expected}, got {header})"
        )


def _parse(content: bytes) -> tuple[list[str], list[list[str]]]:
    rows = list(csv.reader(io.StringIO(content.decode("utf-8-sig"))))
    if not rows:
        return [], []
    return rows[0], rows[1:]


def load_latest(conn: psycopg.Connection, name: str) -> LoadResult:
    snap = conn.execute(
        """
        select sha256, content from raw.file_snapshots
        where file_name = %s order by last_seen_at desc, snapshot_id desc limit 1
        """,
        (name,),
    ).fetchone()
    if snap is None:
        raise LookupError(f"no snapshot for {name}")
    sha, content = snap
    last = conn.execute(
        "select sha256, row_count from src.load_log where file_name = %s order by id desc limit 1", (name,)
    ).fetchone()
    previous_rows = last[1] if last else None
    if last and last[0] == sha:
        conn.rollback()
        return LoadResult(name, sha, last[1], last[1], skipped=True)

    header, rows = _parse(bytes(content))
    validate_header(name, header)
    for i, row in enumerate(rows, start=1):
        if len(row) != len(header):
            raise SchemaDriftError(f"{name}: row {i} has {len(row)} fields, expected {len(header)}")
    if previous_rows and len(rows) < SHRINK_LIMIT * previous_rows:
        conn.rollback()
        raise ShrinkGuardError(
            f"{name}: {len(rows)} rows vs {previous_rows} last time (below {SHRINK_LIMIT:.0%}); not loading"
        )

    table = sql.Identifier("src", name)
    columns = [column_name(h) for h in header] + ["_row_num", "_snapshot_sha"]
    try:
        conn.execute(sql.SQL("drop table if exists {}").format(table))
        conn.execute(
            sql.SQL("create table {} ({})").format(
                table,
                sql.SQL(", ").join(
                    sql.SQL("{} {}").format(sql.Identifier(c), sql.SQL("int" if c == "_row_num" else "text"))
                    for c in columns
                ),
            )
        )
        with conn.cursor().copy(
            sql.SQL("copy {} ({}) from stdin").format(table, sql.SQL(", ").join(map(sql.Identifier, columns)))
        ) as copy:
            for i, row in enumerate(rows, start=1):
                copy.write_row([*row, i, sha])
        conn.execute(
            "insert into src.load_log (file_name, sha256, row_count, previous_row_count) values (%s, %s, %s, %s)",
            (name, sha, len(rows), previous_rows),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return LoadResult(name, sha, len(rows), previous_rows, skipped=False)
