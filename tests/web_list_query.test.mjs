import assert from "node:assert/strict";
import { test } from "node:test";

import {
  RESERVED_LIST_QUERY_KEYS,
  buildQueryFromListState,
  parseListQuery,
} from "../frontend/src/utils/listQuery.js";

const config = {
  defaultSort: "created_at",
  defaultDirection: "desc",
  defaultPageSize: 10,
  allowedFilterKeys: new Set(["status", "vendor_name", "po_amount_min"]),
  allowedSortKeys: new Set(["created_at", "vendor_name"]),
};

test("parseListQuery restores valid list state and ignores reserved or unknown keys", () => {
  const state = parseListQuery(
    {
      q: "alpha",
      status: "approved",
      vendor_name: "Acme",
      po_amount_min: "1000",
      unknown: "drop-me",
      redirect: "/login",
      page: "3",
      pageSize: "25",
      sort: "vendor_name",
      direction: "asc",
    },
    config,
  );

  assert.deepEqual(state, {
    text: "alpha",
    filters: { status: "approved", vendor_name: "Acme", po_amount_min: "1000" },
    currentPage: 3,
    pageSize: 25,
    sort: "vendor_name",
    direction: "asc",
  });
});

test("parseListQuery falls back for invalid page pageSize sort and direction", () => {
  const state = parseListQuery(
    { page: "0", pageSize: "nope", sort: "bad", direction: "sideways" },
    config,
  );

  assert.equal(state.currentPage, 1);
  assert.equal(state.pageSize, 10);
  assert.equal(state.sort, "created_at");
  assert.equal(state.direction, "desc");
});

test("buildQueryFromListState omits empty values and includes filters flat", () => {
  const query = buildQueryFromListState({
    text: "alpha",
    filters: { status: "approved", vendor_name: "", po_amount_min: 1000 },
    currentPage: 2,
    pageSize: 10,
    sort: "created_at",
    direction: "desc",
  });

  assert.deepEqual(query, {
    q: "alpha",
    status: "approved",
    po_amount_min: "1000",
    page: "2",
    pageSize: "10",
    sort: "created_at",
    direction: "desc",
  });
});

test("reserved list query keys include deep-link and auth keys", () => {
  assert.equal(RESERVED_LIST_QUERY_KEYS.has("redirect"), true);
  assert.equal(RESERVED_LIST_QUERY_KEYS.has("returnTo"), true);
  assert.equal(RESERVED_LIST_QUERY_KEYS.has("highlight"), true);
  assert.equal(RESERVED_LIST_QUERY_KEYS.has("action"), true);
});
