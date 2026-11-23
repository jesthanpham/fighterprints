import os

import pytest

TEST_DATABASE_URL = os.environ.get(
    "UFC_TEST_DATABASE_URL", "postgresql://ufc:ufc@localhost:5433/ufc_test"
)
SCHEMAS = ("raw", "src", "staging", "intermediate", "marts")


@pytest.fixture(scope="session")
def db():
    """A fresh test database: every pipeline schema dropped, then bootstrapped."""
    from ufc.db import connect, ensure_schemas

    conn = connect(TEST_DATABASE_URL)
    for schema in SCHEMAS:
        conn.execute(f"drop schema if exists {schema} cascade")
    conn.commit()
    ensure_schemas(conn)
    yield conn
    conn.close()
