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
- `frontend/src/utils/listSearchCore.js`
  Framework-free list search state core used by `useListSearch`; covered by Node tests without Vue or Vite aliases.
- `frontend/src/utils/listQuery.js`
  Pure helpers for URL query parsing/serialization, page/pageSize normalization, sort/direction validation, reserved query filtering, and list-state query objects.
- `frontend/src/utils/date.js`
  Pure local-date helpers: local `YYYY-MM-DD`, add months/years, and deadline shortcut conversion.
- `frontend/src/utils/exportPaging.js`
  Pure helper for paginating through every row from search-style APIs for Vendor all-matching export.
- `tests/web_list_query.test.mjs`
  Node test coverage for pure list-query helper behavior.
- `tests/web_date_helpers.test.mjs`
  Node test coverage for local date/deadline behavior.
- `tests/web_use_list_search.test.mjs`
  Node test coverage for `listSearchCore`: route sync, paging/sorting payloads, reset, export criteria, stale response protection, and route-query restore.
- `tests/web_export_all.test.mjs`
  Node test coverage for Vendor-style paginated `exportAll` criteria forwarding.

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
- `tests/test_api_bridge.py`
- `tests/web_navigation_state.test.mjs`

Do not modify Operation Logs or Email Logs search behavior in this plan.

Email and log scope clarification:
- Do not migrate `/logs`, `/emails`, or `/emails/logs` to `useListSearch`.
- Do not change `EmailLogsView.vue` filtering, pagination, or export behavior.
- Do not change `open_entity_email`, Outlook draft generation, or email notification APIs.
- Do not change `window.__protocolNavigate`; email/protocol deep links continue to open details directly without `returnTo`.
- `action`, `highlight`, `redirect`, and `returnTo` are reserved query keys only so list query parsing never forwards them as backend filters.

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

Expected: FAIL because the new helper modules or exports are missing. If the command fails for syntax or test-runner setup errors instead, fix the test setup before implementing the helpers.

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


def test_gr_is_cancellation_filter_is_supported(app_config):
    _sc_id, _po_id, gr_id, _vendor_id = seed_query_data(app_config)

    assert search_grs(app_config, filters={"is_cancellation": "N"}, current_user=ADMIN)["rows"][0]["gr_id"] == gr_id
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

Replace `_append_text_search` with:

```python
def _append_text_search(
    clauses: list[str],
    params: list,
    text: str | None,
    columns: tuple[str, ...],
) -> None:
    if not text:
        return
    search_clauses = (
        f"lower(coalesce({column}, '')) like ? escape '\\\\'"
        for column in columns
    )
    clauses.append("(" + " or ".join(search_clauses) + ")")
    params.extend([_contains_param(text)] * len(columns))
```

In `_append_filters`, replace only the `elif field in like_fields:` branch with:

```python
        elif field in like_fields:
            column = allowed_filters.get(field)
            if column is None:
                raise ValidationError("filter field is invalid")
            clauses.append(f"lower(coalesce({column}, '')) like ? escape '\\\\'")
            params.append(_contains_param(value))
```

Leave `_from`, `_to`, `_min`, `_max`, and exact-match branches unchanged.

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

Also add GR cancellation to `search_grs` `allowed_filters` so the existing GR list filter remains valid:

```python
"is_cancellation": "gr.is_cancellation",
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
- Modify: `tests/test_api_bridge.py`

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

    rows = export_service.build_cascade_rows(
        app_config, "sc", {}, "created_at", "desc",
        cascade_options={"po": False, "gr": False},
        current_user={"user_id": "U1", "machine_id": "M001", "user_name": "Alice", "role": "admin"},
        text="alpha",
    )
    stats = export_service.compute_statistics(
        app_config,
        {"SC"},
        {},
        export_rows=rows,
        text="alpha",
        sort="created_at",
        direction="desc",
        current_user={"user_id": "U1", "machine_id": "M001", "user_name": "Alice", "role": "admin"},
    )

    assert stats["overview"]["sc"]["total_count"] == 1
    assert stats["overview"]["sc"]["total_amount"] == 50000


def test_cascade_statistics_are_based_on_exported_child_rows(app_config):
    migrate(app_config)
    import sqlite3
    conn = sqlite3.connect(app_config.db_path)
    conn.execute("INSERT INTO users (user_id, machine_id, user_name, role, status, created_at, updated_at) VALUES ('U1', 'M001', 'Alice', 'admin', 'active', '2026-01-01', '2026-01-01')")
    conn.execute("INSERT INTO users (user_id, machine_id, user_name, role, status, created_at, updated_at) VALUES ('U2', 'M002', 'Bob', 'requester', 'active', '2026-01-01', '2026-01-01')")
    conn.execute("INSERT INTO vendors (vendor_id, vendor_name, created_at, updated_at) VALUES ('V1', 'Alpha Vendor', '2026-01-01', '2026-01-01')")
    conn.execute("INSERT INTO sc_records (sc_id, sc_no, requester_id, request_type, cost_center, sc_amount, currency, service_period_start, service_period_end, status, description, created_by, created_at, updated_at) VALUES ('sc-alpha', 'SC-ALPHA', 'U2', 'new', 1000, 50000, 'CNY', '2026-01-01', '2026-06-30', 'approved', 'Alpha service', 'U2', '2026-01-15', '2026-01-15')")
    conn.execute("INSERT INTO sc_records (sc_id, sc_no, requester_id, request_type, cost_center, sc_amount, currency, service_period_start, service_period_end, status, description, created_by, created_at, updated_at) VALUES ('sc-beta', 'SC-BETA', 'U2', 'new', 2000, 30000, 'CNY', '2026-02-01', '2026-07-31', 'approved', 'Beta service', 'U2', '2026-02-01', '2026-02-01')")
    conn.execute("INSERT INTO pos (po_id, po_no, sc_id, vendor_id, po_amount, currency, status, created_at, updated_at) VALUES ('po-alpha', 'PO-ALPHA', 'sc-alpha', 'V1', 700, 'CNY', 'active', '2026-01-20', '2026-01-20')")
    conn.execute("INSERT INTO pos (po_id, po_no, sc_id, vendor_id, po_amount, currency, status, created_at, updated_at) VALUES ('po-beta', 'PO-BETA', 'sc-beta', 'V1', 900, 'CNY', 'active', '2026-02-10', '2026-02-10')")
    conn.commit()
    conn.close()

    rows = export_service.build_cascade_rows(
        app_config, "sc", {}, "created_at", "desc",
        cascade_options={"po": True, "gr": False},
        current_user={"user_id": "U1", "machine_id": "M001", "user_name": "Alice", "role": "admin"},
        text="alpha",
    )
    stats = export_service.compute_statistics(app_config, {"SC", "PO"}, {}, export_rows=rows)

    assert stats["overview"]["sc"]["total_count"] == 1
    assert stats["overview"]["po"]["total_count"] == 1
    assert stats["overview"]["po"]["total_amount"] == 700
```

Append to `tests/test_api_bridge.py`:

```python
def test_bridge_export_methods_forward_text_and_current_user(monkeypatch, app_config):
    from sc_gr_app.api import bridge

    calls = []

    monkeypatch.setattr(bridge, "get_7_digit_id", lambda: "1234567")
    monkeypatch.setattr(
        bridge,
        "get_user_by_machine_id",
        lambda _config, _machine_id: {"user_id": "U1", "machine_id": "1234567", "user_name": "Alice", "role": "admin"},
    )
    monkeypatch.setattr(bridge, "save_workbook_dialog", lambda *_args, **_kwargs: "ok.xlsx")

    def fake_rows(*args, **kwargs):
        calls.append(("rows", args, kwargs))
        return [{"_type": "SC", "sc_id": "sc-alpha"}]

    def fake_stats(*args, **kwargs):
        calls.append(("stats", args, kwargs))
        return {"overview": {}}

    monkeypatch.setattr(bridge.export_service, "build_cascade_rows", fake_rows)
    monkeypatch.setattr(bridge.export_service, "compute_statistics", fake_stats)
    monkeypatch.setattr(bridge.export_service, "build_export_workbook", lambda *_args, **_kwargs: object())

    api = bridge.ApiBridge(app_config)
    api.export_scs_cascade({"text": "alpha", "filters": {"status": "approved"}, "sort": "created_at", "direction": "desc"})

    row_kwargs = calls[0][2]
    stats_kwargs = calls[1][2]
    assert row_kwargs["text"] == "alpha"
    assert row_kwargs["current_user"]["user_id"] == "U1"
    assert stats_kwargs["text"] == "alpha"
    assert stats_kwargs["current_user"]["user_id"] == "U1"
    assert "export_rows" in stats_kwargs
```

- [ ] **Step 2: Run export tests and verify they fail**

Run:

```powershell
uv run pytest tests\test_export_service.py -k "text_criteria or text_search" -q
```

Expected: FAIL because export service does not accept `text`.

- [ ] **Step 3: Thread `text` through export row fetching**

Modify `build_cascade_rows`, `_build_sc_cascade`, `_build_po_cascade`, `_build_gr_rows`, and `_fetch_all_search` to accept `text=None`. Selected-id export still takes priority over text/filters, but it must not bypass visibility rules: for `selected_ids`, fetch rows through the same query service used for normal search by calling `_fetch_all_search(entity_type, config, {id_col: selected_id}, sort, direction, current_user, None, text=None)` for each selected ID, then keep the original `selected_ids` order.

In `_fetch_all_search`, pass `text=text` into the query service call:

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

- [ ] **Step 4: Make statistics use exported row IDs**

Modify `compute_statistics` signature:

```python
def compute_statistics(
    config: AppConfig,
    entity_types: set[str],
    filters: dict,
    selected_ids: list[str] | None = None,
    *,
    export_rows: list[dict] | None = None,
    text: str | None = None,
    sort: str = "created_at",
    direction: str = "desc",
    current_user: dict | None = None,
) -> dict:
```

Inside it, prefer `export_rows` when provided and derive IDs per entity type from the actual rows that will be written to the workbook:

```python
def _ids_by_entity_from_export_rows(rows):
    ids = {"SC": [], "PO": [], "GR": []}
    for row in rows or []:
        row_type = row.get("_type")
        if row_type == "SC" and row.get("sc_id"):
            ids["SC"].append(row["sc_id"])
        elif row_type == "PO" and row.get("po_id"):
            ids["PO"].append(row["po_id"])
        elif row_type == "GR" and row.get("gr_id"):
            ids["GR"].append(row["gr_id"])
    return ids

ids_by_entity = _ids_by_entity_from_export_rows(export_rows) if export_rows is not None else None
```

Pass entity-specific IDs to each statistics helper: SC helpers receive `ids_by_entity["SC"]`, PO helpers receive `ids_by_entity["PO"]`, and GR helpers receive `ids_by_entity["GR"]`. Do not reuse SC IDs for PO or GR statistics.

When `export_rows` is not supplied, preserve existing behavior for legacy callers. When `text` is supplied without `export_rows`, compute root rows using `_fetch_all_search(...)`, derive `ids_by_entity` from those root rows, and use those IDs only for the matching root entity.

- [ ] **Step 5: Thread text through bridge export methods**

In `sc_gr_app/api/bridge.py`, update `export_scs_cascade`, `export_pos_cascade`, and `export_grs_with_stats`:

```python
text = payload.get("text")
```

Pass `text=text` to `export_service.build_cascade_rows(...)`. Store the returned rows in a local variable and pass the same rows to `export_service.compute_statistics(..., export_rows=rows, text=text, ...)` so statistics are computed from the workbook row set.

- [ ] **Step 6: Run export tests**

Run:

```powershell
uv run pytest tests\test_export_service.py tests\test_api_bridge.py -q
```

Expected: PASS.

- [ ] **Step 7: Run query/export regression tests**

Run:

```powershell
uv run pytest tests\test_query_service.py tests\test_query_filters.py tests\test_export_service.py tests\test_api_bridge.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit backend export parity**

Run:

```powershell
git add sc_gr_app/services/export_service.py sc_gr_app/api/bridge.py tests/test_export_service.py tests/test_api_bridge.py
git commit -m "fix(export): honor list text criteria"
```

---

### Task 4: Shared Frontend List Search Composable

**Files:**
- Create: `frontend/src/utils/listSearchCore.js`
- Create: `frontend/src/composables/useListSearch.js`
- Create: `tests/web_use_list_search.test.mjs`
- Modify: `frontend/src/composables/usePo.js`
- Modify: `frontend/src/composables/useSc.js`
- Modify: `frontend/src/composables/useGr.js`
- Modify: `frontend/src/composables/useVendor.js`

- [ ] **Step 1: Write failing list-search core tests**

Create `tests/web_use_list_search.test.mjs`:

```js
import assert from "node:assert/strict";
import { test } from "node:test";

import { createListSearchCore } from "../frontend/src/utils/listSearchCore.js";

function config(overrides = {}) {
  return {
    apiMethod: "search_things",
    defaultSort: "created_at",
    defaultDirection: "desc",
    defaultPageSize: 10,
    allowedFilterKeys: new Set(["status", "vendor_name"]),
    allowedSortKeys: new Set(["created_at", "vendor_name"]),
    ...overrides,
  };
}

function fakeRouter() {
  const calls = [];
  return {
    calls,
    async replace(location) { calls.push(location); },
  };
}

test("initializeFromRoute parses query syncs normalized query and reloads", async () => {
  const calls = [];
  const router = fakeRouter();
  const core = createListSearchCore(config(), async (_method, payload) => {
    calls.push(payload);
    return { rows: [{ id: 1 }], total: 1 };
  });

  await core.initializeFromRoute({ query: { q: "alpha", status: "approved", page: "2", pageSize: "25", sort: "vendor_name", direction: "asc" } }, router);

  assert.equal(core.state.text, "alpha");
  assert.deepEqual(core.state.filters, { status: "approved" });
  assert.equal(calls[0].limit, 25);
  assert.equal(calls[0].offset, 25);
  assert.deepEqual(router.calls.at(-1).query, { q: "alpha", status: "approved", page: "2", pageSize: "25", sort: "vendor_name", direction: "asc" });
});

test("applyFilter resets to first page and exports matching criteria", async () => {
  const calls = [];
  const router = fakeRouter();
  const core = createListSearchCore(config(), async (_method, payload) => {
    calls.push(payload);
    return { rows: [], total: 0 };
  });

  core.state.currentPage = 4;
  await core.applyFilter({ text: "beta", filters: { status: "pending" } }, router);

  assert.equal(core.state.currentPage, 1);
  assert.equal(calls.at(-1).offset, 0);
  assert.deepEqual(core.exportCriteria(), { text: "beta", filters: { status: "pending" }, sort: "created_at", direction: "desc" });
});

test("changeSort normalizes element-plus order and ignores unsupported prop", async () => {
  const calls = [];
  const core = createListSearchCore(config(), async (_method, payload) => {
    calls.push(payload);
    return { rows: [], total: 0 };
  });

  await core.changeSort({ prop: "vendor_name", order: "ascending" });
  assert.equal(core.state.sort, "vendor_name");
  assert.equal(core.state.direction, "asc");
  await core.changeSort({ prop: "bad", order: "descending" });
  assert.equal(core.state.sort, "created_at");
  assert.equal(core.state.direction, "desc");
});

test("restoreFromRoute handles browser back forward without writing router", async () => {
  const calls = [];
  const router = fakeRouter();
  const core = createListSearchCore(config(), async (_method, payload) => {
    calls.push(payload);
    return { rows: [], total: 0 };
  });

  await core.restoreFromRoute({ query: { q: "back", page: "3", pageSize: "10" } });

  assert.equal(core.state.text, "back");
  assert.equal(core.state.currentPage, 3);
  assert.equal(calls.at(-1).offset, 20);
  assert.deepEqual(router.calls, []);
});

test("reload ignores stale slower responses", async () => {
  let resolveFirst;
  const first = new Promise(resolve => { resolveFirst = resolve; });
  let callCount = 0;
  const core = createListSearchCore(config(), async () => {
    callCount += 1;
    if (callCount === 1) return first;
    return { rows: [{ id: "second" }], total: 1 };
  });

  const slow = core.reload();
  await core.reload();
  resolveFirst({ rows: [{ id: "first" }], total: 1 });
  await slow;

  assert.deepEqual(core.state.rows, [{ id: "second" }]);
});
```

- [ ] **Step 2: Run list-search core tests and verify they fail**

Run:

```powershell
node --test tests\web_use_list_search.test.mjs
```

Expected: FAIL because `frontend/src/utils/listSearchCore.js` does not exist.

- [ ] **Step 3: Implement framework-free `listSearchCore.js`**

Create `frontend/src/utils/listSearchCore.js`. It must import only relative pure helpers, not Vue and not `@/...` aliases:

```js
import { buildQueryFromListState, criteriaFromState, parseListQuery } from "./listQuery.js";

function cloneFilters(filters) {
  return { ...(filters || {}) };
}

function sameQuery(a, b) {
  return JSON.stringify(a || {}) === JSON.stringify(b || {});
}

export function createListSearchCore(config, callApi) {
  let requestSeq = 0;
  const state = {
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
  };

  function assignListState(next) {
    state.text = next.text || null;
    state.filters = cloneFilters(next.filters);
    state.sort = next.sort;
    state.direction = next.direction;
    state.pageSize = next.pageSize;
    state.currentPage = next.currentPage;
  }

  function currentQuery() {
    return buildQueryFromListState(state);
  }

  async function syncRoute(router) {
    if (!router) return;
    const query = currentQuery();
    if (sameQuery(router.currentRoute?.value?.query, query)) return;
    await router.replace({ query });
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
    };
  }

  async function reload(extra = {}) {
    const seq = ++requestSeq;
    state.loading = true;
    state.error = null;
    try {
      const result = await callApi(config.apiMethod, payload(extra));
      if (seq !== requestSeq) return;
      state.rows = result.rows || result.items || result || [];
      state.total = result.total ?? state.rows.length;
    } catch (e) {
      if (seq !== requestSeq) return;
      state.error = e.message || String(e);
      state.rows = [];
      state.total = 0;
    } finally {
      if (seq === requestSeq) state.loading = false;
    }
  }

  async function initializeFromRoute(route, router) {
    assignListState(parseListQuery(route?.query || {}, config));
    await syncRoute(router);
    await reload();
  }

  async function restoreFromRoute(route) {
    assignListState(parseListQuery(route?.query || {}, config));
    await reload();
  }

  async function applyFilter({ text, filters }, router) {
    state.text = text || null;
    state.filters = cloneFilters(config.transformFilters ? config.transformFilters(filters || {}) : filters);
    state.currentPage = 1;
    await syncRoute(router);
    await reload();
  }

  async function changePage(page, router) {
    state.currentPage = page;
    await syncRoute(router);
    await reload();
  }

  async function changePageSize(size, router) {
    state.pageSize = size;
    state.currentPage = 1;
    await syncRoute(router);
    await reload();
  }

  async function changeSort({ prop, order }, router) {
    state.sort = config.allowedSortKeys.has(prop) ? prop : config.defaultSort;
    state.direction = order === "ascending" ? "asc" : (order === "descending" ? "desc" : config.defaultDirection);
    state.currentPage = 1;
    await syncRoute(router);
    await reload();
  }

  async function reset(router) {
    state.text = null;
    state.filters = {};
    state.sort = config.defaultSort;
    state.direction = config.defaultDirection;
    state.currentPage = 1;
    await syncRoute(router);
    await reload();
  }

  async function search(text = state.text, filters = state.filters) {
    state.text = text || null;
    state.filters = cloneFilters(config.transformFilters ? config.transformFilters(filters || {}) : filters);
    await reload();
  }

  function exportCriteria() {
    return criteriaFromState(state);
  }

  return { state, initializeFromRoute, restoreFromRoute, applyFilter, changePage, changePageSize, changeSort, reset, reload, search, exportCriteria, currentQuery };
}
```

- [ ] **Step 4: Implement Vue wrapper `useListSearch.js`**

Create `frontend/src/composables/useListSearch.js`:

```js
import { reactive } from 'vue'
import { callApi } from '@/api/bridge.js'
import { createListSearchCore } from '@/utils/listSearchCore.js'

export function useListSearch(config) {
  const core = createListSearchCore(config, callApi)
  core.state = reactive(core.state)
  return core
}
```

`state` is intentionally writable because list pages bind `v-model:text="state.text"` and `v-model:filters="state.filters"` directly. Do not wrap it in `readonly()`.

- [ ] **Step 5: Run list-search core tests and verify they pass**

Run:

```powershell
node --test tests\web_use_list_search.test.mjs
```

Expected: PASS.

- [ ] **Step 6: Refactor `usePo.js`**

Replace list-state implementation with `useListSearch`. Keep existing mutation methods. Configuration:

```js
const list = useListSearch({
  apiMethod: 'search_pos',
  defaultSort: 'created_at',
  defaultDirection: 'desc',
  defaultPageSize: pageSize,
  allowedFilterKeys: new Set([
    'status', 'po_id', 'po_no', 'sc_id', 'vendor_id', 'vendor_name',
    'requester_name', 'is_fc_po', 'contract_type', 'contract_no',
    'payment_frequency', 'contract_pos', 'cost_center', 'purchaser',
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

Return `state: list.state`, `searchPos: list.search`, `setFilters: filters => { list.state.filters = { ...(filters || {}) } }`, `resetFilters: list.reset`, `onSortChange: list.changeSort`, `onPageChange: list.changePage`, `onPageSizeChange: list.changePageSize`, plus `initializeFromRoute`, `restoreFromRoute`, `applyFilter`, `changePage`, `changePageSize`, `changeSort`, `reset`, `reload`, and `exportCriteria`.

- [ ] **Step 7: Refactor `useSc.js`**

Use `useListSearch` for list state. Do not change the existing implementations of `fetchDetail`, `createDraft`, `submitSc`, `updateSc`, `approveSc`, `denySc`, or `finishSc`.

Use this configuration:

```js
const list = useListSearch({
  apiMethod: 'search_scs',
  defaultSort: 'created_at',
  defaultDirection: 'desc',
  defaultPageSize: pageSize,
  allowedFilterKeys: new Set([
    'status', 'request_type', 'service_scope', 'is_calloff', 'asset',
    'cost_center', 'sc_id', 'sc_no', 'requester_id', 'requester_name',
    'created_by', 'created_by_name', 'description', 'calloff_po_id',
    'service_period_start_from', 'service_period_start_to',
    'sc_amount_min', 'sc_amount_max',
    'pending_date_from', 'pending_date_to',
    'approved_date_from', 'approved_date_to',
    'confirmed_at_from', 'confirmed_at_to',
    'deadline_from', 'deadline_to',
  ]),
  allowedSortKeys: new Set([
    'sc_id', 'sc_no', 'requester_id', 'requester_name', 'request_type',
    'service_scope', 'cost_center', 'sc_amount', 'status', 'created_at',
    'updated_at', 'asset', 'pending_date', 'approved_date', 'confirmed_at',
    'calloff_po_id',
  ]),
})
```

Return this list API mapping from `useSc.js`:

```js
return {
  state: list.state,
  searchScs: list.search,
  setFilters: filters => { list.state.filters = { ...(filters || {}) } },
  resetFilters: list.reset,
  onSortChange: list.changeSort,
  onPageChange: list.changePage,
  onPageSizeChange: list.changePageSize,
  initializeFromRoute: list.initializeFromRoute,
  restoreFromRoute: list.restoreFromRoute,
  applyFilter: list.applyFilter,
  changePage: list.changePage,
  changePageSize: list.changePageSize,
  changeSort: list.changeSort,
  reset: list.reset,
  reload: list.reload,
  exportCriteria: list.exportCriteria,
  fetchDetail,
  createDraft,
  submitSc,
  updateSc,
  approveSc,
  denySc,
  finishSc,
}
```

- [ ] **Step 8: Refactor `useGr.js`**

Use `useListSearch` for list state. Do not change the existing GR mutation implementations.

Use this configuration:

```js
const list = useListSearch({
  apiMethod: 'search_grs',
  defaultSort: 'created_at',
  defaultDirection: 'desc',
  defaultPageSize: pageSize,
  allowedFilterKeys: new Set([
    'status', 'gr_id', 'gr_no', 'po_id', 'sc_id', 'requester_id',
    'vendor_id', 'estimated_amount_min', 'estimated_amount_max',
    'tax_rate', 'con_value_min', 'con_value_max', 'gross_cost_min',
    'gross_cost_max', 'pending_date_from', 'pending_date_to',
    'approved_date_from', 'approved_date_to', 'confirmed_at_from',
    'confirmed_at_to', 'goods_service_description', 'confirmation_name',
    'last_delivery', 'is_cancellation', 'remark', 'created_by',
    'deadline_from', 'deadline_to',
  ]),
  allowedSortKeys: new Set([
    'gr_id', 'gr_no', 'po_no', 'sc_no', 'vendor_name', 'estimated_amount',
    'con_value', 'gross_cost', 'tax_rate', 'goods_service_description',
    'confirmation_name', 'last_delivery', 'status', 'created_at',
    'approved_at', 'cancelled_at', 'pending_date', 'approved_date',
    'confirmed_at',
  ]),
})
```

Return this list API mapping from `useGr.js`:

```js
return {
  state: list.state,
  searchGrs: list.search,
  setFilters: filters => { list.state.filters = { ...(filters || {}) } },
  resetFilters: list.reset,
  onSortChange: list.changeSort,
  onPageChange: list.changePage,
  onPageSizeChange: list.changePageSize,
  initializeFromRoute: list.initializeFromRoute,
  restoreFromRoute: list.restoreFromRoute,
  applyFilter: list.applyFilter,
  changePage: list.changePage,
  changePageSize: list.changePageSize,
  changeSort: list.changeSort,
  reset: list.reset,
  reload: list.reload,
  exportCriteria: list.exportCriteria,
  createGr,
  updateGr,
  approveGr,
  denyGr,
  submitGr,
  finishGr,
}
```

- [ ] **Step 9: Refactor `useVendor.js`**

Use `useListSearch` with default sort `vendor_name`, direction `asc`, page size `10`, and API `search_vendors`.

Use this configuration:

```js
const list = useListSearch({
  apiMethod: 'search_vendors',
  defaultSort: 'vendor_name',
  defaultDirection: 'asc',
  defaultPageSize: 10,
  allowedFilterKeys: new Set([
    'vendor_name', 'company_name_cn', 'vendor_id', 'ksrm_vendor_code',
    'service_scope', 'created_by', 'contact_person', 'email', 'phone',
    'description',
  ]),
  allowedSortKeys: new Set([
    'vendor_id', 'vendor_name', 'ksrm_vendor_code', 'company_name_cn',
    'service_scope', 'created_at', 'updated_at',
  ]),
})
```

Return `state: list.state`, `searchVendors: list.search`, `initializeFromRoute`, `restoreFromRoute`, `applyFilter`, `changePage`, `changePageSize`, `changeSort`, `reset`, `reload`, and `exportCriteria`, plus `createVendor`, `updateVendor`, `disableVendor`, `deleteVendor`, and `checkKsrmDuplicate`. Mutations should call `list.reload()` instead of stateless `searchVendors()`.

- [ ] **Step 10: Run frontend behavior tests and build**

Run:

```powershell
node --test tests\web_use_list_search.test.mjs
```

Expected: PASS.

Run from `frontend`:

```powershell
npm.cmd run build
```

Expected: PASS. Existing chunk-size warnings are acceptable.

- [ ] **Step 11: Commit shared composable**

Run:

```powershell
git add frontend/src/utils/listSearchCore.js frontend/src/composables/useListSearch.js frontend/src/composables/usePo.js frontend/src/composables/useSc.js frontend/src/composables/useGr.js frontend/src/composables/useVendor.js tests/web_use_list_search.test.mjs
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

Replace the `<script setup>` block in `frontend/src/components/common/AdvancedFilterBar.vue` with:

```js
import { ref, computed, watch, onUnmounted } from 'vue'
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
let pendingText = props.text || ''

watch(
  () => props.filters,
  value => {
    if (Object.keys(value || {}).length) showAdvanced.value = true
  },
  { immediate: true, deep: true },
)

watch(
  () => props.text,
  value => { pendingText = value || '' },
)

onUnmounted(() => clearTimeout(debounceTimer))

function emitFilterPayload(text = props.text || '') {
  emit('filter', { text: text || null, filters: props.filters || {} })
}

function updateFilter(key, value) {
  const next = { ...(props.filters || {}) }
  if (value === null || value === '' || value === undefined) delete next[key]
  else next[key] = value
  emit('update:filters', next)
  emit('filter', { text: pendingText || props.text || null, filters: next })
}

function onSearchDebounced(value) {
  pendingText = value || ''
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => emitFilterPayload(pendingText), 500)
}

function handleReset() {
  clearTimeout(debounceTimer)
  pendingText = ''
  emit('update:text', '')
  emit('update:filters', {})
  emit('reset')
}
```

Update the top search input to keep the existing visual attributes and pass the current input value into the debounce handler:

```vue
<el-input
  v-model="searchText"
  :placeholder="$t('common.search')"
  :prefix-icon="Search"
  clearable
  style="width: 260px"
  @input="onSearchDebounced"
/>
```

Replace advanced filter controls with controlled `:model-value` / `@update:model-value` bindings:

```vue
<el-select
  v-if="f.type === 'select'"
  :model-value="filters[f.name]"
  :placeholder="f.label"
  clearable
  style="width: 160px"
  @update:model-value="value => updateFilter(f.name, value)"
>
```

```vue
<el-input
  v-else-if="f.type === 'input'"
  :model-value="filters[f.name]"
  :placeholder="f.label"
  clearable
  style="width: 160px"
  @update:model-value="value => updateFilter(f.name, value)"
/>
```

For date ranges, use `f.name + '_from'` and `f.name + '_to'`:

```vue
<el-date-picker
  :model-value="filters[f.name + '_from']"
  :placeholder="f.label + ' ' + $t('common.from')"
  type="date"
  format="YYYY-MM-DD"
  value-format="YYYY-MM-DD"
  style="width: 160px"
  @update:model-value="value => updateFilter(f.name + '_from', value)"
/>
<el-date-picker
  :model-value="filters[f.name + '_to']"
  :placeholder="f.label + ' ' + $t('common.to')"
  type="date"
  format="YYYY-MM-DD"
  value-format="YYYY-MM-DD"
  style="width: 160px"
  @update:model-value="value => updateFilter(f.name + '_to', value)"
/>
```

For amount ranges, use `f.name + '_min'` and `f.name + '_max'` with the same `updateFilter` pattern.

- [ ] **Step 2: Add shared route-watch handlers to each list page**

In each of `PoListView.vue`, `ScListView.vue`, `GrListView.vue`, and `VendorListView.vue`, import `watch` from Vue and import both router hooks:

```js
import { useRoute, useRouter } from 'vue-router'
```

Create route/router and a route-sync guard:

```js
const route = useRoute()
const router = useRouter()
let restoringFromRoute = false

async function restoreListFromRoute() {
  restoringFromRoute = true
  try {
    selectedRows.value = []
    await restoreFromRoute(route)
  } finally {
    restoringFromRoute = false
  }
}

watch(
  () => route.fullPath,
  async () => {
    if (restoringFromRoute) return
    await restoreListFromRoute()
  },
)
```

Use `onMounted(() => initializeFromRoute(route, router))` for the initial load. The watcher covers browser Back/Forward query changes while staying on the same list route.

- [ ] **Step 3: Wire PO list to controlled filter and route state**

In `PoListView.vue`, destructure the list API from `usePo()`:

```js
const {
  state, initializeFromRoute, restoreFromRoute, applyFilter, changePage,
  changePageSize, changeSort, reset, reload, exportCriteria,
  createPo, updatePo, submitPo, finishPo,
} = usePo()
```

Bind the filter bar:

```vue
<AdvancedFilterBar
  v-model:text="state.text"
  v-model:filters="state.filters"
  :filter-config="poFilterConfig"
  @filter="handleFilter"
  @reset="handleReset"
/>
```

Use these handlers:

```js
async function handleFilter(payload) {
  selectedRows.value = []
  await applyFilter(payload, router)
}

async function handleReset() {
  selectedRows.value = []
  await reset(router)
}

async function handlePageChange(page) {
  selectedRows.value = []
  await changePage(page, router)
}

async function handlePageSizeChange(size) {
  selectedRows.value = []
  await changePageSize(size, router)
}

async function handleSortChange(sortEvent) {
  selectedRows.value = []
  await changeSort(sortEvent, router)
}

async function refreshListAfterMutation() {
  selectedRows.value = []
  await reload()
}
```

Detail navigation must use named routes and preserve the current list URL:

```js
function openPoDetail(row) {
  const query = { returnTo: route.fullPath }
  if (row.sc_id) router.push({ name: 'po-detail', params: { scId: row.sc_id, poId: row.po_id }, query })
  else router.push({ name: 'po-detail-independent', params: { poId: row.po_id }, query })
}
```

Pass `:text="state.text"` and `v-bind="exportCriteria()"`-equivalent props to `ExportDialog`: `:filters="state.filters"`, `:sort="state.sort"`, and `:direction="state.direction"`.

- [ ] **Step 4: Wire SC list explicitly**

In `ScListView.vue`, destructure:

```js
const {
  state, initializeFromRoute, restoreFromRoute, applyFilter, changePage,
  changePageSize, changeSort, reset, reload, exportCriteria,
  createDraft, submitSc, updateSc, approveSc, denySc, finishSc,
} = useSc()
```

Bind the SC filter bar:

```vue
<AdvancedFilterBar
  v-model:text="state.text"
  v-model:filters="state.filters"
  :filter-config="scFilterConfig"
  @filter="handleFilter"
  @reset="handleReset"
/>
```

Use these SC handlers:

```js
async function handleFilter(payload) {
  selectedRows.value = []
  await applyFilter(payload, router)
}

async function handleReset() {
  selectedRows.value = []
  await reset(router)
}

async function handlePageChange(page) {
  selectedRows.value = []
  await changePage(page, router)
}

async function handlePageSizeChange(size) {
  selectedRows.value = []
  await changePageSize(size, router)
}

async function handleSortChange(sortEvent) {
  selectedRows.value = []
  await changeSort(sortEvent, router)
}
```

Replace existing detail navigation with:

```js
function openScDetail(row) {
  router.push({ name: 'sc-detail', params: { id: row.sc_id }, query: { returnTo: route.fullPath } })
}
```

Replace import completion handlers that call `searchScs` with:

```js
async function handleImported() {
  selectedRows.value = []
  await reload()
}
```

Pass `:text="state.text"`, `:filters="state.filters"`, `:sort="state.sort"`, and `:direction="state.direction"` to `ExportDialog`.

- [ ] **Step 5: Wire GR list explicitly**

In `GrListView.vue`, destructure:

```js
const {
  state, initializeFromRoute, restoreFromRoute, applyFilter, changePage,
  changePageSize, changeSort, reset, reload, exportCriteria,
  createGr, updateGr, submitGr, approveGr, denyGr, finishGr,
} = useGr()
```

Bind the GR filter bar:

```vue
<AdvancedFilterBar
  v-model:text="state.text"
  v-model:filters="state.filters"
  :filter-config="grFilterConfig"
  @filter="handleFilter"
  @reset="handleReset"
/>
```

Use these GR handlers:

```js
async function handleFilter(payload) {
  selectedRows.value = []
  await applyFilter(payload, router)
}

async function handleReset() {
  selectedRows.value = []
  await reset(router)
}

async function handlePageChange(page) {
  selectedRows.value = []
  await changePage(page, router)
}

async function handlePageSizeChange(size) {
  selectedRows.value = []
  await changePageSize(size, router)
}

async function handleSortChange(sortEvent) {
  selectedRows.value = []
  await changeSort(sortEvent, router)
}
```

Replace detail navigation with:

```js
function openGrDetail(row) {
  router.push({ name: 'gr-detail', params: { scId: row.sc_id, poId: row.po_id, grId: row.gr_id }, query: { returnTo: route.fullPath } })
}
```

Set all backend-supported sortable GR columns to `sortable="custom"`: `gr_no`, `po_no`, `sc_no`, `vendor_name`, `estimated_amount`, `con_value`, `gross_cost`, `tax_rate`, `goods_service_description`, `confirmation_name`, `last_delivery`, `status`, `created_at`, `approved_at`, `cancelled_at`, `pending_date`, `approved_date`, and `confirmed_at`.

Remove `sortable` from unsupported GR list columns currently visible in `GrListView.vue`: `requester_name`, `is_cancellation`, `remark`, and `submitted_date`. This plan does not add backend sort support for those columns.

Keep GR annual report export untouched; do not pass list criteria into annual report export.

- [ ] **Step 6: Wire Vendor list with pagination and export-all criteria**

In `VendorListView.vue`, import router hooks and destructure:

```js
const {
  state, initializeFromRoute, restoreFromRoute, applyFilter, changePage,
  changePageSize, changeSort, reset, reload, exportCriteria,
  createVendor, updateVendor, disableVendor, deleteVendor,
} = useVendor()
const { exportAll } = useExport()
```

Bind `AdvancedFilterBar`:

```vue
<AdvancedFilterBar
  v-model:text="state.text"
  v-model:filters="state.filters"
  :filter-config="vendorFilterConfig"
  @filter="handleFilter"
  @reset="handleReset"
>
```

Add sorting to the table:

```vue
<el-table :data="state.rows" v-loading="state.loading" stripe border @sort-change="handleSortChange">
```

Set Vendor sortable columns to `sortable="custom"` only for backend-supported sort keys visible in the table: `vendor_id`, `vendor_name`, `company_name_cn`, `ksrm_vendor_code`, and `service_scope`.

Add pagination below the table:

```vue
<el-pagination
  v-model:current-page="state.currentPage"
  v-model:page-size="state.pageSize"
  :page-sizes="[10, 25, 50, 100]"
  :total="state.total"
  layout="total, sizes, prev, pager, next, jumper"
  style="margin-top: 12px; justify-content: flex-end"
  @current-change="handlePageChange"
  @size-change="handlePageSizeChange"
/>
```

Replace Vendor export with paginated all-matching export. It must pass `text`, `filters`, `sort`, and `direction`, and must not pass `currentPage`, `pageSize`, or the current page rows:

```js
async function handleExport() {
  exporting.value = true
  try {
    const columns = [
      { key: 'vendor_id', label: t('vendor.vendorId') },
      { key: 'vendor_name', label: t('vendor.vendorName') },
      { key: 'company_name_cn', label: t('vendor.companyNameCn') },
      { key: 'ksrm_vendor_code', label: t('vendor.ksrmCode') },
      { key: 'service_scope', label: t('vendor.serviceScope') },
      { key: 'contact_person', label: t('vendor.contact') },
      { key: 'phone', label: t('vendor.phone') },
      { key: 'email', label: t('vendor.email') },
    ]
    await exportAll('search_vendors', exportCriteria(), columns, `Vendors_${new Date().toISOString().slice(0, 10)}`)
    ElMessage.success(t('export.exported'))
  } catch (e) {
    ElMessage.error(e.message || t('export.failed'))
  } finally {
    exporting.value = false
  }
}
```

After create/update/disable/delete/import, call `reload()` and clear selection if the page has selection state.

- [ ] **Step 7: Run frontend build**

Run from `frontend`:

```powershell
npm.cmd run build
```

Expected: PASS.

- [ ] **Step 8: Commit page wiring**

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
- Create: `frontend/src/utils/exportPaging.js`
- Create: `tests/web_export_all.test.mjs`
- Modify: `frontend/src/composables/useExport.js`

- [ ] **Step 1: Update `PoTable.vue` sorting contract**

In `PoTable.vue`:

- Add `@sort-change="$emit('sort-change', $event)"` to `<el-table>`.
- Add `'sort-change'` to `defineEmits`.
- Use `sortable="custom"` only for backend-supported columns.
- Remove `sortable` from derived unsupported columns `open_po_amount`, `po_pending_total_incl_tax`, `consumed_amount`, and `finished_at`. This plan does not add backend sort support for those columns.

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

- [ ] **Step 3: Add pure export-all paging test**

Create `tests/web_export_all.test.mjs`:

```js
import assert from "node:assert/strict";
import { test } from "node:test";

import { fetchAllSearchRows } from "../frontend/src/utils/exportPaging.js";

test("fetchAllSearchRows forwards criteria and paginates until short batch", async () => {
  const calls = [];
  const rows = await fetchAllSearchRows(
    async (method, payload) => {
      calls.push({ method, payload });
      if (payload.offset === 0) return { rows: [{ id: 1 }, { id: 2 }] };
      return { rows: [{ id: 3 }] };
    },
    "search_vendors",
    { text: "alpha", filters: { service_scope: "IT" }, sort: "vendor_name", direction: "asc" },
    2,
  );

  assert.deepEqual(rows, [{ id: 1 }, { id: 2 }, { id: 3 }]);
  assert.deepEqual(calls.map(c => c.payload), [
    { text: "alpha", filters: { service_scope: "IT" }, sort: "vendor_name", direction: "asc", limit: 2, offset: 0 },
    { text: "alpha", filters: { service_scope: "IT" }, sort: "vendor_name", direction: "asc", limit: 2, offset: 2 },
  ]);
});
```

- [ ] **Step 4: Run export paging test and verify it fails**

Run:

```powershell
node --test tests\web_export_all.test.mjs
```

Expected: FAIL because `frontend/src/utils/exportPaging.js` does not exist.

- [ ] **Step 5: Implement `exportPaging.js` and use it in `useExport.js`**

Create `frontend/src/utils/exportPaging.js`:

```js
export async function fetchAllSearchRows(callApi, apiMethod, params, limit = 500) {
  const allRows = []
  let offset = 0

  while (true) {
    const result = await callApi(apiMethod, { ...params, limit, offset })
    const rows = Array.isArray(result) ? result : (result.items || result.rows || [])
    if (!rows.length) break
    allRows.push(...rows)
    if (rows.length < limit) break
    offset += limit
  }

  return allRows
}
```

In `frontend/src/composables/useExport.js`, import it and replace the duplicated `exportAll` / `exportAllCSV` paging loops with:

```js
import { fetchAllSearchRows } from '@/utils/exportPaging.js'
```

```js
async function exportAll(apiMethod, params, columns, filename) {
  const allRows = await fetchAllSearchRows(callApi, apiMethod, params)
  return await exportRows(allRows, columns, filename)
}
```

```js
async function exportAllCSV(apiMethod, params, columns, filename) {
  const allRows = await fetchAllSearchRows(callApi, apiMethod, params)
  return await exportCSV(allRows, columns, filename)
}
```

- [ ] **Step 6: Add text prop to `ExportDialog.vue`**

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

- [ ] **Step 7: Pass text in export payload**

In `ExportDialog.vue`, selected rows are the only mode that ignores current criteria. Every non-selected export sends current `text`, `filters`, `sort`, and `direction`, so â€œallâ€ means all rows matching the current search/filter state, not unfiltered database all rows.

In `doExport()` payload:

```js
const payload = {
  text: dataScope.value === 'selected' ? null : (props.text || null),
  filters: dataScope.value === 'selected' ? {} : props.filters,
  sort: props.sort,
  direction: props.direction,
  cascade: { po: cascadePo.value, gr: cascadeGr.value },
  selected_ids: dataScope.value === 'selected' ? props.selectedIds : undefined,
}
```

For selected export, selected IDs take priority and text/filters are intentionally ignored by criteria, but backend export must still enforce current-user visibility for those IDs.

- [ ] **Step 8: Run export paging test and frontend build**

Run:

```powershell
node --test tests\web_export_all.test.mjs
```

Expected: PASS.

Run from `frontend`:

```powershell
npm.cmd run build
```

Expected: PASS.

- [ ] **Step 9: Commit table/export frontend updates**

Run:

```powershell
git add frontend/src/components/po/PoTable.vue frontend/src/components/sc/ScTable.vue frontend/src/components/export/ExportDialog.vue frontend/src/composables/useExport.js frontend/src/utils/exportPaging.js tests/web_export_all.test.mjs
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

- [ ] **Step 2: Run navigation helper test and verify it fails**

Run:

```powershell
node --test tests\web_navigation_state.test.mjs
```

Expected: FAIL because `sanitizeRedirectTarget` is not exported from `frontend/src/utils/listQuery.js`.

- [ ] **Step 3: Implement `sanitizeRedirectTarget`**

Add to `frontend/src/utils/listQuery.js`:

```js
export function sanitizeRedirectTarget(value, fallback = "/workbench") {
  if (typeof value !== "string" || !value.startsWith("/") || value.startsWith("//")) {
    return fallback;
  }
  return value;
}
```

- [ ] **Step 4: Use redirect helper in `LoginView.vue`**

Import `sanitizeRedirectTarget` and update `enterApp()`:

```js
const redirect = sanitizeRedirectTarget(router.currentRoute.value.query?.redirect)
router.push(redirect)
```

- [ ] **Step 5: Add `returnTo` to list detail navigation**

In PO/SC/GR list views, update detail route pushes to include:

```js
query: { returnTo: route.fullPath }
```

Use named routes for all list-to-detail pushes:

```js
router.push({ name: 'sc-detail', params: { id: row.sc_id }, query: { returnTo: route.fullPath } })
router.push({ name: 'po-detail', params: { scId: row.sc_id, poId: row.po_id }, query: { returnTo: route.fullPath } })
router.push({ name: 'po-detail-independent', params: { poId: row.po_id }, query: { returnTo: route.fullPath } })
router.push({ name: 'gr-detail', params: { scId: row.sc_id, poId: row.po_id, grId: row.gr_id }, query: { returnTo: route.fullPath } })
```

Use `sc-detail` in `ScListView.vue`, use `po-detail` or `po-detail-independent` in `PoListView.vue` based on whether the row has `sc_id`, and use `gr-detail` in `GrListView.vue`.

- [ ] **Step 6: Propagate `returnTo` during detail-to-detail navigation**

In `ScDetailView.vue`, `PoDetailView.vue`, and `GrDetailView.vue`, add:

```js
function childReturnQuery() {
  return route.query.returnTo ? { returnTo: route.query.returnTo } : {}
}
```

When navigating from SC detail to PO detail, pass `query: childReturnQuery()`:

```js
router.push({ name: 'po-detail', params: { scId, poId: row.po_id }, query: childReturnQuery() })
```

When navigating from PO detail to GR detail, pass `query: childReturnQuery()`:

```js
router.push({ name: 'gr-detail', params: { scId, poId, grId: row.gr_id }, query: childReturnQuery() })
```

When navigating from PO detail back to parent SC detail or from GR detail back to parent PO/SC detail, pass `query: childReturnQuery()` so a user who entered from a filtered list can delete from a deeper detail page and still return to the original list query.

- [ ] **Step 7: Use `returnTo` in detail fallback navigation**

In each of `ScDetailView.vue`, `PoDetailView.vue`, and `GrDetailView.vue`, import `sanitizeRedirectTarget`:

```js
import { sanitizeRedirectTarget } from '@/utils/listQuery.js'
```

If the file does not already have `const route = useRoute()`, add it next to the existing router setup. Then add:

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

- [ ] **Step 8: Run navigation helper tests**

Run:

```powershell
node --test tests\web_navigation_state.test.mjs
```

Expected: PASS.

- [ ] **Step 9: Run frontend build**

Run from `frontend`:

```powershell
npm.cmd run build
```

Expected: PASS.

- [ ] **Step 10: Commit navigation compatibility**

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
uv run pytest tests\test_query_service.py tests\test_query_filters.py tests\test_export_service.py tests\test_api_bridge.py -q
```

Expected: PASS.

- [ ] **Step 2: Run frontend helper tests**

Run:

```powershell
node --test tests\web_list_query.test.mjs tests\web_date_helpers.test.mjs tests\web_use_list_search.test.mjs tests\web_export_all.test.mjs tests\web_navigation_state.test.mjs
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
- Browser Back/Forward on PO/SC/GR/Vendor list restores `q`, advanced filters, page, pageSize, sort, and direction without a full page reload.
- GR list: table sorting triggers backend reload; annual report export still ignores list filters.
- Vendor list: pagination appears; export with a search term exports all matching rows, not only current page.
- Login redirect: unauthenticated `/sc?status=pending&page=2&q=abc` returns to the same URL after login.

- [ ] **Step 6: Commit final verification notes if code changed during cleanup**

When Step 1-5 reveal defects, fix only files touched by this plan. Then run `git status --short`, stage the exact fixed paths shown by status, and commit them:

```powershell
git add frontend/src/utils/listQuery.js frontend/src/utils/date.js frontend/src/utils/listSearchCore.js frontend/src/utils/exportPaging.js frontend/src/composables/useListSearch.js frontend/src/composables/usePo.js frontend/src/composables/useSc.js frontend/src/composables/useGr.js frontend/src/composables/useVendor.js frontend/src/composables/useExport.js frontend/src/components/common/AdvancedFilterBar.vue frontend/src/components/po/PoTable.vue frontend/src/components/sc/ScTable.vue frontend/src/components/export/ExportDialog.vue frontend/src/views/PoListView.vue frontend/src/views/ScListView.vue frontend/src/views/GrListView.vue frontend/src/views/VendorListView.vue frontend/src/views/LoginView.vue frontend/src/views/ScDetailView.vue frontend/src/views/PoDetailView.vue frontend/src/views/GrDetailView.vue sc_gr_app/services/query_service.py sc_gr_app/services/export_service.py sc_gr_app/api/bridge.py tests/test_query_service.py tests/test_export_service.py tests/test_api_bridge.py tests/web_list_query.test.mjs tests/web_date_helpers.test.mjs tests/web_use_list_search.test.mjs tests/web_export_all.test.mjs tests/web_navigation_state.test.mjs tests/web_auth_state.test.mjs
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
