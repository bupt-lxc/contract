from datetime import datetime, timezone
from sc_gr_app.config import AppConfig
from sc_gr_app.db.connection import connect


SCHEMA_VERSION = 20

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
  requester_id TEXT,
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
CREATE INDEX IF NOT EXISTS idx_pos_requester ON pos(requester_id);
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


def _invalid_non_draft_sc_ids(conn) -> list[str]:
    return [
        row["sc_id"]
        for row in conn.execute(
            """
            select sc_id
            from sc_records
            where status != 'draft'
              and (
                request_type is null
                or cost_center is null
                or sc_amount is null
                or service_period_start is null
                or service_period_end is null
              )
            order by sc_id
            """
        )
    ]


def _migrate_v1(conn) -> None:
    conn.executescript(V1_SCHEMA_SQL)
    _record(conn, 1)


def _migrate_v2(conn) -> None:
    if _sc_records_has_v2_constraints(conn):
        _record(conn, 2)
        return

    invalid_sc_ids = _invalid_non_draft_sc_ids(conn)
    if invalid_sc_ids:
        raise RuntimeError(
            "Invalid SC records cannot be migrated: " + ", ".join(invalid_sc_ids)
        )

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


def _migrate_v3(conn) -> None:
    # notification_queue: pending email tasks for the notification script
    conn.execute("""
        CREATE TABLE IF NOT EXISTS notification_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            event_key TEXT NOT NULL,
            to_recipients TEXT NOT NULL,
            cc_recipients TEXT NOT NULL,
            created_at TEXT NOT NULL,
            sent_at TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            error_msg TEXT,
            UNIQUE(entity_type, entity_id, event_key, status)
        )
    """)

    # notification_config: per-SC notification strategy
    conn.execute("""
        CREATE TABLE IF NOT EXISTS notification_config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT NOT NULL DEFAULT 'sc',
            entity_id TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            cc_user_ids TEXT NOT NULL DEFAULT '[]',
            date_thresholds TEXT NOT NULL DEFAULT '[]',
            amount_thresholds TEXT NOT NULL DEFAULT '[]',
            UNIQUE(entity_type, entity_id)
        )
    """)

    # notification_sent_threshold: dedup tracker (each threshold fires once per SC)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS notification_sent_threshold (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            event_key TEXT NOT NULL,
            sent_at TEXT NOT NULL,
            UNIQUE(entity_type, entity_id, event_key)
        )
    """)

    # Default notification settings (only if app_settings table exists)
    if conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='app_settings'"
    ).fetchone():
        defaults = [
            (
                "notify.admin_recipients",
                "[]",
            ),
            (
                "notify.transitions.sc",
                '{"submit":{"to":["notify.admin_recipients"],"cc":["requester"]},'
                '"confirm":{"to":["requester"],"cc":["actor"]},'
                '"approve":{"to":["requester"],"cc":["actor"]},'
                '"deny":{"to":["requester"],"cc":["actor"]},'
                '"close":{"to":["requester","notify.admin_recipients"],"cc":[]},'
                '"revoke":{"to":["requester"],"cc":[]}}',
            ),
            (
                "notify.transitions.po",
                '{"create":{"to":["notify.admin_recipients"],"cc":["requester"]},'
                '"submit":{"to":["notify.admin_recipients"],"cc":["requester"]},'
                '"finish":{"to":["requester","notify.admin_recipients"],"cc":[]}}',
            ),
            (
                "notify.transitions.gr",
                '{"create":{"to":["notify.admin_recipients"],"cc":["requester"]},'
                '"submit":{"to":["notify.admin_recipients"],"cc":["requester"]},'
                '"confirm":{"to":["requester"],"cc":["actor"]},'
                '"approve":{"to":["requester"],"cc":["actor"]},'
                '"cancel":{"to":["requester","notify.admin_recipients"],"cc":[]},'
                '"revoke":{"to":["requester"],"cc":[]}}',
            ),
            ("notify.default_cc", "[]"),
            ("notify.default_date_thresholds", "[6, 3, 1, 0.5]"),
            ("notify.default_amount_thresholds", "[50, 30, 10]"),
        ]
        timestamp = utc_now()
        for key, value in defaults:
            conn.execute(
                "INSERT OR IGNORE INTO app_settings (setting_key, setting_value, updated_at) VALUES (?, ?, ?)",
                (key, value, timestamp),
            )

    _record(conn, 3)


def _migrate_v4(conn) -> None:
    # Add status column to vendors table for enable/disable support
    if not _table_exists(conn, "vendors"):
        _record(conn, 4)
        return
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(vendors)")}
    if "status" not in existing:
        conn.execute("ALTER TABLE vendors ADD COLUMN status TEXT NOT NULL DEFAULT 'active'")
    _record(conn, 4)


def _migrate_v5(conn) -> None:
    # attachments table for SC/PO/GR file attachments
    conn.execute("""
        CREATE TABLE IF NOT EXISTS attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            filename TEXT NOT NULL,
            stored_path TEXT NOT NULL,
            file_size INTEGER NOT NULL,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_attachments_entity ON attachments(entity_type, entity_id)"
    )
    _record(conn, 5)


def _table_exists(conn, table_name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone() is not None


def _migrate_v9(conn) -> None:
    """Add 'draft' status to pos and gr_requests CHECK constraints."""

    # Rebuild pos table with updated CHECK constraint (if it exists)
    if _table_exists(conn, "pos"):
        conn.execute("ALTER TABLE pos RENAME TO pos_old")
        conn.execute("""
            CREATE TABLE pos (
              po_id TEXT PRIMARY KEY,
              sc_id TEXT NOT NULL REFERENCES sc_records(sc_id),
              vendor_id TEXT NOT NULL REFERENCES vendors(vendor_id),
              po_no TEXT,
              requester_id TEXT,
              po_amount REAL NOT NULL CHECK (po_amount > 0),
              status TEXT NOT NULL CHECK (status IN ('draft','po_pending','po_approved','finished')),
              contract_from TEXT,
              contract_to TEXT,
              contract_no TEXT,
              payment_frequency TEXT,
              contract_pos TEXT,
              contract_type TEXT,
              cost_center TEXT,
              purchaser TEXT,
              pending_date TEXT,
              approved_date TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            INSERT INTO pos (
              po_id, sc_id, vendor_id, po_no, requester_id, po_amount, status,
              contract_from, contract_to, contract_no, payment_frequency,
              contract_pos, contract_type, cost_center, purchaser,
              pending_date, approved_date, created_at, updated_at
            )
            SELECT
              po_id, sc_id, vendor_id, po_no,
              (SELECT sc.requester_id FROM sc_records sc WHERE sc.sc_id = pos_old.sc_id) AS requester_id,
              po_amount, status,
              contract_from, contract_to, contract_no, payment_frequency,
              contract_pos, contract_type, cost_center, purchaser,
              pending_date, approved_date, created_at, updated_at
            FROM pos_old
        """)
        conn.execute("DROP TABLE pos_old")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pos_sc ON pos(sc_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pos_vendor ON pos(vendor_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pos_status ON pos(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pos_requester ON pos(requester_id)")

    # Rebuild gr_requests table with updated CHECK constraint (if it exists)
    if _table_exists(conn, "gr_requests"):
        conn.execute("ALTER TABLE gr_requests RENAME TO gr_requests_old")
        conn.execute("""
            CREATE TABLE gr_requests (
              gr_id TEXT PRIMARY KEY,
              po_id TEXT NOT NULL REFERENCES pos(po_id),
              requester_id TEXT NOT NULL REFERENCES users(user_id),
              estimated_amount REAL NOT NULL CHECK (estimated_amount > 0),
              con_value REAL CHECK (con_value >= 0),
              status TEXT NOT NULL CHECK (status IN ('draft','pending','approved','cancelled')),
              remark TEXT,
              created_by TEXT NOT NULL REFERENCES users(user_id),
              created_at TEXT NOT NULL,
              approved_by TEXT REFERENCES users(user_id),
              approved_at TEXT,
              cancelled_by TEXT REFERENCES users(user_id),
              cancelled_at TEXT,
              pending_date TEXT,
              approved_date TEXT
            )
        """)
        conn.execute("""
            INSERT INTO gr_requests (
              gr_id, po_id, requester_id, estimated_amount, con_value, status, remark,
              created_by, created_at, approved_by, approved_at,
              cancelled_by, cancelled_at, pending_date, approved_date
            )
            SELECT
              gr_id, po_id, requester_id, estimated_amount, con_value, status, remark,
              created_by, created_at, approved_by, approved_at,
              cancelled_by, cancelled_at, pending_date, approved_date
            FROM gr_requests_old
        """)
        conn.execute("DROP TABLE gr_requests_old")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_gr_po ON gr_requests(po_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_gr_status ON gr_requests(status)")

    _record(conn, 9)


def _migrate_v13(conn) -> None:
    """Rebuild gr_requests to fix FK references after v12 pos table rebuild."""
    if not _table_exists(conn, "gr_requests"):
        _record(conn, 13)
        return

    conn.execute("ALTER TABLE gr_requests RENAME TO gr_requests_old")
    conn.execute("""
        CREATE TABLE gr_requests (
          gr_id TEXT PRIMARY KEY,
          po_id TEXT NOT NULL REFERENCES pos(po_id),
          requester_id TEXT NOT NULL REFERENCES users(user_id),
          estimated_amount REAL NOT NULL CHECK (estimated_amount > 0),
          con_value REAL CHECK (con_value >= 0),
          status TEXT NOT NULL CHECK (status IN ('draft','pending','approved','cancelled')),
          remark TEXT,
          created_by TEXT NOT NULL REFERENCES users(user_id),
          created_at TEXT NOT NULL,
          approved_by TEXT REFERENCES users(user_id),
          approved_at TEXT,
          cancelled_by TEXT REFERENCES users(user_id),
          cancelled_at TEXT,
          pending_date TEXT,
          approved_date TEXT
        )
    """)
    conn.execute("""
        INSERT INTO gr_requests (
          gr_id, po_id, requester_id, estimated_amount, con_value, status, remark,
          created_by, created_at, approved_by, approved_at,
          cancelled_by, cancelled_at, pending_date, approved_date
        )
        SELECT
          gr_id, po_id, requester_id, estimated_amount, con_value, status, remark,
          created_by, created_at, approved_by, approved_at,
          cancelled_by, cancelled_at, pending_date, approved_date
        FROM gr_requests_old
    """)
    conn.execute("DROP TABLE gr_requests_old")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_gr_po ON gr_requests(po_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_gr_status ON gr_requests(status)")
    _record(conn, 13)


def _migrate_v12(conn) -> None:
    """Simplify PO workflow: replace po_pending/po_approved with activing."""
    if not _table_exists(conn, "pos"):
        _record(conn, 12)
        return

    conn.execute("ALTER TABLE pos RENAME TO pos_old")
    conn.execute("""
        CREATE TABLE pos (
          po_id TEXT PRIMARY KEY,
          sc_id TEXT NOT NULL REFERENCES sc_records(sc_id),
          vendor_id TEXT NOT NULL REFERENCES vendors(vendor_id),
          po_no TEXT,
          requester_id TEXT,
          po_amount REAL NOT NULL CHECK (po_amount > 0),
          status TEXT NOT NULL CHECK (status IN ('draft','activing','finished')),
          contract_from TEXT,
          contract_to TEXT,
          contract_no TEXT,
          payment_frequency TEXT,
          contract_pos TEXT,
          contract_type TEXT,
          cost_center TEXT,
          purchaser TEXT,
          activing_date TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        INSERT INTO pos (
          po_id, sc_id, vendor_id, po_no, requester_id, po_amount, status,
          contract_from, contract_to, contract_no, payment_frequency,
          contract_pos, contract_type, cost_center, purchaser,
          activing_date, created_at, updated_at
        )
        SELECT
          po_id, sc_id, vendor_id, po_no, requester_id, po_amount,
          CASE
            WHEN status IN ('po_pending', 'po_approved') THEN 'activing'
            ELSE status
          END AS status,
          contract_from, contract_to, contract_no, payment_frequency,
          contract_pos, contract_type, cost_center, purchaser,
          COALESCE(approved_date, pending_date, updated_at) AS activing_date,
          created_at, updated_at
        FROM pos_old
    """)
    conn.execute("DROP TABLE pos_old")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pos_sc ON pos(sc_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pos_vendor ON pos(vendor_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pos_status ON pos(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pos_requester ON pos(requester_id)")

    # Rebuild gr_requests to fix FK references to the new pos table
    if _table_exists(conn, "gr_requests"):
        conn.execute("ALTER TABLE gr_requests RENAME TO gr_requests_old")
        conn.execute("""
            CREATE TABLE gr_requests (
              gr_id TEXT PRIMARY KEY,
              po_id TEXT NOT NULL REFERENCES pos(po_id),
              requester_id TEXT NOT NULL REFERENCES users(user_id),
              estimated_amount REAL NOT NULL CHECK (estimated_amount > 0),
              con_value REAL CHECK (con_value >= 0),
              status TEXT NOT NULL CHECK (status IN ('draft','pending','approved','cancelled')),
              remark TEXT,
              created_by TEXT NOT NULL REFERENCES users(user_id),
              created_at TEXT NOT NULL,
              approved_by TEXT REFERENCES users(user_id),
              approved_at TEXT,
              cancelled_by TEXT REFERENCES users(user_id),
              cancelled_at TEXT,
              pending_date TEXT,
              approved_date TEXT
            )
        """)
        conn.execute("""
            INSERT INTO gr_requests (
              gr_id, po_id, requester_id, estimated_amount, con_value, status, remark,
              created_by, created_at, approved_by, approved_at,
              cancelled_by, cancelled_at, pending_date, approved_date
            )
            SELECT
              gr_id, po_id, requester_id, estimated_amount, con_value, status, remark,
              created_by, created_at, approved_by, approved_at,
              cancelled_by, cancelled_at, pending_date, approved_date
            FROM gr_requests_old
        """)
        conn.execute("DROP TABLE gr_requests_old")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_gr_po ON gr_requests(po_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_gr_status ON gr_requests(status)")

    _record(conn, 12)


def _migrate_v11(conn) -> None:
    """Add internal_system_number column to sc_records (FC request type)."""
    if _table_exists(conn, "sc_records"):
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(sc_records)")}
        if "internal_system_number" not in existing:
            conn.execute("ALTER TABLE sc_records ADD COLUMN internal_system_number TEXT")
    _record(conn, 11)


def _migrate_v10(conn) -> None:
    """Add requester_id column to pos table, backfill from SC."""
    if not _table_exists(conn, "pos"):
        _record(conn, 10)
        return

    existing = {row["name"] for row in conn.execute("PRAGMA table_info(pos)")}
    if "requester_id" not in existing:
        conn.execute("ALTER TABLE pos ADD COLUMN requester_id TEXT")

    # Backfill unconditionally — v9 may have created the column with NULLs
    conn.execute(
        """
        UPDATE pos SET requester_id = (
            SELECT sc.requester_id
            FROM sc_records sc
            WHERE sc.sc_id = pos.sc_id
        )
        WHERE pos.requester_id IS NULL
        """
    )

    _record(conn, 10)


def _migrate_v8(conn) -> None:
    # add changes_summary column to audit_logs for human-readable change details
    if _table_exists(conn, "audit_logs"):
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(audit_logs)")}
        if "changes_summary" not in existing:
            conn.execute(
                "ALTER TABLE audit_logs ADD COLUMN changes_summary TEXT"
            )
    _record(conn, 8)


def _migrate_v7(conn) -> None:
    # Add new fields to sc_records, pos, gr_requests
    if _table_exists(conn, "sc_records"):
        sc_cols = {row["name"] for row in conn.execute("PRAGMA table_info(sc_records)")}
        if "asset" not in sc_cols:
            conn.execute("ALTER TABLE sc_records ADD COLUMN asset TEXT NOT NULL DEFAULT 'N'")
        if "asset_nums" not in sc_cols:
            conn.execute("ALTER TABLE sc_records ADD COLUMN asset_nums TEXT")
        if "pending_date" not in sc_cols:
            conn.execute("ALTER TABLE sc_records ADD COLUMN pending_date TEXT")
        if "approved_date" not in sc_cols:
            conn.execute("ALTER TABLE sc_records ADD COLUMN approved_date TEXT")

    if _table_exists(conn, "pos"):
        po_cols = {row["name"] for row in conn.execute("PRAGMA table_info(pos)")}
        if "contract_pos" not in po_cols:
            conn.execute("ALTER TABLE pos ADD COLUMN contract_pos TEXT")
        if "contract_type" not in po_cols:
            conn.execute("ALTER TABLE pos ADD COLUMN contract_type TEXT")
        if "cost_center" not in po_cols:
            conn.execute("ALTER TABLE pos ADD COLUMN cost_center TEXT")
        if "purchaser" not in po_cols:
            conn.execute("ALTER TABLE pos ADD COLUMN purchaser TEXT")
        if "pending_date" not in po_cols:
            conn.execute("ALTER TABLE pos ADD COLUMN pending_date TEXT")
        if "approved_date" not in po_cols:
            conn.execute("ALTER TABLE pos ADD COLUMN approved_date TEXT")

    if _table_exists(conn, "gr_requests"):
        gr_cols = {row["name"] for row in conn.execute("PRAGMA table_info(gr_requests)")}
        if "pending_date" not in gr_cols:
            conn.execute("ALTER TABLE gr_requests ADD COLUMN pending_date TEXT")
        if "approved_date" not in gr_cols:
            conn.execute("ALTER TABLE gr_requests ADD COLUMN approved_date TEXT")

    _record(conn, 7)


def _migrate_v14(conn) -> None:
    """Create sc_vendors junction table for SC-vendor many-to-many relationship."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sc_vendors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sc_id TEXT NOT NULL REFERENCES sc_records(sc_id) ON DELETE CASCADE,
            vendor_id TEXT NOT NULL REFERENCES vendors(vendor_id),
            UNIQUE(sc_id, vendor_id)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_sc_vendors_sc ON sc_vendors(sc_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_sc_vendors_vendor ON sc_vendors(vendor_id)"
    )
    _record(conn, 14)


def _migrate_v15(conn) -> None:
    """Add gr_no column to gr_requests."""
    if _table_exists(conn, "gr_requests"):
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(gr_requests)")}
        if "gr_no" not in existing:
            conn.execute("ALTER TABLE gr_requests ADD COLUMN gr_no TEXT")
    _record(conn, 15)


def _migrate_v16(conn) -> None:
    """Add manager_confirm status to SC and GR workflows, and confirmed_at column."""
    # Rebuild sc_records to add manager_confirm to CHECK constraint + confirmed_at
    if _table_exists(conn, "sc_records"):
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(sc_records)")}
        if "confirmed_at" not in existing or "manager_confirm" not in _sc_records_sql(conn):
            conn.execute("ALTER TABLE sc_records RENAME TO sc_records_old")
            conn.execute("""
                CREATE TABLE sc_records (
                  sc_id TEXT PRIMARY KEY,
                  sc_no TEXT,
                  requester_id TEXT NOT NULL REFERENCES users(user_id),
                  request_type TEXT CHECK (request_type IN ('material', 'service', 'fixed_asset', 'FC')),
                  cost_center INTEGER,
                  sc_amount REAL CHECK (sc_amount IS NULL OR sc_amount > 0),
                  service_period_start TEXT,
                  service_period_end TEXT,
                  status TEXT NOT NULL CHECK (status IN ('draft', 'manager_confirm', 'pending', 'approved', 'denied', 'closed')),
                  description TEXT,
                  created_by TEXT NOT NULL REFERENCES users(user_id),
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  approved_by TEXT REFERENCES users(user_id),
                  approved_at TEXT,
                  closed_at TEXT,
                  confirmed_at TEXT,
                  asset TEXT NOT NULL DEFAULT 'N',
                  asset_nums TEXT,
                  pending_date TEXT,
                  approved_date TEXT,
                  internal_system_number TEXT,
                  CHECK (
                    status = 'draft'
                    OR status = 'manager_confirm'
                    OR (
                      request_type IS NOT NULL
                      AND cost_center IS NOT NULL
                      AND sc_amount IS NOT NULL
                      AND service_period_start IS NOT NULL
                      AND service_period_end IS NOT NULL
                    )
                  )
                )
            """)
            conn.execute("""
                INSERT INTO sc_records (
                  sc_id, sc_no, requester_id, request_type, cost_center, sc_amount,
                  service_period_start, service_period_end, status, description,
                  created_by, created_at, updated_at, approved_by, approved_at, closed_at,
                  confirmed_at, asset, asset_nums, pending_date, approved_date,
                  internal_system_number
                )
                SELECT
                  sc_id, sc_no, requester_id, request_type, cost_center, sc_amount,
                  service_period_start, service_period_end, status, description,
                  created_by, created_at, updated_at, approved_by, approved_at, closed_at,
                  NULL, asset, asset_nums, pending_date, approved_date,
                  internal_system_number
                FROM sc_records_old
            """)
            conn.execute("DROP TABLE sc_records_old")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sc_records_requester ON sc_records(requester_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sc_records_status ON sc_records(status)")

    # Rebuild gr_requests to add manager_confirm to CHECK constraint + confirmed_at
    if _table_exists(conn, "gr_requests"):
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(gr_requests)")}
        if "confirmed_at" not in existing:
            conn.execute("ALTER TABLE gr_requests RENAME TO gr_requests_old")
            conn.execute("""
                CREATE TABLE gr_requests (
                  gr_id TEXT PRIMARY KEY,
                  gr_no TEXT,
                  po_id TEXT NOT NULL REFERENCES pos(po_id),
                  requester_id TEXT NOT NULL REFERENCES users(user_id),
                  estimated_amount REAL NOT NULL CHECK (estimated_amount > 0),
                  con_value REAL CHECK (con_value >= 0),
                  status TEXT NOT NULL CHECK (status IN ('draft', 'manager_confirm', 'pending', 'approved', 'cancelled')),
                  remark TEXT,
                  created_by TEXT NOT NULL REFERENCES users(user_id),
                  created_at TEXT NOT NULL,
                  approved_by TEXT REFERENCES users(user_id),
                  approved_at TEXT,
                  cancelled_by TEXT REFERENCES users(user_id),
                  cancelled_at TEXT,
                  confirmed_at TEXT,
                  pending_date TEXT,
                  approved_date TEXT
                )
            """)
            conn.execute("""
                INSERT INTO gr_requests (
                  gr_id, gr_no, po_id, requester_id, estimated_amount, con_value, status,
                  remark, created_by, created_at, approved_by, approved_at,
                  cancelled_by, cancelled_at, confirmed_at, pending_date, approved_date
                )
                SELECT
                  gr_id, gr_no, po_id, requester_id, estimated_amount, con_value, status,
                  remark, created_by, created_at, approved_by, approved_at,
                  cancelled_by, cancelled_at, NULL, pending_date, approved_date
                FROM gr_requests_old
            """)
            conn.execute("DROP TABLE gr_requests_old")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_gr_po ON gr_requests(po_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_gr_status ON gr_requests(status)")

    # Update notification transition defaults for new confirm/revoke transitions
    if _table_exists(conn, "app_settings"):
        timestamp = utc_now()
        sc_transitions = (
            '{"submit":{"to":["notify.admin_recipients"],"cc":["requester"]},'
            '"confirm":{"to":["requester"],"cc":["actor"]},'
            '"approve":{"to":["requester"],"cc":["actor"]},'
            '"deny":{"to":["requester"],"cc":["actor"]},'
            '"close":{"to":["requester","notify.admin_recipients"],"cc":[]},'
            '"revoke":{"to":["requester"],"cc":[]}}'
        )
        conn.execute(
            "INSERT OR REPLACE INTO app_settings (setting_key, setting_value, updated_at) VALUES (?, ?, ?)",
            ("notify.transitions.sc", sc_transitions, timestamp),
        )
        gr_transitions = (
            '{"create":{"to":["notify.admin_recipients"],"cc":["requester"]},'
            '"submit":{"to":["notify.admin_recipients"],"cc":["requester"]},'
            '"confirm":{"to":["requester"],"cc":["actor"]},'
            '"approve":{"to":["requester"],"cc":["actor"]},'
            '"cancel":{"to":["requester","notify.admin_recipients"],"cc":[]},'
            '"revoke":{"to":["requester"],"cc":[]}}'
        )
        conn.execute(
            "INSERT OR REPLACE INTO app_settings (setting_key, setting_value, updated_at) VALUES (?, ?, ?)",
            ("notify.transitions.gr", gr_transitions, timestamp),
        )

    _record(conn, 16)


def _migrate_v17(conn) -> None:
    """Add vendor_snapshot column to sc_vendors for SC vendor history preservation."""
    if _table_exists(conn, "sc_vendors"):
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(sc_vendors)")}
        if "vendor_snapshot" not in existing:
            conn.execute("ALTER TABLE sc_vendors ADD COLUMN vendor_snapshot TEXT")
    _record(conn, 17)


def _migrate_v18(conn) -> None:
    """Add company_name_cn column to vendors table."""
    if _table_exists(conn, "vendors"):
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(vendors)")}
        if "company_name_cn" not in existing:
            conn.execute("ALTER TABLE vendors ADD COLUMN company_name_cn TEXT")
    _record(conn, 18)


def _migrate_v19(conn) -> None:
    """Add tax_rate column to gr_requests."""
    if _table_exists(conn, "gr_requests"):
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(gr_requests)")}
        if "tax_rate" not in existing:
            conn.execute("ALTER TABLE gr_requests ADD COLUMN tax_rate REAL")
    _record(conn, 19)


def _migrate_v20(conn) -> None:
    """Add goods_service_description, confirmation_name, delivery_from, delivery_to, last_delivery to gr_requests."""
    if _table_exists(conn, "gr_requests"):
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(gr_requests)")}
        for col in ("goods_service_description", "confirmation_name", "delivery_from", "delivery_to", "last_delivery"):
            if col not in existing:
                conn.execute(f"ALTER TABLE gr_requests ADD COLUMN {col} TEXT")
    _record(conn, 20)


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
            if 3 not in _applied_versions(conn):
                conn.execute("BEGIN")
                _migrate_v3(conn)
                conn.commit()
            if 4 not in _applied_versions(conn):
                conn.execute("BEGIN")
                _migrate_v4(conn)
                conn.commit()
            if 5 not in _applied_versions(conn):
                conn.execute("BEGIN")
                _migrate_v5(conn)
                conn.commit()
            if 7 not in _applied_versions(conn):
                conn.execute("BEGIN")
                _migrate_v7(conn)
                conn.commit()
            if 8 not in _applied_versions(conn):
                conn.execute("BEGIN")
                _migrate_v8(conn)
                conn.commit()
            if 9 not in _applied_versions(conn):
                conn.execute("PRAGMA foreign_keys = OFF")
                conn.execute("BEGIN")
                _migrate_v9(conn)
                conn.commit()
                conn.execute("PRAGMA foreign_keys = ON")
            if 10 not in _applied_versions(conn):
                conn.execute("BEGIN")
                _migrate_v10(conn)
                conn.commit()
            if 11 not in _applied_versions(conn):
                conn.execute("BEGIN")
                _migrate_v11(conn)
                conn.commit()
            if 12 not in _applied_versions(conn):
                conn.execute("PRAGMA foreign_keys = OFF")
                conn.execute("BEGIN")
                _migrate_v12(conn)
                conn.commit()
                conn.execute("PRAGMA foreign_keys = ON")
            if 13 not in _applied_versions(conn):
                conn.execute("PRAGMA foreign_keys = OFF")
                conn.execute("BEGIN")
                _migrate_v13(conn)
                conn.commit()
                conn.execute("PRAGMA foreign_keys = ON")
            if 14 not in _applied_versions(conn):
                conn.execute("BEGIN")
                _migrate_v14(conn)
                conn.commit()
            if 15 not in _applied_versions(conn):
                conn.execute("BEGIN")
                _migrate_v15(conn)
                conn.commit()
            if 16 not in _applied_versions(conn):
                conn.execute("PRAGMA foreign_keys = OFF")
                conn.execute("PRAGMA legacy_alter_table = ON")
                conn.execute("BEGIN")
                _migrate_v16(conn)
                conn.commit()
                conn.execute("PRAGMA legacy_alter_table = OFF")
                conn.execute("PRAGMA foreign_keys = ON")
            if 17 not in _applied_versions(conn):
                conn.execute("BEGIN")
                _migrate_v17(conn)
                conn.commit()
            if 18 not in _applied_versions(conn):
                conn.execute("BEGIN")
                _migrate_v18(conn)
                conn.commit()
            if 19 not in _applied_versions(conn):
                conn.execute("BEGIN")
                _migrate_v19(conn)
                conn.commit()
            if 20 not in _applied_versions(conn):
                conn.execute("BEGIN")
                _migrate_v20(conn)
                conn.commit()
        except Exception:
            conn.rollback()
            conn.execute("PRAGMA legacy_alter_table = OFF")
            conn.execute("PRAGMA foreign_keys = ON")
            raise
