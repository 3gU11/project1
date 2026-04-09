<template>
  <div class="ship-page">
    <div class="head-row">
      <h1 class="title">🚛 发货复核</h1>
      <el-button type="primary" :loading="loading" @click="loadPending">刷新</el-button>
    </div>

    <el-alert :closable="false" type="info" :title="`待发货总数：${pendingRows.length}`" />

    <el-table
      :data="pendingRows"
      border
      stripe
      size="small"
      height="560"
      style="margin-top: 10px"
      @selection-change="onSelectionChange"
    >
      <el-table-column type="selection" width="48" />
      <el-table-column prop="发货时间" label="发货时间" width="120" />
      <el-table-column prop="占用订单号" label="订单号" width="170" />
      <el-table-column prop="客户" label="客户" min-width="140" />
      <el-table-column prop="机型" label="机型" width="140" />
      <el-table-column prop="流水号" label="流水号" width="160" />
      <el-table-column prop="订单备注" label="订单备注" min-width="180" />
      <el-table-column prop="机台备注/配置" label="机台备注/配置" min-width="180" />
    </el-table>

    <div class="ops">
      <el-button type="primary" :loading="saving" @click="confirmShip">🚚 正式发货</el-button>
      <el-button :loading="saving" @click="revertShip">🔄 发货撤回</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { apiGet, apiPost, getApiErrorMessage } from '../utils/request'

type Row = Record<string, any>
type ListResponse<T = any> = { data: T[] }
type MessageResponse = { message?: string }
const loading = ref(false)
const saving = ref(false)
const pendingRows = ref<Row[]>([])
const selectedSerials = ref<string[]>([])

const loadPending = async () => {
  loading.value = true
  try {
    const res = await apiGet<ListResponse>('/inventory/shipping/pending')
    pendingRows.value = res.data || []
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '读取待发货数据失败')
  } finally {
    loading.value = false
  }
}

const onSelectionChange = (rows: Row[]) => {
  selectedSerials.value = rows.map((r) => String(r['流水号'] || '')).filter(Boolean)
}

const confirmShip = async () => {
  if (selectedSerials.value.length === 0) {
    ElMessage.warning('请先勾选至少 1 台机台')
    return
  }
  saving.value = true
  try {
    const res = await apiPost<MessageResponse>('/inventory/shipping/confirm', { serial_nos: selectedSerials.value })
    ElMessage.success(res.message || '发货完成')
    selectedSerials.value = []
    await loadPending()
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '正式发货失败')
  } finally {
    saving.value = false
  }
}

const revertShip = async () => {
  if (selectedSerials.value.length === 0) {
    ElMessage.warning('请先勾选至少 1 台机台')
    return
  }
  saving.value = true
  try {
    const res = await apiPost<MessageResponse>('/inventory/shipping/revert', { serial_nos: selectedSerials.value })
    ElMessage.success(res.message || '撤回成功')
    selectedSerials.value = []
    await loadPending()
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '发货撤回失败')
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  loadPending()
})
</script>

<style scoped>
.head-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
.title {
  margin: 0;
  font-size: 30px;
  font-weight: 800;
  color: #1f2937;
}
.ops {
  margin-top: 10px;
  display: flex;
  gap: 10px;
}
</style>
