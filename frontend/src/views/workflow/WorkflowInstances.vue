<template><div class="workflow-page"><div class="page-head"><div><h1>流程实例</h1><p class="intro">查看业务单据触发的工作流运行记录。</p></div><el-button :loading="loading" @click="load">刷新</el-button></div><div class="toolbar"><el-select v-model="status" clearable placeholder="全部状态" @change="search"><el-option label="已完成" value="已完成"/><el-option label="处理中" value="处理中"/><el-option label="失败" value="失败"/></el-select><el-input v-model="businessId" clearable placeholder="业务单据号" @keyup.enter="search"/><el-button @click="search">查询</el-button></div><el-table v-loading="loading" :data="rows" stripe><el-table-column prop="instance_no" label="实例编号" min-width="220"/><el-table-column prop="workflow_key" label="流程 Key" min-width="170"/><el-table-column prop="business_type" label="业务类型" width="120"/><el-table-column prop="business_id" label="业务单据号" min-width="160"/><el-table-column label="状态" width="100"><template #default="{ row }"><el-tag :type="statusType(row.status)" effect="light">{{ row.status }}</el-tag></template></el-table-column><el-table-column prop="result" label="结果" width="90"/><el-table-column label="创建时间" min-width="170"><template #default="{ row }">{{ formatTime(row.created_at) }}</template></el-table-column><el-table-column label="完成时间" min-width="170"><template #default="{ row }">{{ formatTime(row.completed_at) }}</template></el-table-column><el-table-column label="操作" width="140"><template #default="{ row }"><el-button v-if="row.status === '执行异常'" link type="danger" @click="abandon(row)">作废并释放</el-button></template></el-table-column></el-table><div v-if="total > 0" class="pager"><el-pagination v-model:current-page="page" :page-size="pageSize" :total="total" layout="total, prev, pager, next" @current-change="load"/></div><el-empty v-if="!loading && rows.length === 0" description="暂无流程实例"/></div></template>
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { apiGet, apiPost } from '../../utils/request'
// 流程实例按后端分页展示，每页最多 10 条。
const pageSize = 10
const loading = ref(false)
const rows = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const status = ref('')
const businessId = ref('')
const formatTime = (value: any) => value ? String(value).replace('T', ' ').slice(0, 19) : '-'
const statusType = (value: string) => value === '已完成' ? 'success' : value === '失败' ? 'danger' : 'warning'
const abandon = async (row: any) => {
  try {
    const { value } = await ElMessageBox.prompt(
      `作废后该流程会释放对「${row.business_type} ${row.business_id}」的占用，业务数据不会被修改。请填写作废原因：`,
      '作废异常流程',
      { inputPlaceholder: '例如：参数传错，重新发起', confirmButtonText: '确认作废', cancelButtonText: '取消' },
    )
    if (!String(value || '').trim()) { ElMessage.warning('必须填写作废原因'); return }
    await apiPost(`/workflows/instances/${row.instance_no}/abandon`, { reason: value })
    ElMessage.success('已作废并释放业务对象')
    await load()
  } catch (err: any) {
    if (err === 'cancel' || err === 'close') return
    ElMessage.error(err?.response?.data?.detail || '作废失败')
  }
}
const load = async (): Promise<void> => {
  loading.value = true
  try {
    const params = new URLSearchParams({ skip: String((page.value - 1) * pageSize), limit: String(pageSize) })
    if (status.value) params.set('status', status.value)
    if (businessId.value) params.set('business_id', businessId.value)
    const response = await apiGet<{ data: any[]; total?: number }>(`/workflows/instances?${params}`)
    rows.value = response.data || []
    total.value = Number(response.total ?? rows.value.length) || 0
    // 作废或筛选后当前页可能已超出末页，自动退回最后一页，避免出现空白页。
    const lastPage = Math.max(1, Math.ceil(total.value / pageSize))
    if (page.value > lastPage) { page.value = lastPage; return load() }
  } finally {
    loading.value = false
  }
}
const search = () => { page.value = 1; void load() }
onMounted(load)
</script>
<style scoped>.workflow-page{padding:28px;max-width:1500px}.page-head{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:20px}h1{margin:0 0 8px;font-size:24px;color:#1f2937}.intro{color:#64748b}.pager{display:flex;justify-content:flex-end;margin-top:16px}</style>
