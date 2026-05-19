# SC 预算与 GR 管理系统设计方案

## 1. 项目定位

本系统是部门内部使用的 SC 预算与 GR 费用申请管理工具。正式 SC 申请、正式 GR 申请、财务审批和付款仍在外部财务系统中完成。本系统负责记录部门侧的 SC、PO、vendor、GR 流转、金额校验、实际扣减和审计日志。

系统不使用 IP/端口形式的服务端。所有用户运行 Windows 桌面客户端，数据库文件放在共享文件夹中。

## 2. 已确认决策

- 客户端：Python 桌面应用，使用 `pywebview`。
- 不做应用服务端，也不做共享文件夹请求队列。
- 数据库：共享文件夹中的 SQLite 文件。
- 并发预期：中低并发，约 2-5 人可能同时操作，但写入不频繁。
- 权限定位：中等防护。客户端负责角色控制、操作校验和审计日志；不承诺防止有共享文件夹权限的人绕过客户端直接改库。
- 身份识别：使用现有七位机器 ID 自动识别用户。
- 用户角色：`admin` 和 `requester`。
- 领域命名：代码和数据库统一使用 `vendor`；中文界面可显示“供应商”。
- 日志权限：所有已授权用户均可查看全部日志，日志只读。
- 首版不做完整邮件通知系统和复杂自动提醒；但 PO `contract_to` 是需要邮件提醒的业务字段，SC 预估服务期不触发提醒。

## 3. 首版范围

### 3.1 首版包含

- `pywebview + Python` Windows 桌面客户端。
- 共享 SQLite 数据库访问。
- 机器 ID 自动识别用户。
- 管理员 / requester 两类角色。
- SC 创建、SC 信息维护、状态管理、关闭、查看。日常 SC 创建和信息维护由 requester 负责，管理员可以代做。
- 供应商 vendor 独立维护，所有授权用户可见，由 requester 维护，管理员可以代做。
- SC 下 PO 独立维护。SC 与 vendor 是多对多关系，通过 PO 关联；一个 PO 对应一个 vendor。
- GR 创建、取消、审批通过、Con Value 回填。
- 不在表中维护金额汇总冗余字段；需要可用金额时按 SC amount、PO amount 和 GR 记录实时计算。
- 历史数据补录：
  - 管理员可创建任意状态的 SC。
  - 管理员可录入任意 PO 信息。
  - 管理员可录入任意状态的 GR。
  - SC 和 PO 使用情况由系统根据 GR 自动计算。
- 以 SC 为中心的查询界面。
- 全局审计日志，所有授权用户可读。
- 共享 SQLite 可靠性措施：
  - 应用级租约锁。
  - 短 SQLite 写事务。
  - `busy_timeout`。
  - 使用 rollback journal，不使用 WAL。
  - 备份和完整性检查工具。

### 3.2 首版不包含

- 邮件发送。
- SC 服务期提醒。SC 的服务期只是预估时间，不触发提醒；邮件提醒对象是 PO 的 `contract_to`。
- 预算不足自动提醒。
- 通知任务表和个性化通知策略。
- Excel 导入。
- Excel 导出。
- 应用服务端。
- 用户名密码登录。
- 强防篡改权限模型。
- 多级审批或主管角色。

## 4. 系统架构

系统是单体桌面应用，但内部按层拆分：

```text
pywebview 桌面壳
↓
HTML/CSS/JS 前端界面
↓
Python API 层
↓
业务服务层
↓
SQLite 数据访问层
↓
共享文件夹中的 SQLite 数据库
```

主要模块：

- `app_shell`：启动 pywebview、加载前端资源、暴露 Python API。
- `identity`：读取机器 ID，并解析当前用户。
- `rbac`：在前端入口和 Python API 层同时做角色校验。
- `sc_service`：SC 创建、编辑、状态变更、关闭、历史补录入口。
- `vendor_service`：管理 vendor 基础资料。
- `po_service`：管理 SC 下的 PO、PO No、PO amount，以及 PO 与 vendor 的关联。
- `gr_service`：管理 GR 创建、取消、审批和金额处理。
- `budget_engine`：统一负责预算计算和校验。
- `audit_log`：记录关键操作日志。
- `lock_manager`：管理共享文件夹中的租约锁。
- `backup_integrity`：负责数据库备份、完整性检查、锁状态查看。

## 5. 共享 SQLite 并发设计

SQLite 自带写锁，但共享文件夹中的锁可靠性取决于底层网络文件系统。因此系统不能只依赖“SQLite 会自己锁”。首版需要增加应用级锁，降低并发写入和网络异常导致的问题。

### 5.1 锁层级

```text
system
  用于用户管理、设置、数据库迁移、恢复、全库维护。

sc:{sc_id}
  用于某个 SC 下的 SC 信息、PO、GR、金额校验。

db-write-gate
  极短时间锁，只包住 SQLite 写事务入口到提交。
```

### 5.2 读取规则

- 读取不取应用级锁。
- SC 列表、SC 详情、GR 列表、vendor 列表、日志查询都直接读 SQLite。
- UI 展示过的数据不能直接作为写入依据。写操作进入事务后必须重新读取最新状态并再次校验。

### 5.3 写入规则

标准写入流程：

```text
获取业务租约锁，例如 sc:{sc_id}
↓
获取 db-write-gate 租约锁
↓
打开 SQLite 连接
↓
BEGIN IMMEDIATE
↓
重新读取最新状态并校验
↓
写入业务变化
↓
写入审计日志
↓
COMMIT / ROLLBACK
↓
释放 db-write-gate
↓
释放业务租约锁
```

租约锁文件包含：

- owner machine ID
- user
- process ID
- operation
- token
- `acquired_at`
- `heartbeat_at`
- `expires_at`

如果用户 A 拿到锁后断网，heartbeat 会停止。其他客户端发现锁超过过期时间后，可将其识别为 stale lock。管理员可以在系统工具中查看和清理 stale lock，避免永久死锁。

SQLite 连接策略：

- 使用 rollback journal，不使用 WAL。
- 设置 `busy_timeout`。
- 写事务必须短。
- 数据库繁忙或锁失败时给出明确错误，不静默重复提交。

## 6. 数据模型

### 6.1 核心表

`users`

- `user_id`
- `machine_id`
- `user_name`
- `role`
- `email`
- `status`
- `created_at`
- `updated_at`

`sc_records`

- `sc_id`
- `sc_no`
- `requester_id`
- `request_type`
- `cost_center`
- `sc_amount`
- `service_period_start`
- `service_period_end`
- `status`
- `description`
- `created_by`
- `created_at`
- `updated_at`
- `closed_at`

`vendors`

- `vendor_id`
- `vendor_name`
- `ksrm_vendor_code`
- `contact_person`
- `phone`
- `service_scope`
- `email`
- `description`
- `inquiry_history`
- `created_by`
- `created_at`
- `updated_at`

`pos`

- `po_id`
- `sc_id`
- `vendor_id`
- `po_no`
- `po_amount`
- `status`
- `contract_from`
- `contract_to`
- `contract_no`
- `payment_frequency`
- `created_at`
- `updated_at`

`gr_requests`

- `gr_id`
- `po_id`
- `requester_id`
- `estimated_amount`
- `con_value`
- `status`
- `remark`
- `created_by`
- `created_at`
- `approved_by`
- `approved_at`
- `cancelled_by`
- `cancelled_at`

`audit_logs`

- `log_id`
- `action_type`
- `object_type`
- `object_id`
- `sc_id`
- `operator_id`
- `machine_id`
- `before_json`
- `after_json`
- `operation_mode`
- `created_at`

`app_settings`

- 存放数据库版本、备份策略、共享路径等应用配置。

`schema_migrations`

- 记录数据库迁移版本。

### 6.2 首版不建的表

- `notification_task`
- `notification_record`
- 通知策略表
- 邮件模板表
- 附件表
- 多级审批表
- 报表快照表

## 7. 状态模型

SC 状态：

```text
pending
approved
denied
closed
```

SC 是否可以申请 GR 不只由状态决定，而是一个派生业务条件：

```text
sc.status = approved
AND sc_no 已填写
AND 至少存在一个 PO
AND 申请所选 PO 的 po_no 已填写
AND 申请所选 PO 的状态为 po_approved
AND SC 和该 PO 均有足够派生可用金额
```

因此 `approved` 表示管理员已通过 SC；不表示一定已经可以申请 GR。

Vendor 不区分业务状态。供应商资料作为公共基础数据，由 requester 维护，所有授权用户可见。

`service_scope` 采用固定选项：

```text
Transportation
engineering Service
Equipment
Parts
Driver
Test car rental
General Service
Dealers
Import&Export&cusoms clearance
Insurance
Harness
Maintenance
Security
Testing support
Others
```

PO 状态：

```text
po_pending
po_approved
finished
```

只有 `po_approved` 且 OPEN PO 足够的 PO 可以用于新建 GR。`finished` PO 不再允许新建 GR。

GR 状态：

```text
pending
approved
cancelled
```

首版 GR 只支持 `pending`、`approved`、`cancelled` 三种状态，不提供管理员退回或驳回状态。管理员如果不处理某个 GR，可以让 requester 取消后重新提交，或在备注中说明处理情况。

## 8. 金额规则

首版不维护余额冗余字段。SC 只存 `sc_amount`，PO 只存 `po_amount`，GR 存 `estimated_amount` 和 `con_value`。所有可用金额、pending 合计、Con Value 合计都由查询实时计算。

### 8.1 SC 层金额

字段含义：

- `sc_amount`：SC 预算总金额。

派生金额：

```text
sc_pending_total = sum(pending GR estimated_amount under all POs of this SC)
sc_con_value_total = sum(approved GR con_value under all POs of this SC)
sc_available_amount = sc_amount - sc_pending_total - sc_con_value_total
allocated_po_amount = sum(PO po_amount under this SC)
unallocated_sc_amount = sc_amount - allocated_po_amount
```

这些派生金额只用于展示和校验，不存入数据库。

SC 层金额代表整个 SC 的预算使用情况，不等于所有 PO 可用余额的简单求和。因为 SC 可能存在尚未分配给 PO 的预算。

### 8.2 PO 层金额

字段含义：

- `po_amount`：该 SC 下某个 PO 的金额。
- 一个 PO 必须对应一个 vendor。

派生金额：

```text
po_pending_total = sum(pending GR estimated_amount under this PO)
po_con_value_total = sum(approved GR con_value under this PO)
open_po_amount = po_amount - po_pending_total - po_con_value_total
```

这些派生金额只用于展示和校验，不存入数据库。`open_po_amount` 即 OPEN PO。

SC 下所有 PO amount 合计不能超过 SC amount：

```text
sum(po.po_amount) <= sc.sc_amount
```

首版允许小于 SC amount。小于部分视为 `unallocated_sc_amount`，只有后续创建或调整 PO 后，requester 才能基于该部分预算发起 GR。

### 8.3 GR 对金额的影响

业务规则：

- 创建 pending GR 时，不写余额字段；该 GR 的 `estimated_amount` 会在派生计算中计入 pending amount。
- 取消 pending GR 时，GR 状态变为 `cancelled`，不再计入 pending amount。
- 审批通过 GR 时，管理员填写 `con_value`，GR 状态变为 `approved`，该金额计入 Con Value 合计派生值。
- 如果 `con_value > estimated_amount`，审批时必须重新校验 SC 和 PO 的派生可用金额。
- 历史补录后根据 GR 状态和金额自动计算 SC 和 PO 的使用情况。

Approved GR 必须有 `con_value`。历史补录时，如果历史数据没有单独记录 Con Value，管理员应使用可确认的实际金额；如只能以预计金额代替，则将 `con_value = estimated_amount`，并在备注中说明。
## 9. 页面结构

系统以 SC 为中心。Vendor 和 GR 依赖 SC 存在，不作为一级主导航。

一级导航：

```text
首页
SC
待办
日志
系统
```

### 9.1 首页

管理员看到：

- pending GR 数量。
- pending SC 数量。
- 已通过但信息未补全、暂不能申请 GR 的 SC 数量。
- 锁和数据库异常提示。
- 近期 SC。
- 最近审计日志。

Requester 看到：

- 自己负责的 SC。
- 自己已通过但待补全 SC No / PO No / vendor 信息的 SC。
- 自己的 pending GR。
- 最近 GR 审批结果。

### 9.2 SC

- SC 列表。
- SC 详情。
- 新建 SC。
- 历史补录。

SC 详情页：

```text
基本信息
Vendor / PO / 预算
GR 记录
预算
日志
```

### 9.3 待办

- 管理员：pending GR、pending SC。
- Requester：自己的 pending GR、需要关注的 SC。

### 9.4 日志

- 所有已授权用户可查看全部日志。
- 日志只读。
- 未授权设备不能查看日志。

### 9.5 系统

管理员：

- 用户与机器 ID 管理。
- 数据库路径和状态。
- 锁状态。
- stale lock 清理。
- 手动备份。
- 完整性检查。
- 基础设置。

Requester：

- 默认不显示系统页；如有需要，可只展示只读数据库状态。

## 10. 查询、搜索与排序

首版必须提供统一的查询能力。SC、vendor、PO、GR 和日志列表均支持文本搜索、字段筛选和字段排序。

通用规则：

- 列表页提供全局文本搜索框。
- 枚举字段、状态字段、日期字段、金额字段提供结构化筛选。
- 表头支持升序 / 降序排序。
- 多个筛选条件按 AND 组合。
- 搜索、筛选和排序只读 SQLite，不取应用级业务锁。
- 大列表分页，避免一次性加载过多记录。

SC 查询：

- 文本搜索：SC No、requester、request type、Cost Center、description、vendor name、PO No。
- 字段筛选：requester、status、request type、Cost Center、service period 范围、SC amount 范围、是否有 SC No、是否存在可申请 GR 的 PO。
- 排序：SC No、SC amount、request type、Cost Center、service period start / end、status、created_at、updated_at。

vendor 查询：

- 文本搜索：vendor name、KSRM vendor code、contact person、phone、email、service scope、description、inquiry history。
- 字段筛选：service scope、是否有关联 PO、created_by、created_at 范围。
- 排序：vendor name、KSRM vendor code、service scope、created_at、updated_at。

PO 查询：

- 文本搜索：PO No、contract no、vendor name、KSRM vendor code、payment frequency、SC No。
- 字段筛选：SC、vendor、PO 状态、contract_from 范围、contract_to 范围、PO amount 范围、OPEN PO 范围、是否缺少 PO No、是否临近 contract_to。
- 排序：PO No、vendor name、PO amount、OPEN PO、PO 状态、contract_from、contract_to、created_at、updated_at。

GR 查询：

- 文本搜索：GR ID、SC No、PO No、vendor name、requester、remark。
- 字段筛选：status、requester、SC、PO、vendor、estimated amount 范围、Con Value 范围、created_at 范围、approved_at 范围。
- 排序：GR ID、estimated amount、Con Value、status、created_at、approved_at、requester。

日志查询：

- 字段筛选：operator、machine ID、object type、object ID、action type、SC、created_at 范围、operation mode。
- 排序：created_at、operator、object type、action type。

## 11. 核心业务流程

### 11.1 SC 日常流程

```text
requester 创建 SC
↓
SC 状态为 pending
↓
管理员审核 SC
↓
管理员通过后，SC 状态变为 approved
↓
requester 填写或补全 SC No
↓
requester 维护 vendor 基础资料，并在 SC 下维护 PO、PO No、PO amount、PO 状态、合同信息、PO 对应 vendor 等信息
↓
系统校验 PO amount 合计 <= SC amount
↓
系统按 GR 记录计算派生金额
↓
系统记录审计日志
```

管理员可以代 requester 创建 SC、填写 SC No、维护 vendor 和 PO 信息。代做时系统必须同时记录业务归属 requester 和实际操作人 admin。

SC 可申请 GR 的前置条件：

```text
SC 状态为 approved
SC No 已填写
至少存在一个 PO
申请所选 PO 的 PO No 已填写
申请所选 PO 的状态为 po_approved
SC 和该 PO 派生可用金额足够
```

金额不可用或 SC 被手动关闭后，SC 生命周期终止。终止后不能再发起新的 GR。SC 的服务期只是预估时间，不自动终止生命周期。

### 11.2 GR 创建流程

```text
requester 打开自己负责的 approved SC
↓
系统确认该 SC 已填写 SC No
↓
选择已填写 PO No 的 PO
↓
填写预计金额和备注
↓
系统获取 SC 锁
↓
系统在事务中重新校验 SC 状态、SC No、PO No、PO 状态、PO 对应 vendor 和派生可用金额
↓
系统创建 pending GR
↓
系统记录审计日志
```

### 11.3 GR 审批流程

```text
管理员打开 pending GR
↓
管理员在外部财务系统完成正式 GR 操作
↓
管理员填写 Con Value
↓
系统获取 SC 锁
↓
系统在事务中重新校验预算
↓
系统将 GR 标记为 approved
↓
系统将 Con Value 计入 Con Value 合计派生值
↓
系统记录审计日志
```

### 11.4 GR 取消

- Requester 只能取消自己创建且仍为 pending 的 GR。
- GR 首版只支持 `pending`、`approved`、`cancelled` 三种状态。
- 取消后该 GR 不再计入 pending amount。
- 所有操作都记录审计日志。

### 11.5 历史补录

```text
管理员进入历史补录
↓
创建任意支持状态的 SC
↓
添加 PO，并关联 vendor
↓
录入任意支持状态的历史 GR
↓
系统按 GR 记录计算 SC 和 PO 使用情况
↓
系统记录 operation_mode = backfill 的日志
```

## 12. 权限设计

管理员：

- 查看所有 SC。
- 代 requester 创建、编辑、关闭 SC。
- 代 requester 维护 SC No、vendor、PO No、PO amount、PO 状态和合同信息。
- 审核 SC，通过或拒绝 requester 提交的 SC。
- 代 requester 创建 GR。
- 审批、取消 GR。
- 使用历史补录。
- 管理用户和系统工具。
- 查看全部日志。

Requester：

- 查看自己负责的 SC。
- 创建自己负责的 SC。
- 修改自己负责 SC 的业务信息，包括 SC No、request type、Cost Center、预估服务周期、PO No、PO amount、PO 状态、PO 对应 vendor 等。
- 维护 vendor 基础资料，所有授权用户可见。
- 查看自己 SC 下的 PO。
- 在自己负责、approved 且 SC No/PO No/vendor/PO 状态信息完整的 SC 下创建 GR。
- 取消自己创建且 pending 的 GR。
- 查看相关 SC 和 GR 数据。
- 查看全部日志。

所有已授权用户：

- 查看全部审计日志。

未授权设备：

- 只能看到未授权提示，不能进入业务页面。

## 13. 开发阶段

### 阶段 1：项目骨架与数据库基础

目标：应用能启动，能连接共享 SQLite，有迁移和基础表。

内容：

- 建立 Python 项目结构。
- 集成 pywebview。
- 建立前端静态页面结构。
- 配置共享数据库路径。
- 初始化 SQLite schema。
- 实现 `schema_migrations`。
- 设置 SQLite 连接参数。
- 建立基础错误处理。

验收：

- 首次启动能创建数据库。
- 再次启动能识别数据库版本。
- 数据库路径不可用时有明确提示。

### 阶段 2：身份、权限、锁、日志

目标：多用户共享数据库的基础可靠性可用。

内容：

- 机器 ID 识别。
- 用户表与角色判断，默认管理员ID V2SE7PP（开发设备）。
- 未授权设备页面。
- 管理员维护用户。
- 租约锁：
  - `system`
  - `sc:{id}`
  - `db-write-gate`
- stale lock 检测和清理。
- 审计日志基础能力。
- 数据库完整性检查。
- 手动备份。

验收：

- 不同机器 ID 能识别不同用户，能够识别本机ID。
- 未授权用户无法进入业务页面。
- 写操作能生成日志。
- 模拟残留锁后可识别和清理。

### 阶段 3：SC 主流程

目标：SC 作为主工作区可用。

内容：

- 首页和 SC 列表。
- Requester 新建 SC，管理员可代建。
- SC 详情基本信息。
- Requester 维护 SC 业务信息，管理员可代维护。
- 管理员审核 SC 并执行状态变更。
- SC 关闭。
- SC 权限：管理员看全部，requester 只看自己的 SC。
- SC 详情页展示相关日志。

验收：

- Requester 可创建和维护自己负责的 SC，管理员可代做。
- 管理员可通过或拒绝 SC。
- Requester 只能看到自己负责的 SC。
- SC 状态和基础校验正确。

### 阶段 4：Vendor、PO 与金额校验

目标：vendor 基础资料可复用，SC 下 PO/PO amount 可维护，派生金额校验稳定。

内容：

- Vendor 基础资料维护页，所有授权用户可见。
- Vendor 字段包括 KSRM vendor code、联系人、电话、service scope、邮箱、描述、询价历史。
- SC 详情下的 PO tab。
- 新增、编辑 PO，并为每个 PO 选择一个 vendor，维护 PO 状态、合同起止时间、合同编号和付款频率。
- 校验 PO amount 合计不超过 SC amount。
- 金额引擎按 GR 记录计算 SC/PO 的 pending、Con Value、SC available 和 OPEN PO 派生金额。

验收：

- Vendor 可被多个 SC/PO 复用。
- SC 下可维护多个 PO，每个 PO 对应一个 vendor。
- SC 未填写 SC No、所选 PO 未填写 PO No 或 PO 状态不是 po_approved 时，不能发起 GR。
- 派生金额计算正确，数据库中不保存余额冗余字段。

### 阶段 5：GR 流程与历史补录

目标：费用申请闭环可用，历史数据可兼容。

内容：

- SC 详情下的 GR tab。
- Requester 发起 GR。
- Requester 取消 pending GR。
- 管理员审批通过并录入 Con Value。
- 待办页：pending GR / pending SC。
- 历史补录模式：
  - 任意 SC 状态。
  - 任意 GR 状态。
  - 自动计算派生金额。
  - backfill 日志。

验收：

- GR 创建、取消、通过后的派生金额变化正确。
- `con_value > estimated_amount` 时会重新校验派生可用金额。
- 历史补录后派生金额计算正确。

### 阶段 6：查询、打磨、打包

目标：达到部门内部可交付使用。

内容：

- SC、vendor、PO、GR、日志的文本搜索、字段筛选和字段排序。
- SC 内搜索：SC No、vendor、PO No、GR。
- 错误提示和确认弹窗。
- 表格分页、筛选、排序和默认排序规则。
- 数据库备份策略完善。
- 打包为 Windows 可执行程序。
- 编写使用说明和管理员维护说明。
- 基础测试数据和回归测试脚本。

验收：

- 非技术用户能按说明完成日常操作。
- 管理员能维护用户和备份数据库。
- 常见异常有清晰提示。
- 打包程序能在目标 Windows 环境运行。

## 14. 风险与处理

### 14.1 共享 SQLite 风险

风险：共享文件夹锁依赖底层网络文件系统。

处理：

- 使用应用级租约锁。
- SQLite 写事务保持短。
- 使用 rollback journal，不使用 WAL。
- 设置 `busy_timeout`。
- 提供备份和完整性检查。
- 数据库繁忙时明确提示用户。

### 14.2 机器 ID 身份识别风险

风险：用户换电脑、共用电脑或机器 ID 变更时需要人工维护。

处理：

- 提供管理员维护用户与机器 ID 映射的界面。
- 未授权设备显示明确提示。
- 审计日志记录 machine ID 和 operator。

### 14.3 中等权限模型风险

风险：有共享文件夹权限的人理论上可以绕过客户端直接改库。

处理：

- 明确系统定位为内部可信工具。
- 保留完整审计日志。
- 尽量收紧共享文件夹权限。
- 通过定期备份支持恢复。

### 14.4 历史补录风险

风险：补录模式过于宽松可能造成预算不一致。

处理：

- 不存储也不允许手动编辑余额字段。
- 根据 GR 记录自动计算派生金额。
- 补录操作在日志中标记为 `backfill`。
