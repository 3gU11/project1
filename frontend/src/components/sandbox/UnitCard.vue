<template>
  <div
    class="unit-card"
    :class="[typeClass, { locked: unit.is_locked, empty: isEmpty }]"
    :data-unit-id="unit.unit_id"
    @dblclick="$emit('edit', unit)"
    @contextmenu.prevent="$emit('contextmenu', { event: $event, unit })"
  >
    <div v-if="unit.is_locked" class="lock-icon">&#128274;</div>
    <template v-if="!isEmpty">
      <div class="primary-info">
        <div class="model-detail">{{ displayModelDetail }}</div>
        <div class="contract-no">{{ unit.contract_no || '-' }}</div>
        <div class="due-date">{{ formatDate(displayDueDate) }}</div>
        <div v-if="displayDealerName" class="dealer">{{ displayDealerName }}</div>
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
  unit: { type: Object, required: true }
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

const typeClass = computed(() => {
  const batchModel = String(props.unit.batch_model_type || '').trim().toUpperCase()
  const batchID = String(props.unit.batch_id || '').trim().toUpperCase()
  if (batchModel === 'SPECIAL' || batchID.includes('-SPECIAL-')) return 'type-SPECIAL'
  const mt = normalizeModelType(props.unit.model_type)
  return `type-${mt}`
})
</script>
