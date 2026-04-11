<template>
  <div class="page">
    <div class="card">
      <ScanButton @success="onScanSuccess" />
      <van-cell title="最近扫码" :value="lastScanned || '-'" />
      <van-button type="primary" block @click="showSlotPicker = true" :disabled="!inboundStore.selectedSerialNos.length">
        选择库位并确认入库 ({{ inboundStore.selectedSerialNos.length }})
      </van-button>
    </div>

    <div class="card">
      <van-divider>待入库设备</van-divider>
      <van-pull-refresh v-model="refreshing" @refresh="refreshList">
        <van-list :loading="inboundStore.loading" finished finished-text="没有更多了">
          <van-cell
            v-for="item in inboundStore.pendingList"
            :key="item.id"
          >
            <template #title>
              <div class="cell-title">批次号：{{ formatBatchNo(item.batchNo) }}</div>
            </template>
            <template #label>
              <div class="cell-label">流水号：{{ item.serialNo || '-' }}</div>
              <div class="cell-label">机型：{{ item.model || '-' }}</div>
            </template>
            <template #right-icon>
              <van-checkbox
                :model-value="inboundStore.selectedSerialNos.includes(item.serialNo)"
                @update:model-value="inboundStore.toggleSelect(item.serialNo)"
              />
            </template>
          </van-cell>
        </van-list>
      </van-pull-refresh>
    </div>

    <van-popup v-model:show="showSlotPicker" position="bottom" round>
      <div class="slot-picker">
        <h3>选择库位</h3>
        <van-search v-model="slotKeyword" placeholder="搜索库位" />
        <div class="slot-grid">
          <button v-for="slot in filteredSlots" :key="slot.code" class="slot-item" @click="confirm(slot.code)">
            <div>{{ slot.code }}</div>
            <small>{{ slot.current }}/{{ slot.max }}</small>
          </button>
        </div>
      </div>
    </van-popup>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { showToast } from 'vant'
import ScanButton from '@/components/common/ScanButton.vue'
import { useInboundStore } from '@/store/inbound'

const inboundStore = useInboundStore()
const refreshing = ref(false)
const showSlotPicker = ref(false)
const slotKeyword = ref('')
const lastScanned = ref('')

const filteredSlots = computed(() => {
  const q = slotKeyword.value.trim().toLowerCase()
  if (!q) {
    return inboundStore.slots
  }
  return inboundStore.slots.filter((x) => x.code.toLowerCase().includes(q))
})

const refreshList = async () => {
  await inboundStore.loadPendingList()
  refreshing.value = false
}

const onScanSuccess = (code: string) => {
  lastScanned.value = code
  const found = inboundStore.pendingList.find((x) => x.serialNo === code)
  if (found?.serialNo) {
    inboundStore.toggleSelect(found.serialNo)
    showToast(`已选中 ${found.serialNo}`)
  } else {
    showToast('未在待入库列表中命中，已记录扫码结果')
  }
}

const formatBatchNo = (raw: string) => {
  const text = String(raw || '').trim()
  if (!text) {
    return '-'
  }
  const matched = text.match(/^(\d{4})(\d{2})第(\d+)批$/)
  if (!matched) {
    return text
  }
  const month = matched[2]
  const batchIndex = String(Number(matched[3]) || 0).padStart(2, '0')
  return `${month}-${batchIndex}`
}

const confirm = async (slotCode: string) => {
  if (!slotCode || inboundStore.selectedSerialNos.length === 0) {
    showToast('请选择设备和库位')
    return
  }
  await inboundStore.confirmInbound(slotCode)
  showToast('入库完成')
  showSlotPicker.value = false
}

onMounted(async () => {
  await inboundStore.loadPendingList()
  await inboundStore.loadSlots()
})
</script>

<style scoped>
.slot-picker {
  padding: 12px;
}

.slot-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  margin-top: 8px;
  max-height: 50vh;
  overflow: auto;
}

.slot-item {
  border: 1px solid #dcdfe6;
  border-radius: 8px;
  background: #fff;
  padding: 10px;
}

.cell-title {
  font-weight: 600;
}

.cell-label {
  color: #666;
  line-height: 1.5;
}
</style>
