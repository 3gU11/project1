<template>
  <div class="layout">
    <div class="layout__content">
      <router-view />
    </div>

    <van-tabbar route safe-area-inset-bottom>
      <van-tabbar-item
        v-for="item in tabbarItems"
        :key="item.to"
        :to="item.to"
        :icon="item.icon"
      >
        {{ item.title }}
      </van-tabbar-item>
    </van-tabbar>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted } from 'vue'
import { useUserStore } from '@/store/user'
import { startInventorySync, stopInventorySync } from '@/utils/inventorySync'

const userStore = useUserStore()

const canViewProduction = computed(() =>
  userStore.userInfo?.role === 'LineOperator' || userStore.hasPermission('MOBILE_KANBAN_VIEW')
)

const tabbarItems = computed(() => {
  if (userStore.userInfo?.role === 'LineOperator') {
    return [
      { title: '生产', to: '/production', icon: 'cluster-o' },
      { title: '我的', to: '/profile', icon: 'user-o' },
    ]
  }

  if (userStore.userInfo?.role === 'Prod') {
    return [
      { title: '查询', to: '/query', icon: 'search' },
      { title: '找货', to: '/locator', icon: 'location-o' },
      { title: '我的', to: '/profile', icon: 'user-o' },
    ]
  }

  const items = [
    { title: '入库', to: '/query', icon: 'scan' },
    { title: '找货', to: '/locator', icon: 'location-o' },
    { title: '看板', to: '/dashboard', icon: 'chart-trending-o' },
  ]
  if (canViewProduction.value) {
    items.push({ title: '生产', to: '/production', icon: 'cluster-o' })
  }
  items.push({ title: '我的', to: '/profile', icon: 'user-o' })
  return items
})

onMounted(() => startInventorySync(userStore.token))
onBeforeUnmount(stopInventorySync)
</script>

<style scoped>
.layout {
  min-height: 100vh;
  background: var(--van-background-2);
}

.layout__content {
  min-height: calc(100vh - 50px);
  padding-bottom: 50px;
}
</style>
