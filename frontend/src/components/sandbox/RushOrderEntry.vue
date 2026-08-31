<template>
  <div class="rush-entry">
    <div class="rush-header">
      <h3>急单队列</h3>
      <el-button size="small" link type="primary" :loading="rushStore.loadingRushOrders" @click="loadRushOrders">
        刷新
      </el-button>
    </div>

    <div v-if="rushStore.rushOrders.length > 0">
      <el-input
        v-model="rushSearchKeyword"
        class="rush-search"
        clearable
        placeholder="搜索客户名 / 代理商 / 合同号"
      />
      <div class="rush-count">
        待处理急单 ({{ filteredRushOrders.length }} / {{ rushStore.rushOrders.length }})
      </div>
      <VueDraggable
        v-model="draggableRushOrders"
        :group="{ name: 'rush-orders', pull: 'clone', put: false, revertClone: true }"
        item-key="id"
        :sort="false"
        draggable=".rush-card"
        :clone="cloneRushOrder"
      >
        <div v-for="element in filteredRushOrders" :key="element.id" class="rush-card" :data-rush-id="element.id">
          <div class="rush-card-main">
            <strong>{{ element.contract_no }}</strong>
            <span :style="{ color: modelColors[element.model_type] || '#333' }">{{ element.model_type }}</span>
            <span>{{ element.customer || '-' }}</span>
          </div>
          <div class="rush-card-meta">
            {{ element.dealer_name || '-' }} · {{ element.due_date || '-' }}
          </div>
          <div class="rush-card-actions">
            <el-button size="small" type="primary" link @click="autoInsert(element)">自动插入</el-button>
            <el-button size="small" type="success" link @click="returnToSandbox(element)">返回沙盘</el-button>
            <el-button size="small" type="danger" link @click="deleteRushOrder(element)">删除</el-button>
          </div>
        </div>
      </VueDraggable>
      <div v-if="filteredRushOrders.length === 0" class="rush-empty rush-empty-compact">
        未找到匹配的急单
      </div>
    </div>

    <div v-else class="rush-empty">
      合同管理标记急单后自动出现在这里
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { VueDraggable } from 'vue-draggable-plus'
import { ElMessage } from 'element-plus'
import { useRushStore } from '../../stores/useSandboxRushStore'
import { MODEL_COLORS } from '../../utils/sandboxModelType'
import * as sandboxApi from '../../services/sandboxApi'
import { getApiErrorMessage } from '../../utils/request'

const rushStore = useRushStore()
const emit = defineEmits<{
  (e: 'auto-inserted'): void
}>()
const modelColors = MODEL_COLORS
const rushSearchKeyword = ref('')

const filteredRushOrders = computed(() => {
  const keyword = rushSearchKeyword.value.trim().toLowerCase()
  if (!keyword) return rushStore.rushOrders

  return rushStore.rushOrders.filter((order: any) => {
    const searchText = [
      order?.customer,
      order?.dealer_name,
      order?.contract_no
    ].map((value) => String(value || '').toLowerCase()).join(' ')
    return searchText.includes(keyword)
  })
})

const draggableRushOrders = computed({
  get: () => filteredRushOrders.value,
  set: () => {
    // The rush queue is clone-only here; filtering must not rewrite store order.
  }
})

async function loadRushOrders() {
  try {
    await rushStore.fetchRushOrders()
  } catch (e: any) {
    ElMessage.warning(`加载急单队列失败: ${getApiErrorMessage(e) || e.message}`)
  }
}

async function autoInsert(order: any) {
  const rushModel = String(order?.model_type || '').trim()
  if (!rushModel) {
    ElMessage.warning('急单机型为空，无法自动插入')
    return
  }

  const isHigh = String(order?.remark || '').includes('加高')
  const family = rushModel.replace(/加高$/, '').replace(/标准$/, '')

  try {
    const res = await sandboxApi.getBatches({ status: 'In_Production,Confirmed,Predicted', limit: 2000 }) as any
    const batches = Array.isArray(res)
      ? res
      : (res?.batches || res?.data || [])
    
    const hasAvailableSlot = (batches || []).some((b: any) => {
      const bStatus = String(b?.status || '')
      if (!['In_Production', 'Confirmed', 'Predicted'].includes(bStatus)) return false
      
      // 如果是加高急单，不能插入 In_Production
      if (isHigh && bStatus === 'In_Production') return false
      
      return (b?.units || []).some((u: any) => {
        if (Boolean(u?.is_locked)) return false
        
        // 如果该卡片已有合同号，说明它已经被占用（不能算作“空位”直接插入，虽然会顺延，但为了自动插入的稳妥，我们倾向于找真正可承接的位子）
        // 但沙盘的机制是“抢卡片顺延”，所以这里其实只要没有被锁定(is_locked)都可以被抢。
        // 不过如果是加高急单，我们必须确保它能落入一个非生产中的批次。
        const uModel = String(u?.model_type || '').trim()
        if (isHigh) {
          // 加高急单可以抢占同大类的任何未锁定卡片
          return uModel.replace(/加高$/, '').replace(/标准$/, '') === family
        }
        return uModel === rushModel
      })
    })

    if (!hasAvailableSlot) {
      if (isHigh) {
        ElMessage.warning(`自动插入失败：沙盘中无同大类机位（${family}）可供抢占`)
      } else {
        ElMessage.warning(`自动插入失败：当前生产链无可用机型位（${rushModel}）`)
      }
      return
    }
  } catch {
    // 预检失败时继续走后端，让后端给出最终业务校验结果。
  }

  try {
    await rushStore.executeRushAutoInsert(order)
    await rushStore.markRushOrderStatus(order.id, 'inserted')
    emit('auto-inserted')
    ElMessage.success('急单已自动插入')
    await loadRushOrders()
  } catch (e: any) {
    const detail = getApiErrorMessage(e)
    if (detail) {
      ElMessage.error(`自动插入失败: ${detail}`)
    }
  }
}

async function deleteRushOrder(order: any) {
  try {
    await rushStore.markRushOrderStatus(order.id, 'deleted')
    ElMessage.success('急单卡已删除')
    await loadRushOrders()
  } catch (e: any) {
    ElMessage.error(getApiErrorMessage(e) || '删除急单卡失败')
  }
}

async function returnToSandbox(order: any) {
  try {
    await rushStore.returnRushOrderToSandbox(order.id)
    emit('auto-inserted')
    ElMessage.success('急单已返回沙盘')
    await loadRushOrders()
  } catch (e: any) {
    ElMessage.error(getApiErrorMessage(e) || '急单返回沙盘失败')
  }
}

function cloneRushOrder(order: any) {
  return { ...order, __drag_type: 'rush-order' }
}

onMounted(loadRushOrders)
</script>

<style scoped>
.rush-entry {
  height: 100%;
  box-sizing: border-box;
  padding: 8px;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  background: #fff;
  overflow-y: auto;
}
.rush-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}
.rush-header h3 {
  font-size: 13px;
  margin: 0;
}
.rush-count {
  font-size: 11px;
  color: #666;
  margin-bottom: 4px;
}
.rush-search {
  margin-bottom: 5px;
}
.rush-search :deep(.el-input__wrapper) {
  min-height: 26px;
}
.rush-search :deep(.el-input__inner) {
  height: 24px;
  font-size: 12px;
}
.rush-card {
  padding: 5px 7px;
  margin-bottom: 5px;
  border-left: 3px solid #f56c6c;
  border-radius: 5px;
  background: #fff7f7;
  cursor: grab;
}
.rush-card-main {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
  font-size: 11px;
  line-height: 1.25;
}
.rush-card-meta {
  margin-top: 2px;
  font-size: 10px;
  color: #999;
}
.rush-card-actions {
  display: flex;
  gap: 5px;
  justify-content: flex-end;
  margin-top: 2px;
}
.rush-card-actions :deep(.el-button) {
  height: 20px;
  padding: 0;
  font-size: 11px;
}
.rush-empty {
  color: #bbb;
  text-align: center;
  padding: 14px 6px;
  font-size: 12px;
}
.rush-empty-compact {
  padding: 8px 6px 6px;
}
</style>
