<template>
  <div class="page">
    <van-nav-bar title="找货" fixed placeholder />

    <div class="search-card">
      <van-search
        v-model="keyword"
        placeholder="搜索流水号/批次号/机型"
        clearable
        @search="resetProgressiveList"
        @clear="resetProgressiveList"
      />
    </div>

    <van-cell class="summary-cell" title="可定位机台" :value="`${filteredList.length} 台`" />

    <van-list
      v-model:loading="loadingMore"
      :finished="finished"
      finished-text="没有更多了"
      @load="onLoad"
    >
      <div
        v-for="item in displayedItems"
        :key="item.id"
        class="locator-card"
      >
        <div class="locator-card__top">
          <div class="slot-code">{{ item.slotCode || '-' }}</div>
          <van-tag :type="item.status.includes('待发货') ? 'warning' : 'primary'" plain>
            {{ item.status || '-' }}
          </van-tag>
        </div>
        <div class="machine-model">{{ item.model || '-' }}</div>
        <div class="meta-row">
          <span>流水号</span>
          <strong>{{ item.serialNo || '-' }}</strong>
        </div>
        <div class="meta-row">
          <span>批次号</span>
          <strong>{{ item.batchNo || '-' }}</strong>
        </div>
      </div>
    </van-list>

    <van-empty v-if="!loadingMore && filteredList.length === 0" description="没有匹配的在库机台" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { showFailToast } from 'vant'
import { useInventoryStore } from '@/store/inventory'

const inventoryStore = useInventoryStore()
const keyword = ref('')
const displayedItems = ref<any[]>([])
const loadingMore = ref(false)
const finished = ref(false)
const currentPage = ref(0)
const PAGE_SIZE = 20

const locatedList = computed(() =>
  inventoryStore.list.filter((item) => {
    if (!item.slotCode) return false
    return item.status.includes('库存中') || item.status.includes('待发货')
  })
)

const filteredList = computed(() => {
  const q = keyword.value.trim().toLowerCase()
  if (!q) return locatedList.value
  return locatedList.value.filter((item) =>
    item.serialNo.toLowerCase().includes(q) ||
    item.batchNo.toLowerCase().includes(q) ||
    item.model.toLowerCase().includes(q)
  )
})

const resetProgressiveList = () => {
  displayedItems.value = []
  currentPage.value = 0
  finished.value = false
  onLoad()
}

const onLoad = () => {
  setTimeout(() => {
    const start = currentPage.value * PAGE_SIZE
    const end = start + PAGE_SIZE
    const nextBatch = filteredList.value.slice(start, end)

    if (nextBatch.length > 0) {
      displayedItems.value.push(...nextBatch)
      currentPage.value += 1
    }

    loadingMore.value = false
    if (displayedItems.value.length >= filteredList.value.length) {
      finished.value = true
    }
  }, 50)
}

const load = async () => {
  try {
    await inventoryStore.loadInventory()
    resetProgressiveList()
  } catch (error: any) {
    showFailToast(error?.message || '加载失败')
  }
}

watch(keyword, () => {
  resetProgressiveList()
})

onMounted(load)
</script>

<style scoped>
.page {
  min-height: 100vh;
  background: var(--van-background-2);
  padding-bottom: 64px;
}

.search-card {
  background: #fff;
  padding-bottom: 4px;
}

.summary-cell {
  margin: 10px 0;
}

.locator-card {
  margin: 10px 12px;
  padding: 12px;
  background: #fff;
  border: 1px solid var(--van-border-color);
  border-radius: 8px;
}

.locator-card__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.slot-code {
  min-width: 0;
  font-size: 22px;
  line-height: 1.15;
  font-weight: 800;
  color: var(--van-primary-color);
  word-break: break-word;
}

.machine-model {
  margin-top: 10px;
  font-size: 16px;
  line-height: 1.35;
  font-weight: 700;
  color: var(--van-text-color);
  word-break: break-word;
}

.meta-row {
  margin-top: 7px;
  display: grid;
  grid-template-columns: 56px minmax(0, 1fr);
  gap: 8px;
  font-size: 13px;
  line-height: 1.35;
}

.meta-row span {
  color: var(--van-text-color-2);
}

.meta-row strong {
  min-width: 0;
  color: var(--van-text-color);
  word-break: break-word;
}
</style>
