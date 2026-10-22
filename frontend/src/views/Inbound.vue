<template>
  <div class="inbound">
    <h2>📥 设备入库作业</h2>
    <div v-if="derivedPendingCount > 0" class="derived-notice" @click="activeTab = 'derived'">🔔 有 {{ derivedPendingCount }} 条重入库任务待处理，点击查看</div>
    <el-tabs v-model="activeTab">
      <el-tab-pane label="🏭 设备扫描入库" name="machine">
        <h3 class="machine-title">设备入库登记</h3>
        <div class="machine-filter-row">
          <el-input
            v-model="pendingKeywordRaw"
            @input="onPendingKeywordInput"
            placeholder="请输入批次号或流水号进行检索"
            clearable
            style="max-width: 420px"
          />
          <el-select v-model="pendingSortCol" style="width: 140px">
            <el-option label="批次号" value="批次号" />
            <el-option label="流水号" value="流水号" />
            <el-option label="机型" value="机型" />
          </el-select>
          <el-checkbox v-model="pendingSortAsc">升序</el-checkbox>
          <el-button size="small" @click="fetchInventory">刷新数据</el-button>
        </div>

        <div class="list-caption">待入库设备清单 ({{ pendingRows.length }} 台)</div>
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
          <el-table-column prop="机型" label="机型" min-width="160" />
          <el-table-column prop="流水号" label="流水号" width="170" />
          <el-table-column prop="客户" label="客户" min-width="120" />
          <el-table-column prop="代理商" label="代理商" min-width="120" />
          <el-table-column prop="合同备注" label="合同备注" min-width="200" show-overflow-tooltip />
        </el-table>
        <div class="selection-hint">已选择入库设备：{{ selectedPendingRows.length }} 台</div>

        <div v-if="selectedPendingRows.length > 0">
          <div class="slot-section-title">🎯 请选择目标库位（点击下方库位即确认入库）</div>
          <div class="machine-filter-row">
            <el-input v-model="slotKeyword" placeholder="请输入库位编号快速检索（例如：A03）" style="max-width: 320px" clearable />
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
        <div v-else class="slot-hidden-tip">请先从上方清单中勾选需要入库的设备，系统将自动显示可用库位。</div>
      </el-tab-pane>
      <el-tab-pane label="📋 批量导入跟踪单" name="import">
        <el-card shadow="never" class="import-section">
          <template #header>📝 待入库数据审核</template>
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
            <el-checkbox v-model="selectAllTable">全选/取消全选（全表）</el-checkbox>
            <span>已选 {{ selectedCountAll }} 条</span>
            <el-button size="small" @click="saveCurrentPageEdits">💾 保存本页编辑</el-button>
            <el-button size="small" type="danger" :disabled="selectedCountAll === 0" @click="deleteSelectedStagingRows">
              🗑 删除勾选项
            </el-button>
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
            <el-table-column prop="机型" label="机型" min-width="160">
              <template #default="scope">
                <el-select v-model="scope.row['机型']" filterable placeholder="请选择机型" style="width: 100%">
                  <el-option v-for="model in autoGenModelOptions" :key="model" :label="model" :value="model" />
                </el-select>
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
            <el-table-column prop="客户" label="客户" min-width="120">
              <template #default="scope">
                <el-input v-model="scope.row['客户']" />
              </template>
            </el-table-column>
            <el-table-column prop="代理商" label="代理商" min-width="120">
              <template #default="scope">
                <el-input v-model="scope.row['代理商']" />
              </template>
            </el-table-column>
            <el-table-column prop="合同备注" label="合同备注" min-width="180">
              <template #default="scope">
                <el-input v-model="scope.row['合同备注']" />
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

        </el-card>
      </el-tab-pane>
      <el-tab-pane :label="`🔁 重新入库${derivedPendingCount ? `（${derivedPendingCount}）` : ''}`" name="derived">
        <el-table v-loading="derivedLoading" :data="derivedTasks" stripe border>
          <el-table-column prop="task_no" label="任务编号" min-width="230" />
          <el-table-column prop="object_id" label="机台流水号" min-width="150" />
          <el-table-column prop="source_instance_no" label="来源流程" min-width="220" />
          <el-table-column prop="status" label="状态" width="100" />
          <el-table-column label="操作" width="150" fixed="right"><template #default="{ row }"><el-button size="small" type="primary" @click="reinbound(row)">选择库位入库</el-button></template></el-table-column>
        </el-table>
        <el-empty v-if="!derivedLoading && derivedTasks.length === 0" description="暂无待处理重入库任务" />
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="reinboundDialogVisible" title="选择目标库位" width="420px">
      <div class="reinbound-slot-label">机台：{{ reinboundTask?.object_id }}</div>
      <el-select v-model="selectedReinboundSlot" filterable placeholder="请选择库位" style="width: 100%">
        <el-option v-for="slot in reinboundSlotOptions" :key="slot.code" :label="slot.code" :value="slot.code" />
      </el-select>
      <template #footer>
        <el-button @click="reinboundDialogVisible = false">取消</el-button>
        <el-button type="primary" :disabled="!selectedReinboundSlot" :loading="reinboundSubmitting" @click="confirmReinbound">确认入库</el-button>
      </template>
    </el-dialog>

    <div v-if="error" class="error">{{ error }}</div>

  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { apiGet, apiGetAll, apiPost, getApiErrorMessage } from '../utils/request'
import { ElMessage } from 'element-plus'
import { compareModels, getModelOrderList } from '../utils/modelOrder'
import {
  buildSlotStats,
  defaultSlots,
  getSlotCapacity,
  isUnlimitedSlot,
  prioritizeOldFactorySlots,
  persistLayoutToLocal,
  restoreLayoutFromLocal,
  type WarehouseSlot
} from './inboundLayout'
type LayoutResponse = { layout_json?: { slots?: WarehouseSlot[] } }
type MessageResponse = { message?: string }
type InboundSlotResponse = { ok?: boolean }

const layoutId = 'default'
const activeTab = ref('machine')
const derivedTasks = ref<any[]>([])
const derivedLoading = ref(false)
const derivedPendingCount = ref(0)
const reinboundDialogVisible = ref(false)
const reinboundSubmitting = ref(false)
const reinboundTask = ref<any>(null)
const selectedReinboundSlot = ref('')
const loadDerivedTasks = async () => { derivedLoading.value = true; try { const r = await apiGet<{data:any[]}>('/workflows/derived-tasks'); derivedTasks.value = r.data || []; derivedPendingCount.value = derivedTasks.value.length } finally { derivedLoading.value = false } }
const reinboundSlotOptions = computed(() => slotButtons.value.filter((slot: any) => !slotStats.value[slot.code]?.isOverflow))
const reinbound = (row: any) => { reinboundTask.value = row; selectedReinboundSlot.value = ''; reinboundDialogVisible.value = true }
const confirmReinbound = async () => { const row = reinboundTask.value; const slot = selectedReinboundSlot.value; if (!row || !slot) return; reinboundSubmitting.value = true; try { const result = await apiPost<any>('/inventory/inbound-to-slot', { serial_no: row.object_id, slot_code: slot });
if ((result as any)?.approval_pending) { ElMessage.info((result as any).message + '（' + (result as any).instance_no + '）'); window.dispatchEvent(new Event('workflow-pending-updated')); return }
 if (!result?.ok) throw new Error(result?.message || '入库失败'); await apiPost(`/workflows/derived-tasks/${encodeURIComponent(row.task_no)}/complete`, { reason: `成品入库页面确认，库位：${slot}` }); reinboundDialogVisible.value = false; await loadDerivedTasks(); window.dispatchEvent(new Event('workflow-pending-updated')) } catch (err: any) { ElMessage.error(err?.message || '重新入库失败') } finally { reinboundSubmitting.value = false } }
const loading = ref(false)
const error = ref('')
const inventory = ref<any[]>([])
const slots = ref<WarehouseSlot[]>([])
const pendingTableRef = ref()
const pendingKeywordRaw = ref('')
const pendingKeyword = ref('')
const pendingSortCol = ref('批次号')
const pendingSortAsc = ref(true)
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

const stagingRows = ref<any[]>([])
const stagingFilterKeyword = ref('')
const stagingSortCol = ref('流水号')
const stagingSortAsc = ref(true)
const stagingPageSize = ref(20)
const stagingPageNo = ref(1)
const stagingSelectedMap = ref<Record<string, boolean>>({})

const autoGenModelOptions = computed(() => {
  return getModelOrderList()
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
  rows.sort((a, b) => {
    const av = String(a[pendingSortCol.value] || '')
    const bv = String(b[pendingSortCol.value] || '')
    if (pendingSortCol.value === '机型') {
      return pendingSortAsc.value ? compareModels(av, bv) : compareModels(bv, av)
    }
    return pendingSortAsc.value ? av.localeCompare(bv) : bv.localeCompare(av)
  })
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
  const matchedSlots = kw
    ? availableSlots.filter((s) => String(s.code || '').toLowerCase().includes(kw))
    : availableSlots
  return prioritizeOldFactorySlots(matchedSlots)
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
    const nextRows = stagingAllRows.map((r: any) => ({
      流水号: String(r['流水号'] || '').trim(),
      批次号: String(r['批次号'] || '').trim(),
      机型: String(r['机型'] || '').trim(),
      状态: String(r['状态'] || '待入库').trim() || '待入库',
      预计入库时间: String(r['预计入库时间'] || '').slice(0, 10),
      客户: String(r['客户'] || ''),
      代理商: String(r['代理商'] || ''),
      合同备注: String(r['合同备注'] || ''),
    }))
    stagingRows.value = nextRows
    const validSerials = new Set(nextRows.map((r: any) => String(r['流水号'] || '').trim()).filter((sn: string) => !!sn))
    const nextSelected: Record<string, boolean> = {}
    for (const sn of Object.keys(stagingSelectedMap.value)) {
      if (validSerials.has(sn) && stagingSelectedMap.value[sn]) {
        nextSelected[sn] = true
      }
    }
    stagingSelectedMap.value = nextSelected
  } catch (err: any) {
    error.value = getApiErrorMessage(err) || `读取待入库清单失败: ${err.message || err}`
  }
}

const loadLayout = async () => {
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

  const local = restoreLayoutFromLocal(layoutId)
  if (local.length > 0) {
    slots.value = local
    return
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
    if (stagingSortCol.value === '机型') {
      return stagingSortAsc.value ? compareModels(av, bv) : compareModels(bv, av)
    }
    return stagingSortAsc.value ? av.localeCompare(bv) : bv.localeCompare(av)
  })
  return rows
})

const stagingPagedRows = computed(() => {
  const start = (stagingPageNo.value - 1) * stagingPageSize.value
  const end = start + stagingPageSize.value
  return stagingFilteredRows.value.slice(start, end)
})

const selectedStagingSerialNos = computed(() => {
  return Object.keys(stagingSelectedMap.value).filter((k) => stagingSelectedMap.value[k])
})

const selectedCountAll = computed(() => {
  let count = 0
  for (const row of stagingRows.value) {
    const sn = String(row['流水号'] || '').trim()
    if (sn && stagingSelectedMap.value[sn]) count += 1
  }
  return count
})

const selectAllTable = computed({
  get() {
    if (stagingRows.value.length === 0) return false
    return stagingRows.value.every((row) => stagingSelectedMap.value[String(row['流水号'] || '').trim()])
  },
  set(v: boolean) {
    for (const row of stagingRows.value) {
      const sn = String(row['流水号'] || '').trim()
      if (sn) stagingSelectedMap.value[sn] = v
    }
  },
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

const deleteSelectedStagingRows = async () => {
  const serialNos = [...selectedStagingSerialNos.value]
  if (serialNos.length === 0) {
    ElMessage.warning('请先勾选至少 1 条数据')
    return
  }

  try {
    const response = await apiPost<MessageResponse & { deleted?: number }>('/inventory/import-staging/delete', {
      serial_nos: serialNos,
    })
    for (const sn of serialNos) {
      delete stagingSelectedMap.value[sn]
    }
    ElMessage.success(response.message || `已删除 ${serialNos.length} 条数据`)
    await fetchImportStaging()
  } catch (err: any) {
    error.value = getApiErrorMessage(err) || `删除失败: ${err.message || err}`
  }
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
  if (isUnlimitedSlot(slotCode)) {
    return count <= 0 ? '(不限)' : `(${count}/不限)`
  }
  const capacity = getSlotCapacity(slotCode)
  if (count <= 0) return '(空库)'
  if (count >= capacity) return `(${count}/${capacity}占用)`
  return `(${count}/${capacity})`
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

  let pending = 0
  let success = 0
  let failed = 0
  try {
    for (const row of selectedPendingRows.value) {
      try {
        const result = await apiPost<InboundSlotResponse>('/inventory/inbound-to-slot', {
          serial_no: row['流水号'],
          slot_code: slotCode
        })
        if ((result as any)?.approval_pending) { pending += 1; continue }
        
        if (!result?.ok) {
          failed += 1
        } else {
          success += 1
        }
      } catch {
        failed += 1
      }
    }
    if (pending > 0) { ElMessage.info(`审批已发起：${pending} 台；审批通过后自动入库`) }
    if (failed > 0) {
      ElMessage.warning(`库位 ${slotCode} 入库完成：成功 ${success} 台，失败 ${failed} 台`)
    } else if (success > 0) {
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
  await Promise.all([fetchInventory(), loadLayout(), fetchImportStaging(), loadDerivedTasks()])
})
</script>

<style scoped>
.derived-notice{margin:0 0 12px;padding:10px 14px;border:1px solid #f0b429;border-radius:6px;background:#fff7df;color:#8a5a00;cursor:pointer}
</style>

<style scoped>
.inbound {
  background: white;
  padding: var(--space-4);
  border-radius: var(--radius-lg);
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
  gap: var(--space-3);
  align-items: center;
  margin-bottom: var(--space-2);
}
.list-caption {
  margin: 10px 0 8px;
  background: #eef6ff;
  color: var(--color-primary-700);
  padding: 8px 10px;
  border-radius: var(--radius-md);
  font-weight: 600;
}
.slot-section-title {
  margin: 14px 0 8px;
  padding: 8px 10px;
  border: 1px solid var(--border-color-light);
  border-radius: var(--radius-md);
  color: var(--color-gray-700);
  font-weight: 600;
}
.selected-tip {
  color: var(--color-gray-500);
  font-size: var(--font-size-sm);
}
.selection-hint {
  margin-top: var(--space-2);
  color: var(--color-gray-500);
  font-size: var(--font-size-sm);
}
.slot-hidden-tip {
  margin-top: 12px;
  padding: var(--space-2) var(--space-3);
  border: 1px dashed #d1d5db;
  border-radius: var(--radius-lg);
  color: var(--color-gray-500);
  background: #fafafa;
  font-size: var(--font-size-sm);
}
.slot-btn-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 10px;
}
.slot-btn {
  background: #ef4444;
  border: none;
  border-radius: var(--radius-md);
  color: white;
  min-width: 0;
  height: 42px;
  padding: 0 18px;
  font-size: var(--font-size-sm);
  font-weight: 600;
  line-height: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  cursor: pointer;
}
.slot-btn.full {
  background: #f59e0b;
}
.slot-btn.overflow {
  background: var(--color-gray-400);
}
.import-section {
  margin-bottom: 12px;
}
.filters {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: var(--space-2);
}
.import-actions {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  margin-bottom: var(--space-2);
}
.pagination-container {
  margin-top: var(--space-2);
  display: flex;
  justify-content: flex-end;
}
.confirm-row {
  margin-top: var(--space-2);
  display: flex;
  gap: var(--space-2);
  align-items: center;
}
.auto-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(120px, 1fr));
  gap: 8px;
}
.auto-actions {
  margin-top: var(--space-2);
  display: flex;
  gap: var(--space-3);
  align-items: center;
}
button {
  padding: var(--space-2) var(--space-3);
  border: none;
  border-radius: var(--radius-sm);
  background: var(--color-primary-500);
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
