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
      <el-table-column label="操作" width="210">
        <template #default="scope">
          <el-button size="small" type="danger" @click="removeRow(scope.$index)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="photo-config-panel">
      <div class="section-head">
        <div>
          <h2>机型拍照配置</h2>
          <p>按具体机型维护移动端必拍清单、OCR方案和字段规则。</p>
        </div>
        <div class="section-actions">
          <el-button :loading="photoLoading" @click="loadPhotoAdminData">刷新配置</el-button>
          <el-button type="primary" :disabled="!selectedModelId" :loading="photoSaving" @click="saveSelectedModelConfig">保存当前机型配置</el-button>
        </div>
      </div>

      <el-tabs v-model="photoTab" type="border-card">
        <el-tab-pane label="当前机型配置" name="config">
          <div class="config-toolbar">
            <el-select v-model="selectedModelId" filterable placeholder="选择机型" style="width: 280px" @change="loadSelectedModelConfig">
              <el-option
                v-for="row in modelOptions"
                :key="row.id"
                :label="row.model_name"
                :value="row.id"
              />
            </el-select>
            <el-button type="success" :disabled="!selectedModelId || photoItems.length === 0" @click="addConfigRow">新增拍照项</el-button>
            <span class="muted">移动端会按这里的排序生成拍照任务。</span>
          </div>
          <el-table :data="modelPhotoConfig" border stripe size="small">
            <el-table-column label="排序" width="90">
              <template #default="scope">
                <el-input-number v-model="scope.row.sort_order" :min="1" :controls="false" style="width: 70px" />
              </template>
            </el-table-column>
            <el-table-column label="位置编码" width="180">
              <template #default="scope">
                <el-select v-model="scope.row.position_code" filterable placeholder="位置编码" @change="applyPhotoItem(scope.row)">
                  <el-option v-for="item in enabledPhotoItems" :key="item.position_code" :label="`${item.position_code} ${item.item_name}`" :value="item.position_code" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column prop="item_name" label="拍照项目" min-width="180" />
            <el-table-column label="必拍" width="90" align="center">
              <template #default="scope"><el-switch v-model="scope.row.required" /></template>
            </el-table-column>
            <el-table-column label="OCR" width="90" align="center">
              <template #default="scope"><el-switch v-model="scope.row.ocr_enabled" /></template>
            </el-table-column>
            <el-table-column label="OCR方案" width="180">
              <template #default="scope"><el-input v-model="scope.row.ocr_profile" placeholder="编号标签OCR" /></template>
            </el-table-column>
            <el-table-column label="启用" width="90" align="center">
              <template #default="scope"><el-switch v-model="scope.row.enabled" /></template>
            </el-table-column>
            <el-table-column label="备注" min-width="180">
              <template #default="scope"><el-input v-model="scope.row.remark" /></template>
            </el-table-column>
            <el-table-column label="操作" width="90">
              <template #default="scope"><el-button size="small" type="danger" @click="modelPhotoConfig.splice(scope.$index, 1)">删除</el-button></template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="拍照项目库" name="items">
          <div class="config-toolbar">
            <el-button type="success" @click="addPhotoItem">新增项目</el-button>
            <el-button type="primary" :loading="photoSaving" @click="savePhotoItems">保存项目库</el-button>
          </div>
          <el-table :data="photoItems" border stripe size="small">
            <el-table-column label="位置编码" width="150"><template #default="scope"><el-input v-model="scope.row.position_code" /></template></el-table-column>
            <el-table-column label="项目名称" width="180"><template #default="scope"><el-input v-model="scope.row.item_name" /></template></el-table-column>
            <el-table-column label="大类" width="120"><template #default="scope"><el-input v-model="scope.row.item_category" /></template></el-table-column>
            <el-table-column label="拍摄要求" min-width="280"><template #default="scope"><el-input v-model="scope.row.shooting_requirement" /></template></el-table-column>
            <el-table-column label="默认必拍" width="95" align="center"><template #default="scope"><el-switch v-model="scope.row.default_required" /></template></el-table-column>
            <el-table-column label="默认OCR" width="95" align="center"><template #default="scope"><el-switch v-model="scope.row.default_ocr_enabled" /></template></el-table-column>
            <el-table-column label="默认OCR方案" width="170"><template #default="scope"><el-input v-model="scope.row.default_ocr_profile" /></template></el-table-column>
            <el-table-column label="排序" width="90"><template #default="scope"><el-input-number v-model="scope.row.sort_order" :min="1" :controls="false" style="width: 70px" /></template></el-table-column>
            <el-table-column label="启用" width="90" align="center"><template #default="scope"><el-switch v-model="scope.row.enabled" /></template></el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="OCR字段规则" name="ocr">
          <div class="config-toolbar">
            <el-button type="success" @click="addOcrRule">新增字段</el-button>
            <el-button type="primary" :loading="photoSaving" @click="saveOcrRules">保存OCR规则</el-button>
          </div>
          <el-table :data="ocrRules" border stripe size="small">
            <el-table-column label="OCR方案" width="160"><template #default="scope"><el-input v-model="scope.row.ocr_profile" /></template></el-table-column>
            <el-table-column label="位置编码" width="150"><template #default="scope"><el-input v-model="scope.row.position_code" /></template></el-table-column>
            <el-table-column label="字段编码" width="150"><template #default="scope"><el-input v-model="scope.row.field_code" /></template></el-table-column>
            <el-table-column label="字段名称" width="160"><template #default="scope"><el-input v-model="scope.row.field_name" /></template></el-table-column>
            <el-table-column label="必填" width="85" align="center"><template #default="scope"><el-switch v-model="scope.row.required" /></template></el-table-column>
            <el-table-column label="格式正则" min-width="190"><template #default="scope"><el-input v-model="scope.row.pattern" /></template></el-table-column>
            <el-table-column label="置信度" width="110"><template #default="scope"><el-input-number v-model="scope.row.confidence_threshold" :min="0" :max="1" :step="0.01" :controls="false" style="width: 90px" /></template></el-table-column>
            <el-table-column label="启用" width="85" align="center"><template #default="scope"><el-switch v-model="scope.row.enabled" /></template></el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="导入" name="import">
          <div class="import-box">
            <div class="config-toolbar">
              <el-button @click="downloadPhotoImportTemplate">下载Excel模板</el-button>
              <el-upload
                v-model:file-list="importUploadFiles"
                :auto-upload="false"
                :limit="1"
                accept=".xlsx"
                :on-change="onImportFileChange"
                :on-remove="onImportFileRemove"
              >
                <el-button>选择Excel文件</el-button>
              </el-upload>
              <el-button type="primary" :disabled="!importExcelFile" :loading="photoSaving" @click="importPhotoConfigExcel">上传并导入Excel</el-button>
            </div>
            <p class="muted">也可以粘贴 JSON 导入数据，结构为 {"photo_items":[],"model_config":[],"ocr_rules":[]}。</p>
            <el-input v-model="importText" type="textarea" :rows="12" placeholder='{"photo_items":[],"model_config":[],"ocr_rules":[]}' />
            <div class="config-toolbar">
              <el-button type="primary" :loading="photoSaving" @click="importPhotoConfig">导入并校验</el-button>
            </div>
          </div>
        </el-tab-pane>
      </el-tabs>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage, type UploadUserFile } from 'element-plus'
import { apiDownloadBlob, apiGet, apiPost, getApiErrorMessage } from '../utils/request'
import { useModelDictionaryStore, type ModelDictionaryRow } from '../store/modelDictionary'
import { onBeforeRouteLeave } from 'vue-router'

const store = useModelDictionaryStore()
const loading = ref(false)
const saving = ref(false)
const localRows = ref<ModelDictionaryRow[]>([])
const baselineRows = ref<ModelDictionaryRow[]>([])
const draggingKey = ref('')
const dragOverKey = ref('')
const photoTab = ref('config')
const photoLoading = ref(false)
const photoSaving = ref(false)
const selectedModelId = ref<number | undefined>()
const photoItems = ref<PhotoItemRow[]>([])
const modelPhotoConfig = ref<ModelPhotoConfigRow[]>([])
const ocrRules = ref<OcrRuleRow[]>([])
const importText = ref('')
const importExcelFile = ref<File | null>(null)
const importUploadFiles = ref<UploadUserFile[]>([])

type PhotoItemRow = {
  id?: number
  position_code: string
  item_name: string
  item_category?: string
  shooting_requirement?: string
  default_required: boolean
  default_ocr_enabled: boolean
  default_ocr_profile?: string
  sort_order: number
  enabled: boolean
}

type ModelPhotoConfigRow = {
  id?: number
  model_id?: number
  model_name?: string
  position_code: string
  item_name?: string
  item_category?: string
  shooting_requirement?: string
  required: boolean
  ocr_enabled: boolean
  ocr_profile?: string
  sort_order: number
  enabled: boolean
  remark?: string
}

type OcrRuleRow = {
  id?: number
  ocr_profile: string
  position_code: string
  field_code: string
  field_name: string
  required: boolean
  pattern?: string
  confidence_threshold: number
  compare_target?: string
  enabled: boolean
}
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
const enabledPhotoItems = computed(() => photoItems.value.filter((item) => item.enabled))
const modelOptions = computed(() =>
  localRows.value
    .filter((row) => Number.isFinite(Number(row.id)))
    .map((row) => ({ id: Number(row.id), model_name: row.model_name }))
)

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
    if (!selectedModelId.value) {
      selectedModelId.value = localRows.value.find((row) => row.id)?.id
    }
    await loadPhotoAdminData()
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '读取机型字典失败')
  } finally {
    loading.value = false
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

const loadPhotoAdminData = async () => {
  photoLoading.value = true
  try {
    const [itemsRes, rulesRes] = await Promise.all([
      apiGet<{ data?: PhotoItemRow[] }>('/photo-items'),
      apiGet<{ data?: OcrRuleRow[] }>('/ocr-field-rules'),
    ])
    photoItems.value = itemsRes.data || []
    ocrRules.value = rulesRes.data || []
    if (selectedModelId.value) {
      await loadSelectedModelConfig()
    }
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '读取拍照配置失败')
  } finally {
    photoLoading.value = false
  }
}

const loadSelectedModelConfig = async () => {
  if (!selectedModelId.value) {
    modelPhotoConfig.value = []
    return
  }
  const res = await apiGet<{ data?: ModelPhotoConfigRow[] }>(`/model-dictionary/${selectedModelId.value}/photo-config`)
  modelPhotoConfig.value = res.data || []
}

const addPhotoItem = () => {
  photoItems.value.push({
    position_code: '',
    item_name: '',
    item_category: '编号',
    shooting_requirement: '',
    default_required: true,
    default_ocr_enabled: true,
    default_ocr_profile: '编号标签OCR',
    sort_order: photoItems.value.length + 1,
    enabled: true,
  })
}

const savePhotoItems = async () => {
  photoSaving.value = true
  try {
    await apiPost('/photo-items/save', { rows: photoItems.value })
    ElMessage.success('拍照项目库已保存')
    await loadPhotoAdminData()
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '保存拍照项目失败')
  } finally {
    photoSaving.value = false
  }
}

const addConfigRow = () => {
  const item = enabledPhotoItems.value[0]
  modelPhotoConfig.value.push({
    position_code: item?.position_code || '',
    item_name: item?.item_name || '',
    item_category: item?.item_category || '',
    shooting_requirement: item?.shooting_requirement || '',
    required: item?.default_required ?? true,
    ocr_enabled: item?.default_ocr_enabled ?? true,
    ocr_profile: item?.default_ocr_profile || '编号标签OCR',
    sort_order: modelPhotoConfig.value.length + 1,
    enabled: true,
    remark: '',
  })
}

const applyPhotoItem = (row: ModelPhotoConfigRow) => {
  const item = photoItems.value.find((it) => it.position_code === row.position_code)
  if (!item) return
  row.item_name = item.item_name
  row.item_category = item.item_category
  row.shooting_requirement = item.shooting_requirement
  row.required = item.default_required
  row.ocr_enabled = item.default_ocr_enabled
  row.ocr_profile = item.default_ocr_profile
}

const saveSelectedModelConfig = async () => {
  if (!selectedModelId.value) {
    ElMessage.warning('请先选择机型')
    return
  }
  photoSaving.value = true
  try {
    await apiPost(`/model-dictionary/${selectedModelId.value}/photo-config/save`, { rows: modelPhotoConfig.value })
    ElMessage.success('当前机型拍照配置已保存')
    await loadSelectedModelConfig()
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '保存机型拍照配置失败')
  } finally {
    photoSaving.value = false
  }
}

const addOcrRule = () => {
  ocrRules.value.push({
    ocr_profile: '编号标签OCR',
    position_code: '',
    field_code: 'component_no',
    field_name: '部件编号',
    required: true,
    pattern: '',
    confidence_threshold: 0.8,
    compare_target: '',
    enabled: true,
  })
}

const saveOcrRules = async () => {
  photoSaving.value = true
  try {
    await apiPost('/ocr-field-rules/save', { rows: ocrRules.value })
    ElMessage.success('OCR字段规则已保存')
    await loadPhotoAdminData()
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '保存OCR字段规则失败')
  } finally {
    photoSaving.value = false
  }
}

const onImportFileChange = (uploadFile: UploadUserFile, uploadFiles: UploadUserFile[]) => {
  const nextFiles = uploadFiles.slice(-1)
  importUploadFiles.value = nextFiles
  importExcelFile.value = (((nextFiles[0] as any)?.raw || (uploadFile as any).raw || null) as File | null)
}

const onImportFileRemove = () => {
  importExcelFile.value = null
}

const downloadPhotoImportTemplate = async () => {
  try {
    await apiDownloadBlob('/model-dictionary/photo-config/import-template', '机型拍照配置导入模板.xlsx')
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '下载模板失败')
  }
}

const importPhotoConfigExcel = async () => {
  if (!importExcelFile.value) {
    ElMessage.warning('请选择Excel文件')
    return
  }
  const formData = new FormData()
  formData.append('file', importExcelFile.value)
  photoSaving.value = true
  try {
    await apiPost('/model-dictionary/photo-config/import', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    ElMessage.success('Excel导入成功')
    importExcelFile.value = null
    importUploadFiles.value = []
    await loadPhotoAdminData()
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || 'Excel导入失败')
  } finally {
    photoSaving.value = false
  }
}

const importPhotoConfig = async () => {
  let payload: any
  try {
    payload = JSON.parse(importText.value || '{}')
  } catch {
    ElMessage.error('导入内容不是合法JSON')
    return
  }
  photoSaving.value = true
  try {
    await apiPost('/model-dictionary/photo-config/import', payload)
    ElMessage.success('导入成功')
    importText.value = ''
    await loadPhotoAdminData()
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '导入失败')
  } finally {
    photoSaving.value = false
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
.photo-config-panel {
  margin-top: 24px;
}
.section-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 12px;
}
.section-head h2 {
  margin: 0 0 4px;
  font-size: 22px;
}
.section-head p {
  margin: 0;
  color: var(--color-gray-500);
}
.section-actions,
.config-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.config-toolbar {
  margin-bottom: 12px;
}
.muted {
  color: var(--color-gray-500);
  font-size: 13px;
}
.import-box {
  max-width: 900px;
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
