from ufc.db import ensure_schemas


def test_bootstrap_is_idempotent(db):
    ensure_schemas(db)
    ensure_schemas(db)
    rows = db.execute(
        """
        select table_schema || '.' || table_name
        from information_schema.tables
        where (table_schema, table_name) in
              (('raw', 'file_snapshots'), ('src', 'load_log'), ('src', 'fighter_identity'))
        order by 1
        """
    ).fetchall()
    assert [r[0] for r in rows] == ["raw.file_snapshots", "src.fighter_identity", "src.load_log"]
