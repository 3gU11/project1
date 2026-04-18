# 机型字典功能重构方案 (Model Dictionary Refactoring Plan)

## 1. 核心目标
当前机型字典功能存在以下问题，需要通过本次重构彻底解决：
1. **前端交互 Bug**：删除按钮滥用 `@mousedown.stop.prevent` 导致点击事件被浏览器吞噬，需要多次点击才能生效。
2. **后端保存逻辑粗暴**：当前保存字典采用“全量删除 + 全量插入”（`DELETE FROM model_dictionary`）的逻辑。这会导致记录的自增 `id` 不断膨胀，且容易引发并发问题或外键/关联丢失问题。
3. **前端状态管理臃肿**：`store/modelDictionary.ts` 中充斥着过度的容错和手动维护 `_rowKey` 的逻辑，不够 Vue 规范。
4. **排序交互过时**：通过“上移/下移”按钮排序体验较差，可改用或保留原逻辑但需简化底层排序数据结构。

重构目标是：**将机型字典改造为基于 `Upsert`（存在则更新，不存在则插入）的增量保存模式，简化前端状态管理，修复事件冲突，统一全局机型排序机制。**

---

## 2. 后端重构 (FastAPI + SQLAlchemy)

### 2.1 数据库持久化逻辑 (`crud/model_dictionary.py`)
**放弃全表删除重插，改为“同步(Sync)”模式**：
- 前端传递包含所有行的数组，每行带有 `id`（如果有）、`model_name`、`sort_order`、`enabled`、`remark`。
- 后端逻辑：
  1. 找出数据库中存在，但前端没传上来的 `id`，执行 **Delete**（物理删除）。
  2. 对前端传上来的行，如果包含 `id` 且在库中存在，执行 **Update**。
  3. 对前端传上来的行，如果没有 `id` 或库中不存在，执行 **Insert**。

**要求修改的函数 `save_model_dictionary(rows: Iterable[dict])`**：
```python
# 伪代码逻辑示例：
def save_model_dictionary(rows: Iterable[dict]) -> int:
    try:
        with get_engine().begin() as conn:
            # 1. 整理前端传入的数据
            incoming_ids = [r.get('id') for r in rows if r.get('id')]
            
            # 2. 删除不在传入列表中的旧数据
            if incoming_ids:
                # 注意处理 incoming_ids 为空的情况，说明全删了
                conn.execute(text("DELETE FROM model_dictionary WHERE id NOT IN :ids"), {"ids": tuple(incoming_ids)})
            else:
                conn.execute(text("DELETE FROM model_dictionary"))
                
            # 3. 遍历 Upsert (使用 INSERT ... ON DUPLICATE KEY UPDATE 或显式 Select+Update/Insert)
            for idx, row in enumerate(rows):
                # 确保 sort_order 是当前的 idx
                # 如果有 ID，尝试 Update
                # 如果没有 ID 或 Update rowcount 为 0，执行 Insert
                pass
        return len(rows)
    except Exception as e:
        raise RuntimeError(f"保存机型字典失败: {e}") from e
```

---

## 3. 前端状态管理重构 (`store/modelDictionary.ts`)

**清理多余的逻辑，保持 Store 纯粹：**
- 移除复杂的 `_rowKey` 生成逻辑，Vue 的 `v-for` 可以直接使用 `row.id`（已存在的）或前端生成的临时 `uuid`（新增的）。
- 只保留 `loadDictionary` 和 `saveDictionary`，将单行删除逻辑（`deleteOne`）合并到统一的 `saveDictionary` 中（即：前端数组删除该项后，调用保存接口即可同步给后端，不需要单独的删除接口）。

**简化的 Store 结构：**
```typescript
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiGet, apiPost } from '../utils/request'
import { setModelOrderList } from '../utils/modelOrder'

export interface ModelDictionaryRow {
  id?: number
  model_name: string
  sort_order: number
  enabled: boolean
  remark: string
  _tempId?: string // 仅用于前端新增行时的 Vue key
}

export const useModelDictionaryStore = defineStore('modelDictionary', () => {
  const rows = ref<ModelDictionaryRow[]>([])
  
  const applyModelOrder = () => {
    const list = rows.value
      .filter((r) => r.enabled && r.model_name)
      .sort((a, b) => a.sort_order - b.sort_order)
      .map((r) => r.model_name)
    setModelOrderList(list)
  }

  const loadDictionary = async () => {
    const res = await apiGet<{ data: ModelDictionaryRow[] }>('/model-dictionary/')
    rows.value = res.data.map((r, index) => ({ ...r, sort_order: index }))
    applyModelOrder()
  }

  const saveDictionary = async (nextRows: ModelDictionaryRow[]) => {
    // 强制按数组顺序重新赋 sort_order
    const payload = nextRows.map((r, index) => ({
      id: r.id,
      model_name: r.model_name.trim(),
      sort_order: index,
      enabled: r.enabled,
      remark: r.remark?.trim() || ''
    }))
    await apiPost('/model-dictionary/save', { rows: payload })
    await loadDictionary() // 保存后重新拉取最新数据（获取新生成的 DB ID）
  }

  return { rows, loadDictionary, saveDictionary, applyModelOrder }
})
```

---

## 4. 前端视图重构 (`views/ModelDictionary.vue`)

### 4.1 修复致命的点击 Bug
在 `el-table` 的操作列中，**必须**将原本的 `@mousedown.stop.prevent` 彻底移除。
**修改前：**
```vue
<el-button size="small" type="danger" @mousedown.stop.prevent @click.stop="removeRow(scope.row)">删除</el-button>
```
**修改后：**
```vue
<el-button size="small" type="danger" @click="removeRow(scope.$index)">删除</el-button>
```

### 4.2 简化组件逻辑
- 直接在本地操作 `rows` 数组，点击“保存字典”时统一提交给后端。
- 不需要每次点击“删除”都调用后端接口。用户在界面上删除某行后，只有点击“保存字典”才会真正在数据库中删除。这提供了“后悔药”机制。

**组件 Script 核心逻辑要求：**
```typescript
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useModelDictionaryStore, type ModelDictionaryRow } from '../store/modelDictionary'

const store = useModelDictionaryStore()
const localRows = ref<ModelDictionaryRow[]>([])
const loading = ref(false)
const saving = ref(false)

const load = async () => {
  loading.value = true
  await store.loadDictionary()
  localRows.value = JSON.parse(JSON.stringify(store.rows)) // 深拷贝到本地编辑
  loading.value = false
}

const addRow = () => {
  localRows.value.push({
    model_name: '',
    sort_order: localRows.value.length,
    enabled: true,
    remark: '',
    _tempId: crypto.randomUUID() // Vue 3 自带的 UUID 生成方法
  })
}

const removeRow = (index: number) => {
  localRows.value.splice(index, 1)
}

const moveUp = (index: number) => {
  if (index <= 0) return
  const temp = localRows.value[index]
  localRows.value[index] = localRows.value[index - 1]
  localRows.value[index - 1] = temp
}

const moveDown = (index: number) => {
  if (index >= localRows.value.length - 1) return
  const temp = localRows.value[index]
  localRows.value[index] = localRows.value[index + 1]
  localRows.value[index + 1] = temp
}

const save = async () => {
  // 1. 校验空机型
  const hasEmpty = localRows.value.some(r => !r.model_name.trim())
  if (hasEmpty) {
    ElMessage.warning('机型名称不能为空')
    return
  }
  // 2. 校验重复
  const names = localRows.value.map(r => r.model_name.trim())
  if (new Set(names).size !== names.length) {
    ElMessage.warning('机型名称不能重复')
    return
  }
  
  saving.value = true
  try {
    await store.saveDictionary(localRows.value)
    localRows.value = JSON.parse(JSON.stringify(store.rows)) // 更新本地状态
    ElMessage.success('机型字典已保存并生效')
  } catch (error) {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  load()
})
```

### 4.3 模板 Table Key 绑定要求
```vue
<el-table :data="localRows" :row-key="row => row.id || row._tempId" border stripe>
  <!-- 列定义 -->
</el-table>
```

---

## 5. 验收标准 (Acceptance Criteria)
1. **点击响应**：鼠标随意点击“删除”按钮的任意位置（包括文字和内边距），必须100%立即触发删除动作，不再出现点击无效的情况。
2. **数据安全**：后端保存不再使用 `DELETE FROM` 全表清空，已存在的机型 `id` 必须保持不变。
3. **操作原子性**：前端的增删改和排序仅在内存中生效，只有点击“保存”时才会向后端发起一次合并提交。
