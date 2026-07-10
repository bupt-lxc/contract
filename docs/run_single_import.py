"""
Single-row import script: import SC -> PO -> GR one record at a time.
Marks errors in import CSVs and full_data.csv.
Classifies errors as "data_integrity" or "system".
"""
import csv
import os
import sys
import traceback
import sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.stdout.reconfigure(encoding="utf-8")

os.environ["SC_GR_DEV"] = "1"

from sc_gr_app.config import default_config
from sc_gr_app.db.connection import connect
from sc_gr_app.services.import_service import (
    import_scs, import_pos, import_grs,
    _map_import_columns, _SC_COLUMN_ALIASES, _PO_COLUMN_ALIASES, _GR_COLUMN_ALIASES,
    _validate_sc_rows, _validate_po_rows, _validate_gr_rows,
    _is_template_meta_row,
)
from sc_gr_app.errors import ValidationError

BASE = os.path.dirname(os.path.abspath(__file__))
IMPORT_SC = os.path.join(BASE, "import_sc.csv")
IMPORT_PO = os.path.join(BASE, "import_po.csv")
IMPORT_GR = os.path.join(BASE, "import_gr.csv")
FULL_DATA = os.path.join(BASE, "full_data.csv")


def read_csv(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, fieldnames):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def classify_error(error_msg: str, exception_type: str = "") -> str:
    """Classify an error as data_integrity or system."""
    # System-level schema mismatch: pos table CHECK constraint only allows 'FC'
    # but import data has 'call_off' and 'new' — this is a schema bug, not data issue.
    if "request_type IN ('FC')" in error_msg:
        return "system"
    integrity_patterns = [
        "is required", "not found", "Invalid", "unrecognized date format",
        "is not a valid", "should be empty", "required for",
        "matches", "appears", "missing", "Duplicate", "already exists",
        "UNIQUE constraint", "NOT NULL constraint", "FOREIGN KEY constraint",
        "CHECK constraint", "IntegrityError",
    ]
    msg_lower = error_msg.lower()
    for pat in integrity_patterns:
        if pat.lower() in msg_lower:
            return "data_integrity"
    if exception_type and "IntegrityError" in exception_type:
        return "data_integrity"
    return "system"


# ── Resolve admin user ──────────────────────────────────────────────
config = default_config()
with connect(config) as conn:
    admin = dict(conn.execute(
        "SELECT * FROM users WHERE role = 'admin' AND user_id LIKE 'U-V2%' LIMIT 1"
    ).fetchone())
    print(f"Using admin user: {admin['user_id']} ({admin['user_name']})")

current_user = {"user_id": admin["user_id"], "machine_id": admin["machine_id"]}

# ── Read CSVs ───────────────────────────────────────────────────────
sc_rows = read_csv(IMPORT_SC)
po_rows = read_csv(IMPORT_PO)
gr_rows = read_csv(IMPORT_GR)
full_rows = read_csv(FULL_DATA)

print(f"\nLoaded: {len(sc_rows)} SC, {len(po_rows)} PO, {len(gr_rows)} GR, {len(full_rows)} full_data rows")

# ── Build vendor name -> vendor_id mapping from DB ────────────────────
def normalize_name(name: str) -> str:
    """Normalize vendor name for matching."""
    n = name.strip().lower()
    # Remove punctuation variations
    for ch in ".,，。、（）()":
        n = n.replace(ch, "")
    # Collapse whitespace
    n = " ".join(n.split())
    return n

with connect(config) as conn:
    db_vendors = conn.execute("SELECT vendor_id, vendor_name, company_name_cn FROM vendors").fetchall()
vendor_name_to_id = {}
for v in db_vendors:
    vid = v["vendor_id"]
    # English name
    vendor_name_to_id[normalize_name(v["vendor_name"])] = vid
    vendor_name_to_id[v["vendor_name"].strip()] = vid
    # Chinese name
    cn = (v["company_name_cn"] or "").strip()
    if cn:
        vendor_name_to_id[normalize_name(cn)] = vid
        vendor_name_to_id[cn] = vid
print(f"Loaded {len(vendor_name_to_id)} vendor name mappings from DB")

# ── Build sc_no -> vendor_name and po_no -> vendor_name from full_data ──
sc_no_to_vendor_name = {}
po_no_to_vendor_name = {}
for fd in full_rows:
    sc_no = str(fd.get("sc_no", "")).strip()
    po_no = str(fd.get("po_no", "")).strip()
    vendor_name = str(fd.get("vendor", "")).strip()
    if sc_no and vendor_name:
        sc_no_to_vendor_name[sc_no] = vendor_name
    if po_no and vendor_name:
        po_no_to_vendor_name[po_no] = vendor_name
print(f"Built {len(sc_no_to_vendor_name)} sc_no->vendor_name, {len(po_no_to_vendor_name)} po_no->vendor_name mappings")

# ── Resolve vendor_id by name for a given row ─────────────────────────
def resolve_vendor_id(import_row, sc_no="", po_no="") -> tuple:
    """
    Returns (vendor_id, vendor_name, error_msg_or_None).
    Looks up vendor_name from full_data using sc_no or po_no,
    then resolves vendor_id from DB by name.
    """
    # Find vendor name
    vendor_name = ""
    if sc_no:
        vendor_name = sc_no_to_vendor_name.get(sc_no, "")
    if not vendor_name and po_no:
        vendor_name = po_no_to_vendor_name.get(po_no, "")

    if not vendor_name:
        # Fallback: try the vendor_id from import row (if it happens to match DB)
        orig_vid = str(import_row.get("vendor_id", "")).strip()
        if orig_vid:
            with connect(config) as conn:
                exists = conn.execute("SELECT 1 FROM vendors WHERE vendor_id = ?", (orig_vid,)).fetchone()
            if exists:
                return orig_vid, "", None
        return "", "", f"Cannot determine vendor name from full_data (sc_no={sc_no}, po_no={po_no})"

    # Look up vendor_id by name
    db_vid = vendor_name_to_id.get(normalize_name(vendor_name))
    if not db_vid:
        # Try exact match
        db_vid = vendor_name_to_id.get(vendor_name.strip())
    if db_vid:
        return db_vid, vendor_name, None
    else:
        return "", vendor_name, f"Vendor '{vendor_name}' not found in DB (looked up via {'SC ' + sc_no if sc_no else 'PO ' + po_no})"

# Also build a po_no -> sc_no mapping for PO rows
po_no_to_sc_no = {}
for fd in full_rows:
    po_no = str(fd.get("po_no", "")).strip()
    sc_no = str(fd.get("sc_no", "")).strip()
    if po_no and sc_no:
        po_no_to_sc_no[po_no] = sc_no
print(f"Built {len(po_no_to_sc_no)} po_no->sc_no mappings")

# ── Track results ───────────────────────────────────────────────────
all_system_errors = []  # (phase, row_idx, error_msg, traceback)

# Add error columns to import CSVs
for rows in [sc_rows, po_rows, gr_rows]:
    for r in rows:
        r["import_error"] = ""
        r["error_type"] = ""

# Ensure full_data has error columns
fd_fieldnames = list(full_rows[0].keys()) if full_rows else []
if "sc_import_error" not in fd_fieldnames:
    fd_fieldnames.append("sc_import_error")
if "po_import_error" not in fd_fieldnames:
    fd_fieldnames.append("po_import_error")
if "gr_import_error" not in fd_fieldnames:
    fd_fieldnames.append("gr_import_error")
for r in full_rows:
    r.setdefault("sc_import_error", "")
    r.setdefault("po_import_error", "")
    r.setdefault("gr_import_error", "")


def find_full_data_row_by_sc_no(sc_no):
    """Find full_data rows matching sc_no."""
    matches = []
    for fd in full_rows:
        if str(fd.get("sc_no", "")).strip() == str(sc_no).strip():
            matches.append(fd)
    return matches


def find_full_data_row_by_po_no(po_no):
    """Find full_data rows matching po_no."""
    matches = []
    for fd in full_rows:
        if str(fd.get("po_no", "")).strip() == str(po_no).strip():
            matches.append(fd)
    return matches


def find_full_data_row_by_gr(po_no, gr_no):
    """Find full_data rows matching po_no and gr_no (conf_no)."""
    matches = []
    for fd in full_rows:
        fd_po = str(fd.get("po_no", "")).strip()
        fd_conf = str(fd.get("conf_no", "")).strip()
        if fd_po == str(po_no).strip() and fd_conf == str(gr_no).strip():
            matches.append(fd)
    return matches


def append_to_full_data_error(fd_rows, error_msg, col_name):
    """Append error message to full_data rows, avoiding duplicates."""
    for fd in fd_rows:
        existing = str(fd.get(col_name, "")).strip()
        if error_msg not in existing:
            if existing:
                fd[col_name] = existing + "; " + error_msg
            else:
                fd[col_name] = error_msg
        # Mark action as error for failed imports (not for warnings)
        if "[WARN]" not in error_msg:
            fd["action"] = "error"


# ═══════════════════════════════════════════════════════════════════════
# PHASE 1: Import SC (one by one)
# ═══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("PHASE 1: Importing SC records (one by one)")
print("=" * 70)

sc_success = 0
sc_failed = 0
sc_skipped_dup = 0

for i, row in enumerate(sc_rows):
    sc_no = str(row.get("sc_no", "")).strip()
    if not sc_no:
        row["import_error"] = "SC NO is empty"
        row["error_type"] = "data_integrity"
        sc_failed += 1
        continue

    # Resolve vendor_id by name
    vendor_remap_warning = ""
    orig_vid = str(row.get("vendor_id", "")).strip()
    if orig_vid:
        db_vid, vname, vname_err = resolve_vendor_id(row, sc_no=sc_no)
        if vname_err:
            row["import_error"] = vname_err
            row["error_type"] = "data_integrity"
            sc_failed += 1
            print(f"  [{i+1}/{len(sc_rows)}] FAIL [data_integrity] SC {sc_no}: {vname_err}")
            fd_matches = find_full_data_row_by_sc_no(sc_no)
            if fd_matches:
                append_to_full_data_error(fd_matches, vname_err, "sc_import_error")
            continue
        if db_vid:
            row["vendor_id"] = db_vid
            if db_vid != orig_vid:
                vendor_remap_warning = f"[WARN] vendor_id remapped: {orig_vid} -> {db_vid} ({vname})"
                print(f"  [{i+1}/{len(sc_rows)}] {vendor_remap_warning}")

    try:
        result = import_scs(config, current_user, [row])
        if result.get("ok"):
            if result.get("skipped_duplicate", 0) > 0:
                sc_skipped_dup += 1
                print(f"  [{i+1}/{len(sc_rows)}] SKIP (duplicate) SC {sc_no}")
            else:
                sc_success += 1
                print(f"  [{i+1}/{len(sc_rows)}] OK  SC {sc_no}")
                if vendor_remap_warning:
                    row["import_error"] = vendor_remap_warning
                    row["error_type"] = "warning"
        else:
            errors = result.get("errors", [])
            error_msgs = []
            for e in errors:
                msg = e.get("message", str(e))
                error_msgs.append(msg)
            combined = "; ".join(error_msgs)
            error_type = classify_error(combined)
            row["import_error"] = combined
            row["error_type"] = error_type
            sc_failed += 1
            print(f"  [{i+1}/{len(sc_rows)}] FAIL [{error_type}] SC {sc_no}: {combined}")
            # Find in full_data
            fd_matches = find_full_data_row_by_sc_no(sc_no)
            if fd_matches:
                append_to_full_data_error(fd_matches, combined, "sc_import_error")
            else:
                print(f"    WARNING: SC {sc_no} not found in full_data.csv")
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        error_type = classify_error(error_msg, type(e).__name__)
        row["import_error"] = error_msg
        row["error_type"] = error_type
        sc_failed += 1
        tb = traceback.format_exc()
        print(f"  [{i+1}/{len(sc_rows)}] FAIL [{error_type}] SC {sc_no}: {error_msg}")
        if error_type == "system":
            all_system_errors.append(("SC", i+1, error_msg, tb))
        fd_matches = find_full_data_row_by_sc_no(sc_no)
        if fd_matches:
            append_to_full_data_error(fd_matches, error_msg, "sc_import_error")
        else:
            print(f"    WARNING: SC {sc_no} not found in full_data.csv")

print(f"\nSC Import Summary: {sc_success} success, {sc_failed} failed, {sc_skipped_dup} skipped (duplicate)")

# Build sc_no -> sc_id mapping from DB for PO rows
with connect(config) as conn:
    sc_rows_db = conn.execute("SELECT sc_id, sc_no FROM sc_records").fetchall()
sc_no_to_sc_id = {r["sc_no"]: r["sc_id"] for r in sc_rows_db if r["sc_no"]}
print(f"\nBuilt {len(sc_no_to_sc_id)} sc_no->sc_id mappings from DB")

# Fill sc_id in PO rows
sc_id_filled = 0
sc_id_missing = 0
for row in po_rows:
    sc_no = str(row.get("sc_no", "")).strip()
    if sc_no and sc_no in sc_no_to_sc_id:
        row["sc_id"] = sc_no_to_sc_id[sc_no]
        sc_id_filled += 1
    elif sc_no:
        sc_id_missing += 1
        print(f"  WARNING: PO sc_no={sc_no} has no matching sc_id in DB")
print(f"Filled sc_id for {sc_id_filled} PO rows, {sc_id_missing} missing")

# ═══════════════════════════════════════════════════════════════════════
# PHASE 2: Import PO (one by one)
# ═══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("PHASE 2: Importing PO records (one by one)")
print("=" * 70)

po_success = 0
po_failed = 0
po_skipped_dup = 0

for i, row in enumerate(po_rows):
    po_no = str(row.get("po_no", "")).strip()
    if not po_no:
        row["import_error"] = "PO NO is empty"
        row["error_type"] = "data_integrity"
        po_failed += 1
        continue

    # Resolve vendor_id by name (always, even if empty)
    vendor_remap_warning = ""
    orig_vid = str(row.get("vendor_id", "")).strip()
    sc_no_from_fd = po_no_to_sc_no.get(po_no, "")
    db_vid, vname, vname_err = resolve_vendor_id(row, sc_no=sc_no_from_fd, po_no=po_no)
    if vname_err:
        row["import_error"] = vname_err
        row["error_type"] = "data_integrity"
        po_failed += 1
        print(f"  [{i+1}/{len(po_rows)}] FAIL [data_integrity] PO {po_no}: {vname_err}")
        fd_matches = find_full_data_row_by_po_no(po_no)
        if fd_matches:
            append_to_full_data_error(fd_matches, vname_err, "po_import_error")
        continue
    if db_vid:
        row["vendor_id"] = db_vid
        if db_vid != orig_vid:
            vendor_remap_warning = f"[WARN] vendor_id remapped: {orig_vid} -> {db_vid} ({vname})"
            print(f"  [{i+1}/{len(po_rows)}] {vendor_remap_warning}")

    # Convert empty sc_id to None (FK constraint on sc_records)
    if not row.get("sc_id"):
        row["sc_id"] = None

    try:
        result = import_pos(config, current_user, [row])
        if result.get("ok"):
            if result.get("skipped_duplicate", 0) > 0:
                po_skipped_dup += 1
                print(f"  [{i+1}/{len(po_rows)}] SKIP (duplicate) PO {po_no}")
            else:
                po_success += 1
                print(f"  [{i+1}/{len(po_rows)}] OK  PO {po_no}")
                if vendor_remap_warning:
                    row["import_error"] = vendor_remap_warning
                    row["error_type"] = "warning"
        else:
            errors = result.get("errors", [])
            error_msgs = []
            for e in errors:
                msg = e.get("message", str(e))
                error_msgs.append(msg)
            combined = "; ".join(error_msgs)
            error_type = classify_error(combined)
            row["import_error"] = combined
            row["error_type"] = error_type
            po_failed += 1
            print(f"  [{i+1}/{len(po_rows)}] FAIL [{error_type}] PO {po_no}: {combined}")
            fd_matches = find_full_data_row_by_po_no(po_no)
            if fd_matches:
                append_to_full_data_error(fd_matches, combined, "po_import_error")
            else:
                print(f"    WARNING: PO {po_no} not found in full_data.csv")
            # Also mark by sc_no if present
            sc_no = str(row.get("sc_no", "")).strip()
            if sc_no:
                fd_sc_matches = find_full_data_row_by_sc_no(sc_no)
                # filter to those also matching this PO
                for fd in fd_sc_matches:
                    fd_po = str(fd.get("po_no", "")).strip()
                    if fd_po == po_no or not fd_po:
                        append_to_full_data_error([fd], f"[PO:{po_no}] {combined}", "po_import_error")
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        error_type = classify_error(error_msg, type(e).__name__)
        row["import_error"] = error_msg
        row["error_type"] = error_type
        po_failed += 1
        tb = traceback.format_exc()
        print(f"  [{i+1}/{len(po_rows)}] FAIL [{error_type}] PO {po_no}: {error_msg}")
        if error_type == "system":
            all_system_errors.append(("PO", i+1, error_msg, tb))
        fd_matches = find_full_data_row_by_po_no(po_no)
        if fd_matches:
            append_to_full_data_error(fd_matches, error_msg, "po_import_error")
        else:
            print(f"    WARNING: PO {po_no} not found in full_data.csv")

print(f"\nPO Import Summary: {po_success} success, {po_failed} failed, {po_skipped_dup} skipped (duplicate)")

# ═══════════════════════════════════════════════════════════════════════
# PHASE 3: Import GR (one by one)
# ═══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("PHASE 3: Importing GR records (one by one)")
print("=" * 70)

gr_success = 0
gr_failed = 0
gr_skipped_dup = 0

for i, row in enumerate(gr_rows):
    gr_no = str(row.get("gr_no", "")).strip()
    po_no = str(row.get("po_no", "")).strip()
    if not gr_no:
        row["import_error"] = "GR NO is empty"
        row["error_type"] = "data_integrity"
        gr_failed += 1
        continue

    try:
        result = import_grs(config, current_user, [row])
        if result.get("ok"):
            if result.get("skipped_duplicate", 0) > 0:
                gr_skipped_dup += 1
                print(f"  [{i+1}/{len(gr_rows)}] SKIP (duplicate) GR {gr_no}")
            else:
                gr_success += 1
                print(f"  [{i+1}/{len(gr_rows)}] OK  GR {gr_no} (PO {po_no})")
        else:
            errors = result.get("errors", [])
            error_msgs = []
            for e in errors:
                msg = e.get("message", str(e))
                error_msgs.append(msg)
            combined = "; ".join(error_msgs)
            error_type = classify_error(combined)
            row["import_error"] = combined
            row["error_type"] = error_type
            gr_failed += 1
            print(f"  [{i+1}/{len(gr_rows)}] FAIL [{error_type}] GR {gr_no}: {combined}")
            fd_matches = find_full_data_row_by_gr(po_no, gr_no)
            if fd_matches:
                append_to_full_data_error(fd_matches, combined, "gr_import_error")
            else:
                print(f"    WARNING: GR {gr_no} (PO {po_no}) not found in full_data.csv")
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        error_type = classify_error(error_msg, type(e).__name__)
        row["import_error"] = error_msg
        row["error_type"] = error_type
        gr_failed += 1
        tb = traceback.format_exc()
        print(f"  [{i+1}/{len(gr_rows)}] FAIL [{error_type}] GR {gr_no}: {error_msg}")
        if error_type == "system":
            all_system_errors.append(("GR", i+1, error_msg, tb))
        fd_matches = find_full_data_row_by_gr(po_no, gr_no)
        if fd_matches:
            append_to_full_data_error(fd_matches, error_msg, "gr_import_error")
        else:
            print(f"    WARNING: GR {gr_no} (PO {po_no}) not found in full_data.csv")

print(f"\nGR Import Summary: {gr_success} success, {gr_failed} failed, {gr_skipped_dup} skipped (duplicate)")

# ═══════════════════════════════════════════════════════════════════════
# Write updated CSVs
# ═══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("Writing updated CSV files...")

finished_po_nos = {
    str(r.get("po_no", "")).strip()
    for r in gr_rows
    if str(r.get("status", "")).strip() == "finished"
       and str(r.get("po_no", "")).strip()
}
if finished_po_nos:
    normalized_gr = 0
    normalized_po = 0
    for row in gr_rows:
        po_no = str(row.get("po_no", "")).strip()
        if po_no in finished_po_nos and row.get("status") != "finished":
            row["status"] = "finished"
            normalized_gr += 1
    for row in po_rows:
        po_no = str(row.get("po_no", "")).strip()
        if po_no in finished_po_nos and row.get("status") != "finished":
            row["status"] = "finished"
            normalized_po += 1
    print(f"  Normalized finished PO groups: {len(finished_po_nos)} PO, {normalized_gr} GR rows, {normalized_po} PO rows")

# import CSVs
sc_fieldnames = list(sc_rows[0].keys())
write_csv(IMPORT_SC, sc_rows, sc_fieldnames)
print(f"  Updated: {IMPORT_SC}")

po_fieldnames = list(po_rows[0].keys())
write_csv(IMPORT_PO, po_rows, po_fieldnames)
print(f"  Updated: {IMPORT_PO}")

gr_fieldnames = list(gr_rows[0].keys())
write_csv(IMPORT_GR, gr_rows, gr_fieldnames)
print(f"  Updated: {IMPORT_GR}")

# full_data
write_csv(FULL_DATA, full_rows, fd_fieldnames)
print(f"  Updated: {FULL_DATA}")

# ═══════════════════════════════════════════════════════════════════════
# Final report
# ═══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("FINAL IMPORT REPORT")
print("=" * 70)
total = sc_success + po_success + gr_success
total_fail = sc_failed + po_failed + gr_failed
print(f"  Total success: {total}")
print(f"  Total failed:  {total_fail}")
print(f"    SC: {sc_success} ok, {sc_failed} failed")
print(f"    PO: {po_success} ok, {po_failed} failed")
print(f"    GR: {gr_success} ok, {gr_failed} failed")

# Count data_integrity vs system in all rows
di_count = 0
sys_count = 0
for rows in [sc_rows, po_rows, gr_rows]:
    for r in rows:
        et = r.get("error_type", "")
        if et == "data_integrity":
            di_count += 1
        elif et == "system":
            sys_count += 1

print(f"\n  Data integrity errors: {di_count}")
print(f"  System errors:         {sys_count}")

if all_system_errors:
    print(f"\n  === SYSTEM ERRORS ({len(all_system_errors)}) ===")
    for phase, idx, msg, tb in all_system_errors:
        print(f"\n  [{phase}] Row {idx}: {msg}")
        print(f"  Traceback (last 5 lines):")
        for line in tb.strip().split("\n")[-5:]:
            print(f"    {line}")
else:
    print(f"\n  No system-level errors detected.")

print("\nDone.")
