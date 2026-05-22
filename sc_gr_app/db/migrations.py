from datetime import datetime, timezone
from sc_gr_app.config import AppConfig
from sc_gr_app.db.connection import connect


SCHEMA_VERSION = 2

V1_SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
  version INTEGER PRIMARY KEY,
  applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
  user_id TEXT PRIMARY KEY,
  machine_id TEXT NOT NULL UNIQUE,
  user_name TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('admin', 'requester')),
  email TEXT,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled')),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sc_records (
  sc_id TEXT PRIMARY KEY,
  sc_no TEXT,
  requester_id TEXT NOT NULL REFERENCES users(user_id),
  request_type TEXT NOT NULL CHECK (request_type IN ('material', 'service', 'fixed_asset', 'FC')),
  cost_center INTEGER NOT NULL,
  sc_amount REAL NOT NULL CHECK (sc_amount > 0),
  service_period_start TEXT NOT NULL,
  service_period_end TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'denied', 'closed')),
  description TEXT,
  created_by TEXT NOT NULL REFERENCES users(user_id),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  approved_by TEXT REFERENCES users(user_id),
  approved_at TEXT,
  closed_at TEXT
);

CREATE TABLE IF NOT EXISTS vendors (
  vendor_id TEXT PRIMARY KEY,
  vendor_name TEXT NOT NULL,
  ksrm_vendor_code TEXT,
  contact_person TEXT,
  phone TEXT,
  service_scope TEXT NOT NULL CHECK (service_scope IN (
    'Transportation',
    'engineering Service',
    'Equipment',
    'Parts',
    'Driver',
    'Test car rental',
    'General Service',
    'Dealers',
    'Import&Export&cusoms clearance',
    'Insurance',
    'Harness',
    'Maintenance',
    'Security',
    'Testing support',
    'Others'
  )),
  email TEXT,
  description TEXT,
  inquiry_history TEXT,
  created_by TEXT NOT NULL REFERENCES users(user_id),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pos (
  po_id TEXT PRIMARY KEY,
  sc_id TEXT NOT NULL REFERENCES sc_records(sc_id),
  vendor_id TEXT NOT NULL REFERENCES vendors(vendor_id),
  po_no TEXT,
  po_amount REAL NOT NULL CHECK (po_amount > 0),
  status TEXT NOT NULL CHECK (status IN ('po_pending', 'po_approved', 'finished')),
  contract_from TEXT,
  contract_to TEXT,
  contract_no TEXT,
  payment_frequency TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS gr_requests (
  gr_id TEXT PRIMARY KEY,
  po_id TEXT NOT NULL REFERENCES pos(po_id),
  requester_id TEXT NOT NULL REFERENCES users(user_id),
  estimated_amount REAL NOT NULL CHECK (estimated_amount > 0),
  con_value REAL CHECK (con_value >= 0),
  status TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'cancelled')),
  remark TEXT,
  created_by TEXT NOT NULL REFERENCES users(user_id),
  created_at TEXT NOT NULL,
  approved_by TEXT REFERENCES users(user_id),
  approved_at TEXT,
  cancelled_by TEXT REFERENCES users(user_id),
  cancelled_at TEXT
);

CREATE TABLE IF NOT EXISTS audit_logs (
  log_id TEXT PRIMARY KEY,
  action_type TEXT NOT NULL,
  object_type TEXT NOT NULL,
  object_id TEXT NOT NULL,
  sc_id TEXT,
  operator_id TEXT NOT NULL,
  machine_id TEXT NOT NULL,
  before_json TEXT,
  after_json TEXT,
  operation_mode TEXT NOT NULL DEFAULT 'normal',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS app_settings (
  setting_key TEXT PRIMARY KEY,
  setting_value TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sc_records_requester ON sc_records(requester_id);
CREATE INDEX IF NOT EXISTS idx_sc_records_status ON sc_records(status);
CREATE INDEX IF NOT EXISTS idx_vendors_name ON vendors(vendor_name);
CREATE INDEX IF NOT EXISTS idx_pos_sc ON pos(sc_id);
CREATE INDEX IF NOT EXISTS idx_pos_vendor ON pos(vendor_id);
CREATE INDEX IF NOT EXISTS idx_pos_status ON pos(status);
CREATE INDEX IF NOT EXISTS idx_gr_po ON gr_requests(po_id);
CREATE INDEX IF NOT EXISTS idx_gr_status ON gr_requests(status);
CREATE INDEX IF NOT EXISTS idx_audit_sc ON audit_logs(sc_id);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_logs(created_at);
"""


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


def _sc_records_sql(conn) -> str:
    row = conn.execute(
        "select sql from sqlite_master where type = 'table' and name = 'sc_records'"
    ).fetchone()
    return row["sql"] if row else ""


def _sc_records_has_v2_constraints(conn) -> bool:
    columns = {
        row["name"]: row
        for row in conn.execute("PRAGMA table_info(sc_records)")
    }
    status_sql = _sc_records_sql(conn)
    return (
        "draft" in status_sql
        and columns.get("request_type", {})["notnull"] == 0
        and "status = 'draft'" in status_sql
        and "request_type IS NOT NULL" in status_sql
        and "cost_center IS NOT NULL" in status_sql
        and "sc_amount IS NOT NULL" in status_sql
        and "service_period_start IS NOT NULL" in status_sql
        and "service_period_end IS NOT NULL" in status_sql
    )


def _migrate_v1(conn) -> None:
    conn.executescript(V1_SCHEMA_SQL)
    _record(conn, 1)


def _migrate_v2(conn) -> None:
    if _sc_records_has_v2_constraints(conn):
        _record(conn, 2)
        return

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
          closed_at TEXT,
          CHECK (
            status = 'draft'
            OR (
              request_type IS NOT NULL
              AND cost_center IS NOT NULL
              AND sc_amount IS NOT NULL
              AND service_period_start IS NOT NULL
              AND service_period_end IS NOT NULL
            )
          )
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
    _record(conn, 2)


def migrate(config: AppConfig) -> None:
    with connect(config) as conn:
        try:
            applied = _applied_versions(conn)
            if 1 not in applied:
                conn.execute("BEGIN")
                _migrate_v1(conn)
                conn.commit()
            if 2 not in _applied_versions(conn):
                conn.execute("PRAGMA foreign_keys = OFF")
                conn.execute("PRAGMA legacy_alter_table = ON")
                conn.execute("BEGIN")
                _migrate_v2(conn)
                conn.commit()
                conn.execute("PRAGMA legacy_alter_table = OFF")
                conn.execute("PRAGMA foreign_keys = ON")
            elif not _sc_records_has_v2_constraints(conn):
                conn.execute("PRAGMA foreign_keys = OFF")
                conn.execute("PRAGMA legacy_alter_table = ON")
                conn.execute("BEGIN")
                _migrate_v2(conn)
                conn.commit()
                conn.execute("PRAGMA legacy_alter_table = OFF")
                conn.execute("PRAGMA foreign_keys = ON")
        except Exception:
            conn.rollback()
            conn.execute("PRAGMA legacy_alter_table = OFF")
            conn.execute("PRAGMA foreign_keys = ON")
            raise
