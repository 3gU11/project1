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

const tabbarItems = computed(() => {
  if (userStore.userInfo?.role === 'LineOperator') {
    return [
      { title: '生产', to: '/production', icon: 'cluster-o' },
      { title: '我的', to: '/profile', icon: 'user-o' },
    ]
  }

  return [
    { title: '扫码任务', to: '/query', icon: 'scan' },
    { title: '我的', to: '/profile', icon: 'user-o' },
  ]
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
