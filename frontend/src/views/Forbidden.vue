<template>
  <div class="forbidden-page">
    <div class="card">
      <div class="code">403</div>
      <h2>无权限访问</h2>
      <p>当前账号没有访问该模块的权限，请联系管理员或通过侧边栏返回首页。</p>
      <div class="actions">
        <el-button type="primary" @click="goHome">回到首页</el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'

const router = useRouter()
const goHome = () => router.push('/')
</script>

<style scoped>
.forbidden-page {
  min-height: calc(100vh - 80px);
  display: grid;
  place-items: center;
}
.card {
  width: min(520px, 96%);
  border: 1px solid #e5e7eb;
  border-radius: 14px;
  background: #fff;
  padding: 28px;
  text-align: center;
}
.code {
  font-size: 56px;
  line-height: 1;
  color: #ef4444;
  font-weight: 800;
}
h2 {
  margin: 10px 0 8px;
}
p {
  margin: 0;
  color: #6b7280;
}
.actions {
  margin-top: 18px;
  display: flex;
  justify-content: center;
  gap: 10px;
}
</style>
