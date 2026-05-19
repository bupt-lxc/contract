import sqlite3

from sc_gr_app.db.connection import connect
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


def test_migration_records_version_once(app_config):
    migrate(app_config)
    migrate(app_config)

    with sqlite3.connect(app_config.db_path) as conn:
        rows = conn.execute(
            "select version, applied_at from schema_migrations"
        ).fetchall()

    assert len(rows) == 1
    assert rows[0][0] == 1
    assert rows[0][1]


def test_connection_enables_required_pragmas(app_config):
    with connect(app_config) as conn:
        foreign_keys = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]

    assert foreign_keys == 1
    assert journal_mode == "delete"


def test_gr_requests_schema_uses_po_link_and_con_value(app_config):
    migrate(app_config)

    with sqlite3.connect(app_config.db_path) as conn:
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(gr_requests)")
        }

    assert {"po_id", "con_value"}.issubset(columns)
    assert not {
        "sc_id",
        "reason",
        "finance_reference_no",
        "actual_amount",
    }.intersection(columns)


def test_open_po_amount_is_not_stored(app_config):
    migrate(app_config)

    with sqlite3.connect(app_config.db_path) as conn:
        table_names = [
            row[0]
            for row in conn.execute(
                "select name from sqlite_master where type='table'"
            )
        ]
        columns = {
            column[1]
            for table_name in table_names
            for column in conn.execute(f"PRAGMA table_info({table_name})")
        }

    assert "open_po_amount" not in columns
