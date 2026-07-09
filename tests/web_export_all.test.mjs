import assert from "node:assert/strict";
import { test } from "node:test";

import { fetchAllSearchRows } from "../frontend/src/utils/exportPaging.js";

test("fetchAllSearchRows forwards criteria and paginates until short batch", async () => {
  const calls = [];
  const rows = await fetchAllSearchRows(
    async (method, payload) => {
      calls.push({ method, payload });
      if (payload.offset === 0) return { rows: [{ id: 1 }, { id: 2 }] };
      return { rows: [{ id: 3 }] };
    },
    "search_vendors",
    { text: "alpha", filters: { service_scope: "IT" }, sort: "vendor_name", direction: "asc" },
    2,
  );

  assert.deepEqual(rows, [{ id: 1 }, { id: 2 }, { id: 3 }]);
  assert.deepEqual(calls.map(c => c.payload), [
    { text: "alpha", filters: { service_scope: "IT" }, sort: "vendor_name", direction: "asc", limit: 2, offset: 0 },
    { text: "alpha", filters: { service_scope: "IT" }, sort: "vendor_name", direction: "asc", limit: 2, offset: 2 },
  ]);
});
