<template>
  <div
    class="unit-card"
    :class="[typeClass, progressClass, { locked: unit.is_locked, empty: isEmpty, selected }]"
    :data-unit-id="unit.unit_id"
    :title="tooltipContent"
    @click="$emit('select', unit)"
    @dblclick="$emit('edit', unit)"
    @contextmenu.prevent="$emit('contextmenu', { event: $event, unit })"
  >
    <div v-if="unit.is_locked" class="lock-icon">&#128274;</div>
    <template v-if="!isEmpty">
      <div class="card-content-wrapper">
        <div class="card-main-row">
          <div class="card-left-col">
            <div class="model-detail" :title="displayModelDetail">{{ displayModelDetail }}</div>
            <div class="customer-name-highlight" :title="'客户: ' + (unit.customer || '-')">
              {{ unit.customer || '-' }}
            </div>
          </div>
          <div class="card-right-col">
            <div class="due-date" :title="'交期: ' + formatDate(displayDueDate)">
              <span class="card-icon">📅</span>
              <span class="date-text">{{ formatDate(displayDueDate) }}</span>
            </div>
            <div v-if="displayDealerName" class="dealer" :title="'经销商: ' + displayDealerName">
              <span class="card-icon">🏢</span>
              <span class="dealer-text">{{ displayDealerName }}</span>
            </div>
          </div>
        </div>

        <div v-if="showCrossLane" class="cross-lane-row">
          <div class="cross-lane-badge">跨列生产</div>
        </div>

        <div v-if="showSerialNo" class="serial-row">
          <span class="card-icon">#</span>
          <span class="serial-text" :title="'流水号: ' + displaySerialNo">{{ displaySerialNo }}</span>
        </div>

        <div v-if="displayRemark && displayRemark !== '-'" class="remark-row">
          <el-tooltip :content="displayRemark" placement="top" :show-after="300" effect="dark">
            <div class="remark-bubble">
              <span class="card-icon">💬</span>
              <span class="remark-text">{{ displayRemark }}</span>
            </div>
          </el-tooltip>
        </div>
      </div>
      <div class="secondary-info">
        <span class="contract-no-muted" :title="'合同号: ' + (stockPlaceholder ? '备货占位' : (unit.contract_no || '-'))">
          📄 {{ stockPlaceholder ? ('备货占位' + (stackCount > 1 ? ` x ${stackCount}` : '')) : (unit.contract_no || '-') }}
        </span>
        <span>#{{ unit.slot_index }}</span>
      </div>
    </template>
    <template v-else>
      <div class="empty-slot-content">
        <div class="empty-main">
          <span class="plus-icon">+</span>
          <span class="slot-name">空槽 #{{ unit.slot_index }}</span>
        </div>
        <div class="empty-hint">双击排产 / 拖动放置</div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { normalizeModelType, formatDate } from '../../utils/sandboxModelType'
import { normalizeSandboxCategory } from '../../utils/sandboxCategory'

const props = defineProps({
  unit: { type: Object, required: true },
  disableProgressColor: { type: Boolean, default: false },
  stockPlaceholder: { type: Boolean, default: false },
  showCrossLane: { type: Boolean, default: false },
  forceShowSerialNo: { type: Boolean, default: false },
  selected: { type: Boolean, default: false },
  stackCount: { type: Number, default: 1 }
})

defineEmits(['edit', 'contextmenu', 'select'])

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
  if (props.forceShowSerialNo) return true
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
  const familyCategory = normalizeSandboxCategory(String(props.unit.model_family || '').trim())
  if (familyCategory === '特殊') return 'type-SPECIAL'
  if (familyCategory.endsWith('AUTO')) return 'type-AUTO'
  if (familyCategory.endsWith('XS')) return 'type-XS'
  if (familyCategory.endsWith('G')) return 'type-G'
  if (props.unit.model_family === '鐗规畩') return 'type-SPECIAL'
  
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

const tooltipContent = computed(() => {
  if (isEmpty.value) return `空槽 #${props.unit.slot_index}`
  return [
    `机型明细: ${displayModelDetail.value}`,
    `合同号: ${props.stockPlaceholder ? '备货占位' : (props.unit.contract_no || '-')}`,
    `客户: ${props.unit.customer || '-'}`,
    `交期: ${formatDate(displayDueDate.value) || '-'}`,
    `经销商: ${displayDealerName.value || '-'}`,
    showSerialNo.value ? `流水号: ${displaySerialNo.value}` : '',
    `备注: ${displayRemark.value || '-'}`
  ].filter(Boolean).join('\n')
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

/* Card Icons */
.card-icon {
  margin-right: 4px;
  font-size: 11px;
  color: #94a3b8;
  display: inline-block;
  vertical-align: middle;
}

/* Card left color side strips & border styling */
.unit-card {
  border: 1.5px solid #e2e8f0 !important;
  border-left-width: 4.5px !important;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
}

.unit-card.type-G { 
  border-left-color: #10b981 !important; 
}
.unit-card.type-XS { 
  border-left-color: #3b82f6 !important; 
}
.unit-card.type-AUTO { 
  border-left-color: #f59e0b !important; 
}
.unit-card.type-SPECIAL { 
  border-left-color: #ec4899 !important; 
}

/* Default Small Screen Layout (纵向单列堆叠) */
.card-main-row {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.card-left-col,
.card-right-col {
  width: 100%;
}

.card-right-col {
  text-align: left;
}

.model-detail {
  font-size: 14px !important;
  font-weight: 800 !important;
  color: #1e293b !important; /* Dark Slate */
  margin-bottom: 2px;
  white-space: nowrap !important;
  overflow: visible !important;
  text-overflow: clip !important;
}

.customer-name-highlight {
  font-size: 13.5px !important;
  font-weight: 700 !important;
  color: #2563eb !important; /* Highlighted color */
  margin-bottom: 2px;
  display: -webkit-box !important;
  -webkit-line-clamp: 2 !important;
  -webkit-box-orient: vertical !important;
  overflow: hidden !important;
  text-overflow: ellipsis !important;
  white-space: normal !important;
  word-break: break-all !important;
  line-height: 1.35 !important;
}

.due-date {
  font-size: 12px !important;
  font-weight: 600 !important;
  color: #ef4444 !important; /* Urgent soft red */
  margin-bottom: 2px;
  white-space: normal !important;
  word-break: break-all !important;
}

.dealer,
.serial-row {
  font-size: 11.5px !important;
  font-weight: 500 !important;
  color: #64748b !important; /* Slate gray, visually backgrounded */
  margin-bottom: 2px;
  white-space: normal !important;
  word-break: break-all !important;
}

.remark-bubble {
  font-size: 11.5px !important;
  color: #475569 !important;
  background-color: #f1f5f9;
  border: 1px solid #e2e8f0;
  border-radius: 4px;
  padding: 2px 6px;
  margin-top: 4px;
  display: inline-block;
  max-width: 80px !important;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  box-sizing: border-box;
  cursor: pointer;
  transition: max-width 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
}

.remark-bubble:hover {
  max-width: 100% !important;
}

.secondary-info {
  margin-top: 6px !important;
  font-size: 10px !important;
  color: #94a3b8 !important; /* very light gray */
  font-weight: 500;
  display: flex !important;
  justify-content: space-between !important;
  align-items: center !important;
}

.contract-no-muted {
  color: #64748b !important;
  font-weight: 600;
  max-width: 140px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  display: inline-block;
  vertical-align: bottom;
}

/* 32寸大显示屏及高分屏响应式适配 (横向分栏，字号显著放大) */
@media (min-width: 1440px) {
  .unit-card {
    padding: 12px 14px !important;
    min-height: 110px !important;
  }

  .card-main-row {
    flex-direction: row !important;
    justify-content: space-between !important;
    gap: 8px !important;
  }
  
  .card-left-col {
    flex: 1 !important;
    min-width: 0 !important;
  }
  
  .card-right-col {
    flex: 0 0 auto !important;
    text-align: right !important;
    display: flex !important;
    flex-direction: column !important;
    align-items: flex-end !important;
    max-width: 50% !important;
  }
  
  .model-detail {
    font-size: 17px !important;
    margin-bottom: 4px !important;
  }
  
  .customer-name-highlight {
    font-size: 16px !important;
    margin-bottom: 4px !important;
  }
  
  .due-date {
    font-size: 14.5px !important;
    margin-bottom: 4px !important;
  }
  
  .dealer {
    font-size: 14px !important;
    margin-bottom: 4px !important;
    max-width: 100% !important;
  }
  
  .serial-row {
    font-size: 13.5px !important;
    margin-top: 3px !important;
  }
  
  .remark-bubble {
    font-size: 13.5px !important;
    padding: 3px 8px !important;
    margin-top: 6px !important;
    max-width: 110px !important;
  }
  
  .remark-bubble:hover {
    max-width: 100% !important;
  }
  
  .secondary-info {
    font-size: 12px !important;
    margin-top: 10px !important;
  }

  .contract-no-muted {
    max-width: 240px !important;
  }

  .card-icon {
    font-size: 14px !important;
  }
}

/* Empty slot visual design */
.unit-card.empty {
  border: 2px dashed #cbd5e1 !important;
  background: #f8fafc !important;
  cursor: pointer;
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1) !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  box-sizing: border-box;
}

.unit-card.empty:hover {
  border-color: #3b82f6 !important;
  background: #eff6ff !important;
  box-shadow: 0 4px 10px rgba(59, 130, 246, 0.08) !important;
  transform: translateY(-1px);
}

.empty-slot-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  color: #94a3b8;
  user-select: none;
}

.empty-main {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 700;
  font-size: 13.5px;
  color: #64748b;
  transition: color 0.2s;
}

@media (min-width: 1440px) {
  .empty-main {
    font-size: 15px !important;
  }
  .empty-hint {
    font-size: 12px !important;
  }
}

.unit-card.empty:hover .empty-main {
  color: #2563eb;
}

.plus-icon {
  font-size: 16px;
  font-weight: 800;
}

.empty-hint {
  font-size: 11px;
  color: #94a3b8;
  margin-top: 4px;
}

/* 3D Stacked Card Visual Effect */
.unit-card.unit-stacked-card {
  position: relative !important;
  z-index: 1;
}

.unit-card.unit-stacked-card::before,
.unit-card.unit-stacked-card::after {
  content: '' !important;
  position: absolute !important;
  left: 2px !important;
  right: 2px !important;
  height: 100% !important;
  border-radius: 6px !important;
  background: #ffffff !important;
  z-index: -2 !important;
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1) !important;
  box-sizing: border-box;
}

.unit-card.unit-stacked-card::before {
  top: 4px !important;
  transform: scale(0.97) !important;
  border: 1.5px solid #cbd5e1 !important;
  opacity: 0.8 !important;
  box-shadow: 0 1px 2px rgba(0,0,0,0.05) !important;
}

.unit-card.unit-stacked-card::after {
  top: 8px !important;
  transform: scale(0.94) !important;
  border: 1.5px solid #cbd5e1 !important;
  opacity: 0.5 !important;
  box-shadow: 0 1px 1px rgba(0,0,0,0.05) !important;
}

/* Push stacks down on hover */
.unit-card.unit-stacked-card:hover::before {
  top: 5px !important;
  transform: scale(0.98) !important;
  opacity: 0.9 !important;
}

.unit-card.unit-stacked-card:hover::after {
  top: 10px !important;
  transform: scale(0.96) !important;
  opacity: 0.7 !important;
}



</style>
