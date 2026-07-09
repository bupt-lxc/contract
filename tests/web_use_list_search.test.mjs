import assert from "node:assert/strict";
import { test } from "node:test";

import { createListSearchCore } from "../frontend/src/utils/listSearchCore.js";

function config(overrides = {}) {
  return {
    apiMethod: "search_things",
    defaultSort: "created_at",
    defaultDirection: "desc",
    defaultPageSize: 10,
    allowedFilterKeys: new Set(["status", "vendor_name"]),
    allowedSortKeys: new Set(["created_at", "vendor_name"]),
    ...overrides,
  };
}

function fakeRouter() {
  const calls = [];
  return {
    calls,
    async replace(location) { calls.push(location); },
  };
}

test("initializeFromRoute parses query syncs normalized query and reloads", async () => {
  const calls = [];
  const router = fakeRouter();
  const core = createListSearchCore(config(), async (_method, payload) => {
    calls.push(payload);
    return { rows: [{ id: 1 }], total: 1 };
  });

  await core.initializeFromRoute({ query: { q: "alpha", status: "approved", page: "2", pageSize: "25", sort: "vendor_name", direction: "asc" } }, router);

  assert.equal(core.state.text, "alpha");
  assert.deepEqual(core.state.filters, { status: "approved" });
  assert.equal(calls[0].limit, 25);
  assert.equal(calls[0].offset, 25);
  assert.deepEqual(router.calls.at(-1).query, { q: "alpha", status: "approved", page: "2", pageSize: "25", sort: "vendor_name", direction: "asc" });
});

test("applyFilter resets to first page and exports matching criteria", async () => {
  const calls = [];
  const router = fakeRouter();
  const core = createListSearchCore(config(), async (_method, payload) => {
    calls.push(payload);
    return { rows: [], total: 0 };
  });

  core.state.currentPage = 4;
  await core.applyFilter({ text: "beta", filters: { status: "pending" } }, router);

  assert.equal(core.state.currentPage, 1);
  assert.equal(calls.at(-1).offset, 0);
  assert.deepEqual(core.exportCriteria(), { text: "beta", filters: { status: "pending" }, sort: "created_at", direction: "desc" });
});

test("changeSort normalizes element-plus order and ignores unsupported prop", async () => {
  const calls = [];
  const core = createListSearchCore(config(), async (_method, payload) => {
    calls.push(payload);
    return { rows: [], total: 0 };
  });

  await core.changeSort({ prop: "vendor_name", order: "ascending" });
  assert.equal(core.state.sort, "vendor_name");
  assert.equal(core.state.direction, "asc");
  await core.changeSort({ prop: "bad", order: "descending" });
  assert.equal(core.state.sort, "created_at");
  assert.equal(core.state.direction, "desc");
});

test("restoreFromRoute handles browser back forward without writing router", async () => {
  const calls = [];
  const router = fakeRouter();
  const core = createListSearchCore(config(), async (_method, payload) => {
    calls.push(payload);
    return { rows: [], total: 0 };
  });

  await core.restoreFromRoute({ query: { q: "back", page: "3", pageSize: "10" } });

  assert.equal(core.state.text, "back");
  assert.equal(core.state.currentPage, 3);
  assert.equal(calls.at(-1).offset, 20);
  assert.deepEqual(router.calls, []);
});

test("reload ignores stale slower responses", async () => {
  let resolveFirst;
  const first = new Promise(resolve => { resolveFirst = resolve; });
  let callCount = 0;
  const core = createListSearchCore(config(), async () => {
    callCount += 1;
    if (callCount === 1) return first;
    return { rows: [{ id: "second" }], total: 1 };
  });

  const slow = core.reload();
  await core.reload();
  resolveFirst({ rows: [{ id: "first" }], total: 1 });
  await slow;

  assert.deepEqual(core.state.rows, [{ id: "second" }]);
});
