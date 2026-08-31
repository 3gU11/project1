<template>
  <div class="machine-edit">
    <van-nav-bar title="机台档案" left-arrow fixed placeholder @click-left="router.back()" />

    <van-cell-group inset title="基础信息" class="mt-4">
      <van-cell title="流水号" :value="machineInfo.serialNo || serialNo" />
      <van-cell title="机型" :value="machineInfo.model || '-'" />
      <van-cell title="状态" :value="machineInfo.status || '-'" />
      <van-cell title="所在库位" :value="machineInfo.slotCode || '-'" />
    </van-cell-group>

    <van-cell-group inset title="结构化拍照任务" class="mt-4">
      <div class="task-summary">
        <div>
          <strong>{{ summary.photo_done }}/{{ summary.total }}</strong>
          <span> 已拍</span>
          <div class="summary-sub">
            必拍 {{ summary.required_photo_done }}/{{ summary.required_total }}
            · 扫码确认 {{ summary.barcode_confirmed }}/{{ summary.barcode_total }}
            <span v-if="summary.barcode_pending"> · 待扫码 {{ summary.barcode_pending }}</span>
          </div>
        </div>
        <van-button size="small" type="primary" :loading="taskLoading" @click="initTasks">生成/刷新任务</van-button>
      </div>

      <van-empty v-if="!taskLoading && tasks.length === 0" description="该机型暂无拍照任务配置" />

      <div v-for="task in tasks" :key="task.id" class="task-card">
        <div class="task-head">
          <div>
            <div class="task-title">{{ task.position_code }} {{ task.item_name }}</div>
            <div class="task-meta">
              <van-tag v-if="task.required" type="danger">必拍</van-tag>
              <van-tag v-else>选拍</van-tag>
              <van-tag v-if="task.ocr_enabled" type="primary">扫码</van-tag>
              <van-tag :type="statusType(task.status)">{{ statusText(task.status) }}</van-tag>
            </div>
          </div>
          <div v-if="task.file_name" class="file-name">{{ task.file_name }}</div>
        </div>

        <div class="task-actions">
          <van-uploader
            :after-read="(file) => afterTaskRead(task, file)"
            :max-count="1"
            accept="image/*"
            capture="environment"
          >
            <van-button size="small" type="primary" :loading="uploadingTaskId === task.id">{{ taskUploadText(task) }}</van-button>
          </van-uploader>
          <ScanButton
            v-if="task.ocr_enabled"
            button-text="扫码绑定"
            :loading="scanningTaskId === task.id"
            @success="(value) => bindTaskQRCode(task, value)"
          />
          <van-button
            v-if="canResetTaskPhoto(task)"
            size="small"
            type="danger"
            plain
            :loading="deletingTaskId === task.id"
            @click="deleteTaskPhoto(task)"
          >
            清空重拍
          </van-button>
          <van-button v-if="task.status === 'manual_review'" size="small" type="warning" @click="confirmTask(task, 'retake_required')">需补拍</van-button>
          <van-button v-if="!task.required && task.status === 'pending'" size="small" @click="confirmTask(task, 'skipped')">跳过</van-button>
        </div>

        <div v-if="task.barcode_value" class="barcode-result">
          <span>已扫码</span>
          <strong>{{ task.barcode_value }}</strong>
        </div>
      </div>

      <div class="submit-row">
        <van-button block type="success" :loading="submitting" :disabled="!canSubmit" @click="submitPhotos">
          提交当前拍照档案
        </van-button>
      </div>
    </van-cell-group>

    <van-cell-group inset title="历史图片/其他图片" class="mt-4">
      <div class="upload-container">
        <van-uploader
          v-model="fileList"
          multiple
          :max-count="100"
          :after-read="afterRead"
          @click-preview="handlePreview"
          @delete="onDelete"
          accept="image/*"
        />
      </div>
    </van-cell-group>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { showConfirmDialog, showFailToast, showImagePreview, showSuccessToast, showToast } from 'vant'
import type { UploaderFileListItem } from 'vant'
import request from '@/api/index'
import { inventoryApi } from '@/api/inventory'
import ScanButton from '@/components/common/ScanButton.vue'
import { useInventoryStore } from '@/store/inventory'
import { mapMachine } from '@/utils/mapper'
import { useInventoryAutoRefresh } from '@/utils/useInventoryAutoRefresh'

const route = useRoute()
const router = useRouter()
const inventoryStore = useInventoryStore()
const serialNo = computed(() => String(route.params.id || ''))

type ArchiveUploaderItem = UploaderFileListItem & {
  file_name?: string
  fullUrl?: string
}

type PhotoTask = {
  id: number
  serial_no: string
  model_name: string
  position_code: string
  item_name: string
  required: boolean
  ocr_enabled: boolean
  ocr_profile?: string
  status: string
  sort_order: number
  file_id?: number
  file_name?: string
  uploaded_at?: string
  barcode_value?: string
  ocr_issues?: number
  ocr_results?: OcrResult[]
}

type OcrResult = {
  id?: number
  task_id?: number
  field_code: string
  field_name: string
  recognized_value?: string
  manual_value?: string
  display_value: string
  confidence?: number
  check_status?: string
}

type PhotoSummary = {
  total: number
  required_total: number
  required_done: number
  required_photo_done: number
  photo_done: number
  barcode_total: number
  barcode_confirmed: number
  barcode_pending: number
  ocr_total: number
  ocr_confirmed: number
  ocr_pending: number
  missing_required: number
  retake_required: number
  can_submit?: boolean
}

const defaultSummary = (): PhotoSummary => ({
  total: 0,
  required_total: 0,
  required_done: 0,
  required_photo_done: 0,
  photo_done: 0,
  barcode_total: 0,
  barcode_confirmed: 0,
  barcode_pending: 0,
  ocr_total: 0,
  ocr_confirmed: 0,
  ocr_pending: 0,
  missing_required: 0,
  retake_required: 0,
  can_submit: false,
})

const normalizeSummary = (value: Partial<PhotoSummary> | undefined, totalFallback = 0): PhotoSummary => ({
  ...defaultSummary(),
  total: totalFallback,
  ...(value || {}),
})

const extByMime: Record<string, string> = {
  'image/jpeg': '.jpg',
  'image/jpg': '.jpg',
  'image/png': '.png',
  'image/webp': '.webp',
  'image/gif': '.gif',
  'image/bmp': '.bmp',
  'image/heic': '.heic',
  'image/heif': '.heif',
}

const getExtensionByMime = (mime = '') => extByMime[mime] || '.jpg'

const getUploadFileName = (file: { name?: string; type?: string }) => {
  const rawName = String(file.name || '').trim()
  if (rawName) return rawName
  return `upload${getExtensionByMime(String(file.type || ''))}`
}

const dataUrlToBlob = (dataUrl: string) => {
  const [header, body = ''] = dataUrl.split(',')
  const mimeMatch = header.match(/data:(.*?);base64/)
  const mime = mimeMatch?.[1] || 'image/jpeg'
  const binary = atob(body)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i)
  }
  return new Blob([bytes], { type: mime })
}

const normalizeUploadPayload = (item: UploaderFileListItem) => {
  const raw = item.file as any
  if (raw instanceof File) return { file: raw, fileName: getUploadFileName(raw) }
  if (raw instanceof Blob) return { file: raw, fileName: getUploadFileName({ type: raw.type }) }
  if (typeof item.content === 'string' && item.content.startsWith('data:')) {
    const blob = dataUrlToBlob(item.content)
    return { file: blob, fileName: getUploadFileName({ type: blob.type }) }
  }
  throw new Error('无法识别上传文件内容，请重新选择图片')
}

const machineInfo = ref({
  serialNo: '',
  model: '',
  status: '',
  slotCode: ''
})

const fileList = ref<ArchiveUploaderItem[]>([])
const tasks = ref<PhotoTask[]>([])
const summary = ref<PhotoSummary>(defaultSummary())
const taskLoading = ref(false)
const uploadingTaskId = ref<number | null>(null)
const deletingTaskId = ref<number | null>(null)
const scanningTaskId = ref<number | null>(null)
const submitting = ref(false)

const canSubmit = computed(() => tasks.value.length > 0 && (summary.value.can_submit || summary.value.photo_done > 0))

const statusText = (status: string) => {
  const map: Record<string, string> = {
    pending: '待拍',
    uploaded: '已拍待扫码',
    ocr_processing: '识别中',
    ocr_passed: '待扫码确认',
    manual_review: '待确认',
    retake_required: '需补拍',
    completed: '已拍',
    manual_passed: '已确认绑定',
    skipped: '已跳过',
  }
  return map[status] || status || '-'
}

const statusType = (status: string) => {
  if (['completed', 'manual_passed'].includes(status)) return 'success'
  if (['manual_review', 'retake_required'].includes(status)) return 'warning'
  if (status === 'ocr_passed') return 'primary'
  if (status === 'pending') return 'default'
  return 'primary'
}

const taskUploadText = (task: PhotoTask) => {
  if (task.status === 'retake_required') return '补拍/重拍'
  if (task.file_name || task.status === 'manual_review' || task.status === 'ocr_passed' || task.status === 'manual_passed') return '重拍/上传'
  return '拍照/上传'
}

const canResetTaskPhoto = (task: PhotoTask) => (
  !!task.file_name ||
  !!task.ocr_results?.length ||
  ['uploaded', 'ocr_processing', 'ocr_passed', 'manual_review', 'manual_passed', 'completed', 'retake_required'].includes(task.status)
)

const normalizePhotoTasks = (rows: PhotoTask[] = []) => rows.map((task) => ({
  ...task,
  barcode_value: String(task.barcode_value || '').trim(),
}))

const revokeObjectUrls = () => {
  fileList.value.forEach((item: any) => {
    const url = String(item.url || '')
    if (url.startsWith('blob:')) URL.revokeObjectURL(url)
  })
}

const getArchiveImageObjectUrl = async (fileName: string, type: 'thumbnail' | 'preview' = 'thumbnail') => {
  if (!fileName) return ''
  try {
    const response = await request.get(
      `/inventory/machine-archive/${serialNo.value}/files/${fileName}/${type}`,
      { responseType: 'blob', timeout: 60000 }
    )
    const blob = response instanceof Blob ? response : new Blob([response as any])
    if (blob.size < 100) throw new Error('返回数据异常')
    return URL.createObjectURL(blob)
  } catch {
    try {
      const response = await request.get(
        `/inventory/machine-archive/${serialNo.value}/files/${fileName}/download`,
        { responseType: 'blob' }
      )
      const blob = response instanceof Blob ? response : new Blob([response as any])
      return URL.createObjectURL(blob)
    } catch {
      return ''
    }
  }
}

const loadMachineInfo = async () => {
  if (!serialNo.value) return
  try {
    const profile = await inventoryApi.getMachinePhotoProfile(serialNo.value) as any
    if (profile?.machine) {
      machineInfo.value = {
        serialNo: profile.machine.serial_no,
        model: profile.machine.model,
        status: profile.machine.status,
        slotCode: profile.machine.slot_code
      }
      return
    }
  } catch {
    // Fallback keeps the old page useful if the new profile API is unavailable.
  }

  try {
    let exactItem = inventoryStore.list.find((item) => item.serialNo === serialNo.value)
    if (!exactItem) {
      const rows = await inventoryApi.getInventoryAll() as Record<string, unknown>[]
      exactItem = rows.map((row, index) => mapMachine(row, index)).find((item) => item.serialNo === serialNo.value)
    }
    if (exactItem) {
      machineInfo.value = {
        serialNo: exactItem.serialNo,
        model: exactItem.model,
        status: exactItem.status,
        slotCode: exactItem.slotCode
      }
    } else {
      showFailToast('未找到该机台信息')
    }
  } catch (error: any) {
    showFailToast(error.message || '获取机台信息失败')
  }
}

const loadTasks = async () => {
  if (!serialNo.value) return
  try {
    const res = await inventoryApi.getMachinePhotoTasks(serialNo.value) as any
    tasks.value = normalizePhotoTasks(res?.data || [])
    summary.value = normalizeSummary(res?.summary, tasks.value.length)
  } catch {
    tasks.value = []
    summary.value = defaultSummary()
  }
}

const initTasks = async () => {
  if (!serialNo.value) return
  taskLoading.value = true
  try {
    const res = await inventoryApi.initMachinePhotoTasks(serialNo.value) as any
    tasks.value = normalizePhotoTasks(res?.data || [])
    summary.value = normalizeSummary(res?.summary, tasks.value.length)
    if (tasks.value.length === 0) showToast('该机型暂无拍照任务配置')
  } catch (error: any) {
    showFailToast(error?.response?.data?.error || error.message || '生成拍照任务失败')
    await loadTasks()
  } finally {
    taskLoading.value = false
  }
}

const afterTaskRead = async (task: PhotoTask, item: UploaderFileListItem | UploaderFileListItem[]) => {
  const first = (Array.isArray(item) ? item[0] : item) as UploaderFileListItem
  if (!first?.file && !first?.content) return
  uploadingTaskId.value = task.id
  try {
    const { file, fileName } = normalizeUploadPayload(first)
    const formData = new FormData()
    formData.append('file', file, fileName)
    await inventoryApi.uploadPhotoTask(task.id, formData)
    showSuccessToast(task.ocr_enabled ? '上传完成，请扫码绑定' : '上传完成')
    await loadTasks()
  } catch (error: any) {
    showFailToast(error?.response?.data?.error || error.message || '上传失败')
    await loadTasks()
  } finally {
    uploadingTaskId.value = null
  }
}

const bindTaskQRCode = async (task: PhotoTask, barcodeValue: string) => {
  const value = barcodeValue.trim()
  if (!value) return
  if (task.barcode_value && task.barcode_value !== value) {
    try {
      await showConfirmDialog({
        title: '替换已扫码内容？',
        message: `当前内容：${task.barcode_value}`,
        confirmButtonText: '替换',
        cancelButtonText: '取消',
      })
    } catch {
      return
    }
  }
  scanningTaskId.value = task.id
  try {
    await inventoryApi.scanPhotoTaskQRCode(task.id, value)
    showSuccessToast('二维码已绑定')
    await loadTasks()
  } catch (error: any) {
    showFailToast(error?.response?.data?.error || error.message || '扫码绑定失败')
  } finally {
    scanningTaskId.value = null
  }
}

const confirmTask = async (task: PhotoTask, status: string) => {
  try {
    const shouldPassFields = ['manual_passed', 'completed', 'ocr_passed'].includes(status)
    const fields = shouldPassFields
      ? (task.ocr_results || []).map((field) => ({
          field_code: field.field_code,
          field_name: field.field_name,
          manual_value: String(field.display_value || field.recognized_value || '').trim(),
          passed: true,
        }))
      : []
    await inventoryApi.confirmPhotoTask(task.id, { status, fields })
    showSuccessToast('状态已更新')
    await loadTasks()
  } catch (error: any) {
    showFailToast(error?.response?.data?.error || error.message || '更新失败')
  }
}

const deleteTaskPhoto = async (task: PhotoTask) => {
  try {
    await showConfirmDialog({
      title: '清空这个拍照项？',
      message: '会删除当前照片和历史OCR结果；已扫码的物料码会保留。清空后可重新拍照。',
      confirmButtonText: '清空重拍',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  deletingTaskId.value = task.id
  try {
    await inventoryApi.deletePhotoTask(task.id)
    showSuccessToast('已清空，可重新拍照')
    await loadTasks()
  } catch (error: any) {
    showFailToast(error?.response?.data?.error || error.message || '清空失败')
  } finally {
    deletingTaskId.value = null
  }
}

const submitWarningLines = () => {
  const lines: string[] = []
  if (summary.value.missing_required > 0) {
    lines.push(`还有 ${summary.value.missing_required} 个必拍项未拍`)
  }
  if (summary.value.barcode_pending > 0) {
    lines.push(`还有 ${summary.value.barcode_pending} 个位置待扫码`)
  }
  if (summary.value.retake_required > 0) {
    lines.push(`还有 ${summary.value.retake_required} 个项目标记为需补拍`)
  }
  return lines
}

const submitPhotos = async () => {
  const warnings = submitWarningLines()
  if (warnings.length > 0) {
    try {
      await showConfirmDialog({
        title: '提交当前拍照档案？',
        message: `${warnings.join('，')}。可以先提交当前照片，后续继续补充；未确认编号不会同步到维修基础资料。`,
        confirmButtonText: '先提交',
        cancelButtonText: '继续拍照',
      })
    } catch {
      return
    }
  }
  submitting.value = true
  try {
    await inventoryApi.submitMachinePhotos(serialNo.value)
    showSuccessToast('当前拍照档案已提交')
    await loadTasks()
  } catch (error: any) {
    showFailToast(error?.response?.data?.error || error.message || '提交失败')
  } finally {
    submitting.value = false
  }
}

const loadFiles = async () => {
  if (!serialNo.value) return []
  try {
    const res = await inventoryApi.getMachineArchive(serialNo.value)
    if (res && (res as any).data && Array.isArray((res as any).data)) {
      revokeObjectUrls()
      const imageFiles = (res as any).data.filter((file: any) => file.is_image)
      fileList.value = await Promise.all(
        imageFiles.map(async (file: any) => {
          const fileName = String(file.file_name || '')
          return {
            url: await getArchiveImageObjectUrl(fileName, 'thumbnail'),
            fullUrl: '',
            file_name: file.file_name,
            isImage: true,
            deletable: true,
            status: 'done',
            message: ''
          }
        })
      )
      return (res as any).data
    }
    return []
  } catch (error: any) {
    console.error('加载历史图片失败', error)
    return []
  }
}

const handlePreview = (payload: { file: ArchiveUploaderItem }) => {
  const images = fileList.value.map((item) => item.url || '').filter(Boolean)
  const index = fileList.value.findIndex((i: any) => i.file_name === (payload.file as any).file_name)
  showImagePreview({ images, startPosition: index >= 0 ? index : 0, closeable: true })
}

const afterRead = async (items: UploaderFileListItem | UploaderFileListItem[]) => {
  const uploadItems = (Array.isArray(items) ? items : [items]) as ArchiveUploaderItem[]
  for (const item of uploadItems) {
    if (!item.file) continue
    item.status = 'uploading'
    item.message = '准备中...'
    try {
      const { file: rawFile, fileName } = normalizeUploadPayload(item)
      item.message = '上传原图...'
      const formData = new FormData()
      formData.append('files', rawFile, fileName)
      formData.append('label', '档案图片')
      const uploadRes = await inventoryApi.uploadMachineArchive(serialNo.value, formData) as any
      if (!uploadRes?.saved_names?.[0]) throw new Error('上传失败或未返回文件名')
      const savedName = uploadRes.saved_names[0]
      item.file_name = savedName
      item.url = await getArchiveImageObjectUrl(savedName, 'thumbnail')
      item.fullUrl = ''
      item.status = 'done'
      item.message = ''
    } catch (error: any) {
      item.status = 'failed'
      item.message = '失败'
      showFailToast(error.message || '上传失败')
    }
  }
}

const onDelete = async (item: any) => {
  try {
    const filename = item.file_name || (item.url ? item.url.split('/').pop() : '')
    if (filename) {
      await inventoryApi.deleteMachineArchive(serialNo.value, filename)
      showSuccessToast('删除成功')
      return true
    }
    return false
  } catch (error: any) {
    showFailToast(error.message || '删除失败')
    return false
  }
}

watch(
  serialNo,
  async () => {
    revokeObjectUrls()
    fileList.value = []
    tasks.value = []
    summary.value = defaultSummary()
    machineInfo.value = { serialNo: '', model: '', status: '', slotCode: '' }
    await loadMachineInfo()
    await initTasks()
    await loadFiles()
  },
  { immediate: true }
)

useInventoryAutoRefresh(loadMachineInfo)

onBeforeUnmount(() => {
  revokeObjectUrls()
})
</script>

<style scoped>
.machine-edit {
  min-height: 100vh;
  background-color: var(--van-background-2);
  padding-bottom: 24px;
}
.mt-4 {
  margin-top: 16px;
}
.task-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;
}
.summary-sub {
  margin-top: 4px;
  color: var(--van-text-color-2);
  font-size: 12px;
  line-height: 1.4;
}
.task-card {
  margin: 10px 12px;
  padding: 12px;
  border: 1px solid var(--van-border-color);
  border-radius: 8px;
  background: var(--van-background);
}
.task-head {
  display: flex;
  justify-content: space-between;
  gap: 10px;
}
.task-title {
  font-weight: 600;
  line-height: 1.4;
}
.task-meta {
  display: flex;
  gap: 6px;
  margin-top: 6px;
  flex-wrap: wrap;
}
.file-name {
  max-width: 38%;
  color: var(--van-text-color-2);
  font-size: 12px;
  word-break: break-all;
  text-align: right;
}
.task-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 12px;
}
.barcode-result {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-top: 10px;
  padding: 8px 10px;
  color: var(--van-success-color);
  font-size: 12px;
  line-height: 1.4;
  background: var(--van-background-2);
  border-radius: 6px;
  word-break: break-all;
}
.barcode-result strong {
  color: var(--van-text-color);
  font-weight: 600;
}
.submit-row {
  padding: 12px 16px 16px;
}
.upload-container {
  padding: 16px;
}
</style>
