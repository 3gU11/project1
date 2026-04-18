<template>
  <div class="page">
    <div class="head">
      <h1>📚 机型字典</h1>
      <div class="ops">
        <el-button :loading="loading" @click="load">刷新</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存字典</el-button>
      </div>
    </div>

    <div class="tip">
      说明：机型字典用于全局机型下拉和排序，保存后立即生效。仅启用项会参与排序。
    </div>

    <div class="bar">
      <el-button size="small" type="success" @click="addRow">+ 新增机型</el-button>
      <span>共 {{ rows.length }} 条</span>
    </div>
    <div v-if="deleteDebug" class="debug">{{ deleteDebug }}</div>

    <el-table :data="rows" :row-key="getRowKey" border stripe size="small">
      <el-table-column label="#" width="70">
        <template #default="scope">{{ scope.$index + 1 }}</template>
      </el-table-column>
      <el-table-column label="机型名称" min-width="220">
        <template #default="scope">
          <el-input v-model="scope.row.model_name" placeholder="例如 FR-400G" />
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
          <el-button size="small" :disabled="scope.$index === 0" @click="moveUp(scope.$index)">上移</el-button>
          <el-button size="small" :disabled="scope.$index >= rows.length - 1" @click="moveDown(scope.$index)">下移</el-button>
          <el-button size="small" type="danger" :loading="saving" @mousedown.stop.prevent @click.stop="removeRow(scope.row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getApiErrorMessage } from '../utils/request'
import { useModelDictionaryStore, type ModelDictionaryDeleteMetrics, type ModelDictionaryRow } from '../store/modelDictionary'

const store = useModelDictionaryStore()
const loading = ref(false)
const saving = ref(false)
const rows = ref<ModelDictionaryRow[]>([])
const deleteDebug = ref('')

const createRowKey = () => `tmp-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`

const getRowKey = (row: ModelDictionaryRow) => row._rowKey || `db-${row.id || 'unknown'}`

const normalizeSortOrder = () => {
  rows.value = rows.value.map((r, idx) => ({ ...r, sort_order: idx }))
}

const load = async () => {
  loading.value = true
  try {
    const data = await store.loadDictionary()
    rows.value = data.map((r) => ({ ...r }))
    if (rows.value.length === 0) addRow()
    normalizeSortOrder()
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '读取机型字典失败')
  } finally {
    loading.value = false
  }
}

const addRow = () => {
  rows.value.push({
    model_name: '',
    sort_order: rows.value.length,
    enabled: true,
    remark: '',
    _rowKey: createRowKey(),
  })
}

const removeRow = async (target: ModelDictionaryRow) => {
  if (!target) return
  const targetName = String(target.model_name || '').trim()
  const label = targetName || `ID:${target.id || 'new'}`
  const startedAt = performance.now()
  const targetKey = getRowKey(target)

  saving.value = true
  try {
    let metrics: ModelDictionaryDeleteMetrics | null = null
    if (targetName || target.id) {
      metrics = await store.deleteOne(target)
    }

    const beforeLocalRemoveAt = performance.now()
    rows.value = rows.value.filter((row) => getRowKey(row) !== targetKey)
    if (rows.value.length === 0) addRow()
    normalizeSortOrder()
    const afterLocalRemoveAt = performance.now()
    const localRemoveMs = Number((afterLocalRemoveAt - beforeLocalRemoveAt).toFixed(1))
    const totalMs = Number((afterLocalRemoveAt - startedAt).toFixed(1))
    deleteDebug.value = [
      `最近一次删除: ${label}`,
      `接口 ${metrics?.requestMs ?? 0}ms`,
      `刷新 ${metrics?.reloadMs ?? 0}ms`,
      `本地移除 ${localRemoveMs}ms`,
      `总计 ${totalMs}ms`,
    ].join(' | ')
    console.info('[ModelDictionary] delete metrics', {
      label,
      requestMs: metrics?.requestMs ?? 0,
      reloadMs: metrics?.reloadMs ?? 0,
      localRemoveMs,
      totalMs,
    })
    ElMessage.success(`机型已删除，总耗时 ${totalMs}ms`)
  } catch (err: any) {
    deleteDebug.value = `最近一次删除失败: ${label} | ${getApiErrorMessage(err) || '删除失败'}`
    ElMessage.error(getApiErrorMessage(err) || '删除失败')
  } finally {
    saving.value = false
  }
}

const moveUp = (idx: number) => {
  if (idx <= 0) return
  const prev = rows.value[idx - 1]
  rows.value[idx - 1] = rows.value[idx]
  rows.value[idx] = prev
  normalizeSortOrder()
}

const moveDown = (idx: number) => {
  if (idx >= rows.value.length - 1) return
  const next = rows.value[idx + 1]
  rows.value[idx + 1] = rows.value[idx]
  rows.value[idx] = next
  normalizeSortOrder()
}

const save = async () => {
  const names = rows.value.map((r) => String(r.model_name || '').trim()).filter((x) => !!x)
  if (names.length === 0) {
    ElMessage.warning('至少保留 1 个机型')
    return
  }
  if (new Set(names).size !== names.length) {
    ElMessage.warning('机型名称不能重复')
    return
  }
  saving.value = true
  try {
    normalizeSortOrder()
    await store.saveDictionary(rows.value)
    rows.value = store.rows.map((r) => ({ ...r }))
    normalizeSortOrder()
    ElMessage.success('机型字典已保存并生效')
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '保存失败')
  } finally {
    saving.value = false
  }
}

load()
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
.debug {
  margin-bottom: var(--space-2);
  color: var(--color-primary);
  font-size: 13px;
  word-break: break-all;
}
</style>
