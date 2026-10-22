<template><div class="workflow-page"><div class="page-head"><div><h1>流程任务</h1><p class="intro">查看流程节点处理结果和待处理任务。</p></div><el-button :loading="loading" @click="load">刷新</el-button></div><div class="toolbar"><el-select v-model="status" clearable placeholder="全部状态" @change="load"><el-option label="已结束" value="已结束"/><el-option label="处理中" value="处理中"/><el-option label="待处理" value="待处理"/></el-select><el-button @click="load">查询</el-button></div><el-table v-loading="loading" :data="rows" stripe><el-table-column prop="id" label="任务编号" width="100"/><el-table-column prop="instance_id" label="实例编号" width="100"/><el-table-column prop="node_type" label="节点类型" min-width="120"/><el-table-column prop="assignee_id" label="处理人" min-width="120"/><el-table-column label="状态" width="100"><template #default="{ row }"><el-tag :type="row.status === '已结束' ? 'success' : 'warning'" effect="light">{{ row.status }}</el-tag></template></el-table-column><el-table-column prop="decision" label="决定" width="90"/><el-table-column label="分配时间" min-width="170"><template #default="{ row }">{{ formatTime(row.assigned_at) }}</template></el-table-column><el-table-column label="完成时间" min-width="170"><template #default="{ row }">{{ formatTime(row.completed_at) }}</template></el-table-column></el-table><el-empty v-if="!loading && rows.length === 0" description="暂无流程任务"/></div></template>
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { apiGet } from '../../utils/request'
const loading = ref(false)
const rows = ref<any[]>([])
const status = ref('')
const formatTime = (value: any) => value ? String(value).replace('T', ' ').slice(0, 19) : '-'
const load = async () => {
  loading.value = true
  try {
    const query = status.value ? `&status=${encodeURIComponent(status.value)}` : ''
    const response = await apiGet<{ data: any[] }>(`/workflows/tasks?limit=100${query}`)
    rows.value = response.data || []
  } finally {
    loading.value = false
  }
}
onMounted(load)
</script>
<style scoped>.workflow-page{padding:28px;max-width:1500px}.page-head{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:20px}h1{margin:0 0 8px;font-size:24px;color:#1f2937}.intro{color:#64748b}</style>
