# GR Annual Report Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an "Export Annual Report" button to the GR List view that exports current-year Approved/Finished GRs as an Excel file following the EGV_2025 template format.

**Architecture:** New backend endpoint `get_gr_annual_report` queries GRs with JOINs through PO/SC/Vendor/User, filtered by year and status. Frontend builds Excel using the existing `useExport.js` composable and saves via `save_file`. A lightweight year-picker dialog is added to GrListView.vue.

**Tech Stack:** Python (sqlite3), Vue 3 + Element Plus, xlsx (SheetJS), i18n (vue-i18n)

---

### Task 1: Backend — Query function in gr_service.py

**Files:**
- Modify: `sc_gr_app/services/gr_service.py` (append at end)

- [ ] **Step 1: Add `get_annual_report_data` function to gr_service.py**

```python
def get_annual_report_data(config: AppConfig, year: str, current_user: dict) -> list[dict]:
    """Return GRs with status approved/finished in the given year, enriched with
    po_no, sc_no, cost_center, vendor_name, requester_name."""
    import re
    if not re.match(r'^\d{4}$', year):
        raise ValidationError("year must be a 4-digit string")

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
            join sc_records sc on sc.sc_id = po.sc_id
            join vendors vendor on vendor.vendor_id = po.vendor_id
            left join users u on u.user_id = gr.requester_id
            where gr.status in ('approved', 'finished')
              and (
                (gr.status = 'finished' and strftime('%Y', gr.finished_at) = ?)
                or
                (gr.status = 'approved' and strftime('%Y', gr.approved_date) = ?)
              )
            order by gr.finished_at desc, gr.approved_date desc
            """,
            (year, year),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]
```

- [ ] **Step 2: Commit**

```bash
git add sc_gr_app/services/gr_service.py
git commit -m "feat: add get_annual_report_data query for GR annual report export"
```

---

### Task 2: Backend — New API endpoint in bridge.py

**Files:**
- Modify: `sc_gr_app/api/bridge.py` (append new method in the Bridge class)

- [ ] **Step 1: Add `get_gr_annual_report` method to the Bridge class**

Find the `export_grs_with_stats` method (around line 887) in `sc_gr_app/api/bridge.py`. Add this new method right after it (before `save_file`):

```python
    def get_gr_annual_report(self, payload=None) -> dict:
        try:
            payload = self._payload(payload)
            current_user = self._require_current_user()
            year = payload.get("year", "")
            if not year:
                from datetime import datetime
                year = str(datetime.now().year)
            rows = gr_service.get_annual_report_data(self.config, year, current_user)
            return ok({"rows": _format_list_timestamps(rows)})
        except Exception as exc:
            return fail(exc)
```

- [ ] **Step 2: Commit**

```bash
git add sc_gr_app/api/bridge.py
git commit -m "feat: add get_gr_annual_report API endpoint"
```

---

### Task 3: Frontend — i18n keys

**Files:**
- Modify: `frontend/src/i18n/locales/zh-CN.js`
- Modify: `frontend/src/i18n/locales/en-US.js`

- [ ] **Step 1: Add Chinese i18n keys**

In `frontend/src/i18n/locales/zh-CN.js`, inside the `gr:` block (around line 345), add after line 422 (the `importRules` line):

```javascript
    annualReport: '年报导出',
    annualReportTitle: '导出年报',
    selectYear: '选择年份',
    exportingAnnual: '正在导出...',
```

- [ ] **Step 2: Add English i18n keys**

In `frontend/src/i18n/locales/en-US.js`, find the corresponding `gr:` block. Add after the English `importRules` line:

```javascript
    annualReport: 'Annual Report',
    annualReportTitle: 'Export Annual Report',
    selectYear: 'Select Year',
    exportingAnnual: 'Exporting...',
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/i18n/locales/zh-CN.js frontend/src/i18n/locales/en-US.js
git commit -m "feat: add i18n keys for GR annual report export"
```

---

### Task 4: Frontend — UI in GrListView.vue

**Files:**
- Modify: `frontend/src/views/GrListView.vue`

- [ ] **Step 1: Add "年报导出" button**

In `frontend/src/views/GrListView.vue`, in the template section (around line 19), add a new button after the existing Export button:

```html
      <el-button @click="openAnnualReportDialog">
        <el-icon><Download /></el-icon> {{ $t('gr.annualReport') }}
      </el-button>
```

- [ ] **Step 2: Add year picker dialog**

In the template, add the dialog just before the closing `</div>` of the root element (before `</template>`, around line 176):

```html
    <!-- Annual Report Export Dialog -->
    <el-dialog
      v-model="annualReportVisible"
      :title="$t('gr.annualReportTitle')"
      width="360px"
    >
      <el-form label-position="top">
        <el-form-item :label="$t('gr.selectYear')">
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

- [ ] **Step 3: Add script state and logic**

In the `<script setup>` section, add the state variables after the existing `exporting` / `exportDialogVisible` declarations (around line 203):

```javascript
const annualReportVisible = ref(false)
const annualReportYear = ref(new Date().getFullYear().toString())
const annualExporting = ref(false)
```

Add the handler functions after the existing `handleExport` function (around line 419):

```javascript
function openAnnualReportDialog() {
  annualReportYear.value = new Date().getFullYear().toString()
  annualReportVisible.value = true
}

async function handleAnnualExport() {
  annualExporting.value = true
  try {
    const result = await callApi('get_gr_annual_report', { year: annualReportYear.value })
    const rows = result.rows || []

    // Build column definitions matching the spec
    const templateColumns = [
      { key: 'cost_center', label: 'cost center' },
      { key: 'status', label: 'Status', getValue: (row) => row.status === 'finished' ? 'Finished' : 'Approved' },
      { key: 'po_no', label: 'PO number' },
      { key: 'confirmation_name', label: 'Confirmation number' },
      { key: 'gr_no', label: 'GR NO' },
      { key: 'con_value', label: 'GR Value' },
      { key: 'goods_service_description', label: 'GR Description' },
      { key: 'requester_name', label: 'GR Requester' },
      { key: 'finished_at', label: 'Finished Date', getValue: (row) => (row.finished_at || '').slice(0, 10) },
      { key: '__provision', label: 'provision', getValue: () => '' },
      { key: '__provision_net', label: 'Provision amount NET', getValue: () => '' },
    ]

    // Collect remaining GR field names, excluding those already in templateColumns
    // and internal/sensitive fields
    const usedKeys = new Set([
      'cost_center', 'status', 'po_no', 'confirmation_name', 'gr_no',
      'con_value', 'goods_service_description', 'requester_name', 'finished_at',
      'sc_id', '_type',
    ])
    let remainingKeys = []
    if (rows.length > 0) {
      remainingKeys = Object.keys(rows[0]).filter(k => !usedKeys.has(k) && !k.startsWith('_'))
    }

    const allColumns = [
      ...templateColumns,
      ...remainingKeys.map(k => ({ key: k, label: k })),
    ]

    const { exportRows } = useExport()
    await exportRows(rows, allColumns, `GR_Annual_Report_${annualReportYear.value}`)
    ElMessage.success(t('msg.exportedSuccessfully'))
    annualReportVisible.value = false
  } catch (e) {
    ElMessage.error(e.message || t('msg.exportFailed'))
  } finally {
    annualExporting.value = false
  }
}
```

- [ ] **Step 4: Verify no missing imports**

Check that `useExport` is already imported (line 186 of the current file confirms `import { useExport } from '@/composables/useExport.js'`). The `ElMessage` import is also already present (line 195).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/GrListView.vue
git commit -m "feat: add annual report export button and dialog to GR List view"
```

---

### Task 5: Test — Backend unit test

**Files:**
- Create: `tests/test_gr_annual_report.py`

- [ ] **Step 1: Write the test file**

Create `tests/test_gr_annual_report.py`:

```python
import pytest
from datetime import datetime, timezone
from sc_gr_app.services.gr_service import get_annual_report_data
from sc_gr_app.errors import ValidationError


def test_get_annual_report_filters_by_year_and_status(app_config, sample_data):
    """Only approved/finished GRs in the given year should be returned."""
    rows = get_annual_report_data(app_config, "2026", {"role": "admin", "user_id": "u1", "machine_id": "M000001"})
    for r in rows:
        assert r["status"] in ("approved", "finished")
        if r["status"] == "finished":
            assert r["finished_at"].startswith("2026")
        elif r["status"] == "approved":
            assert r["approved_date"].startswith("2026")


def test_get_annual_report_excludes_other_years(app_config, sample_data):
    """GRs from other years should not appear."""
    rows = get_annual_report_data(app_config, "2020", {"role": "admin", "user_id": "u1", "machine_id": "M000001"})
    assert len(rows) == 0


def test_get_annual_report_excludes_draft_pending(app_config, sample_data):
    """Draft/pending/denied GRs should be excluded regardless of year."""
    rows = get_annual_report_data(app_config, "2026", {"role": "admin", "user_id": "u1", "machine_id": "M000001"})
    statuses = {r["status"] for r in rows}
    assert "draft" not in statuses
    assert "pending" not in statuses
    assert "denied" not in statuses


def test_get_annual_report_enriches_joins(app_config, sample_data):
    """Returned rows should include joined fields from PO, SC, vendor, users."""
    rows = get_annual_report_data(app_config, "2026", {"role": "admin", "user_id": "u1", "machine_id": "M000001"})
    if rows:
        r = rows[0]
        assert "po_no" in r
        assert "sc_no" in r
        assert "cost_center" in r
        assert "vendor_name" in r
        assert "requester_name" in r


def test_get_annual_report_rejects_invalid_year(app_config):
    """Non-4-digit year should raise ValidationError."""
    with pytest.raises(ValidationError):
        get_annual_report_data(app_config, "abc", {"role": "admin", "user_id": "u1", "machine_id": "M000001"})
    with pytest.raises(ValidationError):
        get_annual_report_data(app_config, "202", {"role": "admin", "user_id": "u1", "machine_id": "M000001"})
```

- [ ] **Step 2: Add conftest fixture for sample_data**

Check if `tests/conftest.py` exists and has appropriate fixtures. If not, the test needs a fixture that creates GR records across different years/statuses. Check existing fixtures first:

```bash
grep -n "def sample_data\|def app_config\|@pytest.fixture" tests/conftest.py | head -20
```

- [ ] **Step 3: Add sample_data fixture to conftest.py if needed**

If `sample_data` fixture does not exist, add to `tests/conftest.py`:

```python
@pytest.fixture
def sample_data(app_config):
    """Create sample GRs across years and statuses for annual report testing."""
    from sc_gr_app.db.migrations import migrate
    from sc_gr_app.config import AppConfig
    import sqlite3
    migrate(app_config)
    conn = sqlite3.connect(app_config.db_path)
    conn.executescript("""
        INSERT OR IGNORE INTO users (user_id, machine_id, user_name, role, status, created_at, updated_at)
        VALUES ('u1', 'M000001', 'Test User', 'admin', 'active', '2026-01-01T00:00:00', '2026-01-01T00:00:00');

        INSERT OR IGNORE INTO sc_records (sc_id, sc_no, requester_id, request_type, cost_center, sc_amount, service_period_start, service_period_end, status, description, created_by, created_at, updated_at)
        VALUES ('sc-001', 'SC-2026-001', 'u1', 'service', 60473000, 100000, '2026-01-01', '2026-12-31', 'approved', 'Test SC', 'u1', '2026-01-01T00:00:00', '2026-01-01T00:00:00');

        INSERT OR IGNORE INTO vendors (vendor_id, vendor_name, service_scope, created_by, created_at, updated_at)
        VALUES ('v-001', 'Test Vendor', 'General Service', 'u1', '2026-01-01T00:00:00', '2026-01-01T00:00:00');

        INSERT OR IGNORE INTO pos (po_id, sc_id, vendor_id, po_no, po_amount, status, created_at, updated_at)
        VALUES ('po-001', 'sc-001', 'v-001', 'PO-2026-001', 80000, 'active', '2026-01-01T00:00:00', '2026-01-01T00:00:00');

        -- Finished GR in 2026
        INSERT OR IGNORE INTO gr_requests (gr_id, gr_no, po_id, requester_id, estimated_amount, con_value, status, created_by, created_at, finished_at, approved_date)
        VALUES ('gr-001', 'GR-001', 'po-001', 'u1', 50000, 50000, 'finished', 'u1', '2026-03-01T00:00:00', '2026-06-15T00:00:00', '2026-05-01T00:00:00');

        -- Approved GR in 2026
        INSERT OR IGNORE INTO gr_requests (gr_id, gr_no, po_id, requester_id, estimated_amount, con_value, status, created_by, created_at, approved_date)
        VALUES ('gr-002', 'GR-002', 'po-001', 'u1', 30000, 30000, 'approved', 'u1', '2026-04-01T00:00:00', '2026-07-01T00:00:00');

        -- Pending GR in 2026 (should NOT appear)
        INSERT OR IGNORE INTO gr_requests (gr_id, gr_no, po_id, requester_id, estimated_amount, status, created_by, created_at)
        VALUES ('gr-003', 'GR-003', 'po-001', 'u1', 10000, 'pending', 'u1', '2026-05-01T00:00:00');
    """)
    conn.commit()
    conn.close()
    return True
```

- [ ] **Step 4: Run the tests**

```bash
cd c:/Users/V2SE7PP/Projects/contract && python -m pytest tests/test_gr_annual_report.py -v
```
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_gr_annual_report.py tests/conftest.py
git commit -m "test: add unit tests for GR annual report export query"
```

---

### Task 6: Integration — Manual verification

- [ ] **Step 1: Start the app**

```bash
cd c:/Users/V2SE7PP/Projects/contract && python run.py
```

- [ ] **Step 2: Verify the feature end-to-end**

1. Open the GR List page
2. Click "年报导出" button
3. Verify the year picker dialog appears with current year pre-selected
4. Select a year, click Export
5. Verify the downloaded Excel file has:
   - Correct columns (cost center, Status, PO number, Confirmation number, GR NO, GR Value, GR Description, GR Requester, Finished Date, provision, Provision amount NET, + remaining GR fields)
   - Status values: finished → "Finished", approved → "Approved"
   - provision and Provision amount NET columns are empty
   - Only approved/finished GRs from the selected year

- [ ] **Step 3: Test edge cases**

1. Empty year (no GRs) → should export Excel with headers only
2. Cancel the dialog → no API call, no file save

- [ ] **Step 4: Final commit if any fixes needed**

```bash
git add -A
git commit -m "fix: manual verification fixes for annual report export"
```
