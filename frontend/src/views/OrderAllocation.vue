<template>
  <div class="alloc-page">
    <PageHeader title="📦 订单配货">
      <template #actions>
        <el-button type="primary" :loading="loading" @click="loadData(true)">刷新数据</el-button>
      </template>
    </PageHeader>

    <el-row :gutter="12">
      <el-col :span="9">
        <el-card>
          <template #header>
            <div class="card-head">订单列表（进行中）</div>
          </template>
          <el-input v-model="orderKeyword" clearable placeholder="搜索订单号/客户" />
          <div class="order-list">
            <VirtualScrollList :items="filteredOrders" :height="710" :item-height="64" item-key="订单号" :overscan="10">
              <template #default="{ item: o }">
                <button
                  :key="String(o['订单号'] || '')"
                  type="button"
                  class="order-item"
                  :class="{ active: selectedOrderId === String(o['订单号'] || '') }"
                  @click="selectOrder(o)"
                >
                  <div class="order-customer">{{ o['客户名'] }}</div>
                  <div class="sub">{{ o['订单号'] }} | {{ o['需求机型'] }}</div>
                </button>
              </template>
            </VirtualScrollList>
            <el-empty v-if="filteredOrders.length === 0" description="暂无可配货订单" />
          </div>
        </el-card>
      </el-col>

      <el-col :span="15">
        <el-card>
          <template #header>
            <div class="card-head">配货面板</div>
          </template>
          <el-empty v-if="!selectedOrderId" description="请先选择左侧订单" />
          <template v-else>
            <div class="summary">
              <div>订单号：{{ selectedOrderId }}</div>
              <div>客户：{{ selectedOrder?.['客户名'] || '-' }}</div>
              <div>需求总量：{{ totalDemandQty }}</div>
              <div>已配货：{{ allocations.length }}</div>
            </div>

            <el-divider />
            <div class="field-label">需求分解（按机型）</div>
            <el-table :data="demandRows" border stripe size="small">
              <el-table-column prop="model" label="机型" min-width="180" />
              <el-table-column prop="need" label="需求" width="90" />
              <el-table-column prop="allocated" label="已配" width="90" />
              <el-table-column prop="pending" label="待配" width="90" />
              <el-table-column label="状态" width="120">
                <template #default="scope">
                  <el-tag :type="scope.row.pending <= 0 ? 'success' : 'warning'">
                    {{ scope.row.pending <= 0 ? '已满足' : '待补齐' }}
                  </el-tag>
                </template>
              </el-table-column>
            </el-table>

            <el-divider />
            <div class="field-label">候选库存（可分配）</div>
            <el-table
              :data="candidateRows"
              border
              stripe
              size="small"
              height="230"
              @selection-change="onCandidateSelectionChange"
            >
              <el-table-column type="selection" width="48" />
              <el-table-column prop="流水号" label="流水号" width="150" />
              <el-table-column prop="机型" label="机型" min-width="160" />
              <el-table-column prop="状态" label="状态" width="90" />
              <el-table-column prop="批次号" label="批次号" width="120" />
              <el-table-column prop="机台备注/配置" label="机台备注/配置" min-width="160" />
            </el-table>
            <div class="ops">
              <el-button type="primary" :loading="saving" @click="allocateSelected">确认分配</el-button>
            </div>

            <el-divider />
            <div class="field-label">配货撤回</div>
            <el-table
              :data="allocations"
              border
              stripe
              size="small"
              height="230"
              @selection-change="onAllocatedSelectionChange"
            >
              <el-table-column type="selection" width="48" />
              <el-table-column prop="流水号" label="流水号" width="150" />
              <el-table-column prop="机型" label="机型" min-width="160" />
              <el-table-column prop="状态" label="状态" width="90" />
              <el-table-column prop="批次号" label="批次号" width="120" />
              <el-table-column prop="机台备注/配置" label="机台备注/配置" min-width="160" />
            </el-table>
            <div class="ops">
              <el-button :loading="saving" @click="releaseSelected">确认撤回</el-button>
            </div>
          </template>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useRoute } from 'vue-router'
import { apiGet, apiGetAll, apiPost, getApiErrorMessage } from '../utils/request'
import { useCacheStore } from '../store/cache'
import { compareModels, normalizeModelName, sortRowsByModel } from '../utils/modelOrder'
import PageHeader from '../components/PageHeader.vue'
import VirtualScrollList from '../components/VirtualScrollList.vue'
type ListResponse<T = any> = { data: T[] }
type ReleaseResponse = { message?: string; released?: number }

type Row = Record<string, any>

const loading = ref(false)
const saving = ref(false)
const orderKeyword = ref('')
const orders = ref<Row[]>([])
const inventoryRows = ref<Row[]>([])
const allocations = ref<Row[]>([])
const cacheStore = useCacheStore()
const route = useRoute()
const selectedOrderId = ref('')
const selectedOrder = ref<Row | null>(null)
const selectedCandidateSerials = ref<string[]>([])
const selectedAllocatedSerials = ref<string[]>([])

const parseDemandEntries = (order: Row | null) => {
  const entries: Array<{ model: string; qty: number }> = []
  if (!order) return entries
  const raw = String(order['需求机型'] || '')
  const parts = raw.split(/[;；/,，]/g).map((s) => s.trim()).filter(Boolean)
  for (const partRaw of parts) {
    const part = partRaw.replace(/\[[^\]]*]/g, '').trim()
    const m = part.match(/(?:[x×:：]\s*)(\d+)\s*$/i)
    const qty = m ? Number(m[1]) || 0 : 0
    const model = normalizeModelName(part.replace(/(?:[x×:：]\s*)\d+\s*$/i, '').trim())
    if (!model) continue
    entries.push({ model, qty: Math.max(0, qty) })
  }
  if (entries.length === 0) {
    const fallbackModel = normalizeModelName(raw)
    const fallbackQty = Number(order['需求数量'] || 0)
    if (fallbackModel) entries.push({ model: fallbackModel, qty: Number.isFinite(fallbackQty) ? Math.max(0, fallbackQty) : 0 })
  }
  return entries
}

const parseOrderDemandTotal = (order: Row) => {
  let total = 0
  for (const e of parseDemandEntries(order)) total += e.qty
  if (total > 0) return total
  const fallback = Number(order['需求数量'] || 0)
  return Number.isFinite(fallback) ? Math.max(0, fallback) : 0
}

const shippedByOrderId = computed(() => {
  const map = new Map<string, number>()
  for (const row of inventoryRows.value) {
    const orderId = String(row['占用订单号'] || '').trim()
    const status = String(row['状态'] || '').trim()
    if (!orderId) continue
    if (status !== '已出库') continue
    map.set(orderId, (map.get(orderId) || 0) + 1)
  }
  return map
})

const filteredOrders = computed(() => {
  const term = orderKeyword.value.trim().toLowerCase()
  return orders.value
    .filter((o) => ['active', 'ready', 'packed'].includes(String(o.status || 'active')))
    .filter((o) => {
      const orderId = String(o['订单号'] || '')
      const need = parseOrderDemandTotal(o)
      const shipped = shippedByOrderId.value.get(orderId) || 0
      return !(need > 0 && shipped >= need)
    })
    .filter((o) => {
      if (!term) return true
      const hit = `${o['订单号'] || ''} ${o['客户名'] || ''}`.toLowerCase()
      return hit.includes(term)
    })
})

const parseDemandMap = (order: Row | null) => {
  const map = new Map<string, number>()
  for (const e of parseDemandEntries(order)) {
    map.set(e.model, (map.get(e.model) || 0) + (Number.isFinite(e.qty) && e.qty > 0 ? e.qty : 0))
  }
  return map
}

const demandMap = computed(() => parseDemandMap(selectedOrder.value))
const totalDemandQty = computed(() => {
  let total = 0
  for (const qty of demandMap.value.values()) total += qty
  return total
})

const requiredModels = computed(() => {
  if (!selectedOrder.value) return [] as string[]
  return Array.from(demandMap.value.keys())
})

const allocationModelCountMap = computed(() => {
  const map = new Map<string, number>()
  for (const r of allocations.value) {
    const model = normalizeModelName(r['机型'])
    if (!model) continue
    map.set(model, (map.get(model) || 0) + 1)
  }
  return map
})

const demandRows = computed(() => {
  const rows: Array<{ model: string; need: number; allocated: number; pending: number }> = []
  for (const [model, need] of demandMap.value.entries()) {
    const allocated = allocationModelCountMap.value.get(model) || 0
    rows.push({
      model,
      need,
      allocated,
      pending: Math.max(0, need - allocated),
    })
  }
  return rows.sort((a, b) => compareModels(a.model, b.model))
})

const candidateRows = computed(() => {
  if (!selectedOrderId.value) return []
  const modelSet = new Set(requiredModels.value)
  return sortRowsByModel(inventoryRows.value.filter((r) => {
    const status = String(r['状态'] || '')
    const occupied = String(r['占用订单号'] || '')
    const model = normalizeModelName(r['机型'])
    if (!status.startsWith('库存中') && status !== '待入库') return false
    if (occupied) return false
    if (modelSet.size === 0) return true
    return modelSet.has(model)
  }), (r) => String(r['机型'] || ''))
})

const CACHE_ORDERS = 'allocation:orders'
const CACHE_INVENTORY = 'allocation:inventory'
const loadData = async (force = false) => {
  loading.value = true
  try {
    if (!force) {
      const orderCached = cacheStore.get<Row[]>(CACHE_ORDERS)
      const inventoryCached = cacheStore.get<Row[]>(CACHE_INVENTORY)
      if (orderCached && inventoryCached) {
        orders.value = orderCached
        inventoryRows.value = inventoryCached
        await tryAutoSelectOrderFromQuery()
        return
      }
    }
    const [nextOrders, nextInventoryRows] = await Promise.all([
      apiGetAll<Row>('/planning/orders'),
      apiGetAll<Row>('/inventory/'),
    ])
    orders.value = nextOrders
    inventoryRows.value = nextInventoryRows
    cacheStore.set(CACHE_ORDERS, nextOrders, 10_000)
    cacheStore.set(CACHE_INVENTORY, nextInventoryRows, 8_000)
    await tryAutoSelectOrderFromQuery()
    if (selectedOrderId.value) await loadAllocations()
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '读取数据失败')
  } finally {
    loading.value = false
  }
}

const loadAllocations = async () => {
  if (!selectedOrderId.value) {
    allocations.value = []
    return
  }
  try {
    const res = await apiGet<ListResponse>(`/planning/orders/${encodeURIComponent(selectedOrderId.value)}/allocations`)
    allocations.value = res.data || []
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '读取配货记录失败')
    allocations.value = []
  }
}

const selectOrder = async (row: Row) => {
  selectedOrder.value = row
  selectedOrderId.value = String(row['订单号'] || '')
  selectedCandidateSerials.value = []
  selectedAllocatedSerials.value = []
  await loadAllocations()
}

const tryAutoSelectOrderFromQuery = async () => {
  const q = String(route.query.order_id || '').trim()
  if (!q) return
  if (selectedOrderId.value === q) return
  const matched = orders.value.find((o) => String(o['订单号'] || '') === q)
  if (!matched) return
  await selectOrder(matched)
}

const refreshSelectedOrderFromList = () => {
  if (!selectedOrderId.value) return
  const matched = orders.value.find((o) => String(o['订单号'] || '') === selectedOrderId.value)
  if (matched) selectedOrder.value = matched
}

const onCandidateSelectionChange = (rows: Row[]) => {
  selectedCandidateSerials.value = rows.map((r) => String(r['流水号'] || '')).filter(Boolean)
}

const onAllocatedSelectionChange = (rows: Row[]) => {
  selectedAllocatedSerials.value = rows.map((r) => String(r['流水号'] || '')).filter(Boolean)
}

const allocateSelected = async () => {
  if (!selectedOrderId.value) return
  if (selectedCandidateSerials.value.length === 0) {
    ElMessage.warning('请先勾选要配货的机台')
    return
  }
  const demandTotal = totalDemandQty.value
  if (demandTotal > 0 && allocations.value.length + selectedCandidateSerials.value.length > demandTotal) {
    ElMessage.warning(`超出总需求数量：需求 ${demandTotal}，当前已配 ${allocations.value.length}，本次勾选 ${selectedCandidateSerials.value.length}`)
    return
  }

  const selectedRows = candidateRows.value.filter((r) => selectedCandidateSerials.value.includes(String(r['流水号'] || '')))
  const selectedModelMap = new Map<string, number>()
  for (const r of selectedRows) {
    const model = normalizeModelName(r['机型'])
    if (!model) continue
    selectedModelMap.set(model, (selectedModelMap.get(model) || 0) + 1)
  }
  for (const [model, selectedCount] of selectedModelMap.entries()) {
    const need = demandMap.value.get(model)
    if (!need || need <= 0) {
      ElMessage.warning(`机型 ${model} 不在订单需求中，无法配货`)
      return
    }
    const allocated = allocationModelCountMap.value.get(model) || 0
    if (allocated + selectedCount > need) {
      ElMessage.warning(`机型 ${model} 超配：需求 ${need}，已配 ${allocated}，本次勾选 ${selectedCount}`)
      return
    }
  }

  saving.value = true
  try {
    await apiPost(`/planning/orders/${encodeURIComponent(selectedOrderId.value)}/allocate`, {
      selected_serial_nos: selectedCandidateSerials.value,
    })
    ElMessage.success('配货成功')
    selectedCandidateSerials.value = []
    await loadData(true)
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '配货失败')
  } finally {
    saving.value = false
  }
}

const releaseSelected = async () => {
  if (!selectedOrderId.value) return
  if (selectedAllocatedSerials.value.length === 0) {
    ElMessage.warning('请先勾选要释放的机台')
    return
  }
  saving.value = true
  try {
    const res = await apiPost<ReleaseResponse>(`/planning/orders/${encodeURIComponent(selectedOrderId.value)}/release`, {
      selected_serial_nos: selectedAllocatedSerials.value,
      all: false,
    })
    const released = Number(res.released || 0)
    if (released > 0) ElMessage.success(res.message || `已释放 ${released} 台机台`)
    else ElMessage.warning(res.message || '当前没有可释放机台')
    selectedAllocatedSerials.value = []
    await loadData(true)
    refreshSelectedOrderFromList()
    await loadAllocations()
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '释放失败')
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  loadData()
})
</script>

<style scoped>
.head-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-2);
}
.title {
  margin: 0;
  font-size: 28px;
  font-weight: 800;
}
.card-head {
  font-weight: 700;
}
.order-list {
  margin-top: var(--space-2);
  max-height: 710px;
}
.order-item {
  border: 1px solid var(--color-gray-200);
  border-radius: var(--radius-lg);
  background: var(--panel-bg);
  padding: 10px 12px; /* 增加上下内边距 */
  min-height: 64px; /* 从固定 height 56px 改为 min-height 64px，让它自适应内容 */
  text-align: left;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  justify-content: center;
  width: 100%;
}
.order-item.active {
  border-color: #ef4444;
  background: #fee2e2;
}
.order-customer {
  font-size: var(--font-size-base); /* 放大客户名称字号 */
  font-weight: 700; /* 加粗客户名称 */
  color: var(--color-gray-900);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.sub {
  margin-top: 4px;
  color: var(--color-gray-600); /* 略微加深副标题颜色 */
  font-size: var(--font-size-base); /* 放大单号和机型字号 */
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.summary {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px 10px;
  font-size: var(--font-size-base); /* 放大配货面板摘要描述字号 */
}
.field-label {
  margin-bottom: 6px;
  font-size: var(--font-size-base); /* 放大配货面板模块小标题字号 */
  font-weight: 600;
  color: var(--color-gray-800);
}
.ops {
  margin-top: var(--space-2);
  display: flex;
  gap: 8px;
}
</style>
