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
  asset TEXT NOT NULL DEFAULT 'N',
  asset_nums TEXT,
  pending_date TEXT,
  approved_date TEXT,
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
  contract_pos TEXT,
  contract_type TEXT,
  cost_center TEXT,
  purchaser TEXT,
  pending_date TEXT,
  approved_date TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS gr_requests (
  gr_id TEXT PRIMARY KEY,
  gr_no TEXT,
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
  cancelled_at TEXT,
  pending_date TEXT,
  approved_date TEXT
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
  changes_summary TEXT,
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
