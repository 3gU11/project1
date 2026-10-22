<template>
  <div class="workflow-page">
    <div class="page-head">
      <div>
        <h1>流程模型 <el-badge v-if="pendingCount > 0" :value="pendingCount > 99 ? '99+' : pendingCount" class="workflow-badge" /></h1>
        <p class="intro">统一维护业务操作流程；发布版本控制审批、自动执行和通知，已发起的流程保留原版本。</p>
      </div>
    </div>

    <div class="toolbar">
      <el-input v-model="keyword" clearable placeholder="搜索流程名称、Key 或业务对象" class="search-input" />
      <el-select v-model="direction" clearable placeholder="全部方向" class="filter-select">
        <el-option label="正向流程" value="正向" />
        <el-option label="逆向流程" value="逆向" />
      </el-select>
      <el-select v-model="mode" clearable placeholder="全部处理方式" class="filter-select">
        <el-option label="自动通过" value="自动通过" />
        <el-option label="需要审批" value="需要审批" />
      </el-select>
    </div>

    <section v-for="group in filteredGroups" :key="group.title" class="model-group">
      <button class="group-head" type="button" @click="toggleGroup(group.title)">
        <span class="group-title"><span class="chevron" :class="{ expanded: isExpanded(group.title) }">›</span><strong>{{ group.title }}</strong></span>
        <span class="group-count">{{ group.items.length }} 个流程</span>
      </button>
      <div v-if="isExpanded(group.title)" class="table-wrap">
        <el-table :data="group.items" stripe>
          <el-table-column prop="name" label="流程名称" min-width="180" />
          <el-table-column label="方向" width="90">
            <template #default="{ row }"><el-tag :type="row.direction === '逆向' ? 'warning' : 'success'" effect="plain">{{ row.direction }}</el-tag></template>
          </el-table-column>
          <el-table-column label="处理方式" width="110">
            <template #default="{ row }"><span :class="row.mode === '需要审批' ? 'approval-mode' : 'auto-mode'">{{ row.mode }}</span></template>
          </el-table-column>
          <el-table-column prop="visibility" label="可见范围" min-width="120" />
          <el-table-column prop="key" label="流程 Key" min-width="170" />
          <el-table-column prop="object" label="业务对象" min-width="120" />
          <el-table-column prop="form" label="表单信息" min-width="130" />
          <el-table-column label="最后发布" min-width="145">
            <template #default="{ row }"><span>{{ row.publishedAt || '未发布' }}</span><small v-if="row.version" class="version">{{ row.version }}</small></template>
          </el-table-column>
          <el-table-column label="状态" width="90">
            <template #default="{ row }"><el-tag :type="statusType(row.status)" effect="light">{{ row.status }}</el-tag></template>
          </el-table-column>
          <el-table-column label="操作" fixed="right" width="210">
            <template #default="{ row }">
              <el-button v-if="canEdit" link type="primary" @click="editModel(row)">编辑</el-button>
              <el-button v-else link type="primary" @click="editModel(row)">查看</el-button>
              <el-button v-if="row.draftSnapshot" link type="warning" @click="editModel(row, true)">查看草稿</el-button>
              <el-button link @click="copyModel(row)">复制</el-button>
              <el-button v-if="row.status === '未发布' || row.status === '已停用'" link type="success" @click="publishModel(row)">发布</el-button>
              <el-button v-else link type="warning" @click="disableModel(row)">停用</el-button>
              <el-dropdown trigger="click" @command="(command: string) => handleCommand(command, row)">
                <el-button link>更多</el-button>
                <template #dropdown><el-dropdown-menu><el-dropdown-item command="detail">查看详情</el-dropdown-item><el-dropdown-item command="history">历史版本查看</el-dropdown-item><el-dropdown-item command="delete">删除草稿</el-dropdown-item></el-dropdown-menu></template>
              </el-dropdown>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </section>
    <el-empty v-if="filteredGroups.length === 0" description="没有匹配的流程模型" />

    <el-dialog v-model="designer.visible" :title="`编辑流程：${designer.model?.name || ''}`" width="92%" top="4vh" destroy-on-close>
      <div class="designer">
        <aside class="node-palette">
          <strong>节点</strong>
          <div v-for="type in nodeTypes" :key="type.type" class="palette-node" draggable="true" @dragstart="startDrag(type)">
            <span class="node-icon">{{ type.icon }}</span>{{ type.label }}
          </div>
          <p class="palette-tip">拖动节点到画布，点击节点编辑属性。连线通过选择前后两个节点创建。</p>
        </aside>
        <section class="designer-canvas" @dragover.prevent="!preview && $event.preventDefault()" @drop="!preview && dropNode($event)">
          <div class="canvas-toolbar"><el-button v-if="preview && canEdit" size="small" type="primary" @click="enterEditMode">编辑</el-button><el-button v-else-if="!preview" size="small" @click="enterPreviewMode">预览</el-button><el-button v-if="!preview" size="small" @click="undo">撤销</el-button><el-button v-if="!preview" size="small" @click="redo">重做</el-button><span>{{ designer.draft.nodes.length }} 个节点 · {{ designer.draft.edges.length }} 条连线</span></div>
          <div class="canvas-board" :class="{ preview }">
            <svg class="flow-edges" aria-hidden="true"><defs><marker id="flow-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#64748b" /></marker></defs><line v-for="edge in designer.draft.edges" :key="`${edge.source}-${edge.target}`" :x1="(designer.draft.nodes.find(n => n.id === edge.source)?.x || 0) + 110" :y1="(designer.draft.nodes.find(n => n.id === edge.source)?.y || 0) + 29" :x2="designer.draft.nodes.find(n => n.id === edge.target)?.x || 0" :y2="(designer.draft.nodes.find(n => n.id === edge.target)?.y || 0) + 29" stroke="#64748b" stroke-width="2" marker-end="url(#flow-arrow)" /></svg>
            <div v-for="node in designer.draft.nodes" :key="node.id" class="flow-node" :class="{ selected: designer.selectedId === node.id }" :style="{ left: `${node.x}px`, top: `${node.y}px` }" @click.stop="selectNode(node.id)" @dblclick.stop="!preview && removeNode(node.id)">
              <span class="node-icon">{{ iconFor(node.type) }}</span><b>{{ node.label }}</b><small>{{ node.type }}</small>
            </div>
            <div v-if="designer.draft.nodes.length === 0" class="canvas-empty">从左侧拖入节点开始设计</div>
          </div>
        </section>
        <aside class="node-properties" :class="{ 'preview-properties': preview }">
          <strong>节点属性</strong>
          <template v-if="selectedNode">
            <el-form label-position="top" size="small"><el-form-item label="节点名称"><el-input v-model="selectedNode.label" /></el-form-item><el-form-item label="节点类型"><el-input :model-value="selectedNode.type" disabled /></el-form-item><el-form-item v-if="selectedNode.type === 'approval' || selectedNode.type === 'start'" :label="selectedNode.type === 'start' ? '发起人' : '审批角色'"><el-select v-if="selectedNode.type === 'approval'" v-model="selectedNode.approvalRoles" multiple collapse-tags placeholder="选择审批角色" style="width:100%"><el-option v-for="role in workflowRoles" :key="role.role_id" :label="role.role_name || role.role_id" :value="role.role_id" /></el-select><el-input v-else v-model="selectedNode.assigneesText" placeholder="发起人规则（可选）" /><small class="field-help">审批时按模型保存的角色自动生成任务，不在业务操作时临时选择人员。</small></el-form-item><el-form-item v-if="selectedNode.type === 'notify'" label="通知角色"><el-select v-model="selectedNode.notifyRoles" multiple collapse-tags collapse-tags-tooltip placeholder="选择接收通知的角色" style="width:100%"><el-option v-for="role in workflowRoles" :key="role.role_id" :label="role.role_name || role.role_id" :value="role.role_id" /></el-select><small class="field-help">仅在流程模型中配置角色，运行时自动通知该角色的用户。</small></el-form-item><el-form-item v-if="selectedNode.type === 'condition'" label="条件表达式"><el-select v-model="selectedNode.conditionField" placeholder="选择业务字段" style="width:100%"><el-option label="绑定机台数量" value="bound_machine_count"/><el-option label="已发货机台数量" value="shipped_machine_count"/><el-option label="流程对象数量" value="item_count"/></el-select><el-select v-model="selectedNode.conditionOperator" placeholder="比较符" style="width:100%;margin-top:6px"><el-option label=">" value="gt"/><el-option label="=" value="eq"/><el-option label="存在" value="exists"/></el-select><el-input-number v-model="selectedNode.conditionValue" :min="0" :precision="0" controls-position="right" style="width:100%;margin-top:6px"/><small class="field-help">条件节点的两条连线会自动标记为 true 和 false。</small></el-form-item><el-form-item v-if="selectedNode.type === 'execute'" label="业务动作"><el-select v-model="selectedNode.action" placeholder="选择已注册动作" style="width:100%"><el-option v-for="action in actionOptions" :key="action.value" :label="action.label" :value="action.value"/></el-select></el-form-item></el-form>
            <el-button type="danger" plain size="small" @click="removeNode(selectedNode.id)">删除节点</el-button>
          </template><el-empty v-else description="选择节点后编辑" :image-size="70" />
          <div class="edge-help"><template v-if="!preview"><b>创建连线</b><p>依次点击两个节点即可创建连线；条件节点的每条线需标记结果。</p></template><b v-else>流程连线</b><el-tag v-for="edge in designer.draft.edges" :key="`${edge.source}-${edge.target}`" :closable="!preview" @close="!preview && removeEdge(edge)">{{ nodeLabel(edge.source) }} → {{ nodeLabel(edge.target) }}<template v-if="edge.sourceType === 'condition'">（{{ edge.branch || '未设置' }}）</template></el-tag></div>
        </aside>
      </div>
      <template #footer><el-button @click="designer.visible=false">取消</el-button><el-button @click="saveDraft">保存草稿</el-button><el-button type="primary" @click="publishDraft">发布新版本</el-button></template>
    </el-dialog>

    <el-dialog v-model="historyVisible" :title="`历史版本：${historyModel?.name || ''}`" width="92%" top="4vh" destroy-on-close>
      <div class="history-toolbar">
        <el-select v-model="historyVersion" placeholder="选择版本" style="width: 220px" @change="selectHistoryVersion">
          <el-option v-for="version in historyVersions" :key="version.version_no" :label="`v${version.version_no}.0${version.status === '草稿' ? '（草稿）' : ''}`" :value="version.version_no" />
        </el-select>
        <span v-if="selectedHistoryVersion" class="history-meta">{{ selectedHistoryVersion.status }} · {{ selectedHistoryVersion.published_at || '未发布' }}<template v-if="selectedHistoryVersion.published_by"> · {{ selectedHistoryVersion.published_by }}</template></span>
      </div>
      <div class="history-board-wrap">
        <div class="canvas-board preview history-board">
          <svg class="flow-edges" aria-hidden="true"><defs><marker id="history-flow-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#64748b" /></marker></defs><line v-for="edge in historySnapshot.edges" :key="`${edge.source}-${edge.target}`" :x1="(historySnapshot.nodes.find(n => n.id === edge.source)?.x || 0) + 110" :y1="(historySnapshot.nodes.find(n => n.id === edge.source)?.y || 0) + 29" :x2="historySnapshot.nodes.find(n => n.id === edge.target)?.x || 0" :y2="(historySnapshot.nodes.find(n => n.id === edge.target)?.y || 0) + 29" stroke="#64748b" stroke-width="2" marker-end="url(#history-flow-arrow)" /></svg>
          <div v-for="node in historySnapshot.nodes" :key="node.id" class="flow-node" :style="{ left: `${node.x}px`, top: `${node.y}px` }"><span class="node-icon">{{ iconFor(node.type) }}</span><b>{{ node.label }}</b><small>{{ node.type }}</small></div>
          <div v-if="historySnapshot.nodes.length === 0" class="canvas-empty">该版本没有流程图数据</div>
        </div>
      </div>
      <template #footer><el-button @click="historyVisible = false">关闭</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { apiGet, apiPost } from '../../utils/request'
import { useUserStore } from '../../store/user'

type Model = {
  name: string; category: string; direction: '正向' | '逆向'; mode: '自动通过' | '需要审批'; visibility: string
  key: string; object: string; form: string; status: '未发布' | '已发布' | '已停用'; version?: string; publishedAt?: string; snapshot?: { nodes: FlowNode[]; edges: FlowEdge[] }; draftSnapshot?: { nodes: FlowNode[]; edges: FlowEdge[] }
}
type FlowNode = { id: string; type: string; label: string; x: number; y: number; assigneesText?: string; targetState?: string; notifyRoles?: string[]; approvalRoles?: string[]; conditionField?: string; conditionOperator?: string; conditionValue?: number; branches?: { true?: string; false?: string }; action?: string }
type FlowEdge = { source: string; target: string; branch?: 'true' | 'false'; sourceType?: string }

const keyword = ref('')
const direction = ref('')
const mode = ref('')
const expanded = ref(new Set(['合同流程', '订单流程', '发货流程', '库存流程', '配货流程', '客户成品流程', '基础资料流程', '数据清理流程']))

const models = ref<Model[]>([
  { name: '合同创建', category: '合同流程', direction: '正向', mode: '自动通过', visibility: '销售部', key: 'contract-create', object: '销售合同', form: '合同主表', status: '已发布', version: 'v1.0', publishedAt: '2026-10-08 10:20' },
  { name: '取消合同', category: '合同流程', direction: '逆向', mode: '需要审批', visibility: '全体人员', key: 'contract-cancel', object: '销售合同', form: '逆向操作单', status: '已发布', version: 'v1.0', publishedAt: '2026-10-08 10:22' },
  { name: '创建销售订单', category: '订单流程', direction: '正向', mode: '自动通过', visibility: '销售部', key: 'order-create', object: '销售订单', form: '订单主表', status: '已发布', version: 'v1.0', publishedAt: '2026-10-08 10:25' },
  { name: '删除订单', category: '订单流程', direction: '逆向', mode: '需要审批', visibility: '全体人员', key: 'order-delete', object: '销售订单', form: '逆向操作单', status: '已发布', version: 'v1.0', publishedAt: '2026-10-08 10:27' },
  { name: '订单配货', category: '配货流程', direction: '正向', mode: '自动通过', visibility: '仓储部', key: 'allocation-create', object: '配货单', form: '配货明细', status: '已发布', version: 'v1.0', publishedAt: '2026-10-08 10:30' },
  { name: '撤回配货', category: '配货流程', direction: '逆向', mode: '需要审批', visibility: '全体人员', key: 'allocation-recall', object: '配货单', form: '逆向操作单', status: '已发布', version: 'v1.0', publishedAt: '2026-10-08 10:32' },
  { name: '成品入库', category: '库存流程', direction: '正向', mode: '自动通过', visibility: '仓储部', key: 'stock-inbound', object: '机台', form: '入库单', status: '已发布', version: 'v1.0', publishedAt: '2026-10-08 10:35' },
  { name: '发货确认', category: '发货流程', direction: '正向', mode: '自动通过', visibility: '仓储部', key: 'shipment-confirm', object: '发货单', form: '发货复核单', status: '已发布', version: 'v1.0', publishedAt: '2026-10-08 10:38' },
  { name: '发货撤回', category: '发货流程', direction: '逆向', mode: '自动通过', visibility: '全体人员', key: 'shipment-recall', object: '发货单', form: '逆向操作单', status: '未发布' },
  { name: '客户成品核销发货撤回', category: '客户成品流程', direction: '逆向', mode: '需要审批', visibility: '全体人员', key: 'customer-finished-recall', object: '客户成品', form: '核销单', status: '未发布' },
  { name: '删除机型字典', category: '基础资料流程', direction: '逆向', mode: '需要审批', visibility: '全体人员', key: 'model-dict-delete', object: '机型字典', form: '逆向操作单', status: '未发布' },
  { name: '数据清理', category: '数据清理流程', direction: '正向', mode: '自动通过', visibility: '管理员', key: 'data-cleanup', object: '业务数据', form: '清理任务单', status: '已停用', version: 'v1.0', publishedAt: '2026-09-30 16:00' },
])
const loading = ref(false)
const nodeTypes = [{ type: 'start', label: '发起', icon: '▶' }, { type: 'approval', label: '审批', icon: '✓' }, { type: 'execute', label: '自动执行', icon: '⚙' }, { type: 'condition', label: '条件分支', icon: '?' }, { type: 'notify', label: '通知', icon: '!' }, { type: 'end', label: '结束', icon: '■' }]
const designer = ref<{ visible: boolean; model: Model | null; selectedId: string | null; draft: { nodes: FlowNode[]; edges: FlowEdge[] }; history: string[]; future: string[] }>({ visible: false, model: null, selectedId: null, draft: { nodes: [], edges: [] }, history: [], future: [] })
const preview = ref(false)
const historyVisible = ref(false)
const historyModel = ref<Model | null>(null)
const historyVersions = ref<any[]>([])
const historyVersion = ref<number | null>(null)
const historySnapshot = ref<{ nodes: FlowNode[]; edges: FlowEdge[] }>({ nodes: [], edges: [] })
const selectedHistoryVersion = computed(() => historyVersions.value.find(item => item.version_no === historyVersion.value))
const userStore = useUserStore()
const approvers = ref<any[]>([])
const workflowRoles = ref<any[]>([])
const pendingCount = ref(0)
const canEdit = computed(() => ['admin', 'boss'].includes(String(userStore.userInfo?.role || '').toLowerCase()))
const selectedNode = computed(() => designer.value.draft.nodes.find(node => node.id === designer.value.selectedId))
const actionRegistry = [
  { label: '创建合同', value: 'create_contract', workflowKey: 'contract-create' },
  { label: '创建销售订单', value: 'create_sales_order', workflowKey: 'order-create' },
  { label: '执行订单配货', value: 'allocate_order', workflowKey: 'allocation-create' },
  { label: '成品入库', value: 'inbound_machine', workflowKey: 'stock-inbound' },
  { label: '库位转移', value: 'transfer_machine', workflowKey: 'stock-transfer' },
  { label: '确认发货', value: 'confirm_shipment', workflowKey: 'shipment-confirm' },
  { label: '保存客户机台规划', value: 'save_customer_machine_plan', workflowKey: 'customer-machine-plan' },
  { label: '取消合同', value: 'cancel_contract', workflowKey: 'contract-cancel' },
  { label: '取消合同并释放机台', value: 'cancel_contract_reinbound', workflowKey: 'contract-cancel' },
  { label: '删除订单', value: 'delete_order', workflowKey: 'order-delete' },
  { label: '删除订单并派生重入库', value: 'delete_order_reinbound', workflowKey: 'order-delete' },
  { label: '撤回配货', value: 'recall_allocation', workflowKey: 'allocation-recall' },
  { label: '撤回发货', value: 'recall_shipment', workflowKey: 'shipment-recall' },
  { label: '撤回客户成品发货', value: 'recall_customer_finished', workflowKey: 'customer-finished-recall' },
  { label: '客户成品订单发货', value: 'ship_customer_order', workflowKey: 'customer-order-shipped' },
  { label: '停用机型', value: 'disable_model', workflowKey: 'model-dict-delete' },
]
const actionOptions = computed(() => actionRegistry.filter(action => action.workflowKey === designer.value.model?.key))
const normalizeSnapshot = (input: any) => {
  const snapshot = JSON.parse(JSON.stringify(input || { nodes: [], edges: [] }))
  const byId = new Map<string, any>((snapshot.nodes || []).map((node: any) => [String(node.id), node] as [string, any]))
  const grouped = new Map<string, any[]>()
  for (const edge of snapshot.edges || []) {
    const source = byId.get(String(edge.source))
    if (source?.type === 'condition') {
      const list = grouped.get(String(edge.source)) || []
      list.push(edge)
      grouped.set(String(edge.source), list)
    }
  }
  for (const [source, edges] of grouped) {
    const used = new Set(edges.map(edge => edge.branch).filter(Boolean))
    for (const edge of edges) {
      edge.sourceType = 'condition'
      if (!edge.branch) edge.branch = used.has('true') ? 'false' : 'true'
      used.add(edge.branch)
    }
    const node = byId.get(source)
    if (node) node.branches = Object.fromEntries(edges.map(edge => [edge.branch, edge.target]))
  }
  return snapshot
}
const iconFor = (type: string) => nodeTypes.find(item => item.type === type)?.icon || '•'
const nodeLabel = (id: string) => designer.value.draft.nodes.find(node => node.id === id)?.label || nodeTypes.find(item => item.type === id.split('-')[0])?.label || id
const snapshot = () => JSON.stringify(designer.value.draft)
const record = () => { designer.value.history.push(snapshot()); designer.value.future = [] }
const startDrag = (type: any) => { designer.value.selectedId = type.type }
const dropNode = (event: DragEvent) => { const type = nodeTypes.find(item => item.type === designer.value.selectedId) || nodeTypes[0]; record(); const rect = (event.currentTarget as HTMLElement).querySelector('.canvas-board')!.getBoundingClientRect(); const id = `${type.type}-${Date.now()}`; designer.value.draft.nodes.push({ id, type: type.type, label: type.label, x: Math.max(12, event.clientX - rect.left - 55), y: Math.max(48, event.clientY - rect.top - 24) }); designer.value.selectedId = id }
const selectNode = (id: string) => { if (preview.value) { designer.value.selectedId = id; return }; if (designer.value.selectedId && designer.value.selectedId !== id) { const source = designer.value.draft.nodes.find(node => node.id === designer.value.selectedId); const edge: FlowEdge = { source: designer.value.selectedId, target: id }; if (source?.type === 'condition') { edge.sourceType = 'condition'; edge.branch = designer.value.draft.edges.some(item => item.source === source.id && item.branch === 'true') ? 'false' : 'true' } if (!designer.value.draft.edges.some(item => item.source === edge.source && item.target === edge.target)) { record(); designer.value.draft.edges.push(edge) } } designer.value.selectedId = id }
const enterEditMode = () => { designer.value.selectedId = null; preview.value = false }
const enterPreviewMode = () => { designer.value.selectedId = null; preview.value = true }
const removeNode = (id: string) => { record(); designer.value.draft.nodes = designer.value.draft.nodes.filter(node => node.id !== id); designer.value.draft.edges = designer.value.draft.edges.filter(edge => edge.source !== id && edge.target !== id); designer.value.selectedId = null }
const removeEdge = (edge: FlowEdge) => { record(); designer.value.draft.edges = designer.value.draft.edges.filter(item => item !== edge) }
const validateDraft = () => {
  const { nodes, edges } = designer.value.draft
  const byId = new Map(nodes.map(node => [node.id, node]))
  const starts = nodes.filter(node => node.type === 'start')
  if (starts.length !== 1 || !nodes.some(node => node.type === 'end')) return '流程必须且只能有一个发起节点，并包含结束节点'
  const reverseKeys = new Set(actionRegistry.map(action => action.workflowKey))
  const isReverse = reverseKeys.has(designer.value.model?.key || '')
  const outgoing = new Map<string, string[]>()
  const branches = new Map<string, Set<string>>()
  for (const edge of edges) {
    const source = byId.get(edge.source)
    if (!source || !byId.has(edge.target) || edge.source === edge.target) return '流程存在无效连线'
    outgoing.set(edge.source, [...(outgoing.get(edge.source) || []), edge.target])
    if (source.type === 'condition') {
      if (edge.branch !== 'true' && edge.branch !== 'false') return '条件分支连线必须标记 true 或 false'
      const used = branches.get(edge.source) || new Set<string>()
      if (used.has(edge.branch)) return '条件分支的 true/false 出口不能重复'
      used.add(edge.branch)
      branches.set(edge.source, used)
    }
  }
  for (const node of nodes) {
    if (!['start', 'approval', 'execute', 'condition', 'notify', 'end'].includes(node.type)) return `不支持的流程节点类型：${node.type || '(空)'}`
    const degree = outgoing.get(node.id)?.length || 0
    if (node.type === 'end' && degree !== 0) return '结束节点不能再连接后续节点'
    if (node.type === 'condition' && degree !== 2) return '条件分支必须且只能有 true 和 false 两条连线'
    if (!['condition', 'end'].includes(node.type) && degree !== 1) return `节点“${node.label || node.id}”必须且只能有一条后续连线`
    if (node.type === 'condition' && branches.get(node.id)?.size !== 2) return '条件分支必须各配置一条 true 和 false 连线'
    if (node.type === 'approval' && !node.approvalRoles?.length) return '审批节点必须配置审批角色'
    if (node.type === 'notify' && !node.notifyRoles?.length) return '通知节点必须配置通知角色'
    if (node.type === 'execute' && !node.action) return '自动执行节点必须配置业务动作'
    if (node.type === 'execute' && !actionRegistry.some(action => action.value === node.action && (!isReverse || action.workflowKey === designer.value.model?.key))) return `动作“${node.action}”不适用于当前流程`
    if (node.type === 'condition' && (!node.conditionField || !node.conditionOperator)) return '条件分支必须配置业务字段和比较符'
    if (node.type === 'condition' && !['bound_machine_count', 'shipped_machine_count', 'item_count'].includes(node.conditionField || '')) return '条件分支业务字段不受支持'
    if (node.type === 'condition' && !['gt', 'eq', 'exists'].includes(node.conditionOperator || '')) return '条件分支比较符不受支持'
    if (node.type === 'condition' && (!Number.isFinite(Number(node.conditionValue ?? 0)) || Number(node.conditionValue ?? 0) < 0)) return '条件分支比较值必须是非负数字'
  }
  const visiting = new Set<string>()
  const memo = new Map<string, [number, number, number, number]>()
  const walk = (id: string): [number, number, number, number] => {
    if (visiting.has(id)) throw new Error('流程图不允许循环连线')
    const cached = memo.get(id)
    if (cached) return cached
    visiting.add(id)
    const node = byId.get(id)!
    const next = (outgoing.get(id) || []).map(walk)
    // An end node contributes zero nodes to the remaining path. Without this
    // base case Math.min(...[]) becomes Infinity and falsely reports that an
    // approval node is missing from every branch.
    const tails = next.length ? next : [[0, 0, 0, 0] as [number, number, number, number]]
    visiting.delete(id)
    const result: [number, number, number, number] = [
      Number(node.type === 'approval') + Math.min(...tails.map(item => item[0])),
      Number(node.type === 'approval') + Math.max(...tails.map(item => item[1])),
      Number(node.type === 'execute') + Math.min(...tails.map(item => item[2])),
      Number(node.type === 'execute') + Math.max(...tails.map(item => item[3])),
    ]
    memo.set(id, result)
    return result
  }
  try {
    const counts = walk(starts[0].id)
    if (memo.size !== nodes.length) return '流程存在从发起节点不可达的节点'
    if (nodes.filter(node => node.type === 'approval').length > 1) return '当前流程运行时只支持一个审批节点，且必须供所有分支共用'
    if (counts[1] > 1) return '当前流程运行时只支持一个审批节点，且必须供所有分支共用'
    if (nodes.some(node => node.type === 'approval') && counts[0] !== 1) return '存在审批节点时，所有流程分支都必须经过该审批节点'
    if (counts[3] > 1) return '同一流程路径只支持一个业务执行节点'
    if (isReverse && (counts[2] !== 1 || counts[3] !== 1)) return '逆向流程的每条路径必须且只能有一个业务执行节点'
  } catch (error) { return error instanceof Error ? error.message : '流程图无效' }
  return ''
}
const undo = () => { const previous = designer.value.history.pop(); if (!previous) return; designer.value.future.push(snapshot()); designer.value.draft = JSON.parse(previous) }
const redo = () => { const next = designer.value.future.pop(); if (!next) return; designer.value.history.push(snapshot()); designer.value.draft = JSON.parse(next) }
const loadModels = async () => {
  loading.value = true
  try {
    const response = await apiGet<{ data: any[] }>('/workflows/models')
    models.value = (response.data || []).map((item) => ({
      name: item.name, category: item.category_key, direction: item.direction,
      mode: item.processing_type, visibility: item.execution_scope, key: item.workflow_key,
      object: item.business_object, form: item.business_object,
      status: item.status === '草稿' ? '未发布' : item.status,
      version: item.current_version ? `v${item.current_version}.0` : undefined,
      publishedAt: item.updated_at ? String(item.updated_at).replace('T', ' ').slice(0, 16) : undefined,
      snapshot: item.node_snapshot ? normalizeSnapshot(typeof item.node_snapshot === 'string' ? JSON.parse(item.node_snapshot) : item.node_snapshot) : undefined,
      draftSnapshot: item.draft_snapshot ? normalizeSnapshot(typeof item.draft_snapshot === 'string' ? JSON.parse(item.draft_snapshot) : item.draft_snapshot) : undefined,
    }))
  } finally { loading.value = false }
}
const loadPendingCount = async () => {
  try {
    const response = await apiGet<{ data?: any[] }>('/workflows/tasks?status=%E5%BE%85%E5%A4%84%E7%90%86&limit=500')
    const username = String(userStore.userInfo?.username || '')
    pendingCount.value = (response.data || []).filter((task: any) => String(task.assignee_id || '') === username).length
  } catch { pendingCount.value = 0 }
}
onMounted(loadModels)
onMounted(loadPendingCount)
onMounted(async () => { if (!canEdit.value) return; try { const options = await apiGet<{users:any[]; roles:any[]}>('/workflows/configuration-options'); approvers.value = options.users || []; workflowRoles.value = options.roles || [] } catch {} })

const categories = ['合同流程', '订单流程', '发货流程', '库存流程', '配货流程', '客户成品流程', '基础资料流程', '数据清理流程']
const filteredGroups = computed(() => categories.map(category => ({ title: category, items: models.value.filter(item => item.category === category && (!direction.value || item.direction === direction.value) && (!mode.value || item.mode === mode.value) && (!keyword.value || `${item.name}${item.key}${item.object}`.toLowerCase().includes(keyword.value.toLowerCase()))) })).filter(group => group.items.length))
const isExpanded = (title: string) => expanded.value.has(title)
const toggleGroup = (title: string) => { const next = new Set(expanded.value); next.has(title) ? next.delete(title) : next.add(title); expanded.value = next }
const statusType = (status: Model['status']) => status === '已发布' ? 'success' : status === '已停用' ? 'info' : 'warning'
const editModel = (row: Model, viewDraft = false) => {
  const selectedSnapshot = viewDraft ? row.draftSnapshot : row.snapshot
  if (selectedSnapshot?.nodes?.length) {
    designer.value = { visible: true, model: row, selectedId: null, draft: normalizeSnapshot(selectedSnapshot), history: [], future: [] }
    preview.value = true
    return
  }
  const reverse = row.direction === '逆向'
  const automatic = row.mode === '自动通过'
  const notifyAfterExecution = row.key !== 'model-dict-delete'
  const nodes: FlowNode[] = reverse
    ? automatic
      ? [
        { id: 'start', type: 'start', label: '发起', x: 35, y: 120 },
        { id: 'execute', type: 'execute', label: '自动执行', x: 220, y: 120, targetState: '按业务执行器处理' },
        { id: 'notify', type: 'notify', label: '通知', x: 405, y: 120, notifyRoles: ['Inbound'] },
        { id: 'end', type: 'end', label: '结束', x: 590, y: 120 },
      ]
      : notifyAfterExecution ? [
        { id: 'start', type: 'start', label: '发起', x: 35, y: 120 },
        { id: 'approval', type: 'approval', label: '审批', x: 220, y: 120, approvalRoles: ['Boss'] },
        { id: 'execute', type: 'execute', label: '自动执行', x: 405, y: 120, targetState: '按业务执行器处理' },
        { id: 'notify', type: 'notify', label: '通知', x: 590, y: 120, notifyRoles: ['Inbound'] },
        { id: 'end', type: 'end', label: '结束', x: 775, y: 120 },
      ] : [
        { id: 'start', type: 'start', label: '发起', x: 35, y: 120 },
        { id: 'approval', type: 'approval', label: '审批', x: 220, y: 120, approvalRoles: ['Boss'] },
        { id: 'execute', type: 'execute', label: '自动执行', x: 405, y: 120, targetState: '按业务执行器处理' },
        { id: 'end', type: 'end', label: '结束', x: 590, y: 120 },
      ]
    : [{ id: 'start', type: 'start', label: '发起', x: 60, y: 120 }, { id: 'end', type: 'end', label: '结束', x: 430, y: 120 }]
  const edges: FlowEdge[] = reverse
    ? automatic
      ? [{ source: 'start', target: 'execute' }, { source: 'execute', target: 'notify' }, { source: 'notify', target: 'end' }]
      : notifyAfterExecution
        ? [{ source: 'start', target: 'approval' }, { source: 'approval', target: 'execute' }, { source: 'execute', target: 'notify' }, { source: 'notify', target: 'end' }]
        : [{ source: 'start', target: 'approval' }, { source: 'approval', target: 'execute' }, { source: 'execute', target: 'end' }]
    : [{ source: 'start', target: 'end' }]
  designer.value = { visible: true, model: row, selectedId: null, draft: { nodes, edges }, history: [], future: [] }; preview.value = true
}
const saveDraft = async () => { const error = validateDraft(); if (error) { ElMessage.error(error); return }; if (!designer.value.model) return; try { await apiPost(`/workflows/models/${encodeURIComponent(designer.value.model.key)}/draft`, { snapshot: designer.value.draft }); ElMessage.success('流程草稿已保存'); designer.value.visible = false; await loadModels() } catch { /* request interceptor displays the server error */ } }
const publishDraft = async () => { const error = validateDraft(); if (error) { ElMessage.error(error); return }; if (!designer.value.model) return; try { await apiPost<{ data: { version: number } }>(`/workflows/models/${encodeURIComponent(designer.value.model.key)}/publish`, { snapshot: designer.value.draft }); ElMessage.success('流程新版本已发布并生效'); designer.value.visible = false; await loadModels() } catch { /* request interceptor displays the server error */ } }
const copyModel = (row: Model) => { models.value.push({ ...row, name: `${row.name}（副本）`, key: `${row.key}-copy`, status: '未发布', version: undefined, publishedAt: undefined }); ElMessage.success('已复制为未发布草稿') }
const publishModel = (row: Model) => { row.status = '已发布'; row.version = row.version || 'v1.0'; row.publishedAt = new Date().toLocaleString('zh-CN', { hour12: false }); ElMessage.success(`已发布「${row.name}」`) }
const disableModel = (row: Model) => { row.status = '已停用'; ElMessage.success(`已停用「${row.name}」`) }
const handleCommand = async (command: string, row: Model) => {
  if (command === 'detail') { await ElMessageBox.alert(`<p><b>流程 Key：</b>${row.key}</p><p><b>业务对象：</b>${row.object}</p><p><b>处理方式：</b>${row.mode}</p>`, `流程详情：${row.name}`, { dangerouslyUseHTMLString: true }); return }
  if (command === 'history') { await openHistory(row); return }
  if (row.status !== '未发布') { ElMessage.warning('只有未发布草稿可以删除'); return }
  models.value = models.value.filter(item => item !== row); ElMessage.success('草稿已删除')
}
const parseHistorySnapshot = (value: any): { nodes: FlowNode[]; edges: FlowEdge[] } => {
  if (!value) return { nodes: [], edges: [] }
  try { const parsed = typeof value === 'string' ? JSON.parse(value) : value; return { nodes: Array.isArray(parsed?.nodes) ? parsed.nodes : [], edges: Array.isArray(parsed?.edges) ? parsed.edges : [] } } catch { return { nodes: [], edges: [] } }
}
const selectHistoryVersion = () => { const version = selectedHistoryVersion.value; historySnapshot.value = parseHistorySnapshot(version?.node_snapshot) }
const openHistory = async (row: Model) => {
  try {
    const response = await apiGet<{ data: any[] }>(`/workflows/models/${encodeURIComponent(row.key)}/versions`)
    historyModel.value = row
    historyVersions.value = response.data || []
    historyVersion.value = historyVersions.value[0]?.version_no ?? null
    historySnapshot.value = parseHistorySnapshot(historyVersions.value[0]?.node_snapshot)
    historyVisible.value = true
  } catch { /* request interceptor displays the server error */ }
}
</script>

<style scoped>
.workflow-page{padding:28px;max-width:1500px}.page-head{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:20px}h1{margin:0 0 8px;font-size:24px;color:#1f2937}.workflow-badge{vertical-align:top;margin-left:8px}.intro{margin:0;color:#64748b}.toolbar{display:flex;gap:12px;margin-bottom:20px}.search-input{width:320px}.filter-select{width:160px}.model-group{margin-bottom:18px;border:1px solid #e5e7eb;border-radius:8px;background:#fff;overflow:hidden}.group-head{display:flex;justify-content:space-between;align-items:center;width:100%;padding:14px 18px;border:0;background:#f8fafc;color:#1f2937;cursor:pointer;text-align:left}.group-head:hover{background:#f1f5f9}.group-title{display:flex;align-items:center;gap:8px}.group-count{font-size:13px;color:#94a3b8}.chevron{display:inline-block;font-size:22px;line-height:12px;transform:rotate(0deg);transition:transform .15s}.chevron.expanded{transform:rotate(90deg)}.table-wrap{border-top:1px solid #e5e7eb}.approval-mode{color:#d97706}.auto-mode{color:#059669}.version{display:block;color:#94a3b8;font-size:12px;margin-top:2px}.designer{display:grid;grid-template-columns:170px 1fr 240px;gap:12px;min-height:560px}.node-palette,.node-properties{border:1px solid #e5e7eb;padding:14px;background:#f8fafc}.palette-node{padding:10px;margin-top:8px;background:#fff;border:1px solid #dbe3ee;border-radius:6px;cursor:grab}.node-icon{display:inline-flex;width:24px;height:24px;align-items:center;justify-content:center;margin-right:7px;border-radius:50%;background:#e0ecff;color:#2563eb}.palette-tip,.edge-help{font-size:12px;color:#64748b;line-height:1.6}.designer-canvas{border:1px solid #dbe3ee;overflow:auto}.canvas-toolbar{height:42px;padding:8px 12px;display:flex;align-items:center;gap:8px;border-bottom:1px solid #e5e7eb;color:#64748b;font-size:12px}.canvas-board{position:relative;min-width:760px;height:510px;background-color:#fff;background-image:radial-gradient(#d7dee8 1px,transparent 1px);background-size:18px 18px}.canvas-board.preview{background-color:#f8fafc}.flow-node{position:absolute;width:110px;min-height:58px;padding:8px;border:2px solid #cbd5e1;border-radius:8px;background:#fff;cursor:pointer;box-shadow:0 2px 6px #00000012}.flow-node.selected{border-color:#2563eb;box-shadow:0 0 0 2px #93c5fd}.flow-node b,.flow-node small{display:block}.flow-node small{color:#64748b;font-size:11px}.canvas-empty{padding:220px;text-align:center;color:#94a3b8}.node-properties{background:#fff}.edge-help{margin-top:18px}.edge-help .el-tag{margin:3px}
@media (max-width:900px){.workflow-page{padding:16px}.toolbar{flex-wrap:wrap}.search-input{width:100%}.filter-select{flex:1;min-width:140px}.table-wrap{overflow-x:auto}}
 .flow-edges{position:absolute;inset:0;width:100%;height:100%;pointer-events:none;z-index:0}.flow-node{z-index:1}.canvas-board.preview .flow-node{cursor:default}.preview-properties{pointer-events:none;opacity:.75}.field-help{display:block;color:#64748b;font-size:11px;line-height:1.5}
.history-toolbar{display:flex;align-items:center;gap:14px;margin-bottom:12px}.history-meta{color:#64748b;font-size:13px}.history-board-wrap{border:1px solid #dbe3ee;overflow:auto}.history-board{min-width:900px}
</style>

