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
