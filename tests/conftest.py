import os

import pytest

TEST_DATABASE_URL = os.environ.get(
    "UFC_TEST_DATABASE_URL", "postgresql://ufc:ufc@localhost:5433/ufc_test"
)
SCHEMAS = ("raw", "src", "staging", "intermediate", "marts")


@pytest.fixture(scope="session")
def _conn():
    from ufc.db import connect

    conn = connect(TEST_DATABASE_URL)
    yield conn
    conn.close()


def reset(conn) -> None:
    """Drop every pipeline schema and bootstrap again, so a test starts from nothing."""
    from ufc.db import ensure_schemas

    conn.rollback()
    for schema in SCHEMAS:
        conn.execute(f"drop schema if exists {schema} cascade")
    conn.commit()
    ensure_schemas(conn)


@pytest.fixture
def db(_conn):
    """A freshly bootstrapped test database, per test."""
    reset(_conn)
    return _conn
