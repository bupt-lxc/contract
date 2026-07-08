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

重建 `gr_requests` 表，将原来的单体 CHECK 改为区分类型的复合 CHECK。Cancellation GR 的 `estimated_amount` 必须 < 0，`con_value` 必须 <= 0：

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

> **注意：** `schema.sql` 目前已有较多列与最新 migration 不同步（缺少 `gross_cost`、`tax_rate`、`confirmed_at`、`submitted_date` 等），属于已有的 drift。本次 migration 仅关注 `is_cancellation` 和金额约束变更，不修复已有的 schema.sql drift。

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
| `_validate_gr_creation_context` | 签名新增 `is_cancellation` 参数；当 `is_cancellation == 'Y'` 时跳过 SC/PO budget check |
| `_compute_incl_tax` | 公式 `a * (1 + r/100)` 对负数同样正确，无需改 |
| INSERT 语句 | 列列表和 VALUES 中均需新增 `is_cancellation` |

### 2.3 submit_gr()

`submit_gr()` (line ~432-475) 中 budget check `sc_budget["sc_available_amount"] < estimated_amount` 在 `estimated_amount` 为负数时自然恒为 false（正数 < 负数），所以 **无需显式跳过**。但为确保代码意图清晰，建议加注释说明 Cancellation GR 不参与 budget check。

### 2.4 update_gr() — draft/pending

| 位置 | 变更 |
|------|------|
| `estimated_amount` 校验 | 根据 `merged["is_cancellation"]` 选择 `_positive_number` 或 `_negative_number` |
| budget check | `is_cancellation == 'Y'` 时跳过（delta check 对负数变化不适用） |
| `allowed` keys | 新增 `"is_cancellation"` |

### 2.5 update_gr() — approved

| 位置 | 变更 |
|------|------|
| `con_value` 校验 | 根据 `before["is_cancellation"]` 选择 `_non_negative_number` 或 `_non_positive_number` |
| budget check (extra_amount) | `is_cancellation == 'Y'` 时跳过 |

`is_cancellation` 不在 approved 状态的 allowed keys 中（类型不可在审批后变更）。

### 2.6 approve_gr()

| 位置 | 变更 |
|------|------|
| `con_value` 校验 | 根据 `before["is_cancellation"]` 选择 `_non_negative_number` 或 `_non_positive_number` |
| budget check (extra_amount > 0) | `is_cancellation == 'Y'` 时跳过 |

### 2.7 get_annual_report_data()

使用 `SELECT gr.*`，迁移后自动包含 `is_cancellation` 字段，**无需修改**。按需决定是否在年度报告中展示该列。

---

## 3. Backend — import_service.py

### 3.1 列别名

```python
_GR_COLUMN_ALIASES["is_cancellation"] = [
    "Is Cancellation", "is_cancellation", "是否取消类型"
]
```

### 3.2 行校验

`_validate_gr_rows()` 和 `preview_gr_import()` 两处均有行校验逻辑，均需新增交叉校验：

- `is_cancellation` 为可选字段，值必须为 `'Y'` 或 `'N'`（空或缺失时默认 `'N'`）
- 当 `is_cancellation = 'Y'` 时，`estimated_amount` 必须 < 0
- 当 `is_cancellation = 'N'`（或空）时，`estimated_amount` 必须 > 0
- 如果提供了 `con_value`，符号需与 `is_cancellation` 一致（N → >= 0，Y → <= 0）

### 3.3 插入语句

`import_grs()` 和 `import_grs_without_linking()` 的 INSERT 列列表均需新增 `is_cancellation`。

### 3.4 导入模板

`download_gr_template()` (bridge.py) 的模板 header、hint、sample 行中新增 `is_cancellation` 列。

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
- `build_body()` / `_entity_detail_rows()` — 仅需更新 `_GR_RENAMES` 和 `_GR_ORDER`，无需其他改动。金额格式化 `_fmt_amount` 对负数自然支持
- Confirm 按钮邮件：Cancellation GR 的 submit 事件同样显示 confirm 按钮（流程一致），无需特殊处理

### 6.2 邮件标题

`build_subject()` (templates.py) 中，当 `entity_info.get("is_cancellation") == "Y"` 时，标题格式为：

```
[POMP] Submitted (Cancellation) GR 0629-002 from LiXingchen
```

即在 action 和实体类型之间插入 `(Cancellation)`。实现方式：在 `build_subject` 中检测 `entity_info["is_cancellation"]`，将 `entity_type` 替换为 `"(Cancellation) GR"`。

### 6.3 阈值和月度报告

`thresholds.py` 和 `monthly.py` 的 SUM 聚合自然抵消，**无需修改**。

---

## 7. Backend — 其他服务

| 文件 | 影响 |
|------|------|
| `query_service.py` | 搜索/排序/过滤列映射无需改（金额字段已有）；后续可选加 `is_cancellation` 过滤 |
| `sc_service.py` | `con_value is null` 检查不变（Cancellation GR approved 时也必须有 con_value，值 <= 0） |
| `po_service.py` | 同上 |
| `bridge.py` | 不需要修改 allowed keys 过滤（该逻辑在 gr_service.py 中）；仅需更新 `download_gr_template` 模板 |
| `schema.sql` | 同步 gr_requests 定义到最新（本次仅关注 is_cancellation + 复合 CHECK） |

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
sc_gr_app/db/migrations.py          — v37 migration (新字段 + 重建表 + 复合 CHECK)
sc_gr_app/db/schema.sql             — 同步 gr_requests 定义
sc_gr_app/services/gr_service.py    — 校验、budget skip、INSERT、approve、annual report
sc_gr_app/services/import_service.py — 列别名、双路径交叉校验、INSERT、模板
sc_gr_app/services/export_service.py — 无需改 (SUM 自然抵消)
sc_gr_app/services/budget_service.py — 无需改
sc_gr_app/services/query_service.py — 无需改
sc_gr_app/services/sc_service.py    — 无需改
sc_gr_app/services/po_service.py    — 无需改
sc_gr_app/api/bridge.py             — download_gr_template 模板列
sc_gr_app/notification/templates.py — build_subject 标题、字段重命名、排序
sc_gr_app/notification/sender.py    — 无需改 (templates.py 已处理)
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
