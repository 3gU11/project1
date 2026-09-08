<template>
  <div class="page">
    <div class="head">
      <h1>🛠️ 机台信息编辑</h1>
      <el-button type="primary" :loading="loading" @click="loadData">刷新数据</el-button>
    </div>

    <el-row :gutter="10">
      <el-col :span="10">
        <el-input v-model="keyword" clearable placeholder="搜索：流水号/订单号/批次号" />
      </el-col>
    </el-row>

    <div class="selection-bar">
      <el-checkbox
        :model-value="allVisibleSelected"
        :indeterminate="isVisibleIndeterminate"
        @change="(v: any) => toggleAllVisible(Boolean(v))"
      >
        全选当前筛选结果
      </el-checkbox>
      <span>已勾选 {{ selectedSerials.length }} 台</span>
    </div>
    <div class="vtable" style="margin-top: 10px">
      <div class="vhead">
        <div class="c ck"></div>
        <div
          class="c bno sortable"
          :class="{ active: sortState?.key === '批次号' }"
          role="button"
          tabindex="0"
          @click="cycleSort('批次号')"
          @keydown.enter.prevent="cycleSort('批次号')"
          @keydown.space.prevent="cycleSort('批次号')"
        >
          <span>批次号</span>
          <span class="sort-mark">{{ sortMark('批次号') }}</span>
        </div>
        <div
          class="c sn sortable"
          :class="{ active: sortState?.key === '流水号' }"
          role="button"
          tabindex="0"
          @click="cycleSort('流水号')"
          @keydown.enter.prevent="cycleSort('流水号')"
          @keydown.space.prevent="cycleSort('流水号')"
        >
          <span>流水号</span>
          <span class="sort-mark">{{ sortMark('流水号') }}</span>
        </div>
        <div
          class="c model sortable"
          :class="{ active: sortState?.key === '机型' }"
          role="button"
          tabindex="0"
          @click="cycleSort('机型')"
          @keydown.enter.prevent="cycleSort('机型')"
          @keydown.space.prevent="cycleSort('机型')"
        >
          <span>机型</span>
          <span class="sort-mark">{{ sortMark('机型') }}</span>
        </div>
        <div class="c status">状态</div>
        <div class="c loc">库位</div>
        <div class="c order">占用订单号</div>
        <div class="c note">合同备注</div>
        <div class="c time">更新时间</div>
      </div>
      <VirtualScrollList :items="filteredRows" :height="500" :item-height="44" item-key="流水号" :overscan="12">
        <template #default="{ item: row }">
          <div class="vrow">
            <div class="c ck">
              <el-checkbox :model-value="isSelected(row)" @change="(v: any) => toggleRow(row, Boolean(v))" />
            </div>
            <div class="c bno">{{ row['批次号'] || '-' }}</div>
            <div class="c sn">{{ row['流水号'] || '-' }}</div>
            <div class="c model">{{ row['机型'] || '-' }}</div>
            <div class="c status">{{ row['状态'] || '-' }}</div>
            <div class="c loc">{{ row['Location_Code'] || '-' }}</div>
            <div class="c order">{{ row['占用订单号'] || '-' }}</div>
            <div class="c note">{{ row['合同备注'] || '-' }}</div>
            <div class="c time">{{ row['更新时间'] || '-' }}</div>
          </div>
        </template>
      </VirtualScrollList>
    </div>

    <el-divider />
    <h3>批量修改</h3>
    <el-row :gutter="10">
      <el-col :span="12">
        <div class="label">新的合同备注</div>
        <el-input v-model="batchNote" />
      </el-col>
      <el-col :span="12">
        <div class="label">新的机型</div>
        <el-select v-model="batchModel" filterable clearable placeholder="不修改机型" style="width: 100%">
          <el-option v-for="m in modelOptions" :key="m" :label="m" :value="m" />
        </el-select>
      </el-col>
    </el-row>
    <el-row :gutter="10" style="margin-top: 10px">
      <el-col :span="12">
        <div class="label">快捷选项</div>
        <el-checkbox v-model="optXsAuto">XS改X手自一体</el-checkbox>
        <el-checkbox v-model="optBackCond">后导电</el-checkbox>
      </el-col>
    </el-row>
    <div class="ops">
      <el-button type="primary" :loading="saving" @click="saveBatch">💾 批量保存修改</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { apiGetAll, apiPost, getApiErrorMessage } from '../utils/request'
import { useModelDictionaryStore } from '../store/modelDictionary'
import { normalizeModelName } from '../utils/modelOrder'
import { productionGroupOfCategory } from '../utils/sandboxCategory'
import VirtualScrollList from '../components/VirtualScrollList.vue'
type MessageResponse = { message?: string }

type Row = Record<string, any>
type SortKey = '批次号' | '流水号' | '机型'
type SortDirection = 'asc' | 'desc'

const modelDictionaryStore = useModelDictionaryStore()
const loading = ref(false)
const saving = ref(false)
const rows = ref<Row[]>([])
const keyword = ref('')
const keywordDebounced = ref('')
let keywordTimer: number | null = null
const selectedSerials = ref<string[]>([])
const selectedSet = ref<Set<string>>(new Set())
const batchNote = ref('')
const batchModel = ref('')
const optXsAuto = ref(false)
const optBackCond = ref(false)
const sortState = ref<{ key: SortKey; direction: SortDirection } | null>(null)

const modelOptions = computed(() =>
  modelDictionaryStore.rows
    .filter((row) => row.enabled && String(row.model_name || '').trim())
    .sort((a, b) => Number(a.sort_order || 0) - Number(b.sort_order || 0))
    .map((row) => String(row.model_name || '').trim())
)

const modelRankMap = computed(() => {
  const map = new Map<string, number>()
  modelOptions.value.forEach((model, index) => {
    const normalized = normalizeModelName(model)
    const variants = [
      normalized,
      normalized.toUpperCase(),
      normalized.replace(/\s+/g, '').toUpperCase(),
      normalized.replace(/-/g, '').toUpperCase(),
    ].filter(Boolean)
    for (const variant of variants) {
      if (!map.has(variant)) map.set(variant, index)
    }
  })
  return map
})

const familyAliases: Record<string, string> = {
  大机XS: '中大型XS',
  大机AUTO: '中大型AUTO',
  小机XS: '中小型XS',
  '小机/XS': '中小型XS',
  小机AUTO: '中小型AUTO',
  小机G: '中小型G',
  SPECIAL: '特殊',
}

const normalizeFamily = (family: unknown) => {
  const value = String(family || '').trim()
  return familyAliases[value] || value
}

const normalizeModelForFamily = (model: unknown) => {
  return String(model || '').replace('(加高)', '').replace('（加高）', '').trim()
}

const modelLookupKeys = (model: unknown) => {
  const clean = normalizeModelForFamily(model)
  if (!clean) return []
  const upper = clean.toUpperCase()
  return Array.from(new Set([
    clean,
    upper,
    upper.replace(/\s+/g, ''),
    upper.replace(/-/g, ''),
  ]))
}

const modelFamilyLookup = computed(() => {
  const map = new Map<string, string>()
  for (const row of modelDictionaryStore.rows) {
    const family = normalizeFamily(row.model_family)
    for (const key of modelLookupKeys(row.model_name)) {
      if (!map.has(key)) map.set(key, family)
    }
  }
  return map
})

const modelFamilyOf = (model: unknown) => {
  for (const key of modelLookupKeys(model)) {
    const family = modelFamilyLookup.value.get(key)
    if (family) return family
  }

  const value = normalizeModelForFamily(model).toUpperCase()
  if (value === '中大型XS' || value === '大机XS') return '中大型XS'
  if (value === '中大型AUTO' || value === '大机AUTO') return '中大型AUTO'
  const isLarge = ['7055', '8055', '8060'].some((token) => value.includes(token))
  if (!isLarge) return ''
  if (value.includes('AUTO')) return '中大型AUTO'
  if (value.includes('XS')) return '中大型XS'
  return ''
}

const rowBySerial = computed(() => {
  const map = new Map<string, Row>()
  for (const row of rows.value) {
    const sn = String(row['流水号'] || '').trim()
    if (sn) map.set(sn, row)
  }
  return map
})

const selectedRows = computed(() =>
  selectedSerials.value
    .map((sn) => rowBySerial.value.get(sn))
    .filter((row): row is Row => !!row)
)

const isBoundRow = (row: Row) => {
  return Boolean(String(row['占用订单号'] || '').trim() || String(row['合同号'] || '').trim())
}

const formatMachineBrief = (row: Row) => {
  const sn = String(row['流水号'] || '').trim() || '-'
  const model = String(row['机型'] || '').trim() || '-'
  return `${sn}(${model})`
}

const formatBoundMachine = (row: Row) => {
  const sn = String(row['流水号'] || '').trim() || '-'
  const orderNo = String(row['占用订单号'] || '').trim()
  const contractNo = String(row['合同号'] || '').trim()
  const refs = [orderNo ? `订单:${orderNo}` : '', contractNo ? `合同:${contractNo}` : ''].filter(Boolean).join('，')
  return `${sn}${refs ? `(${refs})` : ''}`
}

const filteredRows = computed(() => {
  const term = keywordDebounced.value.trim().toLowerCase()
  const result = rows.value
    .filter((r) => String(r['状态'] || '') !== '已出库')
    .filter((r) => {
      if (!term) return true
      return String(r.__searchText || '').includes(term)
    })
  const state = sortState.value
  if (!state) return result
  return [...result].sort((a, b) => compareRows(a, b, state.key, state.direction))
})

const cycleSort = (key: SortKey) => {
  const current = sortState.value
  if (!current || current.key !== key) {
    sortState.value = { key, direction: 'asc' }
  } else if (current.direction === 'asc') {
    sortState.value = { key, direction: 'desc' }
  } else {
    sortState.value = null
  }
}

const sortMark = (key: SortKey) => {
  if (sortState.value?.key !== key) return ''
  return sortState.value.direction === 'asc' ? '↑' : '↓'
}

const compareText = (a: unknown, b: unknown) => {
  const av = String(a || '').trim()
  const bv = String(b || '').trim()
  if (!av && !bv) return 0
  if (!av) return 1
  if (!bv) return -1
  return av.localeCompare(bv, 'zh-CN', { numeric: true, sensitivity: 'base' })
}

const modelRank = (model: unknown) => {
  const normalized = normalizeModelName(model)
  const variants = [
    normalized,
    normalized.toUpperCase(),
    normalized.replace(/\s+/g, '').toUpperCase(),
    normalized.replace(/-/g, '').toUpperCase(),
  ].filter(Boolean)
  for (const variant of variants) {
    const rank = modelRankMap.value.get(variant)
    if (rank !== undefined) return rank
  }
  return 999999
}

const compareModel = (a: unknown, b: unknown) => {
  const rankA = modelRank(a)
  const rankB = modelRank(b)
  if (rankA !== rankB) return rankA - rankB

  const baseA = normalizeModelName(a)
  const baseB = normalizeModelName(b)
  if (baseA !== baseB) return compareText(baseA, baseB)

  const highA = String(a || '').includes('加高') ? 1 : 0
  const highB = String(b || '').includes('加高') ? 1 : 0
  if (highA !== highB) return highA - highB

  return compareText(a, b)
}

const compareRows = (a: Row, b: Row, key: SortKey, direction: SortDirection) => {
  const aValue = a[key]
  const bValue = b[key]
  const aBlank = !String(aValue || '').trim()
  const bBlank = !String(bValue || '').trim()
  if (aBlank && bBlank) return 0
  if (aBlank) return 1
  if (bBlank) return -1

  const base = key === '机型'
    ? compareModel(aValue, bValue)
    : compareText(aValue, bValue)
  return direction === 'asc' ? base : -base
}

watch(keyword, (v) => {
  if (keywordTimer) window.clearTimeout(keywordTimer)
  keywordTimer = window.setTimeout(() => {
    keywordDebounced.value = v
  }, 180)
})

const loadData = async () => {
  loading.value = true
  try {
    const list = await apiGetAll<Row>('/inventory/machine-edit/list')
    rows.value = list.map((x: Row) => ({
      ...x,
      __draftModel: String(x['机型'] || ''),
      __draftNote: String(x['合同备注'] || ''),
      __searchText: `${String(x['流水号'] || '')} ${String(x['占用订单号'] || '')} ${String(x['批次号'] || '')} ${String(x['机型'] || '')}`.toLowerCase(),
    }))
    const valid = new Set(rows.value.map((r) => String(r['流水号'] || '')).filter(Boolean))
    const next = new Set(Array.from(selectedSet.value).filter((sn) => valid.has(sn)))
    selectedSet.value = next
    selectedSerials.value = Array.from(next)
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '读取数据失败')
  } finally {
    loading.value = false
  }
}

const isSelected = (row: Row) => selectedSet.value.has(String(row['流水号'] || ''))
const toggleRow = (row: Row, checked: boolean) => {
  const sn = String(row['流水号'] || '')
  if (!sn) return
  const next = new Set(selectedSet.value)
  if (checked) next.add(sn)
  else next.delete(sn)
  selectedSet.value = next
  selectedSerials.value = Array.from(next)
}
const allVisibleSelected = computed(() => filteredRows.value.length > 0 && filteredRows.value.every((r) => isSelected(r)))
const isVisibleIndeterminate = computed(() => {
  if (filteredRows.value.length === 0) return false
  const hit = filteredRows.value.filter((r) => isSelected(r)).length
  return hit > 0 && hit < filteredRows.value.length
})
const toggleAllVisible = (checked: boolean) => {
  const next = new Set(selectedSet.value)
  if (checked) {
    for (const r of filteredRows.value) {
      const sn = String(r['流水号'] || '')
      if (sn) next.add(sn)
    }
  } else {
    for (const r of filteredRows.value) {
      const sn = String(r['流水号'] || '')
      if (sn) next.delete(sn)
    }
  }
  selectedSet.value = next
  selectedSerials.value = Array.from(next)
}

const confirmBatchModelChange = async (targetModel: string) => {
  const targetFamily = modelFamilyOf(targetModel)
  const targetGroup = productionGroupOfCategory(targetFamily)
  if (!targetFamily || !targetGroup) {
    ElMessage.error(`目标机型未配置族类，无法改型：${targetModel}`)
    return false
  }
  if (selectedRows.value.length !== selectedSerials.value.length) {
    ElMessage.error('部分已勾选流水号已不在当前数据中，请刷新后重试')
    return false
  }

  const invalidRows = selectedRows.value.filter(
    (row) => productionGroupOfCategory(modelFamilyOf(row['机型'])) !== targetGroup
  )
  if (invalidRows.length > 0) {
    const preview = invalidRows.slice(0, 8).map(formatMachineBrief).join('、')
    const targetGroupLabel = targetGroup === 'LARGE' ? '中大型' : targetFamily
    ElMessage.error(`仅允许同生产组改型；目标生产组为 ${targetGroupLabel}，请先剔除不兼容机台：${preview}${invalidRows.length > 8 ? '等' : ''}`)
    return false
  }

  try {
    await ElMessageBox.confirm(
      `确认按流水号将 ${selectedRows.value.length} 台${targetFamily}机台机型改为 ${targetModel}？批次号、流水号、预计入库时间保持不变。`,
      '同族类改型确认',
      {
        confirmButtonText: '确认修改',
        cancelButtonText: '取消',
        type: 'warning',
      }
    )

    const boundRows = selectedRows.value.filter(isBoundRow)
    if (boundRows.length > 0) {
      const preview = boundRows.slice(0, 10).map(formatBoundMachine).join('；')
      ElMessage.error(`已绑定合同或占用订单的机台请到合同管理修改机型：${preview}${boundRows.length > 10 ? '等' : ''}`)
      return false
    }
    return true
  } catch {
    return false
  }
}

const saveBatch = async () => {
  if (selectedSerials.value.length === 0) {
    ElMessage.warning('请先勾选机台')
    return
  }
  const targetModel = String(batchModel.value || '').trim()
  if (targetModel) {
    const confirmed = await confirmBatchModelChange(targetModel)
    if (!confirmed) return
  }
  saving.value = true
  try {
    const res = await apiPost<MessageResponse>('/inventory/machine-edit/batch-update', {
      serial_nos: selectedSerials.value,
      note: batchNote.value || null,
      model_type: targetModel || null,
      xs_to_auto: optXsAuto.value,
      back_cond: optBackCond.value,
      confirm_bound_change: false,
    })
    ElMessage.success(targetModel ? (res.message || '已按流水号修正机型，批次号不变') : (res.message || '批量更新成功'))
    await loadData()
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '批量更新失败')
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  keywordDebounced.value = keyword.value
  modelDictionaryStore.ensureLoaded().catch(() => {})
  loadData()
})
</script>

<style scoped>
.head { display:flex; justify-content:space-between; align-items:center; margin-bottom: var(--space-2); }
.head h1 { margin:0; font-size:30px; }
.label { font-size: var(--font-size-sm); color:var(--color-gray-500); margin-bottom:4px; }
.ops { margin-top: var(--space-2); }
.selection-bar {
  margin-top: var(--space-2);
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: var(--font-size-sm);
  color: var(--color-gray-500);
}
.vtable {
  border: 1px solid var(--color-gray-200);
  border-radius: var(--radius-lg);
  overflow: hidden;
}
.vhead, .vrow {
  display: grid;
  grid-template-columns: 42px 120px 170px 150px 90px 90px 170px 1fr 150px;
  align-items: center;
}
.vhead {
  background: var(--color-gray-50);
  border-bottom: 1px solid var(--color-gray-200);
  font-size: var(--font-size-sm);
  color: var(--color-gray-700);
  font-weight: 600;
  height: 40px;
}
.vrow {
  height: 44px;
  border-bottom: 1px solid #f1f5f9;
  font-size: var(--font-size-sm);
}
.c {
  padding: 0 8px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.sortable {
  display: flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
  user-select: none;
}
.sortable:hover,
.sortable.active {
  color: var(--color-primary-600);
}
.sortable:focus-visible {
  outline: 2px solid var(--color-primary-600);
  outline-offset: -2px;
}
.sort-mark {
  width: 12px;
  flex: 0 0 12px;
  text-align: center;
  font-size: 12px;
}
.ck {
  display: flex;
  justify-content: center;
}
</style>
