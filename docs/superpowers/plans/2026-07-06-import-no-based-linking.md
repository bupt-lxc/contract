# Import NO-based linking & improvements — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace ID-based import linking with NO-based linking, add smart date parsing, fill in missing fields, show vendor_id in vendor list, and install openpyxl.

**Architecture:** Backend `import_service.py` gets NO→ID resolution, `parse_date` utility, and new field handling. `bridge.py` template generators swap ID columns for NO columns and add missing field columns. Frontend list views update their `ImportPreviewDialog` column configs to match. Vendor list gains a first-column vendor_id.

**Tech Stack:** Python 3.11 (SQLite, openpyxl), Vue 3 (Element Plus, xlsx)

---

### Task 1: Install openpyxl dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add openpyxl to pyproject.toml dependencies**

```toml
# pyproject.toml — add to the dependencies list:
dependencies = [
    "pywebview>=6.2.1",
    "pystray>=0.19.5",
    "pillow>=11.0.0",
    "pywin32>=306",
    "openpyxl>=3.1.0",
]
```

- [ ] **Step 2: Install the dependency**

```bash
pip install openpyxl>=3.1.0
```

- [ ] **Step 3: Verify import works**

```bash
python -c "import openpyxl; print(openpyxl.__version__)"
```

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add openpyxl dependency for vendor import"
```

---

### Task 2: Add parse_date utility to import_service.py

**Files:**
- Modify: `sc_gr_app/services/import_service.py`

- [ ] **Step 1: Add _DATE_FORMATS and parse_date function**

Insert after the existing constants (after `SC_IMPORT_ALLOWED_STATUSES`):

```python
from datetime import datetime

_DATE_FORMATS = [
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%m/%d/%Y",
    "%m-%d-%Y",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%Y%m%d",
]


def parse_date(value: str) -> str | None:
    """Parse a date string into YYYY-MM-DD format. Returns None if unparseable."""
    if not value or not str(value).strip():
        return None
    value = str(value).strip()
    for fmt in _DATE_FORMATS:
        try:
            dt = datetime.strptime(value, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None
```

- [ ] **Step 2: Apply parse_date in import_scs**

In `import_scs`, wrap date fields with `parse_date`:

```python
# Replace the direct row.get() for date fields:
row.get("service_period_start"),
row.get("service_period_end"),
```

Replace with:

```python
parse_date(row.get("service_period_start")),
parse_date(row.get("service_period_end")),
```

- [ ] **Step 3: Apply parse_date in import_pos**

In `import_pos`, wrap date fields:

```python
# Replace:
row.get("contract_from"),
row.get("contract_to"),

# With:
parse_date(row.get("contract_from")),
parse_date(row.get("contract_to")),
parse_date(row.get("active_date")),
```

Also use `parse_date` for `active_date` in the `INSERT` statement (need to add the field first — see Task 5).

- [ ] **Step 4: Apply parse_date in import_grs**

In `import_grs`, wrap date fields:

```python
# Replace:
row.get("delivery_from"),
row.get("delivery_to"),
row.get("last_delivery"),

# With:
parse_date(row.get("delivery_from")),
parse_date(row.get("delivery_to")),
parse_date(row.get("last_delivery")),
```

- [ ] **Step 5: Commit**

```bash
git add sc_gr_app/services/import_service.py
git commit -m "feat: add parse_date utility with multi-format support to import_service"
```

---

### Task 3: SC import — NO-based linking, vendor_id, asset, asset_nums

**Files:**
- Modify: `sc_gr_app/services/import_service.py`

- [ ] **Step 1: Update _is_template_meta_row for SC**

Replace `_is_template_meta_row` with an entity-aware version. Add a new helper that checks `sc_no` instead of `sc_id`:

```python
def _is_template_meta_row(row: dict, id_field: str) -> bool:
    """Check if this is a template meta row (hint or sample) that should be skipped."""
    val = str(row.get(id_field, "")).strip()
    if val == "[EXAMPLE]":
        return True
    if " " in val or "(" in val:
        return True
    return False
```

(This already skips `EXAMPLE` and hint rows by their text, but now `id_field` will be `sc_no`, `po_no`, or `gr_no` instead of the system IDs.)

- [ ] **Step 2: Add SC NO uniqueness check to _validate_sc_rows**

Add after the field validation loop:

```python
def _validate_sc_rows(conn, rows: list[dict]) -> list[dict]:
    errors = []
    for i, row in enumerate(rows, start=1):
        if _is_template_meta_row(row, "sc_no"):
            continue
        for field in ["sc_no", "sc_amount", "status"]:
            if not row.get(field):
                errors.append({"row": i, "field": field, "message": f"{field} is required"})
        status = row.get("status", "")
        if status and status not in SC_IMPORT_ALLOWED_STATUSES:
            errors.append({"row": i, "field": "status", "message": f"Invalid status: {status}"})
        if row.get("requester_id"):
            exists = conn.execute(
                "SELECT 1 FROM users WHERE user_id = ?", (row["requester_id"],)
            ).fetchone()
            if not exists:
                errors.append({"row": i, "field": "requester_id", "message": f"User {row['requester_id']} not found"})
        calloff_po_id = row.get("calloff_po_id")
        if calloff_po_id:
            po_exists = conn.execute(
                "select 1 from pos po join sc_records sc on sc.sc_id = po.sc_id "
                "where po.po_id = ? and sc.request_type = 'FC'",
                (calloff_po_id,),
            ).fetchone()
            if not po_exists:
                errors.append({"row": i, "field": "calloff_po_id", "message": f"calloff_po_id {calloff_po_id} is not a valid FC PO"})
        # Validate vendor_ids if provided
        vendor_ids = row.get("vendor_id", "").strip()
        if vendor_ids:
            for vid in vendor_ids.split(","):
                vid = vid.strip()
                if vid:
                    v = conn.execute("SELECT 1 FROM vendors WHERE vendor_id = ?", (vid,)).fetchone()
                    if not v:
                        errors.append({"row": i, "field": "vendor_id", "message": f"Vendor {vid} not found"})

    # DB-level SC NO uniqueness check: reject if any sc_no appears multiple times in DB
    sc_nos_in_file = [r["sc_no"].strip() for r in rows if r.get("sc_no") and not _is_template_meta_row(r, "sc_no")]
    if sc_nos_in_file:
        placeholders = ",".join(["?"] * len(sc_nos_in_file))
        dupes = conn.execute(
            f"SELECT sc_no, COUNT(*) as cnt FROM sc_records WHERE sc_no IN ({placeholders}) GROUP BY sc_no HAVING COUNT(*) > 1",
            sc_nos_in_file,
        ).fetchall()
        if dupes:
            raise ValidationError(
                f"Duplicate SC NO found in database: {', '.join(d['sc_no'] for d in dupes)}. "
                f"Please resolve duplicates before importing."
            )
    return errors
```

Note: need to add `from sc_gr_app.errors import ValidationError` at the top if not already present.

- [ ] **Step 3: Update import_scs for NO-based sc_id generation and missing fields**

Update the INSERT in `import_scs` to:
- Remove `sc_id` from required logic (still generate if empty)
- Add `vendor_id` → `sc_vendors` junction table insertion
- Add `asset` and `asset_nums` fields

```python
def import_scs(config: AppConfig, current_user: dict, rows: list[dict]) -> dict:
    timestamp = utc_now()
    machine_id = current_user["machine_id"]
    with LeaseLock(config.lock_dir, "import:lock", machine_id):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                errors = _validate_sc_rows(conn, rows)
                if errors:
                    conn.rollback()
                    return {"ok": False, "errors": errors}

                imported = 0
                skipped_duplicate = 0
                for row in rows:
                    if _is_template_meta_row(row, "sc_no"):
                        continue
                    sc_no = (row.get("sc_no") or "").strip()
                    # Uniqueness check: skip if SC NO already exists in DB
                    exists = conn.execute(
                        "SELECT 1 FROM sc_records WHERE sc_no = ?", (sc_no,)
                    ).fetchone()
                    if exists:
                        skipped_duplicate += 1
                        continue
                    sc_id = _generate_sc_id(conn, machine_id)
                    asset_val = row.get("asset", "N").strip() or "N"
                    conn.execute(
                        """INSERT INTO sc_records (
                          sc_id, sc_no, requester_id, request_type, cost_center,
                          sc_amount, service_period_start, service_period_end,
                          status, description, currency, internal_system_number,
                          calloff_po_id, asset, asset_nums,
                          created_by, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            sc_id,
                            sc_no,
                            row.get("requester_id") or current_user["user_id"],
                            row.get("request_type"),
                            row.get("cost_center"),
                            float(row["sc_amount"]) if row.get("sc_amount") else None,
                            parse_date(row.get("service_period_start")),
                            parse_date(row.get("service_period_end")),
                            row["status"],
                            row.get("description"),
                            row.get("currency", "CNY"),
                            row.get("internal_system_number"),
                            row.get("calloff_po_id"),
                            asset_val,
                            row.get("asset_nums"),
                            current_user["user_id"],
                            timestamp,
                            timestamp,
                        ),
                    )
                    # Insert sc_vendors if vendor_id provided (comma-separated)
                    vendor_ids = row.get("vendor_id", "").strip()
                    if vendor_ids:
                        for vid in vendor_ids.split(","):
                            vid = vid.strip()
                            if vid:
                                conn.execute(
                                    "INSERT OR IGNORE INTO sc_vendors (sc_id, vendor_id) VALUES (?, ?)",
                                    (sc_id, vid),
                                )
                    write_operation_record(
                        conn,
                        action_type="import_sc",
                        object_type="sc",
                        object_id=sc_id,
                        sc_id=sc_id,
                        operator_id=current_user["user_id"],
                        machine_id=machine_id,
                        before=None,
                        after=dict(row),
                    )
                    imported += 1

                conn.commit()
                return {"ok": True, "count": imported, "skipped_duplicate": skipped_duplicate}
            except Exception:
                conn.rollback()
                raise
```

- [ ] **Step 4: Update preview_sc_import — meta row check + file-level SC NO dedup**

Change `_is_template_meta_row(row, "sc_id")` → `_is_template_meta_row(row, "sc_no")` (2 occurrences).

Add file-level SC NO duplicate detection: after building the `preview` list, scan for duplicate `sc_no` values within the same file and mark them as `_valid: false` with error `"SC NO appears multiple times in this file"`:

```python
# After the preview loop, before return preview:
sc_no_counts = {}
for row in preview:
    sc_no = (row.get("sc_no") or "").strip()
    if sc_no:
        sc_no_counts[sc_no] = sc_no_counts.get(sc_no, 0) + 1
for row in preview:
    sc_no = (row.get("sc_no") or "").strip()
    if sc_no and sc_no_counts.get(sc_no, 0) > 1:
        row["_errors"].append(f"SC NO '{sc_no}' appears {sc_no_counts[sc_no]} times in this file")
        row["_valid"] = False
```

Same pattern applies to `preview_po_import` (dedup by `po_no`) and `preview_gr_import` (dedup by `gr_no`).

- [ ] **Step 5: Commit**

```bash
git add sc_gr_app/services/import_service.py
git commit -m "feat: SC import — NO-based linking, vendor_id, asset, asset_nums"
```

---

### Task 4: PO import — NO-based linking, active_date

**Files:**
- Modify: `sc_gr_app/services/import_service.py`

- [ ] **Step 1: Update _validate_po_rows for NO-based linking**

Replace the `sc_id` requirement with `sc_no`. Add PO NO uniqueness check.

```python
def _validate_po_rows(conn, rows: list[dict]) -> list[dict]:
    """Validate all PO rows. Returns list of error dicts."""
    errors = []
    for i, row in enumerate(rows, start=1):
        if _is_template_meta_row(row, "po_no"):
            continue
        for field in ["sc_no", "po_no", "po_amount", "status"]:
            if not row.get(field):
                errors.append({"row": i, "field": field, "message": f"{field} is required"})
        status = row.get("status", "")
        if status and status not in PO_IMPORT_ALLOWED_STATUSES:
            errors.append({"row": i, "field": "status", "message": f"Invalid status: {status}"})
        # Resolve sc_no → sc_id
        sc_no = row.get("sc_no", "").strip()
        if sc_no:
            sc_rows = conn.execute(
                "SELECT sc_id FROM sc_records WHERE sc_no = ?", (sc_no,)
            ).fetchall()
            if len(sc_rows) == 0:
                errors.append({"row": i, "field": "sc_no", "message": f"SC with SC NO '{sc_no}' not found"})
            elif len(sc_rows) > 1:
                raise ValidationError(
                    f"Duplicate SC NO '{sc_no}' found in database ({len(sc_rows)} records). "
                    f"Please resolve duplicates before importing."
                )
        if row.get("vendor_id"):
            exists = conn.execute(
                "SELECT 1 FROM vendors WHERE vendor_id = ?", (row["vendor_id"],)
            ).fetchone()
            if not exists:
                errors.append({"row": i, "field": "vendor_id", "message": f"Vendor {row['vendor_id']} not found"})

    # DB-level PO NO uniqueness check
    po_nos_in_file = [r["po_no"].strip() for r in rows if r.get("po_no") and not _is_template_meta_row(r, "po_no")]
    if po_nos_in_file:
        placeholders = ",".join(["?"] * len(po_nos_in_file))
        dupes = conn.execute(
            f"SELECT po_no, COUNT(*) as cnt FROM pos WHERE po_no IN ({placeholders}) GROUP BY po_no HAVING COUNT(*) > 1",
            po_nos_in_file,
        ).fetchall()
        if dupes:
            raise ValidationError(
                f"Duplicate PO NO found in database: {', '.join(d['po_no'] for d in dupes)}. "
                f"Please resolve duplicates before importing."
            )
    return errors
```

- [ ] **Step 2: Update _validate_po_rows preview function**

In `preview_po_import`, same changes: replace `sc_id` field check with `sc_no`, add `sc_no` → `sc_id` resolution, add `po_no` uniqueness check. The preview function should NOT raise `ValidationError` on duplicate NOs in DB — it should instead annotate the row as `_valid: false`:

```python
def preview_po_import(config: AppConfig, rows: list[dict]) -> list[dict]:
    with connect(config) as conn:
        preview = []
        for row in rows:
            if _is_template_meta_row(row, "po_no"):
                continue
            errors_list = []
            for field in ["sc_no", "po_no", "po_amount", "status"]:
                if not row.get(field):
                    errors_list.append(f"{field} is required")
            status = row.get("status", "")
            if status and status not in PO_IMPORT_ALLOWED_STATUSES:
                errors_list.append(f"Invalid status: {status}")
            sc_no = row.get("sc_no", "").strip()
            if sc_no:
                sc_rows = conn.execute(
                    "SELECT sc_id FROM sc_records WHERE sc_no = ?", (sc_no,)
                ).fetchall()
                if len(sc_rows) == 0:
                    errors_list.append(f"SC with SC NO '{sc_no}' not found")
                elif len(sc_rows) > 1:
                    errors_list.append(f"SC NO '{sc_no}' matches {len(sc_rows)} records in DB (duplicate NO)")
            if row.get("vendor_id"):
                exists = conn.execute(
                    "SELECT 1 FROM vendors WHERE vendor_id = ?", (row["vendor_id"],)
                ).fetchone()
                if not exists:
                    errors_list.append(f"Vendor {row['vendor_id']} not found")
            # Check po_no uniqueness in DB
            po_no = (row.get("po_no") or "").strip()
            if po_no:
                po_rows = conn.execute(
                    "SELECT COUNT(*) as cnt FROM pos WHERE po_no = ?", (po_no,)
                ).fetchone()
                if po_rows and po_rows["cnt"] > 1:
                    errors_list.append(f"PO NO '{po_no}' has {po_rows['cnt']} records in DB (duplicate NO)")
            annotated = dict(row)
            annotated["_errors"] = errors_list
            annotated["_valid"] = len(errors_list) == 0
            preview.append(annotated)
    return preview
```

- [ ] **Step 3: Update import_pos for NO→ID resolution and active_date**

```python
def import_pos(config: AppConfig, current_user: dict, rows: list[dict]) -> dict:
    timestamp = utc_now()
    machine_id = current_user["machine_id"]
    with LeaseLock(config.lock_dir, "import:lock", machine_id):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                errors = _validate_po_rows(conn, rows)
                if errors:
                    conn.rollback()
                    return {"ok": False, "errors": errors}

                imported = 0
                skipped_duplicate = 0
                for row in rows:
                    if _is_template_meta_row(row, "po_no"):
                        continue
                    po_no = (row.get("po_no") or "").strip()
                    # Uniqueness check
                    exists = conn.execute(
                        "SELECT 1 FROM pos WHERE po_no = ?", (po_no,)
                    ).fetchone()
                    if exists:
                        skipped_duplicate += 1
                        continue
                    # Resolve sc_no → sc_id
                    sc_no = row.get("sc_no", "").strip()
                    sc_row = conn.execute(
                        "SELECT sc_id FROM sc_records WHERE sc_no = ?", (sc_no,)
                    ).fetchone()
                    sc_id = sc_row["sc_id"]
                    po_id = _generate_po_id(conn, machine_id)
                    conn.execute(
                        """INSERT INTO pos (
                          po_id, sc_id, vendor_id, po_no, requester_id,
                          po_amount, status, contract_from, contract_to, contract_no,
                          payment_frequency, contract_pos, contract_type, cost_center,
                          purchaser, active_date, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            po_id,
                            sc_id,
                            row.get("vendor_id"),
                            po_no,
                            row.get("requester_id") or current_user["user_id"],
                            float(row["po_amount"]) if row.get("po_amount") else None,
                            row.get("status", "draft"),
                            parse_date(row.get("contract_from")),
                            parse_date(row.get("contract_to")),
                            row.get("contract_no"),
                            row.get("payment_frequency"),
                            row.get("contract_pos"),
                            row.get("contract_type"),
                            row.get("cost_center"),
                            row.get("purchaser"),
                            parse_date(row.get("active_date")) if row.get("active_date") else None,
                            timestamp,
                            timestamp,
                        ),
                    )
                    write_operation_record(
                        conn,
                        action_type="import_po",
                        object_type="po",
                        object_id=po_id,
                        sc_id=sc_id,
                        operator_id=current_user["user_id"],
                        machine_id=machine_id,
                        before=None,
                        after=dict(row),
                    )
                    imported += 1

                conn.commit()
                return {"ok": True, "count": imported, "skipped_duplicate": skipped_duplicate}
            except Exception:
                conn.rollback()
                raise
```

- [ ] **Step 4: Commit**

```bash
git add sc_gr_app/services/import_service.py
git commit -m "feat: PO import — NO-based linking, active_date support"
```

---

### Task 5: GR import — NO-based linking

**Files:**
- Modify: `sc_gr_app/services/import_service.py`

- [ ] **Step 1: Update _validate_gr_rows for NO-based linking**

Replace `po_id` requirement with `po_no`. Add GR NO uniqueness check.

```python
def _validate_gr_rows(conn, rows: list[dict]) -> list[dict]:
    errors = []
    for i, row in enumerate(rows, start=1):
        if _is_template_meta_row(row, "gr_no"):
            continue
        for field in ["po_no", "gr_no", "estimated_amount", "con_value", "delivery_from", "delivery_to", "status"]:
            if not row.get(field):
                errors.append({"row": i, "field": field, "message": f"{field} is required"})
        status = row.get("status", "")
        if status and status not in GR_IMPORT_ALLOWED_STATUSES:
            errors.append({"row": i, "field": "status", "message": f"Invalid status: {status}"})
        po_no = row.get("po_no", "").strip()
        if po_no:
            po_rows = conn.execute(
                "SELECT po_id FROM pos WHERE po_no = ?", (po_no,)
            ).fetchall()
            if len(po_rows) == 0:
                errors.append({"row": i, "field": "po_no", "message": f"PO with PO NO '{po_no}' not found"})
            elif len(po_rows) > 1:
                raise ValidationError(
                    f"Duplicate PO NO '{po_no}' found in database ({len(po_rows)} records). "
                    f"Please resolve duplicates before importing."
                )

    # DB-level GR NO uniqueness check
    gr_nos_in_file = [r["gr_no"].strip() for r in rows if r.get("gr_no") and not _is_template_meta_row(r, "gr_no")]
    if gr_nos_in_file:
        placeholders = ",".join(["?"] * len(gr_nos_in_file))
        dupes = conn.execute(
            f"SELECT gr_no, COUNT(*) as cnt FROM gr_requests WHERE gr_no IN ({placeholders}) GROUP BY gr_no HAVING COUNT(*) > 1",
            gr_nos_in_file,
        ).fetchall()
        if dupes:
            raise ValidationError(
                f"Duplicate GR NO found in database: {', '.join(d['gr_no'] for d in dupes)}. "
                f"Please resolve duplicates before importing."
            )
    return errors
```

- [ ] **Step 2: Update preview_gr_import for NO-based linking**

Same pattern: replace `po_id` with `po_no`, add NO→ID resolution, add gr_no DB uniqueness check (annotate `_valid: false`, don't raise).

```python
def preview_gr_import(config: AppConfig, rows: list[dict]) -> list[dict]:
    with connect(config) as conn:
        preview = []
        for row in rows:
            if _is_template_meta_row(row, "gr_no"):
                continue
            errors_list = []
            for field in ["po_no", "gr_no", "estimated_amount", "con_value", "delivery_from", "delivery_to", "status"]:
                if not row.get(field):
                    errors_list.append(f"{field} is required")
            status = row.get("status", "")
            if status and status not in GR_IMPORT_ALLOWED_STATUSES:
                errors_list.append(f"Invalid status: {status}")
            po_no = row.get("po_no", "").strip()
            if po_no:
                po_rows = conn.execute(
                    "SELECT po_id FROM pos WHERE po_no = ?", (po_no,)
                ).fetchall()
                if len(po_rows) == 0:
                    errors_list.append(f"PO with PO NO '{po_no}' not found")
                elif len(po_rows) > 1:
                    errors_list.append(f"PO NO '{po_no}' matches {len(po_rows)} records in DB (duplicate NO)")
            # Check gr_no uniqueness in DB
            gr_no = (row.get("gr_no") or "").strip()
            if gr_no:
                gr_rows = conn.execute(
                    "SELECT COUNT(*) as cnt FROM gr_requests WHERE gr_no = ?", (gr_no,)
                ).fetchone()
                if gr_rows and gr_rows["cnt"] > 1:
                    errors_list.append(f"GR NO '{gr_no}' has {gr_rows['cnt']} records in DB (duplicate NO)")
            annotated = dict(row)
            annotated["_errors"] = errors_list
            annotated["_valid"] = len(errors_list) == 0
            preview.append(annotated)
    return preview
```

- [ ] **Step 3: Update import_grs for NO→ID resolution**

```python
def import_grs(config: AppConfig, current_user: dict, rows: list[dict]) -> dict:
    timestamp = utc_now()
    machine_id = current_user["machine_id"]
    with LeaseLock(config.lock_dir, "import:lock", machine_id):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                errors = _validate_gr_rows(conn, rows)
                if errors:
                    conn.rollback()
                    return {"ok": False, "errors": errors}

                imported = 0
                skipped_duplicate = 0
                for row in rows:
                    if _is_template_meta_row(row, "gr_no"):
                        continue
                    gr_no = (row.get("gr_no") or "").strip()
                    # Uniqueness check
                    exists = conn.execute(
                        "SELECT 1 FROM gr_requests WHERE gr_no = ?", (gr_no,)
                    ).fetchone()
                    if exists:
                        skipped_duplicate += 1
                        continue
                    # Resolve po_no → po_id
                    po_no = row.get("po_no", "").strip()
                    po_row = conn.execute(
                        "SELECT po_id FROM pos WHERE po_no = ?", (po_no,)
                    ).fetchone()
                    po_id = po_row["po_id"]
                    gr_id = _generate_gr_id(conn, machine_id)
                    conn.execute(
                        """INSERT INTO gr_requests (
                          gr_id, po_id, gr_no, requester_id,
                          estimated_amount, con_value, status, remark, tax_rate,
                          gross_cost, goods_service_description, confirmation_name,
                          delivery_from, delivery_to, last_delivery,
                          created_by, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            gr_id,
                            po_id,
                            gr_no,
                            row.get("requester_id") or current_user["user_id"],
                            float(row["estimated_amount"]) if row.get("estimated_amount") else None,
                            float(row["con_value"]) if row.get("con_value") else None,
                            row.get("status", "draft"),
                            row.get("remark"),
                            float(row["tax_rate"]) if row.get("tax_rate") else None,
                            float(row["gross_cost"]) if row.get("gross_cost") else None,
                            row.get("goods_service_description"),
                            row.get("confirmation_name"),
                            parse_date(row.get("delivery_from")),
                            parse_date(row.get("delivery_to")),
                            parse_date(row.get("last_delivery")),
                            current_user["user_id"],
                            timestamp,
                        ),
                    )
                    write_operation_record(
                        conn,
                        action_type="import_gr",
                        object_type="gr",
                        object_id=gr_id,
                        sc_id=None,
                        operator_id=current_user["user_id"],
                        machine_id=machine_id,
                        before=None,
                        after=dict(row),
                    )
                    imported += 1

                conn.commit()
                return {"ok": True, "count": imported, "skipped_duplicate": skipped_duplicate}
            except Exception:
                conn.rollback()
                raise
```

- [ ] **Step 4: Commit**

```bash
git add sc_gr_app/services/import_service.py
git commit -m "feat: GR import — NO-based linking (po_no instead of po_id)"
```

---

### Task 6: Update SC template (bridge.py)

**Files:**
- Modify: `sc_gr_app/api/bridge.py` (around lines 1759-1847)

- [ ] **Step 1: Update download_sc_template headers, hints, sample**

Replace the `download_sc_template` method body. The key changes:
- Remove `sc_id` from headers
- Add `vendor_id`, `asset`, `asset_nums` to headers (before `requester_id` and after `calloff_po_id` respectively)
- Update hints to match new fields
- Update sample row with current user ID for `requester_id`
- Update info text to mention NO-based linking

```python
def download_sc_template(self, _payload=None) -> dict:
    """Return SC import template as base64-encoded xlsx data."""
    import io
    import base64
    import zipfile

    current_user = self._require_current_user()

    headers = ["sc_no", "vendor_id", "requester_id", "request_type", "cost_center",
               "sc_amount", "service_period_start", "service_period_end", "status",
               "description", "currency", "internal_system_number", "calloff_po_id",
               "asset", "asset_nums"]
    hints = ["Required (business NO, must be unique)",
             "Optional (comma-separated, e.g. V000001,V000002)",
             "Optional (defaults to importer)",
             "material/service/fixed_asset/FC", "Cost center number",
             "Required (e.g. 50000)", "YYYY-MM-DD or MM/DD/YYYY", "YYYY-MM-DD or MM/DD/YYYY",
             "approved/finished", "Optional",
             "CNY/EUR/USD", "Optional (FC only)",
             "Optional (FC call-off only)",
             "Y/N (default N)", "Optional"]
    sample = ["", "", current_user["user_id"], "material", "12345",
              "50000", "2026-01-01", "2026-12-31", "approved",
              "Sample SC description", "CNY", "", "",
              "N", ""]

    # (keep the same _col_letter, _inline_str_cell, _xml_escape helpers)
    def _col_letter(i):
        s = ""
        n = i
        while n >= 0:
            s = chr(ord('A') + n % 26) + s
            n = n // 26 - 1
        return s

    def _inline_str_cell(col, row_num, text):
        ref = f"{_col_letter(col)}{row_num}"
        return f'<c r="{ref}" t="inlineStr"><is><t>{_xml_escape(text)}</t></is></c>'

    def _xml_escape(s):
        return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

    header_cells = "".join(_inline_str_cell(i, 2, h) for i, h in enumerate(headers))
    hint_cells = "".join(_inline_str_cell(i, 3, h) for i, h in enumerate(hints))
    sample_cells = "".join(_inline_str_cell(i, 4, v) for i, v in enumerate(sample))

    last_col = _col_letter(len(headers) - 1)
    info_text = (
        "Import Rules: Only SC records with status \"approved\" or \"finished\" can be imported. "
        "Required fields: SC NO, SC Amount, Status. "
        "Linking: Records are identified by SC NO (not system ID). "
        "Duplicate SC NOs in database will cause import errors."
    )
    info_cell = f'<c r="A1" t="inlineStr"><is><t>{_xml_escape(info_text)}</t></is></c>'

    sheet_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    <row r="1">{info_cell}</row>
    <row r="2">{header_cells}</row>
    <row r="3">{hint_cells}</row>
    <row r="4">{sample_cells}</row>
  </sheetData>
  <mergeCells count="1"><mergeCell ref="A1:{last_col}1"/></mergeCells>
</worksheet>"""

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            '</Types>')
        zf.writestr("_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            '</Relationships>')
        zf.writestr("xl/workbook.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="SC Import" sheetId="1" r:id="rId1"/></sheets>'
            '</workbook>')
        zf.writestr("xl/_rels/workbook.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            '</Relationships>')
        zf.writestr("xl/worksheets/sheet1.xml", sheet_xml)
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode("ascii")
    return ok({"filename": "SC_Import_Template.xlsx", "data": b64})
```

- [ ] **Step 2: Commit**

```bash
git add sc_gr_app/api/bridge.py
git commit -m "feat: update SC import template — NO-based, vendor_id, asset, asset_nums"
```

---

### Task 7: Update PO template (bridge.py)

**Files:**
- Modify: `sc_gr_app/api/bridge.py` (around lines 1865-1952)

- [ ] **Step 1: Update download_po_template**

```python
def download_po_template(self, _payload=None) -> dict:
    """Return PO import template as base64-encoded xlsx data."""
    import io
    import base64
    import zipfile

    current_user = self._require_current_user()

    headers = ["sc_no", "vendor_id", "po_no", "requester_id",
               "po_amount", "status", "contract_from", "contract_to", "contract_no",
               "payment_frequency", "contract_pos", "contract_type", "cost_center",
               "purchaser", "active_date"]
    hints = ["Required (SC NO, must exist in DB)",
             "Optional (must exist if provided)",
             "Required (business NO, must be unique)",
             "Optional (defaults to importer)", "Required",
             "active/finished", "YYYY-MM-DD or MM/DD/YYYY", "YYYY-MM-DD or MM/DD/YYYY", "Optional",
             "monthly/quarterly/yearly", "Optional", "Optional", "Optional",
             "Optional", "YYYY-MM-DD or MM/DD/YYYY"]
    sample = ["", "", "", current_user["user_id"],
              "50000", "active", "", "", "",
              "monthly", "", "", "", "",
              ""]

    # ... (same helpers as SC template)
```

- [ ] **Step 2: Update info text**

```python
    info_text = (
        "Import Rules: Only PO records with status \"active\" or \"finished\" can be imported. "
        "Required fields: SC NO, PO NO, PO Amount, Status. "
        "Linking: PO is linked to SC via SC NO (not SC ID). "
        "Duplicate PO NOs in database will cause import errors."
    )
```

- [ ] **Step 3: Commit**

```bash
git add sc_gr_app/api/bridge.py
git commit -m "feat: update PO import template — NO-based, active_date, current user in sample"
```

---

### Task 8: Update GR template (bridge.py)

**Files:**
- Modify: `sc_gr_app/api/bridge.py` (around lines 1970-2058)

- [ ] **Step 1: Update download_gr_template**

```python
def download_gr_template(self, _payload=None) -> dict:
    """Return GR import template as base64-encoded xlsx data."""
    import io
    import base64
    import zipfile

    current_user = self._require_current_user()

    headers = ["po_no", "gr_no", "requester_id",
               "estimated_amount", "con_value", "status", "remark", "tax_rate",
               "gross_cost", "goods_service_description", "confirmation_name",
               "delivery_from", "delivery_to", "last_delivery"]
    hints = ["Required (PO NO, must exist in DB)",
             "Required (business NO, must be unique)",
             "Optional (defaults to importer)",
             "Required", "Required",
             "approved/finished", "Optional",
             "Optional (e.g. 13)", "Optional", "Optional", "Optional",
             "Required (YYYY-MM-DD or MM/DD/YYYY)", "Required (YYYY-MM-DD or MM/DD/YYYY)", "Optional (YYYY-MM-DD or MM/DD/YYYY)"]
    sample = ["", "", current_user["user_id"],
              "10000", "10000", "approved", "", "13",
              "", "Sample goods description", "",
              "2026-01-01", "2026-12-31", ""]

    # ... (same helpers as before)
```

- [ ] **Step 2: Update info text**

```python
    info_text = (
        "Import Rules: Only GR records with status \"approved\" or \"finished\" can be imported. "
        "Required fields: PO NO, GR NO, Estimated Amount, Con Value, Delivery From, Delivery To, Status. "
        "Linking: GR is linked to PO via PO NO (not PO ID). "
        "Duplicate GR NOs in database will cause import errors."
    )
```

- [ ] **Step 3: Commit**

```bash
git add sc_gr_app/api/bridge.py
git commit -m "feat: update GR import template — NO-based, current user in sample"
```

---

### Task 9: Update frontend import columns

**Files:**
- Modify: `frontend/src/views/ScListView.vue` (lines 332-347)
- Modify: `frontend/src/views/PoListView.vue` (lines 309-325)
- Modify: `frontend/src/views/GrListView.vue` (lines 426-442)

- [ ] **Step 1: Update scImportColumns in ScListView.vue**

Remove `sc_id`, add `vendor_id`:

```javascript
const scImportColumns = [
  { prop: 'sc_no', label: t('sc.scNo'), width: '120' },
  { prop: 'vendor_id', label: t('vendor.vendorId'), width: '120' },
  { prop: 'requester_id', label: t('sc.requester'), width: '100' },
  { prop: 'request_type', label: t('sc.requestType'), width: '100' },
  { prop: 'cost_center', label: t('sc.costCenter'), width: '100' },
  { prop: 'sc_amount', label: t('sc.scAmount'), width: '100' },
  { prop: 'currency', label: t('sc.currency'), width: '70' },
  { prop: 'service_period_start', label: t('sc.servicePeriodStart'), width: '110' },
  { prop: 'service_period_end', label: t('sc.servicePeriodEnd'), width: '110' },
  { prop: 'asset', label: t('sc.asset'), width: '60' },
  { prop: 'asset_nums', label: t('sc.assetNums'), width: '100' },
  { prop: 'status', label: t('common.status'), width: '90' },
  { prop: 'description', label: t('common.description'), minWidth: '140' },
  { prop: 'internal_system_number', label: t('sc.internalSystemNumber'), width: '100' },
]
```

- [ ] **Step 2: Update poImportColumns in PoListView.vue**

Remove `po_id` and `sc_id`, add `sc_no` and `active_date`:

```javascript
const poImportColumns = [
  { prop: 'sc_no', label: t('sc.scNo'), width: '120' },
  { prop: 'vendor_id', label: t('po.vendor'), width: '100' },
  { prop: 'po_no', label: t('po.poNo'), width: '120' },
  { prop: 'requester_id', label: t('sc.requester'), width: '100' },
  { prop: 'po_amount', label: t('po.poAmount'), width: '100' },
  { prop: 'status', label: t('common.status'), width: '90' },
  { prop: 'contract_from', label: t('po.contractFrom'), width: '110' },
  { prop: 'contract_to', label: t('po.contractTo'), width: '110' },
  { prop: 'contract_no', label: t('po.contractNo'), width: '120' },
  { prop: 'payment_frequency', label: t('po.paymentFrequency'), width: '100' },
  { prop: 'contract_pos', label: t('po.contractPos'), width: '90' },
  { prop: 'contract_type', label: t('po.contractType'), width: '100' },
  { prop: 'cost_center', label: t('po.costCenter'), width: '100' },
  { prop: 'purchaser', label: t('po.purchaser'), width: '100' },
  { prop: 'active_date', label: t('po.activeDate'), width: '110' },
]
```

- [ ] **Step 3: Update grImportColumns in GrListView.vue**

Remove `gr_id` and `po_id`, add `po_no`:

```javascript
const grImportColumns = [
  { prop: 'po_no', label: t('po.poNo'), width: '120' },
  { prop: 'gr_no', label: t('gr.grNo'), width: '120' },
  { prop: 'requester_id', label: t('gr.requester'), width: '100' },
  { prop: 'estimated_amount', label: t('gr.estimatedAmount'), width: '110' },
  { prop: 'con_value', label: t('gr.conValue'), width: '110' },
  { prop: 'status', label: t('common.status'), width: '90' },
  { prop: 'remark', label: t('gr.remark'), width: '120' },
  { prop: 'tax_rate', label: t('gr.taxRate'), width: '70' },
  { prop: 'gross_cost', label: t('gr.grossCost'), width: '100' },
  { prop: 'goods_service_description', label: t('gr.goodsServiceDescription'), minWidth: '140' },
  { prop: 'confirmation_name', label: t('gr.confirmationName'), width: '120' },
  { prop: 'delivery_from', label: t('gr.deliveryFrom'), width: '110' },
  { prop: 'delivery_to', label: t('gr.deliveryTo'), width: '110' },
  { prop: 'last_delivery', label: t('gr.lastDelivery'), width: '110' },
]
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/ScListView.vue frontend/src/views/PoListView.vue frontend/src/views/GrListView.vue
git commit -m "feat: update frontend import columns — NO-based, hide ID columns"
```

---

### Task 10: Add vendor_id column to VendorListView

**Files:**
- Modify: `frontend/src/views/VendorListView.vue`

- [ ] **Step 1: Add vendor_id as first column in the table**

In the `<el-table>` element, add before `<el-table-column prop="vendor_name" ...>`:

```vue
<el-table-column prop="vendor_id" :label="$t('vendor.vendorId')" width="120" />
```

The full first two columns become:

```vue
<el-table-column prop="vendor_id" :label="$t('vendor.vendorId')" width="120" />
<el-table-column prop="vendor_name" :label="$t('vendor.vendor')" sortable="custom" min-width="160" />
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/views/VendorListView.vue
git commit -m "feat: show vendor_id as first column in vendor list"
```

---

### Task 11: Update tests

**Files:**
- Modify: `tests/test_import_service.py`

- [ ] **Step 1: Add test for parse_date**

```python
class TestParseDate:
    def test_parses_iso_format(self):
        assert import_service.parse_date("2026-01-15") == "2026-01-15"

    def test_parses_slash_format(self):
        assert import_service.parse_date("2026/01/15") == "2026-01-15"

    def test_parses_us_format(self):
        assert import_service.parse_date("01/15/2026") == "2026-01-15"

    def test_parses_us_dash_format(self):
        assert import_service.parse_date("01-15-2026") == "2026-01-15"

    def test_parses_eu_format(self):
        assert import_service.parse_date("15/01/2026") == "2026-01-15"

    def test_parses_compact_format(self):
        assert import_service.parse_date("20260115") == "2026-01-15"

    def test_returns_none_for_invalid(self):
        assert import_service.parse_date("not-a-date") is None

    def test_returns_none_for_empty(self):
        assert import_service.parse_date("") is None
        assert import_service.parse_date(None) is None
```

- [ ] **Step 2: Add test for SC NO uniqueness rejection**

```python
class TestScNoUniqueness:
    def test_rejects_duplicate_sc_no_in_db(self, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            _seed_user(conn)
            # Seed two SCs with same SC NO
            conn.execute(
                """INSERT INTO sc_records (
                    sc_id, sc_no, requester_id, request_type, cost_center,
                    sc_amount, service_period_start, service_period_end,
                    status, asset, created_by, created_at, updated_at
                ) VALUES
                ('SC-DUP-1', 'DUP-NO', 'U000001', 'service', 1000, 50000,
                 '2026-01-01', '2026-12-31', 'approved', 'N', 'U000001', ?, ?),
                ('SC-DUP-2', 'DUP-NO', 'U000001', 'service', 1000, 50000,
                 '2026-01-01', '2026-12-31', 'approved', 'N', 'U000001', ?, ?)""",
                (_utc_now(), _utc_now(), _utc_now(), _utc_now()),
            )
            conn.commit()
        from sc_gr_app.errors import ValidationError
        import pytest
        current_user = {"user_id": "U000001", "machine_id": "M000001", "role": "requester"}
        rows = [{"sc_no": "DUP-NO", "sc_amount": "50000", "status": "approved"}]
        with pytest.raises(ValidationError, match="Duplicate SC NO"):
            import_service.import_scs(app_config, current_user, rows)
```

- [ ] **Step 3: Update existing tests to use NO-based fields**

Update `TestPoImportStatusRestrictions` tests: replace `sc_id` with `sc_no`, and use the SC NO `"SCNO-SC-0000001-20260701-001"` (matching what `_seed_sc` creates):

```python
class TestPoImportStatusRestrictions:
    def test_rejects_draft_status(self, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            _seed_user(conn)
            _seed_sc(conn)
            _seed_vendor(conn)
        rows = [{"sc_no": "SCNO-SC-0000001-20260701-001", "po_no": "PO-001", "po_amount": "50000", "status": "draft"}]
        preview = import_service.preview_po_import(app_config, rows)
        assert preview[0]["_valid"] is False

    def test_accepts_active_status(self, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            _seed_user(conn)
            _seed_sc(conn)
            _seed_vendor(conn)
        rows = [{"sc_no": "SCNO-SC-0000001-20260701-001", "po_no": "PO-002", "po_amount": "50000", "status": "active"}]
        preview = import_service.preview_po_import(app_config, rows)
        assert preview[0]["_valid"] is True

    def test_accepts_finished_status(self, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            _seed_user(conn)
            _seed_sc(conn)
            _seed_vendor(conn)
        rows = [{"sc_no": "SCNO-SC-0000001-20260701-001", "po_no": "PO-003", "po_amount": "50000", "status": "finished"}]
        preview = import_service.preview_po_import(app_config, rows)
        assert preview[0]["_valid"] is True
```

Update `TestGrImportStatusRestrictions` tests: replace `po_id` with `po_no`, using `"PONO-PO-0000001-20260701-001"`:

```python
class TestGrImportStatusRestrictions:
    def _seed_gr_deps(self, conn):
        _seed_user(conn)
        _seed_sc(conn)
        _seed_vendor(conn)
        _seed_po(conn)

    def test_rejects_draft_status(self, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            self._seed_gr_deps(conn)
        rows = [{"po_no": "PONO-PO-0000001-20260701-001", "gr_no": "GR-001", "estimated_amount": "10000",
                  "con_value": "10000", "delivery_from": "2026-01-01", "delivery_to": "2026-12-31", "status": "draft"}]
        preview = import_service.preview_gr_import(app_config, rows)
        assert preview[0]["_valid"] is False
    # ... (same pattern for remaining test methods)
```

Update `TestRequiredFields.test_po_fails_without_po_no`:

```python
def test_po_fails_without_sc_no(self, app_config):
    migrate(app_config)
    with connect(app_config) as conn:
        _seed_user(conn)
        _seed_sc(conn)
        _seed_vendor(conn)
    rows = [{"po_no": "PO-010", "po_amount": "50000", "status": "active"}]
    preview = import_service.preview_po_import(app_config, rows)
    assert preview[0]["_valid"] is False
    assert any("sc_no is required" in e for e in preview[0]["_errors"])
```

Update `TestPreviewAnnotations.test_preview_skips_template_meta_rows`:

```python
def test_preview_skips_template_meta_rows(self, app_config):
    migrate(app_config)
    with connect(app_config) as conn:
        _seed_user(conn)
    # sc_no=EXAMPLE now — since template meta row check uses sc_no
    rows = [{"sc_no": "[EXAMPLE]", "sc_amount": "50000", "status": "draft"}]
    preview = import_service.preview_sc_import(app_config, rows)
    assert len(preview) == 0
```

Update `TestConfirmImport` tests to use NO-based fields:

```python
def test_confirm_po_import_with_required_fields(self, app_config):
    migrate(app_config)
    with connect(app_config) as conn:
        _seed_user(conn)
        _seed_sc(conn)
        _seed_vendor(conn)
    current_user = {"user_id": "U000001", "machine_id": "M000001", "role": "requester"}
    rows = [{"sc_no": "SCNO-SC-0000001-20260701-001", "vendor_id": "V000001", "po_no": "PO-CONFIRM-2", "po_amount": "50000", "status": "active"}]
    result = import_service.import_pos(app_config, current_user, rows)
    assert result["ok"] is True
    assert result["count"] == 1

def test_confirm_gr_import_with_required_fields(self, app_config):
    migrate(app_config)
    with connect(app_config) as conn:
        _seed_user(conn)
        _seed_sc(conn)
        _seed_vendor(conn)
        _seed_po(conn)
    current_user = {"user_id": "U000001", "machine_id": "M000001", "role": "requester"}
    rows = [{"po_no": "PONO-PO-0000001-20260701-001", "gr_no": "GR-CONFIRM-2", "estimated_amount": "10000",
              "con_value": "10000", "delivery_from": "2026-01-01", "delivery_to": "2026-12-31", "status": "approved"}]
    result = import_service.import_grs(app_config, current_user, rows)
    assert result["ok"] is True
    assert result["count"] == 1
```

- [ ] **Step 4: Also update _seed_sc to use a simpler sc_no**

The `_seed_sc` helper currently creates `sc_no` as `f"SCNO-{sc_id}"`. Confirm this works with the test data — yes, `_seed_sc(conn)` creates `sc_id="SC-0000001-20260701-001"` so `sc_no` = `"SCNO-SC-0000001-20260701-001"`. No change needed.

- [ ] **Step 5: Run tests to verify pass**

```bash
python -m pytest tests/test_import_service.py -v
```

- [ ] **Step 6: Commit**

```bash
git add tests/test_import_service.py
git commit -m "test: update import tests for NO-based linking, parse_date"
```

---

### Task 12: Final verification

- [ ] **Step 1: Run the full test suite**

```bash
python -m pytest tests/ -v
```

- [ ] **Step 2: Verify the app starts**

```bash
python -m sc_gr_app.main
```

- [ ] **Step 3: Run git status to confirm clean state**

```bash
git status
```

---

## File Change Summary

| File | Change |
|------|--------|
| `pyproject.toml` | Add `openpyxl>=3.1.0` |
| `sc_gr_app/services/import_service.py` | `parse_date` utility, NO-based validation/import for SC/PO/GR, vendor_id/asset/asset_nums/active_date fields |
| `sc_gr_app/api/bridge.py` | Updated template headers/hints/samples for SC/PO/GR |
| `frontend/src/views/ScListView.vue` | Updated `scImportColumns` (remove sc_id, add vendor_id) |
| `frontend/src/views/PoListView.vue` | Updated `poImportColumns` (remove po_id/sc_id, add sc_no/active_date) |
| `frontend/src/views/GrListView.vue` | Updated `grImportColumns` (remove gr_id/po_id, add po_no) |
| `frontend/src/views/VendorListView.vue` | Add `vendor_id` as first table column |
| `tests/test_import_service.py` | Tests for parse_date, NO uniqueness, updated existing tests |
