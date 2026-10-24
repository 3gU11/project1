# 流程模型实现说明

> 面向开发者的精简版说明。完整版（含背景、链路详解与改进建议）见 [V8流程模型实现说明.docx](./V8流程模型实现说明.docx)。

## 一句话结论

流程模型 = **前端可视化编辑器 + 后端版本化存储 + 后端受控解释执行**。前端只负责把图画出来，后端负责存图、校验、并按图决定审批与分支；真正执行业务的是**预注册的 Python 函数**，图只能"选择"动作，不能"定义"动作。

## 三层结构

| 层次 | 载体 | 职责 | 代码位置 |
|------|------|------|----------|
| 建模层 | 浏览器 | 拖拽画图、连线、节点属性、前端校验 | `frontend/src/views/workflow/WorkflowModels.vue`（396 行） |
| 存储层 | MySQL | 模型、版本快照、实例、任务、审计日志 | `crud/workflows.py`（2120 行） |
| 运行层 | FastAPI | 校验、推进路径、解析动作、派发通知、执行 | `api/routes/workflows.py`（461 行） |

Go 服务（`server/`）**不参与流程模型**，全部逻辑在 Python 侧。

## 前端：只是编辑器

- **没有使用任何流程图库**（无 vue-flow / X6 / LogicFlow / bpmn-js）。
- 画布 = 绝对定位的 `div` 节点 + 一层 `<svg><line>` 连线；坐标由 `getBoundingClientRect` 与鼠标位置算出。
- 连线方式：**依次点击两个节点**。撤销/重做 = 整份 `{nodes, edges}` 快照压栈。
- 6 种节点：`start` / `approval` / `execute` / `condition` / `notify` / `end`。
- 产出物只有一份 JSON，保存走 `POST /workflows/models/{key}/draft`，发布走 `.../publish`。

## 存储：版本钉住

- 图存在 `workflow_model_versions.node_snapshot`（JSON）。
- 一个模型最多一条"草稿"；发布生成新版本号，旧版本置"历史"且**永不修改**。
- 实例创建时写入 `model_version_id` → **改模型不影响在途流程**。

## 运行时：后端读图的 5 个位置

| 函数 | 时机 | 作用 |
|------|------|------|
| `validate_workflow_snapshot` | 保存 / 发布 | 全量校验图（比前端更严） |
| `_snapshot_requires_approval` | 发布 | 有 approval 节点 → `processing_type` 记为"需要审批" |
| `_approval_config` | 创建实例 | 找出审批节点与角色，按待办数最少选审批人，排除发起人 |
| `_advance_approved_graph` | 自动通过 / 审批通过 | 沿图走一遍：求值条件、收集通知角色、记录经过节点 |
| `workflow_action_for_instance` | 执行前 | 从日志 + 钉住快照中解析出**唯一** action |

路径推进结果写入 `workflow_audit_logs`，`action='模型路径推进'`。**后续所有"这条实例走了哪条路"的判断都靠回读这份日志**，不重跑图。

### 能力边界

- 条件字段白名单仅 3 个：`bound_machine_count`、`shipped_machine_count`、`item_count`
- 比较符仅 3 个：`gt`、`eq`、`exists`
- 全图**只允许 1 个审批节点**，所有分支必须共用；每条路径**只允许 1 个 execute 节点**

## 执行：动作是硬编码的

- `WORKFLOW_ACTIONS` 把动作名映射到执行器（`execute_allocation_recall`、`execute_order_delete` 等事务函数）。
- `REVERSE_WORKFLOW_ACTIONS` 限定每个流程可用的动作集，配错在发布时被拒。
- 逆向：直接调对应 `execute_*` 函数。
- 正向：`submit_entry` → 流程引擎 → `execute_forward_entry` → `_invoke` → **回调原业务函数**。
  靠 `ContextVar`（`_replay`）区分"流程入口"与"业务执行体"，避免无限递归，业务逻辑只有一份。

### 幂等与并发

| 机制 | 载体 | 作用 |
|------|------|------|
| 幂等键 | `workflow_instances.idempotency_key` | 重复提交返回已有实例 |
| 业务回执 | `workflow_business_receipts` | 正向执行前插"执行中"，非"成功"则拒绝重跑 |
| 执行租约 | `workflow_execution_attempts` | 过期可回收重试 |
| 对象锁 | `workflow_object_locks` | 同一对象不允许并存多个未完成逆向流程 |

## 为什么不是通用引擎

| 约束 | 目的 |
|------|------|
| 单审批节点、单执行节点 | 一次流程只建一条审批任务、只触发一个业务事务 |
| 字段与动作白名单 | 防止配置注入任意查询或代码 |
| 无环、无不可达节点 | 保证推进必然终止 |

图能表达的是「审批顺序 + 单一条件分叉 + 通知对象 + 一个动作」，仅此而已。这是为事务一致性刻意收窄的。



## 访问控制

流程模型整个界面（含菜单、路由、数据接口）**仅 `admin` 与 `boss` 可访问**，其他角色既看不到菜单，直接输 URL 也会被拦到 403 页。

| 层次 | 实现 |
|------|------|
| 菜单 | `router/index.ts` 的路由定义加 `roles: ['admin', 'boss']`，`getAccessibleMenus(permissions, role)` 按角色过滤 |
| 路由守卫 | `canAccessPath(path, permissions, role)` 命中 `roles` 不匹配即跳 403 |
| 接口 | `GET /workflows/models`、`GET /workflows/models/{key}/versions` 改为 `require_roles('admin','boss')`；写接口原本就限定这两个角色 |

> 其他页面若要限定角色，给对应路由加 `roles: [...]` 即可，与 `permission` 是"与"关系。

## 编辑器接口

| 操作 | 接口 | 说明 |
|------|------|------|
| 保存草稿 | `POST /workflows/models/{key}/draft` | 覆盖该模型唯一草稿 |
| 删除草稿 | `DELETE /workflows/models/{key}/draft` | 只删草稿版本，已发布版本不受影响 |
| 发布新版本 | `POST /workflows/models/{key}/publish` | 校验后生成新版本，旧版本转"历史" |
| 复制模型 | `POST /workflows/models/{key}/duplicate` | 生成 `xxx-copy` 未发布草稿 |
| 停用 | `POST /workflows/models/{key}/disable` | 业务侧查不到可运行版本，在途流程不受影响 |
| 启用 | `POST /workflows/models/{key}/enable` | 恢复当前已发布版本，不产生新版本 |

> 动作白名单与条件字段白名单由 `GET /workflows/models` 的 `catalog` 字段下发，
> 前端不再维护副本（`actionLabels` 只保留中文显示名）。

## 已修复问题（2026-10-24）

| 问题 | 处理 |
|------|------|
| "复制 / 发布 / 停用 / 删除草稿"四个按钮只改本地数组 | 全部接到真实接口（见上表），操作后重新拉取列表 |
| `models` 硬编码 12 条假数据，接口失败静默展示 | 初始值改为空数组；`loadModels` 补 `catch` 并提示错误，表格加 `v-loading` |
| 前后端两套校验规则漂移 | 动作与条件字段白名单改由后端 `catalog` 下发，前端只做展示 |
| `start.assigneesText`、`execute.targetState` 不生效 | 从界面与默认图生成逻辑中移除 |

## 仍待处理

1. 复制出来的 `xxx-copy` 没有删除模型的接口，误操作会留下空模型，只能手工清库。
2. 条件字段仍只有 3 个业务语义（机台数量相关），不支持逻辑与/或组合。
3. `frontend/dist` 是提交进仓库的构建产物，改动后需 `npm run build` 才会同步到静态部署。

## 关键代码索引

```
frontend/src/views/workflow/WorkflowModels.vue   画布、校验、保存发布
api/routes/workflows.py                          路由：models / instances / tasks / approve
crud/workflows.py                                建表、校验、图推进、执行器、发布
crud/forward_entries.py                          正向流程入口与递归回放
```
