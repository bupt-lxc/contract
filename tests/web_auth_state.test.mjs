import assert from "node:assert/strict";
import { test } from "node:test";

import { loadCurrentUserState } from "../sc_gr_app/web/components/auth.js";

test("loadCurrentUserState replaces stale unauthorized state with current user", async () => {
  const state = {
    user: null,
    userError: "This machine is not authorized",
  };
  const api = {
    current_user: async () => ({
      ok: true,
      data: {
        user_id: "U-ADMIN",
        machine_id: "V2SE7PP",
        role: "admin",
      },
    }),
  };

  await loadCurrentUserState(state, api);

  assert.equal(state.user.user_id, "U-ADMIN");
  assert.equal(state.user.machine_id, "V2SE7PP");
  assert.equal(state.user.role, "admin");
  assert.equal(state.userError, null);
});

test("loadCurrentUserState records an authorization error when current_user fails", async () => {
  const state = {
    user: {
      user_id: "U-ADMIN",
      machine_id: "V2SE7PP",
      role: "admin",
    },
    userError: null,
  };
  const api = {
    current_user: async () => ({
      ok: false,
      error: { message: "This machine is not authorized" },
    }),
  };

  await loadCurrentUserState(state, api);

  assert.equal(state.user, null);
  assert.equal(state.userError, "This machine is not authorized");
});
