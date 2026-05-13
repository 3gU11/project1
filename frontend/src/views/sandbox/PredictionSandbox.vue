<template>
  <div class="sandbox-layout">
    <div class="sandbox-header">
      <CapacityRatioEditor />
    </div>

    <div class="sandbox-filters">
      <el-select
        v-model="selectedSeriesFilters"
        multiple
        collapse-tags
        collapse-tags-tooltip
        clearable
        size="small"
        placeholder="系列筛选"
        style="width: 220px"
        @change="onSeriesFilterChange"
      >
        <el-option
          v-for="series in seriesFilterOptions"
          :key="series"
          :label="series"
          :value="series"
        />
      </el-select>
      <el-button size="small" @click="handleManualRefresh" :loading="batchStore.loading">刷新</el-button>
      <el-button size="small" type="primary" @click="handleRecompute" :loading="recomputing">
        全量重算
      </el-button>

      <el-button
        v-if="selectedBatches.length > 0"
        size="small"
        type="warning"
        @click="batchConfirm"
      >
        审核选中批次 ({{ selectedBatches.length }})
      </el-button>
      <el-button
        v-if="canRevoke"
        size="small"
        type="danger"
        @click="batchRevoke"
      >
        撤销审核
      </el-button>
    </div>

    <div ref="topScrollRef" class="top-scroll" @scroll="onTopScroll">
      <div :style="{ width: topScrollWidth + 'px' }"></div>
    </div>

    <div
      ref="batchesContainerRef"
      class="sandbox-batches"
      v-loading="batchStore.loading"
      @scroll="onBodyScroll"
      @mousemove="onEdgeHover"
      @mouseleave="stopEdgeAutoScroll"
    >
      <div
        v-if="filteredBatches.length === 0 && !batchStore.loading"
        style="padding:40px;text-align:center;width:100%;color:#999;"
      >
        暂无批次数据，请点击「全量重算」生成预测批次
      </div>
      <div
        v-for="batch in filteredBatches"
        :key="batch.batch_id"
        class="batch-card"
        :class="`type-${batch.model_type}`"
        :style="{ minWidth: '320px', borderLeft: selectedBatches.includes(batch.batch_id) ? '4px solid #409eff' : '' }"
        @click.self="toggleSelect(batch.batch_id)"
      >
        <div class="batch-header">
          <div>
            <el-checkbox
              :model-value="selectedBatches.includes(batch.batch_id)"
              @change="toggleSelect(batch.batch_id)"
              style="margin-right:6px;"
            />
            <span class="batch-title">[{{ displayBatchCategory(batch) }}] {{ batch.status === 'Predicted' ? '待定' : displayBatchCode(batch) }}</span>
            <span class="batch-meta">
              / 规划 {{ plannedCount(batch) }}
              <template v-if="displayBatchCategory(batch) !== '特殊'">
                / 备货 {{ stockCount(batch) }}
              </template>
              <template v-if="familyMismatchCount(batch) > 0">
                / <span class="mismatch-text">混放 {{ familyMismatchCount(batch) }}</span>
              </template>
            </span>
            <div class="batch-meta batch-meta-due">
              {{ batchDueRangeText(batch) }}
            </div>
            <div class="batch-meta batch-meta-models">
              {{ batchModelSummary(batch) }}
            </div>
          </div>
          <div>
            <el-tag v-if="batch.status === 'Predicted'" type="warning" size="small">待确认</el-tag>
            <el-tag v-else-if="batch.status === 'Confirmed'" type="success" size="small">已确认</el-tag>
            <el-tag v-else size="small">{{ batch.status }}</el-tag>
          </div>
        </div>
        <VueDraggable
          :model-value="batch.units || []"
          :group="{ name: batch.model_type, pull: true, put: true }"
          item-key="unit_id"
          :animation="180"
          draggable=".unit-card"
          filter=".locked"
          ghost-class="unit-ghost"
          chosen-class="unit-chosen"
          class="batch-units"
          @start="(evt: any) => onDragStart(evt, batch)"
          @add="(evt: any) => onUnitMoved(evt, batch)"
          @update="(evt: any) => onUnitMoved(evt, batch)"
          @end="onDragEnd"
        >
          <template v-for="u in batch.units" :key="u.unit_id">
            <UnitCard
              :class="{ 'unit-lane-mismatch': isUnitFamilyMismatch(u, batch) }"
              :unit="{ ...u, batch_model_type: batch.model_type }"
              :show-cross-lane="isCrossLanePlacement(u, batch)"
              :disable-progress-color="true"
              @edit="openEditDrawer"
              @contextmenu="onContextMenu"
            />
          </template>
        </VueDraggable>
        <button
          v-if="canAddSpecialCard(batch)"
          class="special-card-add"
          type="button"
          @click.stop="openSpecialAddDrawer(batch)"
        >
          <el-icon><Plus /></el-icon>
          <span>添加卡片</span>
        </button>
      </div>
    </div>

    <el-drawer v-model="editVisible" title="信息强改" size="400px">
      <el-form v-if="editingUnit" label-width="80px" size="small">
        <el-form-item label="合同号">
          <el-input v-model="editForm.contract_no" />
        </el-form-item>
        <el-form-item label="客户">
          <el-input v-model="editForm.customer" />
        </el-form-item>
        <el-form-item label="经销商">
          <el-input v-model="editForm.dealer_name" />
        </el-form-item>
        <el-form-item label="机型">
          <el-select
            v-model="editForm.model_type"
            filterable
            :allow-create="!isEditingSpecialBatch"
            default-first-option
            style="width:100%"
          >
            <el-option v-for="m in editModelTypes" :key="m" :label="m" :value="m" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="editForm.order_remark" type="textarea" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="saveEdit" :loading="saving">保存并锁定</el-button>
        </el-form-item>
      </el-form>
    </el-drawer>

    <el-drawer v-model="specialAddVisible" title="新增特殊卡片" size="420px">
      <el-form label-width="80px" size="small">
        <el-form-item label="合同号">
          <el-input v-model="specialAddForm.contract_no" />
        </el-form-item>
        <el-form-item label="客户">
          <el-input v-model="specialAddForm.customer" />
        </el-form-item>
        <el-form-item label="经销商">
          <el-input v-model="specialAddForm.dealer_name" />
        </el-form-item>
        <el-form-item label="机型" required>
          <el-select v-model="specialAddForm.model_type" filterable allow-create default-first-option style="width:100%">
            <el-option v-for="m in specialModelTypes" :key="m" :label="m" :value="m" />
          </el-select>
        </el-form-item>
        <el-form-item label="交期">
          <el-date-picker
            v-model="specialAddForm.due_date"
            type="date"
            value-format="YYYY-MM-DD"
            style="width:100%"
          />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="specialAddForm.order_remark" type="textarea" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="submitSpecialCard" :loading="specialAddSaving">提交</el-button>
        </el-form-item>
      </el-form>
    </el-drawer>

    <div
      v-if="contextMenu.visible"
      :style="{ position: 'fixed', left: contextMenu.x + 'px', top: contextMenu.y + 'px', zIndex: 9999 }"
      style="background:#fff;border-radius:6px;box-shadow:0 4px 12px rgba(0,0,0,0.15);padding:4px 0;min-width:120px;"
    >
      <div v-if="contextMenu.unit?.is_locked" class="ctx-item" @click="handleUnlock">解锁</div>
      <div v-if="canMoveToSpecial(contextMenu.unit)" class="ctx-item" @click="handleMoveToSpecial">转移到特殊批次</div>
      <div class="ctx-item" @click="handleMarkSpot">标记现货</div>
      <div class="ctx-item" @click="handleInsertEmptySlot">在此前插入空位</div>
      <div class="ctx-item" @click="contextMenu.visible = false">取消</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, onActivated, nextTick, h } from 'vue'
import { VueDraggable } from 'vue-draggable-plus'
import { ElMessage, ElMessageBox, ElDatePicker } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { useBatchStore } from '../../stores/useSandboxBatchStore'
import * as sandboxApi from '../../services/sandboxApi'
import { getApiErrorMessage } from '../../utils/request'
import UnitCard from '../../components/sandbox/UnitCard.vue'
import CapacityRatioEditor from '../../components/sandbox/CapacityRatioEditor.vue'
import { connect as wsConnect, disconnect as wsDisconnect, onEvent } from '../../services/sandboxWs'
import { categoryOfModel, normalizeMajorFamily } from '../../utils/sandboxCategory'

const batchStore = useBatchStore()
const recomputing = ref(false)

const selectedBatches = ref<string[]>([])
const editVisible = ref(false)
const editingUnit = ref<any>(null)
const saving = ref(false)
const specialAddVisible = ref(false)
const specialAddSaving = ref(false)
const specialAddBatch = ref<any>(null)
const contextMenu = ref<{ visible: boolean; x: number; y: number; unit: any }>({ visible: false, x: 0, y: 0, unit: null })
const dragging = ref(false)
const moving = ref(false)
const pendingRefresh = ref(false)
const suspendAutoSort = ref(false)
const pinnedBatchOrder = ref<string[]>([])
const dragSource = ref<{ unit: any; sourceBatchId: string } | null>(null)
const dragFamily = ref<string>('')
const dragLane = ref<string>('')
const modelTypes = ref<string[]>([])
const modelFamilyMap = ref<Record<string, string>>({})
const selectedSeriesFilters = ref<string[]>([])

const topScrollRef = ref<HTMLElement | null>(null)
const batchesContainerRef = ref<HTMLElement | null>(null)
const syncingScroll = ref(false)
const edgeAutoScrollTimer = ref<number | null>(null)
const topScrollWidth = ref(1200)

const editForm = ref({ contract_no: '', customer: '', dealer_name: '', model_type: '', order_remark: '' })
const specialAddForm = ref({ contract_no: '', customer: '', dealer_name: '', model_type: '', due_date: '', order_remark: '' })

const SANDBOX_STATUS = 'Predicted,Confirmed'
const SANDBOX_STATUS_SET = new Set(SANDBOX_STATUS.split(','))

const filteredBatches = computed(() => {
  let batches = [...batchStore.filteredBatches].filter((b: any) => SANDBOX_STATUS_SET.has(String(b?.status || '')))
  if (selectedSeriesFilters.value.length > 0) {
    const selected = new Set(selectedSeriesFilters.value)
    batches = batches.filter((b: any) => selected.has(displayBatchCategory(b)))
  }
  const pinnedIndex = new Map<string, number>()
  if (suspendAutoSort.value && pinnedBatchOrder.value.length > 0) {
    pinnedBatchOrder.value.forEach((id, idx) => pinnedIndex.set(String(id), idx))
  }
  if (!suspendAutoSort.value) {
    // 预测列排序：
    // 1) 按交期范围起始日期升序
    // 2) 有合同的批次排在无合同批次前
    // 3) 再按 slot_no / batch_no 稳定兜底
    batches.sort((a: any, b: any) => {
      const da = batchDueStartTime(a)
      const db = batchDueStartTime(b)
      if (da !== db) return da - db
      const ha = hasAnyContract(a) ? 1 : 0
      const hb = hasAnyContract(b) ? 1 : 0
      if (ha !== hb) return hb - ha
      const sa = batchSlotOrder(a)
      const sb = batchSlotOrder(b)
      if (sa !== sb) return sa - sb
      return (Number(a.batch_no) || 0) - (Number(b.batch_no) || 0)
    })
  } else if (pinnedIndex.size > 0) {
    batches.sort((a: any, b: any) => {
      const ia = pinnedIndex.get(String(a?.batch_id || ''))
      const ib = pinnedIndex.get(String(b?.batch_id || ''))
      if (ia !== undefined && ib !== undefined) return ia - ib
      if (ia !== undefined) return -1
      if (ib !== undefined) return 1
      return (Number(a?.batch_no) || 0) - (Number(b?.batch_no) || 0)
    })
  }
  return batches
})

function batchSlotOrder(batch: any): number {
  const slotNo = Number(batch?.forecast_slot_no)
  if (Number.isFinite(slotNo) && slotNo > 0) return slotNo
  return Number(batch?.batch_no || 0)
}

function batchDueStartTime(batch: any): number {
  const units = Array.isArray(batch?.units) ? batch.units : []
  const times = units
    .map((u: any) => String(u?.due_date || '').slice(0, 10))
    .filter((d: string) => /^\d{4}-\d{2}-\d{2}$/.test(d))
    .map((d: string) => new Date(`${d}T00:00:00`).getTime())
    .filter((t: number) => Number.isFinite(t))
  if (!times.length) return Number.MAX_SAFE_INTEGER
  return Math.min(...times)
}

function hasAnyContract(batch: any): boolean {
  const units = Array.isArray(batch?.units) ? batch.units : []
  return units.some((u: any) => String(u?.contract_no || '').trim() !== '')
}

// 当前编辑单元所属批次的大类（G/XS/AUTO）
const editingBatchFamily = computed(() => {
  if (!editingUnit.value) return ''
  const batch = batchStore.batches.find((b: any) => b.batch_id === editingUnit.value?.batch_id)
  return majorFamilyOfModel(batch?.model_type)
})

const editingBatchCategory = computed(() => {
  if (!editingUnit.value) return ''
  const batch = batchStore.batches.find((b: any) => b.batch_id === editingUnit.value?.batch_id)
  return batch ? displayBatchCategory(batch) : ''
})
const isEditingSpecialBatch = computed(() => {
  if (!editingUnit.value) return false
  const batch = batchStore.batches.find((b: any) => b.batch_id === editingUnit.value?.batch_id)
  if (!batch) return false
  return String(batch?.model_type || '').trim().toUpperCase() === 'SPECIAL' || displayBatchCategory(batch) === '特殊'
})

function isFamilyToken(modelType: string) {
  const upper = String(modelType || '').trim().toUpperCase()
  return upper === 'G' || upper === 'XS' || upper === 'AUTO' || upper === 'SPECIAL'
}

// 信息强改抽屉里的机型下拉：按当前列类别精确过滤，并排除大类名
const editModelTypes = computed(() => {
  const family = editingBatchFamily.value
  const category = editingBatchCategory.value
  const merged = new Set<string>([...modelTypes.value, ...batchStore.modelTypes])
  const all = [...merged]
    .map((m) => String(m || '').trim())
    .filter(Boolean)
    .filter((m) => !isFamilyToken(m))
    .sort()
  if (category === '特殊') {
    const filtered = all.filter((m: string) => {
      const mf = String(modelFamilyMap.value[m.toUpperCase()] || '')
      return normalizeMajorFamily(mf) === 'SPECIAL' || mf.includes('特殊') || mf.includes('鐗规畩')
    })
    return filtered
  }
  if (!family) return all
  if (category) {
    return all.filter((m: string) => categoryOfModel(m, modelFamilyMap.value[m.toUpperCase()] || '') === category)
  }
  return all.filter((m: string) => majorFamilyOfModel(m) === family)
})

const specialModelTypes = computed(() => {
  const merged = new Set<string>([...modelTypes.value, ...batchStore.modelTypes])
  return [...merged]
    .filter(Boolean)
    .filter((m: string) => {
      const family = modelFamilyMap.value[String(m).toUpperCase()] || ''
      return normalizeMajorFamily(family) === 'SPECIAL' || family.includes('特殊') || family.includes('鐗规畩')
    })
    .sort()
})

const seriesFilterOptions = ['小机G', '小机XS', '大机XS', '小机AUTO', '大机AUTO', '特殊']

function displayBatchCategory(batch: any) {
  const batchModel = String(batch?.model_type || '').trim()
  const batchUpper = batchModel.toUpperCase()
  if (batchUpper.includes('SPECIAL')) return '特殊'

  const batchFamily = majorFamilyOfModel(batchModel)
  const capacity = Number(batch?.capacity || 0)
  if (batchFamily === 'G') return '小机G'
  if (batchFamily === 'XS') return capacity === 16 ? '大机XS' : '小机XS'
  if (batchFamily === 'AUTO') return capacity === 16 ? '大机AUTO' : '小机AUTO'

  const units = Array.isArray(batch?.units) ? batch.units : []
  const count: Record<string, number> = {}
  for (const u of units) {
    const mt = String(u?.model_type || '').trim()
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
  const direct = categoryOfModel(batchModel, '')
  if (direct) return direct
  const family = majorFamilyOfModel(batchModel)
  if (family === 'G') return '小机G'
  if (family === 'XS') return '小机XS'
  if (family === 'AUTO') return '小机AUTO'
  if (family === 'SPECIAL') return '特殊'
  return String(batch?.model_type || '-')
}

function majorFamilyOfModel(modelType: string) {
  const model = String(modelType || '').trim()
  if (!model) return ''
  const byDict = modelFamilyMap.value[model.toUpperCase()]
  return normalizeMajorFamily(byDict || model)
}

function isStockUnit(unit: any) {
  return Boolean(unit?.is_stock || unit?.stock || !unit?.contract_no)
}

function sortBatchUnitsInPlace() {
  for (const batch of batchStore.batches) {
    if (Array.isArray(batch.units)) {
      batch.units.sort((a: any, b: any) => Number(a.slot_index ?? 0) - Number(b.slot_index ?? 0))
    }
  }
}

function batchDueRangeText(batch: any) {
  const inbound = String(batch?.expected_inbound_date || '').slice(0, 10)
  if (inbound) return `预计入库: ${inbound}`

  const dates = (batch.units || [])
    .map((u: any) => String(u?.due_date || '').slice(0, 10))
    .filter((d: string) => d && d !== 'null' && d !== 'undefined')
    .sort()
  if (!dates.length) return '-'
  return dates[0] === dates[dates.length - 1] ? dates[0] : `${dates[0]} ~ ${dates[dates.length - 1]}`
}

function batchModelSummary(batch: any) {
  const units = Array.isArray(batch?.units) ? batch.units : []
  const counter = new Map<string, number>()
  for (const u of units) {
    if (isSpecialPlaceholder(u)) continue
    const model = String(u?.model_type || '').trim()
    if (!model) continue
    counter.set(model, Number(counter.get(model) || 0) + 1)
  }
  if (counter.size === 0) return '机型数量: -'
  const sorted = [...counter.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
  return `机型数量: ${sorted.map(([model, count]) => `${model}×${count}`).join(' / ')}`
}

function plannedCount(batch: any) {
  if (displayBatchCategory(batch) === '特殊') return specialContractCount(batch)
  return (batch.units || []).filter((u: any) => !isStockUnit(u)).length
}

function stockCount(batch: any) {
  if (displayBatchCategory(batch) === '特殊') return 0
  return (batch.units || []).filter((u: any) => isStockUnit(u)).length
}

function isSpecialBatch(batch: any) {
  return String(batch?.model_type || '').trim().toUpperCase() === 'SPECIAL'
}

function isLargeMachineBatch(batch: any) {
  const family = majorFamilyOfModel(batch?.model_type || '')
  return Number(batch?.capacity || 0) === 16 && (family === 'XS' || family === 'AUTO')
}

function laneKeyOfBatch(batch: any) {
  if (!batch) return ''
  if (isSpecialBatch(batch)) return 'SPECIAL'
  const family = majorFamilyOfModel(batch?.model_type || '')
  if (!family) return ''
  if (family === 'G') return 'G-SMALL'
  const size = isLargeMachineBatch(batch) ? 'LARGE' : 'SMALL'
  return `${family}-${size}`
}

function canMoveAcrossLanes(sourceBatch: any, targetBatch: any, unit: any) {
  if (!sourceBatch || !targetBatch || !unit) return false
  if (sourceBatch?.status !== 'Predicted' || targetBatch?.status !== 'Predicted') return false
  const sourceSpecial = isSpecialBatch(sourceBatch)
  const targetSpecial = isSpecialBatch(targetBatch)
  if (sourceSpecial === targetSpecial) return false
  if (!sourceSpecial && !isLargeMachineBatch(sourceBatch)) return false
  if (!targetSpecial && !isLargeMachineBatch(targetBatch)) return false
  if (isStockUnit(unit) || isSpecialPlaceholder(unit)) return false
  const uf = majorFamilyOfModel(String(unit?.model_type || ''))
  if (!uf || (uf !== 'XS' && uf !== 'AUTO')) return false
  const anchorFamily = sourceSpecial
    ? majorFamilyOfModel(String(targetBatch?.model_type || ''))
    : majorFamilyOfModel(String(sourceBatch?.model_type || ''))
  return uf === anchorFamily
}

function isUnitFamilyMismatch(unit: any, batch: any) {
  if (!unit || !batch) return false
  if (isSpecialPlaceholder(unit)) return false
  if (isCrossLanePlacement(unit, batch)) return false
  const uf = majorFamilyOfModel(String(unit?.model_type || ''))
  const bf = majorFamilyOfModel(String(batch?.model_type || ''))
  if (!uf || !bf) return false
  return uf !== bf
}

function familyMismatchCount(batch: any) {
  const units = Array.isArray(batch?.units) ? batch.units : []
  return units.filter((u: any) => isUnitFamilyMismatch(u, batch)).length
}

function specialContractCount(batch: any) {
  return (batch?.units || []).filter((u: any) => !isSpecialPlaceholder(u)).length
}

function ownershipLaneKeyOfUnit(unit: any) {
  const model = String(unit?.model_type || '').trim()
  if (!model) return ''
  const category = categoryOfModel(model, modelFamilyMap.value[model.toUpperCase()] || '')
  if (category === '特殊') return 'SPECIAL'
  if (category === '大机XS') return 'XS-LARGE'
  if (category === '小机XS') return 'XS-SMALL'
  if (category === '大机AUTO') return 'AUTO-LARGE'
  if (category === '小机AUTO') return 'AUTO-SMALL'
  if (category === '小机G') return 'G-SMALL'
  const family = majorFamilyOfModel(model)
  if (family === 'SPECIAL') return 'SPECIAL'
  if (family === 'G') return 'G-SMALL'
  if (family === 'XS') return 'XS-SMALL'
  if (family === 'AUTO') return 'AUTO-SMALL'
  return ''
}

function isCrossLanePlacement(unit: any, batch: any) {
  if (!unit || !batch || isSpecialPlaceholder(unit)) return false
  const placed = laneKeyOfBatch(batch)
  const owner = ownershipLaneKeyOfUnit(unit)
  if (!placed || !owner || placed === owner) return false
  const ownerIsSpecial = owner === 'SPECIAL'
  const placedIsSpecial = placed === 'SPECIAL'
  if (ownerIsSpecial === placedIsSpecial) return false
  const otherLane = ownerIsSpecial ? placed : owner
  return otherLane === 'XS-LARGE' || otherLane === 'AUTO-LARGE'
}

function canAddSpecialCard(batch: any) {
  return Boolean(batch && batch.status === 'Predicted' && isSpecialBatch(batch) && specialContractCount(batch) < 15)
}

function isSpecialPlaceholder(unit: any) {
  const model = String(unit?.model_type || '').trim().toUpperCase()
  return model === 'SPECIAL' &&
    !String(unit?.contract_no || '').trim() &&
    !String(unit?.customer || '').trim() &&
    !String(unit?.dealer_name || '').trim() &&
    !String(unit?.due_date || '').trim() &&
    !String(unit?.order_remark || '').trim()
}

function batchOfUnit(unit: any) {
  if (!unit?.batch_id) return null
  return batchStore.batches.find((b: any) => b.batch_id === unit.batch_id) || null
}

function canMoveToSpecial(unit: any) {
  if (!unit || isStockUnit(unit)) return false
  const batch = batchOfUnit(unit)
  if (!batch || batch.status !== 'Predicted') return false
  if (isSpecialBatch(batch)) return false
  return isLargeMachineBatch(batch)
}

function formatBatchCode(batchNo: any) {
  const n = Number(batchNo)
  if (!Number.isFinite(n) || n <= 0) return `第 ${batchNo || '-'} 批`
  const whole = Math.trunc(n)
  if (whole >= 101) {
    const month = Math.floor(whole / 100)
    const seq = whole % 100
    if (month >= 1 && month <= 12 && seq >= 1) {
      return `${String(month).padStart(2, '0')}-${String(seq).padStart(2, '0')}`
    }
  }
  return `第 ${String(whole).padStart(2, '0')} 批`
}

const canRevoke = computed(() => {
  if (selectedBatches.value.length !== 1) return false
  const batch = batchStore.batches.find((b: any) => b.batch_id === selectedBatches.value[0])
  return batch?.status === 'Confirmed'
})

async function batchRevoke() {
  const selectedId = selectedBatches.value[0]
  if (!selectedId) return
  try {
    await ElMessageBox.confirm('撤销审核将删除 plan_import 中该批次的记录并恢复批次状态，确认？', '撤销审核', {
      confirmButtonText: '确认撤销',
      cancelButtonText: '取消',
      type: 'warning'
    })
    await sandboxApi.revokeBatch(selectedId)
    ElMessage.success('已撤销审核，批次恢复为待确认')
    selectedBatches.value = []
    await refresh()
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error(e.message || '撤销失败')
  }
}

function displayBatchCode(batch: any) {
  const explicit = String(batch?.batch_code || '').trim()
  if (explicit) return explicit
  return formatBatchCode(batch.batch_no)
}

function toggleSelect(batchId: string) {
  const idx = selectedBatches.value.indexOf(batchId)
  if (idx >= 0) selectedBatches.value.splice(idx, 1)
  else selectedBatches.value.push(batchId)
}

async function onSeriesFilterChange() {
  await syncScrollMetrics()
}

async function refresh() {
  if (dragging.value || moving.value) {
    pendingRefresh.value = true
    return
  }
  await batchStore.fetchBatches({ status: SANDBOX_STATUS })
  sortBatchUnitsInPlace()
  await syncScrollMetrics()
}

async function handleManualRefresh() {
  suspendAutoSort.value = false
  pinnedBatchOrder.value = []
  await refresh()
}

async function forceRefresh() {
  pendingRefresh.value = false
  await batchStore.fetchBatches({ status: SANDBOX_STATUS })
  sortBatchUnitsInPlace()
  await syncScrollMetrics()
}

async function flushPendingRefresh() {
  if (dragging.value || moving.value || !pendingRefresh.value) return
  pendingRefresh.value = false
  await batchStore.fetchBatches({ status: SANDBOX_STATUS })
  sortBatchUnitsInPlace()
  await syncScrollMetrics()
}

async function loadModelTypes() {
  try {
    const res = await sandboxApi.getModelTypes() as any
    const list = Array.isArray(res) ? res : (res?.model_types || res?.types || [])
    if (Array.isArray(list)) {
      const nextMap: Record<string, string> = {}
      modelTypes.value = list
        .map((item: any) => {
          if (typeof item === 'string') return item
          if (item && typeof item === 'object') {
            const mt = String(item.model_type || '').trim()
            const mf = String(item.model_family || '').trim()
            if (mt && mf) nextMap[mt.toUpperCase()] = mf
            return mt
          }
          return ''
        })
        .filter(Boolean)
      modelFamilyMap.value = nextMap
    } else {
      modelTypes.value = []
      modelFamilyMap.value = {}
    }
  } catch {
    modelTypes.value = []
    modelFamilyMap.value = {}
  }
}

async function handleRecompute() {
  recomputing.value = true
  try {
    await sandboxApi.recompute()
    ElMessage.success('全量重算完成')
    await refresh()
  } catch (e: any) {
    const status = Number(e?.response?.status || 0)
    if (status === 409) {
      ElMessage.warning('已有全量重算任务执行中，请稍后再试')
    } else if (status === 504) {
      ElMessage.warning('全量重算仍在执行或超时，请稍后刷新重试')
    } else {
      ElMessage.error(e.message || '全量重算失败')
    }
  } finally {
    recomputing.value = false
  }
}

async function batchConfirm() {
  if (selectedBatches.value.length !== 1) {
    ElMessage.warning('批量审核前请只勾选 1 个待审批次')
    return
  }
  const selectedId = selectedBatches.value[0]
  const batch = batchStore.batches.find((b: any) => b.batch_id === selectedId)
  if (!batch) return

  // Suggest next batch_code based on last used one (query DB, not page data)
  let hintText = ''
  let placeholder = '例如 04-12'
  try {
    const res: any = await sandboxApi.getLastBatchCode()
    const lastCode: string = res?.last_batch_code || ''
    if (lastCode && /^\d{2}-\d{2}$/.test(lastCode)) {
      const [m, s] = lastCode.split('-')
      const nextSeq = String(Number(s) + 1).padStart(2, '0')
      hintText = `\n上一批次: ${lastCode}，建议下一批次: ${m}-${nextSeq}`
      placeholder = `上一批次 ${lastCode}`
    }
  } catch {
    // silent — hint is optional
  }

  try {
    const input = await ElMessageBox.prompt(
      `请输入批次号（MM-SS）确认审核${hintText}`,
      '审核确认',
      {
        inputPlaceholder: placeholder,
        confirmButtonText: '下一步',
        cancelButtonText: '取消',
        inputPattern: /^\d{2}-\d{2}$/,
        inputErrorMessage: '格式必须为 MM-SS'
      })
    
    const batchCode = input.value

    // Ask for expected inbound date (default to batch's due_date_end or today)
    const defaultDate = batch.due_date_end
      ? new Date(batch.due_date_end).toISOString().slice(0, 10)
      : new Date().toISOString().slice(0, 10)
    const selectedDate = ref(defaultDate)

    await ElMessageBox({
      title: '预计入库时间',
      message: h('div', { style: 'padding: 8px 0' }, [
        h('p', { style: 'margin-bottom: 10px; color: #606266' }, '请选择预计入库时间'),
        h('input', {
          type: 'date',
          value: defaultDate,
          style: 'width: 220px; height: 32px; padding: 0 10px; border: 1px solid #dcdfe6; border-radius: 4px;',
          onInput: (e: Event) => {
            const target = e.target as HTMLInputElement | null
            selectedDate.value = target?.value || ''
          },
          onChange: (e: Event) => {
            const target = e.target as HTMLInputElement | null
            selectedDate.value = target?.value || ''
          }
        }),
      ]),
      confirmButtonText: '下一步',
      cancelButtonText: '取消',
    })
    const inboundDate = selectedDate.value || defaultDate

    // Preview serial number range before final confirm
    let previewMsg = ''
    try {
      const preview: any = await sandboxApi.previewSyncToPlan(selectedId, batchCode)
      if (preview && preview.count > 0) {
        previewMsg = `\n\n该批次共 ${preview.count} 张卡片待同步\n流水号范围: ${preview.first_serial} ~ ${preview.last_serial}`
      } else {
        previewMsg = '\n\n该批次无可同步卡片'
      }
    } catch {
      previewMsg = '\n\n（无法获取流水号预览）'
    }

    await ElMessageBox.confirm(
      `确认审核批次 ${batchCode}？\n预计入库时间: ${inboundDate}${previewMsg}`,
      '最终确认',
      { confirmButtonText: '确认审核', cancelButtonText: '取消', type: 'warning' }
    )

    await batchStore.confirmBatch(selectedId, batchCode, inboundDate)
    try {
      const syncResult = await sandboxApi.syncBatchToPlan(selectedId, batchCode)
      ElMessage.success(`审核通过，已同步 ${syncResult.count} 条至待排产`)
    } catch (syncErr: any) {
      ElMessage.warning('审核通过，但同步待排产失败: ' + (getApiErrorMessage(syncErr) || syncErr?.message || '未知错误'))
    }
    selectedBatches.value = []
    await refresh()
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error(e.message || '审核失败')
  }
}

function onDragStart(evt: any, sourceBatch: any) {
  dragging.value = true
  const idx = evt?.oldDraggableIndex ?? evt?.oldIndex
  const unit = getDraggedData(evt) || sourceBatch?.units?.[idx]
  dragSource.value = unit?.unit_id
    ? { unit, sourceBatchId: sourceBatch?.batch_id || unit.batch_id }
    : null
  dragFamily.value = majorFamilyOfModel(sourceBatch?.model_type || '')
  dragLane.value = laneKeyOfBatch(sourceBatch)
}

async function onDragEnd() {
  dragging.value = false
  dragFamily.value = ''
  dragLane.value = ''
  dragSource.value = null
  stopEdgeAutoScroll()
  await flushPendingRefresh()
}

function getDraggedData(evt: any) {
  return evt?.data || evt?.clonedData || evt?.item?.__draggable_context?.element
}

function getNewSlot(evt: any) {
  const idx = evt?.newDraggableIndex ?? evt?.newIndex
  if (idx === undefined || idx === null) return 0
  return idx + 1
}

async function onUnitMoved(evt: any, targetBatch: any) {
  const unit = dragSource.value?.unit || getDraggedData(evt)
  const sourceBatchId = dragSource.value?.sourceBatchId || unit?.batch_id
  const targetSlot = getNewSlot(evt)
  if (!unit?.unit_id || !targetBatch?.batch_id || !targetSlot) {
    await forceRefresh()
    return
  }
  if (isStockUnit(unit) && sourceBatchId && sourceBatchId !== targetBatch.batch_id) {
    ElMessage.warning('备货机台不可跨批拖拽')
    await forceRefresh()
    return
  }
  if (isUnitFamilyMismatch(unit, targetBatch)) {
    ElMessage.warning('仅允许同系列机型在同系列批次内移动')
    await forceRefresh()
    return
  }
  const sourceBatch = batchStore.batches.find((b: any) => b.batch_id === sourceBatchId)
  if (sourceBatch && laneKeyOfBatch(sourceBatch) !== laneKeyOfBatch(targetBatch) && !canMoveAcrossLanes(sourceBatch, targetBatch, unit)) {
    ElMessage.warning('仅允许在同列（同系列且同大小机）内拖拽')
    await forceRefresh()
    return
  }
  moving.value = true
  try {
    if (sourceBatchId === targetBatch.batch_id) {
      await sandboxApi.reorderUnitSlot(unit.unit_id, targetSlot)
    } else {
      await sandboxApi.moveUnitBatch(unit.unit_id, targetBatch.batch_id, targetSlot)
    }
    if (!suspendAutoSort.value) {
      pinnedBatchOrder.value = filteredBatches.value.map((b: any) => String(b?.batch_id || ''))
    }
    suspendAutoSort.value = true
    ElMessage.success('机台位置已更新')
    await forceRefresh()
  } catch (e: any) {
    ElMessage.error('移动失败: ' + (e.message || '未知错误'))
    await forceRefresh()
  } finally {
    moving.value = false
    await flushPendingRefresh()
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
  if (isEditingSpecialBatch.value && isFamilyToken(editForm.value.model_type)) {
    editForm.value.model_type = ''
  }
  editVisible.value = true
}

async function saveEdit() {
  if (!editingUnit.value) return
  saving.value = true
  try {
    const batch = batchStore.batches.find((b: any) => b.batch_id === editingUnit.value?.batch_id)
    if (batch && isUnitFamilyMismatch({ ...editingUnit.value, model_type: editForm.value.model_type }, batch)) {
      ElMessage.warning('机型与批次系列不匹配，请选择同系列机型')
      return
    }
    await sandboxApi.updateUnit(editingUnit.value.unit_id, editForm.value)
    ElMessage.success('已保存并锁定')
    editVisible.value = false
    refresh()
  } catch (e: any) {
    ElMessage.error(e.message)
  } finally {
    saving.value = false
  }
}

function openSpecialAddDrawer(batch: any) {
  specialAddBatch.value = batch
  specialAddForm.value = { contract_no: '', customer: '', dealer_name: '', model_type: '', due_date: '', order_remark: '' }
  specialAddVisible.value = true
}

async function submitSpecialCard() {
  const batch = specialAddBatch.value
  if (!batch?.batch_id) return
  const payload = {
    batch_id: batch.batch_id,
    contract_no: String(specialAddForm.value.contract_no || '').trim(),
    customer: String(specialAddForm.value.customer || '').trim(),
    dealer_name: String(specialAddForm.value.dealer_name || '').trim(),
    model_type: String(specialAddForm.value.model_type || '').trim(),
    due_date: String(specialAddForm.value.due_date || '').trim(),
    order_remark: String(specialAddForm.value.order_remark || '').trim()
  }
  if (!payload.model_type) {
    ElMessage.warning('请选择机型')
    return
  }
  specialAddSaving.value = true
  try {
    await sandboxApi.createSpecialCard(payload)
    ElMessage.success('特殊卡片已添加')
    specialAddVisible.value = false
    await refresh()
  } catch (e: any) {
    ElMessage.error(getApiErrorMessage(e) || e.message || '添加特殊卡片失败')
  } finally {
    specialAddSaving.value = false
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
    refresh()
  } catch (e: any) {
    ElMessage.error(e.message)
  }
  contextMenu.value.visible = false
}

async function handleMarkSpot() {
  const unit = contextMenu.value.unit
  if (!unit) return
  try {
    await ElMessageBox.confirm('确认将此机台标记为现货（清除订单信息）？', '确认', { type: 'warning' })
    const res: any = await sandboxApi.markSpot(unit.unit_id)
    if (res && res.blocked_or_warned_units && res.blocked_or_warned_units.length > 0) {
      ElMessage.warning(`已标记为现货，但同合同下仍有 ${res.blocked_or_warned_units.length} 台设备已确认或生产中，需人工处理`)
    } else {
      ElMessage.success('已标记为现货，同合同计划已取消')
    }
    refresh()
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error(e.message)
  }
  contextMenu.value.visible = false
}

async function handleInsertEmptySlot() {
  const unit = contextMenu.value.unit
  contextMenu.value.visible = false
  if (!unit) return
  try {
    await sandboxApi.insertEmptySlot(unit.batch_id, unit.slot_index)
    ElMessage.success('空位已在此卡片前插入')
    refresh()
  } catch (e: any) {
    ElMessage.error(e.message || '插入空位失败')
  }
}

async function handleMoveToSpecial() {
  const unit = contextMenu.value.unit
  contextMenu.value.visible = false
  if (!unit) return
  try {
    await sandboxApi.moveUnitToSpecial(unit.unit_id)
    ElMessage.success('已转移到特殊批次')
    await refresh()
  } catch (e: any) {
    ElMessage.error(getApiErrorMessage(e) || e.message || '转移到特殊批次失败')
  }
}

async function syncScrollMetrics() {
  await nextTick()
  const body = batchesContainerRef.value
  if (!body) return
  topScrollWidth.value = body.scrollWidth
}

function onTopScroll() {
  const top = topScrollRef.value
  const body = batchesContainerRef.value
  if (!top || !body || syncingScroll.value) return
  syncingScroll.value = true
  body.scrollLeft = top.scrollLeft
  requestAnimationFrame(() => { syncingScroll.value = false })
}

function onBodyScroll() {
  const top = topScrollRef.value
  const body = batchesContainerRef.value
  if (!top || !body || syncingScroll.value) return
  syncingScroll.value = true
  top.scrollLeft = body.scrollLeft
  requestAnimationFrame(() => { syncingScroll.value = false })
}

function stopEdgeAutoScroll() {
  if (edgeAutoScrollTimer.value) {
    window.clearInterval(edgeAutoScrollTimer.value)
    edgeAutoScrollTimer.value = null
  }
}

function onEdgeHover(e: MouseEvent) {
  if (!dragging.value) {
    stopEdgeAutoScroll()
    return
  }
  const body = batchesContainerRef.value
  if (!body) return
  const rect = body.getBoundingClientRect()
  const edge = 50
  const speed = 18
  let dir = 0
  if (e.clientX < rect.left + edge) dir = -1
  if (e.clientX > rect.right - edge) dir = 1
  if (!dir) {
    stopEdgeAutoScroll()
    return
  }
  if (edgeAutoScrollTimer.value) return
  edgeAutoScrollTimer.value = window.setInterval(() => {
    body.scrollLeft += dir * speed
    onBodyScroll()
  }, 16)
}

let cleanupFns: (() => void)[] = []

onMounted(async () => {
  await loadModelTypes()
  await refresh()
  wsConnect()
  cleanupFns.push(onEvent('unit:updated', () => refresh()))
  cleanupFns.push(onEvent('batch:updated', () => refresh()))
  cleanupFns.push(onEvent('batch:confirmed', () => refresh()))
  window.addEventListener('resize', syncScrollMetrics)
})

onActivated(async () => {
  await refresh()
})

onUnmounted(() => {
  cleanupFns.forEach(fn => fn())
  cleanupFns = []
  window.removeEventListener('resize', syncScrollMetrics)
  stopEdgeAutoScroll()
  wsDisconnect()
})
</script>

<style scoped>
.top-scroll {
  overflow-x: auto;
  overflow-y: hidden;
  height: 14px;
  margin-bottom: 4px;
  border-radius: 4px;
}
.sandbox-batches {
  /* 隐藏原生底部滚动条，统一使用顶部 top-scroll */
  scrollbar-width: none;
}
.sandbox-batches::-webkit-scrollbar {
  display: none;
}
.ctx-item {
  padding: 6px 16px;
  cursor: pointer;
  font-size: 13px;
}
.ctx-item:hover { background: #f5f5f5; }


.batch-meta-due {
  display: block;
  text-align: center;
}

.batch-meta-models {
  display: inline-block;
  text-align: center;
  color: #1f2d3d;
  font-size: 13px;
  font-weight: 700;
  margin-top: 4px;
  padding: 2px 8px;
  border-radius: 10px;
  background: #eef3ff;
  border: 1px solid #c9d7ff;
}

.special-card-add {
  width: 100%;
  min-height: 54px;
  margin-top: 8px;
  border: 1px dashed #d81b60;
  border-radius: 6px;
  background: #fff7fb;
  color: #b81250;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  font-size: 13px;
}

.special-card-add:hover {
  background: #ffeaf3;
  border-color: #b81250;
}

.mismatch-text {
  color: #d4380d;
  font-weight: 600;
}

.unit-lane-mismatch :deep(.unit-card) {
  box-shadow: 0 0 0 2px rgba(212, 56, 13, 0.45) inset;
}
</style>
