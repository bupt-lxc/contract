# List Search State Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a shared, URL-synchronized search state model for PO, SC, GR, and Vendor list pages, including fuzzy advanced text filters, stable pagination/sorting, and export criteria parity.

**Architecture:** Add a shared frontend `useListSearch` composable and small pure helpers for list query parsing, URL serialization, local date formatting, and deadline conversion. Refactor PO/SC/GR/Vendor composables and list views to use that shared state while preserving existing business methods. Extend backend query/export services so advanced text filters and export rows/statistics use the same normalized criteria, including search text.

**Tech Stack:** Vue 3 composition API, Vue Router 4, Element Plus, Vite, Node test runner for pure frontend helpers, Python 3.11, pytest, SQLite.

---

## File Structure

Create:

- `frontend/src/composables/useListSearch.js`  
  Owns list state, route-query sync, page/sort/filter transitions, backend search calls, and compatibility `search()` behavior.
- `frontend/src/utils/listQuery.js`  
  Pure helpers for URL query parsing/serialization, page/pageSize normalization, sort/direction validation, reserved query filtering, and list-state query objects.
- `frontend/src/utils/date.js`  
  Pure local-date helpers: local `YYYY-MM-DD`, add months/years, and deadline shortcut conversion.
- `tests/web_list_query.test.mjs`  
  Node test coverage for pure list-query helper behavior.
- `tests/web_date_helpers.test.mjs`  
  Node test coverage for local date/deadline behavior.

Modify:

- `frontend/src/components/common/AdvancedFilterBar.vue`  
  Convert to controlled `v-model:text` and `v-model:filters`, keep existing layout and slots.
- `frontend/src/composables/usePo.js`
- `frontend/src/composables/useSc.js`
- `frontend/src/composables/useGr.js`
- `frontend/src/composables/useVendor.js`  
  Rebuild list state around `useListSearch`; preserve existing mutation/detail methods.
- `frontend/src/views/PoListView.vue`
- `frontend/src/views/ScListView.vue`
- `frontend/src/views/GrListView.vue`
- `frontend/src/views/VendorListView.vue`  
  Wire controlled filter bar, route initialization, pagination/sort transitions, reloads, selection clearing, export criteria, and detail `returnTo`.
- `frontend/src/components/po/PoTable.vue`
- `frontend/src/components/sc/ScTable.vue`  
  Ensure server-side sortable columns use `sortable="custom"` and emit sort events.
- `frontend/src/components/export/ExportDialog.vue`  
  Accept `text`, use it in data-scope decisions, pass it to backend export APIs, and omit pagination for all matching rows.
- `frontend/src/composables/useExport.js`  
  Keep `exportAll` available for Vendor export and ensure params include text/filter/sort/direction only.
- `frontend/src/views/LoginView.vue`  
  Guard redirect handling so full list query state survives login redirects safely.
- `sc_gr_app/services/query_service.py`  
  Add escaped, case-insensitive LIKE matching for advanced text filters and update per-entity `like_fields`.
- `sc_gr_app/services/export_service.py`  
  Add `text` to cascade row fetches and statistics; compute export statistics from the same matching root rows.
- `sc_gr_app/api/bridge.py`  
  Thread `text` through SC/PO/GR export bridge methods.
- `tests/test_query_service.py`
- `tests/test_export_service.py`
- `tests/web_auth_state.test.mjs` or a new pure auth helper test if a helper is extracted.

Do not modify Operation Logs or Email Logs search behavior in this plan.

---

### Task 1: Pure URL Query And Date Helpers

**Files:**
- Create: `frontend/src/utils/listQuery.js`
- Create: `frontend/src/utils/date.js`
- Create: `tests/web_list_query.test.mjs`
- Create: `tests/web_date_helpers.test.mjs`

- [ ] **Step 1: Write failing list-query helper tests**

Create `tests/web_list_query.test.mjs`:

```js
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  RESERVED_LIST_QUERY_KEYS,
  buildQueryFromListState,
  parseListQuery,
} from "../frontend/src/utils/listQuery.js";

const config = {
  defaultSort: "created_at",
  defaultDirection: "desc",
  defaultPageSize: 10,
  allowedFilterKeys: new Set(["status", "vendor_name", "po_amount_min"]),
  allowedSortKeys: new Set(["created_at", "vendor_name"]),
};

test("parseListQuery restores valid list state and ignores reserved or unknown keys", () => {
  const state = parseListQuery(
    {
      q: "alpha",
      status: "approved",
      vendor_name: "Acme",
      po_amount_min: "1000",
      unknown: "drop-me",
      redirect: "/login",
      page: "3",
      pageSize: "25",
      sort: "vendor_name",
      direction: "asc",
    },
    config,
  );

  assert.deepEqual(state, {
    text: "alpha",
    filters: { status: "approved", vendor_name: "Acme", po_amount_min: "1000" },
    currentPage: 3,
    pageSize: 25,
    sort: "vendor_name",
    direction: "asc",
  });
});

test("parseListQuery falls back for invalid page pageSize sort and direction", () => {
  const state = parseListQuery(
    { page: "0", pageSize: "nope", sort: "bad", direction: "sideways" },
    config,
  );

  assert.equal(state.currentPage, 1);
  assert.equal(state.pageSize, 10);
  assert.equal(state.sort, "created_at");
  assert.equal(state.direction, "desc");
});

test("buildQueryFromListState omits empty values and includes filters flat", () => {
  const query = buildQueryFromListState({
    text: "alpha",
    filters: { status: "approved", vendor_name: "", po_amount_min: 1000 },
    currentPage: 2,
    pageSize: 10,
    sort: "created_at",
    direction: "desc",
  });

  assert.deepEqual(query, {
    q: "alpha",
    status: "approved",
    po_amount_min: "1000",
    page: "2",
    pageSize: "10",
    sort: "created_at",
    direction: "desc",
  });
});

test("reserved list query keys include deep-link and auth keys", () => {
  assert.equal(RESERVED_LIST_QUERY_KEYS.has("redirect"), true);
  assert.equal(RESERVED_LIST_QUERY_KEYS.has("returnTo"), true);
  assert.equal(RESERVED_LIST_QUERY_KEYS.has("highlight"), true);
  assert.equal(RESERVED_LIST_QUERY_KEYS.has("action"), true);
});
```

- [ ] **Step 2: Write failing local-date helper tests**

Create `tests/web_date_helpers.test.mjs`:

```js
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  addDeadlineShortcut,
  formatLocalDate,
  getDeadlineRange,
} from "../frontend/src/utils/date.js";

test("formatLocalDate uses local date parts instead of UTC ISO slicing", () => {
  const date = new Date(2026, 6, 9, 0, 30, 0);
  assert.equal(formatLocalDate(date), "2026-07-09");
});

test("addDeadlineShortcut supports month and year shortcuts", () => {
  const base = new Date(2026, 0, 31, 12, 0, 0);

  assert.equal(formatLocalDate(addDeadlineShortcut(base, "1m")), "2026-02-28");
  assert.equal(formatLocalDate(addDeadlineShortcut(base, "1y")), "2027-01-31");
});

test("getDeadlineRange returns inclusive local date strings", () => {
  const base = new Date(2026, 6, 9, 8, 0, 0);

  assert.deepEqual(getDeadlineRange("3m", base), {
    deadline_from: "2026-07-09",
    deadline_to: "2026-10-09",
  });
});

test("getDeadlineRange returns empty object for unsupported shortcut", () => {
  assert.deepEqual(getDeadlineRange("bad", new Date(2026, 6, 9)), {});
});
```

- [ ] **Step 3: Run helper tests and verify they fail**

Run:

```powershell
node --test tests\web_list_query.test.mjs tests\web_date_helpers.test.mjs
```

Expected: FAIL because `frontend/src/utils/listQuery.js` and `frontend/src/utils/date.js` do not exist.

- [ ] **Step 4: Implement `listQuery.js`**

Create `frontend/src/utils/listQuery.js`:

```js
export const RESERVED_LIST_QUERY_KEYS = new Set([
  "q",
  "page",
  "pageSize",
  "sort",
  "direction",
  "redirect",
  "returnTo",
  "highlight",
  "action",
]);

function firstValue(value) {
  if (Array.isArray(value)) return value[0];
  return value;
}

function isPresent(value) {
  return value !== undefined && value !== null && value !== "";
}

function normalizePositiveInt(value, fallback) {
  const raw = firstValue(value);
  if (typeof raw === "number" && Number.isInteger(raw) && raw > 0) return raw;
  if (typeof raw === "string" && /^[1-9]\d*$/.test(raw)) return Number(raw);
  return fallback;
}

function normalizeDirection(value, fallback) {
  const raw = String(firstValue(value) || "").toLowerCase();
  return raw === "asc" || raw === "desc" ? raw : fallback;
}

export function parseListQuery(query, config) {
  const filters = {};
  for (const [key, rawValue] of Object.entries(query || {})) {
    if (RESERVED_LIST_QUERY_KEYS.has(key)) continue;
    if (!config.allowedFilterKeys.has(key)) continue;
    const value = firstValue(rawValue);
    if (isPresent(value)) filters[key] = String(value);
  }

  const sortRaw = String(firstValue(query?.sort) || "");
  const direction = normalizeDirection(query?.direction, config.defaultDirection);
  const sort = config.allowedSortKeys.has(sortRaw) ? sortRaw : config.defaultSort;

  return {
    text: isPresent(firstValue(query?.q)) ? String(firstValue(query.q)) : null,
    filters,
    currentPage: normalizePositiveInt(query?.page, 1),
    pageSize: normalizePositiveInt(query?.pageSize, config.defaultPageSize),
    sort,
    direction,
  };
}

export function buildQueryFromListState(state) {
  const query = {};
  if (isPresent(state.text)) query.q = String(state.text);

  for (const [key, value] of Object.entries(state.filters || {})) {
    if (isPresent(value)) query[key] = String(value);
  }

  query.page = String(state.currentPage || 1);
  query.pageSize = String(state.pageSize);
  query.sort = String(state.sort);
  query.direction = String(state.direction);
  return query;
}

export function criteriaFromState(state) {
  return {
    text: state.text || null,
    filters: { ...(state.filters || {}) },
    sort: state.sort,
    direction: state.direction,
  };
}
```

- [ ] **Step 5: Implement `date.js`**

Create `frontend/src/utils/date.js`:

```js
function pad2(value) {
  return String(value).padStart(2, "0");
}

export function formatLocalDate(date = new Date()) {
  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`;
}

function daysInMonth(year, monthIndex) {
  return new Date(year, monthIndex + 1, 0).getDate();
}

export function addDeadlineShortcut(baseDate, shortcut) {
  const match = String(shortcut || "").match(/^(\d+)([ym])$/);
  if (!match) return null;

  const amount = Number(match[1]);
  const unit = match[2];
  const result = new Date(baseDate.getTime());
  const originalDay = result.getDate();

  if (unit === "y") {
    const targetYear = result.getFullYear() + amount;
    const targetMonth = result.getMonth();
    result.setFullYear(targetYear, targetMonth, Math.min(originalDay, daysInMonth(targetYear, targetMonth)));
    return result;
  }

  const targetMonthAbsolute = result.getMonth() + amount;
  const targetYear = result.getFullYear() + Math.floor(targetMonthAbsolute / 12);
  const targetMonth = ((targetMonthAbsolute % 12) + 12) % 12;
  result.setFullYear(targetYear, targetMonth, Math.min(originalDay, daysInMonth(targetYear, targetMonth)));
  return result;
}

export function getDeadlineRange(shortcut, baseDate = new Date()) {
  const end = addDeadlineShortcut(baseDate, shortcut);
  if (!end) return {};
  return {
    deadline_from: formatLocalDate(baseDate),
    deadline_to: formatLocalDate(end),
  };
}
```

- [ ] **Step 6: Run helper tests and verify they pass**

Run:

```powershell
node --test tests\web_list_query.test.mjs tests\web_date_helpers.test.mjs
```

Expected: PASS.

- [ ] **Step 7: Commit helper foundation**

Run:

```powershell
git add frontend/src/utils/listQuery.js frontend/src/utils/date.js tests/web_list_query.test.mjs tests/web_date_helpers.test.mjs
git commit -m "feat(search): add list query helpers"
```

---

### Task 2: Backend Fuzzy Advanced Filters

**Files:**
- Modify: `sc_gr_app/services/query_service.py`
- Modify: `tests/test_query_service.py`

- [ ] **Step 1: Add failing backend fuzzy-filter tests**

Append these tests near the existing query-service filter tests in `tests/test_query_service.py`:

```python
def test_po_advanced_text_filters_are_case_insensitive_contains(app_config):
    seed_query_data(app_config)

    assert search_pos(app_config, filters={"po_no": "alpha"}, current_user=ADMIN)["rows"][0]["po_no"] == "PO-ALPHA"
    assert search_pos(app_config, filters={"vendor_name": "vendor"}, current_user=ADMIN)["rows"][0]["vendor_name"] == "Alpha Vendor"
    assert search_pos(app_config, filters={"cost_center": "10"}, current_user=ADMIN)["rows"][0]["po_no"] == "PO-ALPHA"


def test_sc_advanced_text_filters_are_case_insensitive_contains(app_config):
    sc_id, _po_id, _gr_id, _vendor_id = seed_query_data(app_config)

    assert search_scs(app_config, filters={"sc_no": "alpha"}, current_user=ADMIN)["rows"][0]["sc_id"] == sc_id
    assert search_scs(app_config, filters={"description": "SERVICE"}, current_user=ADMIN)["rows"][0]["sc_id"] == sc_id
    assert search_scs(app_config, filters={"cost_center": "10"}, current_user=ADMIN)["rows"][0]["sc_id"] == sc_id


def test_gr_advanced_text_filters_are_case_insensitive_contains(app_config):
    _sc_id, _po_id, gr_id, _vendor_id = seed_query_data(app_config)

    assert search_grs(app_config, filters={"gr_id": gr_id[-6:]}, current_user=ADMIN)["rows"][0]["gr_id"] == gr_id
    assert search_grs(app_config, filters={"remark": "REMARK"}, current_user=ADMIN)["rows"][0]["gr_id"] == gr_id


def test_vendor_advanced_text_filters_are_case_insensitive_contains(app_config):
    seed_query_data(app_config)

    assert search_vendors(app_config, filters={"vendor_name": "vendor"})["rows"][0]["vendor_name"] == "Alpha Vendor"
    assert search_vendors(app_config, filters={"ksrm_vendor_code": "kv"})["rows"][0]["ksrm_vendor_code"] == "KV-1"


def test_advanced_like_filters_treat_sql_wildcards_as_literals(app_config):
    seed_query_data(app_config)

    assert search_pos(app_config, filters={"po_no": "%"}, current_user=ADMIN)["rows"] == []
    assert search_vendors(app_config, filters={"vendor_name": "_"})["rows"] == []
```

- [ ] **Step 2: Run query tests and verify fuzzy tests fail**

Run:

```powershell
uv run pytest tests\test_query_service.py -k "advanced_text_filters or advanced_like_filters" -q
```

Expected: FAIL because PO/GR advanced text filters are exact and wildcard escaping is not implemented.

- [ ] **Step 3: Implement escaped case-insensitive LIKE helpers**

Modify `sc_gr_app/services/query_service.py` near `_append_text_search`:

```python
def _escape_like(value) -> str:
    text = str(value)
    return (
        text
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


def _contains_param(value) -> str:
    return f"%{_escape_like(value).lower()}%"
```

Then update `_append_text_search` and `_append_filters` LIKE branches to use `lower(...) like ? escape '\\'` and `_contains_param(value)`.

- [ ] **Step 4: Expand per-entity `like_fields`**

Update `like_fields` arguments:

For `search_scs`:

```python
like_fields={
    "sc_id", "sc_no", "requester_id", "requester_name",
    "created_by", "created_by_name", "cost_center",
    "description", "calloff_po_id",
}
```

For `search_vendors`:

```python
like_fields={
    "vendor_id", "vendor_name", "ksrm_vendor_code",
    "company_name_cn", "service_scope", "created_by",
    "contact_person", "email", "phone", "description",
}
```

For `search_pos`, add:

```python
like_fields={
    "po_id", "po_no", "sc_id", "vendor_id", "vendor_name",
    "requester_name", "contract_no", "payment_frequency",
    "contract_pos", "cost_center", "purchaser",
}
```

For `search_grs`, add:

```python
like_fields={
    "gr_id", "gr_no", "po_id", "sc_id", "requester_id",
    "vendor_id", "goods_service_description",
    "confirmation_name", "remark",
}
```

- [ ] **Step 5: Run fuzzy query tests**

Run:

```powershell
uv run pytest tests\test_query_service.py -k "advanced_text_filters or advanced_like_filters" -q
```

Expected: PASS.

- [ ] **Step 6: Run query regression tests**

Run:

```powershell
uv run pytest tests\test_query_service.py tests\test_query_filters.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit backend fuzzy filters**

Run:

```powershell
git add sc_gr_app/services/query_service.py tests/test_query_service.py
git commit -m "feat(search): fuzzy match advanced text filters"
```

---

### Task 3: Backend Export Criteria Parity

**Files:**
- Modify: `sc_gr_app/services/export_service.py`
- Modify: `sc_gr_app/api/bridge.py`
- Modify: `tests/test_export_service.py`

- [ ] **Step 1: Add failing export text/statistics tests**

Append to `tests/test_export_service.py`:

```python
def test_cascade_export_honors_text_search_for_rows(app_config):
    migrate(app_config)
    import sqlite3
    conn = sqlite3.connect(app_config.db_path)
    conn.execute("INSERT INTO users (user_id, machine_id, user_name, role, status, created_at, updated_at) VALUES ('U1', 'M001', 'Alice', 'admin', 'active', '2026-01-01', '2026-01-01')")
    conn.execute("INSERT INTO users (user_id, machine_id, user_name, role, status, created_at, updated_at) VALUES ('U2', 'M002', 'Bob', 'requester', 'active', '2026-01-01', '2026-01-01')")
    conn.execute("INSERT INTO sc_records (sc_id, sc_no, requester_id, request_type, cost_center, sc_amount, currency, service_period_start, service_period_end, status, description, created_by, created_at, updated_at) VALUES ('sc-alpha', 'SC-ALPHA', 'U2', 'new', 1000, 50000, 'CNY', '2026-01-01', '2026-06-30', 'approved', 'Alpha service', 'U2', '2026-01-15', '2026-01-15')")
    conn.execute("INSERT INTO sc_records (sc_id, sc_no, requester_id, request_type, cost_center, sc_amount, currency, service_period_start, service_period_end, status, description, created_by, created_at, updated_at) VALUES ('sc-beta', 'SC-BETA', 'U2', 'new', 2000, 30000, 'CNY', '2026-02-01', '2026-07-31', 'approved', 'Beta service', 'U2', '2026-02-01', '2026-02-01')")
    conn.commit()
    conn.close()

    rows = export_service.build_cascade_rows(
        app_config, "sc", {}, "created_at", "desc",
        cascade_options={"po": False, "gr": False},
        current_user={"user_id": "U1", "machine_id": "M001", "user_name": "Alice", "role": "admin"},
        text="alpha",
    )

    assert [row["sc_no"] for row in rows] == ["SC-ALPHA"]


def test_export_statistics_use_same_text_criteria_as_rows(app_config):
    migrate(app_config)
    import sqlite3
    conn = sqlite3.connect(app_config.db_path)
    conn.execute("INSERT INTO users (user_id, machine_id, user_name, role, status, created_at, updated_at) VALUES ('U1', 'M001', 'Alice', 'admin', 'active', '2026-01-01', '2026-01-01')")
    conn.execute("INSERT INTO users (user_id, machine_id, user_name, role, status, created_at, updated_at) VALUES ('U2', 'M002', 'Bob', 'requester', 'active', '2026-01-01', '2026-01-01')")
    conn.execute("INSERT INTO sc_records (sc_id, sc_no, requester_id, request_type, cost_center, sc_amount, currency, service_period_start, service_period_end, status, description, created_by, created_at, updated_at) VALUES ('sc-alpha', 'SC-ALPHA', 'U2', 'new', 1000, 50000, 'CNY', '2026-01-01', '2026-06-30', 'approved', 'Alpha service', 'U2', '2026-01-15', '2026-01-15')")
    conn.execute("INSERT INTO sc_records (sc_id, sc_no, requester_id, request_type, cost_center, sc_amount, currency, service_period_start, service_period_end, status, description, created_by, created_at, updated_at) VALUES ('sc-beta', 'SC-BETA', 'U2', 'new', 2000, 30000, 'CNY', '2026-02-01', '2026-07-31', 'approved', 'Beta service', 'U2', '2026-02-01', '2026-02-01')")
    conn.commit()
    conn.close()

    stats = export_service.compute_statistics(
        app_config,
        {"SC"},
        {},
        text="alpha",
        sort="created_at",
        direction="desc",
        current_user={"user_id": "U1", "machine_id": "M001", "user_name": "Alice", "role": "admin"},
    )

    assert stats["overview"]["sc"]["total_count"] == 1
    assert stats["overview"]["sc"]["total_amount"] == 50000
```

- [ ] **Step 2: Run export tests and verify they fail**

Run:

```powershell
uv run pytest tests\test_export_service.py -k "text_criteria or text_search" -q
```

Expected: FAIL because export service does not accept `text`.

- [ ] **Step 3: Thread `text` through export row fetching**

Modify `build_cascade_rows`, `_build_sc_cascade`, `_build_po_cascade`, `_build_gr_rows`, and `_fetch_all_search` to accept `text=None`. In `_fetch_all_search`, pass `text=text` into the query service call:

```python
kwargs = {
    "config": config,
    "text": text,
    "filters": filters,
    "sort": sort,
    "direction": direction,
    "limit": limit,
    "offset": offset,
}
```

Keep selected-id behavior taking priority over filters/text.

- [ ] **Step 4: Make statistics use matching root rows**

Modify `compute_statistics` signature:

```python
def compute_statistics(
    config: AppConfig,
    entity_types: set[str],
    filters: dict,
    selected_ids: list[str] | None = None,
    *,
    text: str | None = None,
    sort: str = "created_at",
    direction: str = "desc",
    current_user: dict | None = None,
) -> dict:
```

Inside it, derive root selected IDs when `text` is provided or when filters include fields not supported by `_build_where`:

```python
root_type = "sc" if "SC" in entity_types else ("po" if "PO" in entity_types else "gr")
root_id_col = {"sc": "sc_id", "po": "po_id", "gr": "gr_id"}[root_type]
if selected_ids:
    effective_ids = selected_ids
elif text:
    root_rows = _fetch_all_search(root_type, config, filters, sort, direction, current_user, None, text=text)
    effective_ids = [row[root_id_col] for row in root_rows]
else:
    effective_ids = None
```

Pass `effective_ids` to `_sc_overview`, `_po_overview`, `_gr_overview`, `_financial_summary`, `_processing_time`, `_by_requester`, and `_budget_health`. Preserve existing behavior when no text is provided.

- [ ] **Step 5: Thread text through bridge export methods**

In `sc_gr_app/api/bridge.py`, update `export_scs_cascade`, `export_pos_cascade`, and `export_grs_with_stats`:

```python
text = payload.get("text")
```

Pass `text=text` to `export_service.build_cascade_rows(...)` and `export_service.compute_statistics(...)`.

- [ ] **Step 6: Run export tests**

Run:

```powershell
uv run pytest tests\test_export_service.py -q
```

Expected: PASS.

- [ ] **Step 7: Run query/export regression tests**

Run:

```powershell
uv run pytest tests\test_query_service.py tests\test_query_filters.py tests\test_export_service.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit backend export parity**

Run:

```powershell
git add sc_gr_app/services/export_service.py sc_gr_app/api/bridge.py tests/test_export_service.py
git commit -m "fix(export): honor list text criteria"
```

---

### Task 4: Shared Frontend List Search Composable

**Files:**
- Create: `frontend/src/composables/useListSearch.js`
- Modify: `frontend/src/composables/usePo.js`
- Modify: `frontend/src/composables/useSc.js`
- Modify: `frontend/src/composables/useGr.js`
- Modify: `frontend/src/composables/useVendor.js`

- [ ] **Step 1: Create `useListSearch.js` with the shared API**

Create `frontend/src/composables/useListSearch.js`:

```js
import { reactive, readonly } from 'vue'
import { callApi } from '@/api/bridge.js'
import { buildQueryFromListState, criteriaFromState, parseListQuery } from '@/utils/listQuery.js'

function cloneFilters(filters) {
  return { ...(filters || {}) }
}

export function useListSearch(config) {
  const state = reactive({
    rows: [],
    total: 0,
    loading: false,
    error: null,
    text: null,
    filters: {},
    sort: config.defaultSort,
    direction: config.defaultDirection,
    pageSize: config.defaultPageSize,
    currentPage: 1,
  })

  function assignListState(next) {
    state.text = next.text || null
    state.filters = cloneFilters(next.filters)
    state.sort = next.sort
    state.direction = next.direction
    state.pageSize = next.pageSize
    state.currentPage = next.currentPage
  }

  function syncRoute(router) {
    if (!router) return
    router.replace({ query: buildQueryFromListState(state) })
  }

  function payload(extra = {}) {
    return {
      text: state.text || null,
      filters: cloneFilters(state.filters),
      sort: state.sort,
      direction: state.direction,
      limit: state.pageSize,
      offset: (state.currentPage - 1) * state.pageSize,
      ...extra,
    }
  }

  async function reload(extra = {}) {
    state.loading = true
    state.error = null
    try {
      const result = await callApi(config.apiMethod, payload(extra))
      state.rows = result.rows || result
      state.total = result.total || state.rows.length
    } catch (e) {
      state.error = e.message
      state.rows = []
      state.total = 0
    } finally {
      state.loading = false
    }
  }

  async function initializeFromRoute(route, router) {
    assignListState(parseListQuery(route?.query || {}, config))
    syncRoute(router)
    await reload()
  }

  async function applyFilter({ text, filters }, router) {
    state.text = text || null
    state.filters = cloneFilters(config.transformFilters ? config.transformFilters(filters || {}) : filters)
    state.currentPage = 1
    syncRoute(router)
    await reload()
  }

  async function changePage(page, router) {
    state.currentPage = page
    syncRoute(router)
    await reload()
  }

  async function changePageSize(size, router) {
    state.pageSize = size
    state.currentPage = 1
    syncRoute(router)
    await reload()
  }

  async function changeSort({ prop, order }, router) {
    state.sort = config.allowedSortKeys.has(prop) ? prop : config.defaultSort
    state.direction = order === 'ascending' ? 'asc' : (order === 'descending' ? 'desc' : config.defaultDirection)
    state.currentPage = 1
    syncRoute(router)
    await reload()
  }

  async function reset(router) {
    state.text = null
    state.filters = {}
    state.sort = config.defaultSort
    state.direction = config.defaultDirection
    state.currentPage = 1
    syncRoute(router)
    await reload()
  }

  async function search(text = state.text, filters = state.filters) {
    state.text = text || null
    state.filters = cloneFilters(config.transformFilters ? config.transformFilters(filters || {}) : filters)
    await reload()
  }

  function exportCriteria() {
    return criteriaFromState(state)
  }

  return {
    state: readonly(state),
    initializeFromRoute,
    applyFilter,
    changePage,
    changePageSize,
    changeSort,
    reset,
    reload,
    search,
    exportCriteria,
  }
}
```

- [ ] **Step 2: Refactor `usePo.js`**

Replace list-state implementation with `useListSearch`. Keep existing mutation methods. Configuration:

```js
const list = useListSearch({
  apiMethod: 'search_pos',
  defaultSort: 'created_at',
  defaultDirection: 'desc',
  defaultPageSize: pageSize,
  allowedFilterKeys: new Set([
    'status', 'po_id', 'po_no', 'sc_id', 'vendor_id', 'vendor_name',
    'is_fc_po', 'contract_type', 'cost_center', 'purchaser',
    'po_amount_min', 'po_amount_max',
    'contract_from_from', 'contract_from_to',
    'contract_to_from', 'contract_to_to',
    'active_date_from', 'active_date_to',
    'deadline_from', 'deadline_to',
  ]),
  allowedSortKeys: new Set([
    'po_id', 'po_no', 'sc_no', 'vendor_name', 'requester_name',
    'po_amount', 'status', 'contract_to', 'contract_type',
    'cost_center', 'active_date', 'created_at', 'updated_at',
  ]),
})
```

Return `searchPos: list.search`, `setFilters` as stateful compatibility, `resetFilters: list.reset`, `onSortChange: list.changeSort`, `onPageChange: list.changePage`, `onPageSizeChange: list.changePageSize`, plus new `initializeFromRoute`, `applyFilter`, `changePage`, `changePageSize`, `changeSort`, `reset`, `reload`, and `exportCriteria`.

- [ ] **Step 3: Refactor `useSc.js`**

Use `useListSearch` for list state while preserving `fetchDetail`, `createDraft`, `submitSc`, `updateSc`, `approveSc`, `denySc`, and `finishSc`.

Allowed filters include all SC filter config keys plus generated range keys: `status`, `request_type`, `service_scope`, `is_calloff`, `asset`, `cost_center`, `sc_id`, `sc_no`, `requester_id`, `requester_name`, `created_by`, `created_by_name`, `service_period_start_from`, `service_period_start_to`, `sc_amount_min`, `sc_amount_max`, `pending_date_from`, `pending_date_to`, `approved_date_from`, `approved_date_to`, `deadline_from`, `deadline_to`.

Allowed sorts mirror backend SC allowed sorts.

- [ ] **Step 4: Refactor `useGr.js`**

Use `useListSearch` for list state while preserving GR mutation methods.

Allowed filters include `status`, `gr_id`, `gr_no`, `po_id`, `sc_id`, `requester_id`, `vendor_id`, `estimated_amount_min`, `estimated_amount_max`, `tax_rate`, `con_value_min`, `con_value_max`, `pending_date_from`, `pending_date_to`, `approved_date_from`, `approved_date_to`, `goods_service_description`, `confirmation_name`, `last_delivery`, `is_cancellation`, `deadline_from`, `deadline_to`.

Allowed sorts mirror backend GR allowed sorts.

- [ ] **Step 5: Refactor `useVendor.js`**

Use `useListSearch` with default sort `vendor_name`, direction `asc`, page size `10`, and API `search_vendors`.

Allowed filters: `vendor_name`, `company_name_cn`, `vendor_id`, `ksrm_vendor_code`, `service_scope`, `created_by`, `contact_person`, `email`.

Allowed sorts: `vendor_id`, `vendor_name`, `ksrm_vendor_code`, `company_name_cn`, `service_scope`, `created_at`, `updated_at`.

Keep `createVendor`, `updateVendor`, `disableVendor`, `deleteVendor`, and `checkKsrmDuplicate`. Mutations should call `list.reload()` instead of stateless `searchVendors()`.

- [ ] **Step 6: Run frontend build**

Run:

```powershell
npm.cmd run build
```

from `frontend`.

Expected: PASS. Existing chunk-size warnings are acceptable.

- [ ] **Step 7: Commit shared composable**

Run:

```powershell
git add frontend/src/composables/useListSearch.js frontend/src/composables/usePo.js frontend/src/composables/useSc.js frontend/src/composables/useGr.js frontend/src/composables/useVendor.js
git commit -m "feat(search): share list search state"
```

---

### Task 5: Controlled Filter Bar And List Page Wiring

**Files:**
- Modify: `frontend/src/components/common/AdvancedFilterBar.vue`
- Modify: `frontend/src/views/PoListView.vue`
- Modify: `frontend/src/views/ScListView.vue`
- Modify: `frontend/src/views/GrListView.vue`
- Modify: `frontend/src/views/VendorListView.vue`

- [ ] **Step 1: Convert `AdvancedFilterBar.vue` to controlled props**

Modify script setup:

```js
import { ref, computed, watch } from 'vue'
import { Search } from '@element-plus/icons-vue'

const props = defineProps({
  filterConfig: { type: Array, default: () => [] },
  text: { type: String, default: '' },
  filters: { type: Object, default: () => ({}) },
})

const emit = defineEmits(['update:text', 'update:filters', 'filter', 'reset'])

const searchText = computed({
  get: () => props.text || '',
  set: value => emit('update:text', value),
})

const showAdvanced = ref(false)
let debounceTimer = null

watch(
  () => props.filters,
  value => {
    if (Object.keys(value || {}).length) showAdvanced.value = true
  },
  { immediate: true, deep: true },
)

function updateFilter(key, value) {
  const next = { ...(props.filters || {}) }
  if (value === null || value === '' || value === undefined) delete next[key]
  else next[key] = value
  emit('update:filters', next)
  emit('filter', { text: props.text || null, filters: next })
}

function onSearchDebounced() {
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    emit('filter', { text: props.text || null, filters: props.filters || {} })
  }, 500)
}

function handleReset() {
  clearTimeout(debounceTimer)
  emit('update:text', '')
  emit('update:filters', {})
  emit('reset')
}
```

Update template v-models:

```vue
<el-input
  v-model="searchText"
  ...
/>
```

For advanced controls, replace `v-model="filterValues[...]` with `:model-value="props.filters[...]` and `@update:model-value="value => updateFilter(key, value)"`.

- [ ] **Step 2: Wire PO list to controlled filter and route state**

In `PoListView.vue`:

- Import `useRouter` and use both route/router.
- Destructure new list actions from `usePo`.
- Bind:

```vue
<AdvancedFilterBar
  v-model:text="state.text"
  v-model:filters="state.filters"
  :filter-config="poFilterConfig"
  @filter="handleFilter"
  @reset="handleReset"
/>
```

- Use `applyFilter(payload, router)` in `handleFilter`.
- Use `reset(router)` in `handleReset`.
- Use `changePage(page, router)` and `changePageSize(size, router)`.
- Use `reload()` after save/import/submit/finish.
- Clear `selectedRows.value = []` after filter, reset, page, page-size, sort, and reload-triggering mutations.
- Pass `returnTo: route.fullPath` when navigating to detail.
- Pass `:text="state.text"` to `ExportDialog`.

- [ ] **Step 3: Wire SC list**

In `ScListView.vue`, apply the same patterns:

- Controlled `AdvancedFilterBar`.
- `initializeFromRoute(route, router)` on mount.
- `applyFilter`, `reset`, `changeSort`, `changePage`, `changePageSize`, `reload`.
- Clear selection on list-state transitions.
- Replace import `@imported="searchScs"` with a handler that clears selection and calls `reload()`.
- Detail navigation includes `returnTo`.
- `ExportDialog` gets `text`.

- [ ] **Step 4: Wire GR list**

In `GrListView.vue`:

- Controlled `AdvancedFilterBar`.
- Fix table sorting by changing `@sort-change="onSortChange"` to a local handler that calls `changeSort(..., router)` and clears selection.
- Remove sortable UI from columns not in backend allowed sorts, including `requester_name`, `is_cancellation`, `remark`, and `submitted_date` unless backend sort support is added.
- Keep GR annual report export untouched.
- `ExportDialog` gets `text`.

- [ ] **Step 5: Wire Vendor list with pagination**

In `VendorListView.vue`:

- Controlled `AdvancedFilterBar`.
- Add `@sort-change="handleSortChange"` to table.
- Add pagination below the table, matching PO/SC/GR layout.
- Use `changePage`, `changePageSize`, `changeSort`, `applyFilter`, `reset`, and `initializeFromRoute`.
- Replace export implementation with `exportAll('search_vendors', exportCriteria(), columns, filename)`.
- After create/update/disable/delete/import, call `reload()`.

- [ ] **Step 6: Run frontend build**

Run from `frontend`:

```powershell
npm.cmd run build
```

Expected: PASS.

- [ ] **Step 7: Commit page wiring**

Run:

```powershell
git add frontend/src/components/common/AdvancedFilterBar.vue frontend/src/views/PoListView.vue frontend/src/views/ScListView.vue frontend/src/views/GrListView.vue frontend/src/views/VendorListView.vue
git commit -m "feat(search): wire list pages to shared state"
```

---

### Task 6: Table Sorting And Export Dialog Criteria

**Files:**
- Modify: `frontend/src/components/po/PoTable.vue`
- Modify: `frontend/src/components/sc/ScTable.vue`
- Modify: `frontend/src/components/export/ExportDialog.vue`

- [ ] **Step 1: Update `PoTable.vue` sorting contract**

In `PoTable.vue`:

- Add `@sort-change="$emit('sort-change', $event)"` to `<el-table>`.
- Add `'sort-change'` to `defineEmits`.
- Use `sortable="custom"` only for backend-supported columns.
- Remove `sortable` from derived unsupported columns such as `open_po_amount`, `po_pending_total_incl_tax`, `consumed_amount`, and `finished_at` unless backend sort support has been added.

- [ ] **Step 2: Fix SC table sortable props**

In `ScTable.vue`, keep `sortable="custom"` only on columns supported by `search_scs` backend `allowed_sorts`: `sc_id`, `sc_no`, `requester_id`, `requester_name`, `request_type`, `service_scope`, `cost_center`, `sc_amount`, `status`, `created_at`, `updated_at`, `asset`, `pending_date`, `approved_date`, `confirmed_at`, and `calloff_po_id`.

Remove `sortable="custom"` from current unsupported date columns:

```vue
<el-table-column prop="service_period_start" :label="$t('sc.startDate')" width="120">
<el-table-column prop="service_period_end" :label="$t('sc.endDate')" width="120">
<el-table-column prop="submitted_date" :label="$t('sc.submittedDate')" width="120">
<el-table-column prop="finished_at" :label="$t('timestampLabel.finished')" width="120">
```

Keep existing `@sort-change="$emit('sort-change', $event)"` and `defineEmits(['sort-change', 'detail', 'selection-change'])`.

- [ ] **Step 3: Add text prop to `ExportDialog.vue`**

Modify props:

```js
text: { type: String, default: '' },
```

Modify `initScope` and `hasFilters` so search text counts as filtered:

```js
function hasActiveCriteria() {
  return Boolean(props.text) || Object.keys(props.filters).some(k => props.filters[k] !== '' && props.filters[k] != null)
}
```

Use it in `initScope()` and `hasFilters`.

- [ ] **Step 4: Pass text in export payload**

In `doExport()` payload:

```js
const criteriaFilters = dataScope.value === 'all' ? props.filters : props.filters
const payload = {
  text: dataScope.value === 'selected' ? null : (props.text || null),
  filters: dataScope.value === 'selected' ? {} : criteriaFilters,
  sort: props.sort,
  direction: props.direction,
  cascade: { po: cascadePo.value, gr: cascadeGr.value },
  selected_ids: dataScope.value === 'selected' ? props.selectedIds : undefined,
}
```

For selected export, selected IDs take priority and text/filters are intentionally ignored.

- [ ] **Step 5: Run frontend build**

Run from `frontend`:

```powershell
npm.cmd run build
```

Expected: PASS.

- [ ] **Step 6: Commit table/export frontend updates**

Run:

```powershell
git add frontend/src/components/po/PoTable.vue frontend/src/components/sc/ScTable.vue frontend/src/components/export/ExportDialog.vue
git commit -m "fix(export): pass list text criteria"
```

---

### Task 7: Navigation Compatibility

**Files:**
- Modify: `frontend/src/views/PoListView.vue`
- Modify: `frontend/src/views/ScListView.vue`
- Modify: `frontend/src/views/GrListView.vue`
- Modify: `frontend/src/views/ScDetailView.vue`
- Modify: `frontend/src/views/PoDetailView.vue`
- Modify: `frontend/src/views/GrDetailView.vue`
- Modify: `frontend/src/views/LoginView.vue`
- Create: `tests/web_navigation_state.test.mjs`

- [ ] **Step 1: Add pure redirect helper test**

Create `tests/web_navigation_state.test.mjs`:

```js
import assert from "node:assert/strict";
import { test } from "node:test";

import { sanitizeRedirectTarget } from "../frontend/src/utils/listQuery.js";

test("sanitizeRedirectTarget preserves same-app list query paths", () => {
  assert.equal(
    sanitizeRedirectTarget("/sc?status=pending&page=2&q=abc"),
    "/sc?status=pending&page=2&q=abc",
  );
});

test("sanitizeRedirectTarget rejects external URLs", () => {
  assert.equal(sanitizeRedirectTarget("https://example.com/phish"), "/workbench");
  assert.equal(sanitizeRedirectTarget("//example.com/phish"), "/workbench");
});
```

- [ ] **Step 2: Implement `sanitizeRedirectTarget`**

Add to `frontend/src/utils/listQuery.js`:

```js
export function sanitizeRedirectTarget(value, fallback = "/workbench") {
  if (typeof value !== "string" || !value.startsWith("/") || value.startsWith("//")) {
    return fallback;
  }
  return value;
}
```

- [ ] **Step 3: Use redirect helper in `LoginView.vue`**

Import `sanitizeRedirectTarget` and update `enterApp()`:

```js
const redirect = sanitizeRedirectTarget(router.currentRoute.value.query?.redirect)
router.push(redirect)
```

- [ ] **Step 4: Add `returnTo` to list detail navigation**

In PO/SC/GR list views, update detail route pushes to include:

```js
query: { returnTo: route.fullPath }
```

Use named routes for all three detail pushes:

```js
router.push({ name: 'sc-detail', params: { id: row.sc_id }, query: { returnTo: route.fullPath } })
router.push({ name: 'po-detail', params: { scId: row.sc_id, poId: row.po_id }, query: { returnTo: route.fullPath } })
router.push({ name: 'po-detail-independent', params: { poId: row.po_id }, query: { returnTo: route.fullPath } })
router.push({ name: 'gr-detail', params: { scId: row.sc_id, poId: row.po_id, grId: row.gr_id }, query: { returnTo: route.fullPath } })
```

Use `sc-detail` in `ScListView.vue`, use `po-detail` or `po-detail-independent` in `PoListView.vue` based on whether the row has `sc_id`, and use `gr-detail` in `GrListView.vue`.

- [ ] **Step 5: Use `returnTo` in detail fallback navigation**

In SC/PO/GR detail views, add a helper:

```js
function listReturnPath(fallback) {
  return sanitizeRedirectTarget(route.query.returnTo, fallback)
}
```

Use `listReturnPath` only in flows that currently replace the route after deleting the current detail record:

- `ScDetailView.vue` `handleDelete`: replace `router.replace('/sc')` with `router.replace(listReturnPath('/sc'))`.
- `PoDetailView.vue` `handleDelete`: when `hasSc.value` is true, replace with `router.replace(listReturnPath(\`/sc/${scId.value}\`))`; when false, replace with `router.replace(listReturnPath('/po'))`.
- `GrDetailView.vue` `handleDelete`: replace `router.replace(\`/sc/${scId.value}/po/${poId.value}\`)` with `router.replace(listReturnPath(\`/sc/${scId.value}/po/${poId.value}\`))`.

Do not change finish/recall/approve/deny flows in this task because those flows refresh the current detail page and do not leave the detail route. Direct email/deep links remain supported because `listReturnPath` uses the existing fallback when `returnTo` is absent.

- [ ] **Step 6: Run navigation helper tests**

Run:

```powershell
node --test tests\web_navigation_state.test.mjs
```

Expected: PASS.

- [ ] **Step 7: Run frontend build**

Run from `frontend`:

```powershell
npm.cmd run build
```

Expected: PASS.

- [ ] **Step 8: Commit navigation compatibility**

Run:

```powershell
git add frontend/src/utils/listQuery.js frontend/src/views/LoginView.vue frontend/src/views/PoListView.vue frontend/src/views/ScListView.vue frontend/src/views/GrListView.vue frontend/src/views/ScDetailView.vue frontend/src/views/PoDetailView.vue frontend/src/views/GrDetailView.vue tests/web_navigation_state.test.mjs
git commit -m "feat(search): preserve list navigation state"
```

---

### Task 8: Final Verification And Cleanup

**Files:**
- Review all files touched in Tasks 1-7.

- [ ] **Step 1: Run backend query/export tests**

Run:

```powershell
uv run pytest tests\test_query_service.py tests\test_query_filters.py tests\test_export_service.py -q
```

Expected: PASS.

- [ ] **Step 2: Run frontend helper tests**

Run:

```powershell
node --test tests\web_list_query.test.mjs tests\web_date_helpers.test.mjs tests\web_navigation_state.test.mjs
```

Expected: PASS.

- [ ] **Step 3: Run existing frontend-adjacent Node tests**

Run:

```powershell
node --test tests\web_auth_state.test.mjs tests\web_sc_detail_state.test.mjs tests\web_table_actions.test.mjs
```

Expected: PASS.

- [ ] **Step 4: Run frontend build**

Run from `frontend`:

```powershell
npm.cmd run build
```

Expected: PASS, with existing Vite chunk-size/import warnings allowed.

- [ ] **Step 5: Manual smoke checklist**

Run the app and verify:

- PO list: search text, advanced filter, page change, page size, sort, reset, export.
- SC list: `?status=pending` opens filter panel with status visible; search/filter survives paging and detail return.
- GR list: table sorting triggers backend reload; annual report export still ignores list filters.
- Vendor list: pagination appears; export with a search term exports all matching rows, not only current page.
- Login redirect: unauthenticated `/sc?status=pending&page=2&q=abc` returns to the same URL after login.

- [ ] **Step 6: Commit final verification notes if code changed during cleanup**

When Step 1-5 reveal defects, fix only files touched by this plan. Then run `git status --short`, stage the exact fixed paths shown by status, and commit them:

```powershell
git add frontend/src/utils/listQuery.js frontend/src/utils/date.js frontend/src/composables/useListSearch.js frontend/src/composables/usePo.js frontend/src/composables/useSc.js frontend/src/composables/useGr.js frontend/src/composables/useVendor.js frontend/src/components/common/AdvancedFilterBar.vue frontend/src/components/po/PoTable.vue frontend/src/components/sc/ScTable.vue frontend/src/components/export/ExportDialog.vue frontend/src/views/PoListView.vue frontend/src/views/ScListView.vue frontend/src/views/GrListView.vue frontend/src/views/VendorListView.vue frontend/src/views/LoginView.vue frontend/src/views/ScDetailView.vue frontend/src/views/PoDetailView.vue frontend/src/views/GrDetailView.vue sc_gr_app/services/query_service.py sc_gr_app/services/export_service.py sc_gr_app/api/bridge.py tests/test_query_service.py tests/test_export_service.py tests/web_list_query.test.mjs tests/web_date_helpers.test.mjs tests/web_navigation_state.test.mjs tests/web_auth_state.test.mjs
git commit -m "fix(search): complete list state verification"
```

Remove unchanged paths from the `git add` command before running it. If no files changed, do not create an empty commit.

---

## Self-Review Checklist

- Spec coverage:
  - Shared list state: Tasks 1, 4, 5.
  - URL sync and restore: Tasks 1, 4, 5, 7.
  - Controlled filter bar: Task 5.
  - Fuzzy advanced text filters: Task 2.
  - Vendor pagination/export: Tasks 4, 5, 6.
  - Export rows/statistics parity with text: Tasks 3 and 6.
  - Navigation, email/deep link reserved query keys, auth redirect: Tasks 1 and 7.
  - Logs excluded: File structure and plan scope explicitly say not to modify logs.
  - Tests and verification: Tasks 1-3, 7, 8.
- Red-flag scan: no unresolved drafting markers remain.
- Type consistency:
  - Shared state names: `text`, `filters`, `sort`, `direction`, `currentPage`, `pageSize`, `rows`, `total`, `loading`, `error`.
  - Main API names: `initializeFromRoute`, `applyFilter`, `changePage`, `changePageSize`, `changeSort`, `reset`, `reload`, `search`, `exportCriteria`.
  - URL helpers: `parseListQuery`, `buildQueryFromListState`, `criteriaFromState`, `sanitizeRedirectTarget`.
