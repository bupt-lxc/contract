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
