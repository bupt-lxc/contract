# Email Notification Improvements

**Date:** 2026-07-04
**Status:** Approved

## Context

Three issues with the current email notification system:

1. Operational emails (status_change) jump directly to tables without a greeting line
2. Sender uses the default Outlook account instead of a designated VGC/RS POMP mailbox
3. PyInstaller `console=True` leaves a lingering OpenConsole.exe process on each scheduled task invocation

## Changes

### 1. Greeting line for operational emails

**File:** `sc_gr_app/notification/templates.py` — `build_body()`

Insert a greeting paragraph before the Notification Info table:

```
<p style="margin:0 0 16px 0">{Operator} performed {Action} on {EntityType} {shortEntityID}. Details below:</p>
```

- `Operator`: `actor_name` or "System"
- `Action`: from existing `_describe_event()`
- `EntityType`: SC / PO / GR
- `shortEntityID`: reuse `_short_entity_id()`

Monthly summary already has a greeting (`Hello {requester_name}...`) — no change needed.

### 2. Configurable sender email

**Frontend** — `frontend/src/views/SystemView.vue`:
- Add a new section (below Attachments Dir) with an input field for sender email
- Pattern matches existing attachments_dir UI: input + browse/save buttons, `app_settings` key

**Backend** — `sc_gr_app/api/bridge.py`:
- `get_sender_email` — reads `notify.sender_email` from `app_settings`
- `set_sender_email` — writes `notify.sender_email` to `app_settings`

**Notification script** — `sc_gr_app/notification/sender.py` — `send_entry()`:
- Read `notify.sender_email` from `app_settings`
- If configured, iterate `outlook.Session.Accounts` to find a matching `SmtpAddress`
- Set `mail.SendUsingAccount = account`

### 3. Remove console window from notification executable

**File:** `packaging/notification.spec` — line 40:

```
- console=True,
+ console=False,
```

Eliminates the OpenConsole.exe residual process — the notification script runs headless.
