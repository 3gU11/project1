<template>
  <div class="machine-edit">
    <van-nav-bar
      title="机台档案"
      left-arrow
      fixed
      placeholder
      @click-left="router.back()"
    />

    <!-- Machine Info -->
    <van-cell-group inset title="基础信息" class="mt-4">
      <van-cell title="流水号" :value="machineInfo.serialNo" />
      <van-cell title="机型" :value="machineInfo.model" />
      <van-cell title="状态" :value="machineInfo.status" />
      <van-cell title="所在库位" :value="machineInfo.slotCode || '-'" />
    </van-cell-group>

    <!-- Upload Section -->
    <van-cell-group inset title="档案图片" class="mt-4">
      <div class="upload-container">
        <van-uploader
          v-model="fileList"
          multiple
          :max-count="9"
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
import { showFailToast, showImagePreview, showSuccessToast } from 'vant'
import type { UploaderFileListItem } from 'vant'
import request from '@/api/index'
import { inventoryApi } from '@/api/inventory'
import { useInventoryStore } from '@/store/inventory'
import { mapMachine } from '@/utils/mapper'

const route = useRoute()
const router = useRouter()
const inventoryStore = useInventoryStore()
const serialNo = computed(() => String(route.params.id || ''))
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
  if (rawName) {
    return rawName
  }
  const ext = getExtensionByMime(String(file.type || ''))
  return `upload${ext}`
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
  if (raw instanceof File) {
    return {
      file: raw,
      fileName: getUploadFileName(raw),
    }
  }
  if (raw instanceof Blob) {
    return {
      file: raw,
      fileName: getUploadFileName({ type: raw.type }),
    }
  }
  if (typeof item.content === 'string' && item.content.startsWith('data:')) {
    const blob = dataUrlToBlob(item.content)
    return {
      file: blob,
      fileName: getUploadFileName({ type: blob.type }),
    }
  }
  throw new Error('无法识别上传文件内容，请重新选择图片')
}

const machineInfo = ref({
  serialNo: '',
  model: '',
  status: '',
  slotCode: ''
})

const fileList = ref<UploaderFileListItem[]>([])
const previewImageUrls = computed(() => fileList.value.map((item) => String(item.url || '')).filter(Boolean))

const revokeObjectUrls = () => {
  fileList.value.forEach((item: any) => {
    const url = String(item.url || '')
    if (url.startsWith('blob:')) {
      URL.revokeObjectURL(url)
    }
  })
}

const getArchiveImageObjectUrl = async (fileName: string) => {
  try {
    const response = await request.get(
      `/inventory/machine-archive/${encodeURIComponent(serialNo.value)}/files/${encodeURIComponent(fileName)}/preview`,
      { responseType: 'blob' }
    )
    const blob = response instanceof Blob ? response : new Blob([response as any])
    return URL.createObjectURL(blob)
  } catch {
    const response = await request.get(
      `/inventory/machine-archive/${encodeURIComponent(serialNo.value)}/files/${encodeURIComponent(fileName)}/download`,
      { responseType: 'blob' }
    )
    const blob = response instanceof Blob ? response : new Blob([response as any])
    return URL.createObjectURL(blob)
  }
}

const loadMachineInfo = async () => {
  if (!serialNo.value) return
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

const loadFiles = async () => {
  if (!serialNo.value) return []
  try {
    const res = await inventoryApi.getMachineArchive(serialNo.value)
    if (res && res.data && Array.isArray(res.data)) {
      revokeObjectUrls()
      const imageFiles = res.data.filter((file: any) => file.is_image)
      fileList.value = await Promise.all(
        imageFiles.map(async (file: any) => {
          const fileName = String(file.file_name || '')
          return {
            url: await getArchiveImageObjectUrl(fileName),
            file_name: file.file_name,
            isImage: true,
            deletable: true,
            status: 'done',
            message: ''
          }
        })
      )
      return res.data
    }
    return []
  } catch (error: any) {
    console.error('加载图片失败', error)
    return []
  }
}

const handlePreview = (payload: { file: UploaderFileListItem }) => {
  const currentUrl = String(payload.file?.url || '')
  const startPosition = previewImageUrls.value.findIndex((url) => url === currentUrl)
  showImagePreview({
    images: previewImageUrls.value,
    startPosition: startPosition >= 0 ? startPosition : 0,
    closeable: true,
  })
}

const afterRead = async (items: UploaderFileListItem | UploaderFileListItem[]) => {
  const uploadItems = Array.isArray(items) ? items : [items]
  
  for (const item of uploadItems) {
    if (!item.file && !item.content) continue
    
    item.status = 'uploading'
    item.message = '上传中...'

    try {
      const beforeFiles = await inventoryApi.getMachineArchive(serialNo.value)
      const beforeCount = Array.isArray(beforeFiles?.data) ? beforeFiles.data.length : 0

      const formData = new FormData()
      const payload = normalizeUploadPayload(item)
      formData.append('files', payload.file, payload.fileName)
      // Pass empty label or specific one since we removed labeling requirement
      formData.append('label', '档案图片')

      const uploadRes = await inventoryApi.uploadMachineArchive(serialNo.value, formData) as any
      if (!uploadRes?.message || !String(uploadRes.message).includes('上传成功')) {
        throw new Error('服务端未返回有效的上传成功结果')
      }

      const latestFiles = await loadFiles()
      const afterCount = Array.isArray(latestFiles) ? latestFiles.length : 0
      if (afterCount <= beforeCount) {
        throw new Error('上传响应成功，但未在档案列表中发现新文件')
      }

      item.status = 'done'
      item.message = ''
      showSuccessToast('上传成功')
    } catch (error: any) {
      item.status = 'failed'
      item.message = '上传失败'
      await loadFiles()
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
    machineInfo.value = {
      serialNo: '',
      model: '',
      status: '',
      slotCode: ''
    }
    await loadMachineInfo()
    await loadFiles()
  },
  { immediate: true }
)

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
.upload-container {
  padding: 16px;
}
</style>
