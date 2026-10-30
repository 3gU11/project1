<template><div class="workflow-page"><div class="page-head"><div><h1>流程实例</h1><p class="intro">查看业务单据触发的工作流运行记录。</p></div><el-button :loading="loading" @click="load">刷新</el-button></div><div class="toolbar"><el-select v-model="status" clearable placeholder="全部状态" @change="load"><el-option label="已完成" value="已完成"/><el-option label="处理中" value="处理中"/><el-option label="失败" value="失败"/></el-select><el-input v-model="businessId" clearable placeholder="业务单据号" @keyup.enter="load"/><el-button @click="load">查询</el-button></div><el-table v-loading="loading" :data="rows" stripe><el-table-column prop="instance_no" label="实例编号" min-width="220"/><el-table-column prop="workflow_key" label="流程 Key" min-width="170"/><el-table-column prop="business_type" label="业务类型" width="120"/><el-table-column prop="business_id" label="业务单据号" min-width="160"/><el-table-column label="状态" width="100"><template #default="{ row }"><el-tag :type="statusType(row.status)" effect="light">{{ row.status }}</el-tag></template></el-table-column><el-table-column prop="result" label="结果" width="90"/><el-table-column label="创建时间" min-width="170"><template #default="{ row }">{{ formatTime(row.created_at) }}</template></el-table-column><el-table-column label="完成时间" min-width="170"><template #default="{ row }">{{ formatTime(row.completed_at) }}</template></el-table-column></el-table><el-empty v-if="!loading && rows.length === 0" description="暂无流程实例"/></div></template>
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { apiGet } from '../../utils/request'
const loading = ref(false)
const rows = ref<any[]>([])
const status = ref('')
const businessId = ref('')
const formatTime = (value: any) => value ? String(value).replace('T', ' ').slice(0, 19) : '-'
const statusType = (value: string) => value === '已完成' ? 'success' : value === '失败' ? 'danger' : 'warning'
const load = async () => {
  loading.value = true
  try {
    const params = new URLSearchParams({ limit: '100' }); if (status.value) params.set('status', status.value); if (businessId.value) params.set('business_id', businessId.value)
    const response = await apiGet<{ data: any[] }>(`/workflows/instances?${params}`)
    rows.value = response.data || []
  } finally {
    loading.value = false
  }
}
onMounted(load)
</script>
<style scoped>.workflow-page{padding:28px;max-width:1500px}.page-head{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:20px}h1{margin:0 0 8px;font-size:24px;color:#1f2937}.intro{color:#64748b}</style>
