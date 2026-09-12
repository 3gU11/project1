<template>
  <div class="page photo-task-page">
    <div class="head">
      <div><h1>📷 拍照任务管理</h1><div class="muted">集中查看 mobile 收集的机台照片、识别结果和确认状态。</div></div>
      <el-button type="primary" :loading="loading" @click="load">刷新</el-button>
    </div>
    <div class="filters">
      <el-input v-model="filters.serialNo" clearable placeholder="按机台流水号搜索" @keyup.enter="load" />
      <el-select v-model="filters.status" clearable placeholder="全部状态" @change="load">
        <el-option v-for="item in statusOptions" :key="item.value" :label="item.label" :value="item.value" />
      </el-select>
      <el-button @click="reset">重置</el-button>
    </div>
    <div class="stats">
      <el-statistic title="任务总数" :value="rows.length" />
      <el-statistic title="已完成" :value="countBy('completed')" />
      <el-statistic title="待确认" :value="countBy('manual_review')" />
      <el-statistic title="待上传" :value="countBy('pending')" />
    </div>
    <el-alert v-if="!filters.serialNo" title="请先在机台档案中选择一台机台" type="info" :closable="false" />
    <el-table v-if="false" :data="machineRows" border stripe size="small" class="machine-table" row-key="serial_no">
      <el-table-column prop="serial_no" label="机台流水号" min-width="160" />
      <el-table-column prop="model_name" label="机型" min-width="130" />
      <el-table-column label="收集进度" width="150"><template #default="{ row }">{{ row.done }}/{{ row.total }}（{{ row.progress }}%）</template></el-table-column>
      <el-table-column label="任务状态" width="120"><template #default="{ row }"><el-tag :type="statusType(row.overallStatus)" size="small">{{ statusText(row.overallStatus) }}</el-tag></template></el-table-column>
      <el-table-column prop="lastUploadedBy" label="最近收集人" width="130" />
      <el-table-column prop="lastUploadedAt" label="最近收集时间" width="175" />
      <el-table-column label="操作" width="90"><template #default="{ row }"><el-button link type="primary" @click="showMachine(row.serial_no)">明细</el-button></template></el-table-column>
    </el-table>
    <el-divider v-if="filters.serialNo" content-position="left">当前机台拍照项明细</el-divider>
    <el-table v-if="filters.serialNo" v-loading="loading" :data="rows" border stripe size="small" row-key="id">
      <el-table-column prop="serial_no" label="机台流水号" min-width="150" />
      <el-table-column prop="model_name" label="机型" min-width="130" />
      <el-table-column label="拍照项" min-width="180"><template #default="{ row }">{{ row.position_code }} {{ row.item_name }}</template></el-table-column>
      <el-table-column label="完整组件编号" min-width="170"><template #default="{ row }"><span v-if="taskCode(row)">{{ row.position_code }}{{ taskCode(row) }}</span><span v-else class="muted">未填写</span></template></el-table-column>
      <el-table-column label="要求" width="80"><template #default="{ row }"><el-tag :type="row.required ? 'danger' : 'info'" size="small">{{ row.required ? '必拍' : '选拍' }}</el-tag></template></el-table-column>
      <el-table-column label="状态" width="110"><template #default="{ row }"><el-tag :type="statusType(row.status)" size="small">{{ statusText(row.status) }}</el-tag></template></el-table-column>
      <el-table-column prop="file_name" label="照片文件" min-width="170" show-overflow-tooltip />
      <el-table-column prop="uploaded_by" label="收集人" width="120" />
      <el-table-column prop="uploaded_at" label="上传时间" width="175" />
      <el-table-column label="OCR" width="90"><template #default="{ row }">{{ row.ocr_enabled ? (row.ocr_results?.length ? '有结果' : '待识别') : '不适用' }}</template></el-table-column>
      <el-table-column label="操作" width="90" fixed="right"><template #default="{ row }"><el-button link type="primary" @click="openDetail(row)">详情</el-button></template></el-table-column>
    </el-table>
    <el-dialog v-model="detailVisible" title="拍照任务详情" width="620px">
      <template v-if="selected">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="机台流水号">{{ selected.serial_no }}</el-descriptions-item><el-descriptions-item label="机型">{{ selected.model_name }}</el-descriptions-item>
          <el-descriptions-item label="拍照项">{{ selected.position_code }} {{ selected.item_name }}</el-descriptions-item><el-descriptions-item label="状态">{{ statusText(selected.status) }}</el-descriptions-item>
          <el-descriptions-item label="文件名" :span="2">{{ selected.file_name || '尚未上传' }}</el-descriptions-item>
        </el-descriptions>
        <el-empty v-if="!selected.ocr_results?.length" description="暂无 OCR 结果" />
        <el-table v-else :data="selected.ocr_results" border size="small" class="ocr-table">
          <el-table-column prop="field_name" label="字段" /><el-table-column prop="display_value" label="结果" /><el-table-column prop="check_status" label="校验状态" /><el-table-column prop="recognition_source" label="来源" />
        </el-table>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { apiGet, getApiErrorMessage } from '../utils/request'
type OCRResult = { field_name?: string; display_value?: string; manual_value?: string; recognized_value?: string; check_status?: string; recognition_source?: string }
type Task = { id: number; serial_no: string; model_name: string; position_code: string; item_name: string; required: boolean; status: string; file_name?: string; uploaded_by?: string; uploaded_at?: string; ocr_enabled: boolean; ocr_results?: OCRResult[] }
const props = defineProps<{ serialNo?: string }>()
const statusOptions = [{ value: 'pending', label: '待上传' }, { value: 'uploaded', label: '已上传' }, { value: 'manual_review', label: '待确认' }, { value: 'completed', label: '已完成' }, { value: 'manual_passed', label: '人工通过' }, { value: 'retake_required', label: '需补拍' }, { value: 'skipped', label: '已跳过' }]
const filters = reactive({ serialNo: '', status: '' }); const rows = ref<Task[]>([]); const loading = ref(false); const selected = ref<Task | null>(null); const detailVisible = ref(false)
const route = useRoute()
const machineRows = computed(() => Array.from(rows.value.reduce((map, task) => { const current = map.get(task.serial_no) || { serial_no: task.serial_no, model_name: task.model_name, total: 0, done: 0, lastUploadedBy: '', lastUploadedAt: '', tasks: [] as Task[] }; current.total += 1; current.tasks.push(task); if (['completed', 'manual_passed'].includes(task.status)) current.done += 1; if (task.uploaded_at && task.uploaded_at >= current.lastUploadedAt) { current.lastUploadedAt = task.uploaded_at; current.lastUploadedBy = task.uploaded_by || '-' }; map.set(task.serial_no, current); return map }, new Map<string, any>()).values()).map((row) => ({ ...row, progress: row.total ? Math.round(row.done / row.total * 100) : 0, overallStatus: row.done === row.total ? 'completed' : row.tasks.some((task: Task) => task.status === 'manual_review') ? 'manual_review' : 'pending' })))
const statusText = (status: string) => statusOptions.find((item) => item.value === status)?.label || status || '-'
const statusType = (status: string) => status === 'completed' || status === 'manual_passed' ? 'success' : status === 'manual_review' ? 'warning' : status === 'retake_required' ? 'danger' : 'info'
const countBy = (status: string) => rows.value.filter((row) => row.status === status).length
const taskCode = (task: Task) => {
  const field = task.ocr_results?.find((item) => [item.display_value, item.manual_value, item.recognized_value].some((value) => String(value || '').trim()))
  return String(field?.display_value || field?.manual_value || field?.recognized_value || '').trim()
}
const load = async () => { loading.value = true; try { const params = new URLSearchParams(); if (filters.serialNo) params.set('serial_no', filters.serialNo); if (filters.status) params.set('status', filters.status); const query = params.toString(); const res = await apiGet<{ data?: Task[] }>('/photo-tasks' + (query ? '?' + query : '')); rows.value = res.data || [] } catch (error) { ElMessage.error(getApiErrorMessage(error) || '拍照任务加载失败') } finally { loading.value = false } }
const reset = () => { filters.serialNo = props.serialNo || ''; filters.status = ''; if (filters.serialNo) load(); else rows.value = [] }; const openDetail = (row: Task) => { selected.value = row; detailVisible.value = true }; const showMachine = (serialNo: string) => { const first = rows.value.find((row) => row.serial_no === serialNo); if (first) openDetail(first) }
const applyRouteFilter = () => { filters.serialNo = props.serialNo || (typeof route.query.serial_no === 'string' ? route.query.serial_no : ''); if (filters.serialNo) load(); else rows.value = [] }
onMounted(applyRouteFilter)
watch(() => route.query.serial_no, applyRouteFilter)
watch(() => props.serialNo, applyRouteFilter)
</script>
<style scoped>
.photo-task-page { min-height: 100%; }.filters { display: flex; gap: 12px; margin: 18px 0; max-width: 760px; }.filters .el-input { width: 250px; }.filters .el-select { width: 160px; }.stats { display: flex; gap: 48px; margin: 16px 0 20px; }.management-tip { margin-bottom: 14px; }.machine-table { margin-bottom: 16px; }.ocr-table { margin-top: 18px; }.muted { color: var(--el-text-color-secondary); font-size: 13px; }
</style>
