<template>
  <div class="page">
    <div class="card">
      <van-cell title="姓名" :value="userStore.userInfo?.name || '-'" />
      <van-cell title="账号" :value="userStore.userInfo?.username || '-'" />
      <van-cell title="角色" :value="userStore.userInfo?.role || '-'" />
    </div>
    <div class="card">
      <van-button block type="warning" @click="clearCache">清理缓存</van-button>
      <van-button block type="danger" style="margin-top: 8px" @click="logout">退出登录</van-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { showToast } from 'vant'
import { useUserStore } from '@/store/user'

const userStore = useUserStore()
const router = useRouter()

const clearCache = () => {
  localStorage.removeItem('offlineQueue')
  showToast('缓存已清理')
}

const logout = () => {
  userStore.logout()
  router.replace('/login')
}
</script>
