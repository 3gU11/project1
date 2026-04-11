<template>
  <div class="page">
    <div class="card">
      <h3>库位大屏（移动端简版）</h3>
      <van-grid :column-num="2" gutter="8">
        <van-grid-item text="库位总数" :badge="String(totalSlots)" />
        <van-grid-item text="占用库位" :badge="String(occupiedSlots)" />
      </van-grid>
    </div>
    <div class="card">
      <van-progress :percentage="usage" stroke-width="10" />
      <p>当前库位使用率：{{ usage }}%</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useInventoryStore } from '@/store/inventory'

const inventoryStore = useInventoryStore()

const totalSlots = computed(() => inventoryStore.slots.length)
const occupiedSlots = computed(() => inventoryStore.slots.filter((x) => x.current > 0).length)
const usage = computed(() => {
  if (!totalSlots.value) {
    return 0
  }
  return Math.round((occupiedSlots.value / totalSlots.value) * 100)
})

onMounted(() => inventoryStore.loadSlots())
</script>
