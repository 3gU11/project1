<template>
  <div class="page">
    <van-nav-bar title="生产看板" fixed placeholder>
      <template #right>
        <van-button icon="replay" size="small" round :loading="loading" @click="loadData" />
      </template>
    </van-nav-bar>

    <van-pull-refresh v-model="refreshing" @refresh="loadData">
      <section class="section">
        <div class="section__head">
          <h3>产线</h3>
          <span>{{ lines.length }} 条</span>
        </div>

        <div class="line-list">
          <van-swipe-cell v-for="line in lines" :key="lineId(line)" :disabled="line.status !== 'Busy'">
            <button
              class="line-card"
              :class="lineCardClass(line)"
              type="button"
              @click="openLine(line)"
            >
              <div class="line-card__top">
                <strong>{{ line.line_name || line.production_line_id }}</strong>
                <van-tag :type="lineTagType(line)">
                  {{ lineStatusText(line) }}
                </van-tag>
              </div>
              <div class="line-card__batch">{{ lineBatchSummary(line) }}</div>
              <div class="line-card__meta">
                <span>{{ lineModelSummary(line) }}</span>
                <span class="line-card__unfinished">{{ unfinishedUnitCount(line) ? `未完工 ${unfinishedUnitCount(line)}` : '全部可完工' }}</span>
              </div>
            </button>

            <template #right>
              <van-button
                square
                type="warning"
                :text="canManualCompleteLine(line) ? '手动完工' : '未完工'"
                class="swipe-action"
                :loading="completingLineId === lineId(line)"
                :disabled="!canManualCompleteLine(line)"
                @click="confirmManualComplete(line)"
              />
            </template>
          </van-swipe-cell>
        </div>
      </section>

      <section class="section">
        <div class="section__head">
          <h3>待排批次</h3>
          <span>{{ queueBatches.length }} 批</span>
        </div>
        <div v-if="queueBatches.length" class="batch-list">
          <div v-for="batch in queueBatches" :key="batch.batch_id" class="batch-card">
            <div class="batch-card__top">
              <strong>{{ displayBatchCode(batch) }}</strong>
              <van-tag plain :type="isSpecialBatch(batch) ? 'warning' : 'success'">
                {{ isSpecialBatch(batch) ? '特殊' : batch.model_type || '-' }}
              </van-tag>
            </div>
            <div class="batch-card__meta">
              <span>{{ batch.capacity || unitList(batch).length || 0 }} 台</span>
              <span>{{ fmtDate(batch.expected_inbound_date || batch.due_date_end) }}</span>
            </div>
            <div class="batch-card__models">{{ batchModelSummary(batch) }}</div>
            <van-button
              block
              round
              size="small"
              type="primary"
              :disabled="assignableLinesForBatch(batch).length === 0"
              @click="openAssign(batch)"
            >
              放入产线
            </van-button>
          </div>
        </div>
        <van-empty v-else description="暂无待排批次" />
      </section>
    </van-pull-refresh>

    <van-popup v-model:show="lineVisible" position="bottom" round style="height: 82%;">
      <div class="popup">
        <div class="popup__head">
          <div>
            <h3>{{ currentLine?.line_name || currentLine?.production_line_id || '-' }}</h3>
            <p>{{ currentLine?.status === 'Idle' ? '空闲' : lineBatchSummary(currentLine) }}</p>
          </div>
          <van-button icon="cross" size="small" round @click="lineVisible = false" />
        </div>

        <div v-if="lineBatchGroups.length" class="group-list">
          <div v-for="group in lineBatchGroups" :key="group.key" class="batch-group">
            <div class="batch-group__title">{{ group.label }}</div>
            <div
              v-for="unit in group.units"
              :key="unit.unit_id || `${group.key}-${unit.slot_index}`"
              class="unit-row"
              :class="unitRowClass(unit)"
            >
              <div class="unit-row__main">
                <strong>{{ unit.model_type || '-' }}</strong>
                <span class="unit-row__side">
                  <van-tag :type="isCompletedUnit(unit) ? 'success' : 'warning'" plain>
                    {{ isCompletedUnit(unit) ? '可完工' : '未完工' }}
                  </van-tag>
                </span>
              </div>
              <div class="unit-row__meta">
                <span>流水号 {{ unit.serial_no || unit.forecast_serial_no || '-' }}</span>
              </div>
              <div class="unit-row__meta">
                <span>备注 {{ unit.order_remark || '-' }}</span>
              </div>
            </div>
          </div>
        </div>
        <van-empty v-else description="该产线暂无在产卡片" />
      </div>
    </van-popup>

    <van-popup v-model:show="assignVisible" position="bottom" round style="height: 72%;">
      <div class="popup">
        <div class="popup__head">
          <div>
            <h3>选择产线</h3>
            <p>{{ assigningBatch ? displayBatchCode(assigningBatch) : '-' }}</p>
          </div>
          <van-button icon="cross" size="small" round @click="assignVisible = false" />
        </div>

        <div v-if="assignableLines.length" class="target-list">
          <button
            v-for="line in assignableLines"
            :key="lineId(line)"
            class="target-line"
            :class="{ 'target-line--active': selectedLineId === lineId(line) }"
            type="button"
            @click="selectedLineId = lineId(line)"
          >
            <strong>{{ line.line_name || line.production_line_id }}</strong>
            <span>{{ assignableLineLabel(line) }}</span>
          </button>
        </div>
        <van-empty v-else description="没有可用产线" />

        <div class="popup__actions">
          <van-button block round @click="assignVisible = false">取消</van-button>
          <van-button
            block
            round
            type="primary"
            :loading="assigning"
            :disabled="!selectedLineId"
            @click="confirmAssign"
          >
            确认分配
          </van-button>
        </div>
      </div>
    </van-popup>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { showConfirmDialog, showFailToast, showSuccessToast, showToast } from 'vant'
import { productionApi, type ProductionBatch, type ProductionLine } from '@/api/production'

const loading = ref(false)
const refreshing = ref(false)
const assigning = ref(false)
const completingLineId = ref('')
const lines = ref<ProductionLine[]>([])
const batches = ref<ProductionBatch[]>([])
const lineVisible = ref(false)
const assignVisible = ref(false)
const currentLine = ref<ProductionLine | null>(null)
const assigningBatch = ref<ProductionBatch | null>(null)
const selectedLineId = ref('')

const unitList = (item: any) => Array.isArray(item?.units) ? item.units : []
const lineId = (line: any) => String(line?.production_line_id || line?.line_id || '')

const queueBatches = computed(() =>
  batches.value.filter((batch) => String(batch?.status || '') === 'Confirmed')
)

const assignableLines = computed(() => assignableLinesForBatch(assigningBatch.value))

const lineBatchGroups = computed(() => {
  const line = currentLine.value
  if (!line) return []
  const batchMap = new Map<string, any>()
  ;(Array.isArray(line.batches) ? line.batches : []).forEach((batch: any) => {
    const key = String(batch?.batch_id || batch?.batch_code || batch?.batch_no || 'unknown')
    batchMap.set(key, batch)
  })
  const groups = new Map<string, any[]>()
  unitList(line).forEach((unit: any) => {
    const key = String(unit?.batch_id || (batchMap.size === 1 ? Array.from(batchMap.keys())[0] : 'unknown'))
    groups.set(key, [...(groups.get(key) || []), unit])
  })
  return Array.from(groups.entries()).map(([key, units]) => ({
    key,
    label: displayBatchCode(batchMap.get(key) || { batch_id: key }),
    units: units.sort((a, b) => Number(a?.slot_index || 0) - Number(b?.slot_index || 0)),
  }))
})

const loadData = async () => {
  loading.value = true
  try {
    const [nextLines, nextBatches] = await Promise.all([
      productionApi.getProductionLines(),
      productionApi.getBatches({ status: 'Confirmed' }),
    ])
    lines.value = nextLines
    batches.value = nextBatches
  } catch (error: any) {
    showFailToast(error?.response?.data?.detail || error?.message || '加载失败')
  } finally {
    loading.value = false
    refreshing.value = false
  }
}

const openLine = (line: ProductionLine) => {
  currentLine.value = line
  lineVisible.value = true
}

const openAssign = (batch: ProductionBatch) => {
  assigningBatch.value = batch
  const candidates = assignableLinesForBatch(batch)
  selectedLineId.value = candidates.length ? lineId(candidates[0]) : ''
  assignVisible.value = true
}

const confirmAssign = async () => {
  if (!assigningBatch.value || !selectedLineId.value) return
  assigning.value = true
  try {
    await productionApi.assignLine(selectedLineId.value, String(assigningBatch.value.batch_id))
    if (String(assigningBatch.value.batch_code || '').trim()) {
      await productionApi.importBatchToFinishedGoods(String(assigningBatch.value.batch_id))
    }
    showSuccessToast('分配成功')
    assignVisible.value = false
    await loadData()
  } catch (error: any) {
    showFailToast(error?.response?.data?.detail || error?.message || '分配失败')
  } finally {
    assigning.value = false
  }
}

const confirmManualComplete = async (line: ProductionLine) => {
  const id = lineId(line)
  if (!id) return
  if (!canManualCompleteLine(line)) {
    showToast('该产线还有未完工卡片')
    return
  }
  try {
    await showConfirmDialog({
      title: '确认完工',
      message: `确认 ${line.line_name || id} 已完工？完工后产线会释放为空闲。`,
      confirmButtonText: '确认完工',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }

  completingLineId.value = id
  try {
    await productionApi.manualComplete(id)
    showSuccessToast('已手动完工')
    if (lineId(currentLine.value) === id) lineVisible.value = false
    await loadData()
  } catch (error: any) {
    showFailToast(error?.response?.data?.detail || error?.message || '手动完工失败')
  } finally {
    completingLineId.value = ''
  }
}

function isSpecialBatch(batch: any) {
  return String(batch?.model_type || '').trim().toUpperCase() === 'SPECIAL'
}

function isSpecialLine(line: any) {
  const lineBatches = Array.isArray(line?.batches) ? line.batches : []
  return lineBatches.length > 0 && lineBatches.every((batch: any) => isSpecialBatch(batch))
}

function assignableLinesForBatch(batch: any) {
  if (!batch) return []
  const special = isSpecialBatch(batch)
  return lines.value.filter((line) => {
    if (String(line?.status || '') === 'Idle') return true
    if (!special) return false
    return isSpecialLine(line)
  })
}

function assignableLineLabel(line: any) {
  if (String(line?.status || '') === 'Idle') return '空闲'
  return `特殊在产 ${lineBatchCodes(line).join(', ') || ''}`.trim()
}

function isCompletedUnit(unit: any) {
  const contractNo = String(unit?.contract_no || '').trim()
  const status = String(unit?.fg_status || unit?.status || '').trim()
  if (!status) return false
  if (contractNo) {
    return status === '待发货' || status === '已出库' || status === 'Completed' || status.includes('完工')
  }
  return status !== '待入库' && status !== 'In_Production' && status !== 'Confirmed'
}

function canManualCompleteLine(line: any) {
  if (String(line?.status || '') !== 'Busy') return false
  const units = unitList(line).filter((unit: any) => String(unit?.model_type || unit?.contract_no || '').trim())
  return units.length > 0 && units.every((unit: any) => isCompletedUnit(unit))
}

function unfinishedUnitCount(line: any) {
  const units = unitList(line).filter((unit: any) => String(unit?.model_type || unit?.contract_no || '').trim())
  return units.filter((unit: any) => !isCompletedUnit(unit)).length
}

function lineCardClass(line: any) {
  if (canManualCompleteLine(line)) return 'line-card--can-complete'
  return String(line?.status || '') === 'Idle' ? 'line-card--idle' : 'line-card--busy'
}

function lineTagType(line: any) {
  if (canManualCompleteLine(line)) return 'success'
  return String(line?.status || '') === 'Idle' ? 'success' : 'primary'
}

function lineStatusText(line: any) {
  if (canManualCompleteLine(line)) return '可完工'
  return String(line?.status || '') === 'Idle' ? '空闲' : '在产'
}

function unitRowClass(unit: any) {
  return isCompletedUnit(unit) ? 'unit-row--complete-ready' : 'unit-row--in-progress'
}

function lineBatchCodes(line: any) {
  return (Array.isArray(line?.batches) ? line.batches : [])
    .map((batch: any) => displayBatchCode(batch))
    .filter(Boolean)
}

function lineBatchSummary(line: any) {
  if (!line || String(line?.status || '') === 'Idle') return '暂无批次'
  const codes = lineBatchCodes(line)
  return codes.length ? codes.join(', ') : (line.current_batch_id || '在产批次')
}

function lineModelSummary(line: any) {
  const models = new Map<string, number>()
  unitList(line).forEach((unit: any) => {
    const model = String(unit?.model_type || '').trim()
    if (model) models.set(model, Number(models.get(model) || 0) + 1)
  })
  const text = Array.from(models.entries()).map(([model, count]) => `${model}x${count}`).join(' / ')
  return text || String(line?.model_type || '无机型')
}

function batchModelSummary(batch: any) {
  const models = new Map<string, number>()
  unitList(batch).forEach((unit: any) => {
    const model = String(unit?.model_type || '').trim()
    if (model) models.set(model, Number(models.get(model) || 0) + 1)
  })
  const text = Array.from(models.entries()).slice(0, 3).map(([model, count]) => `${model}x${count}`).join(' / ')
  return text || String(batch?.model_type || '-')
}

function displayBatchCode(batch: any) {
  const explicit = String(batch?.batch_code || '').trim()
  if (explicit) return explicit
  const n = Number(batch?.batch_no)
  if (Number.isFinite(n) && n >= 101) {
    const whole = Math.trunc(n)
    const month = Math.floor(whole / 100)
    const seq = whole % 100
    if (month >= 1 && month <= 12 && seq >= 1) {
      return `${String(month).padStart(2, '0')}-${String(seq).padStart(2, '0')}`
    }
  }
  return String(batch?.batch_no || batch?.batch_id || '-')
}

function fmtDate(value: any) {
  if (!value) return '-'
  return String(value).slice(0, 10)
}

onMounted(loadData)
</script>

<style scoped>
.page {
  min-height: 100vh;
  background: var(--van-background-2);
  padding-bottom: 66px;
}

.section {
  padding: 12px;
}

.section__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
  color: var(--van-text-color-2);
}

.section__head h3 {
  margin: 0;
  font-size: 16px;
  color: var(--van-text-color);
}

.line-list,
.batch-list,
.target-list,
.group-list {
  display: grid;
  gap: 10px;
}

.line-list :deep(.van-swipe-cell) {
  border-radius: 8px;
}

.line-card,
.batch-card,
.target-line,
.unit-row {
  width: 100%;
  border: 1px solid var(--van-border-color);
  border-radius: 8px;
  background: #fff;
  padding: 12px;
  text-align: left;
}

.line-card {
  display: block;
}

.line-card--idle {
  border-color: #16a34a;
  box-shadow: inset 5px 0 0 #16a34a;
}

.line-card--busy,
.target-line--active {
  border-color: var(--van-primary-color);
  box-shadow: inset 5px 0 0 var(--van-primary-color);
}

.line-card--can-complete {
  border-color: #22c55e;
  background: #dcfce7;
  box-shadow: inset 5px 0 0 #22c55e;
}

.swipe-action {
  height: 100%;
}

.unit-row--complete-ready {
  border-color: #22c55e;
  background: #dcfce7;
  box-shadow: inset 5px 0 0 #22c55e;
}

.unit-row--in-progress {
  border-color: #fb923c;
  background: #ffedd5;
  box-shadow: inset 5px 0 0 #fb923c;
}

.line-card__top,
.batch-card__top,
.unit-row__main {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.line-card__top strong,
.batch-card__top strong,
.unit-row__main strong {
  min-width: 0;
  font-size: 15px;
  color: var(--van-text-color);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.unit-row__side {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.line-card__batch,
.batch-card__models {
  margin-top: 8px;
  font-size: 13px;
  color: var(--van-text-color);
}

.line-card__meta,
.batch-card__meta,
.unit-row__meta {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  margin-top: 6px;
  font-size: 12px;
  color: var(--van-text-color-2);
  line-height: 1.45;
  white-space: normal;
  word-break: break-word;
}

.line-card__meta > span:first-child {
  min-width: 0;
}

.line-card__unfinished {
  flex-shrink: 0;
  color: #d4380d;
  font-weight: 600;
}

.line-card--can-complete .line-card__unfinished {
  color: #237804;
}

.batch-card .van-button {
  margin-top: 10px;
}

.popup {
  height: 100%;
  padding: 16px;
  overflow-y: auto;
  box-sizing: border-box;
}

.popup__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.popup__head h3 {
  margin: 0;
  font-size: 18px;
}

.popup__head p {
  margin: 4px 0 0;
  color: var(--van-text-color-2);
  font-size: 13px;
}

.batch-group__title {
  margin: 6px 0 8px;
  font-size: 14px;
  font-weight: 600;
}

.target-line {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.target-line span {
  font-size: 12px;
  color: var(--van-text-color-2);
}

.popup__actions {
  position: sticky;
  bottom: 0;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  padding-top: 16px;
  background: #fff;
}
</style>
