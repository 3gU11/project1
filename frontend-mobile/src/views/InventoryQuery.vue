<template>
  <div class="page">
    <van-nav-bar :title="pageTitle" fixed placeholder />

    <div class="card">
      <van-search v-model="keyword" placeholder="搜索批次号/流水号/机型/库位" @search="load" />
    </div>

    <div class="card">
      <van-cell :title="countTitle" :value="String(countValue)" />
    </div>

    <div class="card">
      <!-- 库管角色：直接点击编辑 -->
      <van-list v-if="isProd" :loading="inventoryStore.loading" finished finished-text="没有更多了">
        <van-cell
          v-for="item in visibleList"
          :key="item.id"
          is-link
          @click="goToEdit(item.serialNo)"
        >
          <template #title>
            <div class="primary-row">
              <span class="machine-model">{{ item.model || '-' }}</span>
            </div>
            <div class="important-row">
              <span>批次号：{{ item.batchNo || '-' }}</span>
              <span>流水号：{{ item.serialNo || '-' }}</span>
            </div>
            <div class="secondary-row">
              <span>库位：{{ item.slotCode || '-' }}</span>
              <span>状态：{{ item.status || '-' }}</span>
            </div>
          </template>
        </van-cell>
      </van-list>

      <!-- 入库员角色：勾选入库 -->
      <div v-else>
        <van-checkbox-group v-model="selectedSerialNos" ref="checkboxGroup">
          <van-list :loading="inventoryStore.loading" finished finished-text="没有更多了">
            <van-cell
              v-for="item in visibleList"
              :key="item.id"
              clickable
              @click="toggleSelection(item.serialNo)"
            >
              <template #title>
                <div class="primary-row">
                  <span class="machine-model">{{ item.model || '-' }}</span>
                </div>
                <div class="important-row">
                  <span>批次号：{{ item.batchNo || '-' }}</span>
                  <span>流水号：{{ item.serialNo || '-' }}</span>
                </div>
                <div class="secondary-row">
                  <span>库位：{{ item.slotCode || '-' }}</span>
                  <span>状态：{{ item.status || '-' }}</span>
                </div>
              </template>
              <template #right-icon>
                <van-checkbox :name="item.serialNo" @click.stop />
              </template>
            </van-cell>
          </van-list>
        </van-checkbox-group>

        <!-- 批量入库操作栏 -->
        <div v-if="selectedSerialNos.length > 0" class="action-bar">
          <div class="selected-count">已选 {{ selectedSerialNos.length }} 项</div>
          <van-button type="primary" size="small" @click="showInboundPopup = true">批量入库</van-button>
        </div>
      </div>
    </div>

    <!-- 入库弹窗 -->
    <van-popup v-model:show="showInboundPopup" position="bottom" round style="height: 70%;">
      <div class="popup-content">
        <h3 class="popup-title">选择入库库位</h3>
        
        <van-field
          v-model="slotKeyword"
          label="库位号"
          placeholder="请输入或扫描库位号"
        />

        <div class="slot-list">
          <div class="slot-title">输入库位后，仅显示匹配结果，点击卡片直接入库：</div>
          <van-grid v-if="filteredSlots.length" :column-num="3" gutter="8" clickable>
            <van-grid-item
              v-for="slot in filteredSlots"
              :key="slot.code"
              :text="slot.code"
              :class="{ 'active-slot': selectedSlotCode === slot.code }"
              @click="selectSlotAndInbound(slot.code)"
            >
              <template #text>
                <div class="slot-item-text" :class="{ 'active-text': selectedSlotCode === slot.code }">
                  {{ slot.code }}
                  <div class="slot-capacity">{{ slot.current }}/{{ slot.max }}</div>
                </div>
              </template>
            </van-grid-item>
          </van-grid>
          <van-empty v-else description="没有匹配的库位" />
        </div>

        <div class="popup-actions">
          <van-button block round @click="showInboundPopup = false">取消</van-button>
          <van-button block round type="primary" :loading="submitting" @click="confirmInbound()" style="margin-left: 16px;">
            确认入库
          </van-button>
        </div>
      </div>
    </van-popup>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { showToast, showSuccessToast, showFailToast } from 'vant'
import { useInventoryStore } from '@/store/inventory'
import { useUserStore } from '@/store/user'
import { inventoryApi } from '@/api/inventory'

const router = useRouter()
const inventoryStore = useInventoryStore()
const userStore = useUserStore()

const keyword = ref('')
const selectedSerialNos = ref<string[]>([])
const showInboundPopup = ref(false)
const slotKeyword = ref('')
const selectedSlotCode = ref('')
const submitting = ref(false)

const isProd = computed(() => userStore.userInfo?.role === 'Prod')
const pageTitle = computed(() => isProd.value ? '查询管理' : '机台入库')
const countTitle = computed(() => (isProd.value ? '现有数量' : '待入库数量'))
const visibleList = computed(() => {
  if (isProd.value) {
    return inventoryStore.list
  }
  return inventoryStore.list.filter((item) => item.status.includes('待入库'))
})
const countValue = computed(() => {
  if (isProd.value) {
    return visibleList.value.length
  }
  return visibleList.value.length
})
const filteredSlots = computed(() => {
  const availableSlots = inventoryStore.slots.filter((slot) => slot.current < slot.max)
  const query = slotKeyword.value.trim().toLowerCase()
  if (!query) {
    return availableSlots
  }
  return availableSlots.filter((slot) => slot.code.toLowerCase().includes(query))
})

const load = async () => {
  await inventoryStore.loadInventory(keyword.value)
  if (!isProd.value) {
    await inventoryStore.loadSlots()
  }
}

const goToEdit = (serialNo: string) => {
  if (!serialNo) return
  router.push(`/machine-edit/${serialNo}`)
}

const toggleSelection = (serialNo: string) => {
  const index = selectedSerialNos.value.indexOf(serialNo)
  if (index > -1) {
    selectedSerialNos.value.splice(index, 1)
  } else {
    selectedSerialNos.value.push(serialNo)
  }
}

const confirmInbound = async (slotCode?: string) => {
  const finalSlotCode = (slotCode ?? slotKeyword.value).trim()
  if (!finalSlotCode) {
    showToast('请输入库位号')
    return
  }
  
  submitting.value = true
  try {
    const promises = selectedSerialNos.value.map(sn => 
      inventoryApi.inboundToSlot({
        serial_no: sn,
        slot_code: finalSlotCode
      })
    )
    await Promise.all(promises)
    
    showSuccessToast('入库成功')
    showInboundPopup.value = false
    selectedSerialNos.value = []
    slotKeyword.value = ''
    selectedSlotCode.value = ''
    await load()
  } catch (error: any) {
    showFailToast(error.message || '入库失败')
  } finally {
    submitting.value = false
  }
}

const selectSlotAndInbound = async (slotCode: string) => {
  selectedSlotCode.value = slotCode
  await confirmInbound(slotCode)
}

onMounted(load)
</script>

<style scoped>
.page {
  min-height: 100vh;
  background-color: var(--van-background-2);
  padding-bottom: 60px; /* 为操作栏留出空间 */
}
.card {
  margin-bottom: 12px;
  background: #fff;
}
.primary-row {
  font-size: 15px;
  font-weight: 600;
  color: var(--van-text-color);
}
.machine-model {
  display: inline-block;
  margin-bottom: 4px;
}
.important-row {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  font-size: 13px;
  color: var(--van-text-color);
}
.secondary-row {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  margin-top: 4px;
  font-size: 12px;
  color: var(--van-text-color-2);
}
.action-bar {
  position: fixed;
  bottom: 50px; /* 在tabbar上方 */
  left: 0;
  right: 0;
  padding: 10px 16px;
  background: #fff;
  box-shadow: 0 -2px 10px rgba(0, 0, 0, 0.05);
  display: flex;
  justify-content: space-between;
  align-items: center;
  z-index: 99;
}
.selected-count {
  font-size: 14px;
  color: #666;
}
.popup-content {
  padding: 16px 16px 32px;
}
.popup-title {
  margin: 0 0 16px;
  text-align: center;
  font-size: 16px;
}
.popup-actions {
  display: flex;
  margin-top: 24px;
}
.slot-list {
  margin-top: 16px;
  max-height: calc(70vh - 180px);
  overflow-y: auto;
}
.slot-title {
  font-size: 14px;
  color: #666;
  margin-bottom: 8px;
  padding: 0 16px;
}
.slot-item-text {
  text-align: center;
  font-size: 14px;
  margin-top: 8px;
  color: var(--van-text-color);
}
.slot-capacity {
  font-size: 12px;
  color: #999;
  margin-top: 4px;
}
.active-slot :deep(.van-grid-item__content) {
  background-color: var(--van-primary-color);
}
.active-text {
  color: #fff;
}
.active-text .slot-capacity {
  color: rgba(255, 255, 255, 0.8);
}
</style>
