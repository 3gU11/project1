<template>
  <div class="inventory-container">
    <el-card shadow="hover">
      <template #header>
        <div class="card-header">
          <span class="title">📊 实时库存比例分布</span>
          <div class="actions">
            <el-select
              v-model="selectedModels"
              multiple
              collapse-tags
              collapse-tags-tooltip
              placeholder="Choose options"
              style="width: 360px; margin-right: 10px"
            >
              <el-option v-for="m in modelOptions" :key="m" :label="m" :value="m" />
            </el-select>
            <el-checkbox v-model="highOnly" style="margin-right: 10px">仅查看加高型号</el-checkbox>
            <el-button type="primary" :icon="Refresh" @click="fetchData(true)" :loading="loading">刷新数据</el-button>
          </div>
        </div>
      </template>

      <div class="ratio-grid">
        <div v-for="item in ratioBoard" :key="item.model" class="ratio-item">
          <div class="ratio-label">{{ item.model }}</div>
          <div class="ratio-value">{{ item.percent }}%</div>
          <div class="ratio-sub">↑ {{ item.count }} / {{ totalCount }}</div>
        </div>
      </div>

      <el-divider />

      <el-row :gutter="16">
        <el-col :span="15">
          <div class="summary-top">
            <div class="summary-title">📦 当前总库存 (Total)</div>
            <div class="summary-value">{{ totalCount }} 台</div>
          </div>
          <div class="summary-row">
            <div class="summary-block">
              <div class="summary-title">✅ 在库 (In Stock)</div>
              <div class="summary-value">{{ inStockCount }}</div>
            </div>
            <div class="summary-block">
              <div class="summary-title">⏳ 待入库 (Pending)</div>
              <div class="summary-value">{{ pendingCount }}</div>
            </div>
          </div>
          <div class="summary-title chart-title">机型分布</div>
          <div class="donut-wrap" v-if="top10Dist.length > 0">
            <div class="donut-chart" :class="{ 'with-decor': donutDecorReady }">
              <svg class="donut-svg" :class="{ 'with-decor': donutDecorReady }" viewBox="0 0 220 220" aria-label="机型分布环形图">
                <path
                  v-for="seg in donutSegments"
                  :key="`seg-${seg.idx}`"
                  :d="describeDonutSlice(seg.startDeg, seg.endDeg, hoveredSegIdx === seg.idx ? 1.06 : 1)"
                  :fill="palette[seg.idx % palette.length]"
                  :class="['donut-seg', { 'with-decor': donutDecorReady }]"
                  @mouseenter="hoveredSegIdx = seg.idx"
                  @mouseleave="hoveredSegIdx = null"
                />
              </svg>
              <div v-if="hoveredSegment" class="donut-tooltip">
                {{ hoveredSegment.model }} {{ hoveredSegment.percent.toFixed(1) }}%
              </div>
              <div class="donut-hole" :class="{ 'with-decor': donutDecorReady }">
                <div class="donut-center-label">Top10</div>
              </div>
            </div>
            <div class="donut-legend">
              <div
                v-for="(item, idx) in top10Dist"
                :key="item.model"
                class="legend-row"
                :class="{ hover: hoveredModel === item.model }"
              >
                <span class="legend-dot" :style="{ background: palette[idx % palette.length] }"></span>
                <span class="legend-link"></span>
                <span class="legend-model">{{ item.model }}</span>
                <span class="legend-arrow">↗</span>
                <span class="legend-val">{{ item.percent.toFixed(1) }}%</span>
              </div>
            </div>
          </div>
          <div v-else class="chart-empty">暂无机型分布数据</div>
        </el-col>
        <el-col :span="9">
          <el-table :data="modelSummary" border stripe size="small" class="model-summary-table" height="620">
            <el-table-column prop="机型" label="机型" />
            <el-table-column prop="库存中" label="库存中" width="100" />
            <el-table-column prop="待入库" label="待入库" width="100" />
            <el-table-column prop="全部" label="全部" width="100" />
          </el-table>
        </el-col>
      </el-row>

      <el-collapse v-model="activePanels" class="detail-collapse">
        <el-collapse-item name="detail">
          <template #title>📄 详细清单 (Detailed List)</template>
          <div class="detail-toolbar">
            <el-input
              v-model="searchQuery"
              placeholder="搜索流水号/机型/批次号..."
              clearable
              style="width: 340px"
              @keyup.enter="handleSearch"
            />
          </div>
          <el-table
            v-loading="loading"
            :data="pagedData"
            border
            stripe
            max-height="430"
          >
            <el-table-column type="index" label="#" width="60" />
            <el-table-column prop="批次号" label="批次号" width="120" />
            <el-table-column prop="机型" label="机型" width="130" />
            <el-table-column prop="流水号" label="流水号" width="150" />
            <el-table-column prop="状态" label="状态" width="100" />
            <el-table-column prop="机台备注/配置" label="机台备注/配置" min-width="180" show-overflow-tooltip />
          </el-table>
          <div class="pagination-container">
            <el-pagination
              v-model:current-page="currentPage"
              v-model:page-size="pageSize"
              :page-sizes="[20, 50, 100, 500]"
              background
              layout="total, sizes, prev, pager, next, jumper"
              :total="total"
            />
          </div>
        </el-collapse-item>
      </el-collapse>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onActivated, watch } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { useInventoryStore } from '../store/inventory'
import { buildInventoryIndex, filterInventoryRows } from '../utils/inventoryFilter'

const loading = ref(false)
const inventoryList = ref<any[]>([])
const inventoryStore = useInventoryStore()
const searchQuery = ref('')
const statusFilter = ref('')
const selectedModels = ref<string[]>([])
const highOnly = ref(false)
const activePanels = ref<string[]>([])
const donutProgress = ref(0)
const donutDecorReady = computed(() => donutProgress.value >= 0.999)
const hoveredSegIdx = ref<number | null>(null)

const currentPage = ref(1)
const pageSize = ref(50)

const fetchData = async (force = false) => {
  loading.value = true
  try {
    const data = await inventoryStore.fetchInventory(force)
    inventoryList.value = data
  } catch (error) {
    console.error('Fetch inventory failed', error)
  } finally {
    loading.value = false
  }
}

const handleSearch = () => {
  currentPage.value = 1
}

const modelOptions = computed(() => {
  const set = new Set<string>()
  for (const row of inventoryList.value) {
    const model = String(row['机型'] || '').trim()
    if (model) set.add(model)
  }
  return Array.from(set)
})

const indexedRows = computed(() => buildInventoryIndex(inventoryList.value))

const filteredForStats = computed(() => {
  return filterInventoryRows(indexedRows.value, {
    selectedModels: selectedModels.value,
    statusFilter: statusFilter.value,
    searchQuery: searchQuery.value,
    highOnly: highOnly.value,
  })
})

const pagedData = computed(() => {
  return filteredForStats.value.slice((currentPage.value - 1) * pageSize.value, currentPage.value * pageSize.value)
})

const total = computed(() => {
  return filteredForStats.value.length
})

const totalCount = computed(() => filteredForStats.value.length)

const inStockCount = computed(() => filteredForStats.value.filter((r) => String(r['状态'] || '').startsWith('库存中')).length)
const pendingCount = computed(() => filteredForStats.value.filter((r) => String(r['状态'] || '') === '待入库').length)

const modelSummary = computed(() => {
  const map = new Map<string, { 机型: string; 库存中: number; 待入库: number; 全部: number }>()
  for (const row of filteredForStats.value) {
    const model = String(row['机型'] || '未知')
    if (!map.has(model)) map.set(model, { 机型: model, 库存中: 0, 待入库: 0, 全部: 0 })
    const hit = map.get(model)!
    const s = String(row['状态'] || '')
    if (s.startsWith('库存中')) hit.库存中 += 1
    if (s === '待入库') hit.待入库 += 1
    hit.全部 += 1
  }
  return Array.from(map.values()).sort((a, b) => b.全部 - a.全部)
})

const ratioBoard = computed(() => {
  return modelSummary.value.slice(0, 8).map((row) => ({
    model: row.机型,
    count: row.全部,
    percent: totalCount.value > 0 ? ((row.全部 / totalCount.value) * 100).toFixed(1) : '0.0',
  }))
})

const palette = ['#3b82f6', '#ef4444', '#10b981', '#f59e0b', '#6366f1', '#06b6d4', '#f97316', '#a855f7', '#14b8a6', '#fb7185']

const top10Dist = computed(() => {
  return modelSummary.value.slice(0, 10).map((row) => ({
    model: row.机型,
    count: row.全部,
    percent: totalCount.value > 0 ? (row.全部 / totalCount.value) * 100 : 0,
  }))
})

const top10DistNormalized = computed(() => {
  const sum = top10Dist.value.reduce((acc, item) => acc + item.count, 0)
  if (sum <= 0) return []
  return top10Dist.value.map((item) => ({
    ...item,
    normPercent: (item.count / sum) * 100,
  }))
})

const donutSegments = computed(() => {
  const result: Array<{ idx: number; model: string; percent: number; startDeg: number; endDeg: number }> = []
  if (top10DistNormalized.value.length === 0) return result
  const sweepDeg = Math.max(0, Math.min(360, donutProgress.value * 360))
  let cursor = 0
  top10DistNormalized.value.forEach((item, idx) => {
    const segDeg = item.normPercent * 3.6
    const drawDeg = Math.min(segDeg, Math.max(0, sweepDeg - cursor))
    if (drawDeg > 0) {
      result.push({
        idx,
        model: item.model,
        percent: item.percent,
        startDeg: cursor,
        endDeg: cursor + drawDeg,
      })
    }
    cursor += segDeg
  })
  return result
})

const hoveredSegment = computed(() => {
  if (hoveredSegIdx.value === null) return null
  return donutSegments.value.find((s) => s.idx === hoveredSegIdx.value) || null
})

const hoveredModel = computed(() => hoveredSegment.value?.model || '')

const polar = (cx: number, cy: number, r: number, deg: number) => {
  const rad = ((deg - 90) * Math.PI) / 180
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) }
}

const describeDonutSlice = (startDeg: number, endDeg: number, scale = 1) => {
  if (endDeg <= startDeg) return ''
  const cx = 110
  const cy = 110
  const outerR = 108 * scale
  const innerR = 58 * scale
  const p1 = polar(cx, cy, outerR, startDeg)
  const p2 = polar(cx, cy, outerR, endDeg)
  const p3 = polar(cx, cy, innerR, endDeg)
  const p4 = polar(cx, cy, innerR, startDeg)
  const largeArc = endDeg - startDeg > 180 ? 1 : 0
  return [
    `M ${p1.x} ${p1.y}`,
    `A ${outerR} ${outerR} 0 ${largeArc} 1 ${p2.x} ${p2.y}`,
    `L ${p3.x} ${p3.y}`,
    `A ${innerR} ${innerR} 0 ${largeArc} 0 ${p4.x} ${p4.y}`,
    'Z',
  ].join(' ')
}

const runDonutBuildAnimation = () => {
  const duration = 1000
  const start = performance.now()
  donutProgress.value = 0
  const tick = (now: number) => {
    const p = Math.min(1, (now - start) / duration)
    // ease-in: 从无到有，前慢后快（逐渐加速）
    donutProgress.value = p * p * p
    if (p < 1) requestAnimationFrame(tick)
  }
  requestAnimationFrame(tick)
}

watch(top10DistNormalized, () => {
  runDonutBuildAnimation()
})

onMounted(async () => {
  await fetchData()
  runDonutBuildAnimation()
})

onActivated(() => {
  runDonutBuildAnimation()
})
</script>

<style scoped>
.inventory-container {
  height: 100%;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.title {
  font-size: 26px;
  font-weight: bold;
  color: var(--text-color-primary);
}
.actions {
  display: flex;
  align-items: center;
}
.ratio-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(140px, 1fr));
  gap: var(--space-3);
  margin-bottom: var(--space-2);
}
.ratio-item {
  border: 1px solid var(--border-color-light);
  border-radius: var(--radius-lg);
  padding: var(--space-2) var(--space-3);
}
.ratio-label {
  color: var(--color-gray-500);
  font-size: var(--font-size-sm);
}
.ratio-value {
  font-size: 34px;
  font-weight: 700;
  color: var(--color-gray-800);
  line-height: 1.15;
}
.ratio-sub {
  color: #16a34a;
  font-size: var(--font-size-sm);
}
.summary-top {
  margin-bottom: var(--space-2);
}
.summary-row {
  display: grid;
  grid-template-columns: repeat(2, minmax(160px, 1fr));
  gap: var(--space-2);
  margin-bottom: var(--space-2);
  max-width: 620px;
}
.summary-block {
  margin-bottom: var(--space-2);
}
.summary-title {
  color: var(--color-gray-700);
  font-size: 18px;
  margin-bottom: 3px;
  font-weight: 700;
}
.summary-value {
  font-size: 54px;
  line-height: 1;
  color: var(--color-gray-900);
}
.summary-row .summary-title {
  font-size: var(--font-size-lg);
}
.summary-row .summary-value {
  font-size: 48px;
}
.chart-title {
  margin-top: 2px;
  margin-bottom: 6px;
}
.donut-wrap {
  display: flex;
  gap: 18px;
  align-items: center;
  max-width: 760px;
}
.donut-chart {
  width: 220px;
  height: 220px;
  border-radius: 50%;
  position: relative;
  flex-shrink: 0;
  overflow: visible;
}
.donut-svg {
  width: 220px;
  height: 220px;
  display: block;
}
.donut-seg {
  transition: opacity 0.12s ease;
}
.donut-chart.with-decor {
  box-shadow: none;
}
.donut-svg.with-decor {
  filter:
    drop-shadow(0 10px 24px rgba(59, 130, 246, 0.16))
    drop-shadow(0 2px 6px rgba(15, 23, 42, 0.08));
}
.donut-seg.with-decor {
  stroke: var(--color-primary-100);
  stroke-width: 1.4;
  stroke-linejoin: round;
  vector-effect: non-scaling-stroke;
  paint-order: stroke fill;
}
.donut-tooltip {
  position: absolute;
  left: 50%;
  top: -8px;
  transform: translate(-50%, -100%);
  background: rgba(15, 23, 42, 0.88);
  color: var(--panel-bg);
  font-size: var(--font-size-sm);
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-md);
  white-space: nowrap;
  pointer-events: none;
}
.donut-hole {
  position: absolute;
  inset: 26%;
  background: var(--panel-bg);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
}
.donut-hole.with-decor {
  border: 1.4px solid var(--color-primary-100);
  box-shadow:
    inset 0 2px 8px rgba(15, 23, 42, 0.06),
    0 2px 6px rgba(15, 23, 42, 0.06),
    0 0 0 1px rgba(219, 234, 254, 0.65);
}
.donut-center-label {
  font-size: var(--font-size-base);
  color: var(--color-gray-700);
  font-weight: 700;
  letter-spacing: 0.2px;
}
.donut-legend {
  display: grid;
  gap: 6px;
  min-width: 360px;
}
.legend-row {
  display: grid;
  grid-template-columns: 12px 34px 1fr 18px auto;
  align-items: center;
  gap: 8px;
  padding: 2px 6px;
  border-radius: var(--radius-md);
  position: relative;
}
.legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}
.legend-link {
  height: 0;
  border-top: 1.5px solid var(--color-gray-300);
}
.legend-arrow {
  color: var(--color-gray-400);
  font-size: var(--font-size-sm);
}
.legend-model {
  font-size: var(--font-size-sm);
  color: var(--color-gray-700);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.legend-val {
  font-size: var(--font-size-sm);
  color: var(--color-gray-700);
}
.legend-row.hover {
  background: #e0f2fe;
  box-shadow:
    inset 0 0 0 1px #38bdf8,
    0 2px 8px rgba(14, 165, 233, 0.22);
}
.legend-row.hover::before {
  content: '';
  position: absolute;
  left: -2px;
  top: 4px;
  bottom: 4px;
  width: 4px;
  border-radius: var(--radius-sm);
  background: linear-gradient(180deg, #0ea5e9, var(--color-primary-600));
}
.legend-row.hover .legend-model,
.legend-row.hover .legend-val {
  color: #0f172a;
  font-weight: 700;
}
.legend-row.hover .legend-arrow {
  color: #0369a1;
}
.chart-empty {
  color: var(--color-gray-500);
  font-size: var(--font-size-sm);
}
.detail-collapse {
  margin-top: 2px;
}
.detail-toolbar {
  margin-bottom: 6px;
  display: flex;
  justify-content: flex-start;
}
.model-summary-table {
  max-width: 520px;
}
.pagination-container {
  margin-top: 6px;
  display: flex;
  justify-content: flex-end;
}
</style>
