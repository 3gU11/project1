<template>
  <el-dialog
    v-model="visible"
    title="选择原订单落点容器"
    width="500px"
    @open="load"
  >
    <p style="margin-bottom:12px;color:#666;font-size:13px;">
      目标机台已有订单，请选择一个空容器作为原订单的新落点：
    </p>
    <div v-if="loading" style="text-align:center;padding:20px;">
      <el-icon class="is-loading"><Loading /></el-icon> 加载中...
    </div>
    <el-empty v-else-if="containers.length === 0" description="暂无可用的空容器" />
    <div v-else style="max-height:300px;overflow-y:auto;">
      <div
        v-for="c in containers" :key="c.unit_id"
        :class="['unit-card', 'empty', `type-${c.model_type}`, { selected: selectedUnitId === c.unit_id }]"
        style="cursor:pointer;margin:4px;"
        @click="selectedUnitId = c.unit_id"
      >
        <div class="empty-slot">
          空槽 #{{ c.slot_index }} ({{ c.batch_id?.slice(0, 18) }}...)
        </div>
      </div>
    </div>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" @click="confirm" :disabled="!selectedUnitId">
        确认落点
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { Loading } from '@element-plus/icons-vue'
import { useRushStore } from '../../stores/useSandboxRushStore'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  modelType: { type: String, default: '' }
})
const emit = defineEmits(['update:modelValue', 'confirm'])

const rushStore = useRushStore()
const visible = ref(false)
const loading = ref(false)
const selectedUnitId = ref<string | null>(null)

watch(() => props.modelValue, (v) => { visible.value = v })
watch(visible, (v) => { emit('update:modelValue', v) })

async function load() {
  selectedUnitId.value = null
  loading.value = true
  await rushStore.fetchEmptyContainers(props.modelType)
  loading.value = false
}

const containers = ref<any[]>([])
watch(() => rushStore.emptyContainers, (v) => { containers.value = v }, { immediate: true })

function confirm() {
  if (!selectedUnitId.value) return
  emit('confirm', selectedUnitId.value)
  visible.value = false
}
</script>
