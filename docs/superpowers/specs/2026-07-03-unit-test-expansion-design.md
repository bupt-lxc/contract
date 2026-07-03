# Unit Test Expansion: sc_service & gr_service

**Date:** 2026-07-03
**Status:** approved

## Context

The project has 398 tests across 26 test files. Two core service files — `sc_service.py` (1,360 lines) and `gr_service.py` (1,070 lines) — have zero dedicated unit tests, representing ~2,430 lines of untested business logic.

## Goal

Add comprehensive unit tests for `sc_service.py` and `gr_service.py` following the existing project test pattern (real SQLite via `tmp_path`, seed data through service calls, assert return values and database state).

## Test Pattern

All tests follow this established convention:

```python
import pytest
from sc_gr_app.db.connection import connect
from sc_gr_app.db.migrations import migrate
from sc_gr_app.errors import ConflictError, NotFound, ValidationError
from sc_gr_app.services.user_service import seed_users

class TestSomething:
    def test_case(self, app_config):
        migrate(app_config)
        seed_users(app_config)
        # call service functions, assert results or pytest.raises
```

## Files to Create

### `tests/test_sc_service.py` (~40-50 tests)

| Class | Functions covered | Test count |
|---|---|---|
| `TestScCreate` | `create_sc`, `create_sc_draft` — required fields, request_type validation, currency validation, backfill mode, FC top-level creation | ~8 |
| `TestScSubmit` | `submit_sc` — draft→manager_confirm, business field enforcement, call-off budget revalidation, vendor_ids sync | ~5 |
| `TestScConfirm` | `confirm_sc` — manager_confirm→pending, non-admin guard, status guard | ~4 |
| `TestScApprove` | `approve_sc` — pending→approved, amount-not-below-usage, FC SC guard | ~4 |
| `TestScUpdate` | `update_sc` — field changes, amount floor check, vendor sync, calloff_po_id immutability, draft-vs-non-draft rules | ~6 |
| `TestScDeny` | `deny_sc` — status guard, state change | ~3 |
| `TestScFinish` | `finish_sc` — approved→finished, cascade finish POs, FC blocker when call-offs exist | ~4 |
| `TestScRecall` | `recall_sc` — finished→approved, active POs blocker | ~3 |
| `TestScDelete` | `delete_sc` — draft-only guard, admin-only, cascade | ~3 |
| `TestScTransfer` | `transfer_sc` — requester reassignment, permission check | ~3 |
| `TestScVendors` | `add_sc_vendor`, `remove_sc_vendor` — link/unlink, duplicate prevention, non-existent vendor, re-remove guard | ~5 |
| `TestScDetail` | `get_sc_detail` — vendors embedded, call-off parent context, status-based permissions | ~3 |
| `TestScCallOff` | `_validate_calloff_po` — consolidated from `test_sc_service_calloff.py` | ~3 |

### `tests/test_gr_service.py` (~35-45 tests)

| Class | Functions covered | Test count |
|---|---|---|
| `TestGrCreate` | `create_gr` — required fields, PO context validation, FC PO rejection, permission check, draft-vs-pending status derivation | ~8 |
| `TestGrSubmit` | `submit_gr` — draft→pending, status guard, cascade draft submit | ~4 |
| `TestGrConfirm` | `confirm_gr` — manager_confirm flow, status guard | ~3 |
| `TestGrApprove` | `approve_gr` — pending→approved, tax calculation, null con_value guard, cascade approve, SC/PO budget check on approve | ~8 |
| `TestGrUpdate` | `update_gr` — estimated_amount, con_value, tax_recalculation, status guards | ~6 |
| `TestGrDeny` | `deny_gr` — pending→denied, state change | ~3 |
| `TestGrFinish` | `finish_gr` — approved→finished | ~3 |
| `TestGrRecall` | `recall_gr` — finished→approved, guard conditions | ~3 |
| `TestGrDelete` | `delete_gr` — draft-only, admin-only | ~3 |
| `TestGrValidation` | `_validate_gr_creation_context` — draft-PO-draft-SC path, active-PO-approved-SC path, budget checks, edge cases | ~5 |

## Files to Modify

- **`conftest.py`** — add `seeded_config` fixture (migrate + seed_users) to reduce boilerplate
- **`test_sc_service_calloff.py`** — delete, tests absorbed into `test_sc_service.py`

## Out of Scope

- `app_shell.py` — desktop shell, requires pywebview runtime
- `notification/sender.py` — already covered by `test_notification_service.py`
- `notification/__main__.py` — CLI entry point
- All existing test files remain unchanged

## Existing Test Gaps (Quick Scan)

Quick scan of the 3 most critical existing test files revealed blind spots:

### `test_po_service.py` (10 tests → ~15-20 missing)

`po_service.py` has 6 public functions. Current tests only cover FC guard paths:

| Function | Currently tested? | What's missing |
|---|---|---|
| `create_po` | Not directly | Required fields, non-positive amount, non-existent SC, SC status→PO status derivation |
| `submit_po` | No unit test | Draft→active transition, permission check, cascade submit |
| `update_po` | 3 tests (vendor, amount floor) | Status guards (can't update finished/recalled), field updates (po_no, contract), non-FC amount floor |
| `finish_po` | FC guard only (3 tests) | Regular PO finish: permission, status guard, cascade |
| `recall_po` | FC guard only (2 tests) | Regular PO recall: finished→active, non-admin guard |
| `delete_po` | FC guard only (1 test) | Regular PO delete: draft-only, admin-only, GR existence check |

### `test_budget_service.py` (25 tests → ~3-4 missing)

| Gap | Detail |
|---|---|
| `manager_confirm` GRs | Only pending + approved GRs tested; manager_confirm should also count toward pending totals |
| Draft/finished GR exclusion | No explicit test confirming draft/finished GRs don't affect budget |
| Empty DB for decimal variants | `compute_sc_budget_decimal` and `compute_po_budget_decimal` not tested with empty database |

### `test_fc_calloff_flow.py` (5 tests → ~2-3 missing)

| Gap | Detail |
|---|---|
| Mixed call-off statuses | Multiple call-off SCs with one denied, one approved — denied should not consume budget |
| Denied call-off budget exclusion | No test confirming denied call-off SC releases budget back |

## Files to Modify

- **`conftest.py`** — add `seeded_config` fixture (migrate + seed_users) to reduce boilerplate
- **`test_po_service.py`** — add `TestPoCreate`, `TestPoSubmit`, extend `TestPoFcGuards` with regular PO paths
- **`test_budget_service.py`** — add manager_confirm GR test, draft/finished exclusion test, empty DB decimal test
- **`test_fc_calloff_flow.py`** — add mixed-status call-off budget test, denied call-off exclusion test
- **`test_sc_service_calloff.py`** — delete, tests absorbed into `test_sc_service.py`

## Revised Estimate

| Category | Tests |
|---|---|
| New: `test_sc_service.py` | ~40-50 |
| New: `test_gr_service.py` | ~35-45 |
| Patch: `test_po_service.py` | ~15-20 |
| Patch: `test_budget_service.py` | ~3-4 |
| Patch: `test_fc_calloff_flow.py` | ~2-3 |
| **Total** | **~95-122** |

## Constraints

- No mocking — real SQLite database via `tmp_path`
- Seed data through service function calls (not raw SQL INSERTs)
- Follow existing class-per-operation-group organization
- Single `conftest.py` fixture addition only
