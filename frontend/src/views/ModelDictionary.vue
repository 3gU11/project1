<template>
  <div class="page">
    <div class="head">
      <h1>📚 机型字典</h1>
      <div class="ops">
        <el-button :disabled="!hasUnsavedChanges" @click="resetLocalChanges">撤销修改</el-button>
        <el-button :loading="loading" @click="load">刷新</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存字典</el-button>
      </div>
    </div>

    <div class="tip">
      说明：机型字典用于全局机型下拉和排序，保存后立即生效。仅启用项会参与排序。可通过左侧拖拽手柄调整顺序。
    </div>

    <div class="bar">
      <el-button size="small" type="success" @click="addRow">+ 新增机型</el-button>
      <span>共 {{ localRows.length }} 条</span>
      <span v-if="hasUnsavedChanges" class="dirty">有未保存修改</span>
    </div>

    <el-table :data="localRows" :row-key="getRowKey" :row-class-name="getRowClassName" border stripe size="small">
      <el-table-column label="拖拽" width="70" align="center">
        <template #default="scope">
          <div
            class="drag-handle"
            :class="{
              'is-dragging': draggingKey === getRowKey(scope.row),
              'is-over': dragOverKey === getRowKey(scope.row),
            }"
            draggable="true"
            @dragstart="handleDragStart(scope.row)"
            @dragend="handleDragEnd"
            @dragover.prevent
            @dragenter.prevent="handleDragEnter(scope.row)"
            @drop.prevent="handleDrop(scope.row)"
          >
            ⋮⋮
          </div>
        </template>
      </el-table-column>
      <el-table-column label="#" width="70">
        <template #default="scope">{{ scope.$index + 1 }}</template>
      </el-table-column>
      <el-table-column label="机型名称" min-width="220">
        <template #default="scope">
          <el-input v-model="scope.row.model_name" placeholder="例如 FR-400G" />
        </template>
      </el-table-column>
      <el-table-column label="大类" width="150">
        <template #default="scope">
          <el-select v-model="scope.row.model_family" clearable placeholder="选择类别">
            <el-option label="中大型AUTO" value="中大型AUTO" />
            <el-option label="中小型AUTO" value="中小型AUTO" />
            <el-option label="中大型XS" value="中大型XS" />
            <el-option label="中小型XS" value="中小型XS" />
            <el-option label="中小型G" value="中小型G" />
            <el-option label="特殊" value="特殊" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="启用" width="90" align="center">
        <template #default="scope">
          <el-switch v-model="scope.row.enabled" />
        </template>
      </el-table-column>
      <el-table-column label="备注" min-width="220">
        <template #default="scope">
          <el-input v-model="scope.row.remark" placeholder="可选备注" />
        </template>
      </el-table-column>
      <el-table-column label="拍照配置" width="130" align="center">
        <template #default="scope">
          <el-button size="small" type="primary" link :disabled="!scope.row.id" @click="openPhotoConfig(scope.row)">配置</el-button>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="210">
        <template #default="scope">
          <el-button size="small" type="danger" @click="removeRow(scope.$index)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-drawer v-model="photoVisible" :title="`拍照配置 - ${photoModel?.model_name || ''}`" size="760px">
      <div class="photo-toolbar">
        <el-button size="small" @click="loadPhotoConfig" :loading="photoLoading">刷新</el-button>
        <span>配置项 {{ photoRows.length }} 条</span>
      </div>
      <el-table :data="photoRows" border stripe size="small" v-loading="photoLoading">
        <el-table-column prop="position_code" label="位置编码" width="130" />
        <el-table-column prop="item_name" label="拍照项目" min-width="150" />
        <el-table-column prop="shooting_requirement" label="拍摄要求" min-width="180" />
        <el-table-column label="必拍" width="80" align="center"><template #default="{ row }"><el-switch v-model="row.required" /></template></el-table-column>
        <el-table-column label="OCR" width="80" align="center"><template #default="{ row }"><el-switch v-model="row.ocr_enabled" /></template></el-table-column>
        <el-table-column prop="ocr_profile" label="OCR配置" width="140"><template #default="{ row }"><el-input v-model="row.ocr_profile" size="small" /></template></el-table-column>
        <el-table-column label="启用" width="80" align="center"><template #default="{ row }"><el-switch v-model="row.enabled" /></template></el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="photoVisible = false">取消</el-button>
        <el-button type="primary" :loading="photoSaving" @click="savePhotoConfig">保存配置</el-button>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { apiGet, apiPost, getApiErrorMessage } from '../utils/request'
import { useModelDictionaryStore, type ModelDictionaryRow } from '../store/modelDictionary'
import { onBeforeRouteLeave } from 'vue-router'

const store = useModelDictionaryStore()
const loading = ref(false)
const saving = ref(false)
const localRows = ref<ModelDictionaryRow[]>([])
const baselineRows = ref<ModelDictionaryRow[]>([])
const draggingKey = ref('')
const dragOverKey = ref('')
const photoVisible = ref(false)
const photoLoading = ref(false)
const photoSaving = ref(false)
const photoModel = ref<ModelDictionaryRow | null>(null)
const photoRows = ref<any[]>([])
const familyAliases: Record<string, string> = {
  小机G: '中小型G',
  小机XS: '中小型XS',
  '小机/XS': '中小型XS',
  小机AUTO: '中小型AUTO',
  大机XS: '中大型XS',
  大机AUTO: '中大型AUTO',
  SPECIAL: '特殊'
}
const allowedFamilies = new Set(['中大型AUTO', '中小型AUTO', '中大型XS', '中小型XS', '中小型G', '特殊'])

const createTempId = () => {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `tmp-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}

const getRowKey = (row: ModelDictionaryRow) => String(row.id ?? row._tempId ?? row.model_name)

const getRowClassName = ({ row }: { row: ModelDictionaryRow }) => {
  const rowKey = getRowKey(row)
  if (draggingKey.value && draggingKey.value === rowKey) return 'drag-row drag-row-source'
  if (dragOverKey.value && dragOverKey.value === rowKey) return 'drag-row drag-row-target'
  return ''
}

const cloneRows = (rows: ModelDictionaryRow[]) => JSON.parse(JSON.stringify(rows || [])) as ModelDictionaryRow[]

const normalizeForCompare = (rows: ModelDictionaryRow[]) => {
  return (rows || []).map((row, idx) => ({
    id: Number.isFinite(Number(row.id)) ? Number(row.id) : null,
    model_name: String(row.model_name || '').trim(),
    model_family: String(row.model_family || '').trim(),
    sort_order: idx,
    enabled: Boolean(row.enabled),
    remark: String(row.remark || '').trim(),
  }))
}

const hasUnsavedChanges = computed(() => {
  return JSON.stringify(normalizeForCompare(localRows.value)) !== JSON.stringify(normalizeForCompare(baselineRows.value))
})

const syncLocalRowsFromStore = () => {
  const cloned = cloneRows(store.rows)
  localRows.value = cloned
  baselineRows.value = cloneRows(cloned)
}

const load = async () => {
  if (hasUnsavedChanges.value && !window.confirm('当前有未保存修改，确认刷新并放弃本地编辑吗？')) return
  loading.value = true
  try {
    await store.loadDictionary()
    syncLocalRowsFromStore()
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '读取机型字典失败')
  } finally {
    loading.value = false
  }
}

const loadPhotoConfig = async () => {
  if (!photoModel.value?.id) return
  photoLoading.value = true
  try {
    const res = await apiGet<{ data?: any[] }>(`/sandbox/model-dictionary/${photoModel.value.id}/photo-config`)
    photoRows.value = (res?.data || []).map((row: any, idx: number) => ({ ...row, sort_order: Number(row.sort_order ?? idx), required: Boolean(row.required), ocr_enabled: Boolean(row.ocr_enabled), enabled: Boolean(row.enabled) }))
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '读取拍照配置失败')
  } finally {
    photoLoading.value = false
  }
}

const openPhotoConfig = async (row: ModelDictionaryRow) => {
  photoModel.value = row
  photoRows.value = []
  photoVisible.value = true
  await loadPhotoConfig()
}

const savePhotoConfig = async () => {
  if (!photoModel.value?.id) return
  photoSaving.value = true
  try {
    await apiPost(`/sandbox/model-dictionary/${photoModel.value.id}/photo-config/save`, { rows: photoRows.value.map((row, idx) => ({ ...row, model_id: photoModel.value?.id, sort_order: idx })) })
    ElMessage.success('拍照配置已保存')
    await loadPhotoConfig()
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '保存拍照配置失败')
  } finally {
    photoSaving.value = false
  }
}

const addRow = () => {
  localRows.value.push({
    model_name: '',
    model_family: '',
    sort_order: localRows.value.length,
    enabled: true,
    remark: '',
    _tempId: createTempId(),
  })
}

const removeRow = (idx: number) => {
  if (idx < 0 || idx >= localRows.value.length) return
  localRows.value.splice(idx, 1)
}

const resetLocalChanges = () => {
  if (!hasUnsavedChanges.value) return
  if (!window.confirm('确认撤销当前未保存的修改吗？')) return
  localRows.value = cloneRows(baselineRows.value)
}

const moveRow = (fromIndex: number, toIndex: number) => {
  if (fromIndex === toIndex || fromIndex < 0 || toIndex < 0) return
  const nextRows = [...localRows.value]
  const [moved] = nextRows.splice(fromIndex, 1)
  if (!moved) return
  const insertIndex = fromIndex < toIndex ? toIndex - 1 : toIndex
  nextRows.splice(insertIndex, 0, moved)
  localRows.value = nextRows
}

const handleDragStart = (row: ModelDictionaryRow) => {
  draggingKey.value = getRowKey(row)
}

const handleDragEnter = (row: ModelDictionaryRow) => {
  if (!draggingKey.value) return
  dragOverKey.value = getRowKey(row)
}

const handleDragEnd = () => {
  draggingKey.value = ''
  dragOverKey.value = ''
}

const handleDrop = (targetRow: ModelDictionaryRow) => {
  const fromKey = draggingKey.value
  const toKey = getRowKey(targetRow)
  if (!fromKey || !toKey) {
    handleDragEnd()
    return
  }
  const fromIndex = localRows.value.findIndex((row) => getRowKey(row) === fromKey)
  const toIndex = localRows.value.findIndex((row) => getRowKey(row) === toKey)
  moveRow(fromIndex, toIndex)
  handleDragEnd()
}

const save = async () => {
  if (localRows.value.length === 0) {
    ElMessage.warning('至少保留 1 个机型')
    return
  }
  const hasEmpty = localRows.value.some((r) => !String(r.model_name || '').trim())
  if (hasEmpty) {
    ElMessage.warning('机型名称不能为空')
    return
  }
  const names = localRows.value.map((r) => String(r.model_name || '').trim())
  if (new Set(names).size !== names.length) {
    ElMessage.warning('机型名称不能重复')
    return
  }
  for (const row of localRows.value) {
    let family = String(row.model_family || '').trim()
    family = familyAliases[family] || family
    if (family && !allowedFamilies.has(family)) {
      ElMessage.warning(`机型 ${row.model_name} 的类别不合法`)
      return
    }
    row.model_family = family
  }
  saving.value = true
  try {
    await store.saveDictionary(localRows.value)
    syncLocalRowsFromStore()
    ElMessage.success('机型字典已保存并生效')
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  load()
})

const handleBeforeUnload = (event: BeforeUnloadEvent) => {
  if (!hasUnsavedChanges.value) return
  event.preventDefault()
  event.returnValue = ''
}

window.addEventListener('beforeunload', handleBeforeUnload)

onBeforeUnmount(() => {
  window.removeEventListener('beforeunload', handleBeforeUnload)
})

onBeforeRouteLeave(() => {
  if (!hasUnsavedChanges.value) return true
  return window.confirm('机型字典有未保存修改，确认离开当前页面吗？')
})
</script>

<style scoped>
.head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-2);
}
.head h1 {
  margin: 0;
  font-size: 30px;
}
.ops {
  display: flex;
  gap: var(--space-2);
}
.ops :deep(.el-button) {
  min-width: 96px;
}
.tip {
  margin-bottom: var(--space-2);
  color: var(--color-gray-500);
}
.bar {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-bottom: var(--space-2);
}
.photo-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  color: var(--color-gray-500);
  font-size: 13px;
}
.dirty {
  color: var(--color-warning, #d97706);
  font-size: 13px;
  font-weight: 600;
}
.drag-handle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 6px;
  cursor: grab;
  user-select: none;
  color: var(--color-gray-500);
  transition: background-color 0.18s ease, color 0.18s ease, transform 0.18s ease, box-shadow 0.18s ease;
}
.drag-handle:hover {
  background: var(--color-gray-100);
  color: var(--color-gray-700);
  transform: scale(1.06);
}
.drag-handle.is-dragging {
  cursor: grabbing;
  background: var(--color-primary-100, rgba(59, 130, 246, 0.12));
  color: var(--color-primary-600, #2563eb);
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.18);
  animation: drag-handle-pulse 0.9s ease-in-out infinite;
}
.drag-handle.is-over {
  background: var(--color-success-100, rgba(34, 197, 94, 0.12));
  color: var(--color-success-700, #15803d);
  transform: scale(1.08);
}
.page :deep(.el-table__row > td) {
  transition: background-color 0.18s ease, box-shadow 0.18s ease, opacity 0.18s ease;
}
.page :deep(.el-table__row.drag-row-source > td) {
  background: rgba(59, 130, 246, 0.08) !important;
  opacity: 0.72;
}
.page :deep(.el-table__row.drag-row-target > td) {
  background: rgba(34, 197, 94, 0.08) !important;
  box-shadow: inset 0 2px 0 rgba(34, 197, 94, 0.45), inset 0 -2px 0 rgba(34, 197, 94, 0.45);
}
.page :deep(.el-table__row.drag-row-target .drag-handle) {
  animation: drag-target-bounce 0.45s ease-in-out infinite alternate;
}
.page :deep(.el-button:hover),
.page :deep(.el-button:active) {
  transform: none !important;
  letter-spacing: normal !important;
}
.page :deep(.el-button:hover) {
  box-shadow: none !important;
}
@keyframes drag-handle-pulse {
  0% {
    transform: scale(1);
  }
  50% {
    transform: scale(1.08);
  }
  100% {
    transform: scale(1);
  }
}
@keyframes drag-target-bounce {
  0% {
    transform: translateY(0) scale(1.04);
  }
  100% {
    transform: translateY(-1px) scale(1.1);
  }
}
</style>
