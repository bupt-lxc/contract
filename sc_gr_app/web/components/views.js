import { callApi } from "./api.js";
import { date, escapeHtml, money, statusLabel, text } from "./format.js";
import { getViewState, resetFilters, setFilter, state } from "./state.js";
import { renderTable } from "./tables.js";

const SERVICE_SCOPES = [
  "Transportation",
  "engineering Service",
  "Equipment",
  "Parts",
  "Driver",
  "Test car rental",
  "General Service",
  "Dealers",
  "Import&Export&cusoms clearance",
  "Insurance",
  "Harness",
  "Maintenance",
  "Security",
  "Testing support",
  "Others",
];

const VIEW_DEFINITIONS = {
  sc: {
    title: "SC List",
    api: "search_scs",
    empty: "No SC records match the search and filters.",
    filters: [
      { name: "status", label: "SC status", type: "select", options: ["pending", "approved", "denied", "closed"] },
      { name: "request_type", label: "Request type", type: "select", options: ["material", "service", "fixed_asset", "FC"] },
      { name: "cost_center", label: "Cost center", type: "text", placeholder: "1001" },
    ],
    columns: [
      { key: "status", label: "Status", sortKey: "status", width: "12%", render: statusBadge },
      { key: "sc_no", label: "SC No", sortKey: "sc_no", width: "13%" },
      { key: "requester_name", label: "Requester", sortKey: "requester_name", width: "13%" },
      { key: "request_type", label: "Type", sortKey: "request_type", width: "12%" },
      { key: "cost_center", label: "Cost Center", sortKey: "cost_center", width: "11%" },
      { key: "sc_amount", label: "SC Amount", sortKey: "sc_amount", width: "13%", className: "amount", render: (value) => money(value) },
      { key: "created_at", label: "Created", sortKey: "created_at", width: "12%", render: (value) => date(value) },
      { key: "description", label: "Description", sortKey: null },
      { key: "actions", label: "Actions", sortKey: null, width: "7%", render: renderOpenDetailAction },
    ],
  },
  vendor: {
    title: "Vendor List",
    api: "search_vendors",
    empty: "No vendors match the selected service scope or search text.",
    filters: [
      { name: "service_scope", label: "Service scope", type: "select", options: SERVICE_SCOPES },
    ],
    columns: [
      { key: "vendor_name", label: "Vendor", sortKey: "vendor_name", width: "22%" },
      { key: "ksrm_vendor_code", label: "KSRM Code", sortKey: "ksrm_vendor_code", width: "12%" },
      { key: "service_scope", label: "Service Scope", sortKey: "service_scope", width: "20%" },
      { key: "contact_person", label: "Contact", sortKey: null, width: "12%" },
      { key: "phone", label: "Phone", sortKey: null, width: "12%" },
      { key: "email", label: "Email", sortKey: null },
    ],
  },
  po: {
    title: "PO List",
    api: "search_pos",
    empty: "No POs match the status, contract, OPEN PO, or search filters.",
    filters: [
      { name: "status", label: "PO status", type: "select", options: ["po_pending", "po_approved", "finished"] },
      { name: "contract_to", label: "Contract to", type: "date", localOnly: true },
      { name: "open_po", label: "OPEN PO", type: "select", localOnly: true, options: ["open", "closed"] },
    ],
    columns: [
      { key: "status", label: "Status", sortKey: "status", width: "12%", render: statusBadge },
      { key: "po_no", label: "PO No", sortKey: "po_no", width: "13%" },
      { key: "sc_no", label: "SC No", sortKey: "sc_no", width: "13%" },
      { key: "vendor_name", label: "Vendor", sortKey: "vendor_name", width: "20%" },
      { key: "po_amount", label: "PO Amount", sortKey: "po_amount", width: "13%", className: "amount", render: (value) => money(value) },
      { key: "open_po_amount", label: "OPEN PO", sortKey: null, width: "12%", className: "amount", render: (value) => money(value) },
      { key: "contract_to", label: "Contract To", sortKey: "contract_to", render: (value) => date(value) },
      { key: "actions", label: "Actions", sortKey: null, width: "7%", render: renderOpenDetailAction },
    ],
  },
  gr: {
    title: "GR List",
    api: "search_grs",
    unavailable: "GR search is not exposed by the desktop bridge yet.",
    empty: "No GR requests match the status, amount, or search filters.",
    filters: [
      { name: "status", label: "GR status", type: "select", options: ["pending", "approved", "cancelled"] },
      { name: "amount_min", label: "Amount min", type: "number", localOnly: true },
      { name: "amount_max", label: "Amount max", type: "number", localOnly: true },
    ],
    columns: [
      { key: "status", label: "Status", sortKey: "status", render: statusBadge },
      { key: "gr_id", label: "GR ID", sortKey: "gr_id", width: "13%" },
      { key: "po_no", label: "PO No", sortKey: "po_no", width: "13%" },
      { key: "sc_no", label: "SC No", sortKey: "sc_no", width: "13%" },
      { key: "vendor_name", label: "Vendor", sortKey: "vendor_name", width: "18%" },
      { key: "estimated_amount", label: "Estimated", sortKey: "estimated_amount", className: "amount", render: (value) => money(value) },
      { key: "con_value", label: "Con Value", sortKey: "con_value", className: "amount", render: (value) => money(value) },
      { key: "actions", label: "Actions", sortKey: null, width: "7%", render: renderOpenDetailAction },
    ],
  },
  logs: {
    title: "Logs List",
    api: "search_audit_logs",
    unavailable: "Audit log search is not exposed by the desktop bridge yet.",
    empty: "No audit logs match the date, action type, or search filters.",
    filters: [
      { name: "created_at", label: "Date", type: "date", localOnly: true },
      { name: "action_type", label: "Action type", type: "text", placeholder: "approve_gr" },
    ],
    columns: [
      { key: "created_at", label: "Created", sortKey: "created_at", width: "15%", render: (value) => date(value) },
      { key: "action_type", label: "Action", sortKey: "action_type", width: "16%" },
      { key: "object_type", label: "Object", sortKey: "object_type", width: "12%" },
      { key: "object_id", label: "Object ID", sortKey: "object_id", width: "14%" },
      { key: "sc_id", label: "SC ID", sortKey: "sc_id", width: "12%" },
      { key: "operator_id", label: "Operator", sortKey: "operator_id", width: "13%" },
      { key: "machine_id", label: "Machine", sortKey: "machine_id" },
    ],
  },
};

let requestSequence = 0;

export function getViewTitle(viewKey) {
  if (viewKey === "home") {
    return "Home";
  }
  if (viewKey === "system") {
    return "System";
  }
  if (viewKey === "sc-detail") {
    return "SC Detail";
  }
  return VIEW_DEFINITIONS[viewKey]?.title ?? "SC List";
}

export function getColumnsForView(viewKey) {
  return VIEW_DEFINITIONS[viewKey]?.columns ?? [];
}

export async function renderView(viewKey, regions, callbacks) {
  regions.home.innerHTML = "";
  regions.filters.innerHTML = "";

  if (viewKey === "home") {
    renderHome(regions);
    return;
  }

  if (viewKey === "system") {
    renderSystem(regions);
    return;
  }

  if (viewKey === "sc-detail") {
    renderScDetail(regions);
    return;
  }

  const definition = VIEW_DEFINITIONS[viewKey];
  renderFilters(viewKey, definition, regions.filters, callbacks);
  await loadAndRenderTable(viewKey, definition, regions.table, callbacks);
}

async function loadAndRenderTable(viewKey, definition, tableRegion, callbacks) {
  const requestId = ++requestSequence;
  const viewState = getViewState(viewKey);
  viewState.loading = true;
  viewState.error = null;
  renderRows(viewKey, definition, tableRegion, callbacks);

  try {
    const remoteFilters = {};
    for (const [key, value] of Object.entries(viewState.filters)) {
      const filterDef = definition.filters.find((filter) => filter.name === key);
      if (!filterDef?.localOnly) {
        remoteFilters[key] = value;
      }
    }
    const payload = {
      text: state.globalSearch || null,
      filters: Object.keys(remoteFilters).length ? remoteFilters : null,
      sort: viewState.sort,
      direction: viewState.direction,
      limit: 100,
      offset: 0,
    };
    const rows = await callApi(definition.api, payload);
    if (requestId !== requestSequence || state.currentView !== viewKey) {
      return;
    }
    viewState.rows = rows;
    viewState.rows = applyLocalFilters(viewState.rows, viewState.filters);
  } catch (error) {
    if (requestId !== requestSequence || state.currentView !== viewKey) {
      return;
    }
    viewState.rows = [];
    viewState.error = definition.unavailable && error.message.startsWith("API not available")
      ? definition.unavailable
      : error.message;
  } finally {
    if (requestId !== requestSequence || state.currentView !== viewKey) {
      return;
    }
    viewState.loading = false;
    renderRows(viewKey, definition, tableRegion, callbacks);
  }
}

function renderRows(viewKey, definition, tableRegion, callbacks) {
  const viewState = getViewState(viewKey);
  renderTable(tableRegion, {
    title: definition.title,
    columns: definition.columns,
    rows: viewState.rows,
    sortKey: viewState.sort,
    sortDirection: viewState.direction,
    loading: viewState.loading,
    error: viewState.error,
    emptyMessage: definition.empty,
    onSort: (sortKey) => callbacks.onSort(viewKey, sortKey),
    onRowClick: callbacks.onRowClick,
    onAction: callbacks.onAction,
  });
}

function renderFilters(viewKey, definition, container, callbacks) {
  const viewState = getViewState(viewKey);
  const fields = definition.filters.map((filter) => {
    const value = viewState.filters[filter.name] ?? "";
    if (filter.type === "select") {
      const options = [`<option value="">All</option>`].concat(
        filter.options.map((option) => `<option value="${escapeHtml(option)}"${option === value ? " selected" : ""}>${escapeHtml(statusLabel(option))}</option>`)
      );
      return fieldWrap(filter, `<select data-filter="${escapeHtml(filter.name)}">${options.join("")}</select>`);
    }
    return fieldWrap(filter, `<input data-filter="${escapeHtml(filter.name)}" type="${escapeHtml(filter.type)}" value="${escapeHtml(value)}" placeholder="${escapeHtml(filter.placeholder ?? "")}">`);
  }).join("");

  container.innerHTML = `
    <form class="filter-bar">
      ${fields}
      <button type="button" class="button" data-reset-filters>Reset</button>
    </form>
  `;

  container.querySelectorAll("[data-filter]").forEach((input) => {
    input.addEventListener("change", () => {
      setFilter(viewKey, input.dataset.filter, input.value);
      callbacks.onRefresh();
    });
  });

  container.querySelector("[data-reset-filters]").addEventListener("click", () => {
    resetFilters(viewKey);
    callbacks.onRefresh();
  });
}

function fieldWrap(filter, controlHtml) {
  return `
    <div class="filter-field">
      <label>${escapeHtml(filter.label)}</label>
      ${controlHtml}
    </div>
  `;
}

function applyLocalFilters(rows, filters) {
  return rows.filter((row) => {
    if (filters.contract_to && date(row.contract_to) !== filters.contract_to) {
      return false;
    }
    const openPoAmount = Number(row.open_po_amount ?? row.po_amount ?? 0);
    if (filters.open_po === "open" && openPoAmount <= 0) {
      return false;
    }
    if (filters.open_po === "closed" && openPoAmount > 0) {
      return false;
    }
    const amount = Number(row.estimated_amount ?? row.con_value ?? 0);
    if (filters.amount_min && amount < Number(filters.amount_min)) {
      return false;
    }
    if (filters.amount_max && amount > Number(filters.amount_max)) {
      return false;
    }
    return true;
  });
}

function statusBadge(value) {
  const raw = text(value);
  return `<span class="status-badge status-${escapeHtml(raw)}">${escapeHtml(statusLabel(raw))}</span>`;
}

function renderOpenDetailAction() {
  return `<button type="button" class="icon-button row-action" data-action="open-detail" title="Open SC detail">&gt;</button>`;
}

function renderScDetail(regions) {
  regions.home.innerHTML = `
    <div class="home-intro">
      <h2>SC Detail</h2>
      <p>SC detail routing is ready. The full detail workspace will load here in the next task.</p>
    </div>
  `;
  regions.table.innerHTML = "";
}

function renderHome(regions) {
  regions.home.innerHTML = `
    <div class="home-intro">
      <h2>Daily SC, vendor, PO, and GR workspace</h2>
      <p>Use the left navigation to move between operational queues. Search and filters apply to the active table without leaving the page.</p>
    </div>
    <div class="summary-grid">
      <div class="metric-card"><div class="metric-label">Default Queue</div><div class="metric-value">SC</div><div class="metric-note">Approved, pending, denied, closed</div></div>
      <div class="metric-card"><div class="metric-label">Bridge Ready</div><div class="metric-value">5</div><div class="metric-note">SC, Vendor, PO, GR, Logs APIs</div></div>
      <div class="metric-card"><div class="metric-label">Pending APIs</div><div class="metric-value">0</div><div class="metric-note">Core search surfaces exposed</div></div>
      <div class="metric-card"><div class="metric-label">Mode</div><div class="metric-value">Desktop</div><div class="metric-note">pywebview static UI</div></div>
    </div>
  `;
  regions.table.innerHTML = "";
}

function renderSystem(regions) {
  const user = state.user;
  const authorized = user ? "Authorized" : "Not authorized";
  regions.home.innerHTML = `
    <div class="home-intro">
      <h2>System</h2>
      <p>Current desktop identity and bridge availability are shown here for operations support.</p>
    </div>
    <div class="summary-grid">
      <div class="metric-card"><div class="metric-label">Authorization</div><div class="metric-value">${escapeHtml(authorized)}</div><div class="metric-note">${escapeHtml(state.userError ?? "Machine is mapped to an active user")}</div></div>
      <div class="metric-card"><div class="metric-label">Role</div><div class="metric-value">${escapeHtml(user?.role ?? "-")}</div><div class="metric-note">${escapeHtml(user?.user_name ?? "No active user loaded")}</div></div>
      <div class="metric-card"><div class="metric-label">Machine ID</div><div class="metric-value">${escapeHtml(user?.machine_id ?? "-")}</div><div class="metric-note">Windows user/device identity</div></div>
      <div class="metric-card"><div class="metric-label">Bridge</div><div class="metric-value">${window.pywebview?.api ? "Ready" : "Unavailable"}</div><div class="metric-note">Provided by pywebview</div></div>
    </div>
  `;
  regions.table.innerHTML = "";
}

export function renderDetail(row, drawer) {
  drawer.root.hidden = false;
  drawer.title.textContent = text(row.sc_no ?? row.po_no ?? row.vendor_name ?? row.gr_id ?? row.log_id ?? "Record");
  drawer.content.innerHTML = Object.entries(row).map(([key, value]) => `
    <div class="detail-row">
      <div class="detail-label">${escapeHtml(key)}</div>
      <div class="detail-value">${escapeHtml(text(value))}</div>
    </div>
  `).join("");
}
