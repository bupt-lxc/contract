import sqlite3

from sc_gr_app.db.migrations import migrate


def test_migration_creates_core_tables(app_config):
    migrate(app_config)

    with sqlite3.connect(app_config.db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "select name from sqlite_master where type='table'"
            )
        }

    assert {
        "schema_migrations",
        "users",
        "sc_records",
        "vendors",
        "pos",
        "gr_requests",
        "audit_logs",
        "app_settings",
    }.issubset(tables)
