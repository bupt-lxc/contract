import { escapeHtml } from "./components/format.js";
import { NAV_ITEMS, setCurrentView, state, toggleSort } from "./components/state.js";
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
  try {
    const api = window.pywebview?.api;
    if (!api?.current_user) {
      throw new Error("API not available: current_user");
    }
    const result = await api.current_user();
    if (!result.ok) {
      throw new Error(result.error?.message || "Unknown API error");
    }
    state.user = result.data;
    state.userError = null;
  } catch (error) {
    state.user = null;
    state.userError = error.message;
  }
  renderUserPanel();
}

async function routeTo(viewKey) {
  if (!NAV_ITEMS.some((item) => item.key === viewKey)) {
    viewKey = "sc";
  }
  setCurrentView(viewKey);
  elements.title.textContent = getViewTitle(viewKey);
  elements.searchInput.value = state.globalSearch;
  elements.searchInput.disabled = viewKey === "home" || viewKey === "system";
  elements.searchInput.placeholder = elements.searchInput.disabled ? "Search unavailable for this view" : "Search current view";
  renderNavigation();
  await renderActiveView();
}

async function renderActiveView() {
  await renderView(
    state.currentView,
    { home: elements.home, filters: elements.filters, table: elements.table },
    {
      onRefresh: renderActiveView,
      onSort: async (viewKey, sortKey) => {
        toggleSort(viewKey, sortKey);
        await renderActiveView();
      },
      onRowClick: (row) => renderDetail(row, elements.drawer),
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
await routeTo(state.user ? "sc" : "system");
