# V7 与微信云托管对接落地方案

## 目标

让 V7 能读取并更新小程序产生的经销商订单，同时不直接暴露云数据库，也不影响 V7 本地数据库安全。

最终链路：

```text
小程序 -> 微信云托管后端 -> 云端 MySQL
V7    -> 微信云托管后端 -> 云端 MySQL
V7    -> V7 本地数据库
```

云托管不主动连接 V7 本地数据库。V7 主动调用云托管 API，同步需要的数据和状态。

## 当前订单状态流转

```text
regional_pending   经销商提交后，等待大区经理初审
regional_rejected  大区经理驳回
pending            大区经理通过，等待 V7 审核
approved           V7 审核通过
rejected           V7 驳回
partial_allocated  部分配货
allocated          已配货
cancelled          已取消
```

V7 只处理 `pending` 及之后的状态。大区经理未初审通过的订单，不进入 V7 审核。

## 云托管需要开放的内容

只开放 HTTPS API，不开放 MySQL 公网直连，不开放任意 SQL 接口。

云托管服务：

```text
环境 ID: prod-d8g4equko61c410ed
服务名: sever
端口: 80
目标目录: server
Dockerfile: Dockerfile
```

环境变量：

```text
MYSQL_ADDRESS=10.4.105.5:3306
MYSQL_USERNAME=root
MYSQL_PASSWORD=实际密码
MYSQL_DATABASE=rjfinshed
FINISHED_GOODS_TABLE=wechat_batch_summary
V7_API_KEY=一串很长的随机密钥
```

后续建议把 `root` 换成低权限 MySQL 用户，只允许访问 `rjfinshed` 库中必要表。

## V7 专用 API 设计

所有 `/api/v7/*` 接口必须校验请求头：

```text
X-V7-API-KEY: 与云托管环境变量 V7_API_KEY 一致
```

没有密钥或密钥错误，直接返回 `401`。

### 读取待审核订单

```http
GET /api/v7/dealer-orders?status=pending
X-V7-API-KEY: <V7_API_KEY>
```

用途：

V7 拉取已经通过大区经理初审、等待工厂审核的订单。

返回字段建议包含：

```json
{
  "id": "O202605180001",
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

### V7 审核订单

```http
POST /api/v7/dealer-orders/{orderNo}/review
X-V7-API-KEY: <V7_API_KEY>
Content-Type: application/json

{
  "status": "approved",
  "reviewedBy": "V7管理员",
  "reviewNote": "审核通过"
}
```

通过时更新：

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

驳回时：

```json
{
  "status": "rejected",
  "reviewedBy": "V7管理员",
  "reviewNote": "驳回原因"
}
```

对应更新：

```sql
UPDATE dealer_orders
SET status = 'rejected',
    reviewed_by = ?,
    reviewed_at = NOW(),
    review_note = ?
WHERE order_no = ?
AND status = 'pending';
```

### V7 配货完成

```http
POST /api/v7/dealer-orders/{orderNo}/allocate
X-V7-API-KEY: <V7_API_KEY>
Content-Type: application/json

{
  "contractNo": "HT20260518001",
  "v7OrderNo": "SO20260518001",
  "allocatedQty": 2
}
```

更新逻辑：

```sql
UPDATE dealer_orders
SET status = 'allocated',
    allocated_qty = quantity,
    contract_no = ?,
    v7_order_no = ?
WHERE order_no = ?
AND status IN ('approved', 'pending');
```

如果后续支持部分配货，则按行更新 `allocated_qty`，再根据整单汇总状态显示 `partial_allocated`。

## V7 侧需要做的事

V7 不需要连接微信云数据库。V7 只需要增加 HTTP 请求能力。

需要配置：

```text
WECHAT_CLOUD_API_BASE=https://云托管公网访问域名
V7_API_KEY=与云托管一致的密钥
```

调用时统一带请求头：

```text
X-V7-API-KEY: <V7_API_KEY>
Content-Type: application/json
```

建议 V7 操作流程：

1. 定时或手动拉取 `GET /api/v7/dealer-orders?status=pending`
2. 在 V7 界面显示待审核经销商订单
3. V7 人工审核后调用 `/review`
4. V7 生成合同、订单、机台绑定后调用 `/allocate`
5. V7 本地数据库继续由 V7 自己维护，云托管不访问 V7 本地库

## 安全边界

必须避免：

```text
不要把 V7 本地数据库密码写入云托管
不要让云托管主动连接 V7 本地数据库
不要开放 MySQL 公网直连给 V7
不要实现“执行任意 SQL”的接口
不要把 V7_API_KEY 提交到 GitHub
不要在小程序前端保存 V7_API_KEY
```

推荐措施：

```text
V7_API_KEY 使用 32 位以上随机字符串
V7_API_KEY 只放在云托管环境变量和 V7 本地配置中
/api/v7/* 与 /api/dealer/* 分开
所有 V7 写操作都限制订单当前状态
所有 V7 写操作记录操作人和时间
云数据库后续换低权限用户
```

## 最小实施步骤

1. 在云托管环境变量增加 `V7_API_KEY`
2. 后端增加 `/api/v7/*` 接口和密钥校验
3. V7 增加 HTTP 客户端配置
4. V7 先只读取 `pending` 订单
5. 确认读取稳定后，再接入 V7 审核写回
6. 最后接入 V7 配货、合同号、订单号写回

## 验收标准

1. 大区经理未通过的订单不会出现在 V7 待审核列表
2. 大区经理通过后，订单状态变成 `pending`
3. V7 能读取 `pending` 订单
4. V7 审核通过后，小程序订单显示为 `approved`
5. V7 驳回后，小程序订单显示为 `rejected`
6. V7 配货后，小程序订单显示为 `allocated`
7. 不配置正确 `X-V7-API-KEY` 时，所有 `/api/v7/*` 接口返回 `401`
