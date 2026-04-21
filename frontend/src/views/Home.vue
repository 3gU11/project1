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
  padding: 4px 20px 12px;
  container-type: inline-size;
  container-name: home;
  min-height: calc(100vh - 44px);
  display: flex;
  flex-direction: column;
}
.page-title {
  margin: 0;
  font-size: clamp(26px, 3.6vw, 30px);
  font-weight: 800;
  color: var(--color-gray-900);
  line-height: var(--leading-tight);
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
  gap: 14px;
  width: calc(100% - 36px);
  margin-left: 36px; /* 让主页按钮区整体稍微靠右 */
}

/* Base Button Styles based on 8pt system and ratios */
.btn-base {
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
  border: none;
  box-shadow: inset 0 0 0 1.5px var(--border-color-light);
  border-radius: var(--radius-md);
  background: var(--panel-bg);
  color: var(--color-gray-700);
  font-size: 15px;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  padding: 10px 16px;
  width: 100%;
}

.top-card {
  min-height: 62px;
}

.divider {
  margin: 14px 0 20px;
  border: none;
  border-top: 1px solid var(--border-color-light);
}

.module-columns {
  display: grid;
  grid-template-columns: repeat(3, minmax(160px, 1fr));
  gap: 28px 96px;
  justify-content: space-between;
  align-content: space-evenly;
  flex: 1;
  width: calc(100% - 52px);
  margin-left: 52px; /* 模块区整体再向右一点 */
  justify-items: center; /* 每列按钮居中，保证中间列中点更容易对齐 */
}

.module-btn {
  min-height: 66px;
  width: 100%;
  max-width: 210px;
  padding: 12px 14px;
  justify-content: center;
  justify-self: center;
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
  .home-page {
    min-height: auto;
  }
  .module-columns {
    grid-template-columns: repeat(2, minmax(140px, 1fr));
    gap: 12px;
    align-content: start;
    flex: none;
    width: 100%;
    margin-left: 0;
  }
  
  .top-cards {
    grid-template-columns: 1fr;
    width: 100%;
    margin-left: 0;
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
