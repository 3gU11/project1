<template>
  <div class="dealer-review-page">
    <PageHeader title="经销商订单审核">
      <template #actions>
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
        <el-option label="部分配货" value="partial_allocated" />
        <el-option label="已配货" value="allocated" />
        <el-option label="已驳回" value="rejected" />
        <el-option label="已取消" value="cancelled" />
      </el-select>
      <el-button @click="loadOrders">查询</el-button>
    </div>

    <el-table
      v-loading="loading"
      :data="orders"
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
      <el-table-column prop="line_count" label="行数" width="70" align="right" />
      <el-table-column prop="quantity" label="总数量" width="90" align="right" />
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
      <el-table-column label="操作" width="270" fixed="right">
        <template #default="{ row }">
          <el-button size="small" :disabled="row.status !== 'pending'" @click.stop="approveOrder(row)">通过</el-button>
          <el-button size="small" type="danger" :disabled="!canReject(row)" @click.stop="rejectOrder(row)">驳回</el-button>
          <el-button size="small" type="success" :disabled="!canAllocate(row)" @click.stop="markAllocated(row)">已配货</el-button>
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
          <el-button type="success" :disabled="!canAllocate(selectedOrder)" @click="markAllocated(selectedOrder)">标记已配货</el-button>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import PageHeader from '../components/PageHeader.vue'
import { apiGet, apiPost, getApiErrorMessage } from '../utils/request'

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

const statusMeta = (status: string) => {
  const map: Record<string, { text: string; type: 'primary' | 'success' | 'warning' | 'danger' | 'info' }> = {
    pending: { text: '待审核', type: 'warning' },
    approved: { text: '已通过', type: 'primary' },
    partial_allocated: { text: '部分配货', type: 'success' },
    allocated: { text: '已配货', type: 'success' },
    rejected: { text: '已驳回', type: 'danger' },
    cancelled: { text: '已取消', type: 'info' },
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
const canAllocate = (row: DealerOrder) => ['pending', 'approved', 'partial_allocated'].includes(row.status)

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
    const res = await apiPost<{ message?: string }>(`/dealer-orders/${encodeURIComponent(row.order_no)}/reject`, {
      reason: reason.value,
    })
    ElMessage.success(res.message || '已驳回')
    await loadOrders()
  } catch (err: any) {
    if (err !== 'cancel') ElMessage.error(getApiErrorMessage(err) || '驳回失败')
  }
}

const markAllocated = async (row: DealerOrder) => {
  try {
    await ElMessageBox.confirm('确认该经销商订单已经在 V7 完成配货？确认后小程序会读取到 allocated 状态。', '标记已配货', {
      type: 'warning',
    })
    const res = await apiPost<{ message?: string }>(`/dealer-orders/${encodeURIComponent(row.order_no)}/mark-allocated`, {
      allocated_qty: Math.max(1, Number(row.quantity || 1) - Number(row.allocated_qty || 0)),
    })
    ElMessage.success(res.message || '已标记配货')
    await loadOrders()
    if (selectedOrderNo.value) await loadPreview(selectedOrderNo.value)
  } catch (err: any) {
    if (err !== 'cancel') ElMessage.error(getApiErrorMessage(err) || '标记失败')
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
</style>
