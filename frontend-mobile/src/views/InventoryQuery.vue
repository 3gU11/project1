<template>
  <div class="page">
    <van-nav-bar :title="pageTitle" fixed placeholder />

    <div class="card search-card">
      <van-search v-model="keyword" placeholder="搜索批次号/流水号/机型/库位" @search="load" />
      
      <!-- 库管角色：增加快捷过滤器 -->
      <div v-if="isProd" class="filter-bar">
        <van-button
          :type="onlyShippingReview ? 'primary' : 'default'"
          size="small"
          round
          plain
          @click="onlyShippingReview = !onlyShippingReview"
        >
          🚢 待发货复核
        </van-button>
      </div>
    </div>

    <div class="card">
      <van-cell :title="countTitle" :value="String(countValue)" />
    </div>

    <div class="card">
      <!-- 库管角色：直接点击编辑 -->
      <van-list
        v-if="isProd"
        v-model:loading="loadingMore"
        :finished="finished"
        finished-text="没有更多了"
        @load="onLoad"
      >
        <van-cell
          v-for="item in displayedItems"
          :key="item.id"
          is-link
          @click="goToEdit(item.serialNo)"
          class="compact-cell"
        >
          <template #title>
            <div class="list-item-content">
              <div class="row-main">
                <span class="machine-model">{{ item.model || '-' }}</span>
                <span class="status-tag">{{ item.status || '-' }}</span>
              </div>
              <div class="row-sub">
                <span>{{ item.batchNo }} | {{ item.serialNo }}</span>
                <span class="slot-text">库位: {{ item.slotCode || '-' }}</span>
              </div>
            </div>
          </template>
        </van-cell>
      </van-list>

      <!-- 入库员角色：勾选入库 -->
      <div v-else>
        <van-checkbox-group v-model="selectedSerialNos" ref="checkboxGroup">
          <van-list
            v-model:loading="loadingMore"
            :finished="finished"
            finished-text="没有更多了"
            @load="onLoad"
          >
            <van-cell
              v-for="item in displayedItems"
              :key="item.id"
              clickable
              @click="toggleSelection(item.serialNo)"
              class="compact-cell"
            >
              <template #title>
                <div class="list-item-content">
                  <div class="row-main">
                    <span class="machine-model">{{ item.model || '-' }}</span>
                    <span class="status-tag">{{ item.status || '-' }}</span>
                  </div>
                  <div class="row-sub">
                    <span>{{ item.batchNo }} | {{ item.serialNo }}</span>
                    <span class="slot-text">库位: {{ item.slotCode || '-' }}</span>
                  </div>
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

        <div class="popup-actions-top">
          <van-button block round @click="showInboundPopup = false">取消</van-button>
          <van-button 
            block 
            round 
            type="primary" 
            :loading="submitting" 
            :disabled="!selectedSlotCode && !slotKeyword.trim()"
            @click="confirmInbound(selectedSlotCode || slotKeyword)" 
            style="margin-left: 16px;"
          >
            确认入库 {{ selectedSlotCode ? `至 ${selectedSlotCode}` : (slotKeyword.trim() ? `至 ${slotKeyword.trim()}` : '') }}
          </van-button>
        </div>
        
        <van-field
          v-model="slotKeyword"
          label="库位号"
          placeholder="请输入或扫描库位号"
          clearable
        />

        <div class="slot-list">
          <div class="slot-title">请选择下方目标库位：</div>
          <van-grid v-if="filteredSlots.length" :column-num="3" gutter="8" clickable>
            <van-grid-item
              v-for="slot in filteredSlots"
              :key="slot.code"
              :class="{ 'active-slot': selectedSlotCode === slot.code }"
              @click="selectedSlotCode = slot.code"
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
const onlyShippingReview = computed({
  get: () => inventoryStore.onlyShippingReview,
  set: (v) => { inventoryStore.onlyShippingReview = v }
})

const isProd = computed(() => userStore.userInfo?.role === 'Prod')
const pageTitle = computed(() => isProd.value ? '查询管理' : '机台入库')
const countTitle = computed(() => (isProd.value ? '现有数量' : '待入库数量'))
const visibleList = computed(() => {
  let list = inventoryStore.list
  if (isProd.value) {
    if (onlyShippingReview.value) {
      list = list.filter((item) => item.status.includes('待发货'))
    }
    return list
  }
  return list.filter((item) => item.status.includes('待入库'))
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
  resetProgressiveList()
}

/** 渐进式渲染逻辑 (解决低性能手机卡顿) */
const displayedItems = ref<any[]>([])
const loadingMore = ref(false)
const finished = ref(false)
const currentPage = ref(0)
const PAGE_SIZE = 20

const resetProgressiveList = () => {
  displayedItems.value = []
  currentPage.value = 0
  finished.value = false
  onLoad()
}

const onLoad = () => {
  // 小延迟模拟平滑加载并避免 UI 阻塞
  setTimeout(() => {
    const start = currentPage.value * PAGE_SIZE
    const end = start + PAGE_SIZE
    const nextBatch = visibleList.value.slice(start, end)
    
    if (nextBatch.length > 0) {
      displayedItems.value.push(...nextBatch)
      currentPage.value++
    }
    
    loadingMore.value = false
    if (displayedItems.value.length >= visibleList.value.length) {
      finished.value = true
    }
  }, 50)
}

// 监听搜索词或过滤器变化，重置列表
import { watch } from 'vue'
watch([keyword, onlyShippingReview], () => {
  resetProgressiveList()
})

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
  const finalSlotCode = (slotCode || selectedSlotCode.value || slotKeyword.value).trim()
  if (!finalSlotCode) {
    showToast('请通过搜索或点击下方卡片选择库位')
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
.search-card {
  padding-bottom: 8px;
}
.filter-bar {
  padding: 0 16px 8px;
  display: flex;
  gap: 8px;
}
.compact-cell {
  padding: 10px 16px;
}
.list-item-content {
  display: flex;
  flex-direction: column;
}
.row-main {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}
.machine-model {
  font-size: 15px;
  font-weight: 600;
  color: var(--van-text-color);
}
.status-tag {
  font-size: 12px;
  background: var(--van-primary-color-light, #eef5fe);
  color: var(--van-primary-color);
  padding: 2px 6px;
  border-radius: 4px;
}
.row-sub {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: #666;
}
.slot-text {
  color: var(--van-primary-color);
  font-weight: 500;
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
.popup-actions-top {
  display: flex;
  margin-bottom: 20px;
  background: #fff;
  z-index: 10;
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
