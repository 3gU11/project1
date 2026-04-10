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
        <div class="c bno">批次号</div>
        <div class="c sn">流水号</div>
        <div class="c model">机型</div>
        <div class="c status">状态</div>
        <div class="c loc">库位</div>
        <div class="c order">占用订单号</div>
        <div class="c note">机台备注/配置</div>
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
            <div class="c note">{{ row['机台备注/配置'] || '-' }}</div>
            <div class="c time">{{ row['更新时间'] || '-' }}</div>
          </div>
        </template>
      </VirtualScrollList>
    </div>

    <el-divider />
    <h3>批量修改</h3>
    <el-row :gutter="10">
      <el-col :span="8">
        <div class="label">新的机型（可选）</div>
        <el-select v-model="batchModel" filterable clearable placeholder="请选择机型（不选则不改）" style="width: 100%">
          <el-option v-for="m in modelOptions" :key="m" :label="m" :value="m" />
        </el-select>
      </el-col>
      <el-col :span="8">
        <div class="label">新的机台备注/配置</div>
        <el-input v-model="batchNote" />
      </el-col>
      <el-col :span="8">
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
import { ElMessage } from 'element-plus'
import { apiGetAll, apiPost, getApiErrorMessage } from '../utils/request'
import VirtualScrollList from '../components/VirtualScrollList.vue'
type MessageResponse = { message?: string }

type Row = Record<string, any>
const loading = ref(false)
const saving = ref(false)
const rows = ref<Row[]>([])
const keyword = ref('')
const keywordDebounced = ref('')
let keywordTimer: number | null = null
const selectedSerials = ref<string[]>([])
const selectedSet = ref<Set<string>>(new Set())
const batchModel = ref('')
const batchNote = ref('')
const optXsAuto = ref(false)
const optBackCond = ref(false)

const filteredRows = computed(() => {
  const term = keywordDebounced.value.trim().toLowerCase()
  return rows.value
    .filter((r) => String(r['状态'] || '') !== '已出库')
    .filter((r) => {
      if (!term) return true
      return String(r.__searchText || '').includes(term)
    })
})

watch(keyword, (v) => {
  if (keywordTimer) window.clearTimeout(keywordTimer)
  keywordTimer = window.setTimeout(() => {
    keywordDebounced.value = v
  }, 180)
})

const modelOptions = computed(() => {
  const set = new Set<string>()
  for (const r of rows.value) {
    const m = String(r['机型'] || '').trim()
    if (m) set.add(m)
  }
  return Array.from(set).sort((a, b) => a.localeCompare(b, 'zh-CN'))
})

const loadData = async () => {
  loading.value = true
  try {
    const list = await apiGetAll<Row>('/inventory/')
    rows.value = list.map((x: Row) => ({
      ...x,
      __draftModel: String(x['机型'] || ''),
      __draftNote: String(x['机台备注/配置'] || ''),
      __searchText: `${String(x['流水号'] || '')} ${String(x['占用订单号'] || '')} ${String(x['批次号'] || '')}`.toLowerCase(),
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

const saveBatch = async () => {
  if (selectedSerials.value.length === 0) {
    ElMessage.warning('请先勾选机台')
    return
  }
  saving.value = true
  try {
    const res = await apiPost<MessageResponse>('/inventory/machine-edit/batch-update', {
      serial_nos: selectedSerials.value,
      model: batchModel.value || null,
      note: batchNote.value || null,
      xs_to_auto: optXsAuto.value,
      back_cond: optBackCond.value,
    })
    ElMessage.success(res.message || '批量更新成功')
    await loadData()
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '批量更新失败')
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  keywordDebounced.value = keyword.value
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
.ck {
  display: flex;
  justify-content: center;
}
</style>
