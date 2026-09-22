<template>
  <div class="app-container">
    <div v-if="isDemo" class="demo-notice" role="status">功能演示环境 · 除机型字典外均为虚构测试数据</div>
    <router-view />
  </div>
</template>

<script setup lang="ts">
const isDemo = import.meta.env.VITE_DEMO_MODE === 'true'
</script>

<style>
.demo-notice {
  position: sticky;
  top: 0;
  z-index: 4000;
  padding: 7px 16px;
  background: #fff3cd;
  color: #664d03;
  text-align: center;
  font-size: 14px;
}
.app-container {
  min-height: 100vh;
  font-family: Arial, sans-serif;
}
</style>
