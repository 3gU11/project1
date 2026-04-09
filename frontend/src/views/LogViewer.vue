<template>
  <div class="page">
    <div class="head">
      <h1>📜 交易日志</h1>
      <el-button type="primary" :loading="loading" @click="loadLogs">刷新</el-button>
    </div>
    <el-table :data="logs" border stripe size="small" height="620">
      <el-table-column prop="时间" label="时间" width="180" />
      <el-table-column prop="操作类型" label="操作类型" width="140" />
      <el-table-column prop="流水号" label="流水号" width="180" />
      <el-table-column prop="操作员" label="操作员" width="140" />
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { apiGet, getApiErrorMessage } from '../utils/request'
type ListResponse<T = any> = { data: T[] }

const loading = ref(false)
const logs = ref<any[]>([])

const loadLogs = async () => {
  loading.value = true
  try {
    const res = await apiGet<ListResponse>('/logs/transactions', { params: { limit: 1000 } })
    logs.value = res.data || []
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '读取日志失败')
  } finally {
    loading.value = false
  }
}

loadLogs()
</script>

<style scoped>
.head{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}.head h1{margin:0;font-size:30px}
</style>
