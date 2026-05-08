<template>
  <div class="batch-card" :class="`type-${batch.model_type}`">
    <div class="batch-header">
      <div>
        <span class="batch-title">[{{ batch.model_type }}] 第 {{ batch.batch_no }} 批</span>
        <span class="batch-meta"> / 共 {{ batch.capacity }} 台</span>
        <span v-if="batch.due_date_start" class="batch-meta">
          / {{ fmtDate(batch.due_date_start) }} ~ {{ fmtDate(batch.due_date_end) }}
        </span>
      </div>
      <el-tag v-if="batch.status === 'Predicted'" type="warning" size="small">待确认</el-tag>
      <el-tag v-else-if="batch.status === 'Confirmed'" type="success" size="small">已确认</el-tag>
      <el-tag v-else-if="batch.status === 'In_Production'" type="primary" size="small">生产中</el-tag>
      <el-tag v-else-if="batch.status === 'Completed'" type="info" size="small">已完工</el-tag>
    </div>
    <div class="batch-units" ref="unitsContainer">
      <slot name="units" :units="batch.units || []">
        <UnitCard v-for="u in batch.units" :key="u.unit_id" :unit="u" />
      </slot>
    </div>
    <div v-if="batch.status === 'Predicted'" style="margin-top: 8px; text-align: right;">
      <el-button type="primary" size="small" @click="$emit('confirm', batch.batch_id)">
        审核通过
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import UnitCard from './UnitCard.vue'

defineProps({
  batch: { type: Object, required: true }
})

defineEmits(['confirm'])

function fmtDate(d: string | null | undefined) {
  if (!d) return '-'
  return String(d).slice(0, 10)
}
</script>
