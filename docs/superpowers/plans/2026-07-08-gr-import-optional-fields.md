# GR Import Optional Fields & Delivery Field Removal — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Relax GR import validation so `estimated_amount` is optional (only `con_value` required), and remove `delivery_from`/`delivery_to` fields system-wide.

**Architecture:** Changes span backend services (import, GR CRUD, query, export, budget, notification, import template endpoint) and frontend (form, detail, list, export, i18n). No database migration — columns are left in place. All null-safety fixes use `or 0` for `estimated_amount` in Decimal conversions and `coalesce(estimated_amount, 0)` in SQL aggregations. Import tests are updated to match new validation rules.

**Tech Stack:** Python (backend), Vue 3 + Element Plus (frontend), SQLite

---

### Task 1: Import Service — Relax Validation & Remove Delivery Fields

**Files:**
- Modify: `sc_gr_app/services/import_service.py`

- [ ] **Step 1: Update `_GR_COLUMN_ALIASES` — remove `delivery_from` and `delivery_to` entries**

Remove lines 65-66 (the `delivery_from` and `delivery_to` alias entries from the dict):

```python
# Before (lines 53-68):
_GR_COLUMN_ALIASES: dict[str, list[str]] = {
    "po_no":                     ["PO NO", "PO Number", "po_no", "采购订单号", "采购订单编号"],
    "gr_no":                     ["GR NO", "GR Number", "gr_no", "收货编号", "收货编号"],
    "requester_id":              ["Requester ID", "requester_id", "申请人ID", "申请人"],
    "estimated_amount":          ["Estimated Amount", "estimated_amount", "预估金额", "估计金额"],
    "con_value":                 ["Con Value", "con_value", "合同价值"],
    "status":                    ["Status", "status", "状态"],
    "remark":                    ["Remark", "remark", "备注"],
    "tax_rate":                  ["Tax Rate", "tax_rate", "税率"],
    "gross_cost":                ["Gross Cost", "gross_cost", "总成本"],
    "goods_service_description": ["Goods/Service Description", "goods_service_description", "商品/服务描述", "货物/服务描述"],
    "confirmation_name":         ["Confirmation Name", "confirmation_name", "确认人", "确认人"],
    "delivery_from":             ["Delivery From", "delivery_from", "交付开始", "开始日期"],
    "delivery_to":               ["Delivery To", "delivery_to", "交付结束", "结束日期"],
    "last_delivery":             ["Last Delivery", "last_delivery", "最后交付"],
}

# After — remove the two delivery lines:
_GR_COLUMN_ALIASES: dict[str, list[str]] = {
    "po_no":                     ["PO NO", "PO Number", "po_no", "采购订单号", "采购订单编号"],
    "gr_no":                     ["GR NO", "GR Number", "gr_no", "收货编号", "收货编号"],
    "requester_id":              ["Requester ID", "requester_id", "申请人ID", "申请人"],
    "estimated_amount":          ["Estimated Amount", "estimated_amount", "预估金额", "估计金额"],
    "con_value":                 ["Con Value", "con_value", "合同价值"],
    "status":                    ["Status", "status", "状态"],
    "remark":                    ["Remark", "remark", "备注"],
    "tax_rate":                  ["Tax Rate", "tax_rate", "税率"],
    "gross_cost":                ["Gross Cost", "gross_cost", "总成本"],
    "goods_service_description": ["Goods/Service Description", "goods_service_description", "商品/服务描述", "货物/服务描述"],
    "confirmation_name":         ["Confirmation Name", "confirmation_name", "确认人", "确认人"],
    "last_delivery":             ["Last Delivery", "last_delivery", "最后交付"],
}
```

- [ ] **Step 2: Update `_validate_gr_rows` — relax required fields**

At line 543, remove `estimated_amount`, `delivery_from`, `delivery_to` from the required-fields check:

```python
# Before (line 543):
for field in ["po_no", "gr_no", "estimated_amount", "con_value", "delivery_from", "delivery_to", "status"]:

# After:
for field in ["po_no", "gr_no", "con_value", "status"]:
```

Note: `GR_IMPORT_ALLOWED_STATUSES = {"approved", "finished"}` already includes these — no change needed.

- [ ] **Step 3: Update `preview_gr_import` — same required-fields change**

At line 746, apply the same change:

```python
# Before (line 746):
for field in ["po_no", "gr_no", "estimated_amount", "con_value", "delivery_from", "delivery_to", "status"]:

# After:
for field in ["po_no", "gr_no", "con_value", "status"]:
```

- [ ] **Step 4: Update `import_grs` INSERT — remove `delivery_from`, `delivery_to` columns**

At lines 820-846, remove `delivery_from` and `delivery_to` from the column list, placeholder list, and value tuple:

```python
# Before (lines 821-827):
conn.execute(
    """INSERT INTO gr_requests (
      gr_id, po_id, gr_no, requester_id,
      estimated_amount, con_value, status, remark, tax_rate,
      gross_cost, goods_service_description, confirmation_name,
      delivery_from, delivery_to, last_delivery,
      created_by, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",

# After:
conn.execute(
    """INSERT INTO gr_requests (
      gr_id, po_id, gr_no, requester_id,
      estimated_amount, con_value, status, remark, tax_rate,
      gross_cost, goods_service_description, confirmation_name,
      last_delivery,
      created_by, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
```

Remove the `delivery_from` and `delivery_to` value lines from the parameter tuple:

```python
# Before (lines 829-846):
(
    gr_id,
    po_id,
    row.get("gr_no"),
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
    row.get("last_delivery"),
    current_user["user_id"],
    timestamp,
),

# After — remove lines 841-842 (parse_date calls for delivery_from/to):
(
    gr_id,
    po_id,
    row.get("gr_no"),
    row.get("requester_id") or current_user["user_id"],
    float(row["estimated_amount"]) if row.get("estimated_amount") else None,
    float(row["con_value"]) if row.get("con_value") else None,
    row.get("status", "draft"),
    row.get("remark"),
    float(row["tax_rate"]) if row.get("tax_rate") else None,
    float(row["gross_cost"]) if row.get("gross_cost") else None,
    row.get("goods_service_description"),
    row.get("confirmation_name"),
    row.get("last_delivery"),
    current_user["user_id"],
    timestamp,
),
```

- [ ] **Step 5: Commit**

```bash
git add sc_gr_app/services/import_service.py
git commit -m "fix: relax GR import required fields, remove delivery_from/to from import"
```

---

### Task 2: Backend — Defensive Null-Safety for `estimated_amount`

**Files:**
- Modify: `sc_gr_app/services/gr_service.py`
- Modify: `sc_gr_app/services/sc_service.py`
- Modify: `sc_gr_app/services/budget_service.py`
- Modify: `sc_gr_app/notification/sender.py`

- [ ] **Step 1: `gr_service.py` `submit_gr` — guard null `estimated_amount`**

At line 459, add `or 0`:

```python
# Before:
estimated_amount = Decimal(str(before["estimated_amount"]))

# After:
estimated_amount = Decimal(str(before["estimated_amount"] or 0))
```

- [ ] **Step 2: `gr_service.py` `approve_gr` — guard null `estimated_amount`**

At line 588, add `or 0`:

```python
# Before:
extra_amount = con_value_amount - Decimal(
    str(before["estimated_amount"])
)

# After:
extra_amount = con_value_amount - Decimal(
    str(before["estimated_amount"] or 0)
)
```

- [ ] **Step 3: `sc_service.py` — guard null `estimated_amount` in GR usage calc**

At line 441, add `or 0`:

```python
# Before:
Decimal(str(row["estimated_amount"]))

# After:
Decimal(str(row["estimated_amount"] or 0))
```

- [ ] **Step 4: `budget_service.py` — add COALESCE for `estimated_amount` in pending totals**

Three locations need the same fix. In each, change `then estimated_amount` to `then coalesce(estimated_amount, 0)`:

**Location 1 — line 148** (SC budget query, `compute_sc_budget_decimal`):
```sql
# Before:
coalesce(sum(case when gr.status in ('pending', 'manager_confirm')
             then gr.estimated_amount else 0 end), 0) as pending_total,

# After:
coalesce(sum(case when gr.status in ('pending', 'manager_confirm')
             then coalesce(gr.estimated_amount, 0) else 0 end), 0) as pending_total,
```

**Location 2 — line 238** (second SC budget query, same pattern):
```sql
# Before:
coalesce(sum(case when gr.status in ('pending', 'manager_confirm')
             then gr.estimated_amount else 0 end), 0) as pending_total,

# After:
coalesce(sum(case when gr.status in ('pending', 'manager_confirm')
             then coalesce(gr.estimated_amount, 0) else 0 end), 0) as pending_total,
```

**Location 3 — line 300** (PO budget query, `compute_po_budget_decimal`):
```sql
# Before:
coalesce(sum(case when status in ('pending', 'manager_confirm') then estimated_amount else 0 end), 0)

# After:
coalesce(sum(case when status in ('pending', 'manager_confirm') then coalesce(estimated_amount, 0) else 0 end), 0)
```

Also fix the pending_total_incl_tax on the same line (L305) — it already uses `coalesce(gross_cost, estimated_amount)` but `estimated_amount` inside could be null. Change to:
```sql
# Before (L304-306):
coalesce(sum(case when status in ('pending', 'manager_confirm')
    then coalesce(gross_cost, estimated_amount) else 0 end), 0)
    as pending_total_incl_tax

# After:
coalesce(sum(case when status in ('pending', 'manager_confirm')
    then coalesce(gross_cost, estimated_amount, 0) else 0 end), 0)
    as pending_total_incl_tax
```

Note: Locations 1 and 2 (SC budget queries, lines 151-153 and 241-243) use `coalesce(gr.gross_cost, gr.estimated_amount)` with an outer `coalesce(sum(...), 0)` that already guards against NULL sums, so those two locations do NOT need the additional `, 0` fallback.

- [ ] **Step 5: `notification/sender.py` — add COALESCE for estimated_amount in PO budget subquery**

At line 56, same fix:
```sql
# Before:
THEN estimated_amount ELSE 0 END), 0) AS pending_total,

# After:
THEN coalesce(estimated_amount, 0) ELSE 0 END), 0) AS pending_total,
```

Also fix the pending_total_incl_tax at line 60:
```sql
# Before:
THEN COALESCE(gross_cost, estimated_amount)

# After:
THEN COALESCE(gross_cost, estimated_amount, 0)
```

- [ ] **Step 6: Commit**

```bash
git add sc_gr_app/services/gr_service.py sc_gr_app/services/sc_service.py sc_gr_app/services/budget_service.py sc_gr_app/notification/sender.py
git commit -m "fix: defensive null-safety for estimated_amount in budget and approval flows"
```

---

### Task 3: Backend — Remove `delivery_from`/`delivery_to` from GR Service

**Files:**
- Modify: `sc_gr_app/services/gr_service.py`

- [ ] **Step 1: `create_gr` — remove from INSERT**

At lines 294-320 (INSERT column list) and lines 322-348 (value tuple), remove `delivery_from` and `delivery_to`:

**Column list** — remove `delivery_from,` and `delivery_to,` from the INSERT columns:
```python
# Before (columns in INSERT, lines 294-320):
insert into gr_requests (
  gr_id,
  gr_no,
  po_id,
  requester_id,
  estimated_amount,
  con_value,
  gross_cost,
  tax_rate,
  status,
  remark,
  created_by,
  created_at,
  updated_at,
  approved_by,
  approved_at,
  denied_by,
  denied_at,
  submitted_date,
  pending_date,
  approved_date,
  goods_service_description,
  confirmation_name,
  delivery_from,
  delivery_to,
  last_delivery
) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

# After:
insert into gr_requests (
  gr_id,
  gr_no,
  po_id,
  requester_id,
  estimated_amount,
  con_value,
  gross_cost,
  tax_rate,
  status,
  remark,
  created_by,
  created_at,
  updated_at,
  approved_by,
  approved_at,
  denied_by,
  denied_at,
  submitted_date,
  pending_date,
  approved_date,
  goods_service_description,
  confirmation_name,
  last_delivery
) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
```

**Value tuple** — remove `data.get("delivery_from"),` and `data.get("delivery_to"),` (lines 345-346):
```python
# Before (lines 322-348):
(
    gr_id,
    data.get("gr_no"),
    po_id,
    requester_id,
    float(estimated_amount),
    None,
    float(gross_cost) if gross_cost is not None else None,
    data.get("tax_rate"),
    gr_status,
    data.get("remark"),
    current_user["user_id"],
    timestamp,
    timestamp,
    None,
    None,
    None,
    None,
    None if is_draft else timestamp,
    None if (is_draft or is_manager_confirm) else timestamp,
    None,
    data.get("goods_service_description"),
    data.get("confirmation_name"),
    data.get("delivery_from"),
    data.get("delivery_to"),
    data.get("last_delivery"),
),

# After — remove the two delivery lines:
(
    gr_id,
    data.get("gr_no"),
    po_id,
    requester_id,
    float(estimated_amount),
    None,
    float(gross_cost) if gross_cost is not None else None,
    data.get("tax_rate"),
    gr_status,
    data.get("remark"),
    current_user["user_id"],
    timestamp,
    timestamp,
    None,
    None,
    None,
    None,
    None if is_draft else timestamp,
    None if (is_draft or is_manager_confirm) else timestamp,
    None,
    data.get("goods_service_description"),
    data.get("confirmation_name"),
    data.get("last_delivery"),
),
```

- [ ] **Step 2: `update_gr` draft/pending — remove from allowed keys and UPDATE**

**Allowed keys** (line 684-698) — remove `"delivery_from",` and `"delivery_to",`:
```python
# Before:
allowed = {
    key: updates[key]
    for key in (
        "po_id",
        "requester_id",
        "estimated_amount",
        "tax_rate",
        "remark",
        "gr_no",
        "pending_date",
        "approved_date",
        "goods_service_description",
        "confirmation_name",
        "delivery_from",
        "delivery_to",
        "last_delivery",
    )
    if key in updates
}

# After:
allowed = {
    key: updates[key]
    for key in (
        "po_id",
        "requester_id",
        "estimated_amount",
        "tax_rate",
        "remark",
        "gr_no",
        "pending_date",
        "approved_date",
        "goods_service_description",
        "confirmation_name",
        "last_delivery",
    )
    if key in updates
}
```

**UPDATE SQL** (lines 758-796) — remove `delivery_from = ?,` and `delivery_to = ?,` from SET clause, and remove corresponding values:
```python
# Before (SET clause, lines 761-776):
set po_id = ?,
    requester_id = ?,
    estimated_amount = ?,
    gross_cost = ?,
    tax_rate = ?,
    remark = ?,
    gr_no = ?,
    pending_date = ?,
    approved_date = ?,
    goods_service_description = ?,
    confirmation_name = ?,
    delivery_from = ?,
    delivery_to = ?,
    last_delivery = ?,
    updated_at = ?
where gr_id = ?

# After:
set po_id = ?,
    requester_id = ?,
    estimated_amount = ?,
    gross_cost = ?,
    tax_rate = ?,
    remark = ?,
    gr_no = ?,
    pending_date = ?,
    approved_date = ?,
    goods_service_description = ?,
    confirmation_name = ?,
    last_delivery = ?,
    updated_at = ?
where gr_id = ?
```

**Value tuple** (lines 778-795) — remove `merged.get("delivery_from"),` and `merged.get("delivery_to"),`:
```python
# Before:
(
    merged["po_id"],
    merged["requester_id"],
    float(amount),
    float(merged["gross_cost"]) if merged.get("gross_cost") is not None else None,
    merged.get("tax_rate"),
    merged.get("remark"),
    merged.get("gr_no"),
    merged.get("pending_date"),
    merged.get("approved_date"),
    merged.get("goods_service_description"),
    merged.get("confirmation_name"),
    merged.get("delivery_from"),
    merged.get("delivery_to"),
    merged.get("last_delivery"),
    timestamp,
    gr_id,
),

# After:
(
    merged["po_id"],
    merged["requester_id"],
    float(amount),
    float(merged["gross_cost"]) if merged.get("gross_cost") is not None else None,
    merged.get("tax_rate"),
    merged.get("remark"),
    merged.get("gr_no"),
    merged.get("pending_date"),
    merged.get("approved_date"),
    merged.get("goods_service_description"),
    merged.get("confirmation_name"),
    merged.get("last_delivery"),
    timestamp,
    gr_id,
),
```

- [ ] **Step 3: `update_gr` approved — remove from allowed keys and UPDATE**

**Allowed keys** (line 800-803) — remove `"delivery_from", "delivery_to",`:
```python
# Before:
for key in ("con_value", "tax_rate", "remark", "gr_no",
            "goods_service_description", "confirmation_name",
            "delivery_from", "delivery_to", "last_delivery")

# After:
for key in ("con_value", "tax_rate", "remark", "gr_no",
            "goods_service_description", "confirmation_name",
            "last_delivery")
```

**UPDATE SQL** (lines 837-858) — remove `delivery_from = ?,` and `delivery_to = ?,` from SET clause, and remove corresponding values:
```python
# Before (SET clause, lines 839-851):
set con_value = ?,
    gross_cost = ?,
    tax_rate = ?,
    remark = ?,
    gr_no = ?,
    goods_service_description = ?,
    confirmation_name = ?,
    delivery_from = ?,
    delivery_to = ?,
    last_delivery = ?,
    updated_at = ?
where gr_id = ?

# After:
set con_value = ?,
    gross_cost = ?,
    tax_rate = ?,
    remark = ?,
    gr_no = ?,
    goods_service_description = ?,
    confirmation_name = ?,
    last_delivery = ?,
    updated_at = ?
where gr_id = ?
```

**Value tuple** (lines 852-858) — remove `merged.get("delivery_from"), merged.get("delivery_to"),`:
```python
# Before:
(float(con_value),
 float(merged["gross_cost"]) if merged.get("gross_cost") is not None else None,
 merged.get("tax_rate"), merged.get("remark"), merged.get("gr_no"),
 merged.get("goods_service_description"), merged.get("confirmation_name"),
 merged.get("delivery_from"), merged.get("delivery_to"), merged.get("last_delivery"),
 timestamp,
 gr_id),

# After:
(float(con_value),
 float(merged["gross_cost"]) if merged.get("gross_cost") is not None else None,
 merged.get("tax_rate"), merged.get("remark"), merged.get("gr_no"),
 merged.get("goods_service_description"), merged.get("confirmation_name"),
 merged.get("last_delivery"),
 timestamp,
 gr_id),
```

- [ ] **Step 4: Commit**

```bash
git add sc_gr_app/services/gr_service.py
git commit -m "refactor: remove delivery_from/to from GR create/update SQL"
```

---

### Task 4: Backend — Remove `delivery_from`/`delivery_to` from Query, Export, Notification

**Files:**
- Modify: `sc_gr_app/services/query_service.py`
- Modify: `sc_gr_app/notification/templates.py`
- Modify: `sc_gr_app/notification/sender.py`

- [ ] **Step 1: `query_service.py` — remove from `text_columns`**

At lines 567-568, remove the two lines:
```python
# Before (L567-568):
"gr.delivery_from",
"gr.delivery_to",

# After: remove these two lines entirely
```

- [ ] **Step 2: `query_service.py` — remove from `allowed_filters`**

At lines 598-603, remove all delivery-related filter entries:
```python
# Before (L598-603):
"delivery_from": "gr.delivery_from",
"delivery_from_from": "gr.delivery_from",
"delivery_from_to": "gr.delivery_from",
"delivery_to": "gr.delivery_to",
"delivery_to_from": "gr.delivery_to",
"delivery_to_to": "gr.delivery_to",

# After: remove all 6 lines
```

- [ ] **Step 3: `query_service.py` — remove from `allowed_sorts`**

At lines 640-641, remove the two lines:
```python
# Before (L640-641):
"delivery_from": "gr.delivery_from",
"delivery_to": "gr.delivery_to",

# After: remove these two lines
```

- [ ] **Step 4: `notification/templates.py` — remove from `_GR_ORDER`**

At lines 118-121, remove `"delivery_from", "delivery_to",` from the list:
```python
# Before:
_GR_ORDER = ["gr_id", "gr_no", "po_id", "requester_id",
             "estimated_amount", "gross_cost", "tax_rate", "con_value",
             "goods_service_description", "remark", "confirmation_name",
             "delivery_from", "delivery_to", "last_delivery"]

# After:
_GR_ORDER = ["gr_id", "gr_no", "po_id", "requester_id",
             "estimated_amount", "gross_cost", "tax_rate", "con_value",
             "goods_service_description", "remark", "confirmation_name",
             "last_delivery"]
```

Also at lines 275-277, remove the `delivery_from` and `delivery_to` entries from the date-formatting tuple:
```python
# Before:
elif key in ("service_period_start", "service_period_end",
            "contract_from", "contract_to", "delivery_from",
            "delivery_to"):

# After:
elif key in ("service_period_start", "service_period_end",
            "contract_from", "contract_to"):
```

- [ ] **Step 5: `notification/sender.py` — remove from `_attach_child_grs` SELECT**

At lines 187-188, remove `delivery_from, delivery_to` from the SELECT:
```python
# Before:
SELECT gr_id, gr_no, estimated_amount, con_value, gross_cost, status,
       goods_service_description, delivery_from, delivery_to
FROM gr_requests

# After:
SELECT gr_id, gr_no, estimated_amount, con_value, gross_cost, status,
       goods_service_description
FROM gr_requests
```

- [ ] **Step 6: Commit**

```bash
git add sc_gr_app/services/query_service.py sc_gr_app/notification/templates.py sc_gr_app/notification/sender.py
git commit -m "refactor: remove delivery_from/to from query, export, and notification code"
```

---

### Task 5: Backend — Update Import Template Endpoint (bridge.py)

**Files:**
- Modify: `sc_gr_app/api/bridge.py`

- [ ] **Step 1: Remove `delivery_from`/`delivery_to` from template headers, hints, sample**

At lines 2141-2155, remove `delivery_from` and `delivery_to` from all three parallel arrays. Also update the `estimated_amount` hint from `"Required"` to `"Optional"`:

**`headers` list (L2141-2144):**

```python
# Before:
headers = ["po_no", "gr_no", "requester_id",
           "estimated_amount", "con_value", "status", "remark", "tax_rate",
           "gross_cost", "goods_service_description", "confirmation_name",
           "delivery_from", "delivery_to", "last_delivery"]

# After:
headers = ["po_no", "gr_no", "requester_id",
           "estimated_amount", "con_value", "status", "remark", "tax_rate",
           "gross_cost", "goods_service_description", "confirmation_name",
           "last_delivery"]
```

**`hints` list (L2145-2151):**

```python
# Before:
hints = ["Required (PO NO, must exist in DB)",
         "Required (business NO, must be unique)",
         "Optional (defaults to importer)",
         "Required", "Required",
         "approved/finished", "Optional",
         "Optional (e.g. 13)", "Optional", "Optional", "Optional",
         "Required (YYYY-MM-DD or MM/DD/YYYY)", "Required (YYYY-MM-DD or MM/DD/YYYY)", "Optional (YYYY-MM-DD or MM/DD/YYYY)"]

# After:
hints = ["Required (PO NO, must exist in DB)",
         "Required (business NO, must be unique)",
         "Optional (defaults to importer)",
         "Optional", "Required",
         "approved/finished", "Optional",
         "Optional (e.g. 13)", "Optional", "Optional", "Optional",
         "Optional (YYYY-MM-DD or MM/DD/YYYY)"]
```

**`sample` list (L2152-2155):**

```python
# Before:
sample = ["", "[EXAMPLE]", current_user["user_id"],
          "10000", "10000", "approved", "", "13",
          "", "Sample goods description", "",
          "2026-01-01", "2026-12-31", ""]

# After:
sample = ["", "[EXAMPLE]", current_user["user_id"],
          "10000", "10000", "approved", "", "13",
          "", "Sample goods description", "",
          ""]
```

- [ ] **Step 2: Commit**

```bash
git add sc_gr_app/api/bridge.py
git commit -m "refactor: remove delivery_from/to from GR import template endpoint"
```

---

### Task 6: Frontend — Remove `delivery_from`/`delivery_to` from Components

**Files:**
- Modify: `frontend/src/components/po/GrFormDialog.vue`
- Modify: `frontend/src/views/GrDetailView.vue`
- Modify: `frontend/src/views/GrListView.vue`
- Modify: `frontend/src/components/export/ExportDialog.vue`
- Modify: `frontend/src/views/PoDetailView.vue`

- [ ] **Step 1: `GrFormDialog.vue` — remove date-picker rows and emptyForm fields**

Remove the date-picker row (lines 71-82 in template):
```vue
<!-- Before (L71-82): remove this entire el-row block -->
<el-row :gutter="16">
  <el-col :span="12">
    <el-form-item :label="$t('gr.deliveryFrom')">
      <el-date-picker v-model="form.delivery_from" type="date" format="YYYY-MM-DD" value-format="YYYY-MM-DD" style="width:100%" />
    </el-form-item>
  </el-col>
  <el-col :span="12">
    <el-form-item :label="$t('gr.deliveryTo')">
      <el-date-picker v-model="form.delivery_to" type="date" format="YYYY-MM-DD" value-format="YYYY-MM-DD" style="width:100%" />
    </el-form-item>
  </el-col>
</el-row>
```

Remove `delivery_from: null, delivery_to: null,` from `emptyForm()` (line 169):
```javascript
// Before:
goods_service_description: '', confirmation_name: '', delivery_from: null, delivery_to: null, last_delivery: 'N'

// After:
goods_service_description: '', confirmation_name: '', last_delivery: 'N'
```

- [ ] **Step 2: `GrDetailView.vue` — remove display rows**

Remove the two `el-descriptions-item` lines (L49-50):
```vue
<!-- Before: remove these two lines -->
<el-descriptions-item :label="$t('gr.deliveryFrom')">{{ (gr.delivery_from || '').slice(0, 10) || '-' }}</el-descriptions-item>
<el-descriptions-item :label="$t('gr.deliveryTo')">{{ (gr.delivery_to || '').slice(0, 10) || '-' }}</el-descriptions-item>
```

- [ ] **Step 3: `GrListView.vue` — remove table columns, filter config, sort config**

Remove table columns (L70-75):
```vue
<!-- Before: remove this block -->
<el-table-column prop="delivery_from" :label="$t('gr.deliveryFrom')" width="110" sortable>
  <template #default="{ row }">{{ (row.delivery_from || '').slice(0, 10) || '-' }}</template>
</el-table-column>
<el-table-column prop="delivery_to" :label="$t('gr.deliveryTo')" width="110" sortable>
  <template #default="{ row }">{{ (row.delivery_to || '').slice(0, 10) || '-' }}</template>
</el-table-column>
```

Remove filter config entries (L283-284):
```javascript
// Before: remove these two lines
{ name: 'delivery_from', label: t('gr.deliveryFrom'), type: 'date-range' },
{ name: 'delivery_to', label: t('gr.deliveryTo'), type: 'date-range' },
```

Remove sort config entries (L522-523):
```javascript
// Before: remove these two lines
{ prop: 'delivery_from', label: t('gr.deliveryFrom'), width: '110' },
{ prop: 'delivery_to', label: t('gr.deliveryTo'), width: '110' },
```

- [ ] **Step 4: `ExportDialog.vue` — remove export columns**

Remove the two export column definitions (L170-171):
```javascript
// Before: remove these two lines
{ key: 'delivery_from', label: t('gr.deliveryFrom'), getValue: r => (r.delivery_from || '').slice(0, 10) },
{ key: 'delivery_to', label: t('gr.deliveryTo'), getValue: r => (r.delivery_to || '').slice(0, 10) },
```

- [ ] **Step 5: `PoDetailView.vue` — remove export columns**

Remove the two export column definitions (L487-488):
```javascript
// Before: remove these two lines
{ key: 'delivery_from', label: t('gr.deliveryFrom'), getValue: r => (r.delivery_from || '').slice(0, 10) },
{ key: 'delivery_to', label: t('gr.deliveryTo'), getValue: r => (r.delivery_to || '').slice(0, 10) },
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/po/GrFormDialog.vue frontend/src/views/GrDetailView.vue frontend/src/views/GrListView.vue frontend/src/components/export/ExportDialog.vue frontend/src/views/PoDetailView.vue
git commit -m "refactor: remove delivery_from/to fields from all frontend components"
```

---

### Task 7: Frontend — Remove `delivery_from`/`delivery_to` i18n Keys

**Files:**
- Modify: `frontend/src/i18n/locales/zh-CN.js`
- Modify: `frontend/src/i18n/locales/en-US.js`

- [ ] **Step 1: Remove from `zh-CN.js`**

Remove lines 424-425:
```javascript
// Before: remove these two lines
deliveryFrom: '交付从',
deliveryTo: '交付至',
```

- [ ] **Step 2: Remove from `en-US.js`**

Remove lines 428-429:
```javascript
// Before: remove these two lines
deliveryFrom: 'Delivery From',
deliveryTo: 'Delivery To',
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/i18n/locales/zh-CN.js frontend/src/i18n/locales/en-US.js
git commit -m "refactor: remove deliveryFrom/deliveryTo i18n keys"
```

---

### Task 8: Tests — Update Import Tests to Match New Validation

**Files:**
- Modify: `tests/test_import_service.py`

- [ ] **Step 1: Delete two obsolete test methods**

Remove `test_gr_fails_without_delivery_from` (L234-245) and `test_gr_fails_without_delivery_to` (L247-258) entirely. These tests assert validation errors that no longer apply.

- [ ] **Step 2: Remove `delivery_from`/`delivery_to` from all test data dictionaries**

Remove `"delivery_from": "2026-01-01", "delivery_to": "2026-12-31"` from every row dict in the test file. These appear at:

- Line 137 (test_gr_rejects_invalid_status)
- Line 146 (same test, second row)
- Line 155 (same test, third row)
- Line 164 (test_gr_allows_approved_and_finished)
- Line 173 (same test, second row)
- Line 216 (test_gr_fails_without_gr_no)
- Line 229 (test_gr_fails_without_con_value)
- Line 242 (test_gr_fails_without_delivery_from — this entire test is deleted in Step 1)
- Line 255 (test_gr_fails_without_delivery_to — this entire test is deleted in Step 1)
- Line 314 (test_gr_import_without_owner)

For each row dict, change:
```python
# Before:
rows = [{"po_no": "PONO-...", "gr_no": "GR-001", "estimated_amount": "10000",
          "con_value": "10000", "delivery_from": "2026-01-01", "delivery_to": "2026-12-31", "status": "draft"}]

# After:
rows = [{"po_no": "PONO-...", "gr_no": "GR-001", "estimated_amount": "10000",
          "con_value": "10000", "status": "draft"}]
```

- [ ] **Step 3: Add a test verifying `estimated_amount` is optional**

Add a new test method that imports a row without `estimated_amount` and expects it to pass:

```python
def test_gr_allows_missing_estimated_amount(self, app_config):
    migrate(app_config)
    with connect(app_config) as conn:
        self._seed_gr_deps(conn)
    rows = [{"po_no": "PONO-PO-0000001-20260701-001", "gr_no": "GR-OPT-001",
              "con_value": "10000", "status": "approved"}]
    preview = import_service.preview_gr_import(app_config, rows)
    assert preview[0]["_valid"] is True
```

- [ ] **Step 4: Commit**

```bash
git add tests/test_import_service.py
git commit -m "test: update import tests for optional estimated_amount and removed delivery fields"
```

---

### Task 9: Verification

- [ ] **Step 1: Run backend tests**

```bash
cd c:/Users/V2SE7PP/Projects/contract && python -m pytest test_api.py -v --tb=short
```

- [ ] **Step 2: Verify no remaining references to delivery_from/delivery_to in code**

```bash
cd c:/Users/V2SE7PP/Projects/contract && grep -rn "delivery_from\|delivery_to\|deliveryFrom\|deliveryTo" sc_gr_app/ frontend/src/ --include="*.py" --include="*.vue" --include="*.js"
```

Expected: only results in database schema/migration files (column definitions) and potentially old docs. No results in active application code.

- [ ] **Step 3: Verify frontend builds**

```bash
cd c:/Users/V2SE7PP/Projects/contract/frontend && npm run build 2>&1 | tail -20
```

Expected: build succeeds with no errors.

- [ ] **Step 4: Commit any fixes from verification**

If verification found issues:
```bash
git add <fixed files>
git commit -m "fix: address delivery_from/to cleanup issues found in verification"
```
