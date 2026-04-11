<template>
  <div class="app-layout">
    <van-nav-bar :title="pageTitle" fixed />
    <main class="layout-main">
      <router-view />
    </main>
    <van-tabbar route>
      <van-tabbar-item v-for="tab in tabs" :key="tab.path" :to="tab.path" :icon="tab.icon">
        {{ tab.title }}
      </van-tabbar-item>
    </van-tabbar>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useUserStore } from '@/store/user'

const route = useRoute()
const userStore = useUserStore()

const pageTitle = computed(() => String(route.meta.title || '仓储移动端'))

const tabs = computed(() => {
  const role = String(userStore.userInfo?.role || '').toLowerCase()
  if (role === 'inbound') {
    return [
      { path: '/inbound', title: '入库', icon: 'cart-o' },
      { path: '/inventory-query', title: '查询', icon: 'search' },
      { path: '/profile', title: '我的', icon: 'user-o' },
    ]
  }
  if (role === 'warehouse') {
    return [
      { path: '/inventory-query', title: '库存', icon: 'search' },
      { path: '/slot-management', title: '库位', icon: 'location-o' },
      { path: '/dashboard', title: '大屏', icon: 'chart-trending-o' },
      { path: '/profile', title: '我的', icon: 'user-o' },
    ]
  }
  return [
    { path: '/inbound', title: '入库', icon: 'cart-o' },
    { path: '/inventory-query', title: '查询', icon: 'search' },
    { path: '/slot-management', title: '库位', icon: 'location-o' },
    { path: '/dashboard', title: '大屏', icon: 'chart-trending-o' },
    { path: '/profile', title: '我的', icon: 'user-o' },
  ]
})
</script>

<style scoped>
.layout-main {
  min-height: 100vh;
  padding-top: 46px;
}
</style>
