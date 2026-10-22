<template>
  <el-dialog v-model="visible" title="合同附件审批（不排产）" width="92%" @opened="load">
    <p>先生成并查看预览，再审批。通过后归档的附件与本次预览一致。</p>
    <el-button :loading="busy" @click="load">刷新</el-button>
    <el-table :data="rows" v-loading="busy" border empty-text="本页暂无未归档合同附件">
      <el-table-column prop="source_order_no" label="订单编号" width="140" />
      <el-table-column prop="created_at" label="提交时间" width="210" />
      <el-table-column label="版本" min-width="150"><template #default="{ row }">{{ row.id }}</template></el-table-column>
      <el-table-column label="状态" width="100"><template #default="{ row }">{{ labels[row.state] || row.state }}</template></el-table-column>
      <el-table-column label="字段完整度" min-width="150"><template #default="{ row }">{{ row.missing_fields?.length ? `待补 ${row.missing_fields.length} 项` : '字段齐全' }}</template></el-table-column>
      <el-table-column label="操作" width="220"><template #default="{ row }">
        <el-button v-if="row.state !== 'approved'" size="small" @click="edit(row)">编辑字段</el-button>
        <el-button v-if="row.state === 'submitted'" size="small" @click="prepare(row)">生成预览</el-button>
        <el-button v-if="row.preview_hash" size="small" @click="view(row)">查看预览</el-button>
      </template></el-table-column>
    </el-table>
    <el-pagination v-model:current-page="page" :page-size="100" layout="prev, pager, next" :total="(page - 1) * 100 + fetchedCount + (fetchedCount === 100 ? 1 : 0)" @current-change="load" />
    <el-dialog v-model="previewVisible" append-to-body title="核对合同预览" width="85%">
      <p>请核对固定条款、产品数量、单价、结算期限及签署信息。以下按 Word 页面布局显示，可下载原文件核对。</p>
      <el-button @click="download">下载本次预览</el-button>
      <el-collapse><el-collapse-item title="对照提交时的原订单">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="订单号">{{ sourceOrder.orderNo }}</el-descriptions-item>
          <el-descriptions-item label="购货单位">{{ sourceOrder.customerName }}</el-descriptions-item>
          <el-descriptions-item label="联系人">{{ sourceOrder.contactName }}</el-descriptions-item>
          <el-descriptions-item label="联系电话">{{ sourceOrder.contactPhone }}</el-descriptions-item>
          <el-descriptions-item label="订单金额">{{ sourceOrder.totalAmount }}</el-descriptions-item>
          <el-descriptions-item label="交货地址">{{ sourceOrder.deliveryAddress }}</el-descriptions-item>
        </el-descriptions>
        <el-table :data="sourceOrder.items || []" border>
          <el-table-column prop="productName" label="产品名称" />
          <el-table-column prop="productCode" label="产品编号" />
          <el-table-column prop="quantity" label="数量" />
          <el-table-column prop="unitPrice" label="单价" />
        </el-table>
      </el-collapse-item></el-collapse>
      <iframe v-if="previewVisible" class="contract-page-preview" :srcdoc="previewHtml" title="合同 Word 页面预览" sandbox="" />
      <template #footer>
        <el-button v-if="selected?.state === 'preview_ready'" :disabled="!verified || busy" @click="decide('rejected')">驳回</el-button>
        <el-button v-if="selected?.state === 'preview_ready'" type="primary" :disabled="!verified || busy || !!selected.missing_fields?.length" @click="decide('approved')">审批通过并归档附件</el-button>
      </template>
    </el-dialog>
    <el-dialog v-model="editVisible" title="编辑合同草稿字段" width="760px" append-to-body>
      <el-form label-width="140px">
        <el-form-item v-for="entry in editableFields" :key="entry.key" :label="fieldLabels[entry.key] || entry.key">
          <el-input v-model="editFields[entry.key]" :type="entry.key === 'remark' || entry.key === 'special_requirements' ? 'textarea' : 'text'" />
        </el-form-item>
      </el-form>
      <template #footer><el-button @click="editVisible=false">取消</el-button><el-button type="primary" :loading="busy" @click="saveFields">保存</el-button></template>
    </el-dialog>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { contractPreviewHtml } from '../utils/contractPreview'
import { apiGet, apiPost, apiPut } from '../utils/request'
type Draft = { id: string; state: string; preview_hash: string; source_order_no: string; created_at: string; source_order_snapshot: Record<string, any>; fields: Record<string, string>; missing_fields: string[] }
const visible = ref(false), busy = ref(false), page = ref(1)
const fetchedCount = ref(0)
const rows = ref<Draft[]>([]), selected = ref<Draft>(), previewVisible = ref(false)
const editVisible = ref(false), editFields = ref<Record<string, string>>({})
const previewHtml = ref(''), verified = ref(false)
const sourceOrder = ref<Record<string, any>>({})
let previewBytes: ArrayBuffer | undefined
let viewSequence = 0
const labels: Record<string,string> = { submitted: '待生成预览', preview_ready: '待审批', approved: '已归档', rejected: '已驳回', superseded: '已被替换' }
const fieldLabels: Record<string,string> = { supplier_name:'供方名称', contract_no:'合同编号', buyer_name:'购货单位', signing_place:'签订地点', signed_date:'签订日期', delivery_date:'交货时间', settlement_terms:'结算方式及期限', total_upper:'合计金额大写', buyer_address:'购货单位地址', contact_name:'联系人', contact_phone:'联系电话', special_requirements:'特殊要求', remark:'备注' }
const editableFields = ref<{key:string}[]>([])
defineExpose({ open: () => { visible.value = true } })
async function load() {
  busy.value = true
  try {
    const drafts = await apiGet<Draft[]>('/contract-drafts/local', { params: { page: page.value }, timeout: 65000 })
    fetchedCount.value = drafts.length
    rows.value = drafts.filter(draft => draft.state !== 'approved')
  }
  finally { busy.value = false }
}
async function prepare(row: Draft) {
  busy.value = true
  try { await apiPost(`/contract-drafts/local/${row.id}/prepare`, {}, { timeout: 120000 }); await load() }
  finally { busy.value = false }
}
function edit(row: Draft) {
  selected.value = row
  editFields.value = { ...row.fields }
  editableFields.value = Object.keys(row.fields).map(key => ({ key }))
  editVisible.value = true
}
async function saveFields() {
  if (!selected.value) return
  busy.value = true
  try {
    await apiPut(`/contract-drafts/local/${selected.value.id}`, { fields: editFields.value }, { timeout: 65000 })
    editVisible.value = false
    ElMessage.success('草稿字段已保存')
    await load()
  } finally { busy.value = false }
}
async function view(row: Draft) {
  const sequence = ++viewSequence
  selected.value = row; verified.value = false; previewHtml.value = ''; previewBytes = undefined
  sourceOrder.value = row.source_order_snapshot || {}
  busy.value = true
  try {
    const bytes = await apiGet<ArrayBuffer>(`/contract-drafts/local/${row.id}/preview`, { params: { previewHash: row.preview_hash }, responseType: 'arraybuffer', timeout: 65000 })
    const html = await contractPreviewHtml(bytes)
    if (sequence !== viewSequence) return
    previewHtml.value = html
    previewBytes = bytes; verified.value = true; previewVisible.value = true
  } catch (error: any) { ElMessage.error(error.message || '预览加载失败') }
  finally { if (sequence === viewSequence) busy.value = false }
}
function download() {
  if (!previewBytes || !selected.value) return
  const url = URL.createObjectURL(new Blob([previewBytes], { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' }))
  const link = document.createElement('a'); link.href = url; link.download = `contract-${selected.value.id}.docx`; link.click()
  setTimeout(() => URL.revokeObjectURL(url), 10000)
}
async function decide(decision: 'approved' | 'rejected') {
  if (!selected.value || !verified.value) return
  let note = ''
  try {
    if (decision === 'rejected') note = (await ElMessageBox.prompt('填写驳回原因', '驳回合同', { inputValidator: value => !!value?.trim() || '请填写原因' })).value
    else await ElMessageBox.confirm('确认已核对该版本预览？通过后仅归档合同附件，不会排产。', '审批合同')
  } catch { return }
  busy.value = true
  try {
    await apiPost(`/contract-drafts/local/${selected.value.id}/review`, { decision, previewHash: selected.value.preview_hash, note }, { timeout: 65000 })
    previewVisible.value = false; ElMessage.success(decision === 'approved' ? '审批通过，附件已归档' : '已驳回'); await load()
  } finally { busy.value = false }
}
</script>

<style scoped>
.contract-page-preview { display: block; width: 100%; height: 68vh; min-height: 460px; border: 1px solid #dcdfe6; background: #e9edf2; }
</style>
