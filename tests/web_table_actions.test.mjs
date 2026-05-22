import assert from "node:assert/strict";
import { test } from "node:test";

import { getColumnsForView } from "../sc_gr_app/web/components/views.js";

for (const viewKey of ["sc", "po", "gr"]) {
  test(`${viewKey} table puts status first and actions last`, () => {
    const columns = getColumnsForView(viewKey);

    assert.equal(columns.at(0).key, "status");
    assert.equal(columns.at(-1).key, "actions");
  });
}
