import assert from "node:assert/strict";
import { test } from "node:test";

import {
  addDeadlineShortcut,
  formatLocalDate,
  getDeadlineRange,
} from "../frontend/src/utils/date.js";

test("formatLocalDate uses local date parts instead of UTC ISO slicing", () => {
  const date = new Date(2026, 6, 9, 0, 30, 0);
  assert.equal(formatLocalDate(date), "2026-07-09");
});

test("addDeadlineShortcut supports month and year shortcuts", () => {
  const base = new Date(2026, 0, 31, 12, 0, 0);

  assert.equal(formatLocalDate(addDeadlineShortcut(base, "1m")), "2026-02-28");
  assert.equal(formatLocalDate(addDeadlineShortcut(base, "1y")), "2027-01-31");
});

test("getDeadlineRange returns inclusive local date strings", () => {
  const base = new Date(2026, 6, 9, 8, 0, 0);

  assert.deepEqual(getDeadlineRange("3m", base), {
    deadline_from: "2026-07-09",
    deadline_to: "2026-10-09",
  });
});

test("getDeadlineRange returns empty object for unsupported shortcut", () => {
  assert.deepEqual(getDeadlineRange("bad", new Date(2026, 6, 9)), {});
});
