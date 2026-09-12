<template>
  <div class="page">
    <van-nav-bar title="库位看板" fixed placeholder />

    <div class="search-panel">
      <van-search v-model="serialKeyword" placeholder="查询机台流水号" clearable @search="findMachine" />
      <van-button block type="primary" plain :loading="searching" @click="findMachine">查询流水号</van-button>
      <div v-if="searchedMachine" class="search-result" @click="openMachineTransfer(searchedMachine)">
        <div><strong>{{ searchedMachine.model || '-' }}</strong><span>{{ searchedMachine.serialNo }}</span></div>
        <div class="search-result__slot">当前库位：{{ searchedMachine.slotCode || '未入库' }} · 点击调拨</div>
      </div>
    </div>

    <div class="board-list">
      <div
        v-for="slot in inventoryStore.slots"
        :key="slot.code"
        class="slot-card"
        :class="slotClass(slot)"
        @click="openSlot(slot)"
      >
        <div class="slot-card__head">
          <span class="slot-card__code">{{ slot.code }}</span>
          <span class="slot-card__tag">{{ slotTag(slot) }}</span>
        </div>
        <div class="slot-card__count">{{ slot.current }} / {{ capacityText(slot) }}</div>
        <div class="slot-card__desc">当前已装 {{ slot.current }} 台机器</div>
      </div>
    </div>

    <van-popup v-model:show="showSlotPopup" position="bottom" round style="height: 82%;">
      <div class="popup-content">
        <div class="popup-header">
          <div class="popup-title">{{ currentSlot?.code || '-' }}</div>
          <div class="popup-subtitle">
            {{ currentSlot ? `${currentSlot.current} / ${capacityText(currentSlot)}` : '-' }} · {{ currentSlot ? slotTag(currentSlot) : '' }}
          </div>
        </div>

        <div class="section-title">在库机台</div>
        <div v-if="currentSlotMachines.length" class="machine-list">
          <div
            v-for="item in currentSlotMachines"
            :key="item.serialNo"
            class="machine-card"
            :class="{ 'machine-card--active': selectedSerialNo === item.serialNo }"
            @click="selectedSerialNo = item.serialNo"
          >
            <div class="machine-card__model">{{ item.model || '-' }}</div>
            <div class="machine-card__meta">批次号：{{ item.batchNo || '-' }}</div>
            <div class="machine-card__meta">流水号：{{ item.serialNo || '-' }}</div>
          </div>
        </div>
        <van-empty v-else description="该库位暂无可调拨机台" />

        <div class="section-title">目标库位</div>
        <van-field v-model="targetSlotCode" label="目标库位" placeholder="请输入目标库位名称" clearable />

        <div class="popup-actions">
          <van-button block round @click="showSlotPopup = false">关闭</van-button>
          <van-button
            block
            round
            type="primary"
            :loading="submitting"
            :disabled="!canTransfer"
            style="margin-left: 16px;"
            @click="confirmTransfer"
          >
            确认调拨
          </van-button>
        </div>
      </div>
    </van-popup>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { showFailToast, showSuccessToast, showToast } from 'vant'
import { inventoryApi } from '@/api/inventory'
import { useInventoryStore } from '@/store/inventory'
import type { MobileMachine, MobileSlot } from '@/utils/mapper'
import { useInventoryAutoRefresh } from '@/utils/useInventoryAutoRefresh'

const inventoryStore = useInventoryStore()
const showSlotPopup = ref(false)
const currentSlot = ref<MobileSlot | null>(null)
const selectedSerialNo = ref('')
const targetSlotCode = ref('')
const submitting = ref(false)
const serialKeyword = ref('')
const searching = ref(false)
const searchedMachine = ref<MobileMachine | null>(null)

const currentSlotMachines = computed(() => {
  const code = currentSlot.value?.code || ''
  if (!code) return [] as MobileMachine[]
  return inventoryStore.list.filter((item) => item.slotCode === code && item.status.includes('库存中'))
})

const canTransfer = computed(() => !!selectedSerialNo.value && !!targetSlotCode.value.trim())
const capacityText = (slot: MobileSlot) => slot.unlimited || slot.max === null ? '不限' : String(slot.max)

const slotClass = (slot: MobileSlot) => {
  if (slot.status.includes('锁定') || slot.status.includes('异常')) return 'slot-card--locked'
  if (!slot.unlimited && slot.max !== null && slot.current >= slot.max) return 'slot-card--full'
  if (slot.current > 0) return 'slot-card--occupied'
  return 'slot-card--idle'
}

const slotTag = (slot: MobileSlot) => {
  if (slot.status.includes('锁定') || slot.status.includes('异常')) return '锁定/异常'
  if (!slot.unlimited && slot.max !== null && slot.current >= slot.max) return '已满'
  if (slot.current > 0) return '占用'
  return '空闲'
}

const loadData = async () => {
  await Promise.all([inventoryStore.loadInventory(), inventoryStore.loadSlots()])
}

const openSlot = (slot: MobileSlot) => {
  currentSlot.value = slot
  selectedSerialNo.value = ''
  targetSlotCode.value = ''
  showSlotPopup.value = true
}

const findMachine = async () => {
  const keyword = serialKeyword.value.trim()
  if (!keyword) { showToast('请输入机台流水号'); return }
  searching.value = true
  try {
    // 每次查询前强制恢复看板全量库存，避免复用其他页面留下的筛选列表。
    await inventoryStore.loadInventory()
    searchedMachine.value = inventoryStore.list.find((item) => item.serialNo === keyword) || inventoryStore.list.find((item) => item.serialNo.includes(keyword)) || null
    if (!searchedMachine.value) showToast('未找到对应机台')
  } finally { searching.value = false }
}

const openMachineTransfer = (machine: MobileMachine) => {
  if (!machine.slotCode) { showToast('该机台当前没有库位'); return }
  currentSlot.value = inventoryStore.slots.find((slot) => slot.code === machine.slotCode) || { code: machine.slotCode, current: 0, max: null, unlimited: true, status: '' } as MobileSlot
  selectedSerialNo.value = machine.serialNo
  targetSlotCode.value = ''
  showSlotPopup.value = true
}

const confirmTransfer = async () => {
  if (!selectedSerialNo.value || !targetSlotCode.value) {
    showToast('请选择调拨机台和目标库位')
    return
  }

  submitting.value = true
  try {
    await inventoryApi.inboundToSlot({
      serial_no: selectedSerialNo.value,
      slot_code: targetSlotCode.value,
      is_transfer: true,
    })
    showSuccessToast('调拨成功')
    showSlotPopup.value = false
    selectedSerialNo.value = ''
    targetSlotCode.value = ''
    await loadData()
    searchedMachine.value = inventoryStore.list.find((item) => item.serialNo === selectedSerialNo.value) || null
  } catch (error: any) {
    showFailToast(error.message || '调拨失败')
  } finally {
    submitting.value = false
  }
}

onMounted(loadData)
useInventoryAutoRefresh(loadData)
</script>

<style scoped>
.page {
  min-height: 100vh;
  background: var(--van-background-2);
}

.search-panel {
  padding: 12px;
  background: #fff;
}

.search-panel :deep(.van-button) { margin-top: 8px; }

.search-result {
  margin-top: 10px;
  padding: 12px;
  border: 1px solid var(--van-primary-color);
  border-radius: 10px;
  background: rgba(25, 137, 250, 0.06);
}

.search-result div:first-child { display: flex; justify-content: space-between; gap: 8px; }
.search-result__slot { margin-top: 6px; font-size: 12px; color: var(--van-text-color-2); }

.board-list {
  padding: 12px;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.slot-card {
  background: #fff;
  border-radius: 12px;
  padding: 14px 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}

.slot-card--idle {
  border: 1px solid #16a34a;
}

.slot-card--occupied {
  border: 1px solid var(--van-primary-color);
}

.slot-card--full {
  border: 1px solid var(--van-danger-color);
}

.slot-card--locked {
  border: 1px solid #f59e0b;
}

.slot-card__head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.slot-card__code {
  font-size: 15px;
  font-weight: 600;
  color: var(--van-text-color);
}

.slot-card__tag {
  font-size: 12px;
  color: var(--van-primary-color);
}

.slot-card--full .slot-card__tag {
  color: var(--van-danger-color);
}

.slot-card--locked .slot-card__tag {
  color: #f59e0b;
}

.slot-card--idle .slot-card__tag {
  color: #16a34a;
}

.slot-card__count {
  font-size: 22px;
  font-weight: 700;
  color: var(--van-text-color);
}

.slot-card__desc {
  margin-top: 6px;
  font-size: 12px;
  color: var(--van-text-color-2);
}

.popup-content {
  position: relative;
  height: 100%;
  box-sizing: border-box;
  padding: 16px 16px 32px;
}

.popup-header {
  margin-bottom: 16px;
}

.popup-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--van-text-color);
}

.popup-subtitle {
  margin-top: 4px;
  font-size: 13px;
  color: var(--van-text-color-2);
}

.section-title {
  margin: 16px 0 10px;
  font-size: 14px;
  font-weight: 600;
  color: var(--van-text-color);
}

.machine-list,
.target-grid {
  display: grid;
  gap: 10px;
}

.machine-card,
.target-card {
  background: #fff;
  border: 1px solid var(--van-border-color);
  border-radius: 12px;
  padding: 12px;
}

.machine-card--active,
.target-card--active {
  border-color: var(--van-primary-color);
  background: rgba(25, 137, 250, 0.06);
}

.machine-card__model,
.target-card__code {
  font-size: 14px;
  font-weight: 600;
  color: var(--van-text-color);
}

.machine-card__meta,
.target-card__meta {
  margin-top: 4px;
  font-size: 12px;
  color: var(--van-text-color-2);
}

.popup-actions {
  display: flex;
  margin-top: 24px;
}
</style>
