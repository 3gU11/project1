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

    <div v-if="cloudSyncStatus.pending || cloudSyncStatus.failed" class="cloud-sync-strip">
      <span>Cloud pending: <strong>{{ cloudSyncStatus.pending }}</strong></span>
      <span>Failed: <strong :class="{ danger: cloudSyncStatus.failed > 0 }">{{ cloudSyncStatus.failed }}</strong></span>
      <span v-if="cloudSyncStatus.recent_failed?.length" class="last-error">
        <span :title="cloudSyncLastError">Last failed: {{ cloudSyncLastSummary }}</span>
      </span>
      <el-button v-if="cloudSyncStatus.failed > 0" size="small" :loading="retryingCloudSync" @click="retryCloudSync">Retry</el-button>
    </div>

    <div class="filters">
      <el-input
        v-model="filters.keyword"
        clearable
        placeholder="搜索订单号 / 经销商 / 联系人 / 机型"
        class="keyword"
        @keyup.enter="loadOrders"
        @clear="loadOrders"
      />
      <el-radio-group v-model="filters.status" class="status-tabs" @change="onStatusChange">
        <el-radio-button label="">全部订单</el-radio-button>
        <el-radio-button label="todo">待审核</el-radio-button>
        <el-radio-button label="approved">已通过</el-radio-button>
        <el-radio-button label="contracted">已转合同</el-radio-button>
        <el-radio-button label="partial_allocated">部分配货</el-radio-button>
        <el-radio-button label="allocated">已配货</el-radio-button>
        <el-radio-button label="rejected">已驳回</el-radio-button>
        <el-radio-button label="cancelled">已取消</el-radio-button>
        <el-radio-button label="completed">已完成</el-radio-button>
      </el-radio-group>
      <el-button @click="loadOrders">查询</el-button>
    </div>

    <div class="todo-summary">
      <span>待办总数 <strong>{{ todoStats.total }}</strong></span>
      <span>新备注审核中 <strong class="warning-count">{{ todoStats.factoryPending }}</strong></span>
      <span>待审核 <strong>{{ todoStats.pending }}</strong></span>
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
      <el-table-column prop="status" label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="statusMeta(row).type">{{ statusMeta(row).text }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="regional_manager_name" label="经销商" width="90" show-overflow-tooltip />
      <el-table-column prop="customer_name" label="客户名" min-width="390" show-overflow-tooltip />
      <el-table-column prop="model" label="机型明细" min-width="150" show-overflow-tooltip />
      <el-table-column prop="batch_no" label="批次/来源" width="120" show-overflow-tooltip>
        <template #default="{ row }">{{ displayBatch(row.batch_no, row.inventory_type) }}</template>
      </el-table-column>
      <el-table-column prop="quantity" label="数量" width="70" align="center">
        <template #default="{ row }">
          <el-tooltip content="点击局部刷新该订单数据" placement="top" :show-after="500">
            <span
              class="qty-highlight"
              :class="{ 'is-refreshing': refreshingOrders[row.order_no] }"
              @click.stop="refreshSingleOrder(row.order_no)"
            >
              <el-icon v-if="refreshingOrders[row.order_no]" class="is-loading"><Loading /></el-icon>
              <template v-else>{{ row.quantity }}</template>
            </span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column prop="remark" label="原备注" min-width="120" show-overflow-tooltip />
      <el-table-column prop="extra_remark" label="附加备注" min-width="120" show-overflow-tooltip />
      <el-table-column prop="ERMQ" label="需改数量" width="80" align="center" />
      <el-table-column label="操作" width="260" align="center" fixed="right">
        <template #default="{ row }">
          <div class="op-buttons">
            <el-button size="small" type="success" :disabled="!canApprove(row)" @click.stop="approveOrder(row)">通过</el-button>
            <el-button size="small" type="danger" :disabled="!canReject(row)" @click.stop="rejectOrder(row)">驳回</el-button>
            <el-button size="small" type="warning" :disabled="!canConvertDealerOrder(row)" @click.stop="openConvertDialog(row._order || row)">
              转合同
            </el-button>
          </div>
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
          <span>当前状态</span><strong>{{ statusMeta(selectedOrder).text }}</strong>
          <span>总数量</span><strong>{{ selectedOrder.quantity }}</strong>
          <span>已配货</span><strong>{{ selectedOrder.allocated_qty ?? 0 }}</strong>
          <span v-if="selectedOrder.contract_no">合同号</span><strong v-if="selectedOrder.contract_no">{{ selectedOrder.contract_no }}</strong>
        </div>

        <el-divider />
        <el-table :data="detailItems" border size="small">
          <el-table-column prop="line_no" label="行号" width="70" align="right" />
          <el-table-column prop="model" label="机型" min-width="150" show-overflow-tooltip />
          <el-table-column prop="batch_no" label="批次/来源" min-width="130" show-overflow-tooltip>
            <template #default="{ row }">{{ displayBatch(row.batch_no, row.inventory_type) }}</template>
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
          <el-table-column prop="status" label="状态" width="120">
            <template #default="{ row }">
              <el-tag :type="statusMeta(row).type">{{ statusMeta(row).text }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="remark" label="原备注" min-width="130" show-overflow-tooltip />
          <el-table-column prop="extra_remark" label="附加备注" min-width="130" show-overflow-tooltip />
          <el-table-column prop="ERMQ" label="需改数量" width="100" align="right" />
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
        <div class="note-title">附加备注</div>
        <div class="note-box">{{ selectedOrder.extra_remark || '-' }}</div>
        <div class="note-title">审核备注</div>
        <div class="note-box">{{ selectedOrder.review_note || '-' }}</div>

        <div class="drawer-actions">
          <el-button :disabled="!canApprove(selectedOrder)" @click="approveOrder(selectedOrder)">通过</el-button>
          <el-button type="danger" :disabled="!canReject(selectedOrder)" @click="rejectOrder(selectedOrder)">驳回</el-button>
          <el-button type="warning" :disabled="!canConvertDealerOrder(selectedOrder)" @click="openConvertDialog(selectedOrder)">转合同</el-button>
        </div>
      </template>
    </el-drawer>

    <el-dialog
      v-model="convertDialogVisible"
      title="经销商订单转合同"
      width="860px"
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
        <el-table-column label="原备注" min-width="120">
          <template #default="scope">
            <el-input v-model="scope.row.remark" placeholder="原备注" />
          </template>
        </el-table-column>
        <el-table-column label="附加备注" min-width="120">
          <template #default="scope">
            <el-input v-model="scope.row.extraRemark" placeholder="附加备注" />
          </template>
        </el-table-column>
        <el-table-column label="需改数量" width="110">
          <template #default="scope">
            <el-input-number v-model="scope.row.ermq" :min="0" :controls="false" style="width:100%" />
          </template>
        </el-table-column>
      </el-table>

      <el-divider />
      <div class="ops-label">合同总备注</div>
      <el-input v-model="convertForm.contractNote" placeholder="可选" />

      <el-divider />
      <div class="ops-label">📎 附加合同文件 (可选)</div>
      <el-upload
        ref="convertUploadRef"
        :auto-upload="false"
        :show-file-list="true"
        multiple
        :on-change="onConvertFileChange"
        :on-remove="onConvertFileRemove"
      >
        <el-button>选择文件</el-button>
      </el-upload>

      <div class="save-mode-section">
        <div class="ops-label">保存方式</div>
        <div class="save-mode-hint">
          {{ isRushActive ? '进入生产看板（参与急单排产）' : '进入沙盘（参与老板计划排产）' }}或使用现货（直接置为已规划）。
        </div>
        <div v-if="!convertCanUseSpot" class="save-mode-blocked">当前"使用现货"不可用：{{ convertSpotBlockReason }}</div>
      </div>

      <template #footer>
        <el-button @click="convertDialogVisible = false">取消</el-button>
        <el-button type="warning" :disabled="!convertCanUseSpot" :loading="convertSaving" @click="submitConvert('spot')">使用现货</el-button>
        <el-button type="primary" :loading="convertSaving" @click="submitConvert('sandbox')">
          {{ isRushActive ? '进入生产看板' : '进入沙盘' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import PageHeader from '../components/PageHeader.vue'
import { apiGet, apiGetAll, apiPost, getApiErrorMessage } from '../utils/request'
import { getModelOrderList, isModelInDictionary } from '../utils/modelOrder'
import { hasText, isPositiveInteger } from '../utils/formRules'

type DealerOrder = {
  id: number
  order_no: string
  line_no?: number
  line_count?: number
  dealer_openid?: string
  dealer_name?: string
  dealer_phone?: string
  regional_manager_name?: string
  customer_name?: string
  contact_name?: string
  contact_phone?: string
  model: string
  batch_no?: string
  expected_inbound_time?: string
  inventory_type?: string
  quantity: number
  approved_qty?: number
  allocated_qty?: number
  delivery_date?: string
  contract_no?: string
  status: string
  remark?: string
  extra_remark?: string
  factory_remark?: string
  ERMQ?: number
  factory_pending?: number
  review_note?: string
  regional_review_note?: string
  reviewed_at?: string
  reviewed_by?: string
  created_at?: string
  updated_at?: string
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

type CloudSyncStatus = {
  pending: number
  failed: number
  recent_failed: Array<{
    id?: number
    event_type?: string
    biz_key?: string
    last_error?: string
    retry_count?: number
    next_retry_at?: string
    updated_at?: string
  }>
}

const loading = ref(false)
const syncing = ref(false)
const inventorySyncing = ref(false)
const completedSyncing = ref(false)
const retryingCloudSync = ref(false)
const cloudSyncStatus = ref<CloudSyncStatus>({ pending: 0, failed: 0, recent_failed: [] })
const orders = ref<DealerOrder[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(50)
const selectedOrderNo = ref('')
const drawerOpen = ref(false)
const preview = ref<PreviewResponse | null>(null)
const filters = reactive({
  keyword: '',
  status: '',
})
const todoStats = reactive({
  total: 0,
  factoryPending: 0,
  pending: 0,
})

const cloudSyncLastError = computed(() => {
  const item = cloudSyncStatus.value.recent_failed?.[0]
  if (!item) return ''
  return [item.biz_key, item.last_error].filter(Boolean).join(' ')
})

const cloudSyncLastSummary = computed(() => {
  const item = cloudSyncStatus.value.recent_failed?.[0]
  if (!item) return '-'
  const orderNo = String(item.biz_key || '').trim()
  const eventType = String(item.event_type || '').replace(/^dealer_order_/, '')
  return [orderNo, eventType || 'sync'].filter(Boolean).join(' / ')
})

const selectedOrder = computed(() => orders.value.find((row) => row.order_no === selectedOrderNo.value) || null)
const detailItems = computed(() => preview.value?.items || selectedOrder.value?.items || (selectedOrder.value ? [selectedOrder.value] : []))
const statusRank = (status: string) => ({
  pending: 0,
  approved: 1,
  contracted: 2,
  partial_allocated: 3,
  allocated: 4,
  rejected: 5,
  cancelled: 6,
  complete: 7,
  completed: 7,
}[status] ?? 9)

const rowPriority = (row: DealerOrder) => {
  const status = String(row.status || '')
  if (Number(row.factory_pending || 0) === 1 && !['complete', 'completed'].includes(status)) return -1
  return statusRank(status)
}

const tableRows = computed<DealerOrderTableRow[]>(() => {
  const rows = orders.value.flatMap((order) => {
    const items = order.items?.length ? order.items : [order]
    return items.map((item, index) => ({
      ...order,
      ...item,
      remark: item.remark || order.remark || '',
      extra_remark: item.extra_remark || order.extra_remark || '',
      factory_remark: item.factory_remark || item.extra_remark || order.factory_remark || order.extra_remark || '',
      ERMQ: Number(item.ERMQ ?? order.ERMQ ?? 0),
      factory_pending: Number(item.factory_pending ?? order.factory_pending ?? 0),
      review_note: item.review_note || order.review_note || '',
      regional_review_note: item.regional_review_note || order.regional_review_note || '',
      items: order.items?.length ? order.items : [order],
      line_count: order.line_count,
      _order: order,
      _row_key: `${order.order_no}-${item.line_no || index + 1}`,
    }))
  })
  rows.sort((a, b) => {
    const priorityDiff = rowPriority(a) - rowPriority(b)
    if (priorityDiff !== 0) return priorityDiff
    const bTime = String(b.updated_at || b.created_at || '')
    const aTime = String(a.updated_at || a.created_at || '')
    if (bTime !== aTime) return bTime.localeCompare(aTime)
    return String(b.order_no || '').localeCompare(String(a.order_no || ''))
  })
  return rows
})

const statusMeta = (rowOrStatus: DealerOrder | string) => {
  const status = typeof rowOrStatus === 'string' ? rowOrStatus : rowOrStatus.status
  const factoryPending = typeof rowOrStatus === 'string' ? 0 : Number(rowOrStatus.factory_pending || 0)
  if (factoryPending === 1 && !['complete', 'completed'].includes(status)) return { text: '新备注审核中', type: 'warning' as const }
  const map: Record<string, { text: string; type: 'primary' | 'success' | 'warning' | 'danger' | 'info' }> = {
    pending: { text: '待审核', type: 'warning' },
    approved: { text: '已通过', type: 'primary' },
    contracted: { text: '已转合同', type: 'success' },
    partial_allocated: { text: '部分配货', type: 'success' },
    allocated: { text: '已配货', type: 'success' },
    rejected: { text: '已驳回', type: 'danger' },
    cancelled: { text: '已取消', type: 'info' },
    complete: { text: '已完成', type: 'success' },
    completed: { text: '已完成', type: 'success' },
  }
  return map[status] || { text: status || '-', type: 'info' }
}

const displayBatch = (batchNo?: string, inventoryType?: string) => {
  if (String(inventoryType || '').trim().toLowerCase() === 'finished') return '库存中'
  if (!batchNo) return '-'
  if (batchNo === 'FINISHED-STOCK') return '库存中'
  return batchNo
}

const hasInsufficientItem = (row: DealerOrder) => {
  const items = row.items?.length ? row.items : [row]
  return items.some((item) => Number(item.available_qty || 0) < Number(item.quantity || 0) - Number(item.allocated_qty || 0))
}

const hasFactoryRemark = (row: DealerOrder) => {
  if (String(row.factory_remark || row.extra_remark || '').trim()) return true
  const items = row.items?.length ? row.items : []
  return items.some((item) => String(item.factory_remark || item.extra_remark || '').trim())
}

const isFactoryPending = (row: DealerOrder) => Number(row.factory_pending || 0) === 1 && !['complete', 'completed'].includes(row.status)
const canApprove = (row: DealerOrder) => isFactoryPending(row) || row.status === 'pending'
const canReject = (row: DealerOrder) => (isFactoryPending(row) ? hasFactoryRemark(row) : ['pending', 'approved'].includes(row.status))
const canConvertDealerOrder = (row: DealerOrder) => ['pending', 'approved'].includes(String(row.status || '').trim()) && !isFactoryPending(row)

const modelOptions = computed(() => getModelOrderList())
const router = useRouter()
const isRushActive = computed(() => convertForm.isRush)
type ConvertItem = { model: string; qty: number; high: boolean; rowNote: string; remark: string; extraRemark: string; ermq: number }
const convertDialogVisible = ref(false)
const convertSaving = ref(false)
const convertCanUseSpot = ref(true)
const convertSpotBlockReason = ref('')
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

const convertPickedFiles = ref<File[]>([])
const convertUploadRef = ref<any>(null)

const onConvertFileChange = (uploadFile: any) => {
  const raw = uploadFile.raw as File | undefined
  if (!raw) return
  convertPickedFiles.value.push(raw)
}

const onConvertFileRemove = (uploadFile: any) => {
  const raw = uploadFile.raw as File | undefined
  if (!raw) return
  convertPickedFiles.value = convertPickedFiles.value.filter((f) => !(f.name === raw.name && f.size === raw.size))
}

const todayYmd = () => new Date().toISOString().slice(0, 10)
const fetchNextContractId = async () => {
  const res = await apiGet<{ contract_no: string }>('/planning/contracts/next-id')
  return String(res.contract_no || '').trim()
}

const isRushHint = (order: DealerOrder) => {
  const remark = String(order.remark || '').toLowerCase()
  if (remark.includes('急') || remark.includes('加急')) return true
  const delivery = String(order.delivery_date || '').trim()
  if (!delivery) return false
  const days = (new Date(delivery).getTime() - Date.now()) / 86400000
  return days <= 3
}

const normalizeDealerOrderItems = (order: DealerOrder) => {
  const source = order.items?.length ? order.items : [order]
  return source
    .map((item) => {
      const model = String(item.model || '').trim()
      const qty = Math.max(1, Number(item.quantity || 1))
      const remark = String(item.remark || '').trim()
      const extraRemark = String(item.factory_remark || item.extra_remark || '').trim()
      const ermq = Number(item.ERMQ || 0)
      const high = model.includes('加高') || remark.includes('加高') || extraRemark.includes('加高')
      const rowNote = [
        remark ? `[备注]${remark}` : '',
        extraRemark ? `[附加]${extraRemark}` : '',
        ermq > 0 ? `[改数]${ermq}` : '',
      ].filter(Boolean).join(' ')
      return { model, qty, high, rowNote, remark, extraRemark, ermq }
    })
    .filter((item) => item.model)
}

const openConvertDialog = async (order: DealerOrder) => {
  if (!canConvertDealerOrder(order)) {
    ElMessage.warning('只有待审核或已通过的经销商订单可以转合同')
    return
  }
  const rows = normalizeDealerOrderItems(order)
  if (rows.length === 0) {
    ElMessage.warning('该经销商订单没有可转合同的机型明细')
    return
  }
  convertForm.contractNo = ''
  convertForm.deliveryDate = String(order.delivery_date || '').slice(0, 10) || todayYmd()
  convertForm.customer = String(order.customer_name || '').trim()
  convertForm.agent = String(order.contact_name || '').trim()
  convertForm.isRush = isRushHint(order)
  convertForm.items = rows
  convertForm.contractNote = String(order.review_note || order.regional_review_note || '').trim()
  convertForm.sourceOrderNo = String(order.order_no || '').trim()
  convertCanUseSpot.value = true
  convertSpotBlockReason.value = ''
  try {
    convertForm.contractNo = await fetchNextContractId()
  } catch (err) {
    ElMessage.error(getApiErrorMessage(err) || '生成合同号失败')
    return
  }
  
  // 重置上传的文件
  convertPickedFiles.value = []
  convertUploadRef.value?.clearFiles()

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

const evaluateSpotModeAvailability = async (rows: Array<{ model: string; qty: number }>) => {
  const requiredByModel = new Map<string, number>()
  for (const row of rows) {
    const model = String(row.model || '').trim()
    if (!model) continue
    requiredByModel.set(model, (requiredByModel.get(model) || 0) + Number(row.qty || 0))
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

const loadPreview = async (orderNo: string) => {
  preview.value = await apiGet<PreviewResponse>(`/dealer-orders/${encodeURIComponent(orderNo)}/preview`)
}

const loadTodoStats = async () => {
  try {
    const res = await apiGet<{ pending: number; factory_pending: number; total: number }>('/dealer-orders/pending-count')
    const changed = todoStats.total !== (res.total || 0) ||
                    todoStats.factoryPending !== (res.factory_pending || 0) ||
                    todoStats.pending !== (res.pending || 0)
    todoStats.total = res.total || 0
    todoStats.factoryPending = res.factory_pending || 0
    todoStats.pending = res.pending || 0
    if (changed) {
      window.dispatchEvent(new CustomEvent('dealer-orders-updated', { detail: res }))
    }
  } catch {
    todoStats.total = 0
    todoStats.factoryPending = 0
    todoStats.pending = 0
  }
}

const loadOrders = async (silent: boolean | any = false) => {
  const isSilent = silent === true
  if (!isSilent) {
    loading.value = true
  }
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
    if (!selectedOrderNo.value && orders.value.length > 0) {
      selectedOrderNo.value = orders.value[0].order_no
      try {
        await loadPreview(selectedOrderNo.value)
      } catch {
        preview.value = null
      }
    }
    void loadTodoStats()
  } finally {
    if (!isSilent) {
      loading.value = false
    }
  }
}

const refreshingOrders = ref<Record<string, boolean>>({})

const refreshSingleOrder = async (orderNo: string) => {
  if (!orderNo || refreshingOrders.value[orderNo]) return
  refreshingOrders.value[orderNo] = true
  try {
    const res = await apiGet<OrderListResponse>('/dealer-orders/', {
      params: {
        keyword: orderNo,
        page: 1,
        page_size: 1,
      },
    })
    const updatedRows = res.data || []
    if (updatedRows.length > 0) {
      const idx = orders.value.findIndex((o) => o.order_no === orderNo)
      if (idx !== -1) {
        orders.value[idx] = updatedRows[0]
      }
    }
  } catch (err: any) {
    ElMessage.error('刷新订单失败: ' + (getApiErrorMessage(err) || err.message))
  } finally {
    refreshingOrders.value[orderNo] = false
  }
}

const loadCloudSyncStatus = async () => {
  try {
    cloudSyncStatus.value = await apiGet<CloudSyncStatus>('/dealer-orders/cloud-sync-status')
  } catch {
    cloudSyncStatus.value = { pending: 0, failed: 0, recent_failed: [] }
  }
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

const onStatusChange = () => {
  page.value = 1
  selectedOrderNo.value = ''
  preview.value = null
  loadOrders()
}

const retryCloudSync = async () => {
  retryingCloudSync.value = true
  try {
    const res = await apiPost<{ queued?: number; processed?: number; synced?: number }>('/dealer-orders/cloud-sync-retry', {})
    ElMessage.success(`Retry queued ${res.queued || 0}, processed ${res.processed || 0}, synced ${res.synced || 0}`)
    await loadCloudSyncStatus()
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || 'Cloud sync retry failed')
  } finally {
    retryingCloudSync.value = false
  }
}

const syncCloudOrders = async () => {
  syncing.value = true
  ElMessage.info('正在同步云端订单，请稍候…')
  try {
    const res = await apiPost<{
      inserted?: number
      updated?: number
      skipped?: number
      factory_pending_orders?: number
      pruned_cloud_deleted_orders?: number
    }>('/dealer-orders/sync-cloud', {
      status: 'all',
      page_size: 100,
      max_pages: 20,
    }, { timeout: 120_000 })
    const prunedText = Number(res.pruned_cloud_deleted_orders || 0) > 0 ? `，清理 ${res.pruned_cloud_deleted_orders}` : ''
    ElMessage.success(`同步完成：新增 ${res.inserted || 0}，更新 ${res.updated || 0}，跳过 ${res.skipped || 0}${prunedText}`)
    if (Number(res.factory_pending_orders || 0) > 0) filters.status = 'todo'
    page.value = 1
    selectedOrderNo.value = ''
    window.dispatchEvent(new CustomEvent('dealer-orders-updated'))
    await loadCloudSyncStatus()
    await loadOrders()
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '同步云端失败')
  } finally {
    syncing.value = false
  }
}

const syncCloudInventory = async () => {
  inventorySyncing.value = true
  ElMessage.info('正在同步库存到云端，请稍候…')
  try {
    const res = await apiPost<{ local_rows?: number; pushed_rows?: number }>('/dealer-orders/sync-wechat-batch-summary', {}, { timeout: 120_000 })
    ElMessage.success(`库存同步完成：本地 ${res.local_rows || 0} 行，已推送 ${res.pushed_rows || 0} 行`)
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '同步云端库存失败')
  } finally {
    inventorySyncing.value = false
  }
}

const syncCompletedCloud = async () => {
  completedSyncing.value = true
  ElMessage.info('正在同步完成状态到云端，请稍候…')
  try {
    const res = await apiPost<{
      scanned?: number
      pushed?: number
      skipped?: number
      failed?: Array<{ order_no?: string; error?: string }>
    }>('/dealer-orders/sync-completed-cloud', { limit: 200 }, { timeout: 120_000 })
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
    const factoryPending = isFactoryPending(row)
    const note = await ElMessageBox.prompt(factoryPending ? '复审备注（可选）' : '审核备注（可选）', factoryPending ? '新备注复审通过' : '通过订单', {
      inputType: 'textarea',
      inputValue: row.remark || '',
      confirmButtonText: '通过',
      cancelButtonText: '取消',
    })
    const endpoint = factoryPending ? 'extra-review/approve' : 'approve'
    const res = await apiPost<{ message?: string; warning?: string }>(`/dealer-orders/${encodeURIComponent(row.order_no)}/${endpoint}`, {
      note: note.value || '',
    })
    ElMessage.success(res.warning || res.message || (factoryPending ? '新备注复审通过' : '已通过'))
    window.dispatchEvent(new CustomEvent('dealer-orders-updated'))
    await loadOrders()
    if (selectedOrderNo.value) {
      try {
        await loadPreview(selectedOrderNo.value)
      } catch {
        preview.value = null
      }
    }
  } catch (err: any) {
    if (err !== 'cancel') ElMessage.error(getApiErrorMessage(err) || '操作失败')
  }
}

const rejectOrder = async (row: DealerOrder) => {
  try {
    const factoryPending = isFactoryPending(row)
    if (factoryPending) {
      await ElMessageBox.confirm(
        '驳回新备注复审后，系统会同步取消该经销商订单已绑定的合同和销售订单，并释放未出库的配货占用。已出库记录不会自动回滚。',
        '确认驳回并同步取消',
        {
          type: 'warning',
          confirmButtonText: '继续驳回',
          cancelButtonText: '取消',
        },
      )
    }
    const reason = await ElMessageBox.prompt(factoryPending ? '请输入新备注复审驳回原因' : '请输入驳回原因', factoryPending ? '新备注复审驳回' : '驳回订单', {
      inputType: 'textarea',
      confirmButtonText: '驳回',
      cancelButtonText: '取消',
      inputValidator: (value) => (String(value || '').trim() ? true : '驳回原因不能为空'),
    })
    const endpoint = factoryPending ? 'extra-review/reject' : 'reject'
    const res = await apiPost<{ message?: string; warning?: string }>(`/dealer-orders/${encodeURIComponent(row.order_no)}/${endpoint}`, {
      reason: reason.value,
    })
    ElMessage.success(res.warning || res.message || (factoryPending ? '新备注复审已驳回' : '已驳回'))
    window.dispatchEvent(new CustomEvent('dealer-orders-updated'))
    await loadOrders()
    if (selectedOrderNo.value) {
      try {
        await loadPreview(selectedOrderNo.value)
      } catch {
        preview.value = null
      }
    }
  } catch (err: any) {
    if (err !== 'cancel') ElMessage.error(getApiErrorMessage(err) || '操作失败')
  }
}

type MessageResponse = { message?: string; rush_created?: number; rush_auto_inserted?: number; warning?: string; contract_no?: string }

const submitConvert = async (saveMode: 'sandbox' | 'spot') => {
  if (!hasText(convertForm.contractNo) || !hasText(convertForm.customer) || !hasText(convertForm.deliveryDate)) {
    ElMessage.warning('请先完整填写合同号、客户名、要求交期')
    return
  }
  const validItems = convertForm.items
    .map((item) => ({
      ...item,
      rowNote: [
        item.remark?.trim() ? `[备注]${item.remark.trim()}` : '',
        item.extraRemark?.trim() ? `[附加]${item.extraRemark.trim()}` : '',
        item.ermq > 0 ? `[改数]${item.ermq}` : '',
      ].filter(Boolean).join(' '),
    }))
    .filter((item) => hasText(item.model) && isPositiveInteger(item.qty))
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
    try {
      const spotAvailability = await evaluateSpotModeAvailability(validItems)
      if (!spotAvailability.canUseSpot) {
        convertCanUseSpot.value = false
        convertSpotBlockReason.value = spotAvailability.reason
        ElMessage.warning(`"使用现货"不可用：${spotAvailability.reason}`)
        return
      }
    } catch (err: any) {
      ElMessage.error(getApiErrorMessage(err) || '校验现货可用机台失败')
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
    const res = await apiPost<MessageResponse>(`/dealer-orders/${encodeURIComponent(convertForm.sourceOrderNo)}/convert-to-contract`, payload)
    
    // 上传附件（如果有选中文件）
    if (convertPickedFiles.value.length > 0) {
      const contractNoStr = res.contract_no || convertForm.contractNo || ''
      const contractIds = contractNoStr.split(/[、,]/).map((s) => s.trim()).filter(Boolean)
      for (const cid of contractIds) {
        for (const f of convertPickedFiles.value) {
          const fd = new FormData()
          fd.append('file', f)
          try {
            await apiPost(`/planning/contract/${encodeURIComponent(cid)}/files`, fd, {
              params: { customer_name: convertForm.customer.trim(), uploader_name: 'Web' },
              headers: { 'Content-Type': 'multipart/form-data' },
            })
          } catch (uploadErr: any) {
            console.error(`Failed to upload attachment ${f.name} to contract ${cid}:`, uploadErr)
            ElMessage.warning(`合同 ${cid} 附件 ${f.name} 上传失败，请稍后在合同管理中重新上传`)
          }
        }
      }
    }

    const autoInserted = Number(res.rush_auto_inserted || 0)
    const pendingRushCards = Math.max(0, Number(res.rush_created || 0) - autoInserted)
    const rushText = [
      autoInserted > 0 ? `已自动进入沙盘 ${autoInserted} 条` : '',
      pendingRushCards > 0 ? `已生成急单卡 ${pendingRushCards} 张` : '',
    ].filter(Boolean).join('，')
    const modeText = saveMode === 'spot'
      ? '已按“使用现货”处理（合同状态：已规划）'
      : (convertForm.isRush ? '已按“进入生产看板”处理（合同状态：待规划）' : '已按“进入沙盘”处理（合同状态：待规划）')
    ElMessage.success(res.warning || `${res.message || '转合同成功'}，${modeText}${rushText ? `，${rushText}` : ''}`)
    convertDialogVisible.value = false
    window.dispatchEvent(new CustomEvent('dealer-orders-updated'))
    await loadOrders()
    if (saveMode === 'sandbox') {
      if (convertForm.isRush) {
        router.push('/production-kanban')
      } else {
        router.push('/prediction-sandbox')
      }
    } else if (saveMode === 'spot') {
      router.push({ path: '/sales-orders', query: { tab: 'import' } })
    }
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '经销商订单转合同失败')
  } finally {
    convertSaving.value = false
  }
}

let pollTimer: any = null

onMounted(async () => {
  await loadTodoStats()
  if (todoStats.total > 0) {
    filters.status = 'todo'
  } else {
    try {
      const res = await apiGet<OrderListResponse>('/dealer-orders/', {
        params: {
          status: 'approved',
          page: 1,
          page_size: 1,
        },
      })
      if (Number(res.total || 0) > 0) {
        filters.status = 'approved'
      } else {
        filters.status = ''
      }
    } catch {
      filters.status = ''
    }
  }
  loadOrders()
  loadCloudSyncStatus()
  
  // 每 5 秒后台无感静默同步一次数据库数据
  pollTimer = setInterval(() => {
    if (!loading.value) {
      loadOrders(true)
    }
  }, 5000)
})

onUnmounted(() => {
  if (pollTimer) {
    clearInterval(pollTimer)
  }
})
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

.status-tabs {
  flex: 1;
  min-width: 520px;
}

.cloud-sync-strip,
.todo-summary {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 36px;
  padding: 8px 10px;
  border: 1px solid var(--color-gray-200);
  border-radius: var(--radius-sm);
  background: var(--color-gray-50);
  color: var(--color-gray-700);
  font-size: 13px;
}

.todo-summary {
  gap: 16px;
  background: #fffbeb;
  color: var(--color-gray-800);
}

.todo-summary strong {
  margin-left: 4px;
  font-size: 16px;
}

.warning-count {
  color: #d97706;
}

.last-error {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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
  grid-template-columns: 1fr 1fr;
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

.qty-highlight {
  font-weight: 700;
  color: #2563eb;
  background-color: #eff6ff;
  padding: 2px 8px;
  border-radius: 4px;
  display: inline-block;
  cursor: pointer;
  transition: all 0.2s ease;
}

.qty-highlight:hover {
  background-color: #dbeafe;
  transform: scale(1.05);
}

.qty-highlight.is-refreshing {
  cursor: not-allowed;
  opacity: 0.7;
}

.op-buttons {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 6px;
  flex-wrap: nowrap;
}
</style>
