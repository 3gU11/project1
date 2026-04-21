<template>
  <div class="archive-page">
    <div class="head-row">
      <h1 class="title">📁 机台档案</h1>
    </div>

    <el-alert :closable="false" type="info" title="💡 管理每台机器的电子档案（照片/文档），文件存储在物理文件夹中。" />

    <div class="query-row">
      <div class="field-label">🔍 搜索/选择流水号</div>
      <el-select v-model="selectedSerial" filterable clearable placeholder="请选择流水号" style="width: 460px; max-width: 100%" @change="onSerialChange">
        <el-option v-for="sn in serials" :key="sn" :label="sn" :value="sn" />
      </el-select>
      <div v-if="selectedSerial" class="machine-meta">
        <div class="sn-title">{{ selectedSerial }}</div>
        <div class="sn-sub">机型: {{ selectedMachine?.model || '-' }} | 状态: {{ selectedMachine?.status || '-' }}</div>
      </div>
    </div>

    <el-divider />

    <template v-if="selectedSerial">
      <div class="empty-bar">{{ imageFiles.length > 0 ? `📷 现有图片存档（${imageFiles.length} 张）` : '暂无图片存档' }}</div>

      <div v-if="renderedImages.length > 0" class="gallery-toolbar">
        <el-checkbox :model-value="allImagesSelected" :indeterminate="isImageIndeterminate" @change="(v:any) => toggleAllImages(Boolean(v))">
          一键全选
        </el-checkbox>
        <el-button type="danger" plain :disabled="selectedImageNames.length === 0 || deletingImages" :loading="deletingImages" @click="deleteSelectedImages">
          删除已选照片
        </el-button>
      </div>

      <div v-if="renderedImages.length > 0" class="gallery-grid">
        <div v-for="(file, idx) in renderedImages" :key="file.file_name" class="gallery-card">
          <div class="gallery-select">
            <el-checkbox :model-value="selectedImageNames.includes(file.file_name)" @change="(v:any) => toggleImage(file.file_name, Boolean(v))">
              选择
            </el-checkbox>
          </div>
          <el-image
            class="gallery-thumb"
            :src="file.objectUrl"
            :preview-src-list="previewImageUrls"
            :initial-index="idx"
            fit="cover"
            preview-teleported
          />
          <div class="gallery-name" :title="file.file_name">{{ file.file_name }}</div>
          <div class="gallery-meta">
            <span>{{ formatSize(file.size) }}</span>
            <span>{{ file.update_time || '-' }}</span>
          </div>
        </div>
      </div>

      <el-divider />

      <el-collapse v-model="activePanels" class="upload-collapse">
        <el-collapse-item name="upload">
          <template #title>
            <span class="section-title">📤 上传机台档案 (必填项)</span>
          </template>

          <el-alert :closable="false" type="info" title="请填入对应部件编号，并上传照片。系统将自动使用编号重命名文件。" />

          <div class="upload-card">
            <el-row :gutter="10">
              <el-col :span="8">
                <div class="small-title">🟢 手轮号</div>
                <el-input v-model="partInput.wheelNo" />
                <div class="small-title">上传手轮照片</div>
                <el-upload :auto-upload="false" :show-file-list="true" :limit="1" :on-change="onPartFileChange('wheel')" :on-remove="onPartFileRemove('wheel')">
                  <el-button>选择文件</el-button>
                </el-upload>
              </el-col>
              <el-col :span="8">
                <div class="small-title">🔵 电机号</div>
                <el-input v-model="partInput.motorNo" />
                <div class="small-title">上传电机照片</div>
                <el-upload :auto-upload="false" :show-file-list="true" :limit="1" :on-change="onPartFileChange('motor')" :on-remove="onPartFileRemove('motor')">
                  <el-button>选择文件</el-button>
                </el-upload>
              </el-col>
              <el-col :span="8">
                <div class="small-title">🟠 板号</div>
                <el-input v-model="partInput.boardNo" />
                <div class="small-title">上传主板照片</div>
                <el-upload :auto-upload="false" :show-file-list="true" :limit="1" :on-change="onPartFileChange('board')" :on-remove="onPartFileRemove('board')">
                  <el-button>选择文件</el-button>
                </el-upload>
              </el-col>
            </el-row>
          </div>

          <div class="upload-card">
            <div class="small-title">⚪ 其他/注释照片</div>
            <el-row :gutter="10">
              <el-col :span="8">
                <div class="small-title">图片说明（选填）</div>
                <el-input v-model="otherLabel" placeholder="例如：机身侧面、包装等" />
              </el-col>
              <el-col :span="16">
                <div class="small-title">上传其他照片（支持多选）</div>
                <el-upload :auto-upload="false" :show-file-list="true" multiple :on-change="onOtherFileChange" :on-remove="onOtherFileRemove">
                  <el-button>选择文件</el-button>
                </el-upload>
              </el-col>
            </el-row>
          </div>

          <el-button type="danger" :loading="saving" @click="saveAllArchivePhotos">💾 保存所有档案照片</el-button>
        </el-collapse-item>
      </el-collapse>
    </template>
    <el-empty v-else description="请先选择流水号，随后显示机台档案上传与图片列表" />
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElMessage, type UploadUserFile } from 'element-plus'
import { getMachineArchivePreviewObjectUrl } from '../utils/machineArchivePreview'
import { apiGet, apiGetAll, apiPost, getApiErrorMessage } from '../utils/request'
type ListResponse<T = any> = { data: T[] }

const loadingSerials = ref(false)
const saving = ref(false)
const deletingImages = ref(false)
const activePanels = ref<string[]>([])
const serials = ref<string[]>([])
const selectedSerial = ref('')
const files = ref<any[]>([])
const renderedImages = ref<Array<{ file_name: string; size: number; update_time: string; objectUrl: string }>>([])
const selectedImageNames = ref<string[]>([])
const inventoryMap = ref<Record<string, { model: string; status: string }>>({})
const selectedMachine = computed(() => inventoryMap.value[selectedSerial.value] || null)
const imageFiles = computed(() => files.value.filter((f) => Boolean(f.is_image)))
const previewImageUrls = computed(() => renderedImages.value.map((item) => item.objectUrl))
const allImagesSelected = computed(() => renderedImages.value.length > 0 && renderedImages.value.every((item) => selectedImageNames.value.includes(item.file_name)))
const isImageIndeterminate = computed(() => {
  if (renderedImages.value.length === 0) return false
  const hit = renderedImages.value.filter((item) => selectedImageNames.value.includes(item.file_name)).length
  return hit > 0 && hit < renderedImages.value.length
})
const formatSize = (size: number) => {
  const value = Number(size || 0)
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / 1024 / 1024).toFixed(1)} MB`
}
const revokeRenderedImages = () => {
  renderedImages.value.forEach((item) => {
    if (item.objectUrl) URL.revokeObjectURL(item.objectUrl)
  })
  renderedImages.value = []
  selectedImageNames.value = []
}
const loadRenderedImages = async () => {
  revokeRenderedImages()
  const next: Array<{ file_name: string; size: number; update_time: string; objectUrl: string }> = []
  for (const file of imageFiles.value) {
    try {
      next.push({
        file_name: String(file.file_name || ''),
        size: Number(file.size || 0),
        update_time: String(file.update_time || ''),
        objectUrl: await getMachineArchivePreviewObjectUrl(selectedSerial.value, String(file.file_name || '')),
      })
    } catch {
      // Skip broken image entries so the page can still render remaining images.
    }
  }
  renderedImages.value = next
}

const partInput = reactive({
  wheelNo: '',
  motorNo: '',
  boardNo: '',
})
const partFiles = reactive<{
  wheel: File | null
  motor: File | null
  board: File | null
}>({
  wheel: null,
  motor: null,
  board: null,
})
const otherLabel = ref('')
const otherFiles = ref<File[]>([])

const loadSerials = async () => {
  loadingSerials.value = true
  try {
    const [snRes, invRows] = await Promise.all([
      apiGet<ListResponse>('/inventory/machine-archive/serials'),
      apiGetAll<any>('/inventory/'),
    ])
    serials.value = snRes.data || []
    const map: Record<string, { model: string; status: string }> = {}
    for (const row of invRows) {
      const sn = String(row['流水号'] || '').trim()
      if (!sn) continue
      map[sn] = {
        model: String(row['机型'] || ''),
        status: String(row['状态'] || ''),
      }
    }
    inventoryMap.value = map
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '读取流水号失败')
  } finally {
    loadingSerials.value = false
  }
}

const loadFiles = async () => {
  if (!selectedSerial.value) {
    files.value = []
    revokeRenderedImages()
    return
  }
  try {
    const res = await apiGet<ListResponse>(`/inventory/machine-archive/${encodeURIComponent(selectedSerial.value)}/files`)
    files.value = res.data || []
    await loadRenderedImages()
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '读取档案失败')
    files.value = []
    revokeRenderedImages()
  }
}

const onSerialChange = async () => {
  resetUploadDraft()
  selectedImageNames.value = []
  await loadFiles()
}
const toggleImage = (fileName: string, checked: boolean) => {
  const next = new Set(selectedImageNames.value)
  if (checked) next.add(fileName)
  else next.delete(fileName)
  selectedImageNames.value = Array.from(next)
}
const toggleAllImages = (checked: boolean) => {
  selectedImageNames.value = checked ? renderedImages.value.map((item) => item.file_name) : []
}
const deleteSelectedImages = async () => {
  if (!selectedSerial.value || selectedImageNames.value.length === 0) {
    ElMessage.warning('请先勾选要删除的照片')
    return
  }
  deletingImages.value = true
  try {
    await apiPost(`/inventory/machine-archive/${encodeURIComponent(selectedSerial.value)}/files/batch-delete`, {
      file_names: selectedImageNames.value,
    })
    ElMessage.success('已删除选中照片')
    selectedImageNames.value = []
    await loadFiles()
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '删除失败')
  } finally {
    deletingImages.value = false
  }
}

const onPartFileChange = (key: 'wheel' | 'motor' | 'board') => (uploadFile: UploadUserFile) => {
  const raw = uploadFile.raw as File | undefined
  if (!raw) return
  partFiles[key] = raw
}

const onPartFileRemove = (key: 'wheel' | 'motor' | 'board') => () => {
  partFiles[key] = null
}

const onOtherFileChange = (uploadFile: UploadUserFile) => {
  const raw = uploadFile.raw as File | undefined
  if (!raw) return
  otherFiles.value.push(raw)
}

const onOtherFileRemove = (uploadFile: UploadUserFile) => {
  const raw = uploadFile.raw as File | undefined
  if (!raw) return
  otherFiles.value = otherFiles.value.filter((f) => !(f.name === raw.name && f.size === raw.size))
}

const resetUploadDraft = () => {
  partInput.wheelNo = ''
  partInput.motorNo = ''
  partInput.boardNo = ''
  partFiles.wheel = null
  partFiles.motor = null
  partFiles.board = null
  otherLabel.value = ''
  otherFiles.value = []
}

const uploadByLabel = async (label: string, fileList: File[]) => {
  const formData = new FormData()
  formData.append('label', label)
  for (const f of fileList) formData.append('files', f)
  await apiPost(`/inventory/machine-archive/${encodeURIComponent(selectedSerial.value)}/upload`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

const saveAllArchivePhotos = async () => {
  if (!selectedSerial.value) {
    ElMessage.warning('请先选择流水号')
    return
  }
  if (partFiles.wheel && !partInput.wheelNo.trim()) return ElMessage.warning('请填写【手轮号】')
  if (partFiles.motor && !partInput.motorNo.trim()) return ElMessage.warning('请填写【电机号】')
  if (partFiles.board && !partInput.boardNo.trim()) return ElMessage.warning('请填写【板号】')
  const hasAny = Boolean(partFiles.wheel || partFiles.motor || partFiles.board || otherFiles.value.length > 0)
  if (!hasAny) return ElMessage.warning('未检测到待保存文件')

  saving.value = true
  try {
    if (partFiles.wheel) await uploadByLabel(`手轮_${partInput.wheelNo.trim()}`, [partFiles.wheel])
    if (partFiles.motor) await uploadByLabel(`电机_${partInput.motorNo.trim()}`, [partFiles.motor])
    if (partFiles.board) await uploadByLabel(`板号_${partInput.boardNo.trim()}`, [partFiles.board])
    if (otherFiles.value.length > 0) await uploadByLabel(otherLabel.value.trim() || '其他', otherFiles.value)
    ElMessage.success('档案保存成功')
    resetUploadDraft()
    await loadFiles()
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '上传失败')
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  loadSerials()
})

onBeforeUnmount(() => {
  revokeRenderedImages()
})
</script>

<style scoped>
.archive-page {
  padding-right: 6px;
}
.head-row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-bottom: var(--space-2);
}
.back-btn {
  padding: 4px 12px;
}
.title {
  margin: 0;
  font-size: 42px;
  font-weight: 800;
  color: var(--color-gray-800);
}
.query-row {
  margin-top: var(--space-2);
}
.field-label {
  color: var(--color-gray-700);
  font-size: var(--font-size-sm);
  margin-bottom: 4px;
}
.machine-meta {
  margin-left: 20px;
  display: inline-block;
  vertical-align: top;
}
.sn-title {
  font-size: 32px;
  font-weight: 700;
  color: var(--color-gray-900);
  line-height: 1.1;
}
.sn-sub {
  margin-top: 4px;
  font-size: var(--font-size-sm);
  color: #94a3b8;
}
.empty-bar {
  border: 1px solid var(--color-primary-100);
  background: var(--color-primary-50);
  border-radius: var(--radius-lg);
  color: var(--color-primary-700);
  font-size: var(--font-size-sm);
  padding: var(--space-2) var(--space-3);
}
.gallery-grid {
  margin-top: var(--space-2);
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 14px;
}
.gallery-toolbar {
  margin-top: var(--space-2);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.gallery-card {
  border: 1px solid var(--color-gray-200);
  border-radius: var(--radius-lg);
  background: #fff;
  padding: 12px;
}
.gallery-select {
  margin-bottom: 8px;
}
.gallery-thumb {
  width: 100%;
  height: 180px;
  border-radius: 10px;
  overflow: hidden;
}
.gallery-name {
  margin-top: 8px;
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--color-gray-800);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.gallery-meta {
  margin-top: 6px;
  display: flex;
  justify-content: space-between;
  gap: 8px;
  font-size: 12px;
  color: #94a3b8;
}
.section-title {
  margin: 0 0 8px;
  font-size: 34px;
  font-weight: 800;
  color: var(--color-gray-900);
}
.upload-collapse {
  margin-top: var(--space-2);
}
.upload-collapse :deep(.el-collapse-item__header) {
  height: auto;
  line-height: 1.4;
  padding: 12px 0;
  font-weight: 700;
}
.upload-collapse :deep(.el-collapse-item__wrap) {
  border-bottom: none;
}
.upload-card {
  margin-top: var(--space-2);
  border: 1px solid var(--color-gray-200);
  border-radius: var(--radius-lg);
  padding: var(--space-2);
}
.small-title {
  font-size: var(--font-size-sm);
  color: var(--color-gray-700);
  margin-bottom: 4px;
  margin-top: 2px;
}
</style>
