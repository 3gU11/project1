<template>
  <div class="sales-page">
    <PageHeader title="📝 销售订单管理" />

    <div class="tabs-row">
      <button type="button" class="tab-btn" :class="{ active: activeTab === 'manual' }" @click="activeTab = 'manual'">➕ 手动下单</button>
      <button type="button" class="tab-btn" :class="{ active: activeTab === 'import' }" @click="activeTab = 'import'">📥 导入已规划合同</button>
      <button type="button" class="tab-btn" :class="{ active: activeTab === 'manage' }" @click="activeTab = 'manage'">📋 订单查询与管理</button>
    </div>
    <el-alert
      v-if="loadError"
      class="load-error"
      type="error"
      :closable="false"
      :title="loadError"
      show-icon
    >
      <template #default>
        <el-button size="small" @click="retryFetch">重试</el-button>
      </template>
    </el-alert>
    <PageSkeleton v-if="showInitialSkeleton" :blocks="9" min-height="320px" />

    <template v-else-if="activeTab === 'manual'">
      <div class="section-title">1. 填写订单详情</div>
      <el-row :gutter="10">
        <el-col :span="12">
          <div class="field-label">客户信息 (Customer)</div>
          <el-input v-model="manualForm.customer" />
        </el-col>
        <el-col :span="12">
          <div class="field-label">代理商 (Agent)</div>
          <el-input v-model="manualForm.agent" />
        </el-col>
      </el-row>

      <div class="section-title">2. 录入机型</div>
      <el-table :data="manualRows" border stripe size="small">
        <el-table-column label="#" width="40">
          <template #default="scope">{{ scope.$index + 1 }}</template>
        </el-table-column>
        <el-table-column label="机型">
          <template #default="scope">
            <el-select v-model="scope.row.model" filterable placeholder="请选择机型" style="width: 100%">
              <el-option v-for="m in availableModels" :key="m" :label="m" :value="m" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="数量" width="180">
          <template #default="scope">
            <el-input-number v-model="scope.row.qty" :min="1" controls-position="right" />
          </template>
        </el-table-column>
        <el-table-column label="加高?" width="120">
          <template #default="scope">
            <el-checkbox v-model="scope.row.high" />
          </template>
        </el-table-column>
        <el-table-column label="单行备注">
          <template #default="scope">
            <el-input v-model="scope.row.rowNote" />
          </template>
        </el-table-column>
      </el-table>

      <div class="row-actions">
        <el-button link type="primary" @click="addManualRow">+ 增加一行</el-button>
      </div>

      <el-divider />
      <div class="field-label">订单总备注</div>
      <el-input v-model="manualForm.note" />

      <el-row :gutter="10" style="margin-top: 8px">
        <el-col :span="18">
          <div class="field-label">发货时间 (选填)</div>
          <el-date-picker v-model="manualForm.deliveryDate" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
        </el-col>
        <el-col :span="6" class="pack-col">
          <el-checkbox v-model="manualForm.needPack">需要包装</el-checkbox>
        </el-col>
      </el-row>

      <div class="field-label" style="margin-top: 8px">指定批次/来源 (初始备注)</div>
      <el-input v-model="manualForm.source" placeholder="如：优先1边货" />

      <el-button class="submit-btn" type="danger" :loading="saving" @click="createManualOrder">✅ 生成订单</el-button>
    </template>

    <template v-else-if="activeTab === 'import'">
      <h3 class="section-title">📥 导入已规划合同 (Import Planned Contracts)</h3>
      <el-table :data="plannedContractRows" border stripe size="small" height="320">
        <el-table-column prop="合同号" label="合同号" width="140" />
        <el-table-column prop="客户名" label="客户名" min-width="240" />
        <el-table-column prop="机型" label="机型" width="140" />
        <el-table-column prop="排产数量" label="排产数量" width="90" />
        <el-table-column prop="要求交期" label="要求交期" width="120" />
        <el-table-column prop="备注" label="备注" min-width="120" />
      </el-table>
      <div class="field-label" style="margin-top: 10px">选择要转换(合并)的合同 (支持多选)</div>
      <el-select
        v-model="selectedImportContractIds"
        multiple
        filterable
        collapse-tags
        collapse-tags-tooltip
        placeholder="请选择合同号"
        style="width: 100%"
      >
        <el-option v-for="id in plannedContractIds" :key="id" :label="id" :value="id" />
      </el-select>

      <el-alert
        v-if="selectedImportContractIds.length > 0"
        class="merge-alert"
        type="warning"
        :closable="false"
        :title="mergeWarningText"
      />

      <template v-if="selectedImportContractIds.length > 0">
        <h4 class="merge-title">🧾 确认合并订单信息 (可修改)</h4>
        <el-row :gutter="10">
          <el-col :span="12">
            <div class="field-label">客户名</div>
            <el-input v-model="mergeDraft.customer" />
          </el-col>
          <el-col :span="12">
            <div class="field-label">发货时间/交期</div>
            <el-date-picker v-model="mergeDraft.deliveryDate" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
          </el-col>
        </el-row>
        <el-row :gutter="10" style="margin-top: 8px">
          <el-col :span="12">
            <div class="field-label">代理商</div>
            <el-input v-model="mergeDraft.agent" />
          </el-col>
          <el-col :span="12" class="pack-col">
            <el-checkbox v-model="mergeDraft.needPack">需要包装</el-checkbox>
          </el-col>
        </el-row>

        <div class="field-label" style="margin-top: 8px">包含机型及数量 (合并汇总):</div>
        <el-table :data="mergeRows" border stripe size="small">
          <el-table-column label="#" width="40">
            <template #default="scope">{{ scope.$index + 1 }}</template>
          </el-table-column>
          <el-table-column prop="sourceContract" label="来源合同" width="140" />
          <el-table-column label="机型" min-width="160">
            <template #default="scope">
              <el-select v-model="scope.row.model" filterable placeholder="请选择机型" style="width: 100%">
                <el-option v-for="m in availableModels" :key="m" :label="m" :value="m" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="加高?" width="90">
            <template #default="scope">
              <el-checkbox v-model="scope.row.high" />
            </template>
          </el-table-column>
          <el-table-column label="数量" width="100">
            <template #default="scope">
              <el-input-number v-model="scope.row.qty" :min="1" controls-position="right" />
            </template>
          </el-table-column>
          <el-table-column label="备注" min-width="140">
            <template #default="scope">
              <el-input v-model="scope.row.rowNote" />
            </template>
          </el-table-column>
        </el-table>

        <div class="field-label" style="margin-top: 8px">订单总备注</div>
        <el-input v-model="mergeDraft.note" />

        <div class="row-actions">
          <el-button type="danger" :loading="saving" @click="createOrderFromPlanned">🚀 确认生成合并订单 (Confirm Merge)</el-button>
        </div>
      </template>
      <div v-else class="hint" style="margin-top: 8px">
        请先选择要导入的合同号
      </div>
    </template>

    <template v-else>
      <h3 class="section-title">🔍 订单查询与管理</h3>
      <div class="filter-grid">
        <div>
          <div class="field-label">订单状态筛选</div>
          <el-radio-group v-model="statusFilter">
            <el-radio value="active">进行中 (Active)</el-radio>
            <el-radio value="done">往期/已完结 (Completed)</el-radio>
            <el-radio value="deleted">已删除 (Deleted)</el-radio>
          </el-radio-group>
        </div>
        <div>
          <div class="field-label">按下单月份筛选</div>
          <el-select v-model="monthFilter" placeholder="全部">
            <el-option label="全部" value="all" />
            <el-option v-for="m in monthOptions" :key="m" :label="m" :value="m" />
          </el-select>
        </div>
      </div>
      <div class="field-label">搜索订单 (订单号/客户/代理)</div>
      <el-input v-model="keyword" clearable />
      <div class="hint">共找到 {{ manageRowsFiltered.length }} 条数据</div>

      <el-table :data="manageRowsPaged" border stripe size="small" height="380" @row-click="onManageRowClick">
        <el-table-column label="选择" width="60">
          <template #default="scope">
            <el-checkbox
              :model-value="selectedManageOrderId === String(scope.row['订单号'] || '')"
              @change="(val: any) => onManageSelectChange(scope.row, Boolean(val))"
            />
          </template>
        </el-table-column>
        <el-table-column prop="订单号" label="订单号" width="170" />
        <el-table-column prop="客户名" label="客户名" min-width="160" />
        <el-table-column prop="代理商" label="代理商" width="90" />
        <el-table-column prop="需求机型" label="需求机型" min-width="150" />
        <el-table-column prop="需求数量" label="需求数量" width="90" />
        <el-table-column prop="发货时间" label="发货时间" width="120" />
        <el-table-column prop="备注" label="备注" min-width="170" />
        <el-table-column prop="下单时间" label="下单时间" width="170" />
      </el-table>
      <div class="pager-wrap">
        <el-pagination
          background
          layout="total, prev, pager, next, sizes"
          :total="manageRowsFiltered.length"
          :page-size="managePageSize"
          :current-page="managePage"
          :page-sizes="[20, 50, 100]"
          @size-change="onManagePageSizeChange"
          @current-change="onManagePageChange"
        />
      </div>

      <template v-if="editingId">
        <el-divider />
        <h4 class="merge-title">🖊 编辑订单：{{ editingId }} | {{ editForm.客户名 }}</h4>
        <el-row :gutter="10">
          <el-col :span="12">
            <div class="field-label">客户名</div>
            <el-input v-model="editForm.客户名" />
          </el-col>
          <el-col :span="12">
            <div class="field-label">发货时间</div>
            <el-date-picker v-model="editForm.发货时间" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
          </el-col>
        </el-row>
        <el-row :gutter="10" style="margin-top: 8px">
          <el-col :span="12">
            <div class="field-label">代理商</div>
            <el-input v-model="editForm.代理商" />
          </el-col>
          <el-col :span="12" class="pack-col">
            <el-checkbox v-model="editNeedPack">需要包装</el-checkbox>
          </el-col>
        </el-row>

        <div class="field-label" style="margin-top: 8px">需求机型 (可修改数量/加高，或增删行)</div>
        <el-table :data="editModelRows" border stripe size="small">
          <el-table-column label="#" width="40">
            <template #default="scope">{{ scope.$index + 1 }}</template>
          </el-table-column>
          <el-table-column label="机型">
            <template #default="scope">
              <el-select v-model="scope.row.model" filterable placeholder="请选择机型" style="width: 100%;">
                <el-option v-for="m in availableModels" :key="m" :label="m" :value="m" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="数量" width="120">
            <template #default="scope">
              <el-input-number v-model="scope.row.qty" :min="1" controls-position="right" />
            </template>
          </el-table-column>
          <el-table-column label="加高?" width="90">
            <template #default="scope">
              <el-checkbox v-model="scope.row.high" />
            </template>
          </el-table-column>
          <el-table-column label="单行备注" min-width="160">
            <template #default="scope">
              <el-input v-model="scope.row.rowNote" />
            </template>
          </el-table-column>
        </el-table>
        <div class="row-actions">
          <el-button link type="primary" @click="addEditRow">+ 增加机型行</el-button>
        </div>

        <div class="field-label">订单总备注</div>
        <el-input v-model="editForm.备注" />

        <div class="field-label" style="margin-top: 8px">指定批次/来源</div>
        <el-input v-model="editSourceText" />

        <el-divider />
        <div class="field-label">删除原因 (若仅标记删除建议填写)</div>
        <el-input v-model="deleteReason" placeholder="例如：客户取消、重复下单等" />

        <div class="edit-actions">
          <el-button type="danger" :loading="saving" @click="saveEdit">💾 保存修改</el-button>
          <el-button :loading="saving" @click="deleteOrder">🗑 删除订单</el-button>
        </div>
      </template>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { apiGetAll, apiPost, apiPut, getApiErrorMessage } from '../utils/request'
import PageSkeleton from '../components/PageSkeleton.vue'
import PageHeader from '../components/PageHeader.vue'
import { useFormSubmit } from '../composables/useFormSubmit'
import { getModelOrderList, isModelInDictionary } from '../utils/modelOrder'
type RowData = Record<string, any>

const loading = ref(false)
const saving = ref(false)
const loadError = ref('')
const loadedOnce = ref(false)
const { submitWithLock } = useFormSubmit()
const rows = ref<RowData[]>([])
const planRows = ref<RowData[]>([])
const inventoryRows = ref<RowData[]>([])

const activeTab = ref<'manual' | 'import' | 'manage'>('manual')
const keyword = ref('')
const statusFilter = ref<'active' | 'done' | 'deleted'>('active')
const monthFilter = ref('all')
const managePage = ref(1)
const managePageSize = ref(50)
const selectedManageOrderId = ref('')
const selectedImportContractIds = ref<string[]>([])
const mergeRows = ref<Array<{ sourceContract: string; model: string; high: boolean; qty: number; rowNote: string }>>([])
const mergeDraft = reactive({
  customer: '',
  agent: '',
  deliveryDate: '',
  needPack: false,
  note: '',
})

const manualForm = reactive({
  customer: '',
  agent: '',
  note: '',
  deliveryDate: '',
  source: '',
  needPack: false,
})
const manualRows = ref<Array<{ model: string; qty: number; high: boolean; rowNote: string }>>([{ model: '', qty: 1, high: false, rowNote: '' }])

const editingId = ref('')
const editNeedPack = ref(false)
const editSourceText = ref('')
const deleteReason = ref('')
const editModelRows = ref<Array<{ model: string; qty: number; high: boolean; rowNote: string }>>([])
const editForm = reactive({
  客户名: '',
  代理商: '',
  需求机型: '',
  需求数量: 1,
  发货时间: '',
  备注: '',
  status: 'active',
})

const monthOptions = computed(() => {
  const set = new Set<string>()
  for (const r of rows.value) {
    const s = String(r['下单时间'] || '')
    if (s.length >= 7) set.add(s.slice(0, 7))
  }
  return Array.from(set).sort().reverse()
})

const availableModels = computed(() => {
  return getModelOrderList()
})

const parseOrderDemandTotal = (order: RowData) => {
  const raw = String(order['需求机型'] || '')
  let total = 0
  for (const tokenRaw of raw.split(';')) {
    const token = tokenRaw.trim()
    if (!token) continue
    const m = token.match(/[x×:：]\s*(\d+)$/i)
    if (m) total += Number(m[1]) || 0
  }
  if (total > 0) return total
  const fallback = Number(order['需求数量'] || 0)
  return Number.isFinite(fallback) ? Math.max(0, fallback) : 0
}

const shippedCountByOrder = computed(() => {
  const map = new Map<string, number>()
  for (const r of inventoryRows.value) {
    if (String(r['状态'] || '') !== '已出库') continue
    const oid = String(r['占用订单号'] || '').trim()
    if (!oid) continue
    map.set(oid, (map.get(oid) || 0) + 1)
  }
  return map
})

const completedOrderIdSet = computed(() => {
  const set = new Set<string>()
  for (const r of rows.value) {
    const oid = String(r['订单号'] || '').trim()
    if (!oid) continue
    const need = parseOrderDemandTotal(r)
    const shipped = shippedCountByOrder.value.get(oid) || 0
    if (need > 0 && shipped >= need) set.add(oid)
  }
  return set
})

const manageRowsFiltered = computed(() => {
  const term = keyword.value.trim().toLowerCase()
  return rows.value
    .filter((r) => {
      const oid = String(r['订单号'] || '')
      const status = String(r.status || 'active')
      const completed = completedOrderIdSet.value.has(oid)
      if (statusFilter.value === 'deleted') return status === 'deleted'
      if (statusFilter.value === 'done') return status === 'done' || completed
      // active
      if (!['active', 'ready', 'packed', 'done'].includes(status)) return false
      return !completed && status !== 'done'
    })
    .filter((r) => {
      if (monthFilter.value === 'all') return true
      return String(r['下单时间'] || '').startsWith(monthFilter.value)
    })
    .filter((r) => {
      if (!term) return true
      const hit = `${r['订单号'] || ''} ${r['客户名'] || ''} ${r['代理商'] || ''}`.toLowerCase()
      return hit.includes(term)
    })
})
const manageRowsPaged = computed(() => {
  const start = (managePage.value - 1) * managePageSize.value
  const end = start + managePageSize.value
  return manageRowsFiltered.value.slice(start, end)
})

const plannedContractRows = computed(() => planRows.value.filter((r) => String(r['状态'] || '') === '已规划'))
const plannedContractIds = computed(() => {
  const set = new Set<string>()
  for (const r of plannedContractRows.value) {
    const id = String(r['合同号'] || '')
    if (id) set.add(id)
  }
  return Array.from(set)
})
const selectedImportRows = computed(() => {
  return plannedContractRows.value.filter((r) => selectedImportContractIds.value.includes(String(r['合同号'] || '')))
})
const mergeWarningText = computed(() => {
  const customers = new Set<string>()
  for (const r of selectedImportRows.value) {
    const c = String(r['客户名'] || '').trim()
    if (c) customers.add(c)
  }
  if (customers.size > 1) return '注意：您选择了不同客户的合同进行合并，请确认是否正确。'
  return '提示：请确认合并后的客户、代理、交期、机型数量与备注。'
})
const showInitialSkeleton = computed(() => loading.value && !loadedOnce.value && !loadError.value)

const addManualRow = () => {
  manualRows.value.push({ model: '', qty: 1, high: false, rowNote: '' })
}

const fetchData = async () => {
  loading.value = true
  loadError.value = ''
  try {
    const [nextOrders, nextPlans, nextInventory] = await Promise.all([
      apiGetAll<RowData>('/planning/orders'),
      apiGetAll<RowData>('/planning/'),
      apiGetAll<RowData>('/inventory/'),
    ])
    rows.value = nextOrders
    planRows.value = nextPlans
    inventoryRows.value = nextInventory
  } catch (err: any) {
    loadError.value = getApiErrorMessage(err) || '读取数据失败'
    ElMessage.error(loadError.value)
  } finally {
    loading.value = false
    loadedOnce.value = true
  }
}
const retryFetch = () => {
  void fetchData()
}

const createManualOrder = async () => {
  if (!manualForm.customer.trim()) {
    ElMessage.warning('请先填写客户信息')
    return
  }
  const validRows = manualRows.value.filter((r) => r.model.trim() && Number(r.qty) > 0)
  if (validRows.length === 0) {
    ElMessage.warning('请至少填写一条有效机型')
    return
  }
  const invalidModels = validRows.map((r) => String(r.model || '').trim()).filter((m) => !isModelInDictionary(m))
  if (invalidModels.length > 0) {
    ElMessage.warning(`以下机型不在字典中：${Array.from(new Set(invalidModels)).join('，')}`)
    return
  }

  const modelTokens = validRows.map((r) => `${r.model.trim()}${r.high ? '(加高)' : ''}x${r.qty}`)
  const totalQty = validRows.reduce((sum, r) => sum + Number(r.qty || 0), 0)
  const rowNotes = validRows.filter((r) => r.rowNote.trim()).map((r) => `${r.model}: ${r.rowNote.trim()}`)
  const noteParts = [manualForm.note.trim(), ...rowNotes]
  const finalNote = noteParts.filter(Boolean).join(' | ')

  await submitWithLock(saving, async () => {
    await apiPost('/planning/orders', {
      客户名: manualForm.customer,
      代理商: manualForm.agent,
      需求机型: modelTokens.join(';'),
      需求数量: totalQty,
      发货时间: manualForm.deliveryDate,
      备注: finalNote,
      包装选项: manualForm.needPack ? '需要包装' : '',
    })
    ElMessage.success('订单已创建')
    manualRows.value = [{ model: '', qty: 1, high: false, rowNote: '' }]
    manualForm.note = ''
    manualForm.source = ''
    await fetchData()
  }, { successMessage: '订单已创建', errorMessage: '创建失败' })
}

const createOrderFromPlanned = async () => {
  if (selectedImportContractIds.value.length === 0) {
    ElMessage.warning('请先选择合同号')
    return
  }
  const selectedRows = selectedImportRows.value
  if (selectedRows.length === 0) {
    ElMessage.warning('未找到可转换的合同数据')
    return
  }

  const modelTokens: string[] = []
  let totalQty = 0
  for (const r of mergeRows.value) {
    const model = String(r.model || '').trim()
    const qty = Number(r.qty || 0)
    if (!model || qty <= 0) continue
    modelTokens.push(`${model}${r.high ? '(加高)' : ''}x${qty}`)
    totalQty += qty
  }
  const invalidModels = mergeRows.value
    .map((r) => String(r.model || '').trim())
    .filter((m) => m && !isModelInDictionary(m))
  if (invalidModels.length > 0) {
    ElMessage.warning(`以下机型不在字典中：${Array.from(new Set(invalidModels)).join('，')}`)
    return
  }
  if (totalQty <= 0) {
    ElMessage.warning('合同机型数量无效')
    return
  }
  if (!mergeDraft.customer.trim()) {
    ElMessage.warning('请填写客户名')
    return
  }

  const rowNotes = mergeRows.value
    .filter((r) => r.rowNote.trim())
    .map((r) => `[${r.sourceContract}] ${r.rowNote.trim()}`)
  const mergedNote = [mergeDraft.note.trim(), ...rowNotes].filter(Boolean).join(' | ')

  await submitWithLock(saving, async () => {
    await apiPost('/planning/orders', {
      客户名: mergeDraft.customer,
      代理商: mergeDraft.agent,
      需求机型: modelTokens.join(';'),
      需求数量: totalQty,
      发货时间: mergeDraft.deliveryDate,
      备注: mergedNote || `合同导入: ${selectedImportContractIds.value.join(',')}`,
      包装选项: mergeDraft.needPack ? '需要包装' : '',
    })
    for (const id of selectedImportContractIds.value) {
      await apiPost(`/planning/contract/${encodeURIComponent(id)}/status`, { status: '已下单' })
    }
    ElMessage.success('已转换为订单')
    selectedImportContractIds.value = []
    mergeRows.value = []
    await fetchData()
  }, { errorMessage: '转换失败' })
}

watch(selectedImportContractIds, () => {
  const rows = selectedImportRows.value
  if (rows.length === 0) {
    mergeRows.value = []
    mergeDraft.customer = ''
    mergeDraft.agent = ''
    mergeDraft.deliveryDate = ''
    mergeDraft.needPack = false
    mergeDraft.note = ''
    return
  }

  const first = rows[0]
  mergeDraft.customer = String(first['客户名'] || '')
  mergeDraft.agent = String(first['代理商'] || '')
  mergeDraft.deliveryDate = String(first['要求交期'] || '')
  mergeDraft.note = rows
    .map((r) => {
      const cid = String(r['合同号'] || '')
      const note = String(r['备注'] || '').trim()
      return note ? `[${cid}] ${note}` : ''
    })
    .filter(Boolean)
    .join(' ')

  mergeRows.value = rows.map((r) => {
    const rawModel = String(r['机型'] || '').trim()
    const high = rawModel.includes('(加高)')
    const model = rawModel.replace('(加高)', '').trim()
    return {
      sourceContract: String(r['合同号'] || ''),
      model,
      high,
      qty: Math.max(1, Number(r['排产数量'] || 1) || 1),
      rowNote: String(r['备注'] || ''),
    }
  })
})

const openEdit = (row: RowData, syncSelection = true) => {
  const currentId = String(row['订单号'] || '')
  if (syncSelection) selectedManageOrderId.value = currentId
  editingId.value = currentId
  editForm.客户名 = String(row['客户名'] || '')
  editForm.代理商 = String(row['代理商'] || '')
  editForm.需求机型 = String(row['需求机型'] || '')
  editForm.需求数量 = Number(row['需求数量'] || 1) || 1
  editForm.发货时间 = String(row['发货时间'] || '')
  editForm.备注 = String(row['备注'] || '')
  editForm.status = String(row['status'] || 'active')
  editNeedPack.value = String(row['包装选项'] || '').includes('需要')
  const sourceRaw = row['指定批次/来源']
  if (typeof sourceRaw === 'string') {
    const t = sourceRaw.trim()
    editSourceText.value = t === '{}' ? '' : t
  } else if (sourceRaw && typeof sourceRaw === 'object') {
    const keys = Object.keys(sourceRaw as Record<string, unknown>)
    editSourceText.value = keys.length === 0 ? '' : JSON.stringify(sourceRaw)
  } else {
    editSourceText.value = ''
  }
  deleteReason.value = ''

  const parsedRows: Array<{ model: string; qty: number; high: boolean; rowNote: string }> = []
  const rawModels = String(row['需求机型'] || '')
    .split(';')
    .map((x: string) => x.trim())
    .filter(Boolean)
  for (const token of rawModels) {
    const m = token.match(/^(.*)x(\d+)$/)
    const modelRaw = m ? m[1] : token
    const qty = m ? Number(m[2]) : 1
    const high = modelRaw.includes('(加高)')
    parsedRows.push({
      model: modelRaw.replace('(加高)', '').trim(),
      qty: qty > 0 ? qty : 1,
      high,
      rowNote: '',
    })
  }
  editModelRows.value = parsedRows.length > 0 ? parsedRows : [{ model: '', qty: 1, high: false, rowNote: '' }]
}

const clearEditPanel = () => {
  selectedManageOrderId.value = ''
  editingId.value = ''
  editForm.客户名 = ''
  editForm.代理商 = ''
  editForm.需求机型 = ''
  editForm.需求数量 = 1
  editForm.发货时间 = ''
  editForm.备注 = ''
  editForm.status = 'active'
  editNeedPack.value = false
  editSourceText.value = ''
  deleteReason.value = ''
  editModelRows.value = []
}

const onManageSelectChange = (row: RowData, checked: boolean) => {
  const rowId = String(row['订单号'] || '')
  if (checked) {
    selectedManageOrderId.value = rowId
    openEdit(row, false)
    return
  }
  if (selectedManageOrderId.value === rowId || editingId.value === rowId) {
    clearEditPanel()
  }
}

const onManageRowClick = (row: RowData, _column: any, event: MouseEvent) => {
  const target = event?.target as HTMLElement | null
  if (target?.closest('.el-checkbox')) return
  openEdit(row)
}

const onManagePageSizeChange = (size: number) => {
  managePageSize.value = size
  managePage.value = 1
}

const onManagePageChange = (page: number) => {
  managePage.value = page
}

const addEditRow = () => {
  editModelRows.value.push({ model: '', qty: 1, high: false, rowNote: '' })
}

const saveEdit = async () => {
  if (!editingId.value) return
  if (!editForm.客户名.trim()) {
    ElMessage.warning('客户名不能为空')
    return
  }
  const validRows = editModelRows.value.filter((r) => r.model.trim() && Number(r.qty) > 0)
  if (validRows.length === 0) {
    ElMessage.warning('客户名和需求机型不能为空')
    return
  }
  const invalidModels = validRows.map((r) => String(r.model || '').trim()).filter((m) => !isModelInDictionary(m))
  if (invalidModels.length > 0) {
    ElMessage.warning(`以下机型不在字典中：${Array.from(new Set(invalidModels)).join('，')}`)
    return
  }
  const modelTokens = validRows.map((r) => `${r.model.trim()}${r.high ? '(加高)' : ''}x${r.qty}`)
  const totalQty = validRows.reduce((sum, r) => sum + Number(r.qty || 0), 0)
  const lineNotes = validRows.filter((r) => r.rowNote.trim()).map((r) => `${r.model}: ${r.rowNote.trim()}`)
  const finalNote = [editForm.备注.trim(), ...lineNotes].filter(Boolean).join(' | ')

  await submitWithLock(saving, async () => {
    await apiPut(`/planning/orders/${encodeURIComponent(editingId.value)}`, {
      客户名: editForm.客户名,
      代理商: editForm.代理商,
      需求机型: modelTokens.join(';'),
      需求数量: totalQty,
      发货时间: editForm.发货时间,
      备注: finalNote,
      包装选项: editNeedPack.value ? '需要包装' : '',
      '指定批次/来源': editSourceText.value,
      status: editForm.status,
    })
    ElMessage.success('订单已更新')
    await fetchData()
  }, { errorMessage: '保存失败' })
}

const deleteOrder = async () => {
  if (!editingId.value) return
  await submitWithLock(saving, async () => {
    const reason = deleteReason.value.trim()
    const deletedNote = [editForm.备注.trim(), reason ? `删除原因: ${reason}` : '删除原因: 未填写'].filter(Boolean).join(' | ')
    await apiPut(`/planning/orders/${encodeURIComponent(editingId.value)}`, {
      status: 'deleted',
      备注: deletedNote,
    })
    ElMessage.success('订单已标记删除')
    await fetchData()
  }, { errorMessage: '删除失败' })
}

onMounted(() => {
  fetchData()
})

watch([keyword, statusFilter, monthFilter], () => {
  managePage.value = 1
  const selectedStillVisible = manageRowsFiltered.value.some((r) => String(r['订单号'] || '') === selectedManageOrderId.value)
  if (!selectedStillVisible) clearEditPanel()
})
</script>

<style scoped>
.sales-page {
  height: 100%;
}
.head-row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-bottom: var(--space-2);
}
.back-btn {
  padding: 4px 12px;
}
.tabs-row {
  display: flex;
  margin-bottom: 12px;
  gap: 8px;
}
.load-error {
  margin-bottom: var(--space-2);
}
.tab-btn {
  border: none;
  background: transparent;
  color: var(--color-gray-500);
  font-size: var(--font-size-sm);
  cursor: pointer;
  padding: 2px 0;
}
.tab-btn.active {
  color: #ef4444;
  font-weight: 700;
  border-bottom: 2px solid #ef4444;
}
.title {
  margin: 0;
  font-size: 44px;
  font-weight: 800;
  color: var(--color-gray-800);
}
.section-title {
  font-size: 32px;
  font-weight: 800;
  color: var(--color-gray-900);
  margin: 6px 0 8px;
}
.field-label {
  font-size: var(--font-size-sm);
  color: var(--color-gray-700);
  margin-bottom: 4px;
}
.row-actions {
  margin-top: 6px;
}
.pack-col {
  display: flex;
  align-items: end;
}
.submit-btn {
  width: 100%;
  margin-top: 12px;
}
.filter-grid {
  display: grid;
  grid-template-columns: 1fr 220px;
  gap: var(--space-2);
  margin-bottom: var(--space-2);
}
.hint {
  margin: 6px 0;
  color: #94a3b8;
  font-size: var(--font-size-sm);
}
.merge-alert {
  margin-top: var(--space-2);
}
.merge-title {
  margin: 10px 0 8px;
  font-size: 22px;
  font-weight: 800;
  color: var(--color-gray-800);
}
.edit-actions {
  margin-top: 12px;
  display: flex;
  gap: var(--space-3);
}
.pager-wrap {
  margin-top: var(--space-2);
  display: flex;
  justify-content: flex-end;
}
</style>
