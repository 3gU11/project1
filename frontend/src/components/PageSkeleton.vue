<template>
  <div class="page-skeleton" :style="{ minHeight }">
    <div class="s-line title" />
    <div class="s-line subtitle" />
    <div class="s-grid">
      <div v-for="i in blocks" :key="i" class="s-card" />
    </div>
  </div>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    blocks?: number
    minHeight?: string
  }>(),
  {
    blocks: 6,
    minHeight: '260px',
  }
)
</script>

<style scoped>
.page-skeleton {
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  padding: 12px;
  background: #fff;
}
.s-line {
  height: 14px;
  border-radius: 999px;
  background: linear-gradient(90deg, #e5e7eb 25%, #f3f4f6 37%, #e5e7eb 63%);
  background-size: 400% 100%;
  animation: pulse 1.6s ease infinite;
}
.s-line.title {
  width: 38%;
  height: 20px;
  margin-bottom: 8px;
}
.s-line.subtitle {
  width: 62%;
  margin-bottom: 12px;
}
.s-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}
.s-card {
  height: 96px;
  border-radius: 8px;
  background: linear-gradient(90deg, #e5e7eb 25%, #f3f4f6 37%, #e5e7eb 63%);
  background-size: 400% 100%;
  animation: pulse 1.6s ease infinite;
}
@keyframes pulse {
  0% {
    background-position: 100% 50%;
  }
  100% {
    background-position: 0 50%;
  }
}
</style>
