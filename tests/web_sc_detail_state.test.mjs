import assert from "node:assert/strict";
import { test } from "node:test";

import { clearScDetailTarget, setScDetailTarget, state } from "../sc_gr_app/web/components/state.js";

test("setScDetailTarget keeps SC context and switches between PO and GR targets", () => {
  clearScDetailTarget();

  setScDetailTarget("SC1", { poId: "PO1" });

  assert.equal(state.scDetail.scId, "SC1");
  assert.equal(state.scDetail.poId, "PO1");
  assert.equal(state.scDetail.grId, null);

  setScDetailTarget("SC1", { grId: "GR1" });

  assert.equal(state.scDetail.scId, "SC1");
  assert.equal(state.scDetail.poId, null);
  assert.equal(state.scDetail.grId, "GR1");
});

test("clearScDetailTarget resets target, record, loading, and error", () => {
  setScDetailTarget("SC1", { poId: "PO1" });
  state.scDetail.record = { sc_id: "SC1" };
  state.scDetail.loading = true;
  state.scDetail.error = "failed";

  clearScDetailTarget();

  assert.deepEqual(state.scDetail, {
    scId: null,
    poId: null,
    grId: null,
    record: null,
    loading: false,
    error: null,
  });
});
