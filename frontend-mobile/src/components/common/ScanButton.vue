<template>
  <van-button type="primary" block :loading="scanning" @click="mockScan">
    <van-icon name="scan" />
    {{ scanning ? '扫描中...' : '点击扫码/模拟扫码' }}
  </van-button>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const emit = defineEmits<{ (e: 'success', value: string): void }>()
const scanning = ref(false)

const mockScan = () => {
  if (scanning.value) {
    return
  }
  scanning.value = true
  setTimeout(() => {
    scanning.value = false
    emit('success', `SN${Date.now()}`)
  }, 800)
}
</script>
