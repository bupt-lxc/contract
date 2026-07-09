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
