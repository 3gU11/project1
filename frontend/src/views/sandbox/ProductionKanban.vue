<template>
  <div class="kanban-layout">
    <div class="kanban-left">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
        <h3 style="font-size:16px;">产线监控 ({{ lineStore.lines.length }} 条)</h3>
        <el-button size="small" @click="() => refreshAll()" :loading="lineStore.loading">刷新</el-button>
      </div>

      <div>
        <div v-for="line in lineStore.lines" :key="line.production_line_id" class="production-line" :data-line-id="line.production_line_id">
          <div class="line-header">
            <span class="line-name">{{ line.line_name }}</span>
            <span class="line-status" :class="line.status === 'Idle' ? 'idle' : 'busy'">
              {{ line.status === 'Idle' ? '空闲' : '忙碌' }}
            </span>
            <span v-if="line.model_type" style="font-size:12px;color:#888;">{{ line.model_type }}</span>
            <span style="flex:1;"></span>
            <el-button
              v-if="line.status === 'Busy'"
              size="small" type="warning" @click="handleManualComplete(line.production_line_id)"
            >
              手动完工
            </el-button>
          </div>
          <VueDraggable
            v-if="line.status === 'Busy' || line.units?.length"
            :model-value="line.units || []"
            :group="{ name: 'line-units', pull: false, put: ['rush-orders'] }"
            item-key="unit_id"
            :sort="false"
            @start="onDragStart"
            @add="(evt: any) => onKanbanDrop(evt, line)"
            @end="onDragEnd"
            class="line-units"
          >
            <template v-for="u in line.units" :key="u.unit_id">
              <UnitCard :unit="u" @edit="openEditDrawer" @contextmenu="onContextMenu" />
            </template>
          </VueDraggable>
          <div v-else style="color:#bbb;font-size:12px;padding:8px;">
            空闲 - 可分配待排产批次
          </div>
        </div>
      </div>
    </div>

    <div class="kanban-right">
      <RushOrderEntry @auto-inserted="() => refreshAll({ silent: true })" />

      <div style="margin-top:16px;">
        <h3 style="font-size:14px;margin-bottom:8px;">
          待排产队列
          <el-select v-model="queueFilter" size="small" style="width:100px;margin-left:8px;" clearable placeholder="全部">
            <el-option label="小机G" value="小机G" />
            <el-option label="小机XS" value="小机XS" />
            <el-option label="大机XS" value="大机XS" />
            <el-option label="小机AUTO" value="小机AUTO" />
            <el-option label="大机AUTO" value="大机AUTO" />
            <el-option label="特殊" value="特殊" />
          </el-select>
        </h3>
        <div>
          <div v-for="batch in queueBatches" :key="batch.batch_id" style="margin-bottom:12px;">
            <div style="font-size:12px;padding:6px 10px;background:#fafafa;border-radius:6px;">
              <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;">
                <span>
                  <strong>[{{ displayBatchCategory(batch) }}] {{ displayBatchCode(batch) }}</strong>
                  ({{ batch.units?.length || 0 }}/{{ batch.capacity }})
                </span>
                <el-button
                  size="small" type="primary"
                  @click="showAssignDialog(batch)"
                  :disabled="!idleLines.length"
                >
                  整批分配
                </el-button>
              </div>
              <div style="font-size:11px;color:#999;">
                {{ fmtDate(batch.due_date_start) }} ~ {{ fmtDate(batch.due_date_end) }}
              </div>
            </div>
          </div>
          <div v-if="queueBatches.length === 0 && !batchStore.loading" style="color:#ccc;text-align:center;padding:20px;font-size:13px;">
            暂无待排产批次
          </div>
        </div>
      </div>

      <!-- 生产中批次列表 -->
      <div style="margin-top:16px;">
        <h3 style="font-size:14px;margin-bottom:8px;color:#1890ff;">
          生产中批次 ({{ inProductionBatches.length }})
        </h3>
        <div>
          <div v-for="batch in inProductionBatches" :key="batch.batch_id" style="margin-bottom:8px;">
            <div style="font-size:12px;padding:6px 10px;background:#e6f7ff;border-radius:6px;border-left:3px solid #1890ff;">
              <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;">
                <span>
                  <strong>[{{ displayBatchCategory(batch) }}] {{ displayBatchCode(batch) }}</strong>
                  ({{ batch.units?.length || 0 }}/{{ batch.capacity }})
                </span>
                <el-button
                  size="small" type="primary" link
                  @click="scrollToLine(batch.production_line_id)"
                >
                  跳转产线
                </el-button>
              </div>
              <div style="font-size:11px;color:#999;">
                {{ fmtDate(batch.due_date_start) }} ~ {{ fmtDate(batch.due_date_end) }}
              </div>
            </div>
          </div>
          <div v-if="inProductionBatches.length === 0" style="color:#ccc;text-align:center;padding:12px;font-size:13px;">
            暂无生产中批次
          </div>
        </div>
      </div>
    </div>
  </div>

    <el-dialog v-model="assignVisible" title="整批分配" width="400px">
      <p>选择空闲产线分配批次 {{ assigningBatch?.batch_id?.slice(0,25) }}...</p>
      <el-select v-model="selectedLineId" placeholder="选择产线" style="width:100%">
        <el-option v-for="l in idleLines" :key="l.production_line_id" :label="l.line_name" :value="l.production_line_id" />
      </el-select>
      <template #footer>
        <el-button @click="assignVisible = false">取消</el-button>
        <el-button type="primary" @click="doAssign" :disabled="!selectedLineId" :loading="assigning2">确认分配</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="editVisible" title="信息强改" size="400px">
      <el-form v-if="editingUnit" label-width="80px" size="small">
        <el-form-item label="合同号"><el-input v-model="editForm.contract_no" /></el-form-item>
        <el-form-item label="客户"><el-input v-model="editForm.customer" /></el-form-item>
        <el-form-item label="经销商"><el-input v-model="editForm.dealer_name" /></el-form-item>
        <el-form-item label="机型"><el-input v-model="editForm.model_type" disabled /></el-form-item>
        <el-form-item label="备注"><el-input v-model="editForm.order_remark" type="textarea" /></el-form-item>
        <el-form-item>
          <el-button type="primary" @click="saveEdit" :loading="saving">保存并锁定</el-button>
        </el-form-item>
      </el-form>
    </el-drawer>

    <div
      v-if="contextMenu.visible"
      :style="{ position: 'fixed', left: contextMenu.x + 'px', top: contextMenu.y + 'px', zIndex: 9999 }"
      style="background:#fff;border-radius:6px;box-shadow:0 4px 12px rgba(0,0,0,0.15);padding:4px 0;min-width:120px;"
    >
      <div class="ctx-item" @click="handleUnlock" v-if="contextMenu.unit?.is_locked">解锁</div>
      <div class="ctx-item" @click="handleMarkSpot">标记现货</div>
      <div class="ctx-item" @click="contextMenu.visible = false">取消</div>
    </div>
</template>


<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { VueDraggable } from 'vue-draggable-plus'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useBatchStore } from '../../stores/useSandboxBatchStore'
import { useLineStore } from '../../stores/useSandboxLineStore'
import { useRushStore } from '../../stores/useSandboxRushStore'
import * as sandboxApi from '../../services/sandboxApi'
import UnitCard from '../../components/sandbox/UnitCard.vue'
import RushOrderEntry from '../../components/sandbox/RushOrderEntry.vue'
import { connect as wsConnect, disconnect as wsDisconnect, onEvent } from '../../services/sandboxWs'
import { categoryOfModel, normalizeMajorFamily } from '../../utils/sandboxCategory'

const batchStore = useBatchStore()
const lineStore = useLineStore()
const rushStore = useRushStore()

const queueFilter = ref('')
const assignVisible = ref(false)
const assigningBatch = ref<any>(null)
const selectedLineId = ref<string | null>(null)
const assigning2 = ref(false)
const editVisible = ref(false)
const editingUnit = ref<any>(null)
const saving = ref(false)
const contextMenu = ref<{ visible: boolean; x: number; y: number; unit: any }>({ visible: false, x: 0, y: 0, unit: null })
const dragging = ref(false)
const pendingRefresh = ref(false)
const modelFamilyMap = ref<Record<string, string>>({})


const editForm = ref({ contract_no: '', customer: '', dealer_name: '', model_type: '', order_remark: '' })

const queueBatches = computed(() => {
  let batches = batchStore.batches.filter((b: any) => b.status === 'Confirmed')
  if (queueFilter.value) batches = batches.filter((b: any) => displayBatchCategory(b) === queueFilter.value)
  return batches
})

const inProductionBatches = computed(() =>
  batchStore.batches.filter((b: any) => b.status === 'In_Production')
)

const idleLines = computed(() => lineStore.lines.filter((l: any) => l.status === 'Idle'))

function scrollToLine(lineId: string | null | undefined) {
  if (!lineId) return
  const el = document.querySelector(`[data-line-id="${lineId}"]`) as HTMLElement | null
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' })
}

function fmtDate(d: string | null | undefined) {
  if (!d) return '-'
  return String(d).slice(0, 10)
}

function displayBatchCode(batch: any) {
  const explicit = String(batch?.batch_code || '').trim()
  if (explicit) return explicit
  const n = Number(batch?.batch_no)
  if (!Number.isFinite(n) || n <= 0) return `第 ${batch?.batch_no || '-'} 批`
  const whole = Math.trunc(n)
  if (whole >= 101) {
    const month = Math.floor(whole / 100)
    const seq = whole % 100
    if (month >= 1 && month <= 12 && seq >= 1) {
      return `${String(month).padStart(2, '0')}-${String(seq).padStart(2, '0')}`
    }
  }
  return `第 ${whole} 批`
}

function majorFamilyOfModel(modelType: string) {
  const model = String(modelType || '').trim()
  if (!model) return ''
  const byDict = modelFamilyMap.value[model.toUpperCase()]
  return normalizeMajorFamily(byDict || model)
}

function displayBatchCategory(batch: any) {
  const units = Array.isArray(batch?.units) ? batch.units : []
  const count: Record<string, number> = {}
  for (const u of units) {
    const mt = String(u?.model_type || '')
    const c = categoryOfModel(mt, modelFamilyMap.value[mt.toUpperCase()] || '')
    if (!c) continue
    count[c] = Number(count[c] || 0) + 1
  }
  const priority: Record<string, number> = {
    特殊: 6, 大机AUTO: 5, 小机AUTO: 4, 大机XS: 3, 小机XS: 2, 小机G: 1
  }
  let best = ''
  let bestN = -1
  for (const k of Object.keys(count)) {
    const cur = Number(count[k] || 0)
    const bestP = Number(priority[best] || 0)
    const curP = Number(priority[k] || 0)
    if (cur > bestN || (cur === bestN && curP > bestP)) {
      best = k
      bestN = cur
    }
  }
  if (best) {
    return best
  }
  const direct = categoryOfModel(String(batch?.model_type || ''), '')
  if (direct) return direct
  if (String(batch?.model_type || '').toUpperCase().includes('SPECIAL')) return '特殊'
  const family = majorFamilyOfModel(String(batch?.model_type || ''))
  if (family === 'G') return '小机G'
  if (family === 'XS') return '小机XS'
  if (family === 'AUTO') return '小机AUTO'
  if (family === 'SPECIAL') return '特殊'
  return String(batch?.model_type || '-')
}

async function loadModelTypes() {
  try {
    const res = await sandboxApi.getModelTypes() as any
    const list = Array.isArray(res) ? res : (res?.model_types || res?.types || [])
    const nextMap: Record<string, string> = {}
    if (Array.isArray(list)) {
      for (const item of list) {
        if (typeof item === 'string') continue
        if (!item || typeof item !== 'object') continue
        const mt = String(item.model_type || '').trim()
        const mf = String(item.model_family || '').trim()
        if (mt && mf) nextMap[mt.toUpperCase()] = mf
      }
    }
    modelFamilyMap.value = nextMap
  } catch {
    modelFamilyMap.value = {}
  }
}

async function refreshAll(options: { silent?: boolean } = {}) {
  if (dragging.value) {
    pendingRefresh.value = true
    return
  }
  await Promise.all([
    lineStore.fetchLines(options),
    batchStore.fetchBatches({}, options),
    safeFetchRushOrders()
  ])
}

async function safeFetchRushOrders() {
  try {
    await rushStore.fetchRushOrders()
  } catch (e: any) {
    console.warn('加载急单队列失败:', e?.message || e)
  }
}

async function forceRefreshAll() {
  pendingRefresh.value = false
  await Promise.all([lineStore.fetchLines(), batchStore.fetchBatches()])
}

async function flushPendingRefresh() {
  if (dragging.value || !pendingRefresh.value) return
  pendingRefresh.value = false
  await Promise.all([lineStore.fetchLines(), batchStore.fetchBatches()])
}

function onDragStart() {
  dragging.value = true
}

async function onDragEnd() {
  dragging.value = false
  await flushPendingRefresh()
}

function showAssignDialog(batch: any) {
  assigningBatch.value = batch
  selectedLineId.value = null
  assignVisible.value = true
}

async function doAssign() {
  if (!selectedLineId.value || !assigningBatch.value) return
  assigning2.value = true
  try {
    await lineStore.assignLine(selectedLineId.value, assigningBatch.value.batch_id)

    // 自动导入 plan_import → finished_goods_data
    const batchCode = String(assigningBatch.value?.batch_code || '').trim()
    if (batchCode) {
      try {
        await sandboxApi.importBatchToFinishedGoods(assigningBatch.value.batch_id)
      } catch (e: any) {
        console.error('自动导入成品库存失败:', e.message)
      }
    }

    ElMessage.success('批次已分配')
    assignVisible.value = false
    await forceRefreshAll()
  } catch (e: any) {
    ElMessage.error(e.message)
  } finally {
    assigning2.value = false
  }
}

async function handleManualComplete(lineId: string) {
  try {
    await ElMessageBox.confirm('确认该产线已完工？', '确认', { type: 'warning' })
    await lineStore.manualComplete(lineId)
    ElMessage.success('已手动完工')
    await forceRefreshAll()
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error(e.message)
  }
}

async function onKanbanDrop(evt: any, line: any) {
  const rushOrder = getDroppedData(evt)
  const targetUnit = resolveTargetUnit(evt, line)
  cleanupDroppedClone(line)
  if (!isRushOrder(rushOrder)) {
    await forceRefreshAll()
    return
  }
  if (!targetUnit) {
    ElMessage.error('未识别目标机台')
    await forceRefreshAll()
    return
  }
  await handleRushDrop(rushOrder, targetUnit)
}

function getDroppedData(evt: any) {
  return evt?.data || evt?.clonedData || evt?.item?.__draggable_context?.element
}

function isRushOrder(order: any) {
  return !!order && !!order.contract_no && (order.id !== undefined || order.__drag_type === 'rush-order')
}

function cleanupDroppedClone(line: any) {
  if (!Array.isArray(line.units)) return
  line.units = line.units.filter((u: any) => u?.unit_id)
}

function getEventPoint(originalEvent: any) {
  const touch = originalEvent?.changedTouches?.[0] || originalEvent?.touches?.[0]
  const source = touch || originalEvent
  if (!source || source.clientX === undefined || source.clientY === undefined) return null
  return { x: source.clientX, y: source.clientY }
}

function resolveTargetUnit(evt: any, line: any) {
  const point = getEventPoint(evt?.originalEvent)
  if (point && document.elementsFromPoint) {
    const elements = document.elementsFromPoint(point.x, point.y)
    for (const el of elements) {
      const card = el.closest?.('.unit-card[data-unit-id]') as HTMLElement | null
      const unitId = card?.dataset?.unitId
      if (unitId) {
        const unit = (line.units || []).find((u: any) => u.unit_id === unitId)
        if (unit) return unit
      }
    }
  }
  const units = (line.units || []).filter((u: any) => u?.unit_id)
  const idx = evt?.newDraggableIndex ?? evt?.newIndex
  if (idx === undefined || idx === null) return null
  return units[idx] || units[idx - 1] || null
}

async function handleRushDrop(rushOrder: any, targetUnit: any) {
  if (targetUnit.is_locked) {
    ElMessage.error('目标机台已锁定')
    return
  }

  const rushMT = majorFamilyOfModel(rushOrder.model_type)
  const targetMT = majorFamilyOfModel(targetUnit.model_type)

  if (rushMT !== targetMT) {
    ElMessage.error(`机型不匹配: ${rushMT} vs ${targetMT}`)
    return
  }

  await doDirectRushInsert(rushOrder, targetUnit)
}

async function doDirectRushInsert(rushOrder: any, targetUnit: any) {
  try {
    await rushStore.executeRushInsertAtTarget(targetUnit.unit_id, rushOrder)
    await rushStore.markRushOrderStatus(rushOrder.id, 'inserted')
    ElMessage.success('急单已插入')
    await forceRefreshAll()
  } catch (e: any) {
    ElMessage.error(e.message)
    await forceRefreshAll()
  }
}

function openEditDrawer(unit: any) {
  editingUnit.value = unit
  editForm.value = {
    contract_no: unit.contract_no || '',
    customer: unit.customer || '',
    dealer_name: unit.dealer_name || '',
    model_type: unit.model_type || '',
    order_remark: unit.order_remark || ''
  }
  editVisible.value = true
}

async function saveEdit() {
  if (!editingUnit.value) return
  saving.value = true
  try {
    const { model_type, ...editableFields } = editForm.value
    await sandboxApi.updateUnit(editingUnit.value.unit_id, editableFields)
    ElMessage.success('已保存并锁定')
    editVisible.value = false
    await forceRefreshAll()
  } catch (e: any) {
    ElMessage.error(e.message)
  } finally {
    saving.value = false
  }
}

function onContextMenu({ event, unit }: { event: MouseEvent; unit: any }) {
  contextMenu.value = { visible: true, x: event.clientX, y: event.clientY, unit }
  setTimeout(() => {
    const close = () => { contextMenu.value.visible = false; document.removeEventListener('click', close) }
    document.addEventListener('click', close)
  }, 100)
}

async function handleUnlock() {
  const unit = contextMenu.value.unit
  if (!unit) return
  try {
    await sandboxApi.unlockUnit(unit.unit_id)
    ElMessage.success('已解锁')
    await forceRefreshAll()
  } catch (e: any) {
    ElMessage.error(e.message)
  }
  contextMenu.value.visible = false
}

async function handleMarkSpot() {
  const unit = contextMenu.value.unit
  if (!unit) return
  try {
    await ElMessageBox.confirm('确认标记为现货？', '确认', { type: 'warning' })
    await sandboxApi.markSpot(unit.unit_id)
    ElMessage.success('已标记')
    await forceRefreshAll()
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error(e.message)
  }
  contextMenu.value.visible = false
}



let cleanupFns: (() => void)[] = []

onMounted(async () => {
  await loadModelTypes()
  await safeFetchRushOrders()
  await refreshAll({ silent: true })
  wsConnect()
  // Listen to WS events for real-time updates
  cleanupFns.push(onEvent('unit:updated', () => refreshAll({ silent: true })))
  cleanupFns.push(onEvent('batch:updated', () => refreshAll({ silent: true })))
  cleanupFns.push(onEvent('batch:confirmed', () => refreshAll({ silent: true })))
  cleanupFns.push(onEvent('line:updated', () => refreshAll({ silent: true })))
  cleanupFns.push(onEvent('line:completed', () => refreshAll({ silent: true })))
})

onUnmounted(() => {
  cleanupFns.forEach(fn => fn())
  cleanupFns = []
  wsDisconnect()
})
</script>

<style scoped>
.ctx-item {
  padding: 6px 16px;
  cursor: pointer;
  font-size: 13px;
}
.ctx-item:hover { background: #f5f5f5; }
</style>
