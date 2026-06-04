# V7 与微信云托管订单对接落地方案

## 目标与边界

本方案用于让 V7 本地系统读取、审核并回写小程序经销商订单状态，同时避免云端和本地系统互相越权访问。

核心边界：

- `/api/v7/*` 只部署在微信云托管后端，是给 V7 本地系统调用的云端 API。
- V7 本地系统只作为 HTTP 客户端主动调用云托管 API，不在 V7 本地 FastAPI 服务暴露同名 `/api/v7/*` 接口。
- 云托管后端只访问云端 MySQL，不主动连接 V7 本地数据库。
- V7 本地数据库继续由 V7 自己维护，云托管不写入、不读取 V7 本地库。
- 云端 MySQL 不开放公网直连，不提供任意 SQL 执行接口。

目标链路：

```text
小程序 -> 微信云托管后端 -> 云端 MySQL
V7    -> 微信云托管后端 -> 云端 MySQL
V7    -> V7 本地数据库
```

## 系统职责划分

| 模块 | 职责 |
| --- | --- |
| 小程序 | 经销商提交订单，大区经理初审，展示订单进度；不保存 V7 专用密钥。 |
| 微信云托管 API | 提供小程序业务接口和 `/api/v7/*` 专用接口，执行鉴权、状态机校验、幂等控制、操作日志记录。 |
| 云端 MySQL | 存储小程序订单、订单明细、审核记录、V7 回写结果、幂等请求记录和操作日志。 |
| V7 本地系统 | 主动拉取待审核订单，在本地完成审核、合同、配货、订单等业务处理，再通过云托管 API 写回结果。 |

## 订单状态流转

现有状态需要包含 V7 已有的 `contracted`，完整状态如下：

```text
regional_pending   经销商提交后，等待大区经理初审
regional_rejected  大区经理驳回
pending            大区经理通过，等待 V7 审核
approved           V7 审核通过，等待合同或配货
rejected           V7 驳回
contracted         V7 已生成合同，尚未完成配货
partial_allocated  部分配货
allocated          已配货
completed          已完成
cancelled          已取消
```

允许状态转换：

| 操作 | 来源状态 | 目标状态 | 说明 |
| --- | --- | --- | --- |
| 经销商提交 | 新建 | `regional_pending` | 小程序产生订单。 |
| 大区经理通过 | `regional_pending` | `pending` | 进入 V7 待审核列表。 |
| 大区经理驳回 | `regional_pending` | `regional_rejected` | 不进入 V7。 |
| V7 审核通过 | `pending` | `approved` | 只允许从 `pending` 通过。 |
| V7 驳回 | `pending` | `rejected` | 默认只允许从 `pending` 驳回；如需补充审核前状态，必须显式配置。 |
| V7 合同写回 | `approved` | `contracted` | 写回合同号、V7 订单号等合同信息。 |
| V7 整单配货 | `approved`、`contracted` | `allocated` | MVP 使用整单配货，不传行级配货数量。 |
| V7 部分配货 | `approved`、`contracted`、`partial_allocated` | `partial_allocated` 或 `allocated` | 第二阶段能力，按明细行汇总判断状态。 |
| 完成订单 | `allocated` | `completed` | 可由小程序或云端后台按业务规则完成。 |
| 取消订单 | 非终态订单 | `cancelled` | 需要单独权限和审计。 |

小程序侧展示建议：

- MVP 可以不单独展示 `contracted`，将 `contracted` 展示为“已审核/待配货”。
- 如果业务需要跟踪合同进度，则在订单详情展示合同号和“已签约/待配货”。
- `completed` 是终态，V7 重复审核、重复合同写回、重复配货不得覆盖终态数据。

## 云托管 API 设计

所有 `/api/v7/*` 接口必须校验请求头：

```text
X-V7-API-KEY: <V7_API_KEY>
```

无密钥、错密钥、空密钥均返回 `401`。所有写接口必须记录操作日志，并支持 `Idempotency-Key` 防止重复写入。

### 读取待处理订单

```http
GET /api/v7/dealer-orders?status=pending
X-V7-API-KEY: <V7_API_KEY>
```

用途：V7 拉取已经通过大区经理初审、等待工厂审核的订单。

规则：

- 默认只返回 `pending` 订单。
- 不返回 `regional_pending`、`regional_rejected`。
- 如后续允许 V7 拉取 `approved`、`contracted` 等状态，必须显式白名单控制。

返回字段建议：

```json
{
  "id": "O202605180001",
  "orderNo": "O202605180001",
  "dealerName": "经销商名称",
  "regionalManagerName": "大区经理名称",
  "customerName": "客户名称",
  "contactName": "联系人",
  "contactPhone": "联系电话",
  "quantity": 2,
  "status": "pending",
  "createdAt": "2026-05-18 19:30:00",
  "items": [
    {
      "lineNo": 1,
      "model": "DK7745",
      "batchNo": "B2026051801",
      "eta": "2026-05-25",
      "inventoryType": "wip",
      "quantity": 2
    }
  ]
}
```

### V7 审核通过

```http
POST /api/v7/dealer-orders/{orderNo}/review
X-V7-API-KEY: <V7_API_KEY>
Idempotency-Key: <uuid>
Content-Type: application/json

{
  "status": "approved",
  "reviewedBy": "V7管理员",
  "reviewNote": "审核通过"
}
```

更新规则：

```sql
UPDATE dealer_orders
SET status = 'approved',
    approved_qty = quantity,
    reviewed_by = ?,
    reviewed_at = NOW(),
    review_note = ?
WHERE order_no = ?
  AND status = 'pending';
```

要求：

- 只能从 `pending` 更新到 `approved`。
- 影响行数为 0 时返回业务错误，例如 `409 Conflict`。
- 重复请求使用同一个 `Idempotency-Key` 时返回第一次处理结果，不重复写日志、不重复改状态。

### V7 驳回

```http
POST /api/v7/dealer-orders/{orderNo}/review
X-V7-API-KEY: <V7_API_KEY>
Idempotency-Key: <uuid>
Content-Type: application/json

{
  "status": "rejected",
  "reviewedBy": "V7管理员",
  "reviewNote": "驳回原因"
}
```

更新规则：

```sql
UPDATE dealer_orders
SET status = 'rejected',
    reviewed_by = ?,
    reviewed_at = NOW(),
    review_note = ?
WHERE order_no = ?
  AND status = 'pending';
```

要求：

- 默认只能从 `pending` 驳回。
- 如果未来允许从其他审核前状态驳回，必须在状态机配置中明确列出。

### V7 合同写回

```http
POST /api/v7/dealer-orders/{orderNo}/contract
X-V7-API-KEY: <V7_API_KEY>
Idempotency-Key: <uuid>
Content-Type: application/json

{
  "contractNo": "HT20260518001",
  "v7OrderNo": "SO20260518001",
  "contractedBy": "V7管理员"
}
```

更新规则：

```sql
UPDATE dealer_orders
SET status = 'contracted',
    contract_no = ?,
    v7_order_no = ?,
    contracted_by = ?,
    contracted_at = NOW()
WHERE order_no = ?
  AND status = 'approved';
```

要求：

- 只能从 `approved` 更新到 `contracted`。
- 不覆盖 `allocated`、`completed`、`cancelled` 等后续或终态订单。
- 如果 MVP 暂不需要单独合同写回接口，可由整单配货接口同时写入合同号，但状态规则仍需兼容 `contracted`。

### V7 整单配货写回（MVP）

```http
POST /api/v7/dealer-orders/{orderNo}/allocate
X-V7-API-KEY: <V7_API_KEY>
Idempotency-Key: <uuid>
Content-Type: application/json

{
  "contractNo": "HT20260518001",
  "v7OrderNo": "SO20260518001",
  "allocatedBy": "V7管理员"
}
```

MVP 只支持整单配货，因此请求体不包含 `allocatedQty`。云端按订单总数量写入 `allocated_qty = quantity`。

更新规则：

```sql
UPDATE dealer_orders
SET status = 'allocated',
    allocated_qty = quantity,
    contract_no = COALESCE(contract_no, ?),
    v7_order_no = COALESCE(v7_order_no, ?),
    allocated_by = ?,
    allocated_at = NOW()
WHERE order_no = ?
  AND status IN ('approved', 'contracted');
```

要求：

- 只能从 `approved` 或 `contracted` 整单配货到 `allocated`。
- 重复调用不得重复增加配货数量。
- 不允许从 `pending` 直接配货。
- 不允许覆盖 `completed`、`cancelled` 或已配货后的关键业务数据。

### V7 部分配货写回（第二阶段）

如果支持部分配货，不使用订单级 `allocatedQty`，必须按明细行写回：

```http
POST /api/v7/dealer-orders/{orderNo}/allocate-lines
X-V7-API-KEY: <V7_API_KEY>
Idempotency-Key: <uuid>
Content-Type: application/json

{
  "contractNo": "HT20260518001",
  "v7OrderNo": "SO20260518001",
  "allocatedBy": "V7管理员",
  "items": [
    {
      "lineNo": 1,
      "allocatedQty": 1
    }
  ]
}
```

规则：

- 每个 `lineNo` 必须存在于订单明细。
- 单行累计配货数量不能超过该行订单数量。
- 重复请求必须幂等，不重复累加。
- 汇总后全部明细配齐则订单状态为 `allocated`，否则为 `partial_allocated`。
- 只允许从 `approved`、`contracted`、`partial_allocated` 写回部分配货。

## V7 侧改造

V7 本地不连接微信云数据库，只新增云托管 HTTP 客户端能力。

配置项：

```text
WECHAT_CLOUD_API_BASE=https://云托管公网访问域名
V7_API_KEY=与云托管一致的密钥
```

调用要求：

```text
X-V7-API-KEY: <V7_API_KEY>
Content-Type: application/json
Idempotency-Key: <uuid> 仅写接口必填
```

建议同步流程：

1. 手动或定时拉取 `GET /api/v7/dealer-orders?status=pending`。
2. 继续使用 V7 现有 `/api/v1/dealer-orders` 页面和逻辑展示、审核订单。
3. V7 人工审核通过或驳回后调用 `/review` 写回云端。
4. V7 生成合同后调用 `/contract`，或在 MVP 中随整单配货一起写回合同号。
5. V7 完成整单配货后调用 `/allocate`。
6. 写回失败时保留本地待重试记录，按订单号和幂等键重试，不人工重复创建新请求。

失败重试策略：

- 网络失败、`5xx`：使用同一个 `Idempotency-Key` 重试。
- `401`：停止重试，检查密钥配置。
- `409`：停止自动重试，提示订单状态已变化，需要人工核对。
- `4xx` 参数错误：记录错误内容，不自动重试。

## 安全与上线要求

上线前必须项：

- 云托管 MySQL 用户必须使用低权限账号，禁止使用 `root`。
- 低权限账号只允许访问必要库表，只授予必要的 `SELECT`、`INSERT`、`UPDATE` 权限。
- `V7_API_KEY` 必须使用 32 位以上高强度随机字符串。
- `V7_API_KEY` 只允许放在云托管环境变量和 V7 本地配置中。
- 密钥不得进入小程序前端、Git、日志、截图或文档样例真实值。
- `/api/v7/*` 与小程序 `/api/dealer/*` 路由、鉴权、限流策略分离。
- 所有 `/api/v7/*` 写接口必须做状态机校验。
- 所有写接口必须记录操作日志：订单号、操作类型、操作者、请求来源 IP、请求时间、旧状态、新状态、幂等键、处理结果。
- 所有写接口必须支持幂等键，避免重复审核、重复配货、重复覆盖合同信息。
- 对 `/api/v7/*` 配置限流；如 V7 出口 IP 固定，优先增加 IP 白名单。
- 制定密钥轮换流程，支持新旧密钥短期并行，轮换完成后下线旧密钥。

禁止项：

- 禁止云托管主动连接 V7 本地数据库。
- 禁止开放 MySQL 公网直连给 V7。
- 禁止实现“执行任意 SQL”的接口。
- 禁止小程序端保存或传递 `V7_API_KEY`。
- 禁止无状态条件的 `UPDATE dealer_orders SET status = ... WHERE order_no = ?`。

## 实施步骤与验收标准

### 阶段一：只读拉取

实施内容：

1. 在云托管环境变量配置 `V7_API_KEY`。
2. 创建云端低权限 MySQL 用户并替换 `root`。
3. 在云托管后端新增 `/api/v7/dealer-orders` 读取接口。
4. V7 本地新增 HTTP 客户端配置和待审核订单拉取流程。

验收标准：

- 只读接口只返回 `pending` 及明确允许的状态订单。
- 不返回 `regional_pending`、`regional_rejected`。
- 无密钥、错密钥、空密钥均返回 `401`。
- 云托管运行账号不是 MySQL `root`。

### 阶段二：审核写回

实施内容：

1. 新增 `/api/v7/dealer-orders/{orderNo}/review`。
2. 增加状态机校验、幂等记录和操作日志。
3. V7 审核通过或驳回后写回云端。

验收标准：

- 审核通过只能从 `pending` 更新到 `approved`。
- 驳回只能从 `pending` 或明确允许的审核前状态更新到 `rejected`。
- 非法状态写入必须失败，不得静默成功。
- 重复审核请求不能产生重复日志、脏数据或覆盖后续状态。

### 阶段三：合同与配货写回

实施内容：

1. 根据 MVP 范围决定是否单独实现 `/contract`。
2. 新增 MVP 整单配货 `/allocate`。
3. 第二阶段再实现行级部分配货 `/allocate-lines`。

验收标准：

- 整单配货只能从 `approved` 或 `contracted` 更新到 `allocated`。
- MVP 整单配货请求不包含无效的 `allocatedQty`。
- 不允许从 `pending` 直接配货。
- 部分配货场景必须按 `items[{lineNo, allocatedQty}]` 写回，并正确汇总为 `partial_allocated` 或 `allocated`。
- 单行和整单配货数量不能超过订单数量。
- 重复配货请求不能重复增加配货数量，不能覆盖已完成状态。
- `completed`、`cancelled` 等终态订单不能被审核、合同或配货接口覆盖。
