# PO Budget Calculation Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix `consumed_amount` to only count approved GR Gross Cost, add `pending_total_incl_tax` field, and fix `manager_confirm` gap in query/PO services.

**Architecture:** Three backend layers change: `budget_service.py` (pure computation), `sender.py` (email data assembly), `query_service.py` + `sc_service.py` (frontend data pipeline). Then `templates.py` (email HTML), `PoDetailView.vue` (UI), and i18n files update to display the new fields.

**Tech Stack:** Python 3.11 + SQLite + Vue 3 + Element Plus

---

### Task 1: Add `pending_total_incl_tax` to `compute_po_budget_decimal`

**Files:**
- Modify: `sc_gr_app/services/budget_service.py:112-134`

- [ ] **Step 1: Update the SQL and return dict**

Edit the `gr_totals` query and return statement in `compute_po_budget_decimal`:

```python
    gr_totals = conn.execute(
        """
        select
          coalesce(sum(case when status in ('pending', 'manager_confirm') then estimated_amount else 0 end), 0)
            as pending_total,
          coalesce(sum(case when status = 'approved' then con_value else 0 end), 0)
            as con_value_total,
          coalesce(sum(case when status in ('pending', 'manager_confirm')
            then estimated_amount * (1 + coalesce(tax_rate, 0) / 100.0) else 0 end), 0)
            as pending_total_incl_tax
        from gr_requests
        where po_id = ?
        """,
        (po_id,),
    ).fetchone()

po_amount = _decimal_or_zero(po["po_amount"])
po_pending_total = _decimal_or_zero(gr_totals["pending_total"])
po_con_value_total = _decimal_or_zero(gr_totals["con_value_total"])
po_pending_total_incl_tax = _decimal_or_zero(gr_totals["pending_total_incl_tax"])

return {
    "po_amount": po_amount,
    "po_pending_total": po_pending_total,
    "po_con_value_total": po_con_value_total,
    "po_pending_total_incl_tax": po_pending_total_incl_tax,
    "open_po_amount": po_amount - po_pending_total - po_con_value_total,
}
```

- [ ] **Step 2: Run existing tests to check for breakage**

```bash
uv run pytest tests/test_budget_service.py -q
```

Expected: test failures because existing tests assert on old dict shape (missing `po_pending_total_incl_tax`).

- [ ] **Step 3: Commit**

```bash
git add sc_gr_app/services/budget_service.py
git commit -m "feat: add pending_total_incl_tax to compute_po_budget_decimal"
```

---

### Task 2: Add `pending_total_incl_tax` to `compute_sc_budget_decimal`

**Files:**
- Modify: `sc_gr_app/services/budget_service.py:45-79`

- [ ] **Step 1: Update the SC-level gr_totals SQL and return dict**

```python
    gr_totals = conn.execute(
        """
        select
          coalesce(sum(case when gr.status in ('pending', 'manager_confirm') then coalesce(gr.con_value, gr.estimated_amount) else 0 end), 0)
            as pending_total,
          coalesce(sum(case when gr.status = 'approved' then gr.con_value else 0 end), 0)
            as con_value_total,
          coalesce(sum(case when gr.status in ('pending', 'manager_confirm')
            then gr.estimated_amount * (1 + coalesce(gr.tax_rate, 0) / 100.0) else 0 end), 0)
            as pending_total_incl_tax
        from gr_requests gr
        join pos po on po.po_id = gr.po_id
        where po.sc_id = ?
        """,
        (sc_id,),
    ).fetchone()

sc_amount = _decimal_or_zero(sc["sc_amount"])
sc_pending_total = _decimal_or_zero(gr_totals["pending_total"])
sc_con_value_total = _decimal_or_zero(gr_totals["con_value_total"])
sc_pending_total_incl_tax = _decimal_or_zero(gr_totals["pending_total_incl_tax"])
allocated_po_amount = _decimal_or_zero(po_totals["allocated_po_amount"])

return {
    "sc_amount": sc_amount,
    "sc_pending_total": sc_pending_total,
    "sc_con_value_total": sc_con_value_total,
    "sc_pending_total_incl_tax": sc_pending_total_incl_tax,
    "sc_available_amount": sc_amount - sc_pending_total - sc_con_value_total,
    "allocated_po_amount": allocated_po_amount,
    "unallocated_sc_amount": sc_amount - allocated_po_amount,
}
```

- [ ] **Step 2: Run tests**

```bash
uv run pytest tests/test_budget_service.py -q
```

- [ ] **Step 3: Commit**

```bash
git add sc_gr_app/services/budget_service.py
git commit -m "feat: add pending_total_incl_tax to compute_sc_budget_decimal"
```

---

### Task 3: Fix `consumed_amount` and add `pending_total_incl_tax` in `sender.py`

**Files:**
- Modify: `sc_gr_app/notification/sender.py:41-68` (`_attach_budget_info` for PO)
- Modify: `sc_gr_app/notification/sender.py:70-88` (`_attach_budget_info` for SC)
- Modify: `sc_gr_app/notification/sender.py:120-136` (`_attach_child_pos`)

- [ ] **Step 1: Fix `_attach_budget_info` for PO (consumed + new field)**

Replace the PO block (lines 51-68):

```python
    if entity_type == "po":
        gr_totals = conn.execute(
            """
            SELECT
              COALESCE(SUM(CASE WHEN status IN ('pending', 'manager_confirm')
                                 THEN estimated_amount ELSE 0 END), 0) AS pending_total,
              COALESCE(SUM(CASE WHEN status = 'approved'
                                 THEN con_value ELSE 0 END), 0) AS con_value_total,
              COALESCE(SUM(CASE WHEN status IN ('pending', 'manager_confirm')
                                 THEN estimated_amount * (1 + COALESCE(tax_rate, 0) / 100.0)
                                 ELSE 0 END), 0) AS pending_total_incl_tax
            FROM gr_requests
            WHERE po_id = ?
            """,
            (entity_id,),
        ).fetchone()
        po_amount = entity_info.get("po_amount") or 0
        pending = gr_totals["pending_total"] or 0
        approved = gr_totals["con_value_total"] or 0
        pending_incl_tax = gr_totals["pending_total_incl_tax"] or 0
        entity_info["open_po_amount"] = po_amount - pending - approved
        entity_info["consumed_amount"] = approved
        entity_info["pending_total"] = pending
        entity_info["pending_total_incl_tax"] = pending_incl_tax
```

- [ ] **Step 2: Fix `_attach_budget_info` for SC (consumed + new field)**

Replace the SC block (lines 70-88):

```python
    elif entity_type == "sc":
        gr_totals = conn.execute(
            """
            SELECT
              COALESCE(SUM(CASE WHEN gr.status IN ('pending', 'manager_confirm')
                                 THEN COALESCE(gr.con_value, gr.estimated_amount) ELSE 0 END), 0) AS pending_total,
              COALESCE(SUM(CASE WHEN gr.status = 'approved'
                                 THEN gr.con_value ELSE 0 END), 0) AS con_value_total,
              COALESCE(SUM(CASE WHEN gr.status IN ('pending', 'manager_confirm')
                                 THEN gr.estimated_amount * (1 + COALESCE(gr.tax_rate, 0) / 100.0)
                                 ELSE 0 END), 0) AS pending_total_incl_tax
            FROM gr_requests gr
            JOIN pos po ON po.po_id = gr.po_id
            WHERE po.sc_id = ?
            """,
            (entity_id,),
        ).fetchone()
        sc_amount = entity_info.get("sc_amount") or 0
        pending = gr_totals["pending_total"] or 0
        approved = gr_totals["con_value_total"] or 0
        pending_incl_tax = gr_totals["pending_total_incl_tax"] or 0
        entity_info["sc_available_amount"] = sc_amount - pending - approved
        entity_info["consumed_amount"] = approved
        entity_info["pending_total"] = pending
        entity_info["pending_total_incl_tax"] = pending_incl_tax

        _attach_child_pos(conn, entity_id, entity_info)
```

- [ ] **Step 3: Fix `_attach_child_pos` (consumed + new field in child PO cards)**

Replace the per-PO budget block inside `_attach_child_pos` (lines 120-136):

```python
        gr_totals = conn.execute(
            """
            SELECT
              COALESCE(SUM(CASE WHEN status IN ('pending', 'manager_confirm')
                                 THEN estimated_amount ELSE 0 END), 0) AS pending_total,
              COALESCE(SUM(CASE WHEN status = 'approved'
                                 THEN con_value ELSE 0 END), 0) AS con_value_total,
              COALESCE(SUM(CASE WHEN status IN ('pending', 'manager_confirm')
                                 THEN estimated_amount * (1 + COALESCE(tax_rate, 0) / 100.0)
                                 ELSE 0 END), 0) AS pending_total_incl_tax
            FROM gr_requests
            WHERE po_id = ?
            """,
            (po["po_id"],),
        ).fetchone()
        po_amount = po.get("po_amount") or 0
        pending = gr_totals["pending_total"] or 0
        approved = gr_totals["con_value_total"] or 0
        pending_incl_tax = gr_totals["pending_total_incl_tax"] or 0
        po["open_po_amount"] = po_amount - pending - approved
        po["consumed_amount"] = approved
        po["pending_total"] = pending
        po["pending_total_incl_tax"] = pending_incl_tax
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_notification_templates.py -q
```

- [ ] **Step 5: Commit**

```bash
git add sc_gr_app/notification/sender.py
git commit -m "fix: consumed_amount to approved only, add pending_total_incl_tax in sender"
```

---

### Task 4: Fix `manager_confirm` gap and add `pending_total_incl_tax` in `query_service.py`

**Files:**
- Modify: `sc_gr_app/services/query_service.py:383-390` (GR totals subquery in `search_pos`)

- [ ] **Step 1: Update the GR totals subquery and main SELECT**

Replace the GR totals LEFT JOIN (lines 383-390):

```python
        left join (
          select
            po_id,
            sum(case when status in ('pending', 'manager_confirm')
                      then estimated_amount else 0 end) as pending_total,
            sum(case when status = 'approved'
                      then con_value else 0 end) as con_value_total,
            sum(case when status in ('pending', 'manager_confirm')
                      then estimated_amount * (1 + coalesce(tax_rate, 0) / 100.0)
                      else 0 end) as pending_total_incl_tax
          from gr_requests
          group by po_id
        ) gr_totals on gr_totals.po_id = po.po_id
```

And update the main SELECT to include the new column. Replace the `po.po_amount - ...` line (lines 377-378):

```python
          po.po_amount - coalesce(gr_totals.pending_total, 0)
            - coalesce(gr_totals.con_value_total, 0) as open_po_amount,
          coalesce(gr_totals.con_value_total, 0) as consumed_amount,
          coalesce(gr_totals.pending_total, 0) as po_pending_total,
          coalesce(gr_totals.pending_total_incl_tax, 0) as po_pending_total_incl_tax
```

- [ ] **Step 2: Run tests**

```bash
uv run pytest tests/test_query_service.py -q
```

- [ ] **Step 3: Commit**

```bash
git add sc_gr_app/services/query_service.py
git commit -m "fix: add manager_confirm to search_pos GR totals, add consumed and pending_incl_tax"
```

---

### Task 5: Fix `manager_confirm` gap in `po_service.py` `_po_gr_usage`

**Files:**
- Modify: `sc_gr_app/services/po_service.py:91-99`

- [ ] **Step 1: Add `manager_confirm` to status filter and usage logic**

```python
    usage = Decimal("0")
    rows = conn.execute(
        """
        select status, estimated_amount, con_value
        from gr_requests
        where po_id = ?
          and status in ('pending', 'manager_confirm', 'approved')
        """,
        (po_id,),
    )
    for row in rows:
        if row["status"] in ("pending", "manager_confirm"):
            usage += Decimal(str(row["estimated_amount"]))
        else:
            usage += Decimal(str(row["con_value"]))
    return usage
```

- [ ] **Step 2: Run tests**

```bash
uv run pytest tests/test_po_service.py -q
```

- [ ] **Step 3: Commit**

```bash
git add sc_gr_app/services/po_service.py
git commit -m "fix: include manager_confirm GRs in _po_gr_usage budget guard"
```

---

### Task 6: Pass budget fields explicitly in `get_sc_detail`

**Files:**
- Modify: `sc_gr_app/services/sc_service.py:1158-1161`

- [ ] **Step 1: Add `consumed_amount`, `pending_total`, `pending_total_incl_tax` to PO dicts**

```python
    for po in pos:
        po["budget"] = compute_po_budget(config, po["po_id"])
        po["open_po_amount"] = po["budget"]["open_po_amount"]
        po["consumed_amount"] = po["budget"]["po_con_value_total"]
        po["pending_total"] = po["budget"]["po_pending_total"]
        po["pending_total_incl_tax"] = po["budget"]["po_pending_total_incl_tax"]
```

- [ ] **Step 2: Run tests**

```bash
uv run pytest tests/test_sc_po_gr_flow.py -q
```

- [ ] **Step 3: Commit**

```bash
git add sc_gr_app/services/sc_service.py
git commit -m "feat: pass consumed/pending/tax fields to PO detail frontend"
```

---

### Task 7: Update `templates.py` PO email fields

**Files:**
- Modify: `sc_gr_app/notification/templates.py:260-266` (`_po_fields`)
- Modify: `sc_gr_app/notification/templates.py:406-408` (`_child_po_table`)

- [ ] **Step 1: Add new budget rows to `_po_fields`**

Replace the financial section in `_po_fields` (around lines 261-266):

```python
    rows.append(row("PO Amount", _fmt_amount(info.get("po_amount"))))
    if "consumed_amount" in info:
        rows.append(row("Consumed Amount", _fmt_amount(info.get("consumed_amount"))))
    if "pending_total" in info:
        rows.append(row("Pending Est. (excl. tax)", _fmt_amount(info.get("pending_total"))))
    if "pending_total_incl_tax" in info:
        rows.append(row("Pending Est. (incl. tax)", _fmt_amount(info.get("pending_total_incl_tax"))))
    if "open_po_amount" in info:
        rows.append(row("Open PO Amount", _fmt_amount(info.get("open_po_amount"))))
```

- [ ] **Step 2: Update `_child_po_table` header and rows**

Replace header (lines 403-411):

```python
    header = (
        f'<tr style="background-color:#f8f9fa">'
        f'<th style="{_TH_STYLE}">PO No</th>'
        f'<th style="{_TH_STYLE}">Vendor</th>'
        f'<th style="{_TH_STYLE}">PO Amount</th>'
        f'<th style="{_TH_STYLE}">Consumed</th>'
        f'<th style="{_TH_STYLE}">Pending (excl. tax)</th>'
        f'<th style="{_TH_STYLE}">Pending (incl. tax)</th>'
        f'<th style="{_TH_STYLE}">Open Amount</th>'
        f'<th style="{_TH_STYLE}">Contract End</th>'
        f'<th style="{_TH_STYLE}">Status</th>'
        f'</tr>'
    )
```

Replace row rendering (lines 416-435):

```python
    for po in child_pos:
        po_no = po.get("po_no") or "-"
        vendor = po.get("vendor_name") or "-"
        po_amount = _fmt_amount(po.get("po_amount"))
        consumed = _fmt_amount(po.get("consumed_amount"))
        pending_excl = _fmt_amount(po.get("pending_total"))
        pending_incl = _fmt_amount(po.get("pending_total_incl_tax"))
        open_amt = _fmt_amount(po.get("open_po_amount"))
        contract_to = _fmt_datetime(po.get("contract_to"))
        status = _status_badge(po.get("status") or "")

        tr = (
            f'<tr>'
            f'<td style="{_TD_STYLE}">{po_no}</td>'
            f'<td style="{_TD_STYLE}">{vendor}</td>'
            f'<td style="{_TD_STYLE}">{po_amount}</td>'
            f'<td style="{_TD_STYLE}">{consumed}</td>'
            f'<td style="{_TD_STYLE}">{pending_excl}</td>'
            f'<td style="{_TD_STYLE}">{pending_incl}</td>'
            f'<td style="{_TD_STYLE}">{open_amt}</td>'
            f'<td style="{_TD_STYLE}">{contract_to}</td>'
            f'<td style="{_TD_STYLE}">{status}</td>'
            f'</tr>'
        )
        rows.append(tr)
```

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/test_notification_templates.py -q
```

- [ ] **Step 4: Commit**

```bash
git add sc_gr_app/notification/templates.py
git commit -m "feat: add pending excl/incl tax rows to PO email templates"
```

---

### Task 8: Add i18n keys

**Files:**
- Modify: `frontend/src/i18n/locales/zh-CN.js`
- Modify: `frontend/src/i18n/locales/en-US.js`

- [ ] **Step 1: Add Chinese keys**

In `zh-CN.js`, after `openPoAmount` inside the `po` section (line 234):

```js
    openPoAmount: '可用采购订单金额',
    consumedAmount: '已消费金额',
    pendingExclTax: '待批准预估消费金额（不含税）',
    pendingInclTax: '待批准预估消费金额（含税）',
```

- [ ] **Step 2: Add English keys**

In `en-US.js`, after `openPoAmount` inside the `po` section (line 234):

```js
    openPoAmount: 'Open PO Amount',
    consumedAmount: 'Consumed Amount',
    pendingExclTax: 'Pending Est. Amount (excl. tax)',
    pendingInclTax: 'Pending Est. Amount (incl. tax)',
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/i18n/locales/zh-CN.js frontend/src/i18n/locales/en-US.js
git commit -m "feat: add i18n keys for consumed/pending tax PO fields"
```

---

### Task 9: Update `PoDetailView.vue` to show new budget fields

**Files:**
- Modify: `frontend/src/views/PoDetailView.vue:39-41`

- [ ] **Step 1: Add three description items after `openPoAmount`**

Replace lines 39-41 in the template:

```html
          <el-descriptions-item :label="$t('po.poAmount')"><AmountDisplay :value="po.po_amount" /></el-descriptions-item>
          <el-descriptions-item :label="$t('po.openPoAmount')"><AmountDisplay :value="po.open_po_amount" /></el-descriptions-item>
          <el-descriptions-item :label="$t('po.consumedAmount')"><AmountDisplay :value="po.consumed_amount || po.budget?.po_con_value_total" /></el-descriptions-item>
          <el-descriptions-item :label="$t('po.pendingExclTax')"><AmountDisplay :value="po.pending_total || po.budget?.po_pending_total" /></el-descriptions-item>
          <el-descriptions-item :label="$t('po.pendingInclTax')"><AmountDisplay :value="po.pending_total_incl_tax || po.budget?.po_pending_total_incl_tax" /></el-descriptions-item>
```

- [ ] **Step 2: Build frontend**

```bash
cd frontend && npm run build
```

- [ ] **Step 3: Verify build succeeds**

```bash
ls sc_gr_app/web/assets/
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/PoDetailView.vue sc_gr_app/web/
git commit -m "feat: add consumed/pending tax fields to PO detail UI"
```

---

### Task 10: Update budget service tests for new dict shape

**Files:**
- Modify: `tests/test_budget_service.py`

- [ ] **Step 1: Update all test assertions to include new field**

Update every expected dict to include the new key. The key changes:

`test_compute_sc_budget_sums_pending_approved_and_po_allocation`:
```python
    assert budget == {
        "sc_amount": 1000.0,
        "sc_pending_total": 100.0,
        "sc_con_value_total": 150.0,
        "sc_pending_total_incl_tax": 100.0,  # 100 * (1 + 0/100) = 100
        "sc_available_amount": 750.0,
        "allocated_po_amount": 800.0,
        "unallocated_sc_amount": 200.0,
    }
```

`test_compute_po_budget_derives_open_po_amount`:
```python
    assert budget == {
        "po_amount": 800.0,
        "po_pending_total": 100.0,
        "po_con_value_total": 150.0,
        "po_pending_total_incl_tax": 100.0,  # 100 * (1 + 0/100) = 100
        "open_po_amount": 550.0,
    }
```

`test_compute_sc_budget_returns_zero_totals_when_sc_has_no_pos`:
```python
    assert budget == {
        "sc_amount": 1000.0,
        "sc_pending_total": 0.0,
        "sc_con_value_total": 0.0,
        "sc_pending_total_incl_tax": 0.0,
        "sc_available_amount": 1000.0,
        "allocated_po_amount": 0.0,
        "unallocated_sc_amount": 1000.0,
    }
```

`test_compute_po_budget_returns_zero_totals_when_po_has_no_grs`:
```python
    assert budget == {
        "po_amount": 800.0,
        "po_pending_total": 0.0,
        "po_con_value_total": 0.0,
        "po_pending_total_incl_tax": 0.0,
        "open_po_amount": 800.0,
    }
```

`test_compute_sc_budget_counts_grs_once_across_multiple_pos`:
```python
    assert budget == {
        "sc_amount": 1000.0,
        "sc_pending_total": 150.0,
        "sc_con_value_total": 225.0,
        "sc_pending_total_incl_tax": 150.0,  # 100+50 * (1+0/100)
        "sc_available_amount": 625.0,
        "allocated_po_amount": 1000.0,
        "unallocated_sc_amount": 0.0,
    }
```

The decimal tests (`test_decimal_sc_budget_uses_exact_decimal_arithmetic` and `test_decimal_po_budget_uses_exact_decimal_arithmetic`) only assert on individual keys, not the full dict shape — they should still pass.

- [ ] **Step 2: Add a new test for pending_total_incl_tax with non-zero tax_rate**

```python
def test_po_pending_total_incl_tax_applies_tax_rate(app_config):
    """pending_total_incl_tax = estimated_amount * (1 + tax_rate/100)"""
    migrate(app_config)
    with connect(app_config) as conn:
        seed_user(conn)
        seed_sc(conn, sc_amount=1000)
        seed_vendor(conn)
        seed_po(conn, po_amount=500)
        # GR with 13% tax
        conn.execute(
            """
            insert into gr_requests (
              gr_id, po_id, requester_id, estimated_amount, con_value,
              tax_rate, status, created_by, created_at
            ) values ('GR1', 'PO1', 'U1', 100, NULL, 13, 'pending', 'U1', ?)
            """,
            (TIMESTAMP,),
        )
        # GR with no tax
        conn.execute(
            """
            insert into gr_requests (
              gr_id, po_id, requester_id, estimated_amount, con_value,
              tax_rate, status, created_by, created_at
            ) values ('GR2', 'PO1', 'U1', 200, NULL, NULL, 'manager_confirm', 'U1', ?)
            """,
            (TIMESTAMP,),
        )
        conn.commit()

    budget = compute_po_budget(app_config, "PO1")

    assert budget["po_pending_total"] == 300.0              # 100 + 200
    assert budget["po_pending_total_incl_tax"] == 313.0     # 100*1.13 + 200*1.0
    assert budget["po_con_value_total"] == 0.0
    assert budget["consumed_amount"] not in budget  # consumed not in budget_service
```

- [ ] **Step 3: Run all budget tests**

```bash
uv run pytest tests/test_budget_service.py -v
```

Expected: all tests PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/test_budget_service.py
git commit -m "test: update budget tests for pending_total_incl_tax, add tax rate test"
```

---

### Task 11: Add tests for `_po_gr_usage` manager_confirm fix

**Files:**
- Modify: `tests/test_po_service.py`

- [ ] **Step 1: Add test for manager_confirm GR blocking PO amount reduction**

In `tests/test_po_service.py`, add a new test method to the `TestPoVendorRestriction` class or as a standalone test:

```python
def test_update_po_rejects_amount_below_manager_confirm_gr_usage(self, app_config):
    """PO amount cannot drop below usage of manager_confirm GRs."""
    migrate(app_config)
    seed_users(app_config)

    with connect(app_config) as conn:
        admin = dict(conn.execute(
            "select * from users where role = 'admin' limit 1"
        ).fetchone())

    sc = create_sc_draft(app_config, admin, {
        "requester_id": admin["user_id"],
    })
    from sc_gr_app.services.sc_service import submit_sc, approve_sc
    from sc_gr_app.services.vendor_service import create_vendor as make_vendor
    from sc_gr_app.services.po_service import submit_po as submit_po_fn

    v = make_vendor(app_config, admin, {
        "vendor_id": "V-TEST",
        "vendor_name": "Test Vendor",
        "service_scope": "General Service",
        "ksrm_vendor_code": "KTEST",
    })
    add_sc_vendor(app_config, admin, sc["sc_id"], v["vendor_id"])
    submit_sc(app_config, admin, sc["sc_id"])
    approve_sc(app_config, admin, sc["sc_id"])

    po = create_po(app_config, admin, {
        "sc_id": sc["sc_id"],
        "vendor_id": v["vendor_id"],
        "po_amount": "500",
    })
    submit_po_fn(app_config, admin, po["po_id"])

    # Insert a manager_confirm GR worth 300
    with connect(app_config) as conn:
        conn.execute(
            """
            insert into gr_requests (
              gr_id, po_id, requester_id, estimated_amount,
              status, created_by, created_at
            ) values ('GR-MC', ?, 'U1', 300, 'manager_confirm', 'U1', ?)
            """,
            (po["po_id"], "2026-05-19T00:00:00+00:00"),
        )
        conn.commit()

    from sc_gr_app.services.po_service import update_po as update_po_fn
    with pytest.raises(ConflictError, match="PO amount cannot be below GR usage"):
        update_po_fn(app_config, admin, po["po_id"], {"po_amount": "200"})
```

- [ ] **Step 2: Run the new test**

```bash
uv run pytest tests/test_po_service.py::TestPoVendorRestriction::test_update_po_rejects_amount_below_manager_confirm_gr_usage -v
```

Expected: PASS (the manager_confirm GR blocks the reduction).

- [ ] **Step 3: Run all PO service tests**

```bash
uv run pytest tests/test_po_service.py -q
```

- [ ] **Step 4: Commit**

```bash
git add tests/test_po_service.py
git commit -m "test: verify manager_confirm GRs block PO amount reduction"
```

---

### Task 12: Run full test suite and build

**Files:**
- None (verification only)

- [ ] **Step 1: Run full test suite**

```bash
uv run pytest -q
```

Expected: all tests pass.

- [ ] **Step 2: Rebuild frontend**

```bash
cd frontend && npm run build
```

- [ ] **Step 3: Verify build output**

```bash
ls sc_gr_app/web/assets/PoDetailView-*.js
```

- [ ] **Step 4: Final commit (if any build output changed)**

```bash
git add sc_gr_app/web/assets/
git commit -m "chore: rebuild frontend with PO budget fields"
```
