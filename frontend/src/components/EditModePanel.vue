<template>
  <div class="mode-panel" :class="{ active }">
    <div class="mode-left">
      <div class="mode-icon">{{ active ? '✏️' : '👁️' }}</div>
      <div class="mode-text">
        <div class="mode-title">{{ title }}</div>
        <div class="mode-subtitle">{{ subtitle }}</div>
      </div>
    </div>
    <div class="mode-right">
      <span class="mode-badge" :class="{ active }">{{ active ? '编辑中' : '只读中' }}</span>
      <el-button
        class="mode-btn"
        :type="active ? 'warning' : 'primary'"
        :disabled="disabled"
        @click="$emit('toggle')"
      >
        {{ active ? '退出编辑' : '进入编辑' }}
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  active: boolean
  title: string
  subtitle: string
  disabled?: boolean
}>()

defineEmits<{
  (e: 'toggle'): void
}>()
</script>

<style scoped>
.mode-panel {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  margin-bottom: 10px;
  padding: 10px 12px;
  border: 1px solid #dbeafe;
  border-radius: 10px;
  background: linear-gradient(180deg, #f8fbff 0%, #eef5ff 100%);
  transition: all 0.2s ease;
}
.mode-panel.active {
  border-color: #fde68a;
  background: linear-gradient(180deg, #fffdf4 0%, #fff7db 100%);
}
.mode-left {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}
.mode-icon {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  background: #e0ecff;
  font-size: 16px;
}
.mode-panel.active .mode-icon {
  background: #fef3c7;
}
.mode-title {
  font-size: 14px;
  font-weight: 700;
  color: #1f2937;
}
.mode-subtitle {
  font-size: 12px;
  color: #64748b;
}
.mode-right {
  display: flex;
  align-items: center;
  gap: 8px;
}
.mode-badge {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 999px;
  color: #1d4ed8;
  background: #dbeafe;
}
.mode-badge.active {
  color: #92400e;
  background: #fde68a;
}
.mode-btn {
  min-width: 94px;
}
</style>
