import { escapeHtml } from "./components/format.js";
import { loadCurrentUserState } from "./components/auth.js";
import { callApi } from "./components/api.js";
import {
  applyScDetailFailure,
  applyScDetailRecord,
  beginScDetailRequest,
  finishScDetailRequest,
  NAV_ITEMS,
  resolveScAction,
  runScDetailAction,
  setCurrentView,
  setScDetailTarget,
  state,
  toggleSort,
} from "./components/state.js";
import { getViewTitle, renderDetail, renderView } from "./components/views.js";

const elements = {
  nav: document.querySelector("#nav"),
  title: document.querySelector("#view-title"),
  toolbar: document.querySelector("#toolbar"),
  userPanel: document.querySelector("#user-panel"),
  searchForm: document.querySelector("#global-search-form"),
  searchInput: document.querySelector("#global-search"),
  home: document.querySelector("#home-view"),
  filters: document.querySelector("#filters"),
  table: document.querySelector("#table-region"),
  drawer: {
    root: document.querySelector("#detail-drawer"),
    title: document.querySelector("#drawer-title"),
    content: document.querySelector("#drawer-content"),
    close: document.querySelector("#drawer-close"),
  },
};

function renderNavigation() {
  elements.nav.innerHTML = NAV_ITEMS.map((item) => `
    <button type="button" class="nav-button ${item.key === state.currentView ? "active" : ""}" data-view="${escapeHtml(item.key)}">
      <span class="nav-icon">${escapeHtml(item.icon)}</span>
      <span>${escapeHtml(item.label)}</span>
    </button>
  `).join("");

  elements.nav.querySelectorAll("[data-view]").forEach((button) => {
    button.addEventListener("click", () => routeTo(button.dataset.view));
  });
}

function renderUserPanel() {
  if (state.user) {
    elements.userPanel.innerHTML = `
      <span class="auth-dot authorized"></span>
      <span>${escapeHtml(state.user.role)} | ${escapeHtml(state.user.machine_id)}</span>
    `;
    return;
  }

  if (state.userError) {
    elements.userPanel.innerHTML = `
      <span class="auth-dot denied"></span>
      <span>Unauthorized | ${escapeHtml(state.userError)}</span>
    `;
    return;
  }

  elements.userPanel.innerHTML = `
    <span class="auth-dot waiting"></span>
    <span>Checking authorization</span>
  `;
}

async function loadCurrentUser() {
  await loadCurrentUserState(state, window.pywebview?.api);
  renderUserPanel();
}

async function routeTo(viewKey) {
  if (!NAV_ITEMS.some((item) => item.key === viewKey) && viewKey !== "sc-detail" && viewKey !== "sc-new") {
    viewKey = "sc";
  }
  setCurrentView(viewKey);
  elements.title.textContent = getViewTitle(viewKey);
  elements.searchInput.value = state.globalSearch;
  elements.searchInput.disabled = viewKey === "home" || viewKey === "system" || viewKey === "sc-detail" || viewKey === "sc-new";
  elements.searchInput.placeholder = elements.searchInput.disabled ? "Search unavailable for this view" : "Search current view";
  renderNavigation();
  if (viewKey === "system") {
    await loadCurrentUser();
  }
  if (viewKey === "sc-detail") {
    await refreshScDetail();
    return;
  }
  await renderActiveView();
}

async function routeToScDetail(scId, target = {}) {
  setScDetailTarget(scId, target);
  await routeTo("sc-detail");
}

async function loadScDetail() {
  const requestedScId = state.scDetail.scId;
  if (!requestedScId) {
    state.scDetail.record = null;
    state.scDetail.loading = false;
    state.scDetail.error = null;
    return;
  }

  const requestToken = beginScDetailRequest(requestedScId);
  await renderActiveView();

  try {
    applyScDetailRecord(requestToken, requestedScId, await callApi("get_sc_detail", { sc_id: requestedScId }));
  } catch (error) {
    applyScDetailFailure(requestToken, requestedScId, error);
  } finally {
    finishScDetailRequest(requestToken, requestedScId);
  }
}

async function refreshScDetail() {
  await loadScDetail();
  await renderActiveView();
}

async function createSc(mode, data) {
  const action = mode === "submit" ? "create-submit" : "create";
  await runScDetailAction(action, async () => {
    const created = await callApi("create_sc_draft", { data });
    const scId = created.sc_id ?? data.sc_id;
    if (mode === "submit") {
      await callApi("submit_sc", { sc_id: scId, data: {} });
    }
    await routeToScDetail(scId);
  });
  await renderActiveView();
}

async function handleScAction(action) {
  const scId = state.scDetail.record?.sc?.sc_id ?? state.scDetail.scId;
  if (!scId) {
    return;
  }
  if (action === "deny" && !window.confirm("Deny this SC?")) {
    return;
  }
  if (action === "close" && !window.confirm("Close this SC?")) {
    return;
  }

  const resolved = resolveScAction(action, scId, buildScUpdateData(state.scDetail.record?.sc ?? {}));
  if (resolved.mode === "edit") {
    state.scDetail.editMode = true;
    state.scDetail.actionError = null;
    await renderActiveView();
    return;
  }
  if (resolved.mode !== "api") {
    return;
  }
  await runScDetailAction(action, async () => {
    await callApi(resolved.api, resolved.payload);
    state.scDetail.editMode = false;
    await refreshScDetail();
  });
  await renderActiveView();
}

async function handleScSave(data) {
  const scId = state.scDetail.record?.sc?.sc_id ?? state.scDetail.scId;
  if (!scId) {
    return;
  }
  const resolved = resolveScAction("save", scId, data);
  await runScDetailAction("save", async () => {
    await callApi(resolved.api, resolved.payload);
    state.scDetail.editMode = false;
    await refreshScDetail();
  });
  await renderActiveView();
}

async function handleScCancelEdit() {
  state.scDetail.editMode = false;
  state.scDetail.actionError = null;
  await renderActiveView();
}

function buildScUpdateData(sc) {
  const keys = ["sc_no", "request_type", "cost_center", "sc_amount", "service_period_start", "service_period_end", "description"];
  return Object.fromEntries(keys.filter((key) => sc[key] !== null && sc[key] !== undefined).map((key) => [key, sc[key]]));
}

async function renderActiveView() {
  await renderView(
    state.currentView,
    { home: elements.home, filters: elements.filters, table: elements.table },
    {
      onRefresh: renderActiveView,
      onNewSc: () => routeTo("sc-new"),
      onCancel: () => routeTo("sc"),
      onCreateSc: createSc,
      onScAction: handleScAction,
      onScSave: handleScSave,
      onScCancelEdit: handleScCancelEdit,
      onSort: async (viewKey, sortKey) => {
        toggleSort(viewKey, sortKey);
        await renderActiveView();
      },
      onRowClick: (row) => renderDetail(row, elements.drawer),
      onAction: (action, row) => {
        if (action !== "open-detail" || !row?.sc_id) {
          return;
        }
        if (state.currentView === "po") {
          void routeToScDetail(row.sc_id, { poId: row.po_id });
          return;
        }
        if (state.currentView === "gr") {
          void routeToScDetail(row.sc_id, { grId: row.gr_id });
          return;
        }
        void routeToScDetail(row.sc_id);
      },
    },
  );
}

elements.searchForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  state.globalSearch = elements.searchInput.value.trim();
  await renderActiveView();
});

elements.searchInput.addEventListener("search", async () => {
  state.globalSearch = elements.searchInput.value.trim();
  await renderActiveView();
});

elements.drawer.close.addEventListener("click", () => {
  elements.drawer.root.hidden = true;
});

renderNavigation();
renderUserPanel();
await loadCurrentUser();
if (state.user) {
  await routeTo("sc");
} else {
  await routeTo("system");
}
