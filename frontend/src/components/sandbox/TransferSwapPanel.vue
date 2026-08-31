<template>
  <div class="transfer-panel">
    <div class="transfer-header">
      <h3>调货队列</h3>
      <el-button size="small" link type="primary" @click="openDialog">
        新增
      </el-button>
    </div>

    <div class="transfer-list">
      <div v-if="store.pairs.length === 0" class="transfer-empty">
        右键单元卡片发起调货
      </div>
      <div
        v-for="pair in store.pairs"
        :key="pair.id"
        class="transfer-pair-card"
        :class="[pair.status, { selecting: store.selectingTargetFor === pair.id }]"
      >
        <div class="pair-row">
          <div class="pair-unit urgent">
            <span class="pair-label">急</span>
            <span class="pair-contract">{{ pair.urgentUnit?.contract_no || '?' }}</span>
            <span class="pair-model">{{ pair.urgentUnit?.model_type || '' }}</span>
            <span class="pair-due">交期 {{ formatUnitDueDate(pair.urgentUnit) }}</span>
          </div>
          <span class="pair-arrow">→</span>
          <div class="pair-unit target">
            <span class="pair-label">标</span>
            <span class="pair-contract">{{ pair.targetUnit?.contract_no || '点击选择' }}</span>
            <span class="pair-model">{{ pair.targetUnit?.model_type || '' }}</span>
            <span class="pair-due">交期 {{ formatUnitDueDate(pair.targetUnit) }}</span>
          </div>
        </div>
        <div v-if="pair.status === 'done'" class="pair-status done">已完成</div>
        <div v-if="pair.status === 'failed'" class="pair-status failed">
          {{ pair.error }}
          <div v-if="pair.alternatives" class="alternatives-box">
            <!-- production line alternatives -->
            <div v-if="pair.alternatives.production_line_targets.length" class="alt-group">
              <div class="alt-group-title">产线替代目标 (可直接点击重试)</div>
              <div
                v-for="alt in pair.alternatives.production_line_targets.slice(0, 5)"
                :key="alt.unit_id"
                class="alt-item line-alt"
                @click="retryWithAlt(pair.id, alt)"
              >
                <span class="alt-line">{{ alt.line_name }}</span>
                <span class="alt-model">{{ alt.model_type }}</span>
                <span class="alt-contract">{{ alt.contract_no || '空位' }}</span>
                <span v-if="alt.buffer_days != null" class="alt-buffer">缓冲{{ alt.buffer_days }}天</span>
              </div>
            </div>
            <!-- sandbox slots -->
            <div v-if="pair.alternatives.confirmed_slots.length || pair.alternatives.predicted_slots.length" class="alt-group">
              <div class="alt-group-title">退回沙盘</div>
              <div v-if="pair.alternatives.confirmed_slots.length" class="alt-sub">已确认批次</div>
              <div
                v-for="alt in pair.alternatives.confirmed_slots.slice(0, 4)"
                :key="alt.unit_id"
                class="alt-item sandbox-alt"
                @click="returnToSandbox(pair.id, alt)"
              >
                <span class="alt-batch">{{ alt.batch_code || alt.batch_id }}</span>
                <span class="alt-model">{{ alt.model_type }}</span>
                <span>槽{{ alt.slot_index }}</span>
              </div>
              <div v-if="pair.alternatives.predicted_slots.length" class="alt-sub">预测批次</div>
              <div
                v-for="alt in pair.alternatives.predicted_slots.slice(0, 4)"
                :key="alt.unit_id"
                class="alt-item sandbox-alt"
                @click="returnToSandbox(pair.id, alt)"
              >
                <span class="alt-batch">{{ alt.batch_id?.slice(0, 30) }}</span>
                <span class="alt-model">{{ alt.model_type }}</span>
                <span>槽{{ alt.slot_index }}</span>
              </div>
            </div>
          </div>
        </div>
        <div v-if="pair.status === 'pending'" class="pair-actions">
          <el-button
            v-if="store.selectingTargetFor !== pair.id"
            size="small" type="primary" link
            @click="startSelect(pair.id)"
          >
            选择目标
          </el-button>
          <el-button
            v-else
            size="small" type="warning" link
            @click="store.cancelTargetSelection()"
          >
            取消选择
          </el-button>
          <el-button size="small" type="danger" link @click="store.removePair(pair.id)">
            移除
          </el-button>
        </div>
      </div>
    </div>

    <div v-if="store.pairs.some(p => p.status === 'done' || p.status === 'failed')" class="transfer-footer">
      <el-button size="small" link @click="store.clearCompleted()">清除已完成/失败</el-button>
    </div>

    <el-dialog v-model="dialogVisible" title="新增调货" width="500px" :close-on-click-modal="false">
      <div class="transfer-dialog-body">
        <div class="transfer-field">
          <label>急合同单元 <span class="field-hint">（右键单元卡片可快捷填入，目标通过点击选择）</span></label>
          <el-input
            v-model="urgentSearch"
            placeholder="输入合同号 / 客户 / 经销商搜索"
            @input="searchUnits"
          />
          <div v-if="candidates.length && urgentSearch" class="transfer-dropdown">
            <div
              v-for="u in candidates.slice(0, 8)"
              :key="u.unit_id"
              class="transfer-dropdown-item"
              @click="selectUrgent(u)"
            >
              <span class="t-contract">{{ u.contract_no || '(无合同)' }}</span>
              <span class="t-model">{{ u.model_type }}</span>
              <span class="t-customer">{{ u.customer || '-' }}</span>
              <span class="t-meta">{{ u.dealer_name || '' }}</span>
            </div>
            <div v-if="candidates.length === 0" class="transfer-dropdown-empty">
              无匹配单元
            </div>
          </div>
          <div v-if="newUrgent" class="transfer-selected">
            已选: <strong>{{ newUrgent.contract_no }}</strong>
            &nbsp; {{ newUrgent.model_type }} / {{ newUrgent.customer }}
          </div>
        </div>

        <div class="transfer-field">
          <label>调货原因</label>
          <el-input v-model="newReason" placeholder="可选" />
        </div>
      </div>

      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button
          type="primary"
          :disabled="!newUrgent"
          @click="addPair"
        >
          加入调货队列
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useTransferStore } from '../../stores/useSandboxTransferStore'
import { useLineStore } from '../../stores/useSandboxLineStore'
import { formatDate } from '../../utils/sandboxModelType'

const store = useTransferStore()
const lineStore = useLineStore()

const dialogVisible = ref(false)
const urgentSearch = ref('')
const newUrgent = ref<any>(null)
const newReason = ref('')

const allKanbanUnits = computed(() => {
  const units: any[] = []
  for (const line of lineStore.lines) {
    const lineName = line.line_name || line.production_line_id || ''
    for (const u of (line.units || [])) {
      units.push({ ...u, line_name: lineName })
    }
  }
  return units
})

const candidates = ref<any[]>([])

function formatUnitDueDate(unit: any) {
  const due = unit?.due_date || unit?.promised_due_date || ''
  return due ? formatDate(due) : '-'
}

function searchUnits() {
  const keyword = urgentSearch.value.trim().toLowerCase()
  if (!keyword) {
    candidates.value = []
    return
  }
  candidates.value = allKanbanUnits.value.filter(u => {
    if (!String(u.contract_no || '').trim()) return false
    const text = [u.contract_no, u.customer, u.model_type, u.dealer_name]
      .map(v => String(v || '').toLowerCase())
      .join(' ')
    return text.includes(keyword)
  })
}

function selectUrgent(u: any) {
  newUrgent.value = u
  urgentSearch.value = ''
  candidates.value = []
}

function addPair() {
  if (!newUrgent.value) return
  store.addPair(newUrgent.value, null, newReason.value)
  newUrgent.value = null
  newReason.value = ''
  dialogVisible.value = false
  ElMessage.success('已加入调货队列，请点击"选择目标"后在产线上点选目标机台')
}

function startSelect(pairId: string) {
  store.startTargetSelection(pairId)
  ElMessage.info('请在左侧产线中点击目标机台')
}

function openDialog() {
  dialogVisible.value = true
}

async function retryWithAlt(pairId: string, alt: any) {
  try {
    await store.retrySwapWithAlternative(pairId, alt)
    ElMessage.success('替代调货完成')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '替代调货失败')
  }
}

async function returnToSandbox(pairId: string, alt: any) {
  try {
    await ElMessageBox.confirm(
      `确认将急合同单元退回沙盘批次？`,
      '退回沙盘',
      { confirmButtonText: '确认', cancelButtonText: '取消', type: 'warning' }
    )
    await store.returnUrgentToSandbox(pairId, alt.batch_id)
    ElMessage.success('已退回沙盘')
  } catch {
    // cancelled or error
  }
}

defineExpose({
  setUrgentUnit(u: any) {
    newUrgent.value = u
    dialogVisible.value = true
  },
  openDialog
})
</script>

<style scoped>
.transfer-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}
.transfer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 5px;
  flex-shrink: 0;
}
.transfer-header h3 {
  font-size: 13px;
  margin: 0;
}
.transfer-dialog-body {
  max-height: 55vh;
}
.transfer-field {
  margin-bottom: 14px;
}
.transfer-field label {
  font-size: 13px;
  color: #333;
  display: block;
  margin-bottom: 4px;
}
.field-hint {
  font-size: 11px;
  color: #999;
  font-weight: normal;
}
.transfer-dropdown {
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  background: #fff;
  max-height: 200px;
  overflow-y: auto;
  margin-top: 2px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.10);
}
.transfer-dropdown-item {
  padding: 8px 12px;
  cursor: pointer;
  font-size: 13px;
  display: flex;
  gap: 10px;
  border-bottom: 1px solid #f5f5f5;
}
.transfer-dropdown-item:hover {
  background: #ecf5ff;
}
.transfer-dropdown-empty {
  padding: 12px;
  color: #ccc;
  font-size: 13px;
  text-align: center;
}
.t-contract { font-weight: 600; min-width: 100px; }
.t-model { color: #1677ff; min-width: 70px; }
.t-customer { color: #666; min-width: 60px; }
.t-meta { color: #999; font-size: 12px; }
.transfer-selected {
  font-size: 13px;
  color: #67c23a;
  padding: 6px 0;
}
.transfer-list {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
}
.transfer-empty {
  color: #ccc;
  text-align: center;
  padding: 10px 6px;
  font-size: 12px;
}
.transfer-pair-card {
  padding: 5px 7px;
  margin-bottom: 5px;
  border-radius: 6px;
  border-left: 3px solid #e6a23c;
  background: #fef9f0;
  font-size: 11px;
}
.transfer-pair-card.selecting {
  border-left-color: #e6a23c;
  background: #fff7e6;
  box-shadow: 0 0 0 2px #e6a23c;
}
.transfer-pair-card.executing {
  border-left-color: #1677ff;
  background: #ecf5ff;
}
.transfer-pair-card.done {
  border-left-color: #67c23a;
  background: #f0f9eb;
  opacity: 0.7;
}
.transfer-pair-card.failed {
  border-left-color: #f56c6c;
  background: #fef0f0;
}
.pair-row {
  display: flex;
  align-items: center;
  gap: 4px;
}
.pair-unit {
  display: flex;
  align-items: center;
  gap: 3px;
  flex-wrap: wrap;
  min-width: 0;
  flex: 1;
  line-height: 1.2;
}
.pair-label {
  display: inline-flex;
  width: 16px;
  height: 16px;
  border-radius: 4px;
  font-size: 9px;
  font-weight: 700;
  color: #fff;
  align-items: center;
  justify-content: center;
}
.pair-unit.urgent .pair-label { background: #e6a23c; }
.pair-unit.target .pair-label { background: #1677ff; }
.pair-contract {
  max-width: 96px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 600;
}
.pair-model { color: #888; font-size: 10px; }
.pair-due {
  flex-basis: 100%;
  margin-left: 19px;
  color: #e65100;
  font-size: 10px;
  font-weight: 600;
}
.pair-arrow { color: #999; font-weight: 700; }
.pair-status {
  margin-top: 2px;
  font-size: 10px;
}
.pair-status.done { color: #67c23a; }
.pair-status.failed { color: #f56c6c; }
.pair-actions {
  margin-top: 2px;
  display: flex;
  gap: 5px;
  justify-content: flex-end;
}
.pair-actions :deep(.el-button) {
  height: 20px;
  padding: 0;
  font-size: 11px;
}
.transfer-footer {
  flex-shrink: 0;
  text-align: center;
  padding-top: 4px;
  border-top: 1px solid #ebeef5;
}
.alternatives-box {
  margin-top: 4px;
  border: 1px solid #e8e8e8;
  border-radius: 6px;
  background: #fff;
  padding: 5px;
  max-height: 180px;
  overflow-y: auto;
}
.alt-group {
  margin-bottom: 6px;
}
.alt-group-title {
  font-size: 11px;
  font-weight: 600;
  color: #e6a23c;
  margin-bottom: 4px;
}
.alt-sub {
  font-size: 10px;
  color: #999;
  margin: 4px 0 2px;
}
.alt-item {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 5px 8px;
  font-size: 11px;
  border-radius: 4px;
  cursor: pointer;
  margin-bottom: 2px;
}
.alt-item.line-alt {
  background: #f6ffed;
  border-left: 2px solid #67c23a;
}
.alt-item.line-alt:hover {
  background: #e6ffe0;
}
.alt-item.sandbox-alt {
  background: #f5f5f7;
  border-left: 2px solid #1677ff;
}
.alt-item.sandbox-alt:hover {
  background: #e5f1ff;
}
.alt-line { font-weight: 600; min-width: 50px; color: #555; }
.alt-model { color: #1677ff; min-width: 70px; }
.alt-contract { font-weight: 600; }
.alt-batch { font-weight: 600; color: #333; min-width: 60px; }
.alt-buffer { color: #67c23a; font-size: 10px; }
</style>
