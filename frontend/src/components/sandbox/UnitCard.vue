<template>
  <div
    class="unit-card"
    :class="[typeClass, progressClass, { locked: unit.is_locked, empty: isEmpty }]"
    :data-unit-id="unit.unit_id"
    @dblclick="$emit('edit', unit)"
    @contextmenu.prevent="$emit('contextmenu', { event: $event, unit })"
  >
    <div v-if="unit.is_locked" class="lock-icon">&#128274;</div>
    <template v-if="!isEmpty">
      <div class="primary-info">
        <div class="model-detail">{{ displayModelDetail }}</div>
        <div v-if="showCrossLane" class="cross-lane-badge">跨列生产</div>
        <div class="contract-no">{{ unit.contract_no || '-' }}</div>
        <div class="due-date">{{ formatDate(displayDueDate) }}</div>
        <div v-if="displayDealerName" class="dealer">{{ displayDealerName }}</div>
        <template v-if="showSerialNo">
          <div class="serial-no">{{ displaySerialNo }}</div>
        </template>
        <div class="remark-line">{{ displayRemark }}</div>
      </div>
      <div class="secondary-info">
        <span>{{ unit.customer || '-' }}</span>
        <span>#{{ unit.slot_index }}</span>
      </div>
    </template>
    <template v-else>
      <div class="empty-slot">空槽 #{{ unit.slot_index }}</div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { normalizeModelType, formatDate } from '../../utils/sandboxModelType'

const props = defineProps({
  unit: { type: Object, required: true },
  disableProgressColor: { type: Boolean, default: false },
  showCrossLane: { type: Boolean, default: false }
})

defineEmits(['edit', 'contextmenu'])

// T7: format model detail — hide bare family names (G/XS/AUTO)
function formatLevel2Model(model: string) {
  const raw = String(model || '').trim()
  if (!raw) return '-'
  const upper = raw.toUpperCase()
  if (upper === 'G' || upper === 'XS' || upper === 'AUTO') return '-'
  return raw
}

// T3: isEmpty checks both contract_no AND model_type
const isEmpty = computed(() => {
  const hasContract = !!props.unit.contract_no
  const hasModel = !!String(props.unit.model_type_detail || props.unit.model_type || '').trim()
  return !hasContract && !hasModel
})

// T7: display model detail with fallback
const displayModelDetail = computed(() =>
  formatLevel2Model(props.unit.model_type_detail || props.unit.model_type)
)

// T7: due date with fallback to promised_due_date
const displayDueDate = computed(() =>
  props.unit.due_date || props.unit.promised_due_date || null
)

// T7: dealer with fallback to dealer_id
const displayDealerName = computed(() => {
  const v = props.unit.dealer_name || props.unit.dealer_id || ''
  return String(v).trim()
})

const showSerialNo = computed(() => {
  const bs = String(props.unit.batch_status || '').trim()
  const us = String(props.unit.status || '').trim()
  return bs === 'Confirmed' || bs === 'In_Production' || us === 'In_Production'
})

const displaySerialNo = computed(() => {
  const v = props.unit.serial_no || props.unit.forecast_serial_no || ''
  return String(v).trim() || '-'
})

const displayRemark = computed(() => {
  const v = props.unit.order_remark || ''
  return String(v).trim() || '-'
})

const typeClass = computed(() => {
  if (props.unit.model_family === '特殊') return 'type-SPECIAL'
  
  const mt = normalizeModelType(props.unit.model_type)
  if (mt === 'SPECIAL') return 'type-SPECIAL'
  if (mt === 'AUTO') return 'type-AUTO'
  if (mt === 'XS') return 'type-XS'
  if (mt === 'G') return 'type-G'

  const batchID = String(props.unit.batch_id || '').trim().toUpperCase()
  if (batchID.includes('-SPECIAL-')) return 'type-SPECIAL'

  if (isEmpty.value) {
    const batchModel = String(props.unit.batch_model_type || '').trim().toUpperCase()
    if (batchModel === 'SPECIAL') return 'type-SPECIAL'
    if (batchModel === 'AUTO') return 'type-AUTO'
    if (batchModel === 'XS') return 'type-XS'
    if (batchModel === 'G') return 'type-G'
  }

  return `type-${mt}`
})

const progressClass = computed(() => {
  if (props.disableProgressColor) return ''
  if (isEmpty.value) return ''
  const contractNo = String(props.unit.contract_no || '').trim()
  const status = String(props.unit.fg_status || props.unit.status || '').trim()
  const hasContract = contractNo.length > 0
  const isCompleted = hasContract
    ? (status === '待发货' || status === '已出库')
    : (status !== '待入库')
  return isCompleted ? 'state-completed' : 'state-in-progress'
})
</script>

<style scoped>
.cross-lane-badge {
  display: inline-block;
  margin: 2px 0 4px;
  padding: 1px 6px;
  border-radius: 10px;
  border: 1px solid #b7bec7;
  color: #5f6975;
  background: #f5f7fa;
  font-size: 11px;
  line-height: 1.4;
}
</style>
