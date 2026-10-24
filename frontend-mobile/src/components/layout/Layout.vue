<template>
  <div class="layout">
    <div class="layout__content">
      <router-view :key="viewKey" />
    </div>

    <van-tabbar route safe-area-inset-bottom>
      <van-tabbar-item
        v-for="item in tabbarItems"
        :key="item.to"
        :to="item.to"
        :icon="item.icon"
        :badge="item.badge || ''"
      >
        {{ item.title }}
      </van-tabbar-item>
    </van-tabbar>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useUserStore } from '@/store/user'
import { startInventorySync, stopInventorySync } from '@/utils/inventorySync'
import { workflowApi } from '@/api/workflow'

const userStore = useUserStore()
const route = useRoute()
const viewKey = computed(() => `${route.fullPath}:${String(userStore.userInfo?.role || '').trim().toLowerCase()}`)

const unreadCount = ref(0)
const unreadBadge = computed(() => (unreadCount.value > 99 ? '99+' : unreadCount.value || ''))
let unreadTimer: ReturnType<typeof setInterval> | undefined

/** 仅入库员有消息入口；失败时静默，不打断现场作业。 */
const refreshUnread = async () => {
  if (String(userStore.userInfo?.role || '').trim() !== 'Inbound') return
  try {
    const res = await workflowApi.getPersonalMessages({ page: 1, limit: 1, unread: true })
    unreadCount.value = Number(res.unread_count || 0)
  } catch { /* ignore */ }
}

type TabItem = { title: string; to: string; icon: string; badge?: string }

const tabbarItems = computed<TabItem[]>(() => {
  const role = String(userStore.userInfo?.role || '').trim()

  if (role === 'LineOperator') {
    return [
      { title: '生产', to: '/production', icon: 'cluster-o' },
      { title: '我的', to: '/profile', icon: 'user-o' },
    ]
  }

  if (role === 'AfterSales') {
    return [
      { title: '扫码任务', to: '/query', icon: 'scan' },
      { title: '我的', to: '/profile', icon: 'user-o' },
    ]
  }

  if (role === 'Prod') {
    return [
      { title: '查询', to: '/query', icon: 'search' },
      { title: '我的', to: '/profile', icon: 'user-o' },
    ]
  }

  if (role === 'Inbound') {
    return [
      { title: '查询', to: '/query', icon: 'search' },
      { title: '找货', to: '/locator', icon: 'location-o' },
      { title: '看板', to: '/dashboard', icon: 'chart-trending-o' },
      { title: '消息', to: '/messages', icon: 'bell', badge: unreadBadge.value },
      { title: '我的', to: '/profile', icon: 'user-o' },
    ]
  }

  return [
    { title: '我的', to: '/profile', icon: 'user-o' },
  ]
})

onMounted(async () => {
  await userStore.refreshUser()
  startInventorySync(userStore.token)
  await refreshUnread()
  unreadTimer = setInterval(refreshUnread, 60000)
})
onBeforeUnmount(() => {
  stopInventorySync()
  if (unreadTimer) { clearInterval(unreadTimer); unreadTimer = undefined }
})
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
