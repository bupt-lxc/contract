from datetime import datetime, timezone
from pathlib import Path

from sc_gr_app.config import AppConfig
from sc_gr_app.db.connection import connect


SCHEMA_VERSION = 2


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _applied_versions(conn) -> set[int]:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
          version INTEGER PRIMARY KEY,
          applied_at TEXT NOT NULL
        );
        """
    )
    return {
        row["version"]
        for row in conn.execute("select version from schema_migrations")
    }


def _record(conn, version: int) -> None:
    conn.execute(
        "insert or ignore into schema_migrations(version, applied_at) values (?, ?)",
        (version, utc_now()),
    )


def _migrate_v1(conn) -> None:
    schema_path = Path(__file__).with_name("schema.sql")
    conn.executescript(schema_path.read_text(encoding="utf-8"))
    _record(conn, 1)


def _migrate_v2(conn) -> None:
    columns = {
        row["name"]: row
        for row in conn.execute("PRAGMA table_info(sc_records)")
    }
    status_row = conn.execute(
        "select sql from sqlite_master where type = 'table' and name = 'sc_records'"
    ).fetchone()
    status_sql = status_row["sql"] if status_row else ""

    if "draft" in status_sql and columns["request_type"]["notnull"] == 0:
        _record(conn, 2)
        return

    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("ALTER TABLE sc_records RENAME TO sc_records_old")
    conn.execute(
        """
        CREATE TABLE sc_records (
          sc_id TEXT PRIMARY KEY,
          sc_no TEXT,
          requester_id TEXT NOT NULL REFERENCES users(user_id),
          request_type TEXT CHECK (request_type IN ('material', 'service', 'fixed_asset', 'FC')),
          cost_center INTEGER,
          sc_amount REAL CHECK (sc_amount IS NULL OR sc_amount > 0),
          service_period_start TEXT,
          service_period_end TEXT,
          status TEXT NOT NULL CHECK (status IN ('draft', 'pending', 'approved', 'denied', 'closed')),
          description TEXT,
          created_by TEXT NOT NULL REFERENCES users(user_id),
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          approved_by TEXT REFERENCES users(user_id),
          approved_at TEXT,
          closed_at TEXT
        )
        """
    )
    conn.execute(
        """
        INSERT INTO sc_records (
          sc_id, sc_no, requester_id, request_type, cost_center, sc_amount,
          service_period_start, service_period_end, status, description,
          created_by, created_at, updated_at, approved_by, approved_at, closed_at
        )
        SELECT
          sc_id, sc_no, requester_id, request_type, cost_center, sc_amount,
          service_period_start, service_period_end, status, description,
          created_by, created_at, updated_at, approved_by, approved_at, closed_at
        FROM sc_records_old
        """
    )
    conn.execute("DROP TABLE sc_records_old")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_sc_records_requester ON sc_records(requester_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_sc_records_status ON sc_records(status)"
    )
    conn.execute("PRAGMA foreign_keys = ON")
    _record(conn, 2)


def migrate(config: AppConfig) -> None:
    with connect(config) as conn:
        try:
            conn.execute("BEGIN")
            applied = _applied_versions(conn)
            if 1 not in applied:
                _migrate_v1(conn)
            if 2 not in _applied_versions(conn):
                _migrate_v2(conn)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
