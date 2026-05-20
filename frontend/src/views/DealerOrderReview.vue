<template>
  <div class="dealer-review-page">
    <PageHeader title="经销商订单审核">
      <template #actions>
        <el-button :loading="syncing" @click="syncCloudOrders">同步云端</el-button>
        <el-button :loading="inventorySyncing" @click="syncCloudInventory">同步库存到云端</el-button>
        <el-button :loading="completedSyncing" @click="syncCompletedCloud">同步完成状态</el-button>
        <el-button type="primary" :loading="loading" @click="loadOrders">刷新</el-button>
      </template>
    </PageHeader>

    <div class="filters">
      <el-input
        v-model="filters.keyword"
        clearable
        placeholder="搜索订单号 / 经销商 / 联系人 / 机型"
        class="keyword"
        @keyup.enter="loadOrders"
        @clear="loadOrders"
      />
      <el-select v-model="filters.status" class="status-filter" @change="loadOrders">
        <el-option label="全部状态" value="" />
        <el-option label="待审核" value="pending" />
        <el-option label="已通过" value="approved" />
        <el-option label="已转合同" value="contracted" />
        <el-option label="部分配货" value="partial_allocated" />
        <el-option label="已配货" value="allocated" />
        <el-option label="已驳回" value="rejected" />
        <el-option label="已取消" value="cancelled" />
        <el-option label="已完成" value="completed" />
      </el-select>
      <el-button @click="loadOrders">查询</el-button>
    </div>

    <el-table
      v-loading="loading"
      :data="tableRows"
      row-key="_row_key"
      border
      stripe
      size="small"
      height="620"
      highlight-current-row
      @row-click="selectOrder"
    >
      <el-table-column prop="created_at" label="提交时间" width="160" />
      <el-table-column prop="order_no" label="订单号" min-width="170" show-overflow-tooltip />
      <el-table-column prop="dealer_name" label="经销商" min-width="150" show-overflow-tooltip />
      <el-table-column prop="contact_name" label="联系人" width="110" show-overflow-tooltip />
      <el-table-column prop="model" label="机型明细" min-width="190" show-overflow-tooltip />
      <el-table-column prop="batch_no" label="批次/来源" width="150" show-overflow-tooltip>
        <template #default="{ row }">{{ displayBatch(row.batch_no) }}</template>
      </el-table-column>
      <el-table-column prop="line_no" label="行号" width="70" align="right" />
      <el-table-column prop="quantity" label="数量" width="90" align="right" />
      <el-table-column prop="status" label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="statusMeta(row.status).type">{{ statusMeta(row.status).text }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="最小可审" width="120" align="right">
        <template #default="{ row }">
          <span :class="{ danger: hasInsufficientItem(row) }">
            {{ row.available_qty ?? '-' }}
          </span>
        </template>
      </el-table-column>
      <el-table-column prop="reviewed_by" label="审核人" width="110" show-overflow-tooltip />
      <el-table-column label="操作" width="340" fixed="right">
        <template #default="{ row }">
          <el-button size="small" :disabled="row.status !== 'pending'" @click.stop="approveOrder(row)">通过</el-button>
          <el-button size="small" type="danger" :disabled="!canReject(row)" @click.stop="rejectOrder(row)">驳回</el-button>
          <el-button size="small" type="primary" :disabled="!canConvert(row)" @click.stop="openConvertDialog(row)">转合同</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="pager-row">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="total"
        :page-sizes="[20, 50, 100]"
        layout="total, sizes, prev, pager, next"
        @current-change="loadOrders"
        @size-change="onSizeChange"
      />
    </div>

    <el-drawer v-model="drawerOpen" title="订单审核详情" size="720px">
      <el-empty v-if="!selectedOrder" description="请选择订单" />
      <template v-else>
        <div class="detail-grid">
          <span>订单号</span><strong>{{ selectedOrder.order_no }}</strong>
          <span>经销商</span><strong>{{ selectedOrder.dealer_name || '-' }}</strong>
          <span>客户</span><strong>{{ selectedOrder.customer_name || '-' }}</strong>
          <span>联系人</span><strong>{{ selectedOrder.contact_name || '-' }}</strong>
          <span>电话</span><strong>{{ selectedOrder.contact_phone || '-' }}</strong>
          <span>当前状态</span><strong>{{ statusMeta(selectedOrder.status).text }}</strong>
          <span>总数量</span><strong>{{ selectedOrder.quantity }}</strong>
          <span>已配货</span><strong>{{ selectedOrder.allocated_qty ?? 0 }}</strong>
          <span v-if="selectedOrder.contract_no">合同号</span><strong v-if="selectedOrder.contract_no">{{ selectedOrder.contract_no }}</strong>
        </div>

        <el-divider />
        <el-table :data="detailItems" border size="small">
          <el-table-column prop="line_no" label="行号" width="70" align="right" />
          <el-table-column prop="model" label="机型" min-width="150" show-overflow-tooltip />
          <el-table-column prop="batch_no" label="批次/来源" min-width="130" show-overflow-tooltip>
            <template #default="{ row }">{{ displayBatch(row.batch_no) }}</template>
          </el-table-column>
          <el-table-column prop="quantity" label="数量" width="80" align="right" />
          <el-table-column prop="allocated_qty" label="已配" width="80" align="right" />
          <el-table-column label="可用" width="90" align="right">
            <template #default="{ row }">
              <span :class="{ danger: Number(row.available_qty || 0) < Number(row.quantity || 0) - Number(row.allocated_qty || 0) }">
                {{ row.available_qty ?? '-' }}
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="status" label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="statusMeta(row.status).type">{{ statusMeta(row.status).text }}</el-tag>
            </template>
          </el-table-column>
        </el-table>

        <el-divider />
        <div class="availability">
          <div>
            <span>库存总量</span>
            <strong>{{ preview?.summary_qty ?? selectedOrder.summary_qty ?? '-' }}</strong>
          </div>
          <div>
            <span>已占用</span>
            <strong>{{ preview?.occupied_qty ?? selectedOrder.occupied_qty ?? '-' }}</strong>
          </div>
          <div>
            <span>最小可审</span>
            <strong :class="{ danger: hasInsufficientItem(selectedOrder) }">
              {{ preview?.available_qty ?? selectedOrder.available_qty ?? '-' }}
            </strong>
          </div>
        </div>

        <el-divider />
        <div class="note-title">订单备注</div>
        <div class="note-box">{{ selectedOrder.remark || '-' }}</div>
        <div class="note-title">审核备注</div>
        <div class="note-box">{{ selectedOrder.review_note || '-' }}</div>

        <div class="drawer-actions">
          <el-button :disabled="selectedOrder.status !== 'pending'" @click="approveOrder(selectedOrder)">通过审核</el-button>
          <el-button type="danger" :disabled="!canReject(selectedOrder)" @click="rejectOrder(selectedOrder)">驳回</el-button>
          <el-button type="primary" :disabled="!canConvert(selectedOrder)" @click="openConvertDialog(selectedOrder)">转为合同</el-button>
        </div>
      </template>
    </el-drawer>

    <el-dialog
      v-model="convertDialogVisible"
      title="转为合同"
      width="680px"
      :close-on-click-modal="false"
      :close-on-press-escape="false"
    >
      <div class="convert-grid">
        <div>
          <div class="ops-label">合同号</div>
          <el-input v-model="convertForm.contractNo" placeholder="自动生成" />
        </div>
        <div>
          <div class="ops-label">期望交付日期</div>
          <el-date-picker v-model="convertForm.deliveryDate" type="date" value-format="YYYY-MM-DD" style="width:100%" />
        </div>
        <div>
          <div class="ops-label">客户名称</div>
          <el-input v-model="convertForm.customer" />
        </div>
        <div>
          <div class="ops-label">代理商</div>
          <el-input v-model="convertForm.agent" />
        </div>
        <div>
          <div class="ops-label">急单</div>
          <el-switch v-model="convertForm.isRush" active-text="是" inactive-text="否" />
        </div>
      </div>

      <el-divider />
      <div class="ops-label">机型明细</div>
      <el-table :data="convertForm.items" border size="small" class="form-table">
        <el-table-column label="#" width="50">
          <template #default="scope">{{ scope.$index + 1 }}</template>
        </el-table-column>
        <el-table-column label="机型" min-width="160">
          <template #default="scope">
            <el-select v-model="scope.row.model" filterable placeholder="机型" style="width:100%">
              <el-option v-for="m in modelOptions" :key="m" :label="m" :value="m" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="数量" width="90">
          <template #default="scope">
            <el-input-number v-model="scope.row.qty" :min="1" :controls="false" style="width:100%" />
          </template>
        </el-table-column>
        <el-table-column label="加高" width="70">
          <template #default="scope">
            <el-checkbox v-model="scope.row.high" />
          </template>
        </el-table-column>
        <el-table-column label="行备注" min-width="120">
          <template #default="scope">
            <el-input v-model="scope.row.rowNote" />
          </template>
        </el-table-column>
      </el-table>

      <el-divider />
      <div class="ops-label">合同总备注</div>
      <el-input v-model="convertForm.contractNote" placeholder="可选" />

      <div class="save-mode-section">
        <div class="ops-label">保存方式</div>
        <div class="save-mode-hint">进入沙盘（参与老板计划排产）或使用现货（直接置为已规划）。</div>
        <div v-if="!convertCanUseSpot" class="save-mode-blocked">当前"使用现货"不可用：{{ convertSpotBlockReason }}</div>
      </div>

      <template #footer>
        <el-button @click="convertDialogVisible = false">取消</el-button>
        <el-button type="warning" :disabled="!convertCanUseSpot" :loading="convertSaving" @click="submitConvert('spot')">使用现货</el-button>
        <el-button type="primary" :loading="convertSaving" @click="submitConvert('sandbox')">进入沙盘</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import PageHeader from '../components/PageHeader.vue'
import { apiGet, apiGetAll, apiPost, getApiErrorMessage } from '../utils/request'
import { getModelOrderList, isModelInDictionary } from '../utils/modelOrder'

type DealerOrder = {
  id: number
  order_no: string
  line_no?: number
  line_count?: number
  dealer_openid?: string
  dealer_name?: string
  customer_name?: string
  contact_name?: string
  contact_phone?: string
  model: string
  batch_no?: string
  expected_inbound_time?: string
  quantity: number
  approved_qty?: number
  allocated_qty?: number
  delivery_date?: string
  contract_no?: string
  status: string
  remark?: string
  review_note?: string
  reviewed_at?: string
  reviewed_by?: string
  created_at?: string
  summary_qty?: number
  occupied_qty?: number
  available_qty?: number
  items?: DealerOrder[]
}

type DealerOrderTableRow = DealerOrder & {
  _row_key: string
  _order: DealerOrder
}

type OrderListResponse = {
  data: DealerOrder[]
  total: number
}

type PreviewResponse = {
  order: DealerOrder
  items: DealerOrder[]
  summary_qty: number
  occupied_qty: number
  available_qty: number
  can_approve: boolean
}

const loading = ref(false)
const syncing = ref(false)
const inventorySyncing = ref(false)
const completedSyncing = ref(false)
const orders = ref<DealerOrder[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(50)
const selectedOrderNo = ref('')
const drawerOpen = ref(false)
const preview = ref<PreviewResponse | null>(null)
const filters = reactive({
  keyword: '',
  status: 'pending',
})

const selectedOrder = computed(() => orders.value.find((row) => row.order_no === selectedOrderNo.value) || null)
const detailItems = computed(() => preview.value?.items || selectedOrder.value?.items || (selectedOrder.value ? [selectedOrder.value] : []))
const tableRows = computed<DealerOrderTableRow[]>(() => {
  return orders.value.flatMap((order) => {
    const items = order.items?.length ? order.items : [order]
    return items.map((item, index) => ({
      ...order,
      ...item,
      remark: item.remark || order.remark || '',
      review_note: item.review_note || order.review_note || '',
      items: order.items?.length ? order.items : [order],
      line_count: order.line_count,
      _order: order,
      _row_key: `${order.order_no}-${item.line_no || index + 1}`,
    }))
  })
})

const statusMeta = (status: string) => {
  const map: Record<string, { text: string; type: 'primary' | 'success' | 'warning' | 'danger' | 'info' }> = {
    pending: { text: '待审核', type: 'warning' },
    approved: { text: '已通过', type: 'primary' },
    contracted: { text: '已转合同', type: 'success' },
    partial_allocated: { text: '部分配货', type: 'success' },
    allocated: { text: '已配货', type: 'success' },
    rejected: { text: '已驳回', type: 'danger' },
    cancelled: { text: '已取消', type: 'info' },
    completed: { text: '已完成', type: 'success' },
  }
  return map[status] || { text: status || '-', type: 'info' }
}

const displayBatch = (batchNo?: string) => {
  if (!batchNo) return '-'
  if (batchNo === 'FINISHED-STOCK') return '库存中'
  return batchNo
}

const hasInsufficientItem = (row: DealerOrder) => {
  const items = row.items?.length ? row.items : [row]
  return items.some((item) => Number(item.available_qty || 0) < Number(item.quantity || 0) - Number(item.allocated_qty || 0))
}

const canReject = (row: DealerOrder) => ['pending', 'approved'].includes(row.status)
const canConvert = (row: DealerOrder) => ['pending', 'approved'].includes(row.status)

const loadOrders = async () => {
  loading.value = true
  try {
    const res = await apiGet<OrderListResponse>('/dealer-orders/', {
      params: {
        status: filters.status || undefined,
        keyword: filters.keyword || undefined,
        page: page.value,
        page_size: pageSize.value,
      },
    })
    orders.value = res.data || []
    total.value = Number(res.total || 0)
    if (selectedOrderNo.value && !orders.value.some((row) => row.order_no === selectedOrderNo.value)) {
      selectedOrderNo.value = ''
      preview.value = null
    }
  } finally {
    loading.value = false
  }
}

const loadPreview = async (orderNo: string) => {
  preview.value = await apiGet<PreviewResponse>(`/dealer-orders/${encodeURIComponent(orderNo)}/preview`)
}

const selectOrder = async (row: DealerOrder) => {
  selectedOrderNo.value = row.order_no
  drawerOpen.value = true
  try {
    await loadPreview(row.order_no)
  } catch {
    preview.value = null
  }
}

const onSizeChange = () => {
  page.value = 1
  loadOrders()
}

const syncCloudOrders = async () => {
  syncing.value = true
  try {
    const res = await apiPost<{
      inserted?: number
      updated?: number
      skipped?: number
    }>('/dealer-orders/sync-cloud', {
      status: 'pending',
      page_size: 100,
      max_pages: 20,
    })
    ElMessage.success(`同步完成：新增 ${res.inserted || 0}，更新 ${res.updated || 0}，跳过 ${res.skipped || 0}`)
    page.value = 1
    await loadOrders()
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '同步云端失败')
  } finally {
    syncing.value = false
  }
}

const syncCloudInventory = async () => {
  inventorySyncing.value = true
  try {
    const res = await apiPost<{
      local_rows?: number
      pushed_rows?: number
    }>('/dealer-orders/sync-wechat-batch-summary', {})
    ElMessage.success(`库存同步完成：本地 ${res.local_rows || 0} 行，已推送 ${res.pushed_rows || 0} 行`)
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '同步云端库存失败')
  } finally {
    inventorySyncing.value = false
  }
}

const syncCompletedCloud = async () => {
  completedSyncing.value = true
  try {
    const res = await apiPost<{
      scanned?: number
      pushed?: number
      skipped?: number
      failed?: Array<{ order_no?: string; error?: string }>
    }>('/dealer-orders/sync-completed-cloud', {
      limit: 200,
    })
    const failed = res.failed?.length || 0
    if (failed > 0) {
      ElMessage.warning(`完成状态同步：成功 ${res.pushed || 0}，跳过 ${res.skipped || 0}，失败 ${failed}`)
    } else {
      ElMessage.success(`完成状态同步：扫描 ${res.scanned || 0}，成功 ${res.pushed || 0}，跳过 ${res.skipped || 0}`)
    }
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '同步完成状态失败')
  } finally {
    completedSyncing.value = false
  }
}

const approveOrder = async (row: DealerOrder) => {
  try {
    const note = await ElMessageBox.prompt('审核备注（可选）', '通过订单', {
      inputType: 'textarea',
      inputValue: row.remark || '',
      confirmButtonText: '通过',
      cancelButtonText: '取消',
    })
    const res = await apiPost<{ message?: string; warning?: string }>(`/dealer-orders/${encodeURIComponent(row.order_no)}/approve`, {
      note: note.value || '',
    })
    ElMessage.success(res.warning || res.message || '已通过')
    await loadOrders()
    if (selectedOrderNo.value) await loadPreview(selectedOrderNo.value)
  } catch (err: any) {
    if (err !== 'cancel') ElMessage.error(getApiErrorMessage(err) || '审核失败')
  }
}

const rejectOrder = async (row: DealerOrder) => {
  try {
    const reason = await ElMessageBox.prompt('请输入驳回原因', '驳回订单', {
      inputType: 'textarea',
      confirmButtonText: '驳回',
      cancelButtonText: '取消',
      inputValidator: (value) => (String(value || '').trim() ? true : '驳回原因不能为空'),
    })
    const res = await apiPost<{ message?: string; warning?: string }>(`/dealer-orders/${encodeURIComponent(row.order_no)}/reject`, {
      reason: reason.value,
    })
    ElMessage.success(res.warning || res.message || '已驳回')
    await loadOrders()
  } catch (err: any) {
    if (err !== 'cancel') ElMessage.error(getApiErrorMessage(err) || '驳回失败')
  }
}

// -- convert to contract --
const modelOptions = computed(() => getModelOrderList())

const todayYmd = () => new Date().toISOString().slice(0, 10)
const genContractId = () => {
  const now = new Date()
  const y = now.getFullYear().toString()
  const m = `${now.getMonth() + 1}`.padStart(2, '0')
  const d = `${now.getDate()}`.padStart(2, '0')
  const rnd = Math.floor(Math.random() * 9000 + 1000)
  return `HT${y}${m}${d}${rnd}`
}

const isRushHint = (row: DealerOrder) => {
  const remark = String(row.remark || '').toLowerCase()
  if (remark.includes('急') || remark.includes('加急')) return true
  const delivery = String(row.delivery_date || '').trim()
  if (!delivery) return false
  const days = (new Date(delivery).getTime() - Date.now()) / 86400000
  return days <= 3
}

const convertDialogVisible = ref(false)
const convertSaving = ref(false)
const convertCanUseSpot = ref(true)
const convertSpotBlockReason = ref('')
type ConvertItem = { model: string; qty: number; high: boolean; rowNote: string }
const convertForm = reactive({
  contractNo: '',
  deliveryDate: '',
  customer: '',
  agent: '',
  isRush: false,
  items: [] as ConvertItem[],
  contractNote: '',
  sourceOrderNo: '',
})

const openConvertDialog = (row: DealerOrder) => {
  convertForm.contractNo = genContractId()
  convertForm.deliveryDate = String(row.delivery_date || '').slice(0, 10) || todayYmd()
  convertForm.customer = String(row.customer_name || '').trim()
  convertForm.agent = String(row.contact_name || '').trim()
  convertForm.isRush = isRushHint(row)
  convertForm.contractNote = String(row.review_note || '').trim()
  convertForm.sourceOrderNo = row.order_no
  const items = row.items?.length ? row.items : [row]
  convertForm.items = items.map((item) => ({
    model: String(item.model || '').trim(),
    qty: Math.max(1, Number(item.quantity || 1)),
    high: String(item.model || '').includes('加高') || String(item.remark || '').includes('加高'),
    rowNote: '',
  }))
  convertCanUseSpot.value = true
  convertSpotBlockReason.value = ''
  convertDialogVisible.value = true
}

const getInStockCountByModel = async () => {
  const inventoryRows = await apiGetAll<any>('/inventory/')
  const map = new Map<string, number>()
  for (const row of inventoryRows) {
    const model = String(row['机型'] || '').trim()
    const status = String(row['状态'] || '').trim()
    if (!model || !status.startsWith('库存中')) continue
    map.set(model, (map.get(model) || 0) + 1)
  }
  return map
}

const evaluateSpotAvailability = async (items: ConvertItem[]) => {
  const requiredByModel = new Map<string, number>()
  for (const item of items) {
    const model = String(item.model || '').trim()
    if (!model) continue
    requiredByModel.set(model, (requiredByModel.get(model) || 0) + Number(item.qty || 0))
  }
  const stockByModel = await getInStockCountByModel()
  const blocked: string[] = []
  for (const [model, required] of requiredByModel.entries()) {
    const inStock = Number(stockByModel.get(model) || 0)
    if (inStock <= 0) blocked.push(`${model}(无机台)`)
    else if (inStock < required) blocked.push(`${model}(库存${inStock} < 需求${required})`)
  }
  return { canUseSpot: blocked.length === 0, reason: blocked.length === 0 ? '' : blocked.join('，') }
}

const submitConvert = async (saveMode: 'sandbox' | 'spot') => {
  const validItems = convertForm.items.filter((item) => item.model && item.qty >= 1)
  if (validItems.length === 0) {
    ElMessage.warning('请至少填写 1 条机型明细')
    return
  }
  const invalidModels = validItems.map((item) => item.model).filter((m) => !isModelInDictionary(m))
  if (invalidModels.length > 0) {
    ElMessage.warning(`以下机型不在字典中：${Array.from(new Set(invalidModels)).join('，')}`)
    return
  }
  if (saveMode === 'spot') {
    const spotAvailability = await evaluateSpotAvailability(validItems)
    if (!spotAvailability.canUseSpot) {
      convertCanUseSpot.value = false
      convertSpotBlockReason.value = spotAvailability.reason
      ElMessage.warning(`"使用现货"不可用：${spotAvailability.reason}`)
      return
    }
  }
  convertSaving.value = true
  try {
    const payload = {
      contract_no: convertForm.contractNo.trim(),
      customer_name: convertForm.customer.trim(),
      agent_name: convertForm.agent.trim(),
      delivery_date: convertForm.deliveryDate.trim(),
      save_mode: saveMode,
      is_rush: convertForm.isRush,
      items: validItems,
      contract_note: convertForm.contractNote.trim(),
    }
    const res = await apiPost<{ message?: string; warning?: string; contract_no?: string; rush_created?: number; rush_auto_inserted?: number; save_mode?: string }>(
      `/dealer-orders/${encodeURIComponent(convertForm.sourceOrderNo)}/convert-to-contract`,
      payload,
    )
    const autoInserted = Number(res.rush_auto_inserted || 0)
    const pendingRushCards = Math.max(0, Number(res.rush_created || 0) - autoInserted)
    const rushText = [
      autoInserted > 0 ? `已自动进入沙盘 ${autoInserted} 条` : '',
      pendingRushCards > 0 ? `已生成急单卡 ${pendingRushCards} 张` : '',
    ].filter(Boolean).join('，')
    const modeText = saveMode === 'spot' ? '已按"使用现货"处理' : '已按"进入沙盘"处理'
    ElMessage.success(res.warning || `${res.message || '转合同成功'}，${modeText}${rushText ? `，${rushText}` : ''}`)
    convertDialogVisible.value = false
    await loadOrders()
    if (selectedOrderNo.value) await loadPreview(selectedOrderNo.value)
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '转为合同失败')
  } finally {
    convertSaving.value = false
  }
}

onMounted(loadOrders)
</script>

<style scoped>
.dealer-review-page {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.filters {
  display: flex;
  align-items: center;
  gap: 8px;
}

.keyword {
  max-width: 360px;
}

.status-filter {
  width: 140px;
}

.pager-row {
  display: flex;
  justify-content: flex-end;
}

.danger {
  color: #dc2626;
  font-weight: 700;
}

.detail-grid {
  display: grid;
  grid-template-columns: 96px minmax(0, 1fr);
  gap: 10px 12px;
  align-items: start;
}

.detail-grid span,
.availability span {
  color: var(--color-gray-600);
}

.detail-grid strong {
  color: var(--color-gray-900);
  word-break: break-word;
}

.availability {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.availability div {
  border: 1px solid var(--color-gray-200);
  border-radius: var(--radius-sm);
  padding: 10px;
}

.availability strong {
  display: block;
  margin-top: 4px;
  font-size: 20px;
}

.note-title {
  margin-top: 12px;
  font-weight: 700;
}

.note-box {
  margin-top: 6px;
  padding: 10px;
  min-height: 44px;
  border: 1px solid var(--color-gray-200);
  border-radius: var(--radius-sm);
  background: var(--color-gray-50);
  white-space: pre-wrap;
  word-break: break-word;
}

.drawer-actions {
  display: flex;
  gap: 8px;
  margin-top: 18px;
}

.convert-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.ops-label {
  font-weight: 600;
  margin-bottom: 4px;
}

.form-table {
  margin-bottom: 8px;
}

.save-mode-section {
  margin-top: 16px;
}

.save-mode-hint {
  color: var(--color-gray-500);
  font-size: 13px;
  margin: 4px 0 8px;
}

.save-mode-blocked {
  color: #dc2626;
  font-size: 13px;
  margin-bottom: 8px;
}
</style>
