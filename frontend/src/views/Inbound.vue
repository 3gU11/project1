<template>
  <div class="inbound">
    <h2>📥 入库作业</h2>
    <el-tabs v-model="activeTab">
      <el-tab-pane label="🏭 机台入库 (Machine Inbound)" name="machine">
        <h3 class="machine-title">🏭 机台入库模块 (扫描入库)</h3>
        <div class="machine-filter-row">
          <el-input
            v-model="pendingKeywordRaw"
            @input="onPendingKeywordInput"
            placeholder="扫描批次号/流水号"
            clearable
            style="max-width: 420px"
          />
          <el-button size="small" @click="fetchInventory">刷新</el-button>
        </div>

        <div class="list-caption">待入库清单 ({{ pendingRows.length }} 台)</div>
        <el-table
          ref="pendingTableRef"
          :data="pendingRows"
          row-key="流水号"
          reserve-selection
          border
          stripe
          max-height="430"
          @selection-change="onPendingSelectionChange"
        >
          <el-table-column type="selection" width="48" />
          <el-table-column prop="批次号" label="批次号" width="120" />
          <el-table-column prop="机型" label="机型" width="140" />
          <el-table-column prop="流水号" label="流水号" width="170" />
          <el-table-column prop="机台备注/配置" label="机台备注/配置" min-width="200" show-overflow-tooltip />
        </el-table>
        <div class="selection-hint">当前已勾选：{{ selectedPendingRows.length }} 台</div>

        <div v-if="selectedPendingRows.length > 0">
          <div class="slot-section-title">💟 请选择目标库位进行入库(点击库位按钮确认)</div>
          <div class="machine-filter-row">
            <el-input v-model="slotKeyword" placeholder="快速定位库位，如 A03 / B12" style="max-width: 320px" clearable />
            <span class="selected-tip">已勾选 {{ selectedPendingRows.length }} 台</span>
          </div>
          <div class="slot-btn-grid">
            <button
              v-for="slot in slotButtons"
              :key="slot.id"
              type="button"
              class="slot-btn"
              :class="{ full: slotStats[slot.code]?.isFull, overflow: slotStats[slot.code]?.isOverflow }"
              :disabled="slotStats[slot.code]?.isOverflow"
              @click="confirmInboundBySlot(slot.code)"
            >
              📦 {{ slot.code }} {{ slotButtonText(slot.code) }}
            </button>
          </div>
        </div>
        <div v-else class="slot-hidden-tip">请先在上方勾选待入库机台，库位按钮将自动显示。</div>
      </el-tab-pane>
      <el-tab-pane label="📋 跟踪单导入 (Tracking Import)" name="import">
        <el-card shadow="never" class="import-section">
          <template #header>📤 上传新跟踪单</template>
          <input ref="trackingFileRef" type="file" accept=".xls,.xlsx" />
          <el-button style="margin-left: 10px" type="primary" :loading="uploading" @click="uploadTracking">
            🔍 解析并追加到待入库清单
          </el-button>
        </el-card>

        <el-card shadow="never" class="import-section">
          <template #header>📝 待入库数据审核 (DB Staging)</template>
          <div class="filters">
            <el-input v-model="stagingFilterKeyword" placeholder="筛选关键字" clearable style="width: 220px" />
            <el-select v-model="stagingSortCol" style="width: 160px">
              <el-option label="流水号" value="流水号" />
              <el-option label="批次号" value="批次号" />
              <el-option label="机型" value="机型" />
              <el-option label="预计入库时间" value="预计入库时间" />
            </el-select>
            <el-checkbox v-model="stagingSortAsc">升序</el-checkbox>
            <el-select v-model="stagingPageSize" style="width: 130px">
              <el-option label="10条/页" :value="10" />
              <el-option label="20条/页" :value="20" />
              <el-option label="50条/页" :value="50" />
              <el-option label="100条/页" :value="100" />
            </el-select>
          </div>

          <div class="import-actions">
            <el-checkbox v-model="selectAllCurrentPage">全选/取消全选</el-checkbox>
            <span>已选 {{ selectedCountCurrentPage }} 条</span>
            <el-button size="small" @click="saveCurrentPageEdits">💾 保存本页编辑</el-button>
          </div>

          <el-table :data="stagingPagedRows" border stripe>
            <el-table-column width="52" align="center">
              <template #default="scope">
                <el-checkbox v-model="stagingSelectedMap[scope.row['流水号']]" />
              </template>
            </el-table-column>
            <el-table-column prop="流水号" label="流水号" width="170">
              <template #default="scope">
                <el-input v-model="scope.row['流水号']" />
              </template>
            </el-table-column>
            <el-table-column prop="批次号" label="批次号" width="120">
              <template #default="scope">
                <el-input v-model="scope.row['批次号']" />
              </template>
            </el-table-column>
            <el-table-column prop="机型" label="机型" width="130">
              <template #default="scope">
                <el-input v-model="scope.row['机型']" />
              </template>
            </el-table-column>
            <el-table-column prop="状态" label="状态" width="100">
              <template #default="scope">
                <el-input v-model="scope.row['状态']" />
              </template>
            </el-table-column>
            <el-table-column prop="预计入库时间" label="预计入库时间" width="150">
              <template #default="scope">
                <el-input v-model="scope.row['预计入库时间']" />
              </template>
            </el-table-column>
            <el-table-column prop="机台备注/配置" label="机台备注/配置" min-width="180">
              <template #default="scope">
                <el-input v-model="scope.row['机台备注/配置']" />
              </template>
            </el-table-column>
          </el-table>

          <div class="pagination-container">
            <el-pagination
              v-model:current-page="stagingPageNo"
              v-model:page-size="stagingPageSize"
              :page-sizes="[10, 20, 50, 100]"
              layout="total, sizes, prev, pager, next, jumper"
              :total="stagingFilteredRows.length"
            />
          </div>

          <div class="confirm-row">
            <el-date-picker
              v-model="selectedInboundDate"
              type="date"
              placeholder="预计入库日期"
              format="YYYY-MM-DD"
              value-format="YYYY-MM-DD"
            />
            <el-button type="primary" :disabled="!canConfirmImport" :loading="confirmingImport" @click="confirmImport">
              🚀 确认导入 (Confirm)
            </el-button>
          </div>
        </el-card>

        <el-card shadow="never" class="import-section">
          <template #header>⚡ 辅助功能：自动生成流水号 (Auto Generate)</template>
          <div class="auto-grid">
            <el-input v-model="autoGen.batch" placeholder="批次号" />
            <el-input v-model="autoGen.model" placeholder="机型" />
            <el-input-number v-model="autoGen.qty" :min="1" />
            <el-date-picker v-model="autoGen.expectedDate" type="date" format="YYYY-MM-DD" value-format="YYYY-MM-DD" />
          </div>
          <el-input
            v-model="autoGen.note"
            type="textarea"
            :rows="2"
            placeholder="机台备注/配置"
            style="margin-top: 8px"
          />
          <div class="auto-actions">
            <el-checkbox v-model="autoGen.confirmed">我确认上述信息无误</el-checkbox>
            <el-button type="primary" :disabled="!autoGen.confirmed" :loading="autoGenerating" @click="submitAutoGenerate">
              ✅ 生成并保存到 PLAN_IMPORT
            </el-button>
          </div>
        </el-card>
      </el-tab-pane>
    </el-tabs>

    <div v-if="error" class="error">{{ error }}</div>

  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { apiGet, apiGetAll, apiPost, getApiErrorMessage } from '../utils/request'
import { ElMessage } from 'element-plus'
import { useFormSubmit } from '../composables/useFormSubmit'
import {
  buildSlotStats,
  defaultSlots,
  persistLayoutToLocal,
  restoreLayoutFromLocal,
  type WarehouseSlot
} from './inboundLayout'
type LayoutResponse = { layout_json?: { slots?: WarehouseSlot[] } }
type MessageResponse = { message?: string }
type ImportConfirmResponse = { success_count?: number; failed_count?: number }
type InboundSlotResponse = { ok?: boolean }

const layoutId = 'default'
const activeTab = ref('machine')
const loading = ref(false)
const error = ref('')
const inventory = ref<any[]>([])
const slots = ref<WarehouseSlot[]>([])
const pendingTableRef = ref()
const pendingKeywordRaw = ref('')
const pendingKeyword = ref('')
const slotKeyword = ref('')
let pendingKeywordTimer: any = null

const onPendingKeywordInput = (val: string) => {
  if (pendingKeywordTimer) clearTimeout(pendingKeywordTimer)
  pendingKeywordTimer = setTimeout(() => {
    pendingKeyword.value = val
  }, 300)
}
const selectedPendingRows = ref<any[]>([])
const selectedPendingSerialNos = ref<string[]>([])
const trackingFileRef = ref<HTMLInputElement | null>(null)
const uploading = ref(false)
const confirmingImport = ref(false)
const autoGenerating = ref(false)
const { submitWithLock } = useFormSubmit()

const stagingRows = ref<any[]>([])
const stagingFilterKeyword = ref('')
const stagingSortCol = ref('流水号')
const stagingSortAsc = ref(true)
const stagingPageSize = ref(20)
const stagingPageNo = ref(1)
const stagingSelectedMap = ref<Record<string, boolean>>({})
const selectedInboundDate = ref('')
const autoGen = reactive({
  batch: '',
  model: '',
  qty: 1,
  expectedDate: '',
  note: '',
  confirmed: false,
})

const pendingRows = computed(() => {
  let rows = inventory.value.filter((item) => String(item['状态'] || '').includes('待入库'))
  const kw = pendingKeyword.value.trim().toLowerCase()
  if (kw) {
    // 1. 尝试完全精确匹配“批次号”
    const exactBatchRows = rows.filter((item) => String(item['批次号'] || '').toLowerCase() === kw)
    if (exactBatchRows.length > 0) {
      // 如果有精确匹配的批次号，优先返回该批次所有机台
      return exactBatchRows
    }
    
    // 2. 如果没有精确匹配的批次，则进行默认的模糊匹配
    rows = rows.filter((item) =>
      String(item['流水号'] || '').toLowerCase().includes(kw) ||
      String(item['批次号'] || '').toLowerCase().includes(kw) ||
      String(item['机型'] || '').toLowerCase().includes(kw)
    )
  }
  return rows
})

const slotStats = computed(() => {
  return buildSlotStats(inventory.value, slots.value)
})

const slotButtons = computed(() => {
  const kw = slotKeyword.value.trim().toLowerCase()
  // 过滤掉已满（或溢出）的库位
  const availableSlots = slots.value.filter((s) => {
    const stats = slotStats.value[s.code]
    return !(stats?.isFull || stats?.isOverflow)
  })
  if (!kw) return availableSlots
  return availableSlots.filter((s) => String(s.code || '').toLowerCase().includes(kw))
})

const fetchInventory = async () => {
  loading.value = true
  error.value = ''
  try {
    inventory.value = await apiGetAll<any>('/inventory/')
    await nextTick()
    syncPendingSelectionBySerial()
  } catch (err: any) {
    error.value = getApiErrorMessage(err) || `读取库存失败: ${err.message || err}`
  } finally {
    loading.value = false
  }
}

const fetchImportStaging = async () => {
  try {
    const stagingAllRows = await apiGetAll<any>('/inventory/import-staging')
    stagingRows.value = stagingAllRows.map((r: any) => ({
      流水号: String(r['流水号'] || '').trim(),
      批次号: String(r['批次号'] || '').trim(),
      机型: String(r['机型'] || '').trim(),
      状态: String(r['状态'] || '待入库').trim() || '待入库',
      预计入库时间: String(r['预计入库时间'] || '').slice(0, 10),
      '机台备注/配置': String(r['机台备注/配置'] || ''),
    }))
  } catch (err: any) {
    error.value = getApiErrorMessage(err) || `读取待入库清单失败: ${err.message || err}`
  }
}

const loadLayout = async () => {
  const local = restoreLayoutFromLocal(layoutId)
  if (local.length > 0) {
    slots.value = local
    return
  }
  try {
    const response = await apiGet<LayoutResponse>(`/inventory/layout/${layoutId}`)
    const remoteSlots = response?.layout_json?.slots
    if (Array.isArray(remoteSlots) && remoteSlots.length > 0) {
      slots.value = remoteSlots
      persistLayoutToLocal(layoutId, slots.value)
      return
    }
  } catch (err: any) {
    error.value = getApiErrorMessage(err) || `读取布局失败: ${err.message || err}`
  }
  slots.value = defaultSlots()
}

const stagingFilteredRows = computed(() => {
  let rows = [...stagingRows.value]
  const kw = stagingFilterKeyword.value.trim().toLowerCase()
  if (kw) {
    rows = rows.filter((r) =>
      String(r['流水号'] || '').toLowerCase().includes(kw) ||
      String(r['批次号'] || '').toLowerCase().includes(kw) ||
      String(r['机型'] || '').toLowerCase().includes(kw)
    )
  }
  rows.sort((a, b) => {
    const av = String(a[stagingSortCol.value] || '')
    const bv = String(b[stagingSortCol.value] || '')
    return stagingSortAsc.value ? av.localeCompare(bv) : bv.localeCompare(av)
  })
  return rows
})

const stagingPagedRows = computed(() => {
  const start = (stagingPageNo.value - 1) * stagingPageSize.value
  const end = start + stagingPageSize.value
  return stagingFilteredRows.value.slice(start, end)
})

const selectedCountCurrentPage = computed(() => {
  let count = 0
  for (const row of stagingPagedRows.value) {
    const sn = String(row['流水号'] || '').trim()
    if (sn && stagingSelectedMap.value[sn]) count += 1
  }
  return count
})

const selectAllCurrentPage = computed({
  get() {
    if (stagingPagedRows.value.length === 0) return false
    return stagingPagedRows.value.every((row) => stagingSelectedMap.value[String(row['流水号'] || '').trim()])
  },
  set(v: boolean) {
    for (const row of stagingPagedRows.value) {
      const sn = String(row['流水号'] || '').trim()
      if (sn) stagingSelectedMap.value[sn] = v
    }
  },
})

const canConfirmImport = computed(() => {
  return selectedCountCurrentPage.value > 0 && !!selectedInboundDate.value
})

const saveCurrentPageEdits = async () => {
  const allRows = stagingRows.value.map((r) => ({ ...r }))
  if (allRows.some((r) => !String(r['流水号'] || '').trim())) {
    ElMessage.error('流水号不能为空')
    return
  }
  try {
    await apiPost('/inventory/import-staging/save', { rows: allRows })
    ElMessage.success('已保存本页编辑')
    await fetchImportStaging()
  } catch (err: any) {
    error.value = `保存失败: ${err.message || err}`
  }
}

const uploadTracking = async () => {
  const file = trackingFileRef.value?.files?.[0]
  if (!file) {
    ElMessage.warning('请选择跟踪单文件')
    return
  }
  await submitWithLock(uploading, async () => {
    const fd = new FormData()
    fd.append('file', file)
    const response = await apiPost<MessageResponse>('/inventory/import-staging/upload', fd)
    ElMessage.success(response.message || '解析成功')
    await fetchImportStaging()
  }, {
    errorMessage: '上传解析失败',
    onError: (err) => {
      error.value = getApiErrorMessage(err) || `上传解析失败: ${err?.message || err}`
    },
  })
}

const confirmImport = async () => {
  const selectedTrackNos: string[] = []
  for (const row of stagingPagedRows.value) {
    const sn = String(row['流水号'] || '').trim()
    if (sn && stagingSelectedMap.value[sn]) selectedTrackNos.push(sn)
  }
  if (selectedTrackNos.length === 0) {
    ElMessage.warning('请先勾选至少 1 条数据')
    return
  }
  if (!selectedInboundDate.value) {
    ElMessage.warning('请选择预计入库日期')
    return
  }
  await submitWithLock(confirmingImport, async () => {
    const response = await apiPost<ImportConfirmResponse>('/inventory/import-staging/import-confirm', {
      selected_track_nos: selectedTrackNos,
      expected_inbound_date: selectedInboundDate.value,
    })
    const successCount = Number(response.success_count || 0)
    const failedCount = Number(response.failed_count || 0)
    if (failedCount > 0) {
      ElMessage.warning(`成功 ${successCount} 条，失败 ${failedCount} 条`)
    } else {
      ElMessage.success(`成功导入 ${successCount} 条`)
    }
    await Promise.all([fetchInventory(), fetchImportStaging()])
  }, {
    errorMessage: '导入失败',
    onError: (err) => {
      error.value = getApiErrorMessage(err) || `导入失败: ${err?.message || err}`
    },
  })
}

const submitAutoGenerate = async () => {
  if (!autoGen.batch || !autoGen.model || !autoGen.expectedDate) {
    ElMessage.warning('请填写完整的批次号、机型和预计入库日期')
    return
  }
  await submitWithLock(autoGenerating, async () => {
    const response = await apiPost<MessageResponse>('/inventory/import-staging/auto-generate', {
      batch: autoGen.batch,
      model: autoGen.model,
      qty: autoGen.qty,
      expected_inbound_date: autoGen.expectedDate,
      machine_note: autoGen.note,
    })
    ElMessage.success(response.message || '生成成功')
    autoGen.confirmed = false
    await fetchImportStaging()
  }, {
    errorMessage: '自动生成失败',
    onError: (err) => {
      error.value = getApiErrorMessage(err) || `自动生成失败: ${err?.message || err}`
    },
  })
}

const onPendingSelectionChange = (rows: any[]) => {
  selectedPendingRows.value = rows
  selectedPendingSerialNos.value = rows
    .map((r) => String(r['流水号'] || '').trim())
    .filter((v) => !!v)
}

const syncPendingSelectionBySerial = () => {
  if (!pendingTableRef.value?.toggleRowSelection) return
  const keep = new Set(selectedPendingSerialNos.value)
  pendingTableRef.value.clearSelection?.()
  for (const row of pendingRows.value) {
    const sn = String(row['流水号'] || '').trim()
    if (sn && keep.has(sn)) {
      pendingTableRef.value.toggleRowSelection(row, true)
    }
  }
}

const slotButtonText = (slotCode: string) => {
  const stat = slotStats.value[slotCode]
  const count = Number(stat?.count || 0)
  if (count <= 0) return '(空库)'
  if (count >= 5) return `(${count}/5占用)`
  return `(${count}/5)`
}

const confirmInboundBySlot = async (slotCode: string) => {
  if (selectedPendingRows.value.length === 0) {
    ElMessage.warning('请先勾选待入库列表中的机台')
    return
  }
  if (slotStats.value[slotCode]?.isOverflow) {
    ElMessage.error(`库位 ${slotCode} 已超量，禁止入库`)
    return
  }

  let success = 0
  let failed = 0
  try {
    for (const row of selectedPendingRows.value) {
      try {
        const result = await apiPost<InboundSlotResponse>('/inventory/inbound-to-slot', {
          serial_no: row['流水号'],
          slot_code: slotCode
        })
        if (!result?.ok) {
          failed += 1
        } else {
          success += 1
        }
      } catch {
        failed += 1
      }
    }
    if (failed > 0) {
      ElMessage.warning(`库位 ${slotCode} 入库完成：成功 ${success} 台，失败 ${failed} 台`)
    } else {
      ElMessage.success(`库位 ${slotCode} 入库成功：${success} 台`)
    }
    await fetchInventory()
    selectedPendingRows.value = []
    pendingTableRef.value?.clearSelection?.()
  } catch (err: any) {
    error.value = `入库失败: ${err.message || err}`
  }
}

onMounted(async () => {
  await Promise.all([fetchInventory(), loadLayout(), fetchImportStaging()])
})
</script>

<style scoped>
.inbound {
  background: white;
  padding: 20px;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
}
.toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 14px;
}
.machine-title {
  margin: 0 0 8px;
}
.machine-filter-row {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 10px;
}
.list-caption {
  margin: 10px 0 8px;
  background: #eef6ff;
  color: #1d4ed8;
  padding: 8px 10px;
  border-radius: 6px;
  font-weight: 600;
}
.slot-section-title {
  margin: 14px 0 8px;
  padding: 8px 10px;
  border: 1px solid #eef2f7;
  border-radius: 6px;
  color: #334155;
  font-weight: 600;
}
.selected-tip {
  color: #6b7280;
  font-size: 13px;
}
.selection-hint {
  margin-top: 8px;
  color: #6b7280;
  font-size: 13px;
}
.slot-hidden-tip {
  margin-top: 12px;
  padding: 10px 12px;
  border: 1px dashed #d1d5db;
  border-radius: 8px;
  color: #6b7280;
  background: #fafafa;
  font-size: 13px;
}
.slot-btn-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(120px, 1fr));
  gap: 8px;
}
.slot-btn {
  background: #ef4444;
  border: none;
  border-radius: 6px;
  color: white;
  height: 34px;
  font-size: 13px;
  cursor: pointer;
}
.slot-btn.full {
  background: #f59e0b;
}
.slot-btn.overflow {
  background: #9ca3af;
}
.import-section {
  margin-bottom: 12px;
}
.filters {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 10px;
}
.import-actions {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 10px;
}
.pagination-container {
  margin-top: 10px;
  display: flex;
  justify-content: flex-end;
}
.confirm-row {
  margin-top: 10px;
  display: flex;
  gap: 10px;
  align-items: center;
}
.auto-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(120px, 1fr));
  gap: 8px;
}
.auto-actions {
  margin-top: 10px;
  display: flex;
  gap: 12px;
  align-items: center;
}
button {
  padding: 8px 12px;
  border: none;
  border-radius: 4px;
  background: #409eff;
  color: white;
  cursor: pointer;
}
button:disabled {
  background: #b6d4fe;
  cursor: not-allowed;
}
.danger {
  background: #f56c6c;
}
.error {
  margin: 10px 0;
  color: #f56c6c;
}
</style>
