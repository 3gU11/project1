# V8 业务逻辑架构与时序图

核对日期：2026-09-22。依据当前工作区代码（含尚未提交的修改），不是线上部署验证。外部系统只描述本仓库可见的交互契约，不推断其内部实现。

时序图表达操作先后及模块协作，不能独自表达全部静态架构。因此先给组件关系，再给业务总览和分流程。图中箭头表示调用或数据操作，不意味着整条链处在同一数据库事务中。

## 1. 组件与职责

```mermaid
flowchart LR
    PC[PC 管理端] --> P[Python FastAPI 业务服务]
    M[移动端 / PDA] --> P
    PC --> G[Go 调度与照片服务]
    M --> G
    P -->|沙盘代理及内部协作| G
    P --> DB[(共享 MySQL)]
    G --> DB
    P --> F[合同与机台附件存储]
    G --> R[照片存储与识别服务]
    P <--> C[小程序云端]
    P <--> X[外部维修 / 采购系统]
    S[维修快照同步工具] --> DB
    S --> X
```

照片接口通过前端代理进入 Go；普通业务接口进入 Python；沙盘多数请求由 Python 校验或处理后转发 Go，也有 Python 直接实现的业务操作。两种后端共享数据库，不是数据库完全隔离的微服务。外部联接是否启用取决于配置和实际部署。

## 2. 业务全景时序

```mermaid
sequenceDiagram
    autonumber
    actor U as 销售 / 计划 / 仓库
    participant C as 小程序云端
    participant P as V8 业务服务
    participant G as 排产与生产服务
    participant D as 业务数据库
    participant X as 外部维修系统
    alt 经销商订单入口
        C-->>P: 通过同步接口提供订单与审核信息
        U->>P: 审核并转合同
    else 本地业务入口
        U->>P: 录入合同或直接创建销售订单
    end
    P->>D: 保存合同 / 订单及关联关系
    opt 需要生产
        U->>P: 预测重算、确认批次、安排产线
        P->>G: 沙盘及产线操作
        G->>D: 更新批次、机台、队列和产线
    end
    opt 配货或批次预占后的二次确认
        U->>P: 选择符合条件的库存或在产机台
        P->>D: 绑定订单、合同与机台
    end
    opt 新生产机台实际入库
        U->>P: 扫流水号并选择库位
        P->>D: 更新库位和状态、记录入库事件
        P->>G: 通知入库完成
    end
    U->>P: 发货复核与确认
    P->>D: 标记已出库，后续更新订单和归档日志
    P-->>C: 后台同步订单状态与库存摘要
    opt 售后联接已配置
        X->>P: 查询机台或部件身份 / 提交换件结果
        P->>D: 查询档案或更新部件绑定
    end
    U->>P: 查询报表、机台档案和追溯
    P->>D: 按相应统计口径读取数据
    P-->>U: 展示结果或导出文件
```

入库和配货的先后可以不同：现货可先入库后配货，在产机台可以先配货后入库；也可以先生产备库再接受销售订单。本图展示协作主线，不要求每笔业务执行全部步骤。

## 3. 订单入口、审核与合同

```mermaid
sequenceDiagram
    actor U as 业务人员
    participant C as 小程序云端
    participant P as Python 订单与合同模块
    participant D as MySQL
    participant O as 同步任务
    U->>P: 拉取云端订单
    P->>C: 请求订单数据
    C-->>P: 订单、审核状态和附加备注
    P->>D: 同步 dealer_orders
    Note over C,P: 区域初审和总部审核属于不同阶段，不能等同于配货确认
    U->>P: 审核通过或拒绝
    P->>D: 保存审核结果
    P->>O: 登记云端状态同步事件
    opt 审核通过并转合同
        U->>P: 预览并确认转合同
        P->>D: 建立 factory_plan 及订单关联
        P->>O: 登记转合同同步事件
    end
    opt 本地直接录入
        U->>P: 创建合同 / 创建销售订单
        P->>D: 保存 factory_plan / sales_orders
    end
    O-->>C: 异步回写业务状态
```

合同承载生产需求；销售订单承载配货和交付；经销商订单承载外部订单及审核状态。三者有关联，但不是同一张表或同一个状态机。

依据：`api/routes/dealer_orders.py`、`api/routes/planning.py`、`crud/dealer_orders.py`。

## 4. 预测排产与生产执行

```mermaid
sequenceDiagram
    actor U as 计划员
    participant P as Python 沙盘入口
    participant G as Go 调度服务
    participant D as MySQL
    U->>P: 配置产能比例并请求预测重算
    P->>G: 转发预测任务
    G->>D: 读取需求及排产数据，重算预测批次与机台
    G-->>P: 任务状态 / 结果
    P-->>U: 沙盘结果
    U->>P: 确认批次
    P->>D: 计算批次影响与阻塞风险
    alt 存在阻塞风险
        P-->>U: 拒绝确认并返回风险
    else 可以确认
        P->>G: 确认批次
        G->>D: 保存确认状态
    end
    opt 同步规划或建立待入库记录
        U->>P: 同步到计划 / 导入成品表
        P->>D: 按接口规则同步关联记录
    end
    U->>P: 分配批次或机台到产线
    P->>G: 产线分配
    G->>D: 更新 production_lines、batches、units
    opt 急单、换位、跨批移动或锁定
        U->>P: 提交调整
        P->>G: 转发对应调度操作
        G->>D: 校验并更新受影响排产数据
    end
    Note over P,G: 部分换机与业务关联在 Python 实现，不能把所有修改都归入 Go
```

预测批次、确认批次、投产和实际入库是不同节点。确认或导入成品表不等于完成实物入库；待排队列也不能直接当作库存。

依据：`api/routes/sandbox.py`、`server/internal/router/router.go`。

## 5. 合同批次规划与销售配货

```mermaid
sequenceDiagram
    actor U as 合同管理员 / 配货员
    participant P as Python 规划与配货模块
    participant D as MySQL
    alt 合同选择整批适配机台
        U->>P: 查询 eligible-batches
        P->>D: 按合同需求筛选可规划批次与空卡
        P-->>U: 候选批次
        U->>P: plan-batch
        P->>D: 锁定合同、批次和候选机台
        P->>D: 创建待二次确认销售订单并预占 units
        P->>D: 关联合同，清理该合同的预测占位及待排需求
        P-->>U: 返回预占结果
        U->>P: confirm-batch-allocation
        P->>D: 锁定并复核机台集合、机型、合同与批次
        alt 已有可用库存或符合实际在产条件
            P->>D: 成品记录置待发货，订单置 ready
            P-->>U: 二次确认成功
        else 尚未投产或存在占用冲突
            P-->>U: 拒绝确认，保留待核查状态
        end
    else 普通销售订单配货
        U->>P: 创建订单并提交所选流水号
        P->>D: 锁定订单与候选机台，校验占用和配货资格
        P->>D: 绑定客户、合同、订单并更新待发货记录
        P-->>U: 返回配货结果
    end
    opt 撤回配货
        U->>P: 释放订单配货
        P->>D: 按来源和当前业务状态恢复记录
    end
```

“待二次确认”是预占阶段；只有已确认批次但尚未投产，不足以通过二次确认。“待发货”和订单 `ready` 也不自动证明实物已入库。

依据：`crud/batch_planning.py:141`、`crud/batch_planning.py:221`、`crud/orders.py:318`、`api/routes/planning.py`。

## 6. 实物入库、调拨和发货

```mermaid
sequenceDiagram
    actor U as 仓库人员
    participant P as Python 库存模块
    participant D as MySQL
    participant G as 生产协作服务
    participant O as 后台同步
    U->>P: 流水号、目标库位、入库或调拨模式
    P->>D: 检查库位与容量，锁定机台记录
    alt 普通实物入库
        P->>D: 结合订单预占情况更新状态与库位
        P->>D: 同事务记录 inbound_history
        P->>D: 提交入库事务
        P->>G: 通知入库完成并检查生产进度
        P->>D: 按条件更新已配货订单状态
    else 库位调拨
        P->>D: 更新目标库位和对应状态
        Note over P,D: 调拨不写成一次新的生产入库事件
    end
    P->>O: 登记库存摘要同步
    P-->>U: 返回结果并通知界面刷新
    U->>P: 确认发货
    P->>D: 锁定成品记录，排除报废及重复出库
    P->>D: 提交已出库状态
    P->>D: 后续统计订单出库数量，满足需求则置 done
    P->>D: 归档发货数据并记录日志
    P->>O: 登记关联经销商订单完成及库存同步
    opt 撤回发货或退货
        U->>P: 提交对应逆向业务
        P->>D: 执行各自恢复逻辑并记录原因
    end
```

代码边界：`shipping/confirm` 当前未完整强制校验“必须待发货且已有实际入库记录”。因此图中不能写成系统已经保证“未入库绝不允许发货”。库存出库、订单完成、归档和云端事件也不在同一个整体事务里。这里记录事实，不代表认可该规则；若要建立严格交付闭环，应另行补齐前置校验及失败补偿。

依据：`crud/inventory.py`、`api/routes/inventory.py:1251`、`crud/orders.py:477`。

## 7. 机台档案、拍照识别与维修联接

```mermaid
sequenceDiagram
    actor U as 档案 / 现场人员
    participant G as Go 照片服务
    participant R as 识别服务
    participant P as Python 档案与维修接口
    participant D as 数据库及文件存储
    participant X as 外部维修系统
    U->>G: 按机型初始化照片任务
    G->>D: 读取拍照配置并建立任务
    U->>G: 上传照片，请求二维码或 OCR 识别
    G->>R: 识别请求
    R-->>G: 识别结果
    G-->>U: 返回待确认结果
    U->>G: 确认识别信息并提交机台照片
    G->>D: 保存任务、照片及相关数据
    opt 合同或机台附件维护
        U->>P: 上传、预览或下载附件
        P->>D: 访问对应文件归档
    end
    opt 维修联接配置有效
        X->>P: 携服务凭证查询机台、部件身份或目录
        P->>D: 读取身份绑定和目录
        P-->>X: 返回查询结果
        X->>P: 提交换件事件和幂等键
        P->>D: 锁定绑定并校验事件与版本
        alt 已处理或发生冲突
            P-->>X: 返回已处理结果或冲突
        else 可应用换件
            P->>D: 更新绑定并保存换件事件
            P-->>X: 返回处理结果
        end
    end
```

维修工单内部审核、领料及结算不属于本仓库可验证的流程。另有 `repair_sync` 出站快照工具；代码存在不证明线上已开启或完成对接。

依据：`server/internal/router/router.go`、`api/routes/repair_identity.py`、`api/routes/repair_catalog.py`、`crud/repair_component_replacements.py`、`repair_sync/README.md`。

## 8. 异步同步、实时刷新与报表追溯

```mermaid
sequenceDiagram
    participant B as 业务操作
    participant D as MySQL
    participant W as Watcher / Outbox Worker
    participant C as 外部云服务
    actor U as 管理人员
    participant P as Python 查询与报表
    B->>D: 保存本地业务数据
    B->>D: 登记适用的 cloud_sync_outbox 事件
    Note over B,D: 部分事件在业务提交后另行写入，并非全链路原子事务
    loop 后台轮询
        W->>D: 检查订单或库存变化及待发送事件
        W-->>U: WebSocket 变化通知
        W->>C: 发送适用的状态或摘要同步
        alt 同步成功
            W->>D: 标记事件同步成功
        else 网络或远端失败
            W->>D: 保存失败信息、重试次数和下次重试时间
        end
    end
    U->>P: 查询库存、追溯、订单或生产报表
    P->>D: 读取对应业务表、入库历史和日志
    P-->>U: 预览结果 / Excel 文件
```

WebSocket 是刷新通知，最终展示内容仍需以接口读取为准。当前库存快照、生产进度、首次入库完工口径和发货数量是不同指标，不能直接互相替代。不同时间请求的预览与导出也不能默认是同一份快照。

依据：`api/main.py`、`crud/cloud_sync_outbox.py`、`crud/reports.py`、`api/routes/reports.py`、`api/routes/traceability.py`。

## 9. 阅读这些图时的关键边界

| 领域 | 主要事实来源 | 不应混淆的概念 |
| --- | --- | --- |
| 合同需求 | factory_plan | 合同不等于销售订单 |
| 销售履约 | sales_orders | 预占、配货与实物发货不同 |
| 外部订单 | dealer_orders | 审核状态不等于机台状态 |
| 生产执行 | batches、units、production_lines、production_queue | 预测、待投产、在产、完工不同 |
| 库存与位置 | finished_goods_data、库位配置 | 表内有记录不等于已有实物库存 |
| 入库事件 | inbound_history | 当前状态不等于历史首次入库时间 |
| 机台身份 | machine_component_bindings 等档案数据 | 身份绑定不等于当前仓库位置 |
| 同步状态 | cloud_sync_outbox | 本地提交成功不等于远端同步成功 |

登录、用户角色、权限、机型字典、库位布局、日志和缓存是贯穿业务的支撑模块。前端根据权限组织菜单，后端在各自入口实施鉴权；本次没有逐接口审计权限，也没有执行数据库写操作或线上联调。

本次只新增说明文档。以上是当前实现的模块级业务地图，不是每个分支都经过运行验证的形式化规格。
