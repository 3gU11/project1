<template>
  <div class="page">
    <van-nav-bar title="库位看板" fixed placeholder />

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
        <div class="slot-card__count">{{ slot.current }} / {{ slot.max }}</div>
        <div class="slot-card__desc">当前已装 {{ slot.current }} 台机器</div>
      </div>
    </div>

    <van-popup v-model:show="showSlotPopup" position="bottom" round style="height: 82%;">
      <div class="popup-content">
        <div class="popup-header">
          <div class="popup-title">{{ currentSlot?.code || '-' }}</div>
          <div class="popup-subtitle">
            {{ currentSlot ? `${currentSlot.current} / ${currentSlot.max}` : '-' }} · {{ currentSlot ? slotTag(currentSlot) : '' }}
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
        <div v-if="availableTargetSlots.length" class="target-grid">
          <div
            v-for="slot in availableTargetSlots"
            :key="slot.code"
            class="target-card"
            :class="{ 'target-card--active': targetSlotCode === slot.code }"
            @click="targetSlotCode = slot.code"
          >
            <div class="target-card__code">{{ slot.code }}</div>
            <div class="target-card__meta">{{ slot.current }} / {{ slot.max }}</div>
          </div>
        </div>
        <van-empty v-else description="没有可调拨的目标库位" />

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

const inventoryStore = useInventoryStore()
const showSlotPopup = ref(false)
const currentSlot = ref<MobileSlot | null>(null)
const selectedSerialNo = ref('')
const targetSlotCode = ref('')
const submitting = ref(false)

const currentSlotMachines = computed(() => {
  const code = currentSlot.value?.code || ''
  if (!code) return [] as MobileMachine[]
  return inventoryStore.list.filter((item) => item.slotCode === code && item.status.includes('库存中'))
})

const availableTargetSlots = computed(() => {
  const currentCode = currentSlot.value?.code || ''
  return inventoryStore.slots.filter((slot) => {
    if (!slot.code || slot.code === currentCode) return false
    if (slot.status.includes('锁定') || slot.status.includes('异常')) return false
    return slot.current < slot.max
  })
})

const canTransfer = computed(() => !!selectedSerialNo.value && !!targetSlotCode.value)

const slotClass = (slot: MobileSlot) => {
  if (slot.status.includes('锁定') || slot.status.includes('异常')) return 'slot-card--locked'
  if (slot.current >= slot.max) return 'slot-card--full'
  if (slot.current > 0) return 'slot-card--occupied'
  return 'slot-card--idle'
}

const slotTag = (slot: MobileSlot) => {
  if (slot.status.includes('锁定') || slot.status.includes('异常')) return '锁定/异常'
  if (slot.current >= slot.max) return '已满'
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
  } catch (error: any) {
    showFailToast(error.message || '调拨失败')
  } finally {
    submitting.value = false
  }
}

onMounted(loadData)
</script>

<style scoped>
.page {
  min-height: 100vh;
  background: var(--van-background-2);
}

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
