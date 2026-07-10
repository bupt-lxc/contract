import assert from "node:assert/strict";
import { test } from "node:test";

import { sanitizeRedirectTarget } from "../frontend/src/utils/listQuery.js";

test("sanitizeRedirectTarget preserves same-app list query paths", () => {
  assert.equal(
    sanitizeRedirectTarget("/sc?status=pending&page=2&q=abc"),
    "/sc?status=pending&page=2&q=abc",
  );
});

test("sanitizeRedirectTarget rejects external URLs", () => {
  assert.equal(sanitizeRedirectTarget("https://example.com/phish"), "/workbench");
  assert.equal(sanitizeRedirectTarget("//example.com/phish"), "/workbench");
});
