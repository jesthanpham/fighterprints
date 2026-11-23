"""Database connection and bootstrap."""

from importlib.resources import files

import psycopg

from ufc.config import database_url


def connect(url: str | None = None) -> psycopg.Connection:
    return psycopg.connect(url or database_url(), autocommit=False)


def ensure_schemas(conn: psycopg.Connection) -> None:
    """Create the raw/src schemas and pipeline-owned tables. Safe to run repeatedly."""
    sql = files("ufc").joinpath("sql/bootstrap.sql").read_text()
    conn.execute(sql)
    conn.commit()
