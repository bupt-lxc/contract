# Manager Confirm Stage — Design Spec

**Date**: 2026-06-03
**Branch**: `feat/manager-confirm`

## Overview

Insert a "Manager Confirm" stage between draft and pending for SC and GR workflows. A requester submits from draft → manager_confirm, then an admin confirms → pending. PO workflow is unchanged.

## State Machines

### SC

```
                    ┌─────────┐
                    │  draft  │
                    └────┬────┘
                         │ submit (requester)
                         ▼
                ┌──────────────────┐
                │ manager_confirm  │◄──────────────────────┐
                └───────┬──────────┘                       │
                        │ confirm (admin)                  │
                        ▼                                  │
                    ┌─────────┐                            │
                    │ pending │────────────────────────────┤
                    └────┬────┘                            │
               ┌─────────┼──────────┐                     │
               ▼         ▼          ▼                      │
          ┌────────┐ ┌──────┐  ┌────────┐                 │
          │approved│ │denied│  │ closed │                 │
          └───┬────┘ └──┬───┘  └────────┘                 │
              │          │                                 │
              ▼          │    revoke (admin/requester)     │
          ┌────────┐     │    from pending ─────────────────┘
          │ closed │     │
          └────────┘     │    re-submit (requester)
                         └─── from denied ─────────────────┘
```

### GR

```
                    ┌─────────┐
                    │  draft  │
                    └────┬────┘
                         │ submit (requester)
                         ▼
                ┌──────────────────┐
                │ manager_confirm  │◄──────────────────────┐
                └───────┬──────────┘                       │
                        │ confirm (admin)                  │
                        ▼                                  │
                    ┌─────────┐                            │
                    │ pending │────────────────────────────┤
                    └────┬────┘                            │
                    ┌────┴────┐                            │
                    ▼         ▼                            │
               ┌────────┐ ┌──────────┐                    │
               │approved│ │cancelled │                    │
               │ (终态) │ │ (终态)   │                    │
               └────────┘ └──────────┘                    │
                                                        revoke (admin)
                                                        from pending ──────────────┘
```

## Revoke Rules

| From | To | Actor |
|------|-----|-------|
| pending | manager_confirm | admin / SC owner |
| manager_confirm | draft | admin / SC owner |

## Workbench (4 columns)

```
┌──────────┬──────────────────┬──────────┬──────────┐
│  draft   │ manager_confirm  │ pending  │ approved │
└──────────┴──────────────────┴──────────┴──────────┘
```

Visibility:
- **draft**: requester only (own)
- **manager_confirm**: admin sees all / requester sees own
- **pending**: admin sees all / requester sees own
- **approved**: admin sees own / requester sees own

## Email Notifications

| Transition | To | CC |
|---|---|---|
| submit (draft → manager_confirm) | admin_recipients | requester |
| confirm (manager_confirm → pending) | requester | actor |
| revoke (pending → manager_confirm) | admin_recipients | requester |
| revoke (manager_confirm → draft) | requester | — |
| deny → re-submit (denied → manager_confirm) | admin_recipients | requester |

## Database Migration v16

- `sc_records`: add `confirmed_at TEXT`
- `gr_requests`: add `confirmed_at TEXT`
- Rebuild both tables to add `manager_confirm` to CHECK constraint

## API Changes

### New bridge methods
- `confirm_sc(sc_id)` — admin confirms SC
- `confirm_gr(gr_id)` — admin confirms GR

### Modified
- `submit_sc`: target status → `manager_confirm`
- `submit_gr`: target status → `manager_confirm`
- `revoke_sc`: pending → manager_confirm, manager_confirm → draft
- `revoke_gr`: pending → manager_confirm (new path), existing paths unchanged
