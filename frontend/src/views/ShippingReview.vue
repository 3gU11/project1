<template>
  <div class="ship-page">
    <div class="head-row">
      <h1 class="title">🚛 发货复核</h1>
      <el-button type="primary" :loading="loading" @click="loadPending">刷新数据</el-button>
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
      <el-table-column prop="机型" label="机型" min-width="160" />
      <el-table-column prop="流水号" label="流水号" width="160" />
      <el-table-column prop="订单备注" label="订单备注" min-width="180" />
      <el-table-column prop="机台备注/配置" label="机台备注/配置" min-width="180" />
    </el-table>

    <div class="ops">
      <el-button type="primary" :loading="saving" @click="confirmShip">🚚 正式发货</el-button>
      <el-button :loading="saving" @click="revertShip">🔄 发货撤回</el-button>
    </div>

    <div v-if="selectedRows.length > 0" class="photo-preview">
      <h3 class="preview-title">📸 选中机台照片预览</h3>
      <el-collapse>
        <el-collapse-item
          v-for="row in selectedRows"
          :key="String(row['流水号'] || '')"
          :name="String(row['流水号'] || '')"
        >
          <template #title>
            <span>{{ String(row['流水号'] || '-') }} - {{ String(row['机型'] || '-') }}</span>
          </template>

          <div class="preview-count">📷 照片总数: {{ getPreviewCount(String(row['流水号'] || '')) }} 张</div>

          <div v-if="getVisiblePhotos(String(row['流水号'] || '')).length > 0" class="preview-grid">
            <el-image
              v-for="(photo, idx) in getVisiblePhotos(String(row['流水号'] || ''))"
              :key="photo.file_name"
              class="preview-thumb"
              :src="photo.objectUrl"
              :preview-src-list="getPreviewUrls(String(row['流水号'] || ''))"
              :initial-index="idx"
              fit="cover"
              preview-teleported
            />
          </div>
          <div v-else class="empty-tip">暂无档案图片</div>

          <div v-if="getRemainingCount(String(row['流水号'] || '')) > 0" class="preview-actions">
            <el-button
              size="small"
              @click="toggleShowAllPhotos(String(row['流水号'] || ''))"
            >
              {{ showAllPhotosMap[String(row['流水号'] || '')] ? '收起照片' : `显示全部照片（剩余 ${getRemainingCount(String(row['流水号'] || ''))} 张）` }}
            </el-button>
          </div>
        </el-collapse-item>
      </el-collapse>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getMachineArchivePreviewObjectUrl } from '../utils/machineArchivePreview'
import { apiGet, apiPost, getApiErrorMessage } from '../utils/request'

type Row = Record<string, any>
type ListResponse<T = any> = { data: T[] }
type MessageResponse = { message?: string }
type ArchiveFile = { file_name: string; is_image?: boolean; size?: number; update_time?: string }
type PreviewPhoto = { file_name: string; objectUrl: string; size: number; update_time: string }
const loading = ref(false)
const saving = ref(false)
const pendingRows = ref<Row[]>([])
const selectedSerials = ref<string[]>([])
const selectedRows = ref<Row[]>([])
const previewPhotosMap = ref<Record<string, PreviewPhoto[]>>({})
const showAllPhotosMap = ref<Record<string, boolean>>({})

const revokePreviewUrls = (serialNo?: string) => {
  const targets = serialNo ? { [serialNo]: previewPhotosMap.value[serialNo] || [] } : previewPhotosMap.value
  Object.values(targets).forEach((photos) => {
    photos.forEach((photo) => {
      if (photo.objectUrl) URL.revokeObjectURL(photo.objectUrl)
    })
  })
  if (serialNo) {
    delete previewPhotosMap.value[serialNo]
    delete showAllPhotosMap.value[serialNo]
  } else {
    previewPhotosMap.value = {}
    showAllPhotosMap.value = {}
  }
}

const loadPreviewPhotos = async (serialNo: string) => {
  if (!serialNo) return
  try {
    const res = await apiGet<ListResponse<ArchiveFile>>(`/inventory/machine-archive/${encodeURIComponent(serialNo)}/files`)
    const imageFiles = (res.data || []).filter((file) => Boolean(file.is_image))
    const photos = await Promise.all(
      imageFiles.map(async (file) => {
        return {
          file_name: String(file.file_name || ''),
          objectUrl: await getMachineArchivePreviewObjectUrl(serialNo, String(file.file_name || '')),
          size: Number(file.size || 0),
          update_time: String(file.update_time || ''),
        } as PreviewPhoto
      })
    )
    previewPhotosMap.value = {
      ...previewPhotosMap.value,
      [serialNo]: photos,
    }
  } catch {
    previewPhotosMap.value = {
      ...previewPhotosMap.value,
      [serialNo]: [],
    }
  }
}

const syncSelectedPreviews = async (rows: Row[]) => {
  const nextSerials = rows.map((row) => String(row['流水号'] || '')).filter(Boolean)
  const nextSet = new Set(nextSerials)

  Object.keys(previewPhotosMap.value).forEach((serialNo) => {
    if (!nextSet.has(serialNo)) {
      revokePreviewUrls(serialNo)
    }
  })

  for (const serialNo of nextSerials) {
    if (!(serialNo in previewPhotosMap.value)) {
      await loadPreviewPhotos(serialNo)
    }
  }
}

const getPreviewCount = (serialNo: string) => (previewPhotosMap.value[serialNo] || []).length
const getPreviewUrls = (serialNo: string) => (previewPhotosMap.value[serialNo] || []).map((photo) => photo.objectUrl)
const getVisiblePhotos = (serialNo: string) => {
  const photos = previewPhotosMap.value[serialNo] || []
  return showAllPhotosMap.value[serialNo] ? photos : photos.slice(0, 8)
}
const getRemainingCount = (serialNo: string) => {
  const total = getPreviewCount(serialNo)
  return total > 8 && !showAllPhotosMap.value[serialNo] ? total - 8 : 0
}
const toggleShowAllPhotos = (serialNo: string) => {
  showAllPhotosMap.value = {
    ...showAllPhotosMap.value,
    [serialNo]: !showAllPhotosMap.value[serialNo],
  }
}

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

const onSelectionChange = async (rows: Row[]) => {
  selectedRows.value = rows
  selectedSerials.value = rows.map((r) => String(r['流水号'] || '')).filter(Boolean)
  await syncSelectedPreviews(rows)
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

onBeforeUnmount(() => {
  revokePreviewUrls()
})
</script>

<style scoped>
.ship-page {
  display: grid;
  gap: var(--space-2);
}
.head-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-2);
}
.title {
  margin: 0;
  font-size: 30px;
  font-weight: 800;
  color: var(--color-gray-800);
}
.ops {
  margin-top: var(--space-2);
  display: flex;
  gap: var(--space-2);
}
.photo-preview {
  margin-top: var(--space-2);
  border-top: 1px solid var(--color-gray-200);
  padding-top: var(--space-2);
}
.preview-title {
  margin: 0 0 12px;
  font-size: 24px;
  font-weight: 800;
  color: var(--color-gray-800);
}
.preview-count {
  margin-bottom: 10px;
  color: var(--color-gray-700);
  font-size: var(--font-size-sm);
}
.preview-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}
.preview-thumb {
  width: 100%;
  height: 220px;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid var(--color-gray-200);
  background: #f8fafc;
}
.preview-actions {
  margin-top: 12px;
}
.empty-tip {
  color: var(--color-gray-500);
  font-size: var(--font-size-sm);
}
</style>
