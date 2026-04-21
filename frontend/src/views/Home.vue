<template>
  <div class="home-page">
    <h1 class="page-title">🏭 成品整机管理系统 V7.0</h1>
    <p class="subtitle">当前用户：{{ userName }} | 角色：{{ userRole }}</p>

    <section class="section">
      <h2 class="section-title">👑 管理与统筹</h2>
      <div class="top-cards">
        <button v-if="can('/planning')" class="btn-base top-card" @click="go('/planning')">
          <span class="icon">👑</span> 生产统筹
        </button>
        <button v-if="can('/contracts')" class="btn-base top-card" @click="go('/contracts')">
          <span class="icon">📊</span> 合同管理
        </button>
      </div>
    </section>

    <hr class="divider" />

    <section class="section">
      <div class="module-columns">
        <button v-if="can('/inbound')" class="btn-base module-btn" @click="go('/inbound')">
          <span class="icon">⬇️</span> 成品入库
        </button>
        <button v-if="can('/shipping-review')" class="btn-base module-btn" @click="go('/shipping-review')">
          <span class="icon">🚚</span> 发货复核
        </button>
        <button v-if="can('/machine-archive')" class="btn-base module-btn" @click="go('/machine-archive')">
          <span class="icon">📂</span> 机台档案
        </button>
        <button v-if="can('/sales-orders')" class="btn-base module-btn" @click="go('/sales-orders')">
          <span class="icon">📝</span> 销售下单
        </button>
        <button v-if="can('/inventory')" class="btn-base module-btn" @click="go('/inventory')">
          <span class="icon">🔍</span> 库存查询
        </button>
        <button v-if="can('/order-allocation')" class="btn-base module-btn" @click="go('/order-allocation')">
          <span class="icon">📋</span> 订单配货
        </button>
        <button v-if="can('/machine-edit')" class="btn-base module-btn" @click="go('/machine-edit')">
          <span class="icon">🛠️</span> 机台编辑
        </button>
        <button v-if="can('/warehouse-dashboard')" class="btn-base module-btn" @click="go('/warehouse-dashboard')">
          <span class="icon">🖥️</span> 库位大屏
        </button>
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
  padding: 32px 40px;
  max-width: 1400px;
  margin: 0 auto;
  container-type: inline-size;
  container-name: home;
  min-height: calc(100vh - 44px);
  display: flex;
  flex-direction: column;
}
.page-title {
  margin: 0;
  font-size: max(24px, 3.2vw);
  font-weight: 700;
  color: var(--color-gray-900);
  letter-spacing: -0.01em;
}
.subtitle {
  margin: 4px 0 18px;
  color: var(--color-gray-500);
  font-size: 12px;
}
.section {
  margin-bottom: 18px;
}
.section:last-of-type {
  flex: 1;
  display: flex;
  flex-direction: column;
}
.section-title {
  margin: 0 0 10px;
  font-size: 16px;
  color: var(--color-gray-900);
  font-weight: 700;
}
.top-cards {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 24px;
  width: 100%;
}

.icon {
  margin-right: 0;
  margin-bottom: 12px;
  font-size: 36px;
  opacity: 0.9;
  display: block;
  transition: transform 0.3s ease;
}

/* Base Button Styles based on 8pt system and ratios */
.btn-base {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  border: 1px solid rgba(0,0,0,0.04);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.9);
  box-shadow: 0 4px 14px rgba(0,0,0,0.03);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  color: var(--color-gray-800);
  font-size: 16px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.25, 0.1, 0.25, 1);
  padding: 24px;
  width: 100%;
}

.top-card {
  min-height: 140px;
  font-size: 18px;
}
.top-card .icon {
  font-size: 42px;
  margin-bottom: 16px;
}

.divider {
  margin: 32px 0;
  border: none;
  border-top: 1px solid rgba(0,0,0,0.06);
}

.module-columns {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 24px;
  width: 100%;
}

.module-btn {
  min-height: 120px;
  width: 100%;
  padding: 16px;
}

.btn-base:hover {
  transform: translateY(-4px);
  box-shadow: 0 12px 30px rgba(0,0,0,0.08);
  border-color: rgba(0,0,0,0.08);
  background: rgba(255, 255, 255, 1);
}

.btn-base:hover .icon {
  transform: scale(1.1);
}

.btn-base:active {
  transform: scale(0.97);
  box-shadow: 0 2px 8px rgba(0,0,0,0.05);
}

.btn-base:focus-visible {
  outline: none;
  box-shadow: var(--shadow-focus);
}

/* Responsive Overrides using Container Queries */
@container home (max-width: 768px) {
  .home-page {
    min-height: auto;
    padding: 16px;
  }
  .module-columns {
    grid-template-columns: repeat(2, minmax(140px, 1fr));
    gap: 16px;
    align-content: start;
    flex: none;
    width: 100%;
    margin-left: 0;
  }
  
  .top-cards {
    grid-template-columns: 1fr;
    width: 100%;
    margin-left: 0;
    gap: 16px;
  }

  .module-btn {
    max-width: none;
  }
}

@container home (max-width: 480px) {
  .module-columns {
    grid-template-columns: 1fr; /* Stack vertically on very small screens */
  }
}
</style>
