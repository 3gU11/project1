<template>
  <div class="page">
    <div class="card">
      <van-search v-model="keyword" placeholder="搜索机型/流水号/库位" @search="load" />
      <van-button type="primary" block icon="scan" @click="quickScan">快速扫码</van-button>
    </div>

    <div class="card">
      <van-grid :column-num="4" gutter="8">
        <van-grid-item text="总库存" :badge="String(inventoryStore.stats.total)" />
        <van-grid-item text="在库" :badge="String(inventoryStore.stats.inStock)" />
        <van-grid-item text="待处理" :badge="String(inventoryStore.stats.pending)" />
        <van-grid-item text="异常" :badge="String(inventoryStore.stats.error)" />
      </van-grid>
    </div>

    <div class="card">
      <van-list :loading="inventoryStore.loading" finished finished-text="没有更多了">
        <van-cell
          v-for="item in inventoryStore.list"
          :key="item.id"
          :title="item.model || item.serialNo"
          :label="`${item.serialNo} | ${item.slotCode || '-'} | ${item.status}`"
        />
      </van-list>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { showToast } from 'vant'
import { useInventoryStore } from '@/store/inventory'

const inventoryStore = useInventoryStore()
const keyword = ref('')

const load = async () => {
  await inventoryStore.loadInventory(keyword.value)
}

const quickScan = async () => {
  keyword.value = `SN${new Date().getSeconds()}`
  await load()
  showToast(`已按 ${keyword.value} 过滤`)
}

onMounted(load)
</script>
