import assert from "node:assert/strict";
import { test } from "node:test";

import { shouldOpenRowFromKeydown } from "../sc_gr_app/web/components/tables.js";
import { getColumnsForView } from "../sc_gr_app/web/components/views.js";

for (const viewKey of ["sc", "po", "gr"]) {
  test(`${viewKey} table puts status first and actions last`, () => {
    const columns = getColumnsForView(viewKey);

    assert.equal(columns.at(0).key, "status");
    assert.equal(columns.at(-1).key, "actions");
  });
}

function fakeTarget(tagName, closestResult = null) {
  return {
    tagName,
    closest: () => closestResult,
  };
}

for (const tagName of ["BUTTON", "INPUT", "SELECT", "TEXTAREA", "A"]) {
  test(`row keydown ignores ${tagName.toLowerCase()} targets`, () => {
    assert.equal(shouldOpenRowFromKeydown({ key: "Enter", target: fakeTarget(tagName) }), false);
  });
}

test("row keydown ignores descendants inside data-action controls", () => {
  const actionButton = { dataset: { action: "open-detail" } };

  assert.equal(shouldOpenRowFromKeydown({ key: "Enter", target: fakeTarget("SPAN", actionButton) }), false);
});

for (const key of ["Enter", " "]) {
  test(`row keydown opens normal row for ${JSON.stringify(key)}`, () => {
    assert.equal(shouldOpenRowFromKeydown({ key, target: fakeTarget("TR") }), true);
  });
}

test("row keydown ignores non-activation keys", () => {
  assert.equal(shouldOpenRowFromKeydown({ key: "Escape", target: fakeTarget("TR") }), false);
});
