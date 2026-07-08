# Cancellation GR 设计

**Date:** 2026-07-08
**Branch:** feat/independent-fc-po

## 概述

新增一种 GR 类型 — Cancellation GR（取消/退款类 GR），用于记录厂家退还部分款项的场景。与普通 GR 流程一致，但金额必须为负数，并由 `is_cancellation` 字段标识。

---

## 1. 数据库 (migration v37)

### 1.1 新增字段

```sql
ALTER TABLE gr_requests ADD COLUMN is_cancellation TEXT NOT NULL DEFAULT 'N'
  CHECK (is_cancellation IN ('N', 'Y'));
```

### 1.2 修改金额约束

重建 `gr_requests` 表，将原来的单体 CHECK 改为区分类型的复合 CHECK：

```sql
-- 旧约束
CHECK (estimated_amount > 0)
CHECK (con_value >= 0)

-- 新约束
CHECK (
  (is_cancellation = 'N' AND estimated_amount > 0 AND con_value >= 0) OR
  (is_cancellation = 'Y' AND estimated_amount < 0 AND con_value <= 0)
)
```

`gross_cost` 不加 CHECK —— 它是计算字段，符号自然跟随 `estimated_amount`。

---

## 2. Backend — gr_service.py

### 2.1 新增校验函数

```python
def _negative_number(value, field: str) -> Decimal:
    """金额必须为负数 (用于 Cancellation GR)"""
    number = Decimal(str(value))
    if not number.is_finite() or number >= 0:
        raise ValidationError(f"{field} must be negative")
    return number

def _non_positive_number(value, field: str) -> Decimal:
    """金额必须 <= 0 (用于 Cancellation GR 的 con_value)"""
    number = Decimal(str(value))
    if not number.is_finite() or number > 0:
        raise ValidationError(f"{field} must be non-positive")
    return number
```

### 2.2 create_gr()

| 位置 | 变更 |
|------|------|
| `estimated_amount` 校验 | 根据 `data.get("is_cancellation")` 选择 `_positive_number` 或 `_negative_number` |
| `_validate_gr_creation_context` | `is_cancellation == 'Y'` 时跳过 budget check |
| `_compute_incl_tax` | 公式 `a * (1 + r/100)` 对负数同样正确，无需改 |

### 2.3 update_gr() — draft/pending

| 位置 | 变更 |
|------|------|
| `estimated_amount` 校验 | 根据 `merged["is_cancellation"]` 选择验证函数 |
| budget check | `is_cancellation == 'Y'` 时跳过 |
| `allowed` keys | 新增 `"is_cancellation"` |

### 2.4 update_gr() — approved

| 位置 | 变更 |
|------|------|
| `con_value` 校验 | 根据 `before["is_cancellation"]` 选择 `_non_negative_number` 或 `_non_positive_number` |
| budget check (extra_amount) | `is_cancellation == 'Y'` 时跳过 |

`is_cancellation` 不在 approved 状态的 allowed keys 中（类型不可在审批后变更）。

### 2.5 approve_gr()

| 位置 | 变更 |
|------|------|
| `con_value` 校验 | 根据 `before["is_cancellation"]` 选择 `_non_negative_number` 或 `_non_positive_number` |
| budget check (extra_amount > 0) | `is_cancellation == 'Y'` 时跳过 |

---

## 3. Backend — import_service.py

### 3.1 列别名

```python
_GR_COLUMN_ALIASES["is_cancellation"] = [
    "Is Cancellation", "is_cancellation", "是否取消类型"
]
```

### 3.2 行校验

`_validate_gr_rows()` 新增交叉校验：

- `is_cancellation` 值必须为 `'Y'` 或 `'N'`（或空，默认 `'N'`）
- 当 `is_cancellation = 'Y'` 时，`estimated_amount` 必须 < 0
- 当 `is_cancellation = 'N'`（或空）时，`estimated_amount` 必须 > 0
- 如果提供了 `con_value`，也做一致性校验（符号与 `is_cancellation` 匹配）

### 3.3 插入语句

INSERT 列列表新增 `is_cancellation`。

---

## 4. Backend — export_service.py

所有 SUM 聚合（`_gr_overview`、`_build_monthly_trends`、`_build_requester_summary`、`_build_budget_summary`）中，负金额自然抵消正金额 —— **无需修改 SQL**。

前端 ExportDialog.vue 的 GR 列定义新增 `is_cancellation` 列。

---

## 5. Backend — budget_service.py

`compute_sc_budget()` / `compute_po_budget()` / downstream budget 中所有 SUM 聚合自然抵消，**无需修改**。

边界情况：如果 Cancellation GR 金额大于已消费金额，`available_amount` 会暂时 > 原始金额。数学上正确（退款释放预算），不做特殊处理。

---

## 6. Backend — notification

### 6.1 templates.py

- `_GR_RENAMES` 新增：`"is_cancellation": "Cancellation GR"`
- `_GR_ORDER` 末尾追加 `"is_cancellation"`
- `_GR_EXCLUDE` 不排除 `is_cancellation`（确保邮件正文显示）

### 6.2 sender.py

邮件标题逻辑：当 `row["is_cancellation"] == "Y"` 时加 `"(Cancellation)"` 前缀。

阈值通知（`thresholds.py`）和月度报告（`monthly.py`）的 SUM 聚合自然抵消，**无需修改**。

---

## 7. Backend — 其他服务

| 文件 | 影响 |
|------|------|
| `query_service.py` | 搜索/排序/过滤列映射无需改（金额字段已有）；后续可选加 `is_cancellation` 过滤 |
| `sc_service.py` | `con_value is null` 检查不变，Cancellation GR 也必须有 con_value |
| `po_service.py` | 同上 |
| `bridge.py` | API 透传字段，注意 `update_gr` 和 `approve_gr` 的 allowed keys |
| `schema.sql` | 同步更新 gr_requests 定义 |

---

## 8. Frontend

### 8.1 GrFormDialog.vue

| 元素 | 变更 |
|------|------|
| 新增字段 | `is_cancellation` — `el-select` (Y/N)，默认 N |
| `estimated_amount` | `:min` / `:max` 动态切换：`is_cancellation = 'N'` → `:min="0"`；`is_cancellation = 'Y'` → `:max="0"` |
| `con_value` | 同 `estimated_amount` |
| `gross_cost` | 同 `estimated_amount`（disabled 字段，约束一致） |
| `computedInclTax` | 公式 `a * (1 + r/100)` 对负数同样正确，无需改 |
| `emptyForm()` | 初始值加 `is_cancellation: 'N'` |

### 8.2 GrDetailView.vue

详情中新增 `is_cancellation` 展示行。

### 8.3 GrListView.vue / GrTable.vue

| 组件 | 变更 |
|------|------|
| `GrListView.vue` | 列表新增 `is_cancellation` 列和过滤器 |
| `GrTable.vue` | PO 详情下 GR 子表新增 `is_cancellation` 列 |
| `AmountDisplay` | 负数正常显示（如 `-5,000.00`），无需改 |

### 8.4 ExportDialog.vue

GR 导出列定义新增 `is_cancellation`。

### 8.5 i18n

| Key | zh-CN | en-US |
|-----|-------|-------|
| `gr.isCancellation` | 是否取消类型 | Cancellation GR |

---

## 9. 影响范围总览

```
sc_gr_app/db/migrations.py          — v37 migration (新字段 + 重建表)
sc_gr_app/db/schema.sql             — 同步 gr_requests 定义
sc_gr_app/services/gr_service.py    — 校验、budget skip、approve
sc_gr_app/services/import_service.py — 列别名、交叉校验、INSERT
sc_gr_app/services/export_service.py — 无需改 (SUM 自然抵消)
sc_gr_app/services/budget_service.py — 无需改
sc_gr_app/services/query_service.py — 无需改
sc_gr_app/services/sc_service.py    — 无需改
sc_gr_app/services/po_service.py    — 无需改
sc_gr_app/api/bridge.py             — update_gr/approve_gr allowed keys
sc_gr_app/notification/templates.py — 字段重命名、排序
sc_gr_app/notification/sender.py    — 邮件标题 "(Cancellation)"
sc_gr_app/notification/thresholds.py — 无需改
sc_gr_app/notification/monthly.py   — 无需改
frontend/.../GrFormDialog.vue       — 新字段 + 动态金额约束
frontend/.../GrDetailView.vue       — 详情展示
frontend/.../GrListView.vue         — 列表列 + 过滤器
frontend/.../GrTable.vue            — 子表列
frontend/.../ExportDialog.vue       — 导出列
frontend/.../zh-CN.js               — i18n
frontend/.../en-US.js               — i18n
```
