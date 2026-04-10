<template>
  <div class="home-page">
    <h1 class="page-title">🏭 成品整机管理系统 V7.0</h1>
    <p class="subtitle">当前用户：{{ userName }} | 角色：{{ userRole }}</p>

    <section class="section">
      <h2 class="section-title">👑 管理与统筹</h2>
      <div class="top-cards">
        <button v-if="can('/planning')" class="btn-base top-card" @click="go('/planning')">👑 生产统筹</button>
        <button v-if="can('/contracts')" class="btn-base top-card" @click="go('/contracts')">📊 合同管理</button>
      </div>
    </section>

    <hr class="divider" />

    <section class="section">
      <div class="module-columns">
        <button v-if="can('/inbound')" class="btn-base module-btn" @click="go('/inbound')">📦 成品入库</button>
        <button v-if="can('/shipping-review')" class="btn-base module-btn" @click="go('/shipping-review')">🚚 发货复核</button>
        <button v-if="can('/machine-archive')" class="btn-base module-btn" @click="go('/machine-archive')">📂 机台档案</button>
        <button v-if="can('/sales-orders')" class="btn-base module-btn" @click="go('/sales-orders')">📌 销售下单</button>
        <button v-if="can('/inventory')" class="btn-base module-btn" @click="go('/inventory')">🔍 库存查询</button>
        <button v-if="can('/order-allocation')" class="btn-base module-btn" @click="go('/order-allocation')">📦 订单配货</button>
        <button v-if="can('/machine-edit')" class="btn-base module-btn" @click="go('/machine-edit')">🛠️ 机台编辑</button>
        <button v-if="can('/warehouse-dashboard')" class="btn-base module-btn" @click="go('/warehouse-dashboard')">🖥️ 库位大屏</button>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '../store/user'
import { canAccessPath } from '../router'

const router = useRouter()
const userStore = useUserStore()

const userName = computed(() => userStore.userInfo?.name || '-')
const userRole = computed(() => userStore.userInfo?.role || '-')

const go = (path: string) => {
  router.push(path)
}
const can = (path: string) => canAccessPath(path, userStore.userInfo?.role)

</script>

<style scoped>
.home-page {
  padding: var(--space-6) var(--space-4) var(--space-12);
  container-type: inline-size;
  container-name: home;
}
.page-title {
  margin: 0;
  font-size: clamp(var(--text-3xl), 5vw, var(--text-4xl));
  font-weight: 800;
  color: var(--color-gray-900);
  line-height: var(--leading-tight);
}
.subtitle {
  margin: var(--space-2) 0 var(--space-8);
  color: var(--color-gray-500);
  font-size: var(--text-sm);
}
.section-title {
  margin: 0 0 var(--space-4);
  font-size: clamp(var(--text-2xl), 4vw, var(--text-3xl));
  color: var(--color-gray-900);
  font-weight: 700;
}
.top-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: var(--space-4);
}

/* Base Button Styles based on 8pt system and ratios */
.btn-base {
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  box-shadow: inset 0 0 0 1px var(--border-color-light);
  border-radius: var(--radius-md);
  background: var(--panel-bg);
  color: var(--color-gray-700);
  font-size: var(--text-base);
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  padding: var(--btn-padding-y) var(--btn-padding-x);
  width: 100%;
}

.top-card {
  height: var(--btn-height-primary);
}

.divider {
  margin: var(--space-8) 0;
  border: none;
  border-top: 1px solid var(--border-color-light);
}

.module-columns {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--space-4);
}

.module-btn {
  height: var(--btn-height-secondary);
  width: 100%;
  padding: var(--space-2) var(--space-4);
  justify-content: center;
}

.btn-base:hover {
  box-shadow: 
    inset 0 0 0 1.5px var(--color-primary-100),
    var(--shadow-md);
  color: var(--color-primary-600);
  transform: scale(var(--button-hover-scale));
  z-index: 1;
}

.btn-base:active {
  transform: scale(1);
  box-shadow: inset 0 0 0 1px var(--color-primary-500);
}

.btn-base:focus-visible {
  outline: none;
  box-shadow: var(--shadow-focus);
}

/* Responsive Overrides using Container Queries */
@container home (max-width: 768px) {
  .module-columns {
    grid-template-columns: repeat(2, 1fr); /* 2 columns on mobile for better touch areas */
    gap: var(--space-3);
  }
  
  .top-cards {
    grid-template-columns: 1fr;
  }
}

@container home (max-width: 480px) {
  .module-columns {
    grid-template-columns: 1fr; /* Stack vertically on very small screens */
  }
}
</style>
