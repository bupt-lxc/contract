"""Create the packaged empty initial SQLite database."""
import argparse
import csv
import gc
import os
import shutil
import tempfile
from pathlib import Path

from sc_gr_app.config import AppConfig
from sc_gr_app.db.connection import connect
from sc_gr_app.db.migrations import migrate
from sc_gr_app.errors import NotFound
from sc_gr_app.services.user_service import seed_users


BUSINESS_TABLES = ("users", "vendors", "sc_records", "pos", "gr_requests")


def _find_admin_user_id(config: AppConfig, conn) -> str:
    """Find an existing admin user, or bootstrap one."""
    admin = conn.execute(
        "SELECT user_id, machine_id FROM users WHERE role = 'admin' AND status = 'active' LIMIT 1"
    ).fetchone()
    if admin:
        return admin["user_id"]
    # Bootstrap
    user_id = "U-86183"
    conn.execute(
        "INSERT INTO users (user_id, machine_id, user_name, role, email, status, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
        (user_id, "86183", "Import Admin", "admin", None, "active"),
    )
    conn.commit()
    return user_id


def _import_vendors_from_xlsx(config: AppConfig, docs_dir: Path, admin_id: str) -> int:
    """Import vendors from Vendors xlsx. Returns count of imported vendors."""
    import openpyxl
    from datetime import datetime, timezone

    xlsx_path = docs_dir / "Vendors_2026-07-07.xlsx"
    if not xlsx_path.exists():
        print(f"  [SKIP] Vendor xlsx not found: {xlsx_path}")
        return 0

    SCOPE_FIXES = {
        "Secirity": "Security",
        "engineering Service": "Engineering Service",
        "Materials": "Others",
        "Driver/Test car rental": "Driver",
        "insurance": "Insurance",
    }
    SUPPORTED_SCOPES = {
        "Transportation", "Engineering Service", "Equipment", "Parts",
        "Driver", "Test car rental", "General Service", "Dealers",
        "Import&Export&cusoms clearance", "Insurance", "Harness",
        "Maintenance&Calibration", "Security", "Testing support",
        "Fix asset", "Materials", "Others",
    }

    ts = datetime.now(timezone.utc).isoformat()
    wb = openpyxl.load_workbook(xlsx_path)
    ws = wb["Sheet1"]
    imported = 0
    skipped = 0

    with connect(config) as conn:
        for i, row in enumerate(ws.iter_rows(min_row=2, values_only=True)):
            _vid = str(row[0]).strip() if row[0] else ""
            vendor_name = str(row[1] or "").strip()
            company_cn = str(row[2] or "").strip()
            ksrm_code = str(row[3] or "").strip() if row[3] else ""
            scope = str(row[4] or "").strip()
            contact = str(row[5] or "").strip() if row[5] else ""
            phone = str(row[6] or "").strip() if row[6] else ""
            email = str(row[7] or "").strip() if row[7] else ""

            if not vendor_name or not scope:
                skipped += 1
                continue

            if scope in SCOPE_FIXES:
                print(f"  [!] Fixing scope: '{scope}' -> '{SCOPE_FIXES[scope]}' ({vendor_name})")
                scope = SCOPE_FIXES[scope]

            if scope not in SUPPORTED_SCOPES:
                skipped += 1
                continue

            vid = _vid
            if not vid or vid == vendor_name:
                row_max = conn.execute(
                    "SELECT COALESCE(MAX(CAST(SUBSTR(vendor_id, 2) AS INTEGER)), 0) + 1 AS n FROM vendors"
                ).fetchone()
                vid = f"V{row_max['n']:06d}"

            try:
                conn.execute(
                    """INSERT INTO vendors (
                      vendor_id, vendor_name, ksrm_vendor_code, company_name_cn,
                      contact_person, phone, service_scope, email,
                      description, inquiry_history, created_by, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (vid, vendor_name, ksrm_code or None, company_cn or None,
                     contact or None, phone or None, scope, email or None,
                     None, None, admin_id, ts, ts),
                )
                conn.commit()
                imported += 1
            except Exception as e:
                skipped += 1
                print(f"  [WARN] Row {i+1} '{vendor_name}': {e}")

    print(f"  Vendors imported: {imported}, skipped: {skipped}")
    return imported


def _load_csv(docs_dir: Path, filename: str) -> list[dict]:
    path = docs_dir / filename
    if not path.exists():
        print(f"  [SKIP] {filename} not found")
        return []
    with open(path, "r", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _seed_users_from_xlsx(config: AppConfig, docs_dir: Path) -> int:
    """Seed additional users from users.xlsx (INSERT OR IGNORE so existing users are safe)."""
    import openpyxl
    from datetime import datetime, timezone

    xlsx_path = docs_dir / "users.xlsx"
    if not xlsx_path.exists():
        return 0

    ts = datetime.now(timezone.utc).isoformat()
    wb = openpyxl.load_workbook(xlsx_path)
    ws = wb["Tabelle1"]
    added = 0
    with connect(config) as conn:
        for row in ws.iter_rows(min_row=2, values_only=True):
            machine_id, name, email, role = row[0], row[1], row[2], row[3]
            if not machine_id:
                continue
            machine_id = str(machine_id).strip()
            name = str(name).strip() if name else ""
            email = str(email).strip() if email else ""
            role = str(role).strip() if role else "requester"
            user_id = f"U-{machine_id}"
            conn.execute(
                """INSERT OR IGNORE INTO users (
                  user_id, machine_id, user_name, role, email, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'active', ?, ?)""",
                (user_id, machine_id, name, role, email, ts, ts),
            )
            added += 1
        conn.commit()
    return added


def _import_production_data(config: AppConfig, docs_dir: Path) -> None:
    """Import vendors, SCs, POs, GRs into a fresh production DB."""
    from sc_gr_app.services.import_service import import_scs, import_pos, import_grs

    with connect(config) as conn:
        admin_id = _find_admin_user_id(config, conn)

    admin = {"user_id": admin_id, "role": "admin", "machine_id": admin_id.split("-")[1]}

    # 0. Seed additional users from users.xlsx
    print("=== Seeding users ===")
    seeded = _seed_users_from_xlsx(config, docs_dir)
    print(f"  Users from xlsx: {seeded}")

    # 1. Import vendors from xlsx
    print("=== Importing vendors ===")
    _import_vendors_from_xlsx(config, docs_dir, admin_id)

    # 2. Import SCs
    print("=== Importing SCs ===")
    sc_rows = _load_csv(docs_dir, "import_sc.csv")
    if sc_rows:
        for r in sc_rows:
            r["calloff_po_id"] = None
        result = import_scs(config, admin, sc_rows)
        print(f"  {result}")
    else:
        print("  No SC rows to import")

    # 3. Import POs
    print("=== Importing POs ===")
    po_rows = _load_csv(docs_dir, "import_po.csv")
    if po_rows:
        # Build ISN -> sc_no lookup
        with connect(config) as conn:
            sc_lookup = {}
            for row in conn.execute(
                "SELECT sc_no, internal_system_number FROM sc_records "
                "WHERE internal_system_number IS NOT NULL AND internal_system_number != ''"
            ).fetchall():
                isn = row["internal_system_number"].strip()
                if isn not in sc_lookup:
                    sc_lookup[isn] = row["sc_no"]

        for r in po_rows:
            r["po_id"] = ""
            r["sc_id"] = ""
            sc_no = (r.get("sc_no") or "").strip()
            if (r.get("request_type") or "").strip() == "FC":
                r["sc_id"] = None
                continue
            if not sc_no:
                po_no = (r.get("po_no") or "").strip()
                if po_no and po_no in sc_lookup:
                    r["sc_no"] = sc_lookup[po_no]
                    print(f"  [RESOLVE] PO {po_no} -> SC {sc_lookup[po_no]}")

        def _has_sc_no_or_is_fc(r):
            if (r.get("request_type") or "").strip() == "FC":
                return True
            return bool((r.get("sc_no") or "").strip())

        valid_po_rows = [r for r in po_rows if _has_sc_no_or_is_fc(r)]
        skipped = len(po_rows) - len(valid_po_rows)
        if skipped:
            skipped_nos = [r.get("po_no", "?") for r in po_rows if not _has_sc_no_or_is_fc(r)]
            print(f"  [SKIP] {skipped} PO rows with no sc_no match: {skipped_nos}")

        if valid_po_rows:
            result = import_pos(config, admin, valid_po_rows)
            print(f"  {result}")
        else:
            print("  No valid PO rows to import")
    else:
        print("  No PO rows to import")

    # 4. Import GRs
    print("=== Importing GRs ===")
    gr_rows = _load_csv(docs_dir, "import_gr.csv")
    if gr_rows:
        for r in gr_rows:
            r["po_id"] = ""
        result = import_grs(config, admin, gr_rows)
        print(f"  {result}")
    else:
        print("  No GR rows to import")

    # 5. Post-import: resolve calloff_po_id
    print("=== Post-import calloff_po_id resolution ===")
    with connect(config) as conn:
        updated = conn.execute(
            """UPDATE sc_records
               SET calloff_po_id = (
                 SELECT po_id FROM pos
                 WHERE pos.po_no = sc_records.internal_system_number
                   AND pos.po_no IS NOT NULL AND pos.po_no != ''
                 ORDER BY pos.created_at DESC
                 LIMIT 1
               )
               WHERE request_type = 'call_off'
                 AND (calloff_po_id IS NULL OR calloff_po_id = '')
                 AND internal_system_number IS NOT NULL
                 AND internal_system_number != ''"""
        ).rowcount
        conn.commit()
        print(f"  Resolved calloff_po_id for {updated} call-off SCs")


def create_empty_initial_database(target_path: Path) -> bool:
    """Create a latest-schema empty template DB when target_path is missing.

    Returns True when a new file is created. Existing files are left untouched.
    """
    target_path = Path(target_path)
    if target_path.exists():
        return False

    target_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        temp_db = tmp_dir / "initial.sqlite3"
        temp_db.touch()
        migrate(AppConfig(db_path=temp_db, lock_dir=tmp_dir / "locks"))
        _assert_empty_business_tables(temp_db)
        shutil.copy2(temp_db, target_path)
        gc.collect()
    return True


def create_production_database_if_missing(target_path: Path, docs_dir: Path | None = None) -> bool:
    """Create the shared production DB when it does not exist.

    The production DB starts with schema + default users + imported business data.
    Existing database files are never modified.
    """
    target_path = Path(target_path)
    if target_path.exists():
        return False

    target_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        temp_db = tmp_dir / "sc_gr.sqlite3"
        temp_db.touch()
        config = AppConfig(db_path=temp_db, lock_dir=tmp_dir / "locks")
        migrate(config)
        seed_users(config)

        # Import business data if docs_dir is provided
        if docs_dir and docs_dir.exists():
            _import_production_data(config, docs_dir)

        shutil.copy2(temp_db, target_path)
        gc.collect()
    return True


def _assert_empty_business_tables(db_path: Path, allow_users: bool = False) -> None:
    import sqlite3

    conn = sqlite3.connect(db_path)
    try:
        for table in BUSINESS_TABLES:
            count = conn.execute(f"select count(*) from {table}").fetchone()[0]
            if allow_users and table == "users":
                continue
            if count != 0:
                raise RuntimeError(f"{table} must be empty in initial database")
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "target",
        nargs="?",
        default=Path(__file__).parent / "initial.sqlite3",
        type=Path,
    )
    parser.add_argument("--production", action="store_true")
    parser.add_argument("--docs-dir", type=Path, default=None,
                       help="Path to docs/ directory with CSV data files for initial import")
    args = parser.parse_args(argv)
    if args.production:
        # Resolve docs_dir: explicit --docs-dir, or auto-detect relative to this file
        docs_dir = args.docs_dir
        if docs_dir is None:
            auto_docs = Path(__file__).resolve().parent.parent.parent / "docs"
            if auto_docs.exists():
                docs_dir = auto_docs
        created = create_production_database_if_missing(args.target, docs_dir)
        if created:
            print(f"Created production database: {args.target}")
        else:
            print(f"Production database already exists, skipped: {args.target}")
    else:
        created = create_empty_initial_database(args.target)
        if created:
            print(f"Created empty initial database: {args.target}")
        else:
            print(f"Initial database already exists, skipped: {args.target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
