<template>
  <div class="page">
    <div class="card">
      <van-button plain block @click="load">刷新库位</van-button>
    </div>

    <div class="card">
      <div class="slot-grid">
        <div v-for="slot in inventoryStore.slots" :key="slot.code" class="slot-card">
          <strong>{{ slot.code }}</strong>
          <div>{{ slot.current }}/{{ slot.max }}</div>
          <small>{{ slot.status }}</small>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useInventoryStore } from '@/store/inventory'

const inventoryStore = useInventoryStore()

const load = async () => {
  await inventoryStore.loadSlots()
}

onMounted(load)
</script>

<style scoped>
.slot-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}

.slot-card {
  background: #fff;
  border: 1px solid #dcdfe6;
  border-radius: 8px;
  padding: 10px;
}
</style>
