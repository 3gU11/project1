<template>
  <div class="workflow-page">
    <div class="page-head"><div><h1>重入库任务</h1><p class="intro">处理逆向操作产生的机台重入库任务。</p></div><el-button :loading="loading" @click="load">刷新</el-button></div>
    <el-table v-loading="loading" :data="rows" stripe>
      <el-table-column prop="task_no" label="任务编号" min-width="250" />
      <el-table-column prop="object_id" label="机台流水号" min-width="150" />
      <el-table-column prop="task_type" label="任务类型" width="110" />
      <el-table-column prop="source_instance_no" label="来源流程" min-width="220" />
      <el-table-column prop="status" label="状态" width="110"><template #default="{ row }"><el-tag type="warning">{{ row.status }}</el-tag></template></el-table-column>
      <el-table-column prop="created_at" label="创建时间" min-width="170" />
      <el-table-column label="操作" fixed="right" width="150"><template #default="{ row }"><el-button type="primary" size="small" @click="complete(row)">选择库位入库</el-button></template></el-table-column>
    </el-table>
    <el-empty v-if="!loading && rows.length === 0" description="暂无待处理重入库任务" />
  </div>
</template>
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { apiGet, apiPost } from '../../utils/request'
const loading = ref(false); const rows = ref<any[]>([])
const load = async () => { loading.value = true; try { const response = await apiGet<{ data: any[] }>('/workflows/derived-tasks'); rows.value = response.data || [] } finally { loading.value = false } }
const complete = async (row: any) => {
  const prompt = await ElMessageBox.prompt(`请输入机台 ${row.object_id} 的目标库位`, '执行重入库', { inputValidator: (v: string) => v.trim() ? true : '库位不能为空' }).catch(() => null)
  if (!prompt) return
  try {
    const result = await apiPost<any>('/inventory/inbound-to-slot', { serial_no: row.object_id, slot_code: prompt.value.trim() })
    if ((result as any)?.approval_pending) { ElMessage.info((result as any).message + '（' + (result as any).instance_no + '）'); window.dispatchEvent(new Event('workflow-pending-updated')); return }
    
    if (!result?.ok) throw new Error(result?.message || '入库失败')
    await apiPost(`/workflows/derived-tasks/${encodeURIComponent(row.task_no)}/complete`, { reason: `入库工作台确认，库位：${prompt.value.trim()}` })
    ElMessage.success('入库完成，重入库任务已关闭')
    window.dispatchEvent(new Event('workflow-pending-updated'))
    await load()
  } catch (err: any) { ElMessage.error(err?.message || '重入库失败') }
}
onMounted(load)
</script>
<style scoped>.workflow-page{padding:28px;max-width:1500px}.page-head{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:18px}h1{margin:0 0 8px;font-size:24px;color:#1f2937}.intro{margin:0;color:#64748b}</style>
