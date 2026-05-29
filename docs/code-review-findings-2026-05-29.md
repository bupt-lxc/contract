# SC/GR 管理系统 — 代码审查问题清单

> 审查日期: 2026-05-29
> 来源: 7 个并行 Agent 审查 69 个源文件 (~8,400 行)

---

## 🔴 P0 — 数据正确性

### 1. SC 列表查询返回重复行
**文件**: `sc_gr_app/services/query_service.py` 第 195-196 行

**问题**: `search_scs` 的 SQL 用 `left join pos` 和 `left join vendors` 但没有 `DISTINCT`。一个 SC 关联了 3 个 PO 时，会返回 3 条完全相同的 SC 记录。

**如何测试**: 
86183
admin
1. 创建一个 SC 并添加 2-3 个 PO
2. 打开 SC 列表页面，看同一个 SC 是否出现多次
3. 或者：对比实际 SC 数量和列表显示的总数是否一致

---

## 🔴 P1 — 认证安全

### 2. 路由守卫把所有错误当认证失败
**文件**: `frontend/src/router/index.js` 第 91 行

**问题**: `beforeEach` 的 catch 块无论什么错误都跳到 `/login`。后端临时重启 → 所有已登录用户被踢。

**如何测试**:
1. 登录后关掉 Python 后端
2. 刷新页面 → 应该显示"连接失败"之类的，而不是直接跳到登录页
3. 重开后端 → 已经在登录页了(错误行为)

---

### 3. 通知 API 三个端点没有权限控制
**文件**: `sc_gr_app/api/bridge.py`
- 第 334 行 `get_sc_notification_config` — 任何人可读任意 SC 通知配置
- 第 343 行 `save_sc_notification_config` — 任何人可写任意 SC 通知配置
- 第 375 行 `list_notification_queue` — 任何人可看全部邮件队列

**如何测试**:
1. 用普通用户登录
2. 打开浏览器控制台，直接调用 `callApi('get_sc_notification_config', {sc_id: '别人的SC'})`
3. 应该返回拒绝，但目前会成功返回

---

## 🟠 P2 — 运行时崩溃

### 4. 查询不存在的供应商时服务端崩溃
**文件**: `sc_gr_app/services/vendor_service.py` 第 53-58 行

**问题**: `_get_vendor` 对 `None` 调用 `dict(None)` 抛出 TypeError。第 157/201 行的 `if not before` 检查永远执行不到（在此之前就崩了）。

**如何测试**:
1. 打开 Vendor 列表
2. 记下一个 vendor_id，然后直接通过 console 调用 `callApi('update_vendor', {vendor_id: '不存在的ID', data: {phone: '123'}})`
3. 应该返回 "Vendor not found"，实际上是 UNEXPECTED_ERROR

---

## 🟠 P3 — 前端功能失效

### 5. PO 列表页编辑保存不生效
**文件**: `frontend/src/views/PoListView.vue` 第 106 行

**问题**: `updatePo(data)` 只传了一个参数，但组合式函数签名是 `updatePo(poId, data)`。PO 详情页已修复，列表页遗漏。

**如何测试**:
1. 进入 PO 列表页 (`/po`)
2. 点击任意 PO 行的编辑按钮
3. 修改合同号或金额 → 保存
4. 应该看到更新后的数据，目前静默失败（控制台有错误）

---

### 6. 供应商筛选完全无效
**文件**: `frontend/src/composables/useVendor.js` 第 11 行

**问题**: `searchVendors` 只发送 `{ text }`，7 个高级筛选字段全部丢弃。

**如何测试**:
1. 创建几个不同服务范围的供应商（如 "Transportation" 和 "General Service"）
2. 在 Vendor 列表页，展开高级筛选，选 Service Scope = "Transportation"
3. 应该只显示 Transportation 的供应商，实际显示全部

---

### 7. 普通用户无法从工作台进入自己的草稿
**文件**: `frontend/src/views/HomeView.vue` 第 60 行

**问题**: 非 Admin 的 "My Drafts" 卡片 `onRowClick` 是空箭头函数 `() => {}`，点击无反应。

**如何测试**:
1. 用 requester 角色登录
2. 创建一个 SC 草稿
3. 回到 Workbench，在 "My Drafts" 卡片点击那条草稿
4. 应该跳转到 SC 详情，实际无反应

---

### 8. SC 详情页全部操作失败时无反馈
**文件**: `frontend/src/views/ScDetailView.vue` 第 143, 152, 161, 175, 184, 193 行

**问题**: submit/approve/deny/close/po-approve/po-finish 全部用空 `catch {}` 吞掉错误。用户点确认后毫无反应，不知道失败。

**如何测试**:
1. 创建一个 SC 草稿，**故意不填 sc_no**
2. 提交 → 点确认 → 应该提示 "SC No is required"，实际上什么都没发生
3. 同样测试：用一个 pending SC，不填 sc_no 就点 Approve

---

### 9. 五个表单对话框保存按钮虚假成功
**文件**: 
- `frontend/src/components/po/PoFormDialog.vue` 第 98 行
- `frontend/src/components/po/GrFormDialog.vue` 第 79 行
- `frontend/src/components/sc/ScFormDialog.vue` 第 127 行
- `frontend/src/components/vendor/VendorFormDialog.vue` 第 112 行
- `frontend/src/components/system/UserFormDialog.vue` 第 73 行

**问题**: `emit('save')` 没加 `await`。对话框立刻关闭并 toast "Saved"，但 API 调用还在进行。失败时用户已经被骗了。

**如何测试**:
1. 打开任意创建对话框（如 New SC）
2. 填写数据后点击保存
3. 断掉后端（或制造一个后端错误），观察：对话框应该保持打开并提示错误，但实际上已经关闭并显示了 "Saved"

---

## 🟡 P4 — 表单验证

### 10. SC 表单提交时验证错误不显示
**文件**: `frontend/src/components/sc/ScFormDialog.vue` 第 25, 34, 39, 46, 51 行

**问题**: 5 个必填字段的 `<el-form-item>` 缺少 `prop` 属性，Element Plus 无法渲染红色错误提示。

**如何测试**:
1. 点击 New SC
2. 只填 requester_id，其余全部留空
3. 点 "Save & Submit"
4. **应该看到**: 5 个字段变红并提示 "required"
5. **实际看到**: 什么都没发生，对话框开着但毫无反馈

---

### 11. SC 表单编辑时泄露内部字段到 API
**文件**: `frontend/src/components/sc/ScFormDialog.vue` 第 116 行

**问题**: `Object.assign(form, props.record)` 把全部字段（包括 sc_id, status, created_by 等内部字段）复制到表单，保存时一起发回后端。

**如何测试**:
1. 打开一个已有 SC 的编辑对话框
2. 在浏览器控制台打断点或打印 form 对象
3. 观察 form 里是否包含了 sc_id, status, created_at 等不应该出现在编辑表单里的字段
4. PoFormDialog, GrFormDialog, VendorFormDialog, UserFormDialog 同样问题

---

## 🟡 P5 — 其他

### 12. 登录页永远不超时
**文件**: `frontend/src/views/LoginView.vue` 第 81-83 行

**问题**: `retryCount` 递增但从未检查上限。后端宕机时永久每 2 秒轮询，用户只能杀进程。

**如何测试**:
1. 登录时不启动后端
2. 观察登录页面是否永远在 "Detecting identity..." → "Retrying..." 之间循环
3. 等 30 秒看看有没有超时提示 (目前没有)

---

### 13. 邮件日志页的 entity_type/entity_id 筛选是假的
**文件**: `frontend/src/views/EmailLogsView.vue` 第 104-109 行

**问题**: 页面上有 Type 和 Entity ID 的筛选控件，但 `loadQueue()` 根本没把这些值传给后端。

**如何测试**:
1. 打开 Email 页面
2. Type 下拉选 "PO" → 点 Refresh
3. 应该只显示 PO 的邮件，实际还是全部显示

---

## 🔵 附加 — 后端已确认但前端不易测的问题

| # | 文件 | 行号 | 问题 |
|---|------|------|------|
| 14 | `po_service.py` | 22-35 | PO ID 生成在锁外 → 并发时可能重复 |
| 15 | `gr_service.py` | 24-37 | GR ID 同上 |
| 16 | `gr_service.py` | 434-439 | 已审批 GR 的 con_value 为 null 时 Decimal(None) 崩溃 |
| 17 | `vendor_service.py` | 164-172 | update_vendor 先写数据库再验证，次序颠倒 |
| 18 | `notification_service.py` | 9-11 | 时间戳格式不统一 (strftime vs isoformat) |
| 19 | `query_service.py` | 263 | search_vendors 无 visibility 过滤(其他 search 都有) |
| 20 | `rbac.py` | 14 | `can_edit_sc` 函数从未被调用 |
| 21 | `app_shell.py` | 58-66 | `_check_update` 中 return 后的代码永久无法执行 |
