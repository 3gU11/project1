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
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
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

// 消息页读完一条/全部已读后立即刷新徽标，不必等 60 秒轮询。
// 移动端浏览器切后台会挂起 setInterval，所以还要在回到前台时补一次。
const onInboxUpdated = () => { void refreshUnread() }
const onVisibilityChange = () => {
  if (document.visibilityState === 'visible') void refreshUnread()
}

// 进出消息页时都刷新一次：进入时对齐服务端（可能在别的设备读过），
// 离开时兜底，即使消息页的请求被中断，徽标也能跟上。
watch(() => route.path, (path, previous) => {
  if (path === '/messages' || previous === '/messages') void refreshUnread()
})

type TabItem = { title: string; to: string; icon: string; badge?: string | number }

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
  window.addEventListener('workflow-inbox-updated', onInboxUpdated)
  document.addEventListener('visibilitychange', onVisibilityChange)
})
onBeforeUnmount(() => {
  stopInventorySync()
  if (unreadTimer) { clearInterval(unreadTimer); unreadTimer = undefined }
  window.removeEventListener('workflow-inbox-updated', onInboxUpdated)
  document.removeEventListener('visibilitychange', onVisibilityChange)
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
