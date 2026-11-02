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
        <el-table v-loading="loading" :data="group.items" stripe>
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
          <div v-for="type in nodeTypes" :key="type.type" class="palette-node" draggable="true" @dragstart="startDrag(type, $event)">
            <span class="node-icon">{{ type.icon }}</span>{{ type.label }}
          </div>
          <p class="palette-tip">拖动节点到画布后，可直接按住节点拖到任意位置。点击节点只编辑属性；连线请先点工具栏「连线」，再依次点击起点和终点。</p>
        </aside>
        <section class="designer-canvas">
          <div class="canvas-toolbar">
            <el-button v-if="preview && canEdit" size="small" type="primary" @click="enterEditMode">编辑</el-button>
            <template v-else-if="!preview">
              <el-button size="small" @click="enterPreviewMode">预览</el-button>
              <el-button size="small" :type="linkMode ? 'primary' : 'default'" @click="toggleLinkMode">连线</el-button>
              <el-button size="small" :disabled="!designer.history.length" @click="undo">撤销</el-button>
              <el-button size="small" :disabled="!designer.future.length" @click="redo">重做</el-button>
            </template>
            <span class="toolbar-divider"></span>
            <el-button size="small" text @click="zoomOut">−</el-button>
            <el-button size="small" text class="zoom-value" @click="resetZoom">{{ Math.round(zoom * 100) }}%</el-button>
            <el-button size="small" text @click="zoomIn">+</el-button>
            <el-button size="small" text @click="fitToView">适应画布</el-button>
            <span class="canvas-stat">{{ designer.draft.nodes.length }} 个节点 · {{ designer.draft.edges.length }} 条连线</span>
          </div>
          <div v-if="!preview && linkMode" class="link-hint" :class="{ active: !!linkSourceId }">
            <span v-if="linkSourceId">已选起点「{{ nodeLabel(linkSourceId) }}」，点击目标节点完成连线（点空白或按 Esc 取消）</span>
            <span v-else>连线模式：先点击起点节点，再点击目标节点</span>
            <el-button link size="small" @click="toggleLinkMode">退出连线</el-button>
          </div>
          <div ref="viewportRef" class="canvas-viewport" @dragover="onDragOver" @drop="onDrop" @dragleave="onDragLeave" @wheel="onWheel">
            <div class="board-scale-box" :style="{ width: `${boardW * zoom}px`, height: `${boardH * zoom}px` }">
              <div ref="boardRef" class="canvas-board" :class="{ preview, 'link-mode': linkMode && !preview, 'drag-over': dragOver }" :style="{ width: `${boardW}px`, height: `${boardH}px`, transform: `scale(${zoom})` }" @click.self="onBoardClick">
                <svg class="flow-edges" aria-hidden="true">
                  <defs><marker id="flow-arrow" markerWidth="9" markerHeight="9" refX="8" refY="4.5" orient="auto"><path d="M0,0 L9,4.5 L0,9 z" fill="#64748b" /></marker></defs>
                  <g v-for="edge in designer.draft.edges" :key="`${edge.source}-${edge.target}`">
                    <path :d="edgePath(edge)" fill="none" stroke="#94a3b8" stroke-width="2" marker-end="url(#flow-arrow)" />
                    <text v-if="edgeBranchLabel(edge)" :x="edgeMidPoint(edge).x" :y="edgeMidPoint(edge).y - 8" class="edge-label" text-anchor="middle">{{ edgeBranchLabel(edge) }}</text>
                  </g>
                </svg>
                <div
                  v-for="node in designer.draft.nodes"
                  :key="node.id"
                  class="flow-node"
                  :class="{ selected: designer.selectedId === node.id, 'link-source': linkMode && linkSourceId === node.id, 'link-target': linkMode && !!linkSourceId && linkSourceId !== node.id }"
                  :style="{ left: `${node.x}px`, top: `${node.y}px` }"
                  @mousedown.stop="onNodeMouseDown(node, $event)"
                  @click.stop="onNodeClick(node)"
                >
                  <span class="node-icon">{{ iconFor(node.type) }}</span><b>{{ node.label }}</b><small>{{ node.type }}</small>
                  <span v-if="linkMode && !preview" class="node-port"></span>
                </div>
                <div v-if="designer.draft.nodes.length === 0" class="canvas-empty">从左侧拖入节点开始设计</div>
              </div>
            </div>
          </div>
        </section>
        <aside class="node-properties" :class="{ 'preview-properties': preview }">
          <strong>节点属性</strong>
          <template v-if="selectedNode">
            <el-form label-position="top" size="small"><el-form-item label="节点名称"><el-input v-model="selectedNode.label" /></el-form-item><el-form-item label="节点类型"><el-input :model-value="selectedNode.type" disabled /></el-form-item><el-form-item v-if="selectedNode.type === 'approval'" label="审批角色"><el-select v-model="selectedNode.approvalRoles" multiple collapse-tags placeholder="选择审批角色" style="width:100%"><el-option v-for="role in workflowRoles" :key="role.role_id" :label="role.role_name || role.role_id" :value="role.role_id" /></el-select><small class="field-help">审批时按模型保存的角色自动生成任务，不在业务操作时临时选择人员。</small></el-form-item><el-form-item v-if="selectedNode.type === 'notify'" label="通知角色"><el-select v-model="selectedNode.notifyRoles" multiple collapse-tags collapse-tags-tooltip placeholder="选择接收通知的角色" style="width:100%"><el-option v-for="role in workflowRoles" :key="role.role_id" :label="role.role_name || role.role_id" :value="role.role_id" /></el-select><small class="field-help">仅在流程模型中配置角色，运行时自动通知该角色的用户。</small></el-form-item><el-form-item v-if="selectedNode.type === 'condition'" label="条件表达式"><el-select v-model="selectedNode.conditionField" placeholder="选择业务字段" style="width:100%"><el-option v-for="field in conditionFields" :key="field.value" :label="field.label" :value="field.value"/></el-select><el-select v-model="selectedNode.conditionOperator" placeholder="比较符" style="width:100%;margin-top:6px"><el-option v-for="op in conditionOperators" :key="op.value" :label="op.label" :value="op.value"/></el-select><el-input-number v-model="selectedNode.conditionValue" :min="0" :precision="0" controls-position="right" style="width:100%;margin-top:6px"/><small class="field-help">条件节点的两条连线会自动标记为 true 和 false。</small></el-form-item><el-form-item v-if="selectedNode.type === 'execute'" label="业务动作"><el-select v-model="selectedNode.action" placeholder="选择已注册动作" style="width:100%"><el-option v-for="action in actionOptions" :key="action.value" :label="action.label" :value="action.value"/></el-select></el-form-item></el-form>
            <el-button plain size="small" :type="linkMode && linkSourceId === selectedNode.id ? 'primary' : 'default'" @click="startLinkFromSelected">从此节点开始连线</el-button>
            <el-button type="danger" plain size="small" @click="removeNode(selectedNode.id)">删除节点</el-button>
          </template><el-empty v-else description="选择节点后编辑" :image-size="70" />
          <div class="edge-help"><template v-if="!preview"><b>创建连线</b><p>点工具栏「连线」进入连线模式，依次点击起点和终点；条件节点的两条出口会自动标记为「是」「否」。</p></template><b v-else>流程连线</b><el-tag v-for="edge in designer.draft.edges" :key="`${edge.source}-${edge.target}`" :closable="!preview" @close="!preview && removeEdge(edge)">{{ nodeLabel(edge.source) }} → {{ nodeLabel(edge.target) }}<template v-if="edge.sourceType === 'condition'">（{{ edge.branch || '未设置' }}）</template></el-tag></div>
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
        <span class="history-zoom">
          <el-button size="small" text @click="historyZoomOut">−</el-button>
          <span class="zoom-value">{{ Math.round(historyZoom * 100) }}%</span>
          <el-button size="small" text @click="historyZoomIn">+</el-button>
          <el-button size="small" text @click="fitHistory">适应画布</el-button>
        </span>
      </div>
      <div class="history-board-wrap">
        <div class="canvas-viewport history-viewport" ref="historyViewportRef">
          <div class="board-scale-box" :style="{ width: `${historyBoardW * historyZoom}px`, height: `${historyBoardH * historyZoom}px` }">
            <div class="canvas-board preview history-board" :style="{ width: `${historyBoardW}px`, height: `${historyBoardH}px`, transform: `scale(${historyZoom})` }">
              <svg class="flow-edges" aria-hidden="true"><defs><marker id="history-flow-arrow" markerWidth="9" markerHeight="9" refX="8" refY="4.5" orient="auto"><path d="M0,0 L9,4.5 L0,9 z" fill="#64748b" /></marker></defs><path v-for="edge in historySnapshot.edges" :key="`${edge.source}-${edge.target}`" :d="edgePathOf(historySnapshot, edge)" fill="none" stroke="#94a3b8" stroke-width="2" marker-end="url(#history-flow-arrow)" /></svg>
              <div v-for="node in historySnapshot.nodes" :key="node.id" class="flow-node" :style="{ left: `${node.x}px`, top: `${node.y}px` }"><span class="node-icon">{{ iconFor(node.type) }}</span><b>{{ node.label }}</b><small>{{ node.type }}</small></div>
              <div v-if="historySnapshot.nodes.length === 0" class="canvas-empty">该版本没有流程图数据</div>
            </div>
          </div>
        </div>
      </div>
      <template #footer><el-button @click="historyVisible = false">关闭</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { apiDelete, apiGet, apiPost, getApiErrorMessage } from '../../utils/request'
import { useUserStore } from '../../store/user'

type Model = {
  name: string; category: string; direction: '正向' | '逆向'; mode: '自动通过' | '需要审批'; visibility: string
  key: string; object: string; form: string; status: '未发布' | '已发布' | '已停用'; version?: string; publishedAt?: string; snapshot?: { nodes: FlowNode[]; edges: FlowEdge[] }; draftSnapshot?: { nodes: FlowNode[]; edges: FlowEdge[] }
}
type FlowNode = { id: string; type: string; label: string; x: number; y: number;  notifyRoles?: string[]; approvalRoles?: string[]; conditionField?: string; conditionOperator?: string; conditionValue?: number; branches?: { true?: string; false?: string }; action?: string }
type FlowEdge = { source: string; target: string; branch?: 'true' | 'false'; sourceType?: string }

const keyword = ref('')
const direction = ref('')
const mode = ref('')
const expanded = ref(new Set(['合同流程', '订单流程', '发货流程', '库存流程', '配货流程', '客户成品流程', '基础资料流程', '数据清理流程']))

const models = ref<Model[]>([])
const loading = ref(false)
const nodeTypes = [{ type: 'start', label: '发起', icon: '▶' }, { type: 'approval', label: '审批', icon: '✓' }, { type: 'execute', label: '自动执行', icon: '⚙' }, { type: 'condition', label: '条件分支', icon: '?' }, { type: 'notify', label: '通知', icon: '!' }, { type: 'end', label: '结束', icon: '■' }]
const designer = ref<{ visible: boolean; model: Model | null; selectedId: string | null; draft: { nodes: FlowNode[]; edges: FlowEdge[] }; history: string[]; future: string[] }>({ visible: false, model: null, selectedId: null, draft: { nodes: [], edges: [] }, history: [], future: [] })
const preview = ref(false)
// 画布交互状态：拖动、显式连线模式、缩放
const viewportRef = ref<HTMLElement | null>(null)
const boardRef = ref<HTMLElement | null>(null)
const historyViewportRef = ref<HTMLElement | null>(null)
const zoom = ref(1)
const historyZoom = ref(1)
const linkMode = ref(false)
const linkSourceId = ref<string | null>(null)
const dragType = ref('')
const dragOver = ref(false)
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

/* ---------------- 画布几何：节点尺寸、可拖范围、自动扩展与缩放 ---------------- */
const NODE_W = 110
const NODE_H = 58
const BOARD_MIN_W = 760
const BOARD_MIN_H = 510
const BOARD_PAD_X = 180
const BOARD_PAD_Y = 140
// 画布逻辑上限，避免拖动时画布无限增长
const BOARD_MAX_W = 4200
const BOARD_MAX_H = 3000
const ZOOM_MIN = 0.3
const ZOOM_MAX = 1.8

const clamp = (value: number, min: number, max: number) => Math.min(Math.max(value, min), Math.max(min, max))
const round2 = (value: number) => Math.round(value * 100) / 100
const nodeById = (id: string) => designer.value.draft.nodes.find(node => node.id === id)

const boardW = computed(() => {
  const nodes = designer.value.draft.nodes
  const maxX = nodes.length ? Math.max(...nodes.map(node => node.x + NODE_W)) : 0
  return Math.round(clamp(Math.max(BOARD_MIN_W, maxX + BOARD_PAD_X), BOARD_MIN_W, BOARD_MAX_W))
})
const boardH = computed(() => {
  const nodes = designer.value.draft.nodes
  const maxY = nodes.length ? Math.max(...nodes.map(node => node.y + NODE_H)) : 0
  return Math.round(clamp(Math.max(BOARD_MIN_H, maxY + BOARD_PAD_Y), BOARD_MIN_H, BOARD_MAX_H))
})
const historyBoardW = computed(() => Math.round(clamp(Math.max(BOARD_MIN_W, Math.max(0, ...historySnapshot.value.nodes.map(node => node.x + NODE_W)) + BOARD_PAD_X), BOARD_MIN_W, BOARD_MAX_W)))
const historyBoardH = computed(() => Math.round(clamp(Math.max(BOARD_MIN_H, Math.max(0, ...historySnapshot.value.nodes.map(node => node.y + NODE_H)) + BOARD_PAD_Y), BOARD_MIN_H, BOARD_MAX_H)))

// 连线走贝塞尔：目标在右侧时从源右端出、目标左端入；目标在左侧时反向绕行，避免直线交叉。
const edgePathOf = (snapshotValue: { nodes: FlowNode[]; edges: FlowEdge[] }, edge: FlowEdge) => {
  const source = snapshotValue.nodes.find(node => node.id === edge.source)
  const target = snapshotValue.nodes.find(node => node.id === edge.target)
  if (!source || !target) return ''
  const forward = target.x >= source.x + NODE_W / 2
  const sx = forward ? source.x + NODE_W : source.x
  const tx = forward ? target.x : target.x + NODE_W
  const sy = source.y + NODE_H / 2
  const ty = target.y + NODE_H / 2
  const dx = Math.max(50, Math.abs(tx - sx) / 2)
  const c1 = forward ? sx + dx : sx - dx
  const c2 = forward ? tx - dx : tx + dx
  return `M${sx},${sy} C${c1},${sy} ${c2},${ty} ${tx},${ty}`
}
const edgePath = (edge: FlowEdge) => edgePathOf(designer.value.draft, edge)
const edgeMidPoint = (edge: FlowEdge) => {
  const source = nodeById(edge.source)
  const target = nodeById(edge.target)
  if (!source || !target) return { x: 0, y: 0 }
  return { x: (source.x + NODE_W + target.x) / 2, y: (source.y + target.y) / 2 + NODE_H / 2 }
}
const edgeBranchLabel = (edge: FlowEdge) => {
  if (edge.sourceType !== 'condition' && nodeById(edge.source)?.type !== 'condition') return ''
  return edge.branch === 'false' ? '否' : '是'
}

/* ---------------- 缩放与自适应 ---------------- */
const zoomIn = () => { zoom.value = round2(clamp(zoom.value + 0.1, ZOOM_MIN, ZOOM_MAX)) }
const zoomOut = () => { zoom.value = round2(clamp(zoom.value - 0.1, ZOOM_MIN, ZOOM_MAX)) }
const resetZoom = () => { zoom.value = 1 }
const fitToView = () => {
  const viewport = viewportRef.value
  if (!viewport) return
  // 按整张画布（含右侧留白）计算，保证缩放后不需要滚动就能看全
  const pad = 12
  const scale = Math.min(
    (viewport.clientWidth - pad * 2) / Math.max(1, boardW.value),
    (viewport.clientHeight - pad * 2) / Math.max(1, boardH.value),
    1.15,
  )
  zoom.value = round2(clamp(scale, ZOOM_MIN, ZOOM_MAX))
  nextTick(() => {
    viewport.scrollLeft = 0
    viewport.scrollTop = 0
  })
}
const fitHistory = () => {
  const viewport = historyViewportRef.value
  if (!viewport) return
  const pad = 12
  const scale = Math.min(
    (viewport.clientWidth - pad * 2) / Math.max(1, historyBoardW.value),
    (viewport.clientHeight - pad * 2) / Math.max(1, historyBoardH.value),
    1.15,
  )
  historyZoom.value = round2(clamp(scale, ZOOM_MIN, ZOOM_MAX))
  nextTick(() => {
    viewport.scrollLeft = 0
    viewport.scrollTop = 0
  })
}
const historyZoomIn = () => { historyZoom.value = round2(clamp(historyZoom.value + 0.1, ZOOM_MIN, ZOOM_MAX)) }
const historyZoomOut = () => { historyZoom.value = round2(clamp(historyZoom.value - 0.1, ZOOM_MIN, ZOOM_MAX)) }

/* ---------------- 节点拖动 ---------------- */
type DragState = { id: string; startX: number; startY: number; originX: number; originY: number; moved: boolean }
let dragState: DragState | null = null
let dragHistorySnapshot = ''
let suppressClick = false

const onNodeMouseDown = (node: FlowNode, event: MouseEvent) => {
  if (preview.value || event.button !== 0) return
  event.preventDefault()
  dragState = { id: node.id, startX: event.clientX, startY: event.clientY, originX: node.x, originY: node.y, moved: false }
  dragHistorySnapshot = snapshot()
  window.addEventListener('mousemove', onNodeMouseMove)
  window.addEventListener('mouseup', onNodeMouseUp)
}
const onNodeMouseMove = (event: MouseEvent) => {
  if (!dragState) return
  const dx = (event.clientX - dragState.startX) / zoom.value
  const dy = (event.clientY - dragState.startY) / zoom.value
  if (!dragState.moved && Math.hypot(dx, dy) < 3) return
  if (!dragState.moved) {
    dragState.moved = true
    // 拖动过程中抑制 click，避免松手时误触选中/连线
    suppressClick = true
  }
  const node = nodeById(dragState.id)
  if (!node) return
  node.x = clamp(Math.round(dragState.originX + dx), 0, BOARD_MAX_W - NODE_W)
  node.y = clamp(Math.round(dragState.originY + dy), 0, BOARD_MAX_H - NODE_H)
}
const onNodeMouseUp = () => {
  const state = dragState
  window.removeEventListener('mousemove', onNodeMouseMove)
  window.removeEventListener('mouseup', onNodeMouseUp)
  dragState = null
  if (state?.moved && dragHistorySnapshot) {
    // 只在拖动结束时压一次历史，避免每个 mousemove 都进撤销栈
    designer.value.history.push(dragHistorySnapshot)
    designer.value.future = []
    // 拖完顺手选中，方便接着调属性
    designer.value.selectedId = state.id
  }
  dragHistorySnapshot = ''
  window.setTimeout(() => { suppressClick = false }, 0)
}

/* ---------------- 节点点击 / 连线模式 ---------------- */
const toggleLinkMode = () => {
  linkMode.value = !linkMode.value
  linkSourceId.value = null
  if (linkMode.value) designer.value.selectedId = null
}
const startLinkFromSelected = () => {
  if (!designer.value.selectedId) { ElMessage.warning('请先选中一个节点作为连线起点'); return }
  linkMode.value = true
  linkSourceId.value = designer.value.selectedId
}
const onBoardClick = () => {
  if (linkSourceId.value) { linkSourceId.value = null; return }
  if (!linkMode.value) designer.value.selectedId = null
}
const createEdge = (sourceId: string, targetId: string) => {
  if (sourceId === targetId) return
  if (designer.value.draft.edges.some(edge => edge.source === sourceId && edge.target === targetId)) {
    ElMessage.warning('这两个节点之间已经有一条连线')
    return
  }
  const source = nodeById(sourceId)
  const outgoing = designer.value.draft.edges.filter(edge => edge.source === sourceId)
  if (source?.type !== 'condition' && outgoing.length) {
    ElMessage.warning(`「${source?.label || sourceId}」已经有一条后续连线，请先删除原有连线`)
    return
  }
  record()
  const edge: FlowEdge = { source: sourceId, target: targetId }
  if (source?.type === 'condition') {
    edge.sourceType = 'condition'
    edge.branch = outgoing.some(item => item.branch === 'true') ? 'false' : 'true'
    source.branches = { ...(source.branches || {}), [edge.branch]: targetId }
  }
  designer.value.draft.edges.push(edge)
  ElMessage.success(`已连线：${nodeLabel(sourceId)} → ${nodeLabel(targetId)}${edge.branch ? `（${edge.branch === 'true' ? '是' : '否'}）` : ''}`)
}
const onNodeClick = (node: FlowNode) => {
  if (suppressClick) return
  if (preview.value) { designer.value.selectedId = node.id; return }
  if (!linkMode.value) { designer.value.selectedId = node.id; return }
  if (!linkSourceId.value) { linkSourceId.value = node.id; designer.value.selectedId = node.id; return }
  if (linkSourceId.value === node.id) { linkSourceId.value = null; return }
  const sourceId = linkSourceId.value
  createEdge(sourceId, node.id)
  // 条件节点需要两条出口，连完一条保留起点方便继续连；其它节点连完即复位
  if (nodeById(sourceId)?.type !== 'condition') linkSourceId.value = null
  designer.value.selectedId = node.id
}

/* ---------------- 拖入节点 ---------------- */
const onDragOver = (event: DragEvent) => {
  if (preview.value) return
  event.preventDefault()
  if (event.dataTransfer) event.dataTransfer.dropEffect = 'copy'
  dragOver.value = true
}
const onDragLeave = (event: DragEvent) => {
  // 移到子元素上也会触发 dragleave，这里过滤掉避免高亮闪烁
  const related = event.relatedTarget as Node | null
  if (related && (event.currentTarget as HTMLElement).contains(related)) return
  dragOver.value = false
}
const onDrop = (event: DragEvent) => {
  dragOver.value = false
  if (preview.value) return
  // 兼容未触发 dragstart 记录的情况（部分浏览器）
  if (!dragType.value && event.dataTransfer) dragType.value = event.dataTransfer.getData('text/plain')
  dropNode(event)
}
const scrollNodeIntoView = (x: number, y: number) => {
  const viewport = viewportRef.value
  if (!viewport) return
  const left = x * zoom.value
  const top = y * zoom.value
  const margin = 80
  if (left < viewport.scrollLeft || left > viewport.scrollLeft + viewport.clientWidth - NODE_W - margin) {
    viewport.scrollLeft = Math.max(0, left - margin)
  }
  if (top < viewport.scrollTop || top > viewport.scrollTop + viewport.clientHeight - NODE_H - margin) {
    viewport.scrollTop = Math.max(0, top - margin)
  }
}
// Ctrl + 滚轮缩放，普通滚轮仍用于滚动查看
const onWheel = (event: WheelEvent) => {
  if (!event.ctrlKey) return
  event.preventDefault()
  if (event.deltaY < 0) zoomIn()
  else zoomOut()
}
// 动作清单由后端 catalog 下发，这里只保留中文标签。
// 后端 WORKFLOW_ACTIONS 新增动作时，前端无需改动即可出现在下拉框（无标签时回退显示动作名）。
const actionLabels: Record<string, string> = {
  create_contract: '创建合同',
  create_sales_order: '创建销售订单',
  allocate_order: '执行订单配货',
  inbound_machine: '成品入库',
  transfer_machine: '库位转移',
  confirm_shipment: '确认发货',
  save_customer_machine_plan: '保存客户机台规划',
  cancel_contract: '取消合同',
  cancel_contract_reinbound: '取消合同并释放机台',
  delete_order: '删除订单',
  delete_order_reinbound: '删除订单并派生重入库',
  recall_allocation: '撤回配货',
  recall_shipment: '撤回发货',
  recall_customer_finished: '撤回客户成品发货',
  ship_customer_order: '客户成品订单发货',
  disable_model: '停用机型',
}
const catalogActions = ref<Record<string, string[]>>({})
const conditionFields = ref<{ value: string; label: string }[]>([
  { value: 'bound_machine_count', label: '绑定机台数量' },
  { value: 'shipped_machine_count', label: '已发货机台数量' },
  { value: 'item_count', label: '流程对象数量' },
])
const conditionOperators = ref<{ value: string; label: string }[]>([
  { value: 'gt', label: '大于' },
  { value: 'eq', label: '等于' },
  { value: 'exists', label: '存在' },
])
const allowedActions = (key: string) => catalogActions.value[key] || []
const actionOptions = computed(() => allowedActions(designer.value.model?.key || '').map(value => ({ value, label: actionLabels[value] || value })))
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
const startDrag = (type: any, event?: DragEvent) => {
  dragType.value = String(type?.type || '')
  if (event?.dataTransfer) {
    event.dataTransfer.effectAllowed = 'copy'
    // 不写数据时 Firefox 不会触发 drop
    event.dataTransfer.setData('text/plain', dragType.value)
  }
}
const dropNode = (event: DragEvent) => {
  const type = nodeTypes.find(item => item.type === dragType.value)
  dragType.value = ''
  if (!type) return
  const board = boardRef.value
  if (!board) return
  event.preventDefault()
  const rect = board.getBoundingClientRect()
  // board 带 transform: scale()，除以 zoom 才能换算成逻辑坐标
  const x = clamp(Math.round((event.clientX - rect.left) / zoom.value - NODE_W / 2), 0, BOARD_MAX_W - NODE_W)
  const y = clamp(Math.round((event.clientY - rect.top) / zoom.value - NODE_H / 2), 0, BOARD_MAX_H - NODE_H)
  record()
  const id = `${type.type}-${Date.now()}`
  designer.value.draft.nodes.push({ id, type: type.type, label: type.label, x, y })
  designer.value.selectedId = id
  nextTick(() => scrollNodeIntoView(x, y))
}
const enterEditMode = () => {
  designer.value.selectedId = null
  preview.value = false
  linkMode.value = false
  linkSourceId.value = null
  nextTick(fitToView)
}
const enterPreviewMode = () => {
  designer.value.selectedId = null
  preview.value = true
  linkMode.value = false
  linkSourceId.value = null
  nextTick(fitToView)
}
const removeNode = (id: string) => { record(); designer.value.draft.nodes = designer.value.draft.nodes.filter(node => node.id !== id); designer.value.draft.edges = designer.value.draft.edges.filter(edge => edge.source !== id && edge.target !== id); designer.value.selectedId = null }
const removeEdge = (edge: FlowEdge) => { record(); designer.value.draft.edges = designer.value.draft.edges.filter(item => item !== edge) }
const validateDraft = () => {
  const { nodes, edges } = designer.value.draft
  const byId = new Map(nodes.map(node => [node.id, node]))
  const starts = nodes.filter(node => node.type === 'start')
  if (starts.length !== 1 || !nodes.some(node => node.type === 'end')) return '流程必须且只能有一个发起节点，并包含结束节点'
  const isReverse = designer.value.model?.direction === '逆向'
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
    if (node.type === 'execute' && !allowedActions(designer.value.model?.key || '').includes(node.action || '')) return `动作“${node.action}”不适用于当前流程`
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
    const response = await apiGet<{ data: any[]; catalog?: any }>('/workflows/models')
    const catalog = response.catalog || {}
    if (catalog.actions && typeof catalog.actions === 'object') catalogActions.value = catalog.actions
    if (Array.isArray(catalog.condition_fields) && catalog.condition_fields.length) conditionFields.value = catalog.condition_fields
    if (Array.isArray(catalog.condition_operators) && catalog.condition_operators.length) conditionOperators.value = catalog.condition_operators
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
  } catch (err: any) {
    // 接口失败时不能退回到本地假数据，否则会让人误判模型状态。
    models.value = []
    ElMessage.error(getApiErrorMessage(err) || '读取流程模型失败，请检查后端服务')
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

// 打开设计器、切换预览/编辑后都自动适配画布，避免历史坐标把节点甩到可视区外
watch(() => designer.value.visible, async (visible) => {
  if (!visible) return
  await nextTick()
  window.setTimeout(fitToView, 80)
})
watch(preview, async () => { await nextTick(); window.setTimeout(fitToView, 60) })

const onKeydown = (event: KeyboardEvent) => {
  if (!designer.value.visible) return
  const target = event.target as HTMLElement | null
  if (target && ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)) return
  if (event.key === 'Escape') {
    if (linkSourceId.value) { linkSourceId.value = null; return }
    if (linkMode.value) { linkMode.value = false; return }
  }
  if ((event.key === 'Delete' || event.key === 'Backspace') && !preview.value && designer.value.selectedId) {
    event.preventDefault()
    removeNode(designer.value.selectedId)
  }
}
onMounted(() => window.addEventListener('keydown', onKeydown))
onMounted(() => window.addEventListener('blur', onNodeMouseUp))
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeydown)
  window.removeEventListener('blur', onNodeMouseUp)
  window.removeEventListener('mousemove', onNodeMouseMove)
  window.removeEventListener('mouseup', onNodeMouseUp)
})

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
        { id: 'execute', type: 'execute', label: '自动执行', x: 220, y: 120 },
        { id: 'notify', type: 'notify', label: '通知', x: 405, y: 120, notifyRoles: ['Inbound'] },
        { id: 'end', type: 'end', label: '结束', x: 590, y: 120 },
      ]
      : notifyAfterExecution ? [
        { id: 'start', type: 'start', label: '发起', x: 35, y: 120 },
        { id: 'approval', type: 'approval', label: '审批', x: 220, y: 120, approvalRoles: ['Boss'] },
        { id: 'execute', type: 'execute', label: '自动执行', x: 405, y: 120 },
        { id: 'notify', type: 'notify', label: '通知', x: 590, y: 120, notifyRoles: ['Inbound'] },
        { id: 'end', type: 'end', label: '结束', x: 775, y: 120 },
      ] : [
        { id: 'start', type: 'start', label: '发起', x: 35, y: 120 },
        { id: 'approval', type: 'approval', label: '审批', x: 220, y: 120, approvalRoles: ['Boss'] },
        { id: 'execute', type: 'execute', label: '自动执行', x: 405, y: 120 },
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
const copyModel = async (row: Model) => {
  try {
    const res = await apiPost<{ data: { workflow_key: string; name: string } }>(`/workflows/models/${encodeURIComponent(row.key)}/duplicate`)
    ElMessage.success(`已复制为未发布草稿「${res.data?.name || row.name}」`)
    await loadModels()
  } catch { /* 请求拦截器已提示后端错误 */ }
}
const publishModel = async (row: Model) => {
  // 已停用的模型走“启用”，恢复原版本，不产生新版本。
  if (row.status === '已停用') {
    try {
      await apiPost(`/workflows/models/${encodeURIComponent(row.key)}/enable`)
      ElMessage.success(`已启用「${row.name}」`)
      await loadModels()
    } catch { /* 请求拦截器已提示 */ }
    return
  }
  if (!row.snapshot?.nodes?.length) {
    ElMessage.warning('该流程还没有可发布的流程图，请先打开编辑器设计并发布')
    return
  }
  try {
    await ElMessageBox.confirm(`确认发布「${row.name}」的当前流程图？发布后立即对新发起的流程生效。`, '发布流程', { type: 'warning' })
  } catch { return }
  try {
    await apiPost(`/workflows/models/${encodeURIComponent(row.key)}/publish`, { snapshot: row.snapshot })
    ElMessage.success(`已发布「${row.name}」`)
    await loadModels()
  } catch { /* 请求拦截器已提示 */ }
}
const disableModel = async (row: Model) => {
  try {
    await ElMessageBox.confirm(`停用后「${row.name}」将无法再发起，在途流程不受影响。确认停用？`, '停用流程', { type: 'warning' })
  } catch { return }
  try {
    await apiPost(`/workflows/models/${encodeURIComponent(row.key)}/disable`)
    ElMessage.success(`已停用「${row.name}」`)
    await loadModels()
  } catch { /* 请求拦截器已提示 */ }
}
const handleCommand = async (command: string, row: Model) => {
  if (command === 'detail') { await ElMessageBox.alert(`<p><b>流程 Key：</b>${row.key}</p><p><b>业务对象：</b>${row.object}</p><p><b>处理方式：</b>${row.mode}</p>`, `流程详情：${row.name}`, { dangerouslyUseHTMLString: true }); return }
  if (command === 'history') { await openHistory(row); return }
  if (!row.draftSnapshot?.nodes?.length) { ElMessage.warning('该流程没有草稿可删除'); return }
  try {
    await ElMessageBox.confirm(`确认删除「${row.name}」的草稿？已发布版本不受影响。`, '删除草稿', { type: 'warning' })
  } catch { return }
  try {
    await apiDelete(`/workflows/models/${encodeURIComponent(row.key)}/draft`)
    ElMessage.success('草稿已删除')
    await loadModels()
  } catch { /* 请求拦截器已提示 */ }
}
const parseHistorySnapshot = (value: any): { nodes: FlowNode[]; edges: FlowEdge[] } => {
  if (!value) return { nodes: [], edges: [] }
  try { const parsed = typeof value === 'string' ? JSON.parse(value) : value; return { nodes: Array.isArray(parsed?.nodes) ? parsed.nodes : [], edges: Array.isArray(parsed?.edges) ? parsed.edges : [] } } catch { return { nodes: [], edges: [] } }
}
const selectHistoryVersion = () => { const version = selectedHistoryVersion.value; historySnapshot.value = parseHistorySnapshot(version?.node_snapshot); nextTick(fitHistory) }
const openHistory = async (row: Model) => {
  try {
    const response = await apiGet<{ data: any[] }>(`/workflows/models/${encodeURIComponent(row.key)}/versions`)
    historyModel.value = row
    historyVersions.value = response.data || []
    historyVersion.value = historyVersions.value[0]?.version_no ?? null
    historySnapshot.value = parseHistorySnapshot(historyVersions.value[0]?.node_snapshot)
    historyVisible.value = true
    await nextTick()
    window.setTimeout(fitHistory, 80)
  } catch { /* request interceptor displays the server error */ }
}
</script>

<style scoped>
.workflow-page{padding:28px;max-width:1500px}.page-head{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:20px}h1{margin:0 0 8px;font-size:24px;color:#1f2937}.workflow-badge{vertical-align:top;margin-left:8px}.intro{margin:0;color:#64748b}.toolbar{display:flex;gap:12px;margin-bottom:20px}.search-input{width:320px}.filter-select{width:160px}.model-group{margin-bottom:18px;border:1px solid #e5e7eb;border-radius:8px;background:#fff;overflow:hidden}.group-head{display:flex;justify-content:space-between;align-items:center;width:100%;padding:14px 18px;border:0;background:#f8fafc;color:#1f2937;cursor:pointer;text-align:left}.group-head:hover{background:#f1f5f9}.group-title{display:flex;align-items:center;gap:8px}.group-count{font-size:13px;color:#94a3b8}.chevron{display:inline-block;font-size:22px;line-height:12px;transform:rotate(0deg);transition:transform .15s}.chevron.expanded{transform:rotate(90deg)}.table-wrap{border-top:1px solid #e5e7eb}.approval-mode{color:#d97706}.auto-mode{color:#059669}.version{display:block;color:#94a3b8;font-size:12px;margin-top:2px}.designer{display:grid;grid-template-columns:170px 1fr 240px;gap:12px;min-height:560px}.node-palette,.node-properties{border:1px solid #e5e7eb;padding:14px;background:#f8fafc}.palette-node{padding:10px;margin-top:8px;background:#fff;border:1px solid #dbe3ee;border-radius:6px;cursor:grab}.node-icon{display:inline-flex;width:24px;height:24px;align-items:center;justify-content:center;margin-right:7px;border-radius:50%;background:#e0ecff;color:#2563eb}.palette-tip,.edge-help{font-size:12px;color:#64748b;line-height:1.6}.designer-canvas{border:1px solid #dbe3ee;overflow:auto}.canvas-toolbar{height:42px;padding:8px 12px;display:flex;align-items:center;gap:8px;border-bottom:1px solid #e5e7eb;color:#64748b;font-size:12px}.canvas-board{position:relative;min-width:760px;height:510px;background-color:#fff;background-image:radial-gradient(#d7dee8 1px,transparent 1px);background-size:18px 18px}.canvas-board.preview{background-color:#f8fafc}.flow-node{position:absolute;width:110px;min-height:58px;padding:8px;border:2px solid #cbd5e1;border-radius:8px;background:#fff;cursor:pointer;box-shadow:0 2px 6px #00000012}.flow-node.selected{border-color:#2563eb;box-shadow:0 0 0 2px #93c5fd}.flow-node b,.flow-node small{display:block}.flow-node small{color:#64748b;font-size:11px}.canvas-empty{padding:220px;text-align:center;color:#94a3b8}.node-properties{background:#fff}.edge-help{margin-top:18px}.edge-help .el-tag{margin:3px}
@media (max-width:900px){.workflow-page{padding:16px}.toolbar{flex-wrap:wrap}.search-input{width:100%}.filter-select{flex:1;min-width:140px}.table-wrap{overflow-x:auto}}
 .flow-edges{position:absolute;inset:0;width:100%;height:100%;pointer-events:none;z-index:0}.flow-node{z-index:1}.canvas-board.preview .flow-node{cursor:default}.preview-properties{pointer-events:none;opacity:.75}.field-help{display:block;color:#64748b;font-size:11px;line-height:1.5}
.history-toolbar{display:flex;align-items:center;gap:14px;margin-bottom:12px}.history-meta{color:#64748b;font-size:13px}.history-board-wrap{border:0;overflow:visible}.history-board{min-width:0}

/* --- 画布交互：节点拖动 / 显式连线模式 / 缩放自适应 --- */
.designer-canvas{display:flex;flex-direction:column;overflow:hidden;height:calc(86vh - 190px);min-height:520px}
.canvas-toolbar{flex:0 0 auto;flex-wrap:wrap;height:auto;min-height:42px}
.toolbar-divider{width:1px;height:16px;background:#e2e8f0;margin:0 4px}
.canvas-stat{margin-left:auto;color:#94a3b8;white-space:nowrap}
.zoom-value{min-width:54px;font-variant-numeric:tabular-nums}
.link-hint{flex:0 0 auto;display:flex;align-items:center;gap:10px;padding:7px 12px;background:#eff6ff;border-bottom:1px solid #bfdbfe;color:#1d4ed8;font-size:12px}
.link-hint.active{background:#fef3c7;border-bottom-color:#fcd34d;color:#b45309}
.link-hint .el-button{margin-left:auto}
.canvas-viewport{position:relative;flex:1 1 auto;overflow:auto;background:#f1f5f9}
.board-scale-box{position:relative}
.canvas-board{position:relative;min-width:0;height:auto;transform-origin:0 0}
.canvas-board.drag-over{box-shadow:inset 0 0 0 2px #93c5fd}
.canvas-board.link-mode{cursor:crosshair}
.flow-node{cursor:grab;user-select:none;touch-action:none}
.flow-node:active{cursor:grabbing}
.canvas-board.preview .flow-node{cursor:default}
.flow-node.link-source{border-color:#f59e0b;box-shadow:0 0 0 3px #fde68a}
.flow-node.link-target:hover{border-color:#2563eb;box-shadow:0 0 0 3px #bfdbfe}
.node-port{position:absolute;right:-7px;top:50%;width:12px;height:12px;margin-top:-6px;border:2px solid #f59e0b;border-radius:50%;background:#fff;pointer-events:none}
.edge-label{font-size:11px;fill:#475569;stroke:#fff;stroke-width:3px;paint-order:stroke}
.canvas-empty{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;padding:0}
.history-viewport{height:62vh;border:1px solid #dbe3ee;border-radius:4px}
.history-board{min-width:0}
.node-properties{max-height:calc(86vh - 190px);overflow-y:auto}
</style>
