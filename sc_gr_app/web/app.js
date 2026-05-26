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
import { getViewTitle, renderDetail, renderLoginScreen, renderView } from "./components/views.js";

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

const scDetailUi = {
  poForm: null,
  grForm: null,
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
  resetScDetailForms();
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

function resetScDetailForms() {
  scDetailUi.poForm = null;
  scDetailUi.grForm = null;
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
    resetScDetailForms();
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

async function openPoForm(mode, row = null) {
  state.scDetail.editMode = false;
  state.scDetail.actionError = null;
  scDetailUi.grForm = null;
  scDetailUi.poForm = { mode, record: mode === "edit" ? row ?? {} : {} };
  await renderActiveView();
}

async function savePo(mode, payload) {
  const data = { ...payload };
  if (mode === "create") {
    data.sc_id = data.sc_id ?? state.scDetail.record?.sc?.sc_id ?? state.scDetail.scId;
  }
  const poId = data.po_id;
  await runScDetailAction("po-save", async () => {
    if (mode === "edit") {
      delete data.po_id;
      delete data.sc_id;
      await callApi("update_po", { po_id: poId, data });
    } else {
      await callApi("create_po", { data });
    }
    scDetailUi.poForm = null;
    await refreshScDetail();
  });
  await renderActiveView();
}

async function handlePoStatusAction(action, row) {
  if (!row?.po_id) {
    return;
  }
  if (action === "finish" && !window.confirm("Finish this PO?")) {
    return;
  }
  const api = action === "approve" ? "approve_po" : action === "finish" ? "finish_po" : null;
  if (!api) {
    return;
  }
  await runScDetailAction(`po-${action}-${row.po_id}`, async () => {
    await callApi(api, { po_id: row.po_id });
    await refreshScDetail();
  });
  await renderActiveView();
}

async function openGrForm(mode, row = null) {
  state.scDetail.editMode = false;
  state.scDetail.actionError = null;
  scDetailUi.poForm = null;
  scDetailUi.grForm = {
    mode,
    record: mode === "edit" ? row ?? {} : {},
    poId: state.scDetail.poId ?? state.scDetail.record?.pos?.[0]?.po_id ?? null,
  };
  await renderActiveView();
}

async function saveGr(mode, payload) {
  const data = { ...payload };
  const grId = data.gr_id;
  await runScDetailAction("gr-save", async () => {
    if (mode === "edit") {
      delete data.gr_id;
      await callApi("update_gr", { gr_id: grId, data });
    } else {
      await callApi("create_gr", { data });
    }
    scDetailUi.grForm = null;
    await refreshScDetail();
  });
  await renderActiveView();
}

async function handleGrStatusAction(action, row) {
  if (!row?.gr_id) {
    return;
  }
  if (action === "cancel" && !window.confirm("Cancel this GR?")) {
    return;
  }
  if (action === "approve") {
    const defaultValue = row.con_value ?? row.estimated_amount ?? "";
    const conValue = window.prompt("Con Value", defaultValue);
    if (conValue === null || String(conValue).trim() === "") {
      return;
    }
    await runScDetailAction(`gr-approve-${row.gr_id}`, async () => {
      await callApi("approve_gr", { gr_id: row.gr_id, con_value: conValue });
      await refreshScDetail();
    });
    await renderActiveView();
    return;
  }
  if (action === "cancel") {
    await runScDetailAction(`gr-cancel-${row.gr_id}`, async () => {
      await callApi("cancel_gr", { gr_id: row.gr_id });
      await refreshScDetail();
    });
    await renderActiveView();
  }
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
      poForm: scDetailUi.poForm,
      grForm: scDetailUi.grForm,
      onPoFormOpen: openPoForm,
      onPoFormCancel: async () => {
        scDetailUi.poForm = null;
        await renderActiveView();
      },
      onPoSave: savePo,
      onPoStatusAction: handlePoStatusAction,
      onGrFormOpen: openGrForm,
      onGrFormCancel: async () => {
        scDetailUi.grForm = null;
        await renderActiveView();
      },
      onGrSave: saveGr,
      onGrStatusAction: handleGrStatusAction,
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

(async function startup() {
  // Show login screen
  renderLoginScreen();

  // Wait for user to click "Enter System"
  await new Promise((resolve) => {
    const check = () => {
      if (window.__loginComplete) {
        resolve();
      } else {
        setTimeout(check, 100);
      }
    };
    check();
  });

  // Rebuild app shell with the normal layout
  const appShell = document.querySelector(".app-shell");
  appShell.innerHTML = `
    <aside class="side-nav" aria-label="Primary navigation">
      <div class="brand-block">
        <div class="brand-mark">SG</div>
        <div>
          <div class="brand-title">SC GR</div>
          <div class="brand-subtitle">Operations</div>
        </div>
      </div>
      <nav id="nav" class="nav-list"></nav>
    </aside>
    <div class="workspace">
      <header class="top-toolbar">
        <div class="toolbar-main" id="toolbar">
          <div>
            <div class="eyebrow">Workspace</div>
            <h1 id="view-title">SC</h1>
          </div>
        </div>
        <form id="global-search-form" class="search-box" role="search">
          <label class="sr-only" for="global-search">Search current view</label>
          <input id="global-search" type="search" autocomplete="off" placeholder="Search current view">
          <button type="submit" class="button primary">Search</button>
        </form>
        <div id="user-panel" class="user-panel" aria-live="polite">
          <span class="auth-dot waiting"></span>
          <span>Checking authorization</span>
        </div>
      </header>
      <main class="content" id="main-content">
        <section id="home-view" class="view-region"></section>
        <section id="filters" class="filter-region" aria-label="Filters"></section>
        <section id="table-region" class="table-region"></section>
      </main>
    </div>
    <aside id="detail-drawer" class="detail-drawer" aria-label="Record detail" hidden>
      <div class="drawer-header">
        <div>
          <div class="eyebrow">Detail</div>
          <h2 id="drawer-title">Record</h2>
        </div>
        <button id="drawer-close" type="button" class="icon-button" aria-label="Close detail drawer">x</button>
      </div>
      <div id="drawer-content" class="drawer-content"></div>
    </aside>
  `;

  // Re-query all DOM references since the shell was rebuilt
  elements.nav = document.querySelector("#nav");
  elements.title = document.querySelector("#view-title");
  elements.toolbar = document.querySelector("#toolbar");
  elements.userPanel = document.querySelector("#user-panel");
  elements.searchForm = document.querySelector("#global-search-form");
  elements.searchInput = document.querySelector("#global-search");
  elements.home = document.querySelector("#home-view");
  elements.filters = document.querySelector("#filters");
  elements.table = document.querySelector("#table-region");
  elements.drawer.root = document.querySelector("#detail-drawer");
  elements.drawer.title = document.querySelector("#drawer-title");
  elements.drawer.content = document.querySelector("#drawer-content");
  elements.drawer.close = document.querySelector("#drawer-close");

  // Re-bind drawer close
  elements.drawer.close.addEventListener("click", () => {
    elements.drawer.root.hidden = true;
  });

  // Re-bind search events
  elements.searchForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    state.globalSearch = elements.searchInput.value.trim();
    await renderActiveView();
  });
  elements.searchInput.addEventListener("search", async () => {
    state.globalSearch = elements.searchInput.value.trim();
    await renderActiveView();
  });

  renderNavigation();
  await loadCurrentUser();
  renderUserPanel();

  if (state.user) {
    await routeTo("sc");
  } else {
    await routeTo("system");
  }
})();
