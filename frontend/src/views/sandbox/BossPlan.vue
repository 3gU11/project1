<template>
  <div class="boss-plan-page">
    <div class="boss-plan-header">
      <div class="header-copy">
        <div class="page-kicker">BOSS 预测沙盘</div>
        <h2>预测沙盘</h2>
        <p>设置机型比例、重算预测方案、调整未确认队列并确认批次。</p>
      </div>
    </div>

    <div class="boss-plan-body">
      <PredictionSandbox />
    </div>
  </div>
</template>

<script setup lang="ts">
import PredictionSandbox from './PredictionSandbox.vue'
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
.header-copy { min-width: 0; }
.page-kicker { margin-bottom: 4px; color: #1677c8; font-size: 12px; font-weight: 700; }

.boss-plan-header p {
  margin: 4px 0 0;
  color: #8e8e93;
  font-size: 13px;
}

.boss-plan-body {
  min-height: calc(100vh - 118px);
}
</style>
