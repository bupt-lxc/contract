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
}

export function clearScDetailTarget() {
  state.scDetail.scId = null;
  state.scDetail.poId = null;
  state.scDetail.grId = null;
  state.scDetail.record = null;
  state.scDetail.loading = false;
  state.scDetail.error = null;
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
