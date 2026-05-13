<template>
  <div class="ship-page">
    <PageHeader title="🚛 发货复核">
      <template #actions>
        <el-button type="primary" :loading="loading" @click="loadPending">刷新数据</el-button>
      </template>
    </PageHeader>

    <el-row :gutter="12">
      <el-col :span="9">
        <el-card>
          <template #header>
            <div class="card-head">待发货订单</div>
          </template>
          <el-input v-model="orderKeyword" clearable placeholder="搜索订单号/客户" />
          <div class="order-list">
            <VirtualScrollList :items="filteredOrders" :height="710" :item-height="64" item-key="订单号" :overscan="10">
              <template #default="{ item: o }">
                <button
                  :key="String(o['订单号'] || '')"
                  type="button"
                  class="order-item"
                  :class="{ active: selectedOrderId === String(o['订单号'] || '') }"
                  @click="selectOrder(o)"
                >
                  <div class="order-item-head">
                    <div class="order-customer" :title="o['客户名']">{{ o['客户名'] }}</div>
                    <el-tag type="warning" size="small" class="status-tag">待发货: {{ o.count }}</el-tag>
                  </div>
                  <div class="sub" :title="o['订单号']">{{ o['订单号'] }}</div>
                </button>
              </template>
            </VirtualScrollList>
            <el-empty v-if="filteredOrders.length === 0" description="暂无待发货订单" />
          </div>
        </el-card>
      </el-col>

      <el-col :span="15">
        <el-card>
          <template #header>
            <div class="card-head">复核面板</div>
          </template>
          <el-empty v-if="!selectedOrderId" description="请先选择左侧订单" />
          <template v-else>
            <div class="summary">
              <div>订单号：{{ selectedOrderId }}</div>
              <div>客户：{{ selectedOrder?.['客户名'] || '-' }}</div>
            </div>

            <el-divider />
            <div class="field-label">待发货机台清单</div>
            <el-table
              :data="candidateRows"
              border
              stripe
              size="small"
              height="300"
              @selection-change="onSelectionChange"
            >
              <el-table-column type="selection" width="48" />
              <el-table-column prop="流水号" label="流水号" width="150" />
              <el-table-column prop="机型" label="机型" min-width="160" />
              <el-table-column prop="发货时间" label="发货时间" width="120" />
              <el-table-column prop="合同备注" label="合同备注" min-width="160" />
            </el-table>
            <div class="ops">
              <el-button type="primary" :loading="saving" @click="confirmShip">🚚 确认发货</el-button>
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
          </template>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getMachineArchivePreviewObjectUrl } from '../utils/machineArchivePreview'
import { apiGet, apiPost, getApiErrorMessage } from '../utils/request'
import PageHeader from '../components/PageHeader.vue'
import VirtualScrollList from '../components/VirtualScrollList.vue'

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

const orderKeyword = ref('')
const selectedOrderId = ref('')
const selectedOrder = ref<Row | null>(null)

const orders = computed(() => {
  const map = new Map<string, Row>()
  for (const row of pendingRows.value) {
    const orderId = String(row['占用订单号'] || '').trim()
    if (!orderId) continue
    if (!map.has(orderId)) {
      map.set(orderId, {
        '订单号': orderId,
        '客户名': String(row['客户'] || '').trim(),
        'count': 1
      })
    } else {
      map.get(orderId)!.count++
    }
  }
  return Array.from(map.values())
})

const filteredOrders = computed(() => {
  const term = orderKeyword.value.trim().toLowerCase()
  if (!term) return orders.value
  return orders.value.filter(o => 
    String(o['订单号']).toLowerCase().includes(term) ||
    String(o['客户名']).toLowerCase().includes(term)
  )
})

const candidateRows = computed(() => {
  if (!selectedOrderId.value) return []
  return pendingRows.value.filter(r => String(r['占用订单号'] || '').trim() === selectedOrderId.value)
})

const selectOrder = (row: Row) => {
  selectedOrder.value = row
  selectedOrderId.value = String(row['订单号'] || '')
  selectedRows.value = []
  selectedSerials.value = []
}

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
    
    // Auto-select order or clear selection if no longer exists
    if (selectedOrderId.value) {
      const stillExists = pendingRows.value.some(r => String(r['占用订单号'] || '').trim() === selectedOrderId.value)
      if (!stillExists) {
        selectedOrderId.value = ''
        selectedOrder.value = null
        selectedRows.value = []
        selectedSerials.value = []
      }
    }
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
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.card-head {
  font-weight: 700;
}
.order-list {
  margin-top: var(--space-2);
  max-height: 710px;
}
.order-item {
  border: 1px solid var(--color-gray-200);
  border-radius: var(--radius-lg);
  background: var(--panel-bg);
  padding: 10px 12px;
  min-height: 64px;
  text-align: left;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  justify-content: center;
  width: 100%;
}
.order-item.active {
  border-color: #ef4444;
  background: #fee2e2;
}
.order-item-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  width: 100%;
  gap: 8px;
}
.order-customer {
  flex: 1;
  font-size: var(--font-size-base);
  font-weight: 700;
  color: var(--color-gray-900);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  text-align: left;
}
.status-tag {
  flex-shrink: 0;
}
.sub {
  margin-top: 4px;
  color: var(--color-gray-600);
  font-size: var(--font-size-base);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  text-align: left;
  width: 100%;
}
.summary {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px 10px;
  font-size: var(--font-size-base);
}
.field-label {
  margin-bottom: 6px;
  font-size: var(--font-size-base);
  font-weight: 600;
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