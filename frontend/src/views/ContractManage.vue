<template>
  <div class="contract-page">
    <PageHeader title="🏢 销售合同管理" />

    <div class="notice">💡 提示：录入的新合同在审批通过后，将自动流转至生产统筹与下单环节。</div>

    <div class="new-row">
      <button type="button" class="new-row-toggle" @click="batchPanelOpen = !batchPanelOpen">
        {{ batchPanelOpen ? '▾' : '▸' }} ➕ 录入新合同 (批量)
      </button>
    </div>

    <div class="batch-slide" :class="{ open: batchPanelOpen }">
      <div class="batch-slide-inner">
        <div class="batch-panel">
          <div class="batch-grid">
        <div>
          <div class="ops-label">系统自动生成合同号</div>
          <div class="auto-id">{{ batchForm.contractId }}</div>
          <div class="tip">格式: HT + 日期 + 随机4位</div>
        </div>
        <div>
          <div class="ops-label">期望交付日期</div>
          <el-date-picker v-model="batchForm.deadline" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
        </div>
        <div>
          <div class="ops-label">客户名称</div>
          <el-input v-model="batchForm.customer" />
        </div>
        <div>
          <div class="ops-label">代理商名称</div>
          <el-input v-model="batchForm.agent" />
        </div>
      </div>

      <el-divider />
      <div class="ops-label">📎 附加合同文件 (可选)</div>
      <el-upload
        :auto-upload="false"
        :show-file-list="true"
        multiple
        :on-change="onBatchFileChange"
        :on-remove="onBatchFileRemove"
      >
        <el-button>选择文件</el-button>
      </el-upload>

      <el-divider />
      <div class="tip">请在下方清单中添加设备机型。支持同一机型添加多条记录（例如：标准版与加高版分开录入）。</div>
      <el-table :data="batchItems" border stripe class="form-table">
        <el-table-column label="#" width="60">
          <template #default="scope">{{ scope.$index + 1 }}</template>
        </el-table-column>
        <el-table-column label="机型">
          <template #default="scope">
            <el-select v-model="scope.row.model" filterable placeholder="请选择机型" style="width: 100%">
              <el-option v-for="m in modelOptions" :key="m" :label="m" :value="m" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="数量" width="100">
          <template #default="scope">
            <el-input-number v-model="scope.row.qty" :min="1" :controls="false" placeholder="数量" style="width: 100%" />
          </template>
        </el-table-column>
        <el-table-column label="加高?" width="90">
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
      <div class="batch-row-actions">
        <el-button link type="primary" @click="addBatchItem">+ 添加机型行</el-button>
      </div>

      <div class="ops-label">合同总备注</div>
      <el-input v-model="batchForm.contractNote" placeholder="可选，应用于所有条目" />

      <div class="batch-save">
        <el-button type="danger" :loading="batchSaving" @click="submitBatchContracts">💾 保存所有合同条目</el-button>
      </div>
        </div>
      </div>
    </div>

    <div class="view-tabs">
      <button type="button" class="view-tab" :class="{ active: viewMode === 'urgent' }" @click="viewMode = 'urgent'">
        🔥 紧急处理 [2月内]
      </button>
      <button type="button" class="view-tab" :class="{ active: viewMode === 'recent' }" @click="viewMode = 'recent'">
        📘 近期规划 [2月内]
      </button>
      <button type="button" class="view-tab" :class="{ active: viewMode === 'all' }" @click="viewMode = 'all'">
        📋 全景视图
      </button>
    </div>

    <el-table
      :data="pagedRows"
      border
      stripe
      size="small"
      height="430"
      @current-change="onCurrentRowChange"
      highlight-current-row
    >
      <el-table-column prop="合同号" label="合同号" min-width="160" />
      <el-table-column prop="客户名" label="客户名" min-width="260" />
      <el-table-column prop="代理商" label="代理商" width="90" />
      <el-table-column prop="机型" label="机型" min-width="160" />
      <el-table-column prop="排产数量" label="排产数量" width="90" />
      <el-table-column prop="要求交期" label="要求交期" width="100" />
      <el-table-column prop="状态" label="状态" width="90" />
      <el-table-column prop="备注" label="备注" min-width="120" />
    </el-table>

    <div v-if="displayRows.length > pageSize" class="table-pagination">
      <el-pagination
        background
        layout="total, prev, pager, next"
        :total="displayRows.length"
        :page-size="pageSize"
        :current-page="tablePage"
        @current-change="onPageChange"
      />
    </div>

    <div class="ops-panel">
      <div class="ops-left">
        <div class="ops-label">选择合同号进行操作</div>
        <el-select v-model="selectedContractId" filterable placeholder="请选择合同号">
          <el-option v-for="id in selectableContractIds" :key="id" :label="id" :value="id" />
        </el-select>
      </div>

      <div class="ops-right">
        <el-radio-group v-model="operationType">
          <el-radio value="ordered">标记已下单</el-radio>
          <el-radio value="cancelled">取消计划</el-radio>
          <el-radio value="done">标记已完工</el-radio>
          <el-radio value="linked">关联现有订单(核销)</el-radio>
        </el-radio-group>
        <el-button type="primary" :loading="executing" @click="executeOperation">执行</el-button>
      </div>
    </div>

    <!-- 订单号输入框 - 只在关联订单时显示 -->
    <div v-if="operationType === 'linked'" class="link-order-panel">
      <div class="ops-label">输入已存在的订单号</div>
      <el-input v-model="linkOrderId" placeholder="例如: SO-2026..." style="width: 300px" />
    </div>

  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { apiPost, getApiErrorMessage } from '../utils/request'
import { useFormSubmit } from '../composables/useFormSubmit'
import { useContractsStore } from '../store/contracts'
import { useRefFormDraft } from '../composables/useFormDraft'
import { hasText, isPositiveInteger } from '../utils/formRules'
import { getModelOrderList, isModelInDictionary } from '../utils/modelOrder'
import PageHeader from '../components/PageHeader.vue'

type ViewMode = 'urgent' | 'recent' | 'all'
type OperationType = 'ordered' | 'cancelled' | 'done' | 'linked'
type MessageResponse = { message?: string }

const loading = ref(false)
const executing = ref(false)
const batchSaving = ref(false)
const batchPanelOpen = ref(false)
const allRows = ref<any[]>([])
const urgentRows = ref<any[]>([])
const recentRows = ref<any[]>([])
const allRowsSorted = ref<any[]>([])
const selectedContractId = ref('')
const viewMode = ref<ViewMode>('urgent')
const operationType = ref<OperationType>('ordered')
const batchPickedFiles = ref<File[]>([])
const linkOrderId = ref('')
const tablePage = ref(1)
const pageSize = 120
const { submitWithLock } = useFormSubmit()
const contractsStore = useContractsStore()
const batchForm = ref({
  contractId: '',
  deadline: '',
  customer: '',
  agent: '',
  contractNote: '',
})
const batchItems = ref<Array<{ model: string; qty: number; high: boolean; rowNote: string }>>([
  { model: '', qty: 1, high: false, rowNote: '' },
])
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

const resetBatchForm = () => {
  batchForm.value = {
    contractId: genContractId(),
    deadline: todayYmd(),
    customer: '',
    agent: '',
    contractNote: '',
  }
  batchItems.value = [{ model: '', qty: 1, high: false, rowNote: '' }]
  batchPickedFiles.value = []
}

const parseDate = (v: string) => {
  const d = new Date(v)
  if (Number.isNaN(d.getTime())) return null
  return d
}

const isWithinDays = (v: string, days: number) => {
  const d = parseDate(v)
  if (!d) return false
  const now = new Date()
  const diff = d.getTime() - now.getTime()
  return diff >= 0 && diff <= days * 24 * 60 * 60 * 1000
}

const sortContractRows = (rows: any[]) => {
  return [...rows].sort((a: any, b: any) => String(a['合同号'] || '').localeCompare(String(b['合同号'] || '')))
}

const rebuildViewCaches = (rows: any[]) => {
  const recent = rows.filter((r: any) => isWithinDays(String(r['要求交期'] || ''), 60))
  urgentRows.value = sortContractRows(
    recent.filter((r: any) => String(r['状态'] || '') === '未下单')
  )
  recentRows.value = sortContractRows(recent)
  allRowsSorted.value = sortContractRows(rows)
}

const filteredRows = computed(() => {
  if (viewMode.value === 'all') return allRowsSorted.value
  if (viewMode.value === 'recent') return recentRows.value
  return urgentRows.value
})

const displayRows = computed(() => {
  return filteredRows.value
})

const pagedRows = computed(() => {
  const start = (tablePage.value - 1) * pageSize
  return displayRows.value.slice(start, start + pageSize)
})

const selectableContractIds = computed(() => {
  const set = new Set<string>()
  for (const row of filteredRows.value) {
    const id = String(row['合同号'] || '')
    if (id) set.add(id)
  }
  return Array.from(set)
})

const onPageChange = (page: number) => {
  tablePage.value = page
}

const statusByOperation: Record<OperationType, string> = {
  ordered: '已下单',
  cancelled: '已取消',
  done: '已完工',
  linked: '已转订单',
}

const fetchContracts = async () => {
  loading.value = true
  try {
    allRows.value = await contractsStore.fetchPlanningContracts()
    rebuildViewCaches(allRows.value)
    if (!selectedContractId.value && selectableContractIds.value.length > 0) {
      selectedContractId.value = selectableContractIds.value[0]
    }
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '读取合同数据失败')
  } finally {
    loading.value = false
  }
}

watch(viewMode, () => {
  tablePage.value = 1
})

const onCurrentRowChange = (row: any) => {
  if (!row) return
  const id = String(row['合同号'] || '')
  if (id) selectedContractId.value = id
}

const executeOperation = async () => {
  if (!selectedContractId.value) {
    ElMessage.warning('请先选择合同号')
    return
  }

  if (operationType.value === 'linked') {
    // 关联订单操作
    const orderId = linkOrderId.value.trim()
    if (!orderId) {
      ElMessage.warning('请输入要关联的订单号')
      return
    }
    await submitWithLock(executing, async () => {
      const res = await apiPost<MessageResponse>(
        `/planning/contract/${encodeURIComponent(selectedContractId.value)}/link-order`,
        { order_id: orderId }
      )
      ElMessage.success(res.message || '关联成功')
      linkOrderId.value = ''
      await fetchContracts()
    }, { errorMessage: '关联订单失败' })
  } else {
    // 其他状态更新操作
    await submitWithLock(executing, async () => {
      await apiPost(`/planning/contract/${encodeURIComponent(selectedContractId.value)}/status`, {
        status: statusByOperation[operationType.value],
      })
      await fetchContracts()
    }, { successMessage: '操作成功', errorMessage: '操作失败' })
  }
}

const addBatchItem = () => {
  batchItems.value.push({ model: '', qty: 1, high: false, rowNote: '' })
}

const onBatchFileChange = (uploadFile: any) => {
  const raw = uploadFile.raw as File | undefined
  if (!raw) return
  batchPickedFiles.value.push(raw)
}

const onBatchFileRemove = (uploadFile: any) => {
  const raw = uploadFile.raw as File | undefined
  if (!raw) return
  batchPickedFiles.value = batchPickedFiles.value.filter((f) => !(f.name === raw.name && f.size === raw.size))
}

const submitBatchContracts = async () => {
  const cid = batchForm.value.contractId.trim()
  const customer = batchForm.value.customer.trim()
  const deadline = batchForm.value.deadline.trim()
  if (!hasText(cid) || !hasText(customer) || !hasText(deadline)) {
    ElMessage.warning('请先完整填写合同号/客户名/要求交期')
    return
  }
  const validRows = batchItems.value.filter((r) => hasText(r.model) && isPositiveInteger(r.qty))
  if (validRows.length === 0) {
    ElMessage.warning('请至少填写 1 条机型明细')
    return
  }
  const invalidModels = validRows.map((r) => String(r.model || '').trim()).filter((m) => !isModelInDictionary(m))
  if (invalidModels.length > 0) {
    ElMessage.warning(`以下机型不在字典中：${Array.from(new Set(invalidModels)).join('，')}`)
    return
  }

  await submitWithLock(batchSaving, async () => {
    const payloadRows = validRows.map((r) => ({
      合同号: cid,
      客户名: customer,
      代理商: batchForm.value.agent.trim(),
      机型: `${r.model.trim()}${r.high ? '(加高)' : ''}`,
      排产数量: Number(r.qty),
      要求交期: deadline,
      备注: [batchForm.value.contractNote.trim(), r.rowNote.trim()].filter(Boolean).join(' | '),
    }))
    const res = await apiPost<MessageResponse>('/planning/contracts/batch-create', { rows: payloadRows })

    if (batchPickedFiles.value.length > 0) {
      for (const f of batchPickedFiles.value) {
        const fd = new FormData()
        fd.append('file', f)
        await apiPost(`/planning/contract/${encodeURIComponent(cid)}/files`, fd, {
          params: { customer_name: customer, uploader_name: 'Web' },
          headers: { 'Content-Type': 'multipart/form-data' },
        })
      }
    }
    ElMessage.success(res.message || '批量录入成功')
    batchPanelOpen.value = false
    resetBatchForm()
    batchFormDraft.clearDraft()
    batchItemsDraft.clearDraft()
    await fetchContracts()
  }, { errorMessage: '批量录入失败' })
}

const batchFormDraft = useRefFormDraft('contracts:batch-form', batchForm)
const batchItemsDraft = useRefFormDraft('contracts:batch-items', batchItems)

onMounted(() => {
  resetBatchForm()
  fetchContracts()
})
</script>

<style scoped>
.contract-page {
  padding-right: 6px;
}
.head-row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}
.back-btn {
  padding: 4px 12px;
}
.title {
  margin: 0;
  font-size: 40px;
  color: var(--color-gray-800);
  font-weight: 800;
}
.notice {
  margin-top: 12px;
  border: 1px solid var(--color-primary-100);
  background: var(--color-primary-50);
  color: var(--color-primary-700);
  border-radius: var(--radius-md);
  padding: var(--space-2) var(--space-3);
  font-size: var(--font-size-base);
}
.new-row {
  margin-top: var(--space-2);
  border: 1px solid var(--color-gray-200);
  border-radius: var(--radius-md);
  padding: 0 10px;
}
.new-row-toggle {
  border: none;
  background: transparent;
  color: var(--color-gray-700);
  font-size: var(--font-size-lg);
  font-weight: 700;
  cursor: pointer;
  padding: var(--space-2) 0;
}
.batch-slide {
  display: grid;
  grid-template-rows: 0fr;
  transition: grid-template-rows 0.35s cubic-bezier(0.4, 0, 0.2, 1);
}
.batch-slide.open {
  grid-template-rows: 1fr;
}
.batch-slide-inner {
  overflow: hidden;
  padding-top: 0;
  transition: padding-top 0.35s cubic-bezier(0.4, 0, 0.2, 1);
}
.batch-slide.open .batch-slide-inner {
  padding-top: var(--space-2);
}
.batch-panel {
  border: 1px solid var(--color-gray-200);
  border-radius: var(--radius-lg);
  padding: var(--space-2);
}
.batch-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-2);
}
.auto-id {
  border: 1px solid var(--color-gray-200);
  background: var(--color-gray-50);
  border-radius: var(--radius-lg);
  padding: 8px 10px;
  font-size: var(--font-size-lg);
  font-weight: 700;
  color: var(--color-gray-800);
}
.batch-row-actions {
  margin-top: 6px;
}
.batch-save {
  margin-top: var(--space-2);
}
.view-tabs {
  margin-top: var(--space-2);
  display: flex;
  gap: var(--space-3);
}
.view-tab {
  border: none;
  background: transparent;
  color: var(--color-gray-500);
  font-size: var(--font-size-base);
  cursor: pointer;
  padding: 8px 4px;
  min-height: 42px;
  font-weight: 600;
}
.view-tab.active {
  color: #ef4444;
  font-weight: 700;
}
:deep(.el-table) {
  margin-top: var(--space-2);
}
.ops-panel {
  margin-top: var(--space-2);
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--space-3);
}
.table-pagination {
  margin-top: var(--space-2);
  display: flex;
  justify-content: flex-end;
}
.ops-left {
  flex: 1;
}
.ops-left :deep(.el-select) {
  width: 520px;
  max-width: 100%;
}
.ops-label {
  font-size: var(--font-size-sm);
  color: var(--color-gray-900);
  margin-bottom: 4px;
}
.ops-right {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  white-space: nowrap;
}
.ops-right :deep(.el-radio-group) {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 14px;
}
.tip {
  color: var(--color-gray-500);
  font-size: var(--font-size-sm);
  margin-bottom: 6px;
}
.link-order-panel {
  margin-top: var(--space-2);
  padding: var(--space-2);
  border: 1px solid var(--color-gray-200);
  border-radius: var(--radius-md);
  background: var(--color-gray-50);
  display: flex;
  align-items: center;
  gap: var(--space-2);
}
.link-order-panel .ops-label {
  margin-bottom: 0;
  white-space: nowrap;
}
.form-table :deep(.el-table__cell) {
  padding: 10px 8px !important;
}
.form-table :deep(.cell) {
  padding: 0 4px !important;
}
</style>
