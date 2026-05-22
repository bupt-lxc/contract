import assert from "node:assert/strict";
import { test } from "node:test";

import { clearScDetailTarget, setScDetailTarget, state } from "../sc_gr_app/web/components/state.js";
import { collectFormData } from "../sc_gr_app/web/components/forms.js";

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

test("collectFormData omits empty optional fields and preserves numeric strings", () => {
  const controls = [
    { name: "sc_id", value: "SC1" },
    { name: "request_type", value: "service" },
    { name: "cost_center", value: "1001" },
    { name: "description", value: "" },
  ];

  const data = collectFormData(controls);

  assert.deepEqual(data, {
    sc_id: "SC1",
    request_type: "service",
    cost_center: "1001",
  });
  assert.equal(Object.hasOwn(data, "description"), false);
});
