<template>
  <div class="card">
    <van-uploader :after-read="afterRead" :max-count="1" accept=".xls,.xlsx" />
    <van-cell title="已选文件" :value="fileName || '未选择'" />
    <van-button block type="primary" :loading="submitting" :disabled="!file" @click="upload">
      上传并导入
    </van-button>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { showToast } from 'vant'
import { inboundApi } from '@/api/inbound'

const emit = defineEmits<{ (e: 'success'): void }>()
const file = ref<File | null>(null)
const fileName = ref('')
const submitting = ref(false)

const afterRead = (items: any) => {
  const item = Array.isArray(items) ? items[0] : items
  if (!item?.file) {
    return
  }
  file.value = item.file as File
  fileName.value = String(item.file.name || '')
}

const upload = async () => {
  if (!file.value) {
    return
  }
  submitting.value = true
  try {
    await inboundApi.uploadBatch(file.value)
    showToast('上传成功')
    emit('success')
  } finally {
    submitting.value = false
  }
}
</script>
