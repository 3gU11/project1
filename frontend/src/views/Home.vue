<template>
  <div class="home-page">
    <h1 class="page-title">🏭 成品整机管理系统 V7.0</h1>
    <p class="subtitle">当前用户：{{ userName }} | 角色：{{ userRole }}</p>

    <section class="section">
      <h2 class="section-title">👑 管理与统筹</h2>
      <div class="top-cards">
        <button v-if="can('/planning')" class="top-card" @click="go('/planning')">👑 生产统筹</button>
        <button v-if="can('/contracts')" class="top-card" @click="go('/contracts')">📊 合同管理</button>
      </div>
    </section>

    <hr class="divider" />

    <section class="section">
      <div class="module-columns">
        <div class="module-col">
          <button v-if="can('/inbound')" class="module-btn" @click="go('/inbound')">📦 成品入库</button>
          <button v-if="can('/shipping-review')" class="module-btn" @click="go('/shipping-review')">🚚 发货复核</button>
          <button v-if="can('/machine-archive')" class="module-btn" @click="go('/machine-archive')">📂 机台档案</button>
        </div>
        <div class="module-col">
          <button v-if="can('/sales-orders')" class="module-btn" @click="go('/sales-orders')">📌 销售下单</button>
          <button v-if="can('/inventory')" class="module-btn" @click="go('/inventory')">🔍 库存查询</button>
        </div>
        <div class="module-col">
          <button v-if="can('/order-allocation')" class="module-btn" @click="go('/order-allocation')">📦 订单配货</button>
          <button v-if="can('/machine-edit')" class="module-btn" @click="go('/machine-edit')">🛠️ 机台编辑</button>
          <button v-if="can('/warehouse-dashboard')" class="module-btn" @click="go('/warehouse-dashboard')">🖥️ 库位大屏</button>
        </div>
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
  padding: 4px 2px 20px;
}
.page-title {
  margin: 0;
  font-size: 50px;
  font-weight: 800;
  color: #1f2937;
}
.subtitle {
  margin: 8px 0 18px;
  color: #9ca3af;
  font-size: 12px;
}
.section-title {
  margin: 0 0 12px;
  font-size: 36px;
  color: #111827;
}
.top-cards {
  display: grid;
  grid-template-columns: repeat(2, minmax(280px, 1fr));
  gap: 10px;
}
.top-card {
  height: 30px;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  background: #fff;
  color: #334155;
  font-size: 14px;
  cursor: pointer;
}
.divider {
  margin: 24px 0;
  border: none;
  border-top: 1px solid #f0f0f0;
}
.module-columns {
  display: grid;
  grid-template-columns: repeat(3, minmax(180px, 240px));
  gap: 32px;
}
.module-col {
  display: grid;
  gap: 16px;
  align-content: start;
}
.module-btn {
  height: 30px;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  background: #fff;
  color: #334155;
  font-size: 14px;
  text-align: left;
  padding: 0 10px;
  cursor: pointer;
}
.module-btn:hover,
.top-card:hover {
  border-color: #93c5fd;
  color: #1d4ed8;
}
</style>
