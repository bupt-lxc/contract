export const NAV_ITEMS = [
  { key: "home", label: "Home", icon: "H" },
  { key: "sc", label: "SC", icon: "S" },
  { key: "vendor", label: "Vendor", icon: "V" },
  { key: "po", label: "PO", icon: "P" },
  { key: "gr", label: "GR", icon: "G" },
  { key: "logs", label: "Logs", icon: "L" },
  { key: "system", label: "System", icon: "Y" },
];

export const state = {
  currentView: "sc",
  user: null,
  userError: null,
  globalSearch: "",
  scDetail: {
    scId: null,
    poId: null,
    grId: null,
    record: null,
    loading: false,
    error: null,
    actionPending: null,
    actionError: null,
    editMode: false,
  },
  views: {
    sc: { rows: [], loading: false, error: null, sort: "created_at", direction: "desc", filters: {} },
    vendor: { rows: [], loading: false, error: null, sort: "vendor_name", direction: "asc", filters: {} },
    po: { rows: [], loading: false, error: null, sort: "created_at", direction: "desc", filters: {} },
    gr: { rows: [], loading: false, error: null, sort: "created_at", direction: "desc", filters: {} },
    logs: { rows: [], loading: false, error: null, sort: "created_at", direction: "desc", filters: {} },
  },
};

export function getViewState(viewKey) {
  return state.views[viewKey];
}

export function setCurrentView(viewKey) {
  state.currentView = viewKey;
}

export function setScDetailTarget(scId, target = {}) {
  state.scDetail.scId = scId;
  state.scDetail.poId = target.poId ?? null;
  state.scDetail.grId = target.grId ?? null;
  state.scDetail.record = null;
  state.scDetail.loading = false;
  state.scDetail.error = null;
  state.scDetail.actionPending = null;
  state.scDetail.actionError = null;
  state.scDetail.editMode = false;
}

export function clearScDetailTarget() {
  state.scDetail.scId = null;
  state.scDetail.poId = null;
  state.scDetail.grId = null;
  state.scDetail.record = null;
  state.scDetail.loading = false;
  state.scDetail.error = null;
  state.scDetail.actionPending = null;
  state.scDetail.actionError = null;
  state.scDetail.editMode = false;
}

let scDetailRequestToken = 0;

export function beginScDetailRequest(scId) {
  const token = ++scDetailRequestToken;
  state.scDetail.loading = Boolean(scId);
  state.scDetail.error = null;
  state.scDetail.record = null;
  return token;
}

export function isCurrentScDetailRequest(token, scId) {
  return token === scDetailRequestToken && state.scDetail.scId === scId;
}

export function applyScDetailRecord(token, scId, record) {
  if (!isCurrentScDetailRequest(token, scId)) {
    return false;
  }
  state.scDetail.record = record;
  state.scDetail.error = null;
  state.scDetail.loading = false;
  return true;
}

export function applyScDetailFailure(token, scId, error) {
  if (!isCurrentScDetailRequest(token, scId)) {
    return false;
  }
  state.scDetail.record = null;
  state.scDetail.error = error?.message ?? String(error);
  state.scDetail.loading = false;
  return true;
}

export function finishScDetailRequest(token, scId) {
  if (!isCurrentScDetailRequest(token, scId)) {
    return false;
  }
  state.scDetail.loading = false;
  return true;
}

export async function runScDetailAction(action, operation) {
  if (state.scDetail.actionPending) {
    return false;
  }
  state.scDetail.actionPending = action;
  state.scDetail.actionError = null;
  try {
    await operation();
    return true;
  } catch (error) {
    state.scDetail.actionError = error?.message ?? String(error);
    return false;
  } finally {
    state.scDetail.actionPending = null;
  }
}

export function resolveScAction(action, scId, data = {}) {
  if (action === "edit") {
    return { mode: "edit" };
  }
  if (action === "save") {
    return { mode: "api", api: "update_sc", payload: { sc_id: scId, data } };
  }
  if (action === "submit") {
    return { mode: "api", api: "submit_sc", payload: { sc_id: scId, data: {} } };
  }
  if (action === "approve") {
    return { mode: "api", api: "approve_sc", payload: { sc_id: scId } };
  }
  if (action === "deny") {
    return { mode: "api", api: "deny_sc", payload: { sc_id: scId } };
  }
  if (action === "close") {
    return { mode: "api", api: "close_sc", payload: { sc_id: scId } };
  }
  return { mode: "noop" };
}

export function toggleSort(viewKey, sortKey) {
  const viewState = getViewState(viewKey);
  if (viewState.sort === sortKey) {
    viewState.direction = viewState.direction === "asc" ? "desc" : "asc";
    return;
  }
  viewState.sort = sortKey;
  viewState.direction = "asc";
}

export function setFilter(viewKey, name, value) {
  const viewState = getViewState(viewKey);
  if (value === null || value === undefined || value === "") {
    delete viewState.filters[name];
    return;
  }
  viewState.filters[name] = value;
}

export function resetFilters(viewKey) {
  getViewState(viewKey).filters = {};
}
