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
          <el-select
            v-model="orderModelFilter"
            class="order-model-filter"
            clearable
            filterable
            placeholder="按机台筛选"
          >
            <el-option v-for="model in orderModelOptions" :key="model" :label="model" :value="model" />
          </el-select>
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
                  <div class="order-item-head">
                    <div class="order-customer" :title="o['客户名']">{{ o['客户名'] }}</div>
                    <el-tag :type="getComputedOrderState(o).type" size="small" class="status-tag">
                      {{ getComputedOrderState(o).text }}
                    </el-tag>
                  </div>
                  <div class="sub" :title="`${o['订单号']} | ${o['需求机型']}`">{{ o['订单号'] }} | {{ o['需求机型'] }}</div>
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
              <div class="summary-note">备注：{{ selectedOrder?.['备注'] || '-' }}</div>
            </div>

            <el-divider />
            <div class="field-label">需求分解（按机型）</div>
            <el-table :data="demandRows" border stripe size="small">
              <el-table-column prop="displayModel" label="机型" min-width="180" />
              <el-table-column prop="need" label="需求" width="90" />
              <el-table-column prop="allocated" label="已确认" width="90" />
              <el-table-column prop="pending" label="待确认" width="90" />
              <el-table-column label="状态" width="120">
                <template #default="scope">
                  <el-tag :type="scope.row.pending <= 0 ? 'success' : 'warning'">
                    {{ scope.row.pending <= 0 ? '已满足' : '待补齐' }}
                  </el-tag>
                </template>
              </el-table-column>
            </el-table>

            <el-divider />
            <div class="field-head">
              <div class="field-label">应配机台清单（按合同自动带出）</div>
              <div class="field-head-right" style="display: flex; gap: 8px; align-items: center;">
                <el-input v-model="candidateKeyword" placeholder="搜索流水号/机型/批次" clearable style="width: 200px" />
                <el-select v-model="candidateStatusFilter" style="width: 200px">
                  <el-option label="全部状态" value="" />
                  <el-option label="待入库" value="待入库" />
                  <el-option label="库存中" value="库存中" />
                </el-select>
              </div>
            </div>
            <el-table
              :data="candidateRows"
              border
              stripe
              size="small"
              height="230"
              :row-class-name="getAllocationRowClassName"
              @selection-change="onCandidateSelectionChange"
            >
              <el-table-column type="selection" width="48" />
              <el-table-column prop="流水号" label="流水号" width="150" />
              <el-table-column prop="机型" label="机型" min-width="160" />
              <el-table-column prop="状态" label="状态" width="120" />
              <el-table-column prop="批次号" label="批次号" width="120" />
              <el-table-column prop="合同备注" label="合同备注" min-width="160" />
            </el-table>
            <div class="ops">
              <el-button type="primary" :loading="saving" @click="allocateSelected">复核确认配货</el-button>
            </div>

            <el-divider />
            <div class="field-label">配货撤回</div>
            <el-table
              :data="confirmedRows"
              border
              stripe
              size="small"
              height="230"
              :row-class-name="getAllocationRowClassName"
              @selection-change="onAllocatedSelectionChange"
            >
              <el-table-column type="selection" width="48" />
              <el-table-column prop="流水号" label="流水号" width="150" />
              <el-table-column prop="机型" label="机型" min-width="160" />
              <el-table-column prop="状态" label="状态" width="90" />
              <el-table-column prop="批次号" label="批次号" width="120" />
              <el-table-column prop="合同备注" label="合同备注" min-width="160" />
            </el-table>
            <div class="ops">
              <el-button type="danger" :loading="saving" @click="releaseSelected">⚠️ 确认撤回</el-button>
              <el-button type="success" :loading="saving" @click="completeAllocation">配货完成</el-button>
            </div>
          </template>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useRoute } from 'vue-router'
import { apiGet, apiGetAll, apiPost, getApiErrorMessage } from '../utils/request'
import { useCacheStore } from '../store/cache'
import { compareModels, normalizeModelName, sortRowsByModel } from '../utils/modelOrder'
import PageHeader from '../components/PageHeader.vue'
import VirtualScrollList from '../components/VirtualScrollList.vue'
type ListResponse<T = any> = { data: T[] }
type ReleaseResponse = { message?: string; released?: number }
type TagType = 'primary' | 'success' | 'warning' | 'info' | 'danger'

type Row = Record<string, any>

const loading = ref(false)
const saving = ref(false)
const orderKeyword = ref('')
const orderModelFilter = ref('')
const orders = ref<Row[]>([])
const allocations = ref<Row[]>([])
const orderDetailRows = ref<Array<{ model: string; high: boolean; qty: number }>>([])
const orderDetailsSource = ref<'factory_plan' | 'sales_orders' | ''>('')
const cacheStore = useCacheStore()
const route = useRoute()
const selectedOrderId = ref('')
const selectedOrder = ref<Row | null>(null)
const selectedCandidateSerials = ref<string[]>([])
const selectedAllocatedSerials = ref<string[]>([])
const candidateStatusFilter = ref('')
const candidateKeyword = ref('')

const isHighHint = (...values: unknown[]) => values.some((value) => String(value || '').includes('加高'))

const variantKey = (model: string, high: boolean) => `${model}||${high ? 'high' : 'normal'}`

const parseLegacyOrderLineNotes = (note: unknown) => {
  const map = new Map<string, string[]>()
  const raw = String(note || '').replace(/^(\[总\]\s*)+/, '').trim()
  const label = String.raw`(?:\[[^\]]+\]\s*)?[A-Za-z0-9][A-Za-z0-9_\-./+]*(?:\([^)]*\))*`
  const pattern = new RegExp(
    String.raw`(?:^|\s)(?:\[[^\]]+\]\s*)?([A-Za-z0-9][A-Za-z0-9_\-./+]*(?:\([^)]*\))*)\s*[:：]\s*` +
      String.raw`(.*?)(?=\s+${label}\s*[:：]|$)`,
    'g',
  )
  let m: RegExpExecArray | null = null
  while ((m = pattern.exec(raw)) !== null) {
    const model = normalizeModelName(m[1])
    const rowNote = String(m[2] || '').trim()
    if (!model || !rowNote) continue
    if (!map.has(model)) map.set(model, [])
    map.get(model)?.push(rowNote)
  }
  return map
}

const rowVariant = (row: Row) => {
  const model = normalizeModelName(row['机型'])
  const high = isHighHint(row['机型'], row['批次号'], row['合同备注'])
  return { model, high, key: variantKey(model, high) }
}

const parseDemandEntries = (order: Row | null) => {
  const isSelectedOrder = !!order && String(order['订单号'] || '') === selectedOrderId.value
  if (isSelectedOrder && orderDetailsSource.value === 'factory_plan' && orderDetailRows.value.length > 0) {
    return orderDetailRows.value
  }
  const entries: Array<{ model: string; high: boolean; qty: number }> = []
  if (!order) return entries
  const raw = String(order['需求机型'] || '')
  const legacyNotes = parseLegacyOrderLineNotes(order['备注'])
  const parts = raw.split(/[;；/,，]/g).map((s) => s.trim()).filter(Boolean)
  for (const partRaw of parts) {
    const part = partRaw.replace(/\[[^\]]*]/g, '').trim()
    const m = part.match(/(?:[x×:：]\s*)(\d+)\s*$/i)
    const qty = m ? Number(m[1]) || 0 : 0
    const modelRaw = part.replace(/(?:[x×:：]\s*)\d+\s*$/i, '').trim()
    const model = normalizeModelName(modelRaw)
    if (!model) continue
    const rowNotes = legacyNotes.get(model) || []
    const legacyNote = rowNotes.shift() || ''
    entries.push({ model, high: isHighHint(modelRaw, legacyNote), qty: Math.max(0, qty) })
  }
  if (entries.length === 0) {
    const fallbackModel = normalizeModelName(raw)
    const fallbackQty = Number(order['需求数量'] || 0)
    if (fallbackModel) {
      const legacyHigh = (legacyNotes.get(fallbackModel) || []).some((note) => isHighHint(note))
      entries.push({
        model: fallbackModel,
        high: legacyHigh,
        qty: Number.isFinite(fallbackQty) ? Math.max(0, fallbackQty) : 0,
      })
    }
  }
  return entries
}

const isActiveOrder = (order: Row) => {
  const status = String(order.status || 'active').toLowerCase()
  return !['done', 'shipped', 'completed', 'canceled', 'deleted'].includes(status)
}

const orderContainsModel = (order: Row, modelFilter: string) => {
  if (!modelFilter) return true
  return parseDemandEntries(order).some((entry) => entry.model === modelFilter)
}

const orderModelOptions = computed(() => {
  const models = new Set<string>()
  for (const order of orders.value) {
    if (!isActiveOrder(order)) continue
    for (const entry of parseDemandEntries(order)) {
      if (entry.model) models.add(entry.model)
    }
  }
  return Array.from(models).sort(compareModels)
})

const filteredOrders = computed(() => {
  const term = orderKeyword.value.trim().toLowerCase()
  const modelFilter = orderModelFilter.value.trim()
  let result = orders.value
    .filter(isActiveOrder)
    .filter((o) => orderContainsModel(o, modelFilter))
    .filter((o) => {
      if (!term) return true
      const hit = `${o['订单号'] || ''} ${o['客户名'] || ''}`.toLowerCase()
      return hit.includes(term)
    })
    
  // Sort by order creation time (oldest first for FIFO, or newest first, let's do descending newest first)
  return result.sort((a, b) => {
    const timeA = new Date(a['下单时间'] || 0).getTime()
    const timeB = new Date(b['下单时间'] || 0).getTime()
    return timeB - timeA
  })
})

const parseDemandMap = (order: Row | null) => {
  const map = new Map<string, { model: string; high: boolean; qty: number }>()
  for (const e of parseDemandEntries(order)) {
    const key = variantKey(e.model, e.high)
    const current = map.get(key) || { model: e.model, high: e.high, qty: 0 }
    current.qty += Number.isFinite(e.qty) && e.qty > 0 ? e.qty : 0
    map.set(key, current)
  }
  return map
}

const demandMap = computed(() => parseDemandMap(selectedOrder.value))
const totalDemandQty = computed(() => {
  let total = 0
  for (const item of demandMap.value.values()) total += item.qty
  return total
})

const allocationModelCountMap = computed(() => {
  const map = new Map<string, number>()
  for (const r of allocations.value) {
    const occupied = String(r['占用订单号'] || '').trim()
    const status = String(r['状态'] || '').trim()
    if (occupied !== selectedOrderId.value) continue
    if (status === '已出库' || status === '未入库') continue
    const variant = rowVariant(r)
    if (!variant.model) continue
    map.set(variant.key, (map.get(variant.key) || 0) + 1)
  }
  return map
})

const demandRows = computed(() => {
  const rows: Array<{ model: string; high: boolean; displayModel: string; need: number; allocated: number; pending: number }> = []
  for (const [key, item] of demandMap.value.entries()) {
    const allocated = allocationModelCountMap.value.get(key) || 0
    rows.push({
      model: item.model,
      high: item.high,
      displayModel: `${item.model}${item.high ? '（加高）' : '（普通）'}`,
      need: item.qty,
      allocated,
      pending: Math.max(0, item.qty - allocated),
    })
  }
  return rows.sort((a, b) => compareModels(a.model, b.model))
})

const candidateRows = computed(() => {
  if (!selectedOrderId.value) return []
  const kw = candidateKeyword.value.trim().toLowerCase()
  return sortRowsByModel(allocations.value.filter((r) => {
    const serialNo = String(r['流水号'] || '').trim()
    const status = String(r['状态'] || '').trim()
    const occupied = String(r['占用订单号'] || '')
    const model = String(r['机型'] || '').trim()
    const batch = String(r['批次号'] || '').trim()
    
    if (!serialNo) return false
    if (status === '未入库' || status === '已出库' || status === '已绑定') return false
    if (occupied) return false
    
    if (candidateStatusFilter.value === '待入库' && status !== '待入库') return false
    if (candidateStatusFilter.value === '库存中' && !status.startsWith('库存中')) return false
    
    if (kw) {
      const hit = `${model} ${batch} ${serialNo}`.toLowerCase()
      if (!hit.includes(kw)) return false
    }
    
    return true
  }), (r) => String(r['机型'] || ''))
})

const confirmedRows = computed(() => {
  return sortRowsByModel(allocations.value.filter((r) => {
    const serialNo = String(r['流水号'] || '').trim()
    const occupied = String(r['占用订单号'] || '').trim()
    const status = String(r['状态'] || '').trim()
    return serialNo && occupied === selectedOrderId.value && status !== '已出库'
  }), (r) => String(r['机型'] || ''))
})
const confirmedAllocatedTotal = computed(() => confirmedRows.value.length)

const CACHE_ORDERS = 'allocation:orders'
const loadData = async (force = false) => {
  loading.value = true
  try {
    if (!force) {
      const orderCached = cacheStore.get<Row[]>(CACHE_ORDERS)
      if (orderCached) {
        orders.value = orderCached
        await tryAutoSelectOrderFromQuery()
        return
      }
    }
    const nextOrders = await apiGetAll<Row>('/planning/orders')
    orders.value = nextOrders
    cacheStore.set(CACHE_ORDERS, nextOrders, 10_000)
    await tryAutoSelectOrderFromQuery()
    refreshSelectedOrderFromList()
    if (selectedOrderId.value) await loadSelectedOrderContext()
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '读取数据失败')
  } finally {
    loading.value = false
  }
}

const updateOrderStatusLocally = (orderId: string, status: string) => {
  if (!orderId) return
  const nextOrders = orders.value.map((order) => (
    String(order['订单号'] || '') === orderId ? { ...order, status } : order
  ))
  orders.value = nextOrders
  const matched = nextOrders.find((order) => String(order['订单号'] || '') === orderId)
  if (matched) selectedOrder.value = matched
  cacheStore.set(CACHE_ORDERS, nextOrders, 10_000)
}

const refreshCurrentOrder = async (nextStatus?: string) => {
  if (nextStatus) {
    updateOrderStatusLocally(selectedOrderId.value, nextStatus)
  } else {
    refreshSelectedOrderFromList()
  }
  await loadSelectedOrderContext()
}

const loadOrderDetails = async () => {
  orderDetailRows.value = []
  orderDetailsSource.value = ''
  if (!selectedOrderId.value) return
  try {
    const res: any = await apiGet(`/planning/orders/${encodeURIComponent(selectedOrderId.value)}/details`)
    const source = res?.source === 'factory_plan' ? 'factory_plan' : 'sales_orders'
    orderDetailsSource.value = source
    if (source !== 'factory_plan') return
    const details = Array.isArray(res.details) ? res.details : []
    orderDetailRows.value = details
      .map((item: any) => {
        const model = normalizeModelName(item?.['机型'])
        const remark = String(item?.['备注'] || '')
        return {
          model,
          high: isHighHint(item?.['机型'], remark),
          qty: Math.max(0, Number(item?.['数量'] || 0) || 0),
        }
      })
      .filter((item: { model: string; qty: number }) => item.model && item.qty > 0)
  } catch {
    orderDetailRows.value = []
    orderDetailsSource.value = ''
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

const loadSelectedOrderContext = async () => {
  if (!selectedOrderId.value) {
    orderDetailRows.value = []
    orderDetailsSource.value = ''
    allocations.value = []
    return
  }
  await Promise.all([loadOrderDetails(), loadAllocations()])
}

const selectOrder = async (row: Row) => {
  selectedOrder.value = row
  selectedOrderId.value = String(row['订单号'] || '')
  selectedCandidateSerials.value = []
  selectedAllocatedSerials.value = []
  await loadSelectedOrderContext()
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

const getAllocationRowClassName = ({ row }: { row: Row }) => {
  const hasContract = String(row['合同号'] || '').trim()
  const hasOrder = String(row['占用订单号'] || '').trim()

  // 有合同号 或 已配货给订单 → 绿色底色高亮
  if (hasContract || hasOrder) {
    return 'contract-specified-row'
  }
  return ''
}

watch(candidateStatusFilter, () => {
  selectedCandidateSerials.value = []
})

watch([orderKeyword, orderModelFilter, filteredOrders], async () => {
  if (!selectedOrderId.value) return
  const stillVisible = filteredOrders.value.some((order) => String(order['订单号'] || '') === selectedOrderId.value)
  if (stillVisible) return
  const first = filteredOrders.value[0]
  if (first) {
    await selectOrder(first)
  } else {
    selectedOrder.value = null
    selectedOrderId.value = ''
    allocations.value = []
    orderDetailRows.value = []
    orderDetailsSource.value = ''
  }
})

const allocateSelected = async () => {
  if (!selectedOrderId.value) return
  if (selectedCandidateSerials.value.length === 0) {
    ElMessage.warning('请先勾选要配货的机台')
    return
  }
  const demandTotal = totalDemandQty.value
  if (demandTotal > 0 && confirmedAllocatedTotal.value + selectedCandidateSerials.value.length > demandTotal) {
    ElMessage.warning(`超出总需求数量：需求 ${demandTotal}，当前已配 ${confirmedAllocatedTotal.value}，本次勾选 ${selectedCandidateSerials.value.length}`)
    return
  }

  const selectedRows = candidateRows.value.filter((r) => selectedCandidateSerials.value.includes(String(r['流水号'] || '')))
  const selectedModelMap = new Map<string, number>()
  for (const r of selectedRows) {
    const variant = rowVariant(r)
    if (!variant.model) continue
    selectedModelMap.set(variant.key, (selectedModelMap.get(variant.key) || 0) + 1)
  }
  for (const [key, selectedCount] of selectedModelMap.entries()) {
    const demand = demandMap.value.get(key)
    if (!demand || demand.qty <= 0) {
      const [model, highText] = key.split('||')
      ElMessage.warning(`机型 ${model}${highText === 'high' ? '（加高）' : '（普通）'} 不在订单需求中，无法配货`)
      return
    }
    const allocated = allocationModelCountMap.value.get(key) || 0
    if (allocated + selectedCount > demand.qty) {
      ElMessage.warning(`机型 ${demand.model}${demand.high ? '（加高）' : '（普通）'} 超配：需求 ${demand.qty}，已配 ${allocated}，本次勾选 ${selectedCount}`)
      return
    }
  }

  saving.value = true
  try {
    await apiPost(`/planning/orders/${encodeURIComponent(selectedOrderId.value)}/allocate`, {
      selected_serial_nos: selectedCandidateSerials.value,
    })
    ElMessage.success('配货复核已确认')
    selectedCandidateSerials.value = []
    await refreshCurrentOrder()
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '配货复核失败')
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
    await refreshCurrentOrder(released > 0 ? 'active' : undefined)
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '释放失败')
  } finally {
    saving.value = false
  }
}

const completeAllocation = async () => {
  if (!selectedOrderId.value) return
  saving.value = true
  try {
    const res = await apiPost<{ message?: string }>(`/planning/orders/${encodeURIComponent(selectedOrderId.value)}/complete-allocation`, {})
    ElMessage.success(res.message || '配货完成')
    await refreshCurrentOrder('ready')
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '配货完成失败')
  } finally {
    saving.value = false
  }
}

const getComputedOrderState = (o: Row): { text: string; type: TagType } => {
  const s = String(o.status || 'active')
  if (s === 'packed') return { text: '已打包', type: 'primary' }
  if (s === 'shipped') return { text: '已出库', type: 'info' }
  if (s === 'canceled') return { text: '已取消', type: 'danger' }

  if (s === 'ready') {
    return { text: '已满足', type: 'success' }
  }
  return { text: '待配齐', type: 'danger' }
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
.order-model-filter {
  width: 100%;
  margin-top: 8px;
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
.order-item-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  width: 100%;
  gap: 8px;
}
.order-customer {
  flex: 1;
  font-size: var(--font-size-base); /* 放大客户名称字号 */
  font-weight: 700; /* 加粗客户名称 */
  color: var(--color-gray-900);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  text-align: left;
}
.status-tag {
  flex-shrink: 0;
}
.sub {
  margin-top: 4px;
  color: var(--color-gray-600); /* 略微加深副标题颜色 */
  font-size: var(--font-size-base); /* 放大单号和机型字号 */
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  text-align: left;
  width: 100%;
}
.summary {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px 10px;
  font-size: var(--font-size-base); /* 放大配货面板摘要描述字号 */
}
.summary-note {
  grid-column: 1 / -1;
  min-height: 22px;
  color: var(--color-gray-700);
  white-space: normal;
  word-break: break-word;
}
.field-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 6px;
}
.field-label {
  font-size: var(--font-size-base); /* 放大配货面板模块小标题字号 */
  font-weight: 600;
  color: var(--color-gray-800);
}
.ops {
  margin-top: var(--space-2);
  display: flex;
  gap: 8px;
}
:deep(.contract-specified-row td) {
  background-color: #ecfdf5 !important;
}
:deep(.contract-specified-row:hover td) {
  background-color: #d1fae5 !important;
}
</style>
