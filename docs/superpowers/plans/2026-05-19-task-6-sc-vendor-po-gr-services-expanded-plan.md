# Task 6 SC/Vendor/PO/GR Services Expanded Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. This plan expands Task 6 from `2026-05-18-sc-gr-management-implementation-plan.md`.

**Goal:** Implement the core write services for SC, vendor, PO, and GR records with validation, RBAC, lease locks, SQLite transactions, budget checks, and audit logs.

**Architecture:** Services are plain Python functions over SQLite. Reads are lock-free; writes use `LeaseLock` and `BEGIN IMMEDIATE`. SC-affecting writes use `sc:{sc_id}`. Global vendor writes use `system`.

**Tech Stack:** Python 3.11, sqlite3, pytest, existing `AppConfig`, `LeaseLock`, `write_audit_log`, RBAC helpers, and budget service formulas.

---

## Shared Rules

- Use `uv run pytest ...` for all verification.
- Do not add an app server or ORM.
- Do not store derived `open_po_amount`.
- Do not add GR fields outside schema.
- Use `ValidationError` for missing/invalid user input, `PermissionDenied` for role failures, `NotFound` for missing rows, and `ConflictError` for business state/budget conflicts.
- Timestamps use `datetime.now(timezone.utc).isoformat()`.
- Every write calls `write_audit_log(...)` in the same SQLite transaction.
- Every write starts `BEGIN IMMEDIATE` after acquiring its lease lock.
- Use current user fields `user_id`, `role`, and `machine_id`.

## Required Files

- Create `sc_gr_app/services/sc_service.py`
- Create `sc_gr_app/services/vendor_service.py`
- Create `sc_gr_app/services/po_service.py`
- Create `sc_gr_app/services/gr_service.py`
- Create `tests/test_vendor_service.py`
- Create `tests/test_sc_po_gr_flow.py`

## Function Contracts

### `vendor_service.py`

- `create_vendor(config, current_user, data) -> dict`
  - Requires requester/admin.
  - Required fields: `vendor_id`, `vendor_name`, `service_scope`.
  - Optional fields: `ksrm_vendor_code`, `contact_person`, `phone`, `email`, `description`, `inquiry_history`.
  - Uses `LeaseLock(config.lock_dir, "system", current_user["machine_id"])`.
  - Inserts into `vendors`.
  - Audits action `create_vendor`, object `vendor`, object id vendor_id, `sc_id=None`.
  - Returns inserted row as dict.

- `search_vendors(config, text=None) -> list[dict]`
  - Lock-free read.
  - If text is provided, case-insensitive search over `vendor_name` and `ksrm_vendor_code`.
  - Order by `vendor_name asc`.

### `sc_service.py`

- `create_sc(config, current_user, data, operation_mode="normal") -> dict`
  - Requires requester/admin.
  - Required fields: `sc_id`, `requester_id`, `request_type`, `cost_center`, `sc_amount`, `service_period_start`, `service_period_end`.
  - Optional: `sc_no`, `description`, `status`.
  - Normal mode always creates `pending`, ignoring any supplied status.
  - `operation_mode == "backfill"` requires admin and may create one of `pending`, `approved`, `denied`, `closed`.
  - `sc_amount` must be positive.
  - Uses `LeaseLock(config.lock_dir, f"sc:{sc_id}", machine_id)`.
  - Inserts into `sc_records`.
  - Audits `create_sc`.

- `approve_sc(config, current_user, sc_id) -> dict`
  - Requires admin.
  - Requires existing SC status `pending`; otherwise `ConflictError`.
  - Updates status `approved`, `approved_by`, `approved_at`, `updated_at`.
  - Audits before/after as `approve_sc`.

### `po_service.py`

- `create_po(config, current_user, data) -> dict`
  - Requires requester/admin.
  - Required fields: `po_id`, `sc_id`, `vendor_id`, `po_amount`.
  - Optional: `po_no`, `status`, `contract_from`, `contract_to`, `contract_no`, `payment_frequency`.
  - Default status is `po_pending`; supported statuses are `po_pending`, `po_approved`, `finished`.
  - SC must exist and be `approved`.
  - Vendor must exist.
  - `po_amount` must be positive.
  - Existing PO total under SC plus new amount must not exceed SC amount.
  - Uses `LeaseLock(config.lock_dir, f"sc:{sc_id}", machine_id)`.
  - Inserts into `pos`.
  - Audits `create_po`.

### `gr_service.py`

- `create_gr(config, current_user, data) -> dict`
  - Requires requester/admin.
  - Required fields: `gr_id`, `po_id`, `estimated_amount`.
  - Optional: `remark`.
  - Finds PO, SC, and vendor through joins.
  - SC must be `approved`.
  - SC must have non-empty `sc_no`.
  - PO must have non-empty `po_no`.
  - PO status must be `po_approved`.
  - Estimated amount must be positive.
  - SC available amount and PO open amount must both cover `estimated_amount`.
  - Uses `LeaseLock(config.lock_dir, f"sc:{sc_id}", machine_id)`.
  - Inserts pending GR with `requester_id=current_user["user_id"]`, `created_by=current_user["user_id"]`, `con_value=None`.
  - Audits `create_gr`.

- `approve_gr(config, current_user, gr_id, con_value) -> dict`
  - Requires admin.
  - GR must exist and be `pending`.
  - `con_value` must be non-negative.
  - If `con_value > estimated_amount`, re-check SC available and PO open amount for the extra amount above the pending estimate.
  - Updates GR to `approved`, sets `con_value`, `approved_by`, `approved_at`.
  - Audits `approve_gr`.

## Minimum Tests

- `test_create_and_search_vendor` exactly covers vendor creation and text search.
- `test_sc_po_gr_happy_path` exactly covers create SC, approve SC, create vendor, create approved PO, create GR, approve GR.
- Add focused tests for:
  - requester cannot approve SC or GR.
  - PO cannot exceed SC amount.
  - GR creation requires approved SC, non-empty SC No, non-empty PO No, `po_approved`, enough SC available, and enough open PO.
  - audit rows are written for SC, vendor, PO, GR writes.

## Verification

- `uv run pytest tests/test_vendor_service.py tests/test_sc_po_gr_flow.py -q`
- `uv run pytest -q`
