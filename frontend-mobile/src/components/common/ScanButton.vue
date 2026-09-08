<template>
  <van-button type="primary" :size="size" :block="block" :loading="loading || opening" @click="openScanner">
    <van-icon name="scan" />
    {{ buttonText }}
  </van-button>

  <van-popup v-model:show="showScanner" position="bottom" :style="{ height: '78%' }" @closed="stopScanner">
    <van-nav-bar title="扫描二维码" left-arrow @click-left="closeScanner" />
    <div class="scanner-panel">
      <div :id="scannerId" class="scanner-view" />
      <van-field v-model="manualValue" label="二维码内容" placeholder="无法扫码时可手工输入" clearable />
      <van-button block type="primary" :disabled="!manualValue.trim()" @click="submitManualValue">确认内容</van-button>
      <p v-if="scanError" class="scan-error">{{ scanError }}</p>
    </div>
  </van-popup>
</template>

<script setup lang="ts">
import { Html5Qrcode, Html5QrcodeSupportedFormats } from 'html5-qrcode'
import { nextTick, onBeforeUnmount, ref } from 'vue'

const props = withDefaults(defineProps<{
  buttonText?: string
  loading?: boolean
  size?: 'large' | 'normal' | 'small' | 'mini'
  block?: boolean
}>(), {
  buttonText: '扫码绑定',
  loading: false,
  size: 'small',
  block: false,
})
const emit = defineEmits<{ (e: 'success', value: string): void }>()
const showScanner = ref(false)
const opening = ref(false)
const scanError = ref('')
const manualValue = ref('')
const scannerId = `qr-reader-${Math.random().toString(36).slice(2)}`

let scanner: Html5Qrcode | null = null
let cameraRunning = false
let handlingResult = false

const stopScanner = async () => {
  const activeScanner = scanner
  scanner = null
  if (!activeScanner) return
  try {
    if (cameraRunning) await activeScanner.stop()
  } catch {
    // The browser may already have released the camera.
  } finally {
    cameraRunning = false
    try {
      await activeScanner.clear()
    } catch {
      // clear() can fail after a denied camera request.
    }
  }
}

const handleScanResult = async (value: string) => {
  const normalizedValue = value.trim()
  if (!normalizedValue || handlingResult) return
  handlingResult = true
  manualValue.value = normalizedValue
  await stopScanner()
  showScanner.value = false
  emit('success', normalizedValue)
  handlingResult = false
}

const openScanner = async () => {
  if (props.loading || opening.value) return
  opening.value = true
  scanError.value = ''
  manualValue.value = ''
  handlingResult = false
  showScanner.value = true
  await nextTick()
  try {
    scanner = new Html5Qrcode(scannerId, {
      formatsToSupport: [Html5QrcodeSupportedFormats.QR_CODE],
      verbose: false,
    })
    await scanner.start(
      { facingMode: 'environment' },
      { fps: 10, qrbox: { width: 240, height: 240 } },
      (decodedText) => { void handleScanResult(decodedText) },
      () => undefined,
    )
    cameraRunning = true
  } catch {
    scanError.value = '无法打开摄像头，请允许相机权限后重试。'
    await stopScanner()
  } finally {
    opening.value = false
  }
}

const closeScanner = async () => {
  showScanner.value = false
  await stopScanner()
}

const submitManualValue = () => {
  void handleScanResult(manualValue.value)
}

onBeforeUnmount(() => { void stopScanner() })
</script>

<style scoped>
.scanner-panel {
  display: grid;
  gap: 16px;
  padding: 16px;
}
.scanner-view {
  width: 100%;
  min-height: 260px;
  overflow: hidden;
  background: #111827;
}
.scanner-view :deep(video) {
  width: 100%;
  height: auto;
}
.scan-error {
  margin: 0;
  color: var(--van-danger-color);
  font-size: 13px;
  line-height: 1.5;
}
</style>
