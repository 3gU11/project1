<template>
  <div class="boss-plan-page">
    <div class="boss-plan-header">
      <div>
        <h2>老板计划</h2>
        <p>生产看板与预测沙盘统一入口</p>
      </div>
      <el-segmented v-model="activeTab" :options="tabOptions" size="large" />
    </div>

    <div class="boss-plan-body">
      <KeepAlive>
        <component :is="activeComponent" />
      </KeepAlive>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import ProductionKanban from './ProductionKanban.vue'
import PredictionSandbox from './PredictionSandbox.vue'

const activeTab = ref('kanban')
const tabOptions = [
  { label: '生产看板', value: 'kanban' },
  { label: '预测沙盘', value: 'sandbox' }
]

const activeComponent = computed(() => (activeTab.value === 'kanban' ? ProductionKanban : PredictionSandbox))
</script>

<style scoped>
.boss-plan-page {
  min-height: calc(100vh - 80px);
  background: #f0f2f5;
}

.boss-plan-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  padding: 18px 20px;
  background: #fff;
  border-bottom: 1px solid #e8e8e8;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.04);
}

.boss-plan-header h2 {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
}

.boss-plan-header p {
  margin: 4px 0 0;
  color: #8e8e93;
  font-size: 13px;
}

.boss-plan-body {
  min-height: calc(100vh - 156px);
}
</style>
