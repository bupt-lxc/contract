import { callApi } from "./api.js";
import { date, escapeHtml, money, statusLabel, text } from "./format.js";
import { collectFormData, field } from "./forms.js";
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
  if (viewKey === "sc-new") {
    return "New SC";
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
    renderScDetail(regions, callbacks);
    return;
  }

  if (viewKey === "sc-new") {
    renderNewSc(regions, callbacks);
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

  if (viewKey === "sc") {
    const caption = tableRegion.querySelector(".table-caption");
    if (caption && !caption.querySelector("[data-new-sc]")) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "button primary";
      button.dataset.newSc = "";
      button.textContent = "New SC";
      button.addEventListener("click", () => callbacks.onNewSc?.());
      caption.append(button);
    }
  }
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

export function visibleDetailActions(detail) {
  const permissions = detail?.permissions ?? {};
  return [
    ["can_submit_sc", "submit-sc"],
    ["can_edit_sc", "edit-sc"],
    ["can_approve_sc", "approve-sc"],
    ["can_deny_sc", "deny-sc"],
    ["can_close_sc", "close-sc"],
    ["can_manage_po", "add-po"],
    ["can_manage_gr", "add-gr"],
  ]
    .filter(([permission]) => permissions[permission])
    .map(([, action]) => action);
}

export function visiblePoActions(row, detail) {
  if (!detail?.permissions?.can_manage_po) {
    return [];
  }
  const actions = ["edit"];
  if (row?.status === "po_pending") {
    actions.push("approve");
  }
  if (row?.status === "po_approved") {
    actions.push("finish");
  }
  return actions;
}

export function visibleGrActions(row, detail) {
  if (!detail?.permissions?.can_manage_gr) {
    return [];
  }
  if (row?.status === "pending") {
    return ["edit", "approve", "cancel"];
  }
  if (row?.status === "approved") {
    return ["edit"];
  }
  return [];
}

function renderNewSc(regions, callbacks) {
  regions.filters.innerHTML = "";
  regions.table.innerHTML = "";
  const pending = state.scDetail.actionPending;
  const actionError = state.scDetail.actionError
    ? `<div class="state-panel error action-error"><p>${escapeHtml(state.scDetail.actionError)}</p></div>`
    : "";
  const disabled = pending ? " disabled" : "";
  regions.home.innerHTML = `
    <section class="detail-section">
      <div class="detail-page-header">
        <div>
          <p class="eyebrow">SC</p>
          <h2>New SC</h2>
        </div>
        <div class="actions">
          <button type="button" class="button" data-cancel>Cancel</button>
        </div>
      </div>
      ${actionError}
      <form class="sc-form" data-new-sc-form>
        <div class="form-grid">
          ${field("requester_id", "Requester", state.user?.user_id ?? "", "text", { readonly: true, required: true })}
          ${field("sc_id", "SC ID", "", "text", { required: true })}
          ${field("sc_no", "SC No")}
          ${field("request_type", "Request Type")}
          ${field("cost_center", "Cost Center")}
          ${field("sc_amount", "SC Amount", "", "number")}
          ${field("service_period_start", "Service Period Start", "", "date")}
          ${field("service_period_end", "Service Period End", "", "date")}
          <label class="form-field full">
            <span>Description</span>
            <textarea name="description"></textarea>
          </label>
        </div>
        <div class="actions">
          <button type="submit" class="button" data-mode="draft"${disabled}>Save Draft${pending === "create" ? "..." : ""}</button>
          <button type="submit" class="button primary" data-mode="submit"${disabled}>Submit${pending === "create-submit" ? "..." : ""}</button>
          <button type="button" class="button" data-cancel${disabled}>Cancel</button>
        </div>
      </form>
    </section>
  `;

  const formElement = regions.home.querySelector("[data-new-sc-form]");
  formElement.addEventListener("submit", async (event) => {
    event.preventDefault();
    const mode = event.submitter?.dataset.mode ?? "draft";
    await callbacks.onCreateSc?.(mode, collectFormData(formElement.elements));
  });
  regions.home.querySelectorAll("[data-cancel]").forEach((button) => {
    button.addEventListener("click", () => callbacks.onCancel?.());
  });
}

export function renderScDetail(regions, callbacks = {}) {
  regions.filters.innerHTML = "";
  regions.table.innerHTML = "";
  const detail = state.scDetail.record;

  if (state.scDetail.loading) {
    regions.home.innerHTML = detailState("loading", "Loading SC detail", "Fetching SC, PO, GR, and audit data.");
    return;
  }

  if (state.scDetail.error) {
    regions.home.innerHTML = detailState("error", "Unable to load SC detail", state.scDetail.error);
    return;
  }

  if (!detail?.sc) {
    regions.home.innerHTML = detailState("empty", "No SC selected", "Open an SC from the list to view the detail workspace.");
    return;
  }

  const permissions = detail.permissions ?? {};
  const sc = detail.sc;
  const pending = state.scDetail.actionPending;
  const actionError = state.scDetail.actionError
    ? `<div class="state-panel error action-error"><p>${escapeHtml(state.scDetail.actionError)}</p></div>`
    : "";
  const scContent = state.scDetail.editMode
    ? renderScEditForm(sc, pending)
    : `<div class="detail-grid">${detailFields(sc, ["sc_id", "sc_no", "requester_id", "request_type", "cost_center", "sc_amount", "service_period_start", "service_period_end", "description", "created_at", "updated_at"])}</div>`;
  regions.home.innerHTML = `
    <div class="detail-page">
      <div class="detail-page-header">
        <div>
          <p class="eyebrow">SC Detail</p>
          <h2>${escapeHtml(text(sc.sc_no ?? sc.sc_id))}</h2>
          <p>${statusBadge(sc.status)} <span class="muted-text">${escapeHtml(text(sc.request_type))}</span></p>
        </div>
        <div class="actions">
          ${state.scDetail.editMode ? "" : scActionButton("edit", "Edit", permissions.can_edit_sc, pending)}
          ${scActionButton("submit", "Submit", permissions.can_submit_sc, pending)}
          ${scActionButton("approve", "Approve", permissions.can_approve_sc, pending, true)}
          ${scActionButton("deny", "Deny", permissions.can_deny_sc, pending)}
          ${scActionButton("close", "Close", permissions.can_close_sc, pending)}
        </div>
      </div>
      ${actionError}
      <section class="detail-section sc-section">
        <div class="section-toolbar"><h3>SC</h3></div>
        ${scContent}
      </section>
      ${renderPoSection(detail, callbacks.poForm, callbacks.grForm, pending)}
      <section class="detail-section audit-section">
        <div class="section-toolbar"><h3>Audit</h3></div>
        ${simpleTable(detail.audit_logs ?? [], ["created_at", "action_type", "object_type", "object_id", "operator_id", "machine_id"])}
      </section>
    </div>
  `;

  regions.home.querySelectorAll("[data-sc-action]").forEach((button) => {
    button.addEventListener("click", async () => {
      await callbacks.onScAction?.(button.dataset.scAction);
    });
  });
  const editForm = regions.home.querySelector("[data-sc-edit-form]");
  editForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    await callbacks.onScSave?.(collectFormData(editForm.elements));
  });
  regions.home.querySelector("[data-sc-cancel-edit]")?.addEventListener("click", async () => {
    await callbacks.onScCancelEdit?.();
  });
  regions.home.querySelectorAll("[data-po-form-open]").forEach((button) => {
    button.addEventListener("click", async () => {
      await callbacks.onPoFormOpen?.(button.dataset.poFormOpen, findPo(detail, button.dataset.poId));
    });
  });
  regions.home.querySelectorAll("[data-po-action]").forEach((button) => {
    button.addEventListener("click", async () => {
      await callbacks.onPoStatusAction?.(button.dataset.poAction, findPo(detail, button.dataset.poId));
    });
  });
  const poForm = regions.home.querySelector("[data-po-form]");
  poForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    await callbacks.onPoSave?.(poForm.dataset.mode, collectFormData(poForm.elements));
  });
  regions.home.querySelector("[data-po-form-cancel]")?.addEventListener("click", async () => {
    await callbacks.onPoFormCancel?.();
  });
  regions.home.querySelectorAll("[data-gr-form-open]").forEach((button) => {
    button.addEventListener("click", async () => {
      const row = findGr(detail, button.dataset.grId);
      await callbacks.onGrFormOpen?.(button.dataset.grFormOpen, { ...row, poId: button.dataset.poId });
    });
  });
  regions.home.querySelectorAll("[data-gr-action]").forEach((button) => {
    button.addEventListener("click", async () => {
      await callbacks.onGrStatusAction?.(button.dataset.grAction, findGr(detail, button.dataset.grId));
    });
  });
  const grForm = regions.home.querySelector("[data-gr-form]");
  grForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    await callbacks.onGrSave?.(grForm.dataset.mode, collectFormData(grForm.elements));
  });
  regions.home.querySelector("[data-gr-form-cancel]")?.addEventListener("click", async () => {
    await callbacks.onGrFormCancel?.();
  });

  if (window.Alpine) {
    window.Alpine.initTree(regions.home);
  }
}

function detailState(kind, title, message) {
  return `
    <div class="detail-section">
      <div class="state-panel ${kind}">
        <div>
          <h3>${escapeHtml(title)}</h3>
          <p>${escapeHtml(message)}</p>
        </div>
      </div>
    </div>
  `;
}

function scActionButton(action, label, enabled, pending = null, primary = false) {
  if (!enabled) {
    return "";
  }
  const disabled = pending ? " disabled" : "";
  const pendingText = pending === action ? "..." : "";
  const dangerClass = action === "close" ? " danger" : "";
  const primaryClass = !dangerClass && primary ? " primary" : "";
  return `<button type="button" class="button${primaryClass}${dangerClass}" data-sc-action="${escapeHtml(action)}"${disabled}>${escapeHtml(label)}${pendingText}</button>`;
}

function renderScEditForm(sc, pending) {
  const disabled = pending ? " disabled" : "";
  return `
    <form class="sc-form" data-sc-edit-form>
      <div class="form-grid">
        ${field("sc_no", "SC No", sc.sc_no ?? "")}
        ${field("request_type", "Request Type", sc.request_type ?? "")}
        ${field("cost_center", "Cost Center", sc.cost_center ?? "")}
        ${field("sc_amount", "SC Amount", sc.sc_amount ?? "", "number")}
        ${field("service_period_start", "Service Period Start", sc.service_period_start ?? "", "date")}
        ${field("service_period_end", "Service Period End", sc.service_period_end ?? "", "date")}
        <label class="form-field full">
          <span>Description</span>
          <textarea name="description"${disabled}>${escapeHtml(text(sc.description))}</textarea>
        </label>
      </div>
      <div class="actions">
        <button type="submit" class="button primary"${disabled}>Save${pending === "save" ? "..." : ""}</button>
        <button type="button" class="button" data-sc-cancel-edit${disabled}>Cancel</button>
      </div>
    </form>
  `;
}

function renderPoSection(detail, poFormState, grFormState, pending) {
  const canManagePo = Boolean(detail.permissions?.can_manage_po);
  const canManageGr = Boolean(detail.permissions?.can_manage_gr);
  const pos = detail.pos ?? [];
  const grs = detail.grs ?? [];
  const poForm = poFormState && !poFormState.poId ? renderPoForm(detail.sc, poFormState, pending) : "";

  if (!pos.length) {
    return `
      <section class="detail-section po-section">
        <div class="section-toolbar">
          <h3>PO / GR</h3>
          ${canManagePo && !poFormState ? `<button type="button" class="button" data-po-form-open="create"${pending ? " disabled" : ""}>Add PO</button>` : ""}
        </div>
        ${poForm}
        <p class="empty-note">No PO records.</p>
      </section>
    `;
  }

  const posHtml = pos.map((po) => {
    const poGrs = grs.filter((gr) => String(gr.po_id) === String(po.po_id));
    const poId = escapeHtml(text(po.po_id));
    return `
      <div class="po-group" x-data="{ expanded: false }">
        <table class="data-table detail-table">
          <tbody>
            <tr class="status-row status-${escapeHtml(po.status)} po-parent-row" @click="expanded = !expanded">
              <td style="width: 36px;">
                <span class="po-expand-icon" :class="expanded ? 'expanded' : ''">▶</span>
              </td>
              <td>${statusBadge(po.status)}</td>
              <td>${escapeHtml(text(po.po_no ?? po.po_id))}</td>
              <td>${escapeHtml(text(po.vendor_id))}</td>
              <td class="amount">${money(po.po_amount)}</td>
              <td class="amount">${money(po.open_po_amount)}</td>
              <td>${date(po.contract_from)}</td>
              <td>${date(po.contract_to)}</td>
              <td>
                <div class="row-actions">
                  ${renderPoRowActions(po, detail, pending)}
                </div>
              </td>
            </tr>
            ${poGrs.map((gr) => `
              <tr class="status-row status-${escapeHtml(gr.status)} gr-child-row" x-show="expanded">
                <td></td>
                <td>${statusBadge(gr.status)}</td>
                <td>${escapeHtml(text(gr.gr_id))}</td>
                <td>${escapeHtml(text(gr.requester_id))}</td>
                <td class="amount">${money(gr.estimated_amount)}</td>
                <td class="amount">${money(gr.con_value)}</td>
                <td>${escapeHtml(text(gr.remark))}</td>
                <td>${date(gr.created_at)}</td>
                <td><div class="row-actions">${renderGrRowActions(gr, detail, pending)}</div></td>
              </tr>
            `).join("")}
            ${poGrs.length === 0 ? `
              <tr class="gr-child-row" x-show="expanded">
                <td></td>
                <td colspan="8"><span class="empty-note">No GRs for this PO.</span></td>
              </tr>
            ` : ""}
          </tbody>
        </table>
        ${canManageGr ? `<div style="padding: 4px 0 4px 36px;" x-show="expanded"><button type="button" class="button compact" data-gr-form-open="create" data-po-id="${poId}"${pending ? " disabled" : ""}>Add GR</button></div>` : ""}
        ${grFormState && String(grFormState.poId) === String(po.po_id) ? renderGrForm(detail, grFormState, pending, po.po_id) : ""}
      </div>
    `;
  }).join("");

  return `
    <section class="detail-section po-section">
      <div class="section-toolbar">
        <h3>PO / GR</h3>
        ${canManagePo && !poFormState ? `<button type="button" class="button" data-po-form-open="create"${pending ? " disabled" : ""}>Add PO</button>` : ""}
      </div>
      ${poForm}
      ${posHtml}
    </section>
  `;
}

function renderPoRowActions(row, detail, pending) {
  const disabled = pending ? " disabled" : "";
  const buttons = visiblePoActions(row, detail).map((action) => {
    if (action === "edit") {
      return `<button type="button" class="button compact" data-po-form-open="edit" data-po-id="${escapeHtml(row.po_id)}"${disabled}>Edit</button>`;
    }
    if (action === "approve") {
      return `<button type="button" class="button compact" data-po-action="approve" data-po-id="${escapeHtml(row.po_id)}"${disabled}>Approve${pending === `po-approve-${row.po_id}` ? "..." : ""}</button>`;
    }
    if (action === "finish") {
      return `<button type="button" class="button compact" data-po-action="finish" data-po-id="${escapeHtml(row.po_id)}"${disabled}>Finish${pending === `po-finish-${row.po_id}` ? "..." : ""}</button>`;
    }
    return "";
  });
  return buttons.join("");
}

function renderPoForm(sc, formState, pending) {
  const record = formState.record ?? {};
  const disabled = pending ? " disabled" : "";
  return `
    <form class="inline-record-form po-form" data-po-form data-mode="${escapeHtml(formState.mode)}">
      <div class="form-grid">
        ${field("sc_id", "SC ID", sc.sc_id ?? "", "hidden")}
        ${field("po_id", "PO ID", record.po_id ?? "", "text", { readonly: formState.mode === "edit", required: true })}
        ${field("vendor_id", "Vendor ID", record.vendor_id ?? "", "text", { required: true })}
        ${field("po_no", "PO No", record.po_no ?? "")}
        ${field("po_amount", "PO Amount", record.po_amount ?? "", "number")}
        ${field("contract_from", "Contract From", record.contract_from ?? "", "date")}
        ${field("contract_to", "Contract To", record.contract_to ?? "", "date")}
        ${field("contract_no", "Contract No", record.contract_no ?? "")}
        ${field("payment_frequency", "Payment Frequency", record.payment_frequency ?? "")}
      </div>
      <div class="actions">
        <button type="submit" class="button primary"${disabled}>Save${pending === "po-save" ? "..." : ""}</button>
        <button type="button" class="button" data-po-form-cancel${disabled}>Cancel</button>
      </div>
    </form>
  `;
}

function renderGrRowActions(row, detail, pending) {
  const disabled = pending ? " disabled" : "";
  const buttons = visibleGrActions(row, detail).map((action) => {
    if (action === "edit") {
      return `<button type="button" class="button compact" data-gr-form-open="edit" data-gr-id="${escapeHtml(row.gr_id)}" data-po-id="${escapeHtml(row.po_id)}"${disabled}>Edit</button>`;
    }
    if (action === "approve") {
      return `<button type="button" class="button compact" data-gr-action="approve" data-gr-id="${escapeHtml(row.gr_id)}"${disabled}>Approve${pending === `gr-approve-${row.gr_id}` ? "..." : ""}</button>`;
    }
    if (action === "cancel") {
      return `<button type="button" class="button compact" data-gr-action="cancel" data-gr-id="${escapeHtml(row.gr_id)}"${disabled}>Cancel${pending === `gr-cancel-${row.gr_id}` ? "..." : ""}</button>`;
    }
    return "";
  });
  return buttons.join("");
}

function renderGrForm(detail, formState, pending, parentPoId = null) {
  const record = formState.record ?? {};
  const poId = parentPoId ?? formState.poId ?? detail.pos?.[0]?.po_id ?? "";
  const disabled = pending ? " disabled" : "";
  return `
    <form class="inline-record-form gr-form" data-gr-form data-mode="${escapeHtml(formState.mode)}" data-po-id="${escapeHtml(poId)}">
      <div class="form-grid">
        ${field("gr_id", "GR ID", record.gr_id ?? "", "text", { readonly: formState.mode === "edit", required: true })}
        ${field("po_id", "PO ID", poId, "hidden")}
        ${field("requester_id", "Requester ID", record.requester_id ?? state.user?.user_id ?? "")}
        ${field("estimated_amount", "Estimated Amount", record.estimated_amount ?? "", "number")}
        ${field("con_value", "Con Value", record.con_value ?? "", "number")}
        <label class="form-field full">
          <span>Remark</span>
          <textarea name="remark"${disabled}>${escapeHtml(text(record.remark))}</textarea>
        </label>
      </div>
      <div class="actions">
        <button type="submit" class="button primary"${disabled}>Save${pending === "gr-save" ? "..." : ""}</button>
        <button type="button" class="button" data-gr-form-cancel${disabled}>Cancel</button>
      </div>
    </form>
  `;
}

function renderPoIdControl(pos, value) {
  if (!pos.length) {
    return field("po_id", "PO ID", value);
  }
  const options = pos.map((po) => {
    const poId = text(po.po_id);
    const label = text(po.po_no ?? po.po_id);
    return `<option value="${escapeHtml(poId)}"${poId === value ? " selected" : ""}>${escapeHtml(label)}</option>`;
  }).join("");
  return `
    <label class="form-field">
      <span>PO ID</span>
      <select name="po_id">${options}</select>
    </label>
  `;
}

function detailFields(record, keys) {
  return keys.map((key) => `
    <div class="detail-row">
      <div class="detail-label">${escapeHtml(key)}</div>
      <div class="detail-value">${formatDetailValue(key, record?.[key])}</div>
    </div>
  `).join("");
}

function formatDetailValue(key, value) {
  if (key.includes("amount") || key === "con_value") {
    return money(value);
  }
  if (key.endsWith("_at") || key.includes("period") || key.includes("contract_")) {
    return date(value);
  }
  return escapeHtml(text(value));
}

function simpleTable(rows, keys, actionsRenderer = null) {
  if (!rows.length) {
    return `<p class="empty-note">No records.</p>`;
  }
  const headers = keys.map((key) => `<th>${escapeHtml(key)}</th>`).join("") + (actionsRenderer ? "<th>actions</th>" : "");
  const body = rows.map((row) => `
    <tr>${keys.map((key) => `<td>${formatDetailValue(key, row?.[key])}</td>`).join("")}${actionsRenderer ? `<td><div class="row-actions">${actionsRenderer(row)}</div></td>` : ""}</tr>
  `).join("");
  return `
    <table class="data-table detail-table">
      <thead><tr>${headers}</tr></thead>
      <tbody>${body}</tbody>
    </table>
  `;
}

function findPo(detail, poId) {
  return (detail.pos ?? []).find((po) => String(po.po_id) === String(poId)) ?? null;
}

function findGr(detail, grId) {
  return (detail.grs ?? []).find((gr) => String(gr.gr_id) === String(grId)) ?? null;
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

export function renderCloseModal(scNo) {
  return `
    <div class="modal-overlay" id="close-modal" data-action="close-modal">
      <div class="modal-card">
        <h3>Close SC ${escapeHtml(scNo)}?</h3>
        <div class="modal-body">
          <p style="color: var(--danger); font-weight: 700;">This action cannot be undone.</p>
          <p>This SC will be permanently closed. No further PO or GR operations will be possible.</p>
          <p class="muted-text" style="margin-top: 12px;">Type <strong>I CONFIRM CLOSE THIS SC</strong> to proceed.</p>
          <input
            type="text"
            id="close-confirmation-input"
            placeholder="I CONFIRM CLOSE THIS SC"
            style="margin-top: 8px;"
            autofocus
          >
        </div>
        <div class="modal-actions">
          <button
            type="button"
            class="button danger"
            id="close-confirm-btn"
            disabled
          >Close SC</button>
          <button
            type="button"
            class="button"
            id="close-cancel-btn"
          >Cancel</button>
        </div>
      </div>
    </div>
  `;
}

export async function renderLoginScreen() {
  const loadingEl = document.getElementById("login-state-loading");
  const authorizedEl = document.getElementById("login-state-authorized");
  const unauthorizedEl = document.getElementById("login-state-unauthorized");
  const mainShell = document.getElementById("main-shell");

  try {
    const data = await callApi("current_user");
    loadingEl.hidden = true;
    document.getElementById("login-welcome-name").textContent = data.user_name;
    document.getElementById("login-welcome-role").textContent = (data.role || "") + " | " + (data.machine_id || "");
    authorizedEl.hidden = false;

    document.getElementById("login-enter-btn").addEventListener("click", () => {
      document.getElementById("login-screen").hidden = true;
      mainShell.hidden = false;
      window.__loginComplete = true;
    });
  } catch (error) {
    loadingEl.hidden = true;
    document.getElementById("login-machine-id").textContent = error.message || "Bridge unavailable";
    unauthorizedEl.hidden = false;
  }
}
