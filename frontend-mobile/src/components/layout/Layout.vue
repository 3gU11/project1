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
import { computed } from 'vue'
import { useUserStore } from '@/store/user'

const userStore = useUserStore()

const tabbarItems = computed(() => {
  if (userStore.userInfo?.role === 'Prod') {
    return [
      { title: '查询', to: '/query', icon: 'search' },
      { title: '我的', to: '/profile', icon: 'user-o' },
    ]
  }

  return [
    { title: '入库', to: '/query', icon: 'scan' },
    { title: '看板', to: '/dashboard', icon: 'chart-trending-o' },
    { title: '我的', to: '/profile', icon: 'user-o' },
  ]
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
