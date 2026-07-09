# PO Annual Report Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an admin-only PO List annual report export that outputs qualifying PO rows plus SC-only rows, and repair the existing GR annual report export path.

**Architecture:** Backend services produce stable annual-report row dictionaries and enforce admin access. Bridge methods expose those rows to the Vue frontend, which builds one SheetJS workbook through the existing save-file flow. Export helpers are tightened so empty result sets still produce headers and save cancellation does not show false success.

**Tech Stack:** Python 3.11, sqlite3, pytest, Vue 3, Element Plus, vue-i18n, SheetJS `xlsx`

---

## File Structure

- Modify `sc_gr_app/services/po_service.py`: add `get_annual_report_data`, annual-year validation, PO row query, SC-only row query.
- Modify `sc_gr_app/services/gr_service.py`: add missing `get_annual_report_data` for the existing GR annual report UI.
- Modify `sc_gr_app/api/bridge.py`: add `get_po_annual_report` and `get_gr_annual_report` methods.
- Modify `frontend/src/composables/useExport.js`: return `save_file` results and preserve headers for empty row exports.
- Modify `frontend/src/views/PoListView.vue`: add admin-only annual report button, year dialog, export handler, and columns.
- Modify `frontend/src/views/GrListView.vue`: gate annual report button to admins and handle save cancellation.
- Modify `frontend/src/i18n/locales/zh-CN.js` and `frontend/src/i18n/locales/en-US.js`: add PO annual report labels.
- Create `tests/test_po_annual_report.py`: backend unit tests for PO/SC annual report data.
- Modify `tests/test_gr_annual_report.py`: add admin-permission expectation for GR annual report.
- Modify `tests/test_api_bridge.py`: bridge forwarding tests for both annual endpoints.

## Task 1: Backend PO Annual Report Data

**Files:**
- Create: `tests/test_po_annual_report.py`
- Modify: `sc_gr_app/services/po_service.py`

- [ ] **Step 1: Write failing PO annual report tests**

Create `tests/test_po_annual_report.py`:

```python
import sqlite3

import pytest

from sc_gr_app.db.migrations import migrate
from sc_gr_app.errors import PermissionDenied, ValidationError
from sc_gr_app.services import po_service


ADMIN = {"user_id": "U_ADMIN", "role": "admin", "machine_id": "M_ADMIN"}
REQUESTER = {"user_id": "U_REQ", "role": "requester", "machine_id": "M_REQ"}


def _seed(config):
    migrate(config)
    conn = sqlite3.connect(config.db_path)
    conn.executescript(
        """
        INSERT INTO users (user_id, machine_id, user_name, role, email, status, created_at, updated_at)
        VALUES
          ('U_ADMIN', 'M_ADMIN', 'Admin User', 'admin', 'admin@test.local', 'active', '2025-01-01', '2025-01-01'),
          ('U_REQ', 'M_REQ', 'Requester One', 'requester', 'req@test.local', 'active', '2025-01-01', '2025-01-01');

        INSERT INTO vendors (vendor_id, vendor_name, service_scope, created_by, created_at, updated_at)
        VALUES ('V1', 'Vendor One', 'General', 'U_ADMIN', '2025-01-01', '2025-01-01');

        INSERT INTO sc_records (
          sc_id, sc_no, requester_id, request_type, cost_center, sc_amount,
          service_period_start, service_period_end, status, description,
          created_by, created_at, updated_at
        )
        VALUES
          ('SC_APPROVED', 'SC-APP-001', 'U_REQ', 'new', 1000, 10000, '2025-01-01', '2025-12-31', 'approved', 'Approved service', 'U_ADMIN', '2025-01-01', '2025-01-01'),
          ('SC_APPROVED_DRAFT_ONLY', 'SC-APP-002', 'U_REQ', 'new', 2000, 20000, '2025-01-01', '2025-12-31', 'approved', 'No qualifying PO', 'U_ADMIN', '2025-01-01', '2025-01-01'),
          ('SC_DRAFT', 'SC-DRAFT-001', 'U_REQ', 'new', 3000, 30000, '2025-01-01', '2025-12-31', 'draft', 'Draft parent', 'U_ADMIN', '2025-01-01', '2025-01-01');

        INSERT INTO pos (
          po_id, sc_id, vendor_id, po_no, requester_id, po_amount, status,
          contract_from, contract_to, created_at, updated_at, finished_at, request_type
        )
        VALUES
          ('PO_ACTIVE_APPROVED', 'SC_APPROVED', 'V1', 'PO-ACT-APP', 'U_REQ', 6000, 'active', '2025-01-01', '2025-12-31', '2025-01-01', '2025-01-01', NULL, NULL),
          ('PO_DRAFT_APPROVED', 'SC_APPROVED', 'V1', 'PO-DRAFT-APP', 'U_REQ', 1000, 'draft', '2025-01-01', '2025-12-31', '2025-01-01', '2025-01-01', NULL, NULL),
          ('PO_DRAFT_ONLY', 'SC_APPROVED_DRAFT_ONLY', 'V1', 'PO-DRAFT-ONLY', 'U_REQ', 1000, 'draft', '2025-01-01', '2025-12-31', '2025-01-01', '2025-01-01', NULL, NULL),
          ('PO_WITH_YEAR_GR', 'SC_DRAFT', 'V1', 'PO-YEAR-GR', 'U_REQ', 5000, 'draft', '2025-01-01', '2025-12-31', '2025-01-01', '2025-01-01', NULL, NULL),
          ('PO_ACTIVE_INDEPENDENT', NULL, 'V1', 'PO-ACT-FC', 'U_REQ', 7000, 'active', '2025-01-01', '2025-12-31', '2025-01-01', '2025-01-01', NULL, 'FC'),
          ('PO_FINISHED_2025', 'SC_DRAFT', 'V1', 'PO-FIN-2025', 'U_REQ', 8000, 'finished', '2025-01-01', '2025-12-31', '2025-01-01', '2025-06-01', '2025-06-01', NULL),
          ('PO_FINISHED_2024', 'SC_DRAFT', 'V1', 'PO-FIN-2024', 'U_REQ', 9000, 'finished', '2024-01-01', '2024-12-31', '2024-01-01', '2024-06-01', '2024-06-01', NULL);

        INSERT INTO gr_requests (
          gr_id, gr_no, po_id, requester_id, estimated_amount, con_value,
          status, created_by, created_at, approved_date, finished_at
        )
        VALUES
          ('GR_PREV', 'GR-PREV', 'PO_ACTIVE_APPROVED', 'U_REQ', 120, 120, 'approved', 'U_ADMIN', '2024-05-01', '2024-05-02', NULL),
          ('GR_SELECTED', 'GR-SEL', 'PO_ACTIVE_APPROVED', 'U_REQ', 250, 250, 'finished', 'U_ADMIN', '2025-05-01', '2025-05-02', '2025-05-03'),
          ('GR_PENDING', 'GR-PENDING', 'PO_ACTIVE_APPROVED', 'U_REQ', 999, NULL, 'pending', 'U_ADMIN', '2025-05-01', NULL, NULL),
          ('GR_DRAFT_PARENT', 'GR-DRAFT-PARENT', 'PO_WITH_YEAR_GR', 'U_REQ', 300, 300, 'approved', 'U_ADMIN', '2025-02-01', '2025-02-02', NULL);
        """
    )
    conn.commit()
    conn.close()


def _by_po(rows):
    return {row["po_no"]: row for row in rows if row["row_type"] == "po"}


def _by_sc(rows):
    return {row["sc_no"]: row for row in rows if row["row_type"] == "sc"}


def test_po_annual_report_includes_qualifying_po_rows_and_sc_only_rows(app_config):
    _seed(app_config)

    rows = po_service.get_annual_report_data(app_config, "2025", ADMIN)

    po_rows = _by_po(rows)
    sc_rows = _by_sc(rows)
    assert "PO-ACT-APP" in po_rows
    assert "PO-DRAFT-APP" not in po_rows
    assert "PO-DRAFT-ONLY" not in po_rows
    assert "PO-YEAR-GR" in po_rows
    assert "PO-ACT-FC" in po_rows
    assert "PO-FIN-2025" in po_rows
    assert "PO-FIN-2024" not in po_rows
    assert "SC-APP-002" in sc_rows
    assert sc_rows["SC-APP-002"]["requester"] == "Requester One"
    assert sc_rows["SC-APP-002"]["po_no"] == ""
    assert sc_rows["SC-APP-002"]["po_amount"] == ""
    assert sc_rows["SC-APP-002"]["previous_year_gr"] == ""
    assert sc_rows["SC-APP-002"]["selected_year_gr"] == ""


def test_po_annual_report_maps_amounts_and_blank_columns(app_config):
    _seed(app_config)

    rows = po_service.get_annual_report_data(app_config, "2025", ADMIN)
    row = _by_po(rows)["PO-ACT-APP"]

    assert row["requester"] == "Requester One"
    assert row["sc_no"] == "SC-APP-001"
    assert row["short_text"] == "Approved service"
    assert row["sc_amount"] == 10000
    assert row["po_amount"] == 6000
    assert row["previous_year_gr"] == 120
    assert row["selected_year_gr"] == 250
    assert row["previous_year_provision"] == ""
    assert row["selected_year_to_be_gr"] == ""
    assert row["selected_year_fc_gr"] == ""
    assert row["remark"] == ""


def test_po_annual_report_rejects_invalid_year_and_non_admin(app_config):
    _seed(app_config)

    with pytest.raises(ValidationError):
        po_service.get_annual_report_data(app_config, "25", ADMIN)
    with pytest.raises(ValidationError):
        po_service.get_annual_report_data(app_config, "202A", ADMIN)
    with pytest.raises(PermissionDenied):
        po_service.get_annual_report_data(app_config, "2025", REQUESTER)
```

- [ ] **Step 2: Run PO annual report tests to verify failure**

Run:

```bash
python -m pytest tests/test_po_annual_report.py -v
```

Expected: FAIL because `sc_gr_app.services.po_service` has no `get_annual_report_data` attribute.

- [ ] **Step 3: Add PO annual report implementation**

Append this implementation to `sc_gr_app/services/po_service.py`:

```python
def _validate_annual_report_year(year: str) -> tuple[str, str]:
    import re

    if not isinstance(year, str) or not re.fullmatch(r"\d{4}", year):
        raise ValidationError("year must be a 4-digit string")
    previous_year = str(int(year) - 1)
    return year, previous_year


def _annual_gr_year_expr() -> str:
    return (
        "case "
        "when status = 'finished' then substr(finished_at, 1, 4) "
        "when status = 'approved' then substr(approved_date, 1, 4) "
        "else null end"
    )


def get_annual_report_data(config: AppConfig, year: str, current_user: dict) -> list[dict]:
    """Return annual report rows for PO List export.

    Rows include qualifying PO rows plus SC-only rows for approved SCs with no
    qualifying PO row. Export-only formula columns are intentionally blank.
    """
    require_admin(current_user)
    selected_year, previous_year = _validate_annual_report_year(year)
    year_expr = _annual_gr_year_expr()

    with connect(config) as conn:
        po_rows = conn.execute(
            f"""
            with gr_totals as (
              select
                po_id,
                sum(case when report_year = ? then coalesce(con_value, 0) else 0 end) as previous_year_gr,
                sum(case when report_year = ? then coalesce(con_value, 0) else 0 end) as selected_year_gr,
                sum(case when report_year = ? then 1 else 0 end) as selected_year_count
              from (
                select po_id, con_value, {year_expr} as report_year
                from gr_requests
                where status in ('approved', 'finished')
              )
              where report_year is not null
              group by po_id
            )
            select
              'po' as row_type,
              po.sc_id as _sc_id,
              coalesce(u.user_name, po.requester_id, '') as requester,
              coalesce(sc.sc_no, '') as sc_no,
              coalesce(po.po_no, '') as po_no,
              coalesce(sc.description, '') as short_text,
              sc.sc_amount as sc_amount,
              po.po_amount as po_amount,
              coalesce(gr.previous_year_gr, 0) as previous_year_gr,
              '' as previous_year_provision,
              coalesce(gr.selected_year_gr, 0) as selected_year_gr,
              '' as selected_year_to_be_gr,
              '' as selected_year_fc_gr,
              '' as remark
            from pos po
            left join sc_records sc on sc.sc_id = po.sc_id
            left join users u on u.user_id = po.requester_id
            left join gr_totals gr on gr.po_id = po.po_id
            where
              (sc.status = 'approved' and po.status in ('active', 'finished'))
              or coalesce(gr.selected_year_count, 0) > 0
              or po.status = 'active'
              or (po.status = 'finished' and substr(po.finished_at, 1, 4) = ?)
            order by coalesce(sc.sc_no, ''), coalesce(po.po_no, ''), po.po_id
            """,
            (previous_year, selected_year, selected_year, selected_year),
        ).fetchall()

        qualifying_sc_ids = {
            row["_sc_id"] for row in po_rows if row["_sc_id"] not in (None, "")
        }

        sc_rows = conn.execute(
            """
            select
              'sc' as row_type,
              sc.sc_id as _sc_id,
              coalesce(u.user_name, sc.requester_id, '') as requester,
              coalesce(sc.sc_no, '') as sc_no,
              '' as po_no,
              coalesce(sc.description, '') as short_text,
              sc.sc_amount as sc_amount,
              '' as po_amount,
              '' as previous_year_gr,
              '' as previous_year_provision,
              '' as selected_year_gr,
              '' as selected_year_to_be_gr,
              '' as selected_year_fc_gr,
              '' as remark
            from sc_records sc
            left join users u on u.user_id = sc.requester_id
            where sc.status = 'approved'
            order by coalesce(sc.sc_no, ''), sc.sc_id
            """
        ).fetchall()

    result: list[dict] = []
    for row in po_rows:
        item = dict(row)
        item.pop("_sc_id", None)
        result.append(item)

    for row in sc_rows:
        item = dict(row)
        sc_id = item.pop("_sc_id", None)
        if sc_id not in qualifying_sc_ids:
            result.append(item)

    return result
```

- [ ] **Step 4: Run PO annual report tests to verify pass**

Run:

```bash
python -m pytest tests/test_po_annual_report.py -v
```

Expected: PASS all 3 tests.

- [ ] **Step 5: Commit PO annual report service**

```bash
git add tests/test_po_annual_report.py sc_gr_app/services/po_service.py
git commit -m "feat: add PO annual report data service"
```

## Task 2: Backend GR Annual Report Repair

**Files:**
- Modify: `tests/test_gr_annual_report.py`
- Modify: `sc_gr_app/services/gr_service.py`

- [ ] **Step 1: Add failing GR admin permission test**

Append to `tests/test_gr_annual_report.py`:

```python
def test_get_annual_report_requires_admin(app_config, sample_data):
    with pytest.raises(PermissionDenied):
        get_annual_report_data(
            app_config,
            "2026",
            {"role": "requester", "user_id": "u1", "machine_id": "M000001"},
        )
```

Also update the imports at the top of `tests/test_gr_annual_report.py`:

```python
from sc_gr_app.errors import PermissionDenied, ValidationError
```

- [ ] **Step 2: Run GR annual report tests to verify failure**

Run:

```bash
python -m pytest tests/test_gr_annual_report.py -v
```

Expected: FAIL because `get_annual_report_data` is missing from `gr_service.py`.

- [ ] **Step 3: Add GR annual report implementation**

Append to `sc_gr_app/services/gr_service.py`:

```python
def _validate_annual_report_year(year: str) -> str:
    import re

    if not isinstance(year, str) or not re.fullmatch(r"\d{4}", year):
        raise ValidationError("year must be a 4-digit string")
    return year


def get_annual_report_data(config: AppConfig, year: str, current_user: dict) -> list[dict]:
    """Return approved/finished GR rows in the selected report year."""
    require_admin(current_user)
    year = _validate_annual_report_year(year)

    with connect(config) as conn:
        rows = conn.execute(
            """
            select
              gr.*,
              po.po_no,
              po.sc_id,
              sc.sc_no,
              sc.cost_center,
              vendor.vendor_name,
              u.user_name as requester_name
            from gr_requests gr
            join pos po on po.po_id = gr.po_id
            left join sc_records sc on sc.sc_id = po.sc_id
            join vendors vendor on vendor.vendor_id = po.vendor_id
            left join users u on u.user_id = gr.requester_id
            where gr.status in ('approved', 'finished')
              and (
                (gr.status = 'finished' and substr(gr.finished_at, 1, 4) = ?)
                or
                (gr.status = 'approved' and substr(gr.approved_date, 1, 4) = ?)
              )
            order by coalesce(gr.finished_at, gr.approved_date, gr.created_at) desc,
                     gr.gr_no
            """,
            (year, year),
        ).fetchall()

    return [_row_to_dict(row) for row in rows]
```

- [ ] **Step 4: Run GR annual report tests to verify pass**

Run:

```bash
python -m pytest tests/test_gr_annual_report.py -v
```

Expected: PASS all tests in `tests/test_gr_annual_report.py`.

- [ ] **Step 5: Commit GR annual report repair**

```bash
git add tests/test_gr_annual_report.py sc_gr_app/services/gr_service.py
git commit -m "fix: restore GR annual report backend data"
```

## Task 3: Bridge Annual Report APIs

**Files:**
- Modify: `tests/test_api_bridge.py`
- Modify: `sc_gr_app/api/bridge.py`

- [ ] **Step 1: Add failing bridge forwarding tests**

Append to `tests/test_api_bridge.py`:

```python
def test_bridge_annual_report_methods_forward_current_user_and_year(monkeypatch, app_config):
    from sc_gr_app.api import bridge

    current_user = {"user_id": "U_ADMIN", "role": "admin", "machine_id": "1234567"}
    calls = []

    monkeypatch.setattr(bridge, "get_7_digit_id", lambda: "1234567")
    monkeypatch.setattr(
        bridge,
        "get_user_by_machine_id",
        lambda config, machine_id: current_user,
    )

    def fake_po_report(config, year, user):
        calls.append(("po", config, year, user))
        return [{"row_type": "po", "po_no": "PO-1"}]

    def fake_gr_report(config, year, user):
        calls.append(("gr", config, year, user))
        return [{"gr_no": "GR-1"}]

    monkeypatch.setattr(bridge.po_service, "get_annual_report_data", fake_po_report)
    monkeypatch.setattr(bridge.gr_service, "get_annual_report_data", fake_gr_report)

    api = bridge.ApiBridge(app_config)

    assert api.get_po_annual_report({"year": "2025"}) == {
        "ok": True,
        "data": {"rows": [{"row_type": "po", "po_no": "PO-1"}]},
    }
    assert api.get_gr_annual_report({"year": "2026"}) == {
        "ok": True,
        "data": {"rows": [{"gr_no": "GR-1"}]},
    }
    assert calls == [
        ("po", app_config, "2025", current_user),
        ("gr", app_config, "2026", current_user),
    ]
```

- [ ] **Step 2: Run bridge test to verify failure**

Run:

```bash
python -m pytest tests/test_api_bridge.py::test_bridge_annual_report_methods_forward_current_user_and_year -v
```

Expected: FAIL because `ApiBridge` has no `get_po_annual_report` and `get_gr_annual_report`.

- [ ] **Step 3: Add bridge methods**

In `sc_gr_app/api/bridge.py`, add these methods after `export_grs_with_stats` and before `save_file`:

```python
    def get_po_annual_report(self, payload=None) -> dict:
        try:
            from datetime import datetime

            payload = self._payload(payload)
            current_user = self._require_current_user()
            year = payload.get("year") or str(datetime.now().year)
            rows = po_service.get_annual_report_data(self.config, year, current_user)
            return ok({"rows": _format_list_timestamps(rows)})
        except Exception as exc:
            return fail(exc)

    def get_gr_annual_report(self, payload=None) -> dict:
        try:
            from datetime import datetime

            payload = self._payload(payload)
            current_user = self._require_current_user()
            year = payload.get("year") or str(datetime.now().year)
            rows = gr_service.get_annual_report_data(self.config, year, current_user)
            return ok({"rows": _format_list_timestamps(rows)})
        except Exception as exc:
            return fail(exc)
```

- [ ] **Step 4: Run bridge test to verify pass**

Run:

```bash
python -m pytest tests/test_api_bridge.py::test_bridge_annual_report_methods_forward_current_user_and_year -v
```

Expected: PASS.

- [ ] **Step 5: Run backend annual report tests together**

Run:

```bash
python -m pytest tests/test_po_annual_report.py tests/test_gr_annual_report.py tests/test_api_bridge.py::test_bridge_annual_report_methods_forward_current_user_and_year -v
```

Expected: PASS.

- [ ] **Step 6: Commit bridge APIs**

```bash
git add tests/test_api_bridge.py sc_gr_app/api/bridge.py
git commit -m "feat: expose annual report bridge APIs"
```

## Task 4: Export Helper Save Result and Empty Headers

**Files:**
- Modify: `frontend/src/composables/useExport.js`

- [ ] **Step 1: Update `exportRows` to preserve headers and return save result**

In `frontend/src/composables/useExport.js`, replace `exportRows` with:

```javascript
  async function exportRows(rows, columns, filename) {
    let ws
    if (!rows.length) {
      ws = XLSX.utils.aoa_to_sheet([columns.map(c => c.label)])
    } else {
      const sheetData = rows.map(row => {
        const obj = {}
        columns.forEach(col => {
          const raw = col.getValue ? col.getValue(row) : (row[col.key] ?? '')
          obj[col.label] = raw
        })
        return obj
      })
      ws = XLSX.utils.json_to_sheet(sheetData)
    }
    ws['!cols'] = columns.map(c => ({ wch: Math.max(c.label.length, 12) }))

    const wb = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(wb, ws, 'Sheet1')

    const wbArray = XLSX.write(wb, { type: 'array', bookType: 'xlsx' })
    const binary = _uint8ToString(new Uint8Array(wbArray))
    const b64 = btoa(binary)
    return await callApi('save_file', { filename: `${filename}.xlsx`, data: b64 })
  }
```

- [ ] **Step 2: Update `exportMultiSheet`, `exportCSV`, `exportAll`, and `exportAllCSV` return values**

In `exportMultiSheet`, replace the sheet-building loop body with:

```javascript
      let ws
      if (!sheet.rows.length) {
        ws = XLSX.utils.aoa_to_sheet([sheet.columns.map(c => c.label)])
      } else {
        const sheetData = sheet.rows.map(row => {
          const obj = {}
          sheet.columns.forEach(col => {
            const raw = col.getValue ? col.getValue(row) : (row[col.key] ?? '')
            obj[col.label] = raw
          })
          return obj
        })
        ws = XLSX.utils.json_to_sheet(sheetData)
      }

      ws['!cols'] = sheet.columns.map(c => ({ wch: Math.max(c.label.length, 12) }))
      XLSX.utils.book_append_sheet(wb, ws, sheet.name)
```

At the end of `exportMultiSheet`, replace:

```javascript
    await callApi('save_file', { filename: `${filename}.xlsx`, data: b64 })
```

with:

```javascript
    return await callApi('save_file', { filename: `${filename}.xlsx`, data: b64 })
```

In `exportCSV`, replace:

```javascript
    await callApi('save_file', { filename: `${filename}.csv`, data: b64 })
```

with:

```javascript
    return await callApi('save_file', { filename: `${filename}.csv`, data: b64 })
```

In `exportAll`, replace:

```javascript
    await exportRows(allRows, columns, filename)
```

with:

```javascript
    return await exportRows(allRows, columns, filename)
```

In `exportAllCSV`, replace:

```javascript
    await exportCSV(allRows, columns, filename)
```

with:

```javascript
    return await exportCSV(allRows, columns, filename)
```

- [ ] **Step 3: Build frontend to verify helper syntax**

Run:

```bash
cd frontend
npm run build
```

Expected: build completes with exit code 0.

- [ ] **Step 4: Commit export helper changes**

```bash
git add frontend/src/composables/useExport.js
git commit -m "fix: preserve export headers and cancellation result"
```

## Task 5: Frontend PO and GR Annual Report UI

**Files:**
- Modify: `frontend/src/views/PoListView.vue`
- Modify: `frontend/src/views/GrListView.vue`
- Modify: `frontend/src/i18n/locales/zh-CN.js`
- Modify: `frontend/src/i18n/locales/en-US.js`

- [ ] **Step 1: Add PO i18n keys**

In `frontend/src/i18n/locales/zh-CN.js`, inside the `po:` block after `importRules`, add:

```javascript
    annualReport: '年报导出',
    annualReportTitle: '导出年报',
    selectYear: '选择年份',
```

In `frontend/src/i18n/locales/en-US.js`, inside the `po:` block after `importRules`, add:

```javascript
    annualReport: 'Annual Report',
    annualReportTitle: 'Export Annual Report',
    selectYear: 'Select Year',
```

- [ ] **Step 2: Add PO annual report button and dialog**

In `frontend/src/views/PoListView.vue`, add `computed` to the Vue import:

```javascript
import { computed, ref, onMounted } from 'vue'
```

After `const { t } = useI18n()`, add:

```javascript
const isAdmin = computed(() => window.__currentUser?.role === 'admin')
```

Change the `useExport` destructuring to:

```javascript
const { exportRows } = useExport()
```

After `const exportDialogVisible = ref(false)`, add:

```javascript
const annualReportVisible = ref(false)
const annualReportYear = ref(new Date().getFullYear().toString())
const annualExporting = ref(false)
```

In the toolbar, after the existing common export button, add:

```vue
      <el-button v-if="isAdmin" @click="openAnnualReportDialog">
        <el-icon><Download /></el-icon> {{ $t('po.annualReport') }}
      </el-button>
```

Before the closing root `</div>` in the template, after `ExportDialog`, add:

```vue
    <el-dialog
      v-model="annualReportVisible"
      :title="$t('po.annualReportTitle')"
      width="360px"
    >
      <el-form label-position="top">
        <el-form-item :label="$t('po.selectYear')">
          <el-date-picker
            v-model="annualReportYear"
            type="year"
            placeholder="YYYY"
            format="YYYY"
            value-format="YYYY"
            style="width:100%"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="annualReportVisible = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="annualExporting" @click="handleAnnualExport">
          {{ $t('common.export') }}
        </el-button>
      </template>
    </el-dialog>
```

- [ ] **Step 3: Add PO annual report handler**

In `frontend/src/views/PoListView.vue`, after `handleExport`, add:

```javascript
function openAnnualReportDialog() {
  annualReportYear.value = new Date().getFullYear().toString()
  annualReportVisible.value = true
}

async function handleAnnualExport() {
  annualExporting.value = true
  try {
    const year = annualReportYear.value
    const previousYear = String(Number(year) - 1)
    const result = await callApi('get_po_annual_report', { year })
    const rows = result.rows || []
    const columns = [
      { key: 'requester', label: 'Requester' },
      { key: 'sc_no', label: 'SC no' },
      { key: 'po_no', label: 'PO number' },
      { key: 'short_text', label: 'Short Text' },
      { key: 'sc_amount', label: 'SC amount' },
      { key: 'po_amount', label: 'PO amount' },
      { key: 'previous_year_gr', label: `${previousYear} GR` },
      { key: 'previous_year_provision', label: `${previousYear} Provision` },
      { key: 'selected_year_gr', label: `${year} GR` },
      { key: 'selected_year_to_be_gr', label: `${year} to be GR` },
      { key: 'selected_year_fc_gr', label: `${year} FC GR` },
      { key: 'remark', label: 'Remark' },
    ]
    const saveResult = await exportRows(rows, columns, `PO_Annual_Report_${year}`)
    if (saveResult?.cancelled) return
    ElMessage.success(t('msg.exportedSuccessfully'))
    annualReportVisible.value = false
  } catch (e) {
    ElMessage.error(e.message || t('msg.exportFailed'))
  } finally {
    annualExporting.value = false
  }
}
```

- [ ] **Step 4: Gate GR annual button to admins and handle cancellation**

In `frontend/src/views/GrListView.vue`, change the annual report button to:

```vue
      <el-button v-if="isAdmin" @click="openAnnualReportDialog">
        <el-icon><Download /></el-icon> {{ $t('gr.annualReport') }}
      </el-button>
```

In `handleAnnualExport`, replace:

```javascript
    await exportRows(rows, allColumns, `GR_Annual_Report_${annualReportYear.value}`)
    ElMessage.success(t('msg.exportedSuccessfully'))
    annualReportVisible.value = false
```

with:

```javascript
    const saveResult = await exportRows(rows, allColumns, `GR_Annual_Report_${annualReportYear.value}`)
    if (saveResult?.cancelled) return
    ElMessage.success(t('msg.exportedSuccessfully'))
    annualReportVisible.value = false
```

- [ ] **Step 5: Build frontend**

Run:

```bash
cd frontend
npm run build
```

Expected: build completes with exit code 0.

- [ ] **Step 6: Commit frontend annual report UI**

```bash
git add frontend/src/views/PoListView.vue frontend/src/views/GrListView.vue frontend/src/i18n/locales/zh-CN.js frontend/src/i18n/locales/en-US.js
git commit -m "feat: add admin annual report export UI"
```

## Task 6: Final Verification

**Files:**
- No source edits expected unless verification exposes a defect.

- [ ] **Step 1: Run focused backend tests**

```bash
python -m pytest tests/test_po_annual_report.py tests/test_gr_annual_report.py tests/test_api_bridge.py::test_bridge_annual_report_methods_forward_current_user_and_year -v
```

Expected: all selected tests PASS.

- [ ] **Step 2: Run export service regression tests**

```bash
python -m pytest tests/test_export_service.py tests/test_budget_service.py -v
```

Expected: PASS. If failures appear, inspect whether the annual report changes modified shared budget/export behavior; they should not.

- [ ] **Step 3: Run frontend production build**

```bash
cd frontend
npm run build
```

Expected: build completes with exit code 0.

- [ ] **Step 4: Run full pytest suite when focused checks pass**

```bash
python -m pytest -q
```

Expected: all tests PASS.

- [ ] **Step 5: Inspect git diff for unintended side effects**

```bash
git diff --stat HEAD
git diff -- sc_gr_app/notification sc_gr_app/services/notification_service.py sc_gr_app/services/record_service.py
```

Expected: annual report implementation does not modify notification modules or record-service code.

- [ ] **Step 6: Final commit if verification fixes were needed**

If Step 1-5 required small corrections, commit them:

```bash
git add <changed-files>
git commit -m "fix: polish annual report export verification issues"
```

If no corrections were needed, do not create an empty commit.
