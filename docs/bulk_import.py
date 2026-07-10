"""Bulk import SC, PO, GR, vendor CSVs using the import service functions."""
import csv
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ["SC_GR_DEV"] = "1"

from sc_gr_app.config import default_config
from sc_gr_app.services.import_service import import_scs, import_pos, import_grs
from sc_gr_app.services.vendor_service import create_vendor

config = default_config()
BASE = os.path.dirname(os.path.abspath(__file__))

def _get_admin(config):
    """Find an existing admin user, or create one if needed."""
    from sc_gr_app.db.connection import connect
    with connect(config) as conn:
        admin = conn.execute(
            "SELECT user_id, machine_id FROM users WHERE role = 'admin' AND status = 'active' LIMIT 1"
        ).fetchone()
        if admin:
            return {"user_id": admin["user_id"], "role": "admin", "machine_id": admin["machine_id"]}
    # No admin exists — bootstrap one directly
    with connect(config) as conn:
        user_id = "U-86183"
        conn.execute(
            "INSERT INTO users (user_id, machine_id, user_name, role, email, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
            (user_id, "86183", "Import Admin", "admin", None, "active"),
        )
        conn.commit()
    return {"user_id": user_id, "role": "admin", "machine_id": "86183"}

ADMIN = _get_admin(config)

def load_csv(filename):
    path = os.path.join(BASE, filename)
    if not os.path.exists(path):
        print(f"  [SKIP] {filename} not found")
        return []
    with open(path, "r", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))

# 1. Import vendors
print("=== Importing vendors ===")
vendor_rows = load_csv("import_vendor.csv")
vendor_imported = 0
for v in vendor_rows:
    vname = v.get("vendor_name", "").strip()
    if not vname:
        continue
    try:
        create_vendor(config, ADMIN, {
            "vendor_name": vname,
            "service_scope": v.get("service_scope", ""),
            "ksrm_vendor_code": v.get("ksrm_vendor_code", ""),
            "company_name_cn": v.get("company_name_cn", ""),
            "contact_person": v.get("contact_person", ""),
            "phone": v.get("phone", ""),
            "email": v.get("email", ""),
            "description": v.get("description", ""),
            "inquiry_history": v.get("inquiry_history", ""),
        })
        vendor_imported += 1
    except Exception as e:
        print(f"  [WARN] Vendor '{vname}': {e}")
print(f"  Imported: {vendor_imported}")

# 2. Import SCs (must come before POs so sc_id references are available)
# Clear calloff_po_id on fresh import -- POs don't exist yet, so any
# pre-populated values are stale PO numbers that would fail FK checks.
# The post-import step below resolves calloff_po_id correctly.
print("=== Importing SCs ===")
sc_rows = load_csv("import_sc.csv")
if sc_rows:
    for r in sc_rows:
        r["calloff_po_id"] = None
    result = import_scs(config, ADMIN, sc_rows)
    print(f"  {result}")
else:
    print("  No SC rows to import")

# 3. Import POs
# Preprocess PO rows:
# - Clear po_id so import service auto-generates it
# - Clear stale sc_id so _resolve_po_sc_id resolves by sc_no
# - For rows without sc_no, try to find matching SC by internal_system_number = po_no
# - Filter out rows that still can't be resolved (import service is all-or-nothing)
print("=== Importing POs ===")
po_rows = load_csv("import_po.csv")
po_resolved = 0
po_skipped = 0
if po_rows:
    from sc_gr_app.db.connection import connect
    with connect(config) as conn:
        # Build lookup: internal_system_number -> sc_no (for resolving FC POs)
        sc_lookup = {}
        for row in conn.execute(
            "SELECT sc_no, internal_system_number FROM sc_records "
            "WHERE internal_system_number IS NOT NULL AND internal_system_number != ''"
        ).fetchall():
            isn = row["internal_system_number"].strip()
            if isn not in sc_lookup:
                sc_lookup[isn] = row["sc_no"]

    for r in po_rows:
        r["po_id"] = ""          # let import service auto-generate
        r["sc_id"] = ""           # let _resolve_po_sc_id resolve by sc_no
        sc_no = (r.get("sc_no") or "").strip()
        if not sc_no:
            po_no = (r.get("po_no") or "").strip()
            if po_no and po_no in sc_lookup:
                r["sc_no"] = sc_lookup[po_no]
                print(f"  [RESOLVE] PO {po_no} -> SC {sc_lookup[po_no]}")
                po_resolved += 1

    # Filter out rows that still don't have sc_no (can't be linked to any SC)
    valid_po_rows = [r for r in po_rows if (r.get("sc_no") or "").strip()]
    po_skipped = len(po_rows) - len(valid_po_rows)

    if po_skipped:
        skipped_nos = [r.get("po_no", "?") for r in po_rows if not (r.get("sc_no") or "").strip()]
        print(f"  [SKIP] {po_skipped} PO rows with no sc_no match: {skipped_nos}")

    if valid_po_rows:
        result = import_pos(config, ADMIN, valid_po_rows)
        print(f"  {result}")
    else:
        print("  No valid PO rows to import")
else:
    print("  No PO rows to import")

# 4. Import GRs
# Preprocess: clear stale po_id; _resolve_gr_po_id will set it from po_no.
# gr_id is auto-generated by import_grs.
print("=== Importing GRs ===")
gr_rows = load_csv("import_gr.csv")
if gr_rows:
    for r in gr_rows:
        r["po_id"] = ""
    result = import_grs(config, ADMIN, gr_rows)
    print(f"  {result}")
else:
    print("  No GR rows to import")

# 5. Post-import: resolve calloff_po_id for SCs that weren't resolved
# at CSV generation time (fresh DB has no POs yet during CSV generation).
print("=== Post-import calloff_po_id resolution ===")
with connect(config) as conn:
    # Match SC.internal_system_number to PO.po_no and set calloff_po_id
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

print("\nDone.")
