<template>
  <div class="sandbox-layout">
    <div class="sandbox-header">
      <CapacityRatioEditor />
    </div>

    <div class="sandbox-filters">
      <el-radio-group
        v-model="selectedSeriesFilters"
        @change="onSeriesFilterChange"
        class="series-tabs"
      >
        <el-radio-button label="">全部</el-radio-button>
        <el-radio-button
          v-for="series in seriesFilterOptions"
          :key="series"
          :label="series"
        />
      </el-radio-group>
      <el-button @click="handleManualRefresh" :loading="batchStore.loading">刷新</el-button>
      <el-button type="primary" @click="handleRecompute" :loading="recomputing">
        {{ recomputeButtonText }}
      </el-button>

      <el-button
        v-if="selectedBatches.length > 0"
        type="warning"
        @click="batchConfirm"
      >
        审核选中列
      </el-button>
      <el-button
        v-if="canRevoke"
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
        :class="[`type-${batch.model_type}`, { 'batch-confirmed': batch.status === 'Confirmed', 'batch-target-slot': isTargetOptimizedBatch(batch), 'batch-recompute-target': isSelectedRecomputeTarget(batch), 'batch-placeholder-slot': isNonTargetPredictedBatch(batch), 'is-valid-drop-target': dragging && isValidDragTargetBatch(batch), 'is-invalid-drop-target': dragging && !isValidDragTargetBatch(batch) }]"
        :style="{ position: 'relative', width: '390px', minWidth: '390px', maxWidth: '390px', borderLeft: selectedBatches.includes(batchSlotOrder(batch)) ? '4px solid #409eff' : '' }"
      >
        <div v-if="targetBadgeText(batch)" class="batch-target-badge">
          {{ targetBadgeText(batch) }}
        </div>
        <div class="batch-status-top-right">
          <el-tag v-if="batch.status === 'Predicted'" type="warning" size="small" class="corner-tag">待确认</el-tag>
          <el-tag v-else-if="batch.status === 'Confirmed'" type="success" size="small" class="corner-tag">已确认</el-tag>
          <el-tag v-else size="small" class="corner-tag">{{ batch.status }}</el-tag>
        </div>
        <div class="batch-header" @click="toggleSelect(batchSlotOrder(batch))" style="cursor: pointer;">
          <div class="batch-header-main">
            <div class="batch-headline">
              <el-checkbox
                :model-value="selectedBatches.includes(batchSlotOrder(batch))"
                @change="toggleSelect(batchSlotOrder(batch))"
                class="batch-select"
                @click.stop
              />
              <span class="batch-title">[{{ displayBatchCategory(batch) }}]{{ batch.status === 'Predicted' ? '' : ' ' + displayBatchCode(batch) }}</span>
              
              <span class="batch-meta batch-counts">
                <span class="batch-count batch-count-ordered">已订 {{ orderedCount(batch) }}</span>
                <template v-if="displayBatchCategory(batch) !== '特殊'">
                  <span class="batch-count-separator">/</span>
                  <span class="batch-count batch-count-stock">备货 {{ stockCount(batch) }}</span>
                </template>
                <template v-if="familyMismatchCount(batch) > 0">
                  <span class="batch-count-separator">/</span>
                  <span class="batch-count mismatch-text">混放 {{ familyMismatchCount(batch) }}</span>
                </template>
              </span>
            </div>

            <!-- Capacity Progress Bar -->
            <div 
              class="batch-capacity-bar" 
              :title="`容量: ${batch.capacity || 15} (已订: ${orderedCount(batch)}, 备货: ${stockCount(batch)}, 空槽: ${Math.max(0, (batch.capacity || 15) - orderedCount(batch) - stockCount(batch))})`"
            >
              <div class="bar-segment segment-ordered" :style="{ width: (orderedCount(batch) / (batch.capacity || 15) * 100) + '%' }"></div>
              <div class="bar-segment segment-stock" :style="{ width: (stockCount(batch) / (batch.capacity || 15) * 100) + '%' }"></div>
              <div class="bar-segment segment-empty" :style="{ width: (Math.max(0, (batch.capacity || 15) - orderedCount(batch) - stockCount(batch)) / (batch.capacity || 15) * 100) + '%' }"></div>
            </div>

            <div class="batch-meta batch-meta-due">
              {{ batchDueRangeText(batch) }}
            </div>
            <!-- 批次号和预计入库时间的输入放到列顶 -->
            <div v-if="batch.status === 'Predicted'" class="batch-top-inputs" @click.stop>
              <div class="input-row">
                <el-input
                  v-model="batchCodeInputs[batch.batch_id]"
                  placeholder="批次号"
                  style="width: 170px"
                />
                <el-date-picker
                  v-model="inboundDateInputs[batch.batch_id]"
                  type="date"
                  value-format="YYYY-MM-DD"
                  placeholder="预计入库时间"
                  style="width: 190px"
                  :clearable="false"
                />
              </div>
            </div>
            <div
              class="batch-meta batch-placeholder-note"
              :style="{ visibility: isNonTargetPredictedBatch(batch) ? 'visible' : 'hidden' }"
            >
              备货占位
            </div>
            <div class="batch-meta batch-meta-models">
              <template v-if="batchModelSummaryRows(batch).length">
                <div
                  v-for="row in batchModelSummaryRows(batch)"
                  :key="row.model"
                  class="batch-model-row"
                >
                  <span class="batch-model-name">{{ row.model }}</span>
                  <span v-if="row.ordered > 0" class="model-count-ordered">已订{{ row.ordered }}</span>
                  <span v-if="row.stock > 0" class="model-count-stock">备货{{ row.stock }}</span>
                </div>
              </template>
              <template v-else>机型数量: -</template>
            </div>
          </div>
        </div>
        <div v-if="canEditBatchStock(batch) && stockEditRows(batch).length" class="stock-editor" @click.stop>
          <div
            v-for="row in stockEditRows(batch)"
            :key="row.model"
            class="stock-editor-row"
          >
            <span class="stock-editor-model">{{ row.model }}</span>
            <el-input-number
              v-model="stockEdits[batch.batch_id][row.model]"
              size="small"
              :min="0"
              :step="1"
              :precision="0"
              controls-position="right"
              class="stock-editor-input"
            />
          </div>
          <div v-if="stockEditError(batch)" class="stock-editor-error">
            {{ stockEditError(batch) }}
          </div>
          <div class="stock-editor-actions">
            <el-button size="small" text @click.stop="resetBatchStockEdit(batch)">重置</el-button>
            <el-button
              size="small"
              type="primary"
              :loading="Boolean(stockSaving[batch.batch_id])"
              :disabled="Boolean(stockEditError(batch)) || !isBatchStockDirty(batch)"
              @click.stop="saveBatchStockEdit(batch)"
            >
              保存
            </el-button>
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
              :class="{ 
                'hidden-card': !getStockPlaceholderStackInfo(u, batch).show,
                'unit-lane-mismatch': isUnitFamilyMismatch(u, batch), 
                'unit-stock-placeholder': isNonTargetStockPlaceholder(u, batch),
                'unit-stacked-card': getStockPlaceholderStackInfo(u, batch).isStacked,
                'is-active-dropzone': dragging && isValidDragTargetBatch(batch) && (isUnitEmptySlot(u) || isStockUnit(u))
              }"
              :unit="{ ...u, batch_model_type: batch.model_type, model_family: u.model_family || modelFamilyMap[String(u.model_type || '').toUpperCase()] || '' }"
              :stock-placeholder="isNonTargetStockPlaceholder(u, batch)"
              :show-cross-lane="isCrossLanePlacement(u, batch)"
              :disable-progress-color="true"
              :stack-count="getStockPlaceholderStackInfo(u, batch).count"
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
          <el-input v-model="editForm.contract_no" disabled />
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
      <div v-if="canConvertToRush(contextMenu.unit)" class="ctx-item" @click="handleConvertToRush">转为急单</div>
      <div v-if="canMoveToSpecial(contextMenu.unit)" class="ctx-item" @click="handleMoveToSpecial">转移到特殊批次</div>
      <div class="ctx-item" @click="handleMarkSpot">标记现货</div>
      <div class="ctx-item" @click="handleInsertEmptySlot">在此前插入空位</div>
      <div class="ctx-item" @click="contextMenu.visible = false">取消</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, onActivated, nextTick } from 'vue'
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
const optimizedTargetSlotNo = ref(1)

const selectedBatches = ref<number[]>([])
const batchCodeInputs = ref<Record<string, string>>({})
const inboundDateInputs = ref<Record<string, string>>({})
const lastBatchCodeFromDB = ref('')
let enterRecomputed = false



function initBatchInputs() {
  for (const batch of batchStore.batches) {
    if (String(batch.status || '') === 'Predicted') {
      const id = batch.batch_id
      if (batchCodeInputs.value[id] === undefined) {
        batchCodeInputs.value[id] = ''
      }
      if (inboundDateInputs.value[id] === undefined) {
        inboundDateInputs.value[id] = ''
      }
    }
  }
}

async function fetchLastBatchCode() {
  try {
    const res: any = await sandboxApi.getLastBatchCode()
    lastBatchCodeFromDB.value = res?.last_batch_code || ''
  } catch {
    lastBatchCodeFromDB.value = ''
  }
}

async function autoRecomputeOnEnter() {
  recomputing.value = true
  let recomputeRes: any = null
  try {
    recomputeRes = await sandboxApi.recompute(1, false)
    ElMessage.success('已自动进行全量重算')
  } catch (e: any) {
    console.error('Auto-recompute on load failed:', e)
  } finally {
    recomputing.value = false
  }
  await refresh()
  // 全量重算后，根据大类缺口自动定位本次备货建议列
  const suggestedSlot = findSuggestedSlotByGap(recomputeRes?.achievement?.categories)
  optimizedTargetSlotNo.value = suggestedSlot
}
const selectedRecomputeTarget = computed(() => {
  if (selectedBatches.value.length !== 1) return null
  const selectedSlot = Number(selectedBatches.value[0])
  const batch = batchStore.batches.find((b: any) => batchSlotOrder(b) === selectedSlot)
  if (!batch || String(batch.status || '') !== 'Predicted' || isSpecialBatch(batch)) return null
  return batch
})
const recomputeButtonText = computed(() => {
  return selectedRecomputeTarget.value ? '按选中列重算' : '全量重算'
})
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
const selectedSeriesFilters = ref<string>('')
const stockEdits = ref<Record<string, Record<string, number>>>({})
const stockSaving = ref<Record<string, boolean>>({})

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
  if (selectedSeriesFilters.value) {
    batches = batches.filter((b: any) => displayBatchCategory(b) === selectedSeriesFilters.value)
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

// 根据大类库存缺口自动推断本次备货建议列
// categories 来自 recompute 响应的 achievement.categories
// 找出 gap_pct 最小（最缺）的大类对应的第一个预测列
function findSuggestedSlotByGap(categories?: any[]): number {
  const productionCats = ['中小型G', '中小型XS', '中大型XS', '中小型AUTO', '中大型AUTO']
  const catToFamily: Record<string, string> = {
    '中小型G': 'G',
    '中小型XS': 'XS',
    '中大型XS': 'XS',
    '中小型AUTO': 'AUTO',
    '中大型AUTO': 'AUTO',
  }
  if (!categories || categories.length === 0) return 1
  // 仅考虑有目标占比的大类
  const valid = categories.filter(
    (c: any) => productionCats.includes(c.name) && (c.target_pct ?? 0) > 0
  )
  if (valid.length === 0) return 1
  // 找 gap_pct 最小（最缺货）的大类，gap_pct = current_pct - target_pct
  valid.sort((a: any, b: any) => (a.gap_pct ?? 0) - (b.gap_pct ?? 0))
  const mostNeeded = valid[0]
  const targetFamily = catToFamily[mostNeeded.name] ?? 'XS'
  // 在当前 batches 中找到该 family 下排在最前的预测列
  const candidates = batchStore.batches.filter(
    (b: any) => String(b.status || '') === 'Predicted' &&
      !isSpecialBatch(b) &&
      String(b.model_type || '').toUpperCase() === targetFamily.toUpperCase()
  )
  if (candidates.length === 0) return 1
  candidates.sort((a: any, b: any) => batchSlotOrder(a) - batchSlotOrder(b))
  return batchSlotOrder(candidates[0])
}

function isTargetOptimizedBatch(batch: any) {
  return String(batch?.status || '') === 'Predicted' &&
    !isSpecialBatch(batch) &&
    batchSlotOrder(batch) === optimizedTargetSlotNo.value
}

function isSelectedRecomputeTarget(batch: any) {
  return Boolean(batch?.batch_id && selectedRecomputeTarget.value?.batch_id === batch.batch_id)
}

function targetBadgeText(batch: any) {
  if (isSelectedRecomputeTarget(batch)) return '重算目标'
  if (isTargetOptimizedBatch(batch)) return '本次备货建议'
  return ''
}

function isNonTargetPredictedBatch(batch: any) {
  return String(batch?.status || '') === 'Predicted' &&
    !isSpecialBatch(batch) &&
    !isTargetOptimizedBatch(batch)
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

const seriesFilterOptions = ['中小型G', '中小型XS', '中大型XS', '中小型AUTO', '中大型AUTO', '特殊']

function displayBatchCategory(batch: any) {
  const batchModel = String(batch?.model_type || '').trim()
  const batchUpper = batchModel.toUpperCase()
  if (batchUpper.includes('SPECIAL')) return '特殊'

  const batchFamily = majorFamilyOfModel(batchModel)
  const capacity = Number(batch?.capacity || 0)
  if (batchFamily === 'G') return '中小型G'
  if (batchFamily === 'XS') return capacity === 16 ? '中大型XS' : '中小型XS'
  if (batchFamily === 'AUTO') return capacity === 16 ? '中大型AUTO' : '中小型AUTO'

  const units = Array.isArray(batch?.units) ? batch.units : []
  const count: Record<string, number> = {}
  for (const u of units) {
    const mt = String(u?.model_type || '').trim()
    const c = categoryOfModel(mt, modelFamilyMap.value[mt.toUpperCase()] || '')
    if (!c) continue
    count[c] = Number(count[c] || 0) + 1
  }
  const priority: Record<string, number> = {
    特殊: 6, 中大型AUTO: 5, 中小型AUTO: 4, 中大型XS: 3, 中小型XS: 2, 中小型G: 1
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
  if (family === 'G') return '中小型G'
  if (family === 'XS') return '中小型XS'
  if (family === 'AUTO') return '中小型AUTO'
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

function isNonTargetStockPlaceholder(unit: any, batch: any) {
  return isStockUnit(unit) && !isSpecialPlaceholder(unit) && isNonTargetPredictedBatch(batch)
}

function isUnitEmptySlot(unit: any) {
  const hasContract = !!unit.contract_no
  const hasModel = !!String(unit.model_type_detail || unit.model_type || '').trim()
  return !hasContract && !hasModel
}

function getStockPlaceholderStackInfo(unit: any, batch: any) {
  if (!batch || !Array.isArray(batch.units)) {
    return { isStacked: false, count: 1, show: true };
  }
  
  const isStock = isStockUnit(unit) && !isSpecialPlaceholder(unit);
  if (!isStock) {
    return { isStacked: false, count: 1, show: true };
  }
  
  const units = batch.units;
  const idx = units.findIndex((u: any) => u.unit_id === unit.unit_id);
  if (idx === -1) {
    return { isStacked: false, count: 1, show: true };
  }
  
  const currentModel = String(unit.model_type || '').trim().toUpperCase();
  
  const firstIdx = units.findIndex((u: any) => {
    return isStockUnit(u) && !isSpecialPlaceholder(u) && String(u.model_type || '').trim().toUpperCase() === currentModel;
  });
  if (idx > firstIdx) {
    return { isStacked: true, count: 0, show: false };
  }
  
  let count = 0;
  for (let i = 0; i < units.length; i++) {
    const u = units[i];
    if (isStockUnit(u) && !isSpecialPlaceholder(u) && String(u.model_type || '').trim().toUpperCase() === currentModel) {
      count++;
    }
  }
  
  return {
    isStacked: count > 1,
    count: count,
    show: true
  };
}

function isValidDragTargetBatch(targetBatch: any) {
  if (!dragging.value || !dragSource.value) return false
  const unit = dragSource.value.unit
  const sourceBatchId = dragSource.value.sourceBatchId
  
  // 1. Stock units cannot drag across batches
  if (isStockUnit(unit) && sourceBatchId && sourceBatchId !== targetBatch.batch_id) {
    return false
  }
  
  // 2. Family matching check
  if (isUnitFamilyMismatch(unit, targetBatch)) {
    const canContractFirstOccupy = sourceBatchId && sourceBatchId !== targetBatch.batch_id && hasUnboundPlaceholder(targetBatch)
    if (!canContractFirstOccupy) {
      return false
    }
  }
  
  // 3. Lane matching check
  const sourceBatch = batchStore.batches.find((b: any) => b.batch_id === sourceBatchId)
  if (sourceBatch && laneKeyOfBatch(sourceBatch) !== laneKeyOfBatch(targetBatch) && !canMoveAcrossLanes(sourceBatch, targetBatch, unit)) {
    return false
  }
  
  return true
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

function batchModelSummaryRows(batch: any) {
  const units = Array.isArray(batch?.units) ? batch.units : []
  const counter = new Map<string, { model: string; ordered: number; stock: number }>()
  for (const u of units) {
    if (isSpecialPlaceholder(u)) continue
    const model = String(u?.model_type || '').trim()
    if (!model) continue
    const current = counter.get(model) || { model, ordered: 0, stock: 0 }
    if (isStockUnit(u)) {
      current.stock += 1
    } else {
      current.ordered += 1
    }
    counter.set(model, current)
  }
  return [...counter.values()].filter((row) => row.ordered > 0 || row.stock > 0).sort((a, b) => {
    const totalA = a.ordered + a.stock
    const totalB = b.ordered + b.stock
    return totalB - totalA || a.model.localeCompare(b.model)
  })
}

function orderedCount(batch: any) {
  if (displayBatchCategory(batch) === '特殊') return specialContractCount(batch)
  return (batch.units || []).filter((u: any) => !isStockUnit(u)).length
}

function stockCount(batch: any) {
  if (displayBatchCategory(batch) === '特殊') return 0
  return (batch.units || []).filter((u: any) => isStockUnit(u)).length
}

function canEditBatchStock(batch: any) {
  return isTargetOptimizedBatch(batch) && displayBatchCategory(batch) !== seriesFilterOptions[5]
}

function currentStockCounts(batch: any) {
  const counts: Record<string, number> = {}
  const units = Array.isArray(batch?.units) ? batch.units : []
  for (const u of units) {
    if (!isStockUnit(u) || isSpecialPlaceholder(u)) continue
    const model = String(u?.model_type || '').trim()
    if (!model) continue
    counts[model] = Number(counts[model] || 0) + 1
  }
  return counts
}

function orderedModelNames(batch: any) {
  const models = new Set<string>()
  const units = Array.isArray(batch?.units) ? batch.units : []
  for (const u of units) {
    if (isStockUnit(u) || isSpecialPlaceholder(u)) continue
    const model = String(u?.model_type || '').trim()
    if (model) models.add(model)
  }
  return [...models]
}

function resetBatchStockEdit(batch: any) {
  const batchId = String(batch?.batch_id || '')
  if (!batchId) return
  const counts = { ...currentStockCounts(batch) }
  for (const model of orderedModelNames(batch)) {
    if (counts[model] === undefined) counts[model] = 0
  }
  stockEdits.value[batchId] = counts
}

function resetAllStockEdits() {
  const next: Record<string, Record<string, number>> = {}
  for (const batch of batchStore.batches) {
    const batchId = String(batch?.batch_id || '')
    if (!batchId) continue
    next[batchId] = { ...currentStockCounts(batch) }
  }
  stockEdits.value = next
}

function ensureBatchStockEdit(batch: any) {
  const batchId = String(batch?.batch_id || '')
  if (!batchId) return {}
  if (!stockEdits.value[batchId]) {
    resetBatchStockEdit(batch)
  }
  return stockEdits.value[batchId] || {}
}

function stockEditRows(batch: any) {
  const edit = ensureBatchStockEdit(batch)
  const current = currentStockCounts(batch)
  const models = new Set<string>([...orderedModelNames(batch), ...Object.keys(current), ...Object.keys(edit)])
  return [...models]
    .filter(Boolean)
    .sort((a, b) => a.localeCompare(b))
    .map((model) => ({ model }))
}

function stockEditTotal(batch: any) {
  const edit = ensureBatchStockEdit(batch)
  return Object.values(edit).reduce((sum, n) => sum + Math.max(0, Number(n) || 0), 0)
}

function stockEditError(batch: any) {
  const ordered = orderedCount(batch)
  const stock = stockEditTotal(batch)
  const capacity = Number(batch?.capacity || 0)
  if (ordered + stock > capacity) {
    return `已订 ${ordered} + 备货 ${stock} 超过本批次容量 ${capacity}`
  }
  return ''
}

function isBatchStockDirty(batch: any) {
  const edit = ensureBatchStockEdit(batch)
  const current = currentStockCounts(batch)
  const models = new Set<string>([...Object.keys(current), ...Object.keys(edit)])
  for (const model of models) {
    if ((Number(edit[model]) || 0) !== (Number(current[model]) || 0)) return true
  }
  return false
}

async function saveBatchStockEdit(batch: any) {
  const batchId = String(batch?.batch_id || '')
  if (!batchId || stockEditError(batch)) return
  const edit = ensureBatchStockEdit(batch)
  const stocks = Object.keys(edit)
    .sort((a, b) => a.localeCompare(b))
    .map((model) => ({ model_type: model, count: Math.max(0, Math.trunc(Number(edit[model]) || 0)) }))
  stockSaving.value[batchId] = true
  try {
    await sandboxApi.updateBatchStockModels(batchId, stocks)
    ElMessage.success('备货数量已保存')
    await refresh()
  } catch (e: any) {
    resetBatchStockEdit(batch)
    ElMessage.error(getApiErrorMessage(e) || e.message || '备货数量保存失败')
  } finally {
    stockSaving.value[batchId] = false
  }
}

function isSpecialBatch(batch: any) {
  return String(batch?.model_type || '').trim().toUpperCase() === 'SPECIAL'
}

function isLargeMachineBatch(batch: any) {
  const category = displayBatchCategory(batch)
  return category === '中大型XS' || category === '中大型AUTO'
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

function hasUnboundPlaceholder(batch: any) {
  const units = Array.isArray(batch?.units) ? batch.units : []
  return units.some((u: any) => isStockUnit(u) && !isSpecialPlaceholder(u))
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
  if (category === '中大型XS') return 'XS-LARGE'
  if (category === '中小型XS') return 'XS-SMALL'
  if (category === '中大型AUTO') return 'AUTO-LARGE'
  if (category === '中小型AUTO') return 'AUTO-SMALL'
  if (category === '中小型G') return 'G-SMALL'
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
  const category = categoryOfModel(String(unit?.model_type || ''), modelFamilyMap.value[String(unit?.model_type || '').toUpperCase()] || '')
  return category === '中大型XS' || category === '中大型AUTO'
}

function canConvertToRush(unit: any) {
  if (!unit || isStockUnit(unit) || isSpecialPlaceholder(unit)) return false
  if (!String(unit?.contract_no || '').trim()) return false
  if (!String(unit?.model_type || '').trim()) return false
  const batch = batchOfUnit(unit)
  return Boolean(batch && batch.status === 'Predicted')
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
  const selectedSlot = Number(selectedBatches.value[0])
  const batch = batchStore.batches.find((b: any) => batchSlotOrder(b) === selectedSlot)
  return batch?.status === 'Confirmed'
})

async function batchRevoke() {
  if (selectedBatches.value.length !== 1) return
  const selectedSlot = Number(selectedBatches.value[0])
  const batch = batchStore.batches.find((b: any) => batchSlotOrder(b) === selectedSlot)
  if (!batch) return
  const selectedId = batch.batch_id
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

async function toggleSelect(slotNo: number) {
  if (recomputing.value || batchStore.loading) return
  const isSelected = selectedBatches.value[0] === slotNo
  selectedBatches.value = isSelected ? [] : [slotNo]
  
  if (!isSelected) {
    // 选中列直接进行重算
    const selectedBatch = batchStore.batches.find((b: any) => batchSlotOrder(b) === slotNo)
    if (selectedBatch && String(selectedBatch.status || '') === 'Predicted' && !isSpecialBatch(selectedBatch)) {
      recomputing.value = true
      try {
        await sandboxApi.recompute(slotNo, true)
        optimizedTargetSlotNo.value = slotNo
        ElMessage.success(`已按选中列(第 ${slotNo} 列)重算备货建议`)
        await refresh()
      } catch (e: any) {
        const status = Number(e?.response?.status || 0)
        if (status === 409) {
          ElMessage.warning('已有重算任务执行中，请稍后再试')
        } else if (status === 504) {
          ElMessage.warning('重算仍在执行或超时，请稍后刷新重试')
        } else {
          ElMessage.error(e.message || '重算失败')
        }
      } finally {
        recomputing.value = false
      }
    }
  }
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
  initBatchInputs()
  resetAllStockEdits()
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
  initBatchInputs()
  resetAllStockEdits()
  await syncScrollMetrics()
}

async function flushPendingRefresh() {
  if (dragging.value || moving.value || !pendingRefresh.value) return
  pendingRefresh.value = false
  await batchStore.fetchBatches({ status: SANDBOX_STATUS })
  sortBatchUnitsInPlace()
  initBatchInputs()
  resetAllStockEdits()
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
  let targetSlotNo: number | undefined
  let isClicked = false
  if (selectedBatches.value.length === 1) {
    const selectedSlot = Number(selectedBatches.value[0])
    const selectedBatch = batchStore.batches.find((b: any) => batchSlotOrder(b) === selectedSlot)
    if (!selectedBatch || String(selectedBatch.status || '') !== 'Predicted') {
      ElMessage.warning('请选择 1 个待确认预测批次作为重算目标列')
      return
    }
    targetSlotNo = batchSlotOrder(selectedBatch)
    isClicked = true
  }
  if (!targetSlotNo || targetSlotNo <= 0) {
    targetSlotNo = 1
    isClicked = false
  }
  recomputing.value = true
  try {
    const recomputeRes: any = await sandboxApi.recompute(targetSlotNo, isClicked)
    selectedBatches.value = []
    ElMessage.success('已按目标列优化备货比例，其他预测列备货仅作占位参考')
    await refresh()
    if (isClicked) {
      // 点击单列：直接标记选中列为备货建议
      optimizedTargetSlotNo.value = targetSlotNo ?? 1
    } else {
      // 全量重算：根据大类缺口自动找最需要备货的列
      const suggestedSlot = findSuggestedSlotByGap(recomputeRes?.achievement?.categories)
      optimizedTargetSlotNo.value = suggestedSlot
    }
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
    ElMessage.warning('审核前请勾选 1 个待审批次')
    return
  }
  const selectedSlot = Number(selectedBatches.value[0])
  const batch = batchStore.batches.find((b: any) => batchSlotOrder(b) === selectedSlot)
  if (!batch) return
  const selectedId = batch.batch_id

  // 从列顶获取输入的批次号和预计入库时间
  const batchCode = String(batchCodeInputs.value[selectedId] || '').trim()
  if (!batchCode) {
    ElMessage.warning('请在列顶输入批次号')
    return
  }
  const codePattern = /^\d{2}-\d{2}[\u4e00-\u9fa5A-Za-z0-9_-]{0,20}$/
  if (!codePattern.test(batchCode)) {
    ElMessage.warning('批次号格式错误：必须以 MM-SS 开头，后面可追加20字以内中文/字母/数字/下划线/中划线')
    return
  }

  const inboundDate = String(inboundDateInputs.value[selectedId] || '').trim()
  if (!inboundDate) {
    ElMessage.warning('请在列顶选择预计入库时间')
    return
  }

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

  try {
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
    const canContractFirstOccupy = sourceBatchId && sourceBatchId !== targetBatch.batch_id && hasUnboundPlaceholder(targetBatch)
    if (!canContractFirstOccupy) {
      ElMessage.warning('仅允许同系列机型在同系列批次内移动')
      await forceRefresh()
      return
    }
  }
  const sourceBatch = batchStore.batches.find((b: any) => b.batch_id === sourceBatchId)
  if (sourceBatch && laneKeyOfBatch(sourceBatch) !== laneKeyOfBatch(targetBatch) && !canMoveAcrossLanes(sourceBatch, targetBatch, unit)) {
    ElMessage.warning('仅允许在同列（同系列且同大类）内拖拽')
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
    const { contract_no: _, ...data } = editForm.value as any
    await sandboxApi.updateUnit(editingUnit.value.unit_id, data)
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

async function handleConvertToRush() {
  const unit = contextMenu.value.unit
  contextMenu.value.visible = false
  if (!unit) return
  try {
    await ElMessageBox.confirm(
      `确认将合同 ${unit.contract_no || '-'} 的这张卡片转为急单？原沙盘卡片会清空为占位。`,
      '转为急单',
      { type: 'warning', confirmButtonText: '转为急单', cancelButtonText: '取消' }
    )
    await sandboxApi.convertUnitToRush(unit.unit_id)
    ElMessage.success('已转为急单，可在生产看板急单队列中处理')
    await refresh()
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error(getApiErrorMessage(e) || e.message || '转为急单失败')
  }
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
  await fetchLastBatchCode()
  if (!enterRecomputed) {
    enterRecomputed = true
    await autoRecomputeOnEnter()
  } else {
    await refresh()
  }
  wsConnect()
  cleanupFns.push(onEvent('unit:updated', () => refresh()))
  cleanupFns.push(onEvent('batch:updated', () => refresh()))
  cleanupFns.push(onEvent('batch:confirmed', () => refresh()))
  window.addEventListener('resize', syncScrollMetrics)
})

onActivated(async () => {
  if (!enterRecomputed) {
    enterRecomputed = true
    await autoRecomputeOnEnter()
  } else {
    await refresh()
  }
})

onUnmounted(() => {
  enterRecomputed = false
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

.batch-header-main {
  min-width: 0;
  flex: 1 1 auto;
}

.batch-headline {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  width: 100%;
  white-space: nowrap;
  line-height: 1.25;
}

.batch-select {
  flex: 0 0 auto;
  margin-right: 2px;
}

.batch-headline .batch-title {
  flex: 0 1 auto;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.25;
  font-size: 17px;
  font-weight: 700;
}

.batch-counts {
  flex: 0 0 auto;
  max-width: 100%;
  white-space: nowrap;
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 15px;
  font-weight: 700;
  padding-left: 8px;
  border-left: 1px solid #d7dce5;
  line-height: 1.25;
  overflow: hidden;
}

.batch-count {
  line-height: 1.25;
}

.batch-count-ordered {
  color: #0f766e;
}

.batch-count-stock {
  color: #d97706;
}

.batch-count-separator {
  color: #c4c9d4;
  font-weight: 700;
}

.batch-status-top-right {
  position: absolute;
  top: 0;
  right: 0;
  z-index: 10;
}

.batch-target-badge {
  position: absolute;
  top: 0;
  left: 0;
  z-index: 10;
  padding: 2px 8px;
  border-bottom-right-radius: 8px;
  background: #2563eb;
  color: #fff;
  font-size: 12px;
  font-weight: 700;
  line-height: 20px;
}

.batch-target-slot,
.batch-recompute-target {
  box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.35) inset;
}

.corner-tag {
  border-top-left-radius: 0;
  border-bottom-right-radius: 0;
  border-top-right-radius: 8px;
  border-bottom-left-radius: 8px;
  border-top: none;
  border-right: none;
  font-weight: 700;
}

.batch-meta-due {
  display: block;
  text-align: center;
  font-size: 13.5px;
  color: #4b5563;
  font-weight: 600;
}

.batch-meta-models {
  display: block;
  text-align: left;
  color: #1f2d3d;
  font-size: 15px;
  font-weight: 700;
  margin-top: 4px;
  padding: 6px 12px;
  border-radius: 10px;
  background: #eef3ff;
  border: 1px solid #c9d7ff;
  height: 86px;
  overflow-y: auto;
}

.batch-placeholder-note {
  margin-top: 2px;
  color: #8a6d3b;
  font-size: 13px;
  font-weight: 700;
}

.batch-placeholder-slot {
  opacity: 0.82;
}

.batch-model-row {
  display: flex;
  align-items: baseline;
  justify-content: center;
  gap: 8px;
  line-height: 1.55;
  white-space: normal;
  word-break: break-all;
}

.batch-model-name {
  min-width: 0;
}

.model-count-ordered {
  color: #0f766e;
  font-weight: 600;
}

.model-count-stock {
  color: #d97706;
  font-weight: 600;
}

.stock-editor {
  margin: 8px 8px 0;
  padding: 8px;
  border: 1px solid #d7dce5;
  border-radius: 6px;
  background: #fff;
}

.stock-editor-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 118px;
  gap: 8px;
  align-items: center;
  min-height: 32px;
}

.stock-editor-row + .stock-editor-row {
  margin-top: 6px;
}

.stock-editor-model {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  font-weight: 700;
  color: #1f2d3d;
}

.stock-editor-input {
  width: 118px;
}

.stock-editor-error {
  margin-top: 6px;
  color: #d4380d;
  font-size: 12px;
  line-height: 1.4;
}

.stock-editor-actions {
  display: flex;
  justify-content: flex-end;
  gap: 6px;
  margin-top: 8px;
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

/* 沙盘批次列内的卡片需要撑满列宽（生产看板不适用此规则，所以在此处局部覆盖） */
.batch-units :deep(.unit-card) {
  width: calc(100% - 8px) !important;
  box-sizing: border-box !important;
}

.unit-lane-mismatch :deep(.unit-card) {
  box-shadow: 0 0 0 2px rgba(212, 56, 13, 0.45) inset;
}

.unit-stock-placeholder :deep(.unit-card) {
  border-style: dashed;
  opacity: 0.72;
}

.batch-top-inputs {
  margin-top: 8px;
  margin-bottom: 6px;
  padding: 0 4px;
}

.batch-top-inputs :deep(.el-input),
.batch-top-inputs :deep(.el-date-editor) {
  height: 38px !important;
}

.batch-top-inputs :deep(.el-input__wrapper) {
  height: 38px !important;
  box-sizing: border-box !important;
  padding: 4px 10px !important;
}

.batch-top-inputs :deep(.el-input__inner) {
  height: 100% !important;
  font-size: 13px !important;
  font-weight: 700 !important;
  color: #0f172a !important;
}

.batch-top-inputs :deep(.el-input__inner::placeholder) {
  color: #475569 !important;
  opacity: 1 !important;
}
.batch-top-inputs :deep(.el-input__inner::-webkit-input-placeholder) {
  color: #475569 !important;
}
.batch-top-inputs :deep(.el-input__inner::-moz-placeholder) {
  color: #475569 !important;
}
.batch-top-inputs :deep(.el-input__inner:-ms-input-placeholder) {
  color: #475569 !important;
}

.input-row {
  display: flex;
  align-items: center;
  gap: 8px;
  justify-content: space-between;
}

.series-tabs :deep(.el-radio-button__inner) {
  min-height: 38px !important;
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
  font-size: var(--font-size-base) !important;
  font-weight: 500 !important;
  padding: 6px 16px !important;
  transition: all 0.3s cubic-bezier(0.2, 0, 0, 1) !important;
}

.series-tabs :deep(.el-radio-button:first-child .el-radio-button__inner) {
  border-top-left-radius: var(--radius-md) !important;
  border-bottom-left-radius: var(--radius-md) !important;
}

.series-tabs :deep(.el-radio-button:last-child .el-radio-button__inner) {
  border-top-right-radius: var(--radius-md) !important;
  border-bottom-right-radius: var(--radius-md) !important;
}

/* Batch capacity and confirmation status styling updates */
.batch-card.batch-confirmed {
  background-color: #f0fdf4 !important; /* soft green success background */
  border: 1px solid #bbf7d0 !important;
  box-shadow: 0 4px 10px rgba(16, 185, 129, 0.04) !important;
}

.batch-capacity-bar {
  display: flex;
  height: 6px;
  background-color: #f1f5f9;
  border-radius: 3px;
  overflow: hidden;
  margin: 8px 0;
  width: 100%;
  box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.05);
}

.bar-segment {
  height: 100%;
  transition: width 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.segment-ordered {
  background-color: #10b981; /* Emerald Green */
}

.segment-stock {
  background-color: #f59e0b; /* Warm Amber */
}

.segment-empty {
  background-color: #cbd5e1; /* Slate/Gray */
}

.batch-top-inputs :deep(.el-input__wrapper),
.batch-top-inputs :deep(.el-date-editor) {
  background-color: #ffffff !important;
  border: 1.5px solid #94a3b8 !important;
  box-shadow: none !important;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}

.batch-top-inputs :deep(.el-input__wrapper:hover),
.batch-top-inputs :deep(.el-input__wrapper.is-focus) {
  background-color: #ffffff !important;
  border-color: #2563eb !important;
  box-shadow: 0 0 0 1px #2563eb !important;
}

/* Drag and drop interactive guides */
.batch-card.is-valid-drop-target {
  box-shadow: 0 0 0 2.5px #10b981, 0 4px 12px rgba(16, 185, 129, 0.08) !important;
  background-color: #f0fdf4 !important;
  transition: all 0.25s ease !important;
}

.batch-card.is-invalid-drop-target {
  opacity: 0.35 !important;
  pointer-events: none !important;
  transition: all 0.25s ease !important;
}

:deep(.unit-card.is-active-dropzone) {
  border: 2px dashed #10b981 !important;
  background: #f0fdf4 !important;
  animation: dropzone-pulse 2s infinite ease-in-out !important;
}

:deep(.hidden-card) {
  display: none !important;
}

@keyframes dropzone-pulse {
  0%, 100% {
    box-shadow: 0 0 0 0px rgba(16, 185, 129, 0.2);
  }
  50% {
    box-shadow: 0 0 0 4px rgba(16, 185, 129, 0.4);
  }
}
</style>
