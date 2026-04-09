<template>
  <div class="page-header">
    <div class="left">
      <el-button v-if="showBack" class="back-btn" size="small" @click="$emit('back')">⬅ 返回</el-button>
      <h1 class="title">{{ title }}</h1>
    </div>
    <div class="right">
      <slot name="actions" />
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  title: string
  showBack?: boolean
}>()

defineEmits<{
  (e: 'back'): void
}>()
</script>

<style scoped>
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.left {
  display: flex;
  align-items: center;
  gap: 14px;
  min-width: 0;
}
.right {
  display: flex;
  align-items: center;
  gap: 8px;
}
.back-btn {
  padding: 4px 12px;
}
.title {
  margin: 0;
  font-size: 40px;
  color: #1f2937;
  font-weight: 800;
  line-height: 1.1;
}
</style>
