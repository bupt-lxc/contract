# Email Notification System — Design Spec

**Date**: 2026-05-29
**Branch**: `feature/email-notification`

## Overview

Windows desktop app email notification system with two components:

1. **Status change notifications** — when SC/PO/GR transitions, writes to a queue. Desktop-side, inside existing write transactions.
2. **Threshold check notifications** — daily scan of active SCs for date/amount thresholds, computed by a dedicated script.

Email is sent via Outlook COM (win32com) from a shared company mailbox on a dedicated always-on Windows machine.

## Architecture

```
Desktop App (each user)          Notification Script (dedicated machine)
═══════════════════════           ═══════════════════════════════════════
Status change                   Every 5 min: process pending queue
  │                               Every 15 min: retry failed queue
  ▼                               Once per day: threshold check
notification_service             
  .queue_status_change() ────────►  notification_queue table (shared SQLite)
  (inside write txn)                                          │
                                                              ▼
                                                          sender.py (Outlook COM)
                                                              │
                                                              ▼
                                                         sent / failed
```

**Key principle**: The desktop app never sends email. It only writes to the queue. The notification script on the dedicated machine is the sole sender.

## Database Schema (v3 migration)

### `notification_queue`

| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | autoincrement |
| entity_type | TEXT NOT NULL | 'sc' / 'po' / 'gr' |
| entity_id | TEXT NOT NULL | |
| event_type | TEXT NOT NULL | 'status_change' / 'threshold_date' / 'threshold_amount' |
| event_key | TEXT NOT NULL | 'submit', 'threshold_date:6m', 'threshold_amount:50%' |
| to_recipients | TEXT NOT NULL | JSON array of user IDs |
| cc_recipients | TEXT NOT NULL | JSON array of user IDs |
| created_at | TEXT NOT NULL | ISO timestamp |
| sent_at | TEXT | nullable ISO timestamp |
| status | TEXT NOT NULL DEFAULT 'pending' | 'pending' / 'sent' / 'failed' |
| error_msg | TEXT | nullable |

UNIQUE(entity_type, entity_id, event_key, status) — prevents duplicate pending entries for the same event.

### `notification_config`

Per-entity notification strategy (primarily per-SC):

| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| entity_type | TEXT NOT NULL DEFAULT 'sc' | |
| entity_id | TEXT NOT NULL | |
| enabled | INTEGER NOT NULL DEFAULT 1 | |
| cc_user_ids | TEXT NOT NULL DEFAULT '[]' | JSON array |
| date_thresholds | TEXT NOT NULL DEFAULT '[]' | JSON array of months, e.g. `[6, 3, 1, 0.5]` |
| amount_thresholds | TEXT NOT NULL DEFAULT '[]' | JSON array of remaining %, e.g. `[50, 30, 10]` |

UNIQUE(entity_type, entity_id)

### `notification_sent_threshold`

Dedup tracker for threshold events (each threshold fires only once per SC):

| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| entity_type | TEXT NOT NULL | |
| entity_id | TEXT NOT NULL | |
| event_key | TEXT NOT NULL | 'threshold_date:6m' |
| sent_at | TEXT NOT NULL | |

UNIQUE(entity_type, entity_id, event_key)

### `app_settings` new keys

| Key | Value example |
|---|---|
| `notify.transitions.sc` | `{"submit":{"to":["admin"],"cc":["requester"]},"approve":{"to":["requester"],"cc":["admin"]},"deny":{"to":["requester"],"cc":["admin"]},"close":{"to":["requester"],"cc":["admin"]}}` |
| `notify.transitions.po` | same structure |
| `notify.transitions.gr` | same structure |
| `notify.default_cc` | `[]` (JSON array of user IDs) |
| `notify.default_date_thresholds` | `[6, 3, 1, 0.5]` |
| `notify.default_amount_thresholds` | `[50, 30, 10]` |

## Recipient Rules

### Status change recipients

| Entity | Transition | To | CC |
|---|---|---|---|
| SC | submit | admin users | CC list + requester |
| SC | approve | requester | CC list + approving admin |
| SC | deny | requester | CC list + denying admin |
| SC | close | requester, admin users | CC list |
| PO | submit | admin users | CC list + requester |
| PO | approve | requester | CC list + approving admin |
| PO | deny | requester | CC list |
| GR | submit | admin users | CC list + requester |
| GR | approve | requester | CC list + approving user |
| GR | cancel | requester, admin users | CC list |

### Threshold notification recipients

- To: requester + admin users
- CC: per-SC CC list + default CC list

### Resolution rules

- `admin` → all users with role='admin'
- `requester` → the entity's requester_id field
- `approving admin` → the user who performed the approve/deny action
- User IDs → email addresses from `users` table

Recipient rules are stored as JSON in `app_settings` and editable from the UI.

## Event Flows

### Flow 1: Status Change (desktop app)

```
User clicks "Submit SC"
  → sc_service.submit_sc()  [BEGIN IMMEDIATE]
    → business validation + write
    → notification_service.queue_status_change()
      → lookup transition rules from app_settings
      → lookup per-SC notification_config (CC list)
      → resolve to/cc user IDs
      → INSERT into notification_queue (status='pending')
    → write_audit_log()
  → COMMIT  (on failure: retry up to 3x with backoff 1s/2s/4s, then ROLLBACK)
```

The queue write is **transactional** — if it fails after 3 retries, the entire transaction rolls back and the user sees an error. Notifications are never silently dropped.

### Flow 2: Threshold Check (script, daily)

```
For each SC where status='approved':
  │
  ├── Date check:
  │     remaining_days = service_period_end - today
  │     thresholds = per-SC config.date_thresholds OR default_date_thresholds
  │     For each threshold (descending):
  │       If remaining_days < threshold * 30:
  │         If (entity_id, 'threshold_date:Nm') NOT IN notification_sent_threshold:
  │           INSERT into notification_queue (status='pending')
  │           INSERT into notification_sent_threshold
  │
  ├── Amount check:
  │     spent = SUM(approved GR con_value)
  │     remaining_pct = (sc_amount - spent) / sc_amount * 100
  │     thresholds = per-SC config.amount_thresholds OR default_amount_thresholds
  │     For each threshold (descending):
  │       If remaining_pct < threshold:
  │         If (entity_id, 'threshold_amount:N%') NOT IN notification_sent_threshold:
  │           INSERT into notification_queue
  │           INSERT into notification_sent_threshold
```

Thresholds are processed in descending order. Only the tightest unmet threshold fires (progressive descreasing).

### Flow 3: Script Send Loop

```
Every 5 minutes:
  SELECT * FROM notification_queue WHERE status='pending'
  For each entry:
    resolve user IDs → email addresses
    send_email(to, cc, subject, body)
    success → status='sent', sent_at=now
    failure → status='failed', error_msg=exception

Every 15 minutes:
  SELECT * FROM notification_queue WHERE status='failed'
  For each entry: retry sending
    success → status='sent', sent_at=now
    failure → status stays 'failed', update error_msg
```

No permanent failure. Failed entries are retried every 15 minutes indefinitely.

## Script Structure

```
sc_gr_app/notification/
  __init__.py
  __main__.py       # CLI: --poll-interval, --run-once, --thresholds-only
  engine.py         # Poll loop: process pending every 5min, retry failed every 15min, thresholds daily
  sender.py         # win32com Outlook: create/send MailItem
  queue.py          # Read/write notification_queue (shared with desktop's notification_service)
  thresholds.py     # Daily threshold check for all active SCs
  config.py         # Read notification_config + app_settings, merge with defaults
  templates.py      # Email subject + HTML body (Chinese)
```

Dependencies on existing code:
- `sc_gr_app/db/connection.py` — `connect()`
- `sc_gr_app/config.py` — `AppConfig`
- `sc_gr_app/services/budget_service.py` — amount remaining computation

Entry point: `uv run python -m sc_gr_app.notification`

## API Endpoints (bridge.py)

| Method | Payload | Returns | Notes |
|---|---|---|---|
| `get_sc_notification_config` | `{sc_id}` | config or null | Falls back to defaults if null |
| `save_sc_notification_config` | `{sc_id, enabled, cc_user_ids, date_thresholds, amount_thresholds}` | `{ok: true}` | Upsert. Requires SC ownership or admin |
| `get_notification_defaults` | `{}` | defaults object | Admin only |
| `save_notification_defaults` | `{transitions, default_cc, date_thresholds, amount_thresholds}` | `{ok: true}` | Admin only |
| `list_notification_queue` | `{sc_id?, status?, limit?, offset?}` | `{items, total}` | View sent/failed history |

## UI Design

### SC Detail View — Notification Card

New collapsible card below Audit Log in `ScDetailView.vue`:

- Enable/disable toggle
- CC list: multi-select user picker
- Date thresholds: checkboxes (6m, 3m, 1m, 2w)
- Amount thresholds: checkboxes (50%, 30%, 10%)
- If no per-SC config saved, defaults from system settings apply

### System Settings — Notification Defaults Card

New card in `SystemView.vue` (admin only):

- Transition rules table: for each transition (submit/approve/deny/close), configure To and CC role selections
- Default CC list: multi-select user picker
- Default date thresholds: checkboxes
- Default amount thresholds: checkboxes

Uses existing Element Plus components (`el-card`, `el-checkbox`, `el-select`, `el-table`).

## Testing

### `tests/test_notification_service.py`
- Queue write with correct to/cc/event_key/status
- Per-SC config CC merge with transition rules
- Fallback to defaults when no per-SC config
- CRUD for sc_config and notification_defaults
- Transaction rollback on queue write failure after 3 retries
- Atomic: SC submit commits both SC and queue entry or neither

### `tests/test_notification_thresholds.py`
- Date threshold fires when below, skips when above
- Date threshold skip when already in sent_threshold
- Amount threshold fires when below, skips when above
- Progressive thresholds: only tightest unmet fires
- Disabled config skips all checks
- Falls back to defaults when no per-SC config
- 2-week (0.5 month) threshold correctness

### `tests/test_notification_sender.py`
- Resolve user IDs to emails, handle missing users
- Subject/body generation (Chinese)
- Send success via mocked Outlook
- Send failure marks queue as failed
- Retry picks up failed entries

All tests use `app_config` fixture (isolated SQLite per test). Only Outlook COM is mocked.

## Deployment

| Component | Runs on | How |
|---|---|---|
| Desktop app (queue writer) | Each user's PC | Normal pywebview app |
| Notification script | Dedicated Windows machine | Windows Task Scheduler: at startup, repeat every 5 min |
| Shared DB | Network drive | Both access via `SC_GR_DATA_DIR` |

Prerequisites on the dedicated machine:
- Python 3.11 + `uv`
- Outlook installed with shared company mailbox configured
- Network access to shared database folder
- `SC_GR_DATA_DIR` environment variable set

Task Scheduler action: `uv run python -m sc_gr_app.notification`
