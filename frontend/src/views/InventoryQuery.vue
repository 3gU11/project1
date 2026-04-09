<template>
  <div class="inventory-container">
    <el-card shadow="hover">
      <template #header>
        <div class="card-header">
          <span class="title">📊 库存比例(看板)</span>
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
            <el-checkbox v-model="highOnly" style="margin-right: 10px">仅显示加高 (High Only)</el-checkbox>
            <el-button type="primary" :icon="Refresh" @click="fetchData(true)" :loading="loading">刷新</el-button>
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
          <div class="bar-chart-wrap">
            <div v-for="(item, idx) in distBarData" :key="item.model" class="bar-row">
              <div class="bar-label">{{ item.model }}</div>
              <div class="bar-track">
                <div
                  class="bar-fill"
                  :style="{
                    width: `${item.percent}%`,
                    background: palette[idx % palette.length]
                  }"
                ></div>
              </div>
              <div class="bar-value">{{ item.percent.toFixed(1) }}%</div>
            </div>
          </div>
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
import { ref, computed, onMounted } from 'vue'
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
const activePanels = ref<string[]>(['detail'])

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

const distBarData = computed(() => {
  return modelSummary.value.map((row) => ({
    model: row.机型,
    count: row.全部,
    percent: totalCount.value > 0 ? (row.全部 / totalCount.value) * 100 : 0,
  }))
})

onMounted(() => {
  fetchData()
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
  color: #303133;
}
.actions {
  display: flex;
  align-items: center;
}
.ratio-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(140px, 1fr));
  gap: 14px;
  margin-bottom: 8px;
}
.ratio-item {
  border: 1px solid #eef2f7;
  border-radius: 8px;
  padding: 10px 12px;
}
.ratio-label {
  color: #6b7280;
  font-size: 12px;
}
.ratio-value {
  font-size: 34px;
  font-weight: 700;
  color: #1f2937;
  line-height: 1.15;
}
.ratio-sub {
  color: #16a34a;
  font-size: 12px;
}
.summary-top {
  margin-bottom: 8px;
}
.summary-row {
  display: grid;
  grid-template-columns: repeat(2, minmax(160px, 1fr));
  gap: 10px;
  margin-bottom: 8px;
  max-width: 620px;
}
.summary-block {
  margin-bottom: 10px;
}
.summary-title {
  color: #374151;
  font-size: 18px;
  margin-bottom: 3px;
  font-weight: 700;
}
.summary-value {
  font-size: 54px;
  line-height: 1;
  color: #111827;
}
.summary-row .summary-title {
  font-size: 16px;
}
.summary-row .summary-value {
  font-size: 48px;
}
.chart-title {
  margin-top: 2px;
  margin-bottom: 6px;
}
.bar-chart-wrap {
  max-width: 760px;
  max-height: 360px;
  overflow: auto;
  padding-right: 4px;
}
.bar-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}
.bar-label {
  width: 150px;
  font-size: 13px;
  color: #374151;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.bar-track {
  flex: 1;
  height: 16px;
  background: #eef2f7;
  border-radius: 10px;
  overflow: hidden;
}
.bar-fill {
  height: 100%;
  border-radius: 10px;
}
.bar-value {
  width: 56px;
  text-align: right;
  font-size: 13px;
  color: #374151;
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
