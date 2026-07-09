# Service Scope 调整及 Request Type 重构设计

**Date:** 2026-07-07
**Branch:** feat/independent-fc-po

## 概述

三项改动：
1. SC `request_type` 从 4 值改为 3 值，旧值映射
2. SC 新增 `service_scope` 非必填字段（15 个分类值）
3. Vendor `service_scope` 重命名 2 个旧值，vendor 表 + sc_vendors 快照同步更新

---

## 1. request_type 重定义

### 旧值 → 新值

| 旧值 | 新值 | 说明 |
|------|------|------|
| `FC` | `FC` | 框架合同，不变 |
| `material` | `new` | 映射 |
| `service` | `new` | 映射 |
| `fixed_asset` | `new` | 映射 |
| — | `call_off` | 新增，子合同 |

### 新值显示标签

| DB 值 | 显示标签 | 说明 |
|-------|---------|------|
| `FC` | `FC` | 不变 |
| `call_off` | `Call Off` | 邮件/界面统一 |
| `new` | (空白) | 不显示，等同于普通合同 |

### call_off 业务规则

- 前端：已有 `PoFcSelectorDialog.vue` 二步流程。用户先在弹出的 FC PO 列表中选择父 PO（仅列出 status=`active` 且 is_fc_po=1 的 PO），选中后 `calloffPoId` 通过 prop 传入 `ScFormDialog.vue`。ScFormDialog 收到 `calloffPoId` 后自动将 `request_type` 设为 `call_off` 并从选项列表中排除 `FC`。
- 后端：`_validate_calloff_po()` 校验：`request_type == 'call_off'` 时 `calloff_po_id` 必填；父 PO 必须 `status = 'active'` 且为 FC 类型（PO 自身 `request_type = 'FC'` 或其 SC 的 `request_type = 'FC'`）。`request_type == 'FC'` 时拒绝 `calloff_po_id`。
- 安全性：`call_off` SC 自身的 PO 不会被视为 FC（PO 侧 `request_type` 为 NULL，SC 侧 `request_type = 'call_off'`），`_validate_calloff_po` 中对 `po_request_type` 和 `parent_sc_type` 的双重检查已天然阻止被其他 call_off 引用。
- 父 PO 选择仅限于 status=`active` 的 FC PO。

### 后端改动

**sc_service.py**:
- `SUPPORTED_REQUEST_TYPES` → `{"FC", "call_off", "new"}`
- `create_sc_draft` / `create_sc` / `update_sc` / submit: 校验改为新 set
- `_validate_calloff_po`: `request_type == 'call_off'` 时 `calloff_po_id` 必填，父 PO 校验 status=`active` + FC 类型；`call_off` 与 `FC` 互斥

**po_service.py**: FC 检测 `request_type == 'FC'` 保持不变（PO 侧不改）

**import_service.py**: `_validate_sc_rows` 新增 `request_type` 合法性校验（当前缺失，仅靠 DB CHECK 兜底）；PO 导入不变

**export_service.py**: 不变（透传 DB 值）

**query_service.py**: `search_scs` 筛选选项改为 3 值；`search_pos` FC 检测 `po.request_type = 'FC' OR sc.request_type = 'FC'` 不变；`is_fc_po` 过滤条件不变

**bridge.py**:
- SC 模板下载 hint 从 `"material/service/fixed_asset/FC"` → `"FC/call_off/new"`
- 模板示例行 `request_type` 从 `"material"` → `"new"`
- FC 检测逻辑不变

**budget_service.py / gr_service.py**: FC 检测 `request_type == 'FC'` 保持不变

**notification 层** (sender.py, thresholds.py, monthly.py):
- FC 检测 `request_type == 'FC'` 保持不变
- templates.py: 新增 `_REQUEST_TYPE_LABEL = {"FC": "FC", "call_off": "Call Off", "new": ""}`，邮件渲染时使用 label 而非原始值

### 前端改动

**ScFormDialog.vue**:
- `requestTypes` → `['FC', 'call_off', 'new']`
- 保持现有 `calloffPoId` prop 机制：收到 prop 时自动设 `request_type = 'call_off'` 并从选项中排除 `FC`
- 不新增内嵌父 PO 选择器 —— 继续使用现有 `PoFcSelectorDialog` 二步流程

**ScListView.vue**: `requestTypes` → `['FC', 'call_off', 'new']`，筛选同步

**PoFcSelectorDialog.vue**: 不变（已正确筛选 `is_fc_po: '1', status: 'active'`）

**HomeView.vue**:
- `typeLabel()` 映射更新：`{ FC: 'FC', call_off: 'CO', new: '' }`
- `new` 类型返回空字符串，表格单元格不显示内容

**ScDetailCard.vue / ScTable.vue / PoTable.vue / PoListView.vue / PoDetailView.vue / GrListView.vue**:
- FC 判断 `=== 'FC'` 不变
- 原始值显示: 直接使用 DB 值（`FC`/`call_off`/`new`），通过统一 `requestTypeLabel()` 工具函数转为显示标签

**新增工具函数** (放入共用 composable):
```javascript
export function requestTypeLabel(type) {
  if (!type) return ''
  const map = { FC: 'FC', call_off: 'Call Off', new: '' }
  return map[type] || type
}
```

**ExportDialog.vue**: 不变

---

## 2. SC 新增 service_scope 字段

### 数据库

在 v35 重建 `sc_records` 表时直接加入列定义：

```sql
service_scope TEXT
```

- 非必填（无 NOT NULL），无 CHECK 约束
- 值与 Vendor `SUPPORTED_SERVICE_SCOPES` 共享同一 15 值集合

### 15 值列表

```
Transportation, Engineering Service, Equipment, Parts, Driver,
Test car rental, General Service, Dealers, Import&Export&cusoms clearance,
Insurance, Harness, Maintenance&Calibration, Security, Testing support, Others
```

### 后端

**sc_service.py**: `OPTIONAL_UPDATE_FIELDS` + `"service_scope"`；CRUD 透传

**import_service.py**: SC 导入列别名加入 `"service_scope": ["Service Scope", "service_scope", "服务范围"]`；`_validate_sc_rows` 中非空时校验值在 `SUPPORTED_SERVICE_SCOPES` 内

**export_service.py**: SC 导出列映射 + `"service_scope": "service_scope"`

**query_service.py**: `search_scs` 搜索/筛选/排序 + `service_scope`

**bridge.py**: SC 模板下载 headers + `service_scope`

### 前端

**ScFormDialog.vue**: 新增 `el-select`（非必填，clearable），选项来自共享 15 值列表

**ScDetailCard.vue**: 新增展示行（`v-if="sc.service_scope"`）

**ScTable.vue**: 新增 `service_scope` 列

**ScListView.vue**: 筛选配置 + `service_scope`

**ExportDialog.vue**: SC 导出字段 + `service_scope`

---

## 3. Vendor service_scope 重命名

### 变更

| 旧值 | 新值 |
|------|------|
| `engineering Service` | `Engineering Service` |
| `Maintenance` | `Maintenance&Calibration` |

其余 13 个值不变。

### 数据库迁移

```sql
-- vendors 表
UPDATE vendors SET service_scope = 'Engineering Service'
  WHERE service_scope = 'engineering Service';
UPDATE vendors SET service_scope = 'Maintenance&Calibration'
  WHERE service_scope = 'Maintenance';

-- sc_vendors 快照 JSON
UPDATE sc_vendors
  SET vendor_snapshot = json_set(vendor_snapshot, '$.service_scope', 'Engineering Service')
  WHERE json_extract(vendor_snapshot, '$.service_scope') = 'engineering Service';
UPDATE sc_vendors
  SET vendor_snapshot = json_set(vendor_snapshot, '$.service_scope', 'Maintenance&Calibration')
  WHERE json_extract(vendor_snapshot, '$.service_scope') = 'Maintenance';
```

`json_extract(NULL, ...)` 返回 NULL，`NULL = 'engineering Service'` 为 false，NULL 快照安全跳过。

### 后端

**vendor_service.py**: `SUPPORTED_SERVICE_SCOPES` 更新 2 值；`preview_import` 增加校验: 非空且值在 `SUPPORTED_SERVICE_SCOPES` 内

### 前端

**VendorFormDialog.vue**: `serviceScopes` 数组更新 2 值

**VendorImportDialog.vue**: 校验提示更新为新的值列表

**seed_data.py**: 3 处 vendor `"engineering Service"` → `"Engineering Service"`；SC request_type 旧值 `material`/`service`/`fixed_asset` → `new`

---

## 4. 迁移 v35

### 前置条件

调用方必须先执行 `PRAGMA foreign_keys = OFF`（与现有 v34 模式一致），确保 ALTER TABLE 不会因隐式提交破坏事务原子性。

### 迁移步骤

由于 SQLite 限制，修改 `sc_records` 的 CHECK 约束或新增列都需要重建表。而重建 `sc_records` 会使其被 rename，所有指向它的 FK（pos, gr_requests, sc_vendors）必须同步重建。v35 遵循 v34 的四表重建模式，但**不新增 FK 依赖表**（pos/gr_requests/sc_vendors 结构与当前一致，仅因 rename 而被级联重建）。

```python
def _migrate_v35(conn):
    # 1. 数据迁移 — 重命名 vendor service_scope 旧值
    conn.execute(
        "UPDATE vendors SET service_scope = 'Engineering Service' "
        "WHERE service_scope = 'engineering Service'"
    )
    conn.execute(
        "UPDATE vendors SET service_scope = 'Maintenance&Calibration' "
        "WHERE service_scope = 'Maintenance'"
    )

    # 2. 数据迁移 — sc_vendors 快照 JSON
    conn.execute(
        "UPDATE sc_vendors SET vendor_snapshot = json_set("
        "  vendor_snapshot, '$.service_scope', 'Engineering Service'"
        ") WHERE json_extract(vendor_snapshot, '$.service_scope') = 'engineering Service'"
    )
    conn.execute(
        "UPDATE sc_vendors SET vendor_snapshot = json_set("
        "  vendor_snapshot, '$.service_scope', 'Maintenance&Calibration'"
        ") WHERE json_extract(vendor_snapshot, '$.service_scope') = 'Maintenance'"
    )

    # 3. 数据迁移 — request_type 旧值映射
    conn.execute(
        "UPDATE sc_records SET request_type = 'new' "
        "WHERE request_type IN ('material', 'service', 'fixed_asset')"
    )

    # 4. 四表重建（遵循 v34 模式）
    #    Phase 1: rename pos, sc_records, gr_requests, sc_vendors → *_old
    #    Phase 2: CREATE TABLE 新表
    #      - sc_records: CHECK(request_type IN ('FC','call_off','new')), 新增 service_scope TEXT
    #      - pos, gr_requests, sc_vendors: 结构与 v34 一致（无变更）
    #    Phase 3: INSERT INTO ... SELECT FROM *_old（映射列）
    #    Phase 4: DROP TABLE *_old
    #    Phase 5: 重建所有索引

    _record(conn, 35)
```

### 重建涉及的表

| 表 | 重建原因 | 结构变更 |
|----|---------|---------|
| `sc_records` | CHECK 约束更新 + 新增列 | CHECK `IN ('FC','call_off','new')`; +service_scope TEXT |
| `pos` | FK 指向 sc_records（级联） | 无 |
| `gr_requests` | FK 指向 sc_records + pos（级联） | 无 |
| `sc_vendors` | FK 指向 sc_records（级联） | 无 |

### V1_SQL 同步更新

- sc_records CHECK → `CHECK (request_type IN ('FC', 'call_off', 'new'))`
- vendors CHECK → 更新 `'engineering Service'` 和 `'Maintenance'` 为 `'Engineering Service'` 和 `'Maintenance&Calibration'`
- sc_records 新增 `service_scope TEXT`

---

## 5. 请求类型显示标签汇总

所有显示 `request_type` 的地方统一使用标签映射：

| 位置 | 处理方式 |
|------|---------|
| 邮件模板 (templates.py) | `_REQUEST_TYPE_LABEL` dict: `{"FC":"FC", "call_off":"Call Off", "new":""}` |
| 前端表格/详情 | 共用 `requestTypeLabel()` 工具函数 |
| HomeView typeLabel | `{FC:'FC', call_off:'CO', new:''}` — new 返回空字符串 |
| ScListView 筛选 | 选项 label 使用 `requestTypeLabel()` |

---

## 6. 不受影响的逻辑

- FC 类型判断: `request_type == 'FC'` 语义不变
- PO 侧 request_type: 只存 `FC` 或 NULL，逻辑不变
- GR 对 FC 的排除: `sc.request_type != 'FC'` 不变
- 预算/通知 FC 分支: 不变
- `coalesce(po.request_type, sc.request_type)` 作为有效类型: 不变
- `ScDetailView.vue` `:is-fc="detail.sc.request_type === 'FC'"`: 不变（仅 FC 触发预算卡片）
- `PoFcSelectorDialog.vue`: 不变（筛选 `is_fc_po: '1', status: 'active'`）

---

## 7. 改动文件汇总

### 后端 (11)
| 文件 | 改动 |
|------|------|
| `sc_gr_app/db/migrations.py` | v35 四表重建 + V1_SQL 更新 |
| `sc_gr_app/services/sc_service.py` | `SUPPORTED_REQUEST_TYPES` 3 值 + `_validate_calloff_po` + service_scope CRUD |
| `sc_gr_app/services/vendor_service.py` | `SUPPORTED_SERVICE_SCOPES` 更新 + import 校验 |
| `sc_gr_app/services/import_service.py` | SC 导入 request_type 校验 + service_scope 列别名与校验 |
| `sc_gr_app/services/export_service.py` | SC 导出 + service_scope |
| `sc_gr_app/services/query_service.py` | `search_scs` + service_scope |
| `sc_gr_app/api/bridge.py` | SC 模板 hint + 示例行 + service_scope 列 |
| `sc_gr_app/notification/templates.py` | `_REQUEST_TYPE_LABEL` 映射 |
| `seed_data.py` | vendor service_scope + SC request_type 旧值 |

### 前端 (11)
| 文件 | 改动 |
|------|------|
| `frontend/src/components/sc/ScFormDialog.vue` | request_type 3 值 + service_scope 字段 |
| `frontend/src/components/sc/ScDetailCard.vue` | service_scope 展示 |
| `frontend/src/components/sc/ScTable.vue` | service_scope 列 |
| `frontend/src/components/sc/ScVendorSection.vue` | 不变（仅展示 vendor 的 service_scope） |
| `frontend/src/views/ScListView.vue` | requestType 选项 + service_scope 筛选 |
| `frontend/src/views/HomeView.vue` | `typeLabel` 映射更新 |
| `frontend/src/components/vendor/VendorFormDialog.vue` | `serviceScopes` 更新 |
| `frontend/src/components/vendor/VendorImportDialog.vue` | 校验提示 |
| `frontend/src/components/export/ExportDialog.vue` | service_scope 字段 |
| `frontend/src/composables/` | 新增 `requestTypeLabel()` 共用工具函数 |

### 测试 (约 13 个文件)
- request_type 值更新: `material`/`service`/`fixed_asset` → `new`
- 新增 v35 迁移测试 + service_scope 相关测试
