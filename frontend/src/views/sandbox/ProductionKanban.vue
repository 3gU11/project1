<template>
  <div class="kanban-layout">
    <div class="kanban-left">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
        <h3 style="font-size:16px;">产线监控 ({{ lineStore.lines.length }} 条)</h3>
        <div style="display:flex;align-items:center;gap:8px;">
          <el-button size="small" @click="() => refreshAll()" :loading="lineStore.loading">刷新</el-button>
          <el-dropdown trigger="click" @command="handleDownloadCommand">
            <el-button type="primary" size="small">
              下载报表<el-icon class="el-icon--right"><ArrowDown /></el-icon>
            </el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="ledger">下载排产报表</el-dropdown-item>
                <el-dropdown-item command="tracking">下载跟踪单</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </div>

      <div v-if="transferStore.selectingTargetFor" class="selecting-banner">
        <span>请点击产线中的机台作为调货目标</span>
        <el-button size="small" @click="transferStore.cancelTargetSelection()">取消</el-button>
      </div>

      <div>
        <div v-for="line in lineStore.lines" :key="line.production_line_id" class="production-line" :data-line-id="line.production_line_id">
          <div class="line-header">
            <span class="line-name">{{ line.line_name }}</span>
            <span class="line-status" :class="line.status === 'Idle' ? 'idle' : 'busy'">
              {{ line.status === 'Idle' ? '空闲' : '忙碌' }}
            </span>
            <span v-if="line.model_type" style="font-size:12px;color:#888;">{{ line.model_type }}</span>
            <span v-if="lineBatchLabels(line)" style="font-size:15px;color:#222;font-weight:bold;margin-left:8px;">{{ lineBatchLabels(line) }}</span>
            <span v-if="lineExpectedInboundLabels(line)" class="line-inbound-date">
              {{ lineExpectedInboundLabels(line) }}
            </span>
            <span style="flex:1;"></span>
            <el-button
              v-if="line.status === 'Busy'"
              size="small" type="warning" @click="handleManualComplete(line.production_line_id)"
            >
              手动完工
            </el-button>
            <el-button
              v-if="line.status === 'Busy'"
              size="small"
              type="danger"
              :disabled="selectedCount(line) === 0"
              @click="showLockDialog(line)"
            >
              锁定{{ selectedCount(line) ? `(${selectedCount(line)})` : '' }}
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
              <UnitCard
                :unit="{ ...u, model_family: u.model_family || modelFamilyMap[String(u.model_type || '').toUpperCase()] || '' }"
                :selected="isUnitSelected(line.production_line_id, u.unit_id)"
                @select="() => toggleUnitSelection(line.production_line_id, u)"
                @edit="openEditDrawer"
                @contextmenu="onContextMenu"
              />
            </template>
          </VueDraggable>
          <div v-else style="color:#bbb;font-size:12px;padding:8px;">
            空闲 - 可分配待排产批次
          </div>
        </div>
      </div>
    </div>

    <div class="kanban-right">
      <div class="sidebar-panel" style="flex: 3">
        <RushOrderEntry @auto-inserted="() => refreshAll({ silent: true })" />
      </div>

      <div class="sidebar-panel" style="flex: 2">
        <TransferSwapPanel />
      </div>

      <div class="sidebar-panel" style="flex: 1">
        <div class="queue-section">
          <h3 class="queue-title">
            待排产队列
            <el-select v-model="queueFilter" size="small" style="width:100px;margin-left:8px;" clearable placeholder="全部">
              <el-option label="中小型G" value="中小型G" />
              <el-option label="中小型XS" value="中小型XS" />
              <el-option label="中大型XS" value="中大型XS" />
              <el-option label="中小型AUTO" value="中小型AUTO" />
              <el-option label="中大型AUTO" value="中大型AUTO" />
              <el-option label="特殊" value="特殊" />
            </el-select>
          </h3>
          <div class="queue-scroll">
            <div v-for="batch in queueBatches" :key="batch.batch_id" class="queue-batch-item">
              <div class="queue-batch-card">
                <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;">
                  <span class="queue-batch-label">
                    <strong>[{{ displayBatchCategory(batch) }}] {{ displayBatchCode(batch) }}</strong>
                    ({{ batch.units?.length || 0 }}/{{ batch.capacity }})
                  </span>
                  <el-button
                    size="small" type="primary"
                    @click="showAssignDialog(batch)"
                    :disabled="assignableLinesForBatch(batch).length === 0"
                  >
                    整批分配
                  </el-button>
                </div>
                <div style="font-size:11px;color:#999;">
                  {{ fmtDate(batch.due_date_start) }} ~ {{ fmtDate(batch.due_date_end) }}
                </div>
              </div>
            </div>
            <div v-if="queueBatches.length === 0 && !batchStore.loading" class="queue-empty">
              暂无待排产批次
            </div>
          </div>
        </div>

      </div>
    </div>
  </div>

  <el-button
    class="stats-floating-toggle"
    type="primary"
    @click="statsPanelOpen = !statsPanelOpen"
  >
    {{ statsPanelOpen ? '收起列表' : '打开列表' }}
  </el-button>

  <el-collapse-transition>
    <div v-show="statsPanelOpen" class="kanban-stats-panel stats-floating-panel">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
        <span style="font-weight:bold;color:#303133;">排产汇总列表</span>
        <el-button size="small" type="primary" @click="exportSummaryToExcel">导出汇总 Excel</el-button>
      </div>
      <el-table
        :data="kanbanStatsRows"
        size="small"
        border
        stripe
        empty-text="暂无统计数据"
        max-height="calc(100vh - 190px)"
        :span-method="statsSpanMethod"
        :row-class-name="statsRowClassName"
      >
        <el-table-column prop="groupName" label="分组" min-width="180">
          <template #default="{ row }">
            <div class="stat-group-cell" :class="{ 'queue-group': !row.lineId }">
              <span class="stat-group-name">{{ row.groupName }}</span>
              <el-button
                v-if="row.lineId"
                size="small"
                type="primary"
                link
                @click.stop="navigateToLine(row.lineId)"
              >
                定位
              </el-button>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="batchLabel" label="批次号" min-width="160" />
        <el-table-column prop="modelType" label="机型" min-width="180" />
        <el-table-column prop="expectedInbound" label="预计入库时间" min-width="180" />
        <el-table-column prop="ordered" label="已订数量" width="130" align="right">
          <template #default="{ row }">
            <span class="stat-number ordered">{{ row.ordered }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="stock" label="备货数量" width="130" align="right">
          <template #default="{ row }">
            <span class="stat-number stock">{{ row.stock }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="total" label="合计" width="120" align="right">
          <template #default="{ row }">
            <span class="stat-number total">{{ row.total }}</span>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </el-collapse-transition>

    <el-dialog v-model="assignVisible" title="整批分配" width="400px">
      <p>选择空闲产线分配批次 {{ assigningBatch?.batch_id?.slice(0,25) }}...</p>
      <el-select v-model="selectedLineId" placeholder="选择产线" style="width:100%">
        <el-option v-for="l in assignableLines" :key="l.production_line_id" :label="assignableLineLabel(l)" :value="l.production_line_id" />
      </el-select>
      <template #footer>
        <el-button @click="assignVisible = false">取消</el-button>
        <el-button type="primary" @click="doAssign" :disabled="!selectedLineId" :loading="assigning2">确认分配</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="lockVisible" title="批量锁定" width="420px">
      <div style="font-size:13px;margin-bottom:10px;">
        将锁定已选 {{ lockSelectedCount }} 张卡片，并覆盖这些卡片的备注。
      </div>
      <el-input
        v-model="lockRemark"
        type="textarea"
        :rows="4"
        placeholder="请输入备注"
      />
      <template #footer>
        <el-button @click="lockVisible = false">取消</el-button>
        <el-button type="danger" @click="doLockUnits" :disabled="lockSelectedCount === 0" :loading="locking">确认锁定</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="editVisible" title="信息强改" size="400px">
      <el-form v-if="editingUnit" label-width="80px" size="small">
        <el-form-item label="合同号"><el-input v-model="editForm.contract_no" disabled /></el-form-item>
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
      <div class="ctx-item ctx-item-primary" @click="handleTransferUrgent">急合同调货</div>
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
import { useTransferStore } from '../../stores/useSandboxTransferStore'
import * as sandboxApi from '../../services/sandboxApi'
import UnitCard from '../../components/sandbox/UnitCard.vue'
import RushOrderEntry from '../../components/sandbox/RushOrderEntry.vue'
import TransferSwapPanel from '../../components/sandbox/TransferSwapPanel.vue'
import { connect as wsConnect, disconnect as wsDisconnect, onEvent } from '../../services/sandboxWs'
import { categoryOfModel, normalizeMajorFamily } from '../../utils/sandboxCategory'
import { apiDownloadBlob, apiDownloadBlobPost } from '../../utils/request'
import { ArrowDown } from '@element-plus/icons-vue'

const batchStore = useBatchStore()
const lineStore = useLineStore()
const rushStore = useRushStore()
const transferStore = useTransferStore()

const queueFilter = ref('')
const statsPanelOpen = ref(false)
const assignVisible = ref(false)
const assigningBatch = ref<any>(null)
const selectedLineId = ref<string | null>(null)
const assigning2 = ref(false)
const editVisible = ref(false)
const editingUnit = ref<any>(null)
const saving = ref(false)
const contextMenu = ref<{ visible: boolean; x: number; y: number; unit: any }>({ visible: false, x: 0, y: 0, unit: null })
const selectedByLine = ref<Record<string, string[]>>({})
const lockVisible = ref(false)
const lockingLine = ref<any>(null)
const lockRemark = ref('')
const locking = ref(false)
const dragging = ref(false)
const pendingRefresh = ref(false)
const modelFamilyMap = ref<Record<string, string>>({})


const editForm = ref({ contract_no: '', customer: '', dealer_name: '', model_type: '', order_remark: '' })

type KanbanStatRow = {
  groupName: string
  lineId: string
  groupOrder: number
  batchKey: string
  batchLabel: string
  batchOrder: number
  modelType: string
  expectedInbound: string
  ordered: number
  stock: number
  total: number
}

function unitExpectedInbound(unit: any, fallback: string) {
  const date = fmtDate(unit?.batch_expected_inbound_date || unit?.fg_expected_inbound_date)
  if (date && date !== '-') return date
  return fallback
}

function addUnitToStats(
  group: Map<string, { modelType: string; expectedInbound: string; ordered: number; stock: number }>,
  unit: any,
  fallbackInbound: string
) {
  const modelType = String(unit?.model_type || '').trim()
  if (!modelType) return
  const expectedInbound = unitExpectedInbound(unit, fallbackInbound)
  const key = `${modelType}__${expectedInbound}`
  const current = group.get(key) || { modelType, expectedInbound, ordered: 0, stock: 0 }
  if (String(unit?.contract_no || '').trim()) {
    current.ordered += 1
  } else {
    current.stock += 1
  }
  group.set(key, current)
}

function buildStatRows(
  groupName: string,
  lineId: string,
  batchKey: string,
  batchLabel: string,
  batch: any,
  units: any[],
  groupOrder: number,
  batchOrder: number
): KanbanStatRow[] {
  const fallbackInbound = batchExpectedInboundLabel(batch, units)
  const group = new Map<string, { modelType: string; expectedInbound: string; ordered: number; stock: number }>()
  for (const unit of units) addUnitToStats(group, unit, fallbackInbound)
  return Array.from(group.values())
    .map((counts) => ({
      groupName,
      lineId,
      groupOrder,
      batchKey,
      batchLabel,
      batchOrder,
      modelType: counts.modelType,
      expectedInbound: counts.expectedInbound,
      ordered: counts.ordered,
      stock: counts.stock,
      total: counts.ordered + counts.stock
    }))
    .sort((a, b) => b.total - a.total || a.modelType.localeCompare(b.modelType, 'zh-Hans-CN'))
}

function batchIdentity(batch: any, fallback: string) {
  return String(batch?.batch_id || batch?.id || fallback).trim()
}

function batchExpectedInboundLabel(batch: any, units: any[]) {
  const dates = Array.from(new Set(
    [
      batch?.expected_inbound_date,
      ...units.map((u: any) => u?.batch_expected_inbound_date || u?.fg_expected_inbound_date)
    ]
      .map((value: any) => fmtDate(value))
      .filter((date: string) => date && date !== '-')
  ))
  return dates.join(', ')
}

const queueBatches = computed(() => {
  let batches = batchStore.batches.filter((b: any) => b.status === 'Confirmed')
  if (queueFilter.value) batches = batches.filter((b: any) => displayBatchCategory(b) === queueFilter.value)
  return batches
})

const kanbanStatsRows = computed<KanbanStatRow[]>(() => {
  const rows: KanbanStatRow[] = []
  lineStore.lines.forEach((line: any, index: number) => {
    const units = Array.isArray(line?.units) ? line.units : []
    const batches = Array.isArray(line?.batches) ? line.batches : []
    const batchById = new Map<string, any>()
    const batchByCode = new Map<string, any>()
    batches.forEach((batch: any, batchIndex: number) => {
      const id = batchIdentity(batch, `line-${index}-batch-${batchIndex}`)
      if (id) batchById.set(id, batch)
      const batchNo = String(batch?.batch_no || '').trim()
      if (batchNo) batchByCode.set(batchNo, batch)
      const code = String(displayBatchCode(batch) || '').trim()
      if (code) batchByCode.set(code, batch)
    })

    if (!batchById.size && batches.length === 1) {
      batchById.set(batchIdentity(batches[0], `line-${index}-batch-0`), batches[0])
    }

    const unitsByBatch = new Map<string, any[]>()
    units.forEach((unit: any) => {
      const fallbackBatchId = batches.length === 1 ? batchIdentity(batches[0], `line-${index}-batch-0`) : ''
      const unitBatchId = String(unit?.batch_id || fallbackBatchId || 'unknown').trim()
      const list = unitsByBatch.get(unitBatchId) || []
      list.push(unit)
      unitsByBatch.set(unitBatchId, list)
    })

    Array.from(unitsByBatch.entries()).forEach(([batchId, batchUnits], batchIndex) => {
      const batch = batchById.get(batchId) || batchByCode.get(batchId)
      const batchLabel = batch ? displayBatchCode(batch) : (batchId === 'unknown' ? '-' : batchId)
      rows.push(...buildStatRows(
        String(line?.line_name || line?.production_line_id || '未命名产线'),
        String(line?.production_line_id || ''),
        batchId,
        batchLabel,
        batch,
        batchUnits,
        index,
        batchIndex
      ))
    })
  })

  queueBatches.value.forEach((batch: any, index: number) => {
    const units = Array.isArray(batch?.units) ? batch.units : []
    const batchId = batchIdentity(batch, `queue-batch-${index}`)
    rows.push(...buildStatRows(
      '待排产队列',
      '',
      batchId,
      displayBatchCode(batch),
      batch,
      units,
      Number.MAX_SAFE_INTEGER,
      index
    ))
  })
  return rows
})

function statsRowspan(rowIndex: number, sameAs: (row: KanbanStatRow, current: KanbanStatRow) => boolean) {
  const rows = kanbanStatsRows.value
  const current = rows[rowIndex]
  if (!current) return 1
  if (rowIndex > 0 && sameAs(rows[rowIndex - 1], current)) return 0
  let span = 1
  for (let i = rowIndex + 1; i < rows.length; i += 1) {
    if (!sameAs(rows[i], current)) break
    span += 1
  }
  return span
}

function statsSpanMethod({ rowIndex, columnIndex }: { rowIndex: number; columnIndex: number }) {
  if (columnIndex === 0) {
    const rowspan = statsRowspan(rowIndex, (row, current) => row.groupName === current.groupName)
    return { rowspan, colspan: rowspan ? 1 : 0 }
  }
  if (columnIndex === 1) {
    const rowspan = statsRowspan(rowIndex, (row, current) =>
      row.groupName === current.groupName && row.batchKey === current.batchKey
    )
    return { rowspan, colspan: rowspan ? 1 : 0 }
  }
  if (columnIndex === 3) {
    const rowspan = statsRowspan(rowIndex, (row, current) =>
      row.groupName === current.groupName &&
      row.batchKey === current.batchKey &&
      row.expectedInbound === current.expectedInbound
    )
    return { rowspan, colspan: rowspan ? 1 : 0 }
  }
  return { rowspan: 1, colspan: 1 }
}

function statsRowClassName({ row, rowIndex }: { row: KanbanStatRow; rowIndex: number }) {
  const prev = kanbanStatsRows.value[rowIndex - 1]
  const classes: string[] = []
  if (!prev || prev.groupName !== row.groupName) classes.push('stats-group-start')
  if (row.lineId) classes.push('stats-production-line-row')
  else classes.push('stats-queue-row')
  return classes.join(' ')
}

const assignableLines = computed(() => assignableLinesForBatch(assigningBatch.value))

const lockSelectedCount = computed(() => selectedCount(lockingLine.value))

function isSpecialBatch(batch: any) {
  return String(batch?.model_type || '').trim().toUpperCase() === 'SPECIAL'
}

function isSpecialLine(line: any) {
  const batches = Array.isArray(line?.batches) ? line.batches : []
  if (!batches.length) return false
  return batches.every((b: any) => isSpecialBatch(b))
}

function lineBatchCodes(line: any) {
  const batches = Array.isArray(line?.batches) ? line.batches : []
  return batches.map((b: any) => displayBatchCode(b)).filter((s: string) => Boolean(String(s).trim()))
}

function lineBatchLabels(line: any) {
  const codes = lineBatchCodes(line)
  if (!codes.length) return ''
  return `批次: ${codes.join(', ')}`
}

function lineExpectedInboundLabels(line: any) {
  const batches = Array.isArray(line?.batches) ? line.batches : []
  const units = Array.isArray(line?.units) ? line.units : []
  const dates = Array.from(new Set(
    [
      ...batches.map((b: any) => b?.expected_inbound_date),
      ...units.map((u: any) => u?.batch_expected_inbound_date || u?.fg_expected_inbound_date)
    ]
      .map((value: any) => fmtDate(value))
      .filter((date: string) => date && date !== '-')
  ))
  if (!dates.length) return ''
  return `预计入库: ${dates.join(', ')}`
}

function assignableLinesForBatch(batch: any) {
  if (!batch) return []
  const special = isSpecialBatch(batch)
  return lineStore.lines.filter((line: any) => {
    if (line.status === 'Idle') return true
    if (!special) return false
    return isSpecialLine(line)
  })
}

function assignableLineLabel(line: any) {
  const lineName = String(line.line_name || line.production_line_id || '')
  if (line.status === 'Idle') return `${lineName} (空闲)`
  const codes = lineBatchCodes(line)
  if (!codes.length) return `${lineName} (特殊在产)`
  return `${lineName} (特殊在产: ${codes.join(', ')})`
}

function scrollToLine(lineId: string | null | undefined) {
  if (!lineId) return
  const el = document.querySelector(`[data-line-id="${lineId}"]`) as HTMLElement | null
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' })
}

function navigateToLine(lineId: string | null | undefined) {
  scrollToLine(lineId)
  statsPanelOpen.value = false
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
  const batchModelType = String(batch?.model_type || '')
  const batchToken = batchModelType.trim().toUpperCase()
  if (!['G', 'XS', 'AUTO', 'SPECIAL'].includes(batchToken)) {
    const direct = categoryOfModel(batchModelType, '')
    if (direct) return direct
  }
  if (batchToken.includes('SPECIAL')) return '特殊'
  const family = majorFamilyOfModel(batchModelType)
  if (family === 'G') return '中小型G'
  if (family === 'XS') return Number(batch?.capacity || 0) === 16 ? '中大型XS' : '中小型XS'
  if (family === 'AUTO') return Number(batch?.capacity || 0) === 16 ? '中大型AUTO' : '中小型AUTO'
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
  const candidates = assignableLinesForBatch(batch)
  selectedLineId.value = candidates.length ? candidates[0].production_line_id : null
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

function selectedLineUnitIds(line: any) {
  if (!line) return []
  const lineId = String(line.production_line_id || '')
  const selected = new Set(selectedByLine.value[lineId] || [])
  return (Array.isArray(line.units) ? line.units : [])
    .map((u: any) => String(u?.unit_id || ''))
    .filter((id: string) => id && selected.has(id))
}

function selectedCount(line: any) {
  return selectedLineUnitIds(line).length
}

function isUnitSelected(lineId: string, unitId: string) {
  return (selectedByLine.value[lineId] || []).includes(unitId)
}

function toggleUnitSelection(lineId: string, unit: any) {
  const unitId = String(unit?.unit_id || '')
  if (!lineId || !unitId) return

  if (transferStore.selectingTargetFor) {
    handleTransferTargetSelected(unit)
    return
  }

  const current = selectedByLine.value[lineId] || []
  const next = current.includes(unitId)
    ? current.filter((id: string) => id !== unitId)
    : [...current, unitId]
  selectedByLine.value = { ...selectedByLine.value, [lineId]: next }
}

function clearLineSelection(lineId: string) {
  selectedByLine.value = { ...selectedByLine.value, [lineId]: [] }
}

function showLockDialog(line: any) {
  if (selectedCount(line) === 0) return
  lockingLine.value = line
  lockRemark.value = ''
  lockVisible.value = true
}

async function doLockUnits() {
  const line = lockingLine.value
  if (!line) return
  const lineId = String(line.production_line_id || '')
  const unitIds = selectedLineUnitIds(line)
  if (!lineId || unitIds.length === 0) return
  locking.value = true
  try {
    await sandboxApi.lockLineUnits(lineId, unitIds, lockRemark.value)
    ElMessage.success(`已锁定 ${unitIds.length} 张卡片`)
    clearLineSelection(lineId)
    lockVisible.value = false
    await forceRefreshAll()
  } catch (e: any) {
    ElMessage.error(e.message)
  } finally {
    locking.value = false
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

async function handleTransferTargetSelected(targetUnit: any) {
  const pairId = transferStore.selectingTargetFor
  if (!pairId) return

  if (targetUnit.is_locked) {
    ElMessage.error('目标机台已锁定，无法调货')
    return
  }

  try {
    await transferStore.executeSwapWithTarget(pairId, targetUnit)
    ElMessage.success('调货完成')
    await forceRefreshAll()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '调货失败')
    await forceRefreshAll()
  }
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
    const { model_type, contract_no, ...editableFields } = editForm.value
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

function handleTransferUrgent() {
  const unit = contextMenu.value.unit
  if (!unit) return
  if (!unit.contract_no) {
    ElMessage.warning('该单元无合同号，无法作为急合同调出')
    contextMenu.value.visible = false
    return
  }
  transferStore.addPair(unit, null)
  ElMessage.success('已加入调货队列，拖拽到目标机台完成调货')
  contextMenu.value.visible = false
}



const handleDownloadCommand = async (command: string) => {
  if (command === 'ledger') {
    try {
      ElMessage.info('正在生成排产报表，请稍候…')
      await apiDownloadBlob('/planning/export-production-history?sheet=ledger', `排产历史数据_${new Date().toISOString().slice(0, 10)}.xlsx`)
      ElMessage.success('排产数据报表下载成功')
    } catch (e: any) {
      ElMessage.error('下载排产报表失败: ' + (e.message || e))
    }
  } else if (command === 'tracking') {
    try {
      ElMessage.info('正在生成生产跟踪单，请稍候…')
      await apiDownloadBlob('/planning/export-production-history?sheet=tracking', `生产跟踪单_${new Date().toISOString().slice(0, 10)}.xlsx`)
      ElMessage.success('生产跟踪单下载成功')
    } catch (e: any) {
      ElMessage.error('下载生产跟踪单失败: ' + (e.message || e))
    }
  }
}


const exportSummaryToExcel = async () => {
  try {
    ElMessage.info('正在导出汇总 Excel，请稍候…')
    const headers = ['分组', '批次号', '机型', '预计入库时间', '已订数量', '备货数量', '合计']
    const rows = kanbanStatsRows.value.map(row => [
      row.groupName || '',
      row.batchLabel || '',
      row.modelType || '',
      row.expectedInbound || '',
      row.ordered ?? 0,
      row.stock ?? 0,
      row.total ?? 0
    ])

    const payload = {
      filename: `生产看板汇总_${new Date().toISOString().slice(0, 10)}`,
      sheet_name: '汇总',
      headers,
      rows
    }

    await apiDownloadBlobPost('/planning/export-excel', payload, `${payload.filename}.xlsx`)
    ElMessage.success('汇总 Excel 导出成功')
  } catch (e: any) {
    ElMessage.error('导出汇总 Excel 失败: ' + (e.message || e))
  }
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
.stats-floating-toggle {
  position: fixed;
  top: 42px;
  right: 640px;
  z-index: 2000;
  min-width: 92px;
  height: 38px;
  border-radius: 8px;
  box-shadow: 0 8px 20px rgba(22, 119, 255, 0.22);
}

.stats-floating-panel {
  position: fixed;
  top: 88px;
  right: 390px;
  z-index: 1990;
  width: min(1320px, calc(100vw - 620px));
  max-height: calc(100vh - 104px);
  overflow: hidden;
  box-shadow: 0 14px 36px rgba(15, 23, 42, 0.16);
}

.kanban-stats-panel {
  padding: 14px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
}

.kanban-stats-panel :deep(.el-table) {
  font-size: 14px;
}

.kanban-stats-panel :deep(.el-table__header th) {
  background: #f5f7fa;
  color: #303133;
  font-weight: 700;
}

.kanban-stats-panel :deep(.el-table__cell) {
  padding: 10px 0;
  border-color: #e5e7eb;
}

.kanban-stats-panel :deep(.stats-group-start > td) {
  border-top: 2px solid #d7dee8 !important;
}

.kanban-stats-panel :deep(.stats-group-start:first-child > td) {
  border-top-color: #e5e7eb !important;
}

.stat-group-cell {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 58px;
  margin: -4px 0;
  padding: 12px 14px;
  background: #f7fbff;
  border-left: 4px solid #1677ff;
  border-radius: 6px;
}

.stat-group-cell.queue-group {
  background: #fffaf0;
  border-left-color: #faad14;
}

.stat-group-name {
  font-size: 15px;
  font-weight: 800;
  color: #1f2937;
}

.stat-group-cell.queue-group .stat-group-name {
  color: #ad6800;
}

.stat-number {
  display: inline-flex;
  min-width: 52px;
  height: 28px;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  font-size: 18px;
  font-weight: 800;
  line-height: 1;
}

.stat-number.ordered {
  color: #0958d9;
  background: #e6f4ff;
}

.stat-number.stock {
  color: #ad6800;
  background: #fff7e6;
}

.stat-number.total {
  color: #237804;
  background: #f6ffed;
}

.ctx-item {
  padding: 6px 16px;
  cursor: pointer;
  font-size: 13px;
}
.ctx-item:hover { background: #f5f5f5; }
.ctx-item-primary {
  color: #e6a23c;
  font-weight: 600;
}
.ctx-item-primary:hover { background: #fef9f0; }

.queue-section {
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.queue-section.in-production-section {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid #ebeef5;
}
.queue-title {
  font-size: 14px;
  margin: 0 0 8px 0;
  flex-shrink: 0;
}
.queue-scroll {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
}
.queue-batch-item {
  margin-bottom: 8px;
}
.queue-batch-card {
  font-size: 12px;
  padding: 6px 10px;
  background: #fafafa;
  border-radius: 6px;
}
.queue-batch-card.in-production-card {
  background: #e6f7ff;
  border-left: 3px solid #1890ff;
}
.queue-batch-label {
  font-size: 12px;
}
.queue-empty {
  color: #ccc;
  text-align: center;
  padding: 12px;
  font-size: 13px;
}
.line-inbound-date {
  color: #d4380d;
  background-color: #fff2e8;
  border: 1px solid #ffbb96;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 15px;
  font-weight: bold;
  margin-left: 8px;
}

.selecting-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px;
  margin-bottom: 12px;
  background: #fff7e6;
  border: 2px solid #e6a23c;
  border-radius: 8px;
  color: #ad6800;
  font-size: 14px;
  font-weight: 600;
  animation: pulse-border 1.2s ease-in-out infinite;
}
@keyframes pulse-border {
  0%, 100% { border-color: #e6a23c; }
  50% { border-color: #ffc53d; }
}

@media (max-width: 1280px) {
  .stats-floating-toggle {
    right: 24px;
  }

  .stats-floating-panel {
    left: 24px;
    right: 24px;
    width: auto;
  }
}

/* ── 1920px 宽屏 / 32寸 FHD 适配 ─────────────────────────── */
@media (min-width: 1920px) {
  .stats-floating-toggle {
    right: 700px;
    min-width: 108px;
    height: 42px;
    font-size: 15px;
  }

  .stats-floating-panel {
    top: 94px;
    right: 420px;
    width: min(1680px, calc(100vw - 640px));
    max-height: calc(100vh - 110px);
  }

  .kanban-stats-panel {
    padding: 18px;
  }

  .kanban-stats-panel :deep(.el-table) {
    font-size: 16px;
  }

  .kanban-stats-panel :deep(.el-table__header th) {
    font-size: 15px;
  }

  .kanban-stats-panel :deep(.el-table__cell) {
    padding: 14px 4px;
  }

  .stat-group-cell {
    min-height: 68px;
    padding: 14px 18px;
    gap: 16px;
  }

  .stat-group-name {
    font-size: 17px;
  }

  .stat-number {
    min-width: 62px;
    height: 34px;
    font-size: 22px;
    border-radius: 8px;
  }
}

/* ── 2560px 宽屏 / 32寸 QHD 适配 ────────────────────────────── */
@media (min-width: 2560px) {
  .stats-floating-toggle {
    right: 860px;
    min-width: 124px;
    height: 48px;
    font-size: 17px;
    border-radius: 10px;
  }

  .stats-floating-panel {
    top: 100px;
    right: 520px;
    width: min(2200px, calc(100vw - 760px));
    max-height: calc(100vh - 120px);
  }

  .kanban-stats-panel {
    padding: 22px;
  }

  .kanban-stats-panel :deep(.el-table) {
    font-size: 18px;
  }

  .kanban-stats-panel :deep(.el-table__header th) {
    font-size: 17px;
  }

  .kanban-stats-panel :deep(.el-table__cell) {
    padding: 18px 6px;
  }

  .stat-group-cell {
    min-height: 80px;
    padding: 16px 22px;
    gap: 20px;
    border-left-width: 6px;
    border-radius: 8px;
  }

  .stat-group-name {
    font-size: 20px;
  }

  .stat-number {
    min-width: 76px;
    height: 42px;
    font-size: 26px;
    border-radius: 10px;
  }
}

</style>
