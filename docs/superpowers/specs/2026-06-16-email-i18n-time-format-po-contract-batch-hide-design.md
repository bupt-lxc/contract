# Design: Email I18n + Time Format + PO Contract Optional + Batch Button Role Hide

Date: 2026-06-16

## Summary

Four independent minor changes requested:

1. Email field labels changed from Chinese to English (matching system UI labels)
2. Email timestamp display format changed from raw ISO 8601 to readable CST (seconds precision)
3. PO "Contract NO" field changed from required to optional
4. Batch approve and batch confirm buttons hidden for requester role

## 1. Email Labels → English

**File:** `sc_gr_app/notification/templates.py`

Change all hardcoded Chinese strings to English, matching the labels used in `frontend/src/i18n/locales/en-US.js`.

### Status labels (`_STATUS_LABELS`)

| Chinese | English |
|---------|---------|
| 草稿 | Draft |
| 待审批 | Pending |
| 待经理确认 | Manager Confirm |
| 已批准 | Approved |
| 已拒绝 | Denied |
| 已关闭 | Closed |
| 已完成 | Finished |
| 已取消 | Cancelled |
| 进行中 | Activing |
| 待采购审批 | PO Pending |
| 采购已批准 | PO Approved |

### Transition labels (`_TRANSITION_LABELS`)

| Chinese | English |
|---------|---------|
| 已创建 | Created |
| 已提交 | Submitted |
| 已确认 | Confirmed |
| 已批准 | Approved |
| 已拒绝 | Denied |
| 已关闭 | Closed |
| 已完成 | Finished |
| 已取消 | Cancelled |

### SC fields (`_sc_fields`)

| Chinese label | English label |
|---------------|---------------|
| SC 编号 | SC No |
| 申请人 | Requester |
| 申请类型 | Request Type |
| 成本中心 | Cost Center |
| SC 金额 | SC Amount |
| 已消费金额 | Consumed Amount |
| 剩余可用金额 | Available Amount |
| 服务期间 | Service Period |
| 描述 | Description |
| 资产标识 | Asset |
| 资产数量 | Asset Numbers |
| 内部系统编号 | Internal System Number |
| 创建时间 | Created At |
| 更新时间 | Updated At |
| 提交时间 | Pending Date |
| 批准时间 | Approved Date |
| 关闭时间 | Closed Date |

### PO fields (`_po_fields`)

| Chinese label | English label |
|---------------|---------------|
| PO 编号 | PO No |
| 申请人 | Requester |
| 供应商 | Vendor |
| PO 金额 | PO Amount |
| 已消费金额 | Consumed Amount |
| 剩余可用金额 | Open PO Amount |
| 成本中心 | Cost Center |
| 合同编号 | Contract No |
| 合同类型 | Contract Type |
| 合同期间 | Contract Period |
| 合同POS | Contract Pos. |
| 付款频率 | Payment Frequency |
| 采购员 | Purchaser |
| 激活日期 | Activing Date |
| 创建时间 | Created At |
| 更新时间 | Updated At |

### GR fields (`_gr_fields`)

| Chinese label | English label |
|---------------|---------------|
| GR 编号 | GR No |
| 申请人 | Requester |
| 预估金额 (净价) | Estimated Amount (Net) |
| 确认金额 (含税) | Confirmed Amount (Tax incl.) |
| 增值税率(%) | VAT Rate (%) |
| 货物/服务描述 | Goods/Service Description |
| 备注 | Remark |
| 确认名称 | Confirmation Name |
| 交付期间 | Delivery Period |
| 最后交付日 | Last Delivery |
| 创建时间 | Created At |
| 提交时间 | Pending Date |
| 批准时间 | Approved Date |
| 取消时间 | Cancelled At |
| 确认时间 | Confirmed At |

### Notification info section (`build_body`)

| Chinese | English |
|---------|---------|
| 通知类型 | Notification Type |
| 实体 ID | Entity ID |
| 事件 | Event |
| 当前状态 | Current Status |
| 操作者 | Operator |
| 触发时间 | Trigger Time |
| 通知信息 | Notification Info |
| 提醒计划 | Reminder Plan |
| 详细信息 | Details |

### Child tables

PO child table (`_child_po_table`): section title, all column headers to English.
GR child table (`_child_gr_table`): section title, all column headers to English.

### Event descriptions (`_describe_event`, `_describe_schedule`)

| Chinese | English |
|---------|---------|
| 合同到期提醒：剩余不足{months}个月 | Contract Expiry: Less than {months} months remaining |
| 预算耗尽提醒：剩余不足{pct}% | Budget Exhaustion: Less than {pct}% remaining |
| 定期提醒 | Scheduled Reminder |
| 每月定期提醒 | Monthly Reminder |
| 月度定期提醒 | Monthly Weekday Reminder |
| 每周定期提醒 | Weekly Reminder |

### Subject lines (`build_subject`, `build_monthly_summary_subject`)

All Chinese in subject lines to English.

### Footer and shell

- `html lang="zh-CN"` → `html lang="en"`
- Footer text: `"此邮件由 PO Management Platform 自动发送，请勿回复。"` → `"This email is automatically sent by PO Management Platform. Please do not reply."`
- `"生成时间："` → `"Generated at: "`

### Monthly summary (`build_monthly_summary_body`)

- Title, subtitle, intro paragraph, table headers, legend text all to English
- Status labels use updated `_STATUS_LABELS`
- `"天"` → `" days"`, `"黄色"` → `"Yellow"`, `"红色"` → `"Red"`, `"您好"` → `"Hello"`

---

## 2. Time Format → Readable CST

**File:** `sc_gr_app/notification/templates.py`

### New helper: `_fmt_datetime(value)`

- Parse ISO 8601 string (handles both `2026-06-16T02:34:12.333756+00:00` and `2026-06-16T02:34:12`)
- Convert to China Standard Time (UTC+8)
- Format as `YYYY-MM-DD HH:MM:SS` (seconds precision)
- Return `"-"` if value is empty, None, or unparseable

### Apply to all timestamp fields

Replace direct value rendering for timestamp fields in:
- `_sc_fields`: `created_at`, `updated_at`, `pending_date`, `approved_date`, `closed_at`
- `_po_fields`: `created_at`, `updated_at`, `activing_date`
- `_gr_fields`: `created_at`, `pending_date`, `approved_date`, `cancelled_at`, `confirmed_at`
- `_fmt_period`: start/end values (already handles formatting, but pass through `_fmt_datetime` first)
- `build_body` trigger time row

### Note

`_fmt_period` already handles date ranges. The fields passed to it (service_period_start/end, contract_from/to, delivery_from/to) will first be individually formatted through `_fmt_datetime` before being passed to `_fmt_period`.

---

## 3. PO Contract NO → Optional

**File:** `frontend/src/components/po/PoFormDialog.vue`

### Changes

1. Line 48: Remove `prop="contract_no"` from the `<el-form-item>` — this removes Element Plus form validation on this field
2. Line 148: Remove the `contract_no` rule from the `rules` object

### Rationale

- Backend (`po_service.py`) does NOT include `contract_no` in `REQUIRED_FIELDS` — already allows empty
- Database schema has no NOT NULL constraint on `contract_no`
- The i18n key `po.contractNoRequired` can stay (may be used elsewhere or kept for future), but is now unreferenced by this component

---

## 4. Hide Batch Approve/Confirm for Requester

**Files:**
- `frontend/src/views/ScListView.vue`
- `frontend/src/views/GrListView.vue`

### Changes

In both files:
- Add a computed property: `const isAdmin = computed(() => window.__currentUser?.role === 'admin')`
- Add `&& isAdmin` to:
  - Batch Confirm button (`v-if`
- In ScListView only: add `&& isAdmin` to Batch Approve button
- Batch Submit button: **unchanged** (both admin and requester can submit)

### Rationale

- Backend RBAC already enforces admin-only for confirm/approve operations
- This change prevents requesters from seeing buttons that will only fail on the backend
- Batch Submit is allowed for both roles, so it remains visible

---

## Files Changed (4 files)

| File | Changes |
|------|---------|
| `sc_gr_app/notification/templates.py` | English labels, `_fmt_datetime` helper, apply to all timestamp fields |
| `frontend/src/components/po/PoFormDialog.vue` | Remove `prop="contract_no"` and `contract_no` rule |
| `frontend/src/views/ScListView.vue` | Add `isAdmin` check to batch confirm/approve buttons |
| `frontend/src/views/GrListView.vue` | Add `isAdmin` check to batch confirm button |
