import assert from "node:assert/strict";
import { test } from "node:test";

import {
  visibleGrActions,
  visibleDetailActions,
  visiblePoActions,
} from "../sc_gr_app/web/components/views.js";

import {
  applyScDetailFailure,
  applyScDetailRecord,
  beginScDetailRequest,
  clearScDetailTarget,
  resolveScAction,
  runScDetailAction,
  setScDetailTarget,
  state,
} from "../sc_gr_app/web/components/state.js";
import { collectFormData } from "../sc_gr_app/web/components/forms.js";

test("visibleDetailActions includes PO and GR management actions from permissions", () => {
  const actions = visibleDetailActions({
    permissions: {
      can_manage_po: true,
      can_manage_gr: true,
      can_approve_sc: false,
      can_close_sc: true,
    },
  });

  assert.deepEqual(actions, ["close-sc", "add-po", "add-gr"]);
  assert.equal(actions.includes("add-po"), true);
  assert.equal(actions.includes("add-gr"), true);
  assert.equal(actions.includes("close-sc"), true);
  assert.equal(actions.includes("approve-sc"), false);
});

test("visiblePoActions hides PO status actions without PO management permission", () => {
  const detail = { permissions: { can_manage_po: false } };

  assert.deepEqual(visiblePoActions({ po_id: "PO1", status: "po_pending" }, detail), []);
  assert.deepEqual(visiblePoActions({ po_id: "PO1", status: "po_approved" }, detail), []);
});

test("visiblePoActions shows PO row actions only when status and permission match", () => {
  const detail = { permissions: { can_manage_po: true } };

  assert.deepEqual(visiblePoActions({ po_id: "PO1", status: "po_pending" }, detail), ["edit", "approve"]);
  assert.deepEqual(visiblePoActions({ po_id: "PO1", status: "po_approved" }, detail), ["edit", "finish"]);
  assert.deepEqual(visiblePoActions({ po_id: "PO1", status: "finished" }, detail), ["edit"]);
});

test("visibleGrActions hides GR status actions without GR management permission", () => {
  const detail = { permissions: { can_manage_gr: false } };

  assert.deepEqual(visibleGrActions({ gr_id: "GR1", status: "pending" }, detail), []);
});

test("visibleGrActions shows GR row actions only when status and permission match", () => {
  const detail = { permissions: { can_manage_gr: true } };

  assert.deepEqual(visibleGrActions({ gr_id: "GR1", status: "pending" }, detail), ["edit", "approve", "cancel"]);
  assert.deepEqual(visibleGrActions({ gr_id: "GR1", status: "approved" }, detail), ["edit"]);
});

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
    actionPending: null,
    actionError: null,
    editMode: false,
  });
});

test("stale SC detail responses are ignored when the target or token changes", () => {
  clearScDetailTarget();
  setScDetailTarget("SC1");
  const staleByTarget = beginScDetailRequest(state.scDetail.scId);

  setScDetailTarget("SC2");

  assert.equal(applyScDetailRecord(staleByTarget, "SC1", { sc: { sc_id: "SC1" } }), false);
  assert.equal(state.scDetail.record, null);

  const staleByToken = beginScDetailRequest("SC2");
  const currentToken = beginScDetailRequest("SC2");

  assert.equal(applyScDetailFailure(staleByToken, "SC2", new Error("slow failed")), false);
  assert.equal(state.scDetail.error, null);
  assert.equal(state.scDetail.loading, true);

  assert.equal(applyScDetailRecord(currentToken, "SC2", { sc: { sc_id: "SC2" } }), true);
  assert.deepEqual(state.scDetail.record, { sc: { sc_id: "SC2" } });
  assert.equal(state.scDetail.loading, false);
});

test("runScDetailAction captures errors, records actionError, and clears pending", async () => {
  clearScDetailTarget();
  setScDetailTarget("SC1");

  await runScDetailAction("submit", async () => {
    throw new Error("bridge unavailable");
  }).catch(() => undefined);

  assert.equal(state.scDetail.actionPending, null);
  assert.equal(state.scDetail.actionError, "bridge unavailable");
});

test("resolveScAction does not map edit to update_sc before save", () => {
  assert.deepEqual(resolveScAction("edit", "SC1"), { mode: "edit" });
  assert.deepEqual(resolveScAction("save", "SC1", { description: "updated" }), {
    mode: "api",
    api: "update_sc",
    payload: { sc_id: "SC1", data: { description: "updated" } },
  });
  assert.deepEqual(resolveScAction("submit", "SC1"), {
    mode: "api",
    api: "submit_sc",
    payload: { sc_id: "SC1", data: {} },
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
