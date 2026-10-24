<template>
  <el-dialog
    v-model="visible"
    :title="dialogTitle"
    width="90%"
    top="4vh"
    append-to-body
    :close-on-click-modal="false"
    :close-on-press-escape="false"
    @closed="reset"
  >
    <div v-loading="busy" class="draft-wrap">
      <el-empty
        v-if="!loading && !currentDraft"
        :description="`订单 ${orderNo || ''} 暂无可审批的合同附件`"
      >
        <el-button type="primary" :disabled="!canApproveOrder || busy" @click="approveWithoutDraft">
          直接审核订单
        </el-button>
      </el-empty>

      <template v-else-if="currentDraft">
        <div class="draft-bar">
          <span class="draft-meta">订单 <strong>{{ orderNo }}</strong></span>
          <el-tag size="small" :type="stateType(currentDraft.state)">
            {{ labels[currentDraft.state] || currentDraft.state }}
          </el-tag>
          <span class="draft-meta">提交时间 {{ currentDraft.created_at }}</span>
          <span v-if="currentDraft.missing_fields?.length" class="draft-warn">
            待补 {{ currentDraft.missing_fields.length }} 项字段
          </span>
          <div class="draft-bar-right">
            <el-select
              v-if="drafts.length > 1"
              v-model="activeDraftId"
              size="small"
              class="draft-version"
              @change="onSwitchDraft"
            >
              <el-option
                v-for="draft in drafts"
                :key="draft.id"
                :label="`${draft.created_at} · ${labels[draft.state] || draft.state}`"
                :value="draft.id"
              />
            </el-select>
            <el-button v-if="currentDraft.state !== 'approved'" size="small" @click="edit(currentDraft)">
              编辑字段
            </el-button>
            <el-button size="small" :disabled="!previewBytes" @click="download">下载本次预览</el-button>
          </div>
        </div>

        <el-collapse class="draft-source">
          <el-collapse-item title="对照提交时的原订单">
            <el-descriptions :column="2" border size="small">
              <el-descriptions-item label="订单号">{{ sourceOrder.orderNo }}</el-descriptions-item>
              <el-descriptions-item label="购货单位">{{ sourceOrder.customerName }}</el-descriptions-item>
              <el-descriptions-item label="联系人">{{ sourceOrder.contactName }}</el-descriptions-item>
              <el-descriptions-item label="联系电话">{{ sourceOrder.contactPhone }}</el-descriptions-item>
              <el-descriptions-item label="订单金额">{{ sourceOrder.totalAmount }}</el-descriptions-item>
              <el-descriptions-item label="交货地址">{{ sourceOrder.deliveryAddress }}</el-descriptions-item>
            </el-descriptions>
            <el-table :data="sourceOrder.items || []" border size="small">
              <el-table-column prop="productName" label="产品名称" />
              <el-table-column prop="productCode" label="产品编号" />
              <el-table-column prop="quantity" label="数量" width="90" />
              <el-table-column prop="unitPrice" label="单价" width="110" />
            </el-table>
          </el-collapse-item>
        </el-collapse>

        <iframe
          v-if="previewHtml"
          class="contract-page-preview"
          :srcdoc="previewHtml"
          title="合同 Word 页面预览"
          sandbox=""
        />
        <el-empty v-else-if="!busy" description="该版本还没有可用的预览" />
      </template>
    </div>

    <template #footer>
      <div class="draft-footer">
        <span class="draft-footer-hint">{{ footerHint }}</span>
        <div class="draft-footer-actions">
          <el-button @click="visible = false">关闭</el-button>
          <el-button v-if="canDecide" :disabled="busy" @click="decide('rejected')">驳回</el-button>
          <el-button
            v-if="canDecide"
            type="primary"
            :disabled="!verified || busy || !canApproveOrder || !!currentDraft?.missing_fields?.length"
            @click="decide('approved')"
          >
            审批通过
          </el-button>
        </div>
      </div>
    </template>

    <el-dialog v-model="editVisible" title="编辑合同草稿字段" width="760px" append-to-body>
      <el-form label-width="140px">
        <el-form-item v-for="entry in editableFields" :key="entry.key" :label="fieldLabels[entry.key] || entry.key">
          <el-input
            v-model="editFields[entry.key]"
            :type="entry.key === 'remark' || entry.key === 'special_requirements' ? 'textarea' : 'text'"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="busy" @click="saveFields">保存</el-button>
      </template>
    </el-dialog>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { contractPreviewHtml } from '../utils/contractPreview'
import { apiGet, apiPost, apiPut } from '../utils/request'

type Draft = {
  id: string
  state: string
  preview_hash: string
  source_order_no: string
  created_at: string
  source_order_snapshot: Record<string, any>
  fields: Record<string, string>
  missing_fields: string[]
}

const props = defineProps<{
  /** 通过订单本身（含库存校验）；返回 false 时合同附件不会归档。 */
  confirmOrderApprove: () => Promise<boolean>
  /** 当前订单是否还能通过；不能通过时只允许查看合同。 */
  canApproveOrder: boolean
}>()

const emit = defineEmits<{
  (event: 'done'): void
  (event: 'approve-order'): void
}>()

const visible = ref(false)
const busy = ref(false)
const loading = ref(false)
const orderNo = ref('')
const drafts = ref<Draft[]>([])
const activeDraftId = ref('')
const previewHtml = ref('')
const previewBytes = ref<ArrayBuffer>()
const verified = ref(false)
const sourceOrder = ref<Record<string, any>>({})
const editVisible = ref(false)
const editFields = ref<Record<string, string>>({})
const editableFields = ref<{ key: string }[]>([])
let viewSequence = 0

const labels: Record<string, string> = {
  submitted: '待生成预览',
  preview_ready: '待审批',
  approved: '已归档',
  rejected: '已驳回',
  superseded: '已被替换',
}

const fieldLabels: Record<string, string> = {
  supplier_name: '供方',
  dealer_name: '需方',
  office_name: '所属办事处',
  signed_date: '签订时间',
  item1_product: '第1行 产品名称',
  item1_spec: '第1行 规格型号',
  item1_qty: '第1行 数量',
  item1_tax: '第1行 税票',
  item2_product: '第2行 产品名称',
  item2_spec: '第2行 规格型号',
  item2_qty: '第2行 数量',
  item2_tax: '第2行 税票',
  item3_product: '第3行 产品名称',
  item3_spec: '第3行 规格型号',
  item3_qty: '第3行 数量',
  item3_tax: '第3行 税票',
  item4_product: '第4行 产品名称',
  item4_spec: '第4行 规格型号',
  item4_qty: '第4行 数量',
  item4_tax: '第4行 税票',
  remark: '备注',
  delivery_date: '交货时间',
  settlement_terms: '结算方式',
  buyer_name: '购货方 名称',
  buyer_address: '购货方 地址',
  contact_name: '购货方 联系人',
  contact_phone: '购货方 联系方式',
  office_branch: '办事处',
  office_contact: '办事处 联系人',
  office_phone: '办事处 联系方式',
  special_requirements: '其他特殊要求',
}

const dialogTitle = computed(() => (orderNo.value ? `合同附件预览与审批 · ${orderNo.value}` : '合同附件预览与审批'))
const currentDraft = computed(() => drafts.value.find((draft) => draft.id === activeDraftId.value) || null)
const canDecide = computed(() => currentDraft.value?.state === 'preview_ready' && props.canApproveOrder)
const footerHint = computed(() => {
  if (!currentDraft.value) return '该订单没有合同附件，可直接审核订单'
  if (currentDraft.value.missing_fields?.length) return `请先补全 ${currentDraft.value.missing_fields.length} 项字段后再审批`
  if (currentDraft.value.state === 'approved') return '该合同附件已归档'
  if (currentDraft.value.state === 'rejected') return '该合同附件已驳回'
  if (!props.canApproveOrder) return '当前订单不可通过，只能查看合同附件'
  if (!verified.value) return '预览加载中…'
  return '请核对固定条款、产品数量、单价、结算期限及签署信息'
})

const stateType = (state: string) => {
  if (state === 'approved') return 'success' as const
  if (state === 'rejected') return 'danger' as const
  if (state === 'preview_ready') return 'warning' as const
  return 'info' as const
}

// 接口错误已由 request 拦截器统一提示，这里只补前端自身抛出的错误，避免弹两条。
const notifyError = (error: any, fallback: string) => {
  if (error?.response) return
  ElMessage.error(error?.message || fallback)
}

function reset() {
  viewSequence += 1
  orderNo.value = ''
  drafts.value = []
  activeDraftId.value = ''
  previewHtml.value = ''
  previewBytes.value = undefined
  verified.value = false
  sourceOrder.value = {}
  busy.value = false
  loading.value = false
}

async function openForOrder(no: string) {
  const normalizedOrderNo = String(no || '').trim()
  if (!normalizedOrderNo) {
    ElMessage.warning('订单号为空，无法加载合同附件')
    return
  }
  reset()
  orderNo.value = normalizedOrderNo
  visible.value = true
  await loadDrafts()
}

async function loadDrafts() {
  loading.value = true
  busy.value = true
  try {
    const list = await apiGet<Draft[]>('/contract-drafts/local', {
      params: { order_no: orderNo.value },
      timeout: 65000,
    })
    drafts.value = Array.isArray(list) ? list : []
    if (drafts.value.length === 0) return
    const preferred = drafts.value.find((draft) => draft.state !== 'approved') || drafts.value[0]
    activeDraftId.value = preferred.id
    await showPreview(preferred)
  } catch (error: any) {
    notifyError(error, '加载合同附件失败')
  } finally {
    loading.value = false
    busy.value = false
  }
}

async function showPreview(draft: Draft) {
  const sequence = ++viewSequence
  previewHtml.value = ''
  previewBytes.value = undefined
  verified.value = false
  sourceOrder.value = draft.source_order_snapshot || {}
  busy.value = true
  try {
    let row = draft
    if (row.state === 'submitted') {
      row = await apiPost<Draft>(`/contract-drafts/local/${row.id}/prepare`, {}, { timeout: 120000 })
      const index = drafts.value.findIndex((item) => item.id === row.id)
      if (index >= 0) drafts.value[index] = row
      activeDraftId.value = row.id
    }
    if (!row.preview_hash) return
    const bytes = await apiGet<ArrayBuffer>(`/contract-drafts/local/${row.id}/preview`, {
      params: { previewHash: row.preview_hash },
      responseType: 'arraybuffer',
      timeout: 65000,
    })
    const html = await contractPreviewHtml(bytes)
    if (sequence !== viewSequence) return
    previewHtml.value = html
    previewBytes.value = bytes
    verified.value = true
  } catch (error: any) {
    if (sequence === viewSequence) notifyError(error, '预览加载失败')
  } finally {
    if (sequence === viewSequence) busy.value = false
  }
}

async function onSwitchDraft() {
  const draft = currentDraft.value
  if (!draft) return
  await showPreview(draft)
}

function edit(draft: Draft) {
  editFields.value = { ...draft.fields }
  editableFields.value = Object.keys(draft.fields || {}).map((key) => ({ key }))
  editVisible.value = true
}

async function saveFields() {
  const draft = currentDraft.value
  if (!draft) return
  busy.value = true
  try {
    const updated = await apiPut<Draft>(`/contract-drafts/local/${draft.id}`, { fields: editFields.value }, { timeout: 65000 })
    const index = drafts.value.findIndex((item) => item.id === draft.id)
    if (index >= 0 && updated) drafts.value[index] = updated
    editVisible.value = false
    ElMessage.success('草稿字段已保存')
    await loadDrafts()
  } catch (error: any) {
    notifyError(error, '保存失败')
  } finally {
    busy.value = false
  }
}

function download() {
  const draft = currentDraft.value
  if (!previewBytes.value || !draft) return
  const url = URL.createObjectURL(
    new Blob([previewBytes.value], { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' }),
  )
  const link = document.createElement('a')
  link.href = url
  link.download = `contract-${orderNo.value || draft.id}.docx`
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 10000)
}

async function decide(decision: 'approved' | 'rejected') {
  const draft = currentDraft.value
  if (!draft || !verified.value) return
  let note = ''
  try {
    if (decision === 'rejected') {
      note = (
        await ElMessageBox.prompt('填写驳回原因', '驳回合同附件', {
          inputType: 'textarea',
          inputValidator: (value) => (String(value || '').trim() ? true : '请填写原因'),
        })
      ).value
    } else {
      await ElMessageBox.confirm(
        `确认已核对订单 ${orderNo.value} 的合同附件？通过后将归档该附件并同步通过订单。`,
        '审批合同附件',
        { confirmButtonText: '审批通过', cancelButtonText: '再看看' },
      )
    }
  } catch {
    return
  }

  busy.value = true
  try {
    if (decision === 'approved') {
      // 先过订单（含库存校验）：订单过不了就不要归档附件，避免出现"附件已归档但订单未通过"。
      const orderApproved = await props.confirmOrderApprove()
      if (!orderApproved) return
    }
    await apiPost(
      `/contract-drafts/local/${draft.id}/review`,
      { decision, previewHash: draft.preview_hash, note },
      { timeout: 65000 },
    )
    ElMessage.success(decision === 'approved' ? '审批通过，合同附件已归档' : '已驳回')
    visible.value = false
    emit('done')
  } catch (error: any) {
    notifyError(error, '操作失败')
  } finally {
    busy.value = false
  }
}

function approveWithoutDraft() {
  visible.value = false
  emit('approve-order')
}

defineExpose({ openForOrder })
</script>

<style scoped>
.draft-wrap {
  min-height: 240px;
}

.draft-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 10px;
  font-size: 13px;
  color: var(--color-gray-600);
}

.draft-meta strong {
  color: var(--color-gray-900);
}

.draft-warn {
  color: #d97706;
  font-weight: 600;
}

.draft-bar-right {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 8px;
}

.draft-version {
  width: 240px;
}

.draft-source {
  margin-bottom: 10px;
}

.contract-page-preview {
  display: block;
  width: 100%;
  height: 62vh;
  min-height: 420px;
  border: 1px solid #dcdfe6;
  background: #e9edf2;
}

.draft-footer {
  display: flex;
  align-items: center;
  gap: 12px;
}

.draft-footer-hint {
  flex: 1;
  min-width: 0;
  text-align: left;
  color: var(--color-gray-500);
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.draft-footer-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
</style>
