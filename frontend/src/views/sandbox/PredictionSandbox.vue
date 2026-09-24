<template>
  <div class="sandbox-layout">
    <div class="sandbox-summary" aria-label="预测方案摘要">
      <div><span>预测</span><strong>{{ predictedBatchCount }}</strong></div>
      <div><span>已确认</span><strong>{{ confirmedBatchCount }}</strong></div>
      <div><span>订单</span><strong>{{ contractUnitCount }}</strong></div>
      <div><span>备货</span><strong>{{ stockUnitCount }}</strong></div>
    </div>
    <details class="sandbox-settings">
      <summary>机型比例</summary>
      <div class="sandbox-header"><CapacityRatioEditor :editable="canEditSandbox" /></div>
    </details>
    <div class="sandbox-filters">
      <el-radio-group
        v-model="selectedSeriesFilters"
        @change="onSeriesFilterChange"
        class="series-tabs"
      >
        <el-radio-button value="">全部</el-radio-button>
        <el-radio-button
          v-for="series in seriesFilterOptions"
          :key="series"
          :value="series"
        >{{ series }}</el-radio-button>
      </el-radio-group>
      <el-button text @click="handleManualRefresh" :loading="batchStore.loading">刷新</el-button>
      <span v-if="hasDataUpdate" class="sandbox-data-update" role="status">
        数据有更新
      </span>
      <el-button v-if="canEditSandbox" type="primary" @click="handleRecompute()" :loading="recomputing">
        {{ recomputeButtonText }}
      </el-button>
      <el-button v-if="canEditSandbox" type="success" @click="openManualPredictedDrawer">
        新增预测产线
      </el-button>
      <span v-if="pendingRecomputeJobId" class="recompute-job-status">
        正在重算
        <span v-if="recomputeElapsedSeconds >= 2">已运行 {{ recomputeElapsedSeconds }} 秒</span>
        <el-button text type="primary" size="small" @click="resumePendingRecompute">查看结果</el-button>
      </span>
      <el-tooltip :disabled="!selectedBatchBlockingReason" :content="selectedBatchBlockingReason" placement="bottom">
        <span>
          <el-button
            v-if="selectedBatches.length > 0 && canEditSandbox"
            type="warning"
            :disabled="Boolean(selectedBatchBlockingReason)"
            @click="batchConfirm"
          >
            确认预测批次
          </el-button>
        </span>
      </el-tooltip>
      <el-button
        v-if="canRevoke && canEditSandbox"
        type="danger"
        @click="batchRevoke"
      >
        撤销确认
      </el-button>
    </div>

    <div ref="topScrollRef" class="top-scroll" @scroll="onTopScroll">
      <div :style="{ width: topScrollWidth + 'px' }"></div>
    </div>

    <div
      ref="batchesContainerRef"
      class="sandbox-batches"
      v-loading="batchStore.loading"
      @scroll="onBodyScroll"
      @mousemove="onEdgeHover"
      @mouseleave="stopEdgeAutoScroll"
    >
      <div
        v-if="filteredBatches.length === 0 && !batchStore.loading"
        style="padding:40px;text-align:center;width:100%;color:#999;"
      >
        暂无预测批次
      </div>
      <div
        v-for="batch in filteredBatches"
        :key="batch.batch_id"
        class="batch-card"
        :class="[`type-${batch.model_type}`, { 'batch-confirmed': batch.status === 'Confirmed', 'batch-target-slot': isTargetOptimizedBatch(batch), 'batch-recompute-target': isSelectedRecomputeTarget(batch), 'batch-placeholder-slot': isNonTargetPredictedBatch(batch), 'is-valid-drop-target': dragging && isValidDragTargetBatch(batch), 'is-invalid-drop-target': dragging && !isValidDragTargetBatch(batch) }]"
        :style="{ position: 'relative', width: '390px', minWidth: '390px', maxWidth: '390px', borderLeft: selectedBatches.includes(getBatchUniqueId(batch)) ? '4px solid #409eff' : '' }"
      >
        <div v-if="targetBadgeText(batch)" class="batch-target-badge">
          {{ targetBadgeText(batch) }}
        </div>
        <div class="batch-status-top-right">
          <el-tag v-if="isBatchManuallyAdjusted(batch)" type="info" size="small" class="manual-adjusted-tag">已人工调整</el-tag>
          <el-tag v-if="batch.status === 'Predicted'" type="warning" size="small" class="corner-tag">待确认</el-tag>
          <el-tag v-else-if="batch.status === 'Confirmed'" type="success" size="small" class="corner-tag">已确认</el-tag>
          <el-tag v-else size="small" class="corner-tag">{{ batch.status }}</el-tag>
        </div>
        <div class="batch-header" @click="toggleSelect(getBatchUniqueId(batch))" style="cursor: pointer;">
          <div class="batch-header-main">
            <div class="batch-headline">
              <el-checkbox
                :model-value="selectedBatches.includes(getBatchUniqueId(batch))"
                @change="toggleSelect(getBatchUniqueId(batch))"
                class="batch-select"
                @click.stop
              />
              <span class="batch-title">[{{ displayBatchCategory(batch) }}]{{ batch.status === 'Predicted' ? '' : ' ' + displayBatchCode(batch) }}</span>
              
              <span class="batch-meta batch-counts">
                <span class="batch-count batch-count-ordered">已订 {{ orderedCount(batch) }}</span>
                <template v-if="displayBatchCategory(batch) !== '特殊'">
                  <span class="batch-count-separator">/</span>
                  <span class="batch-count batch-count-stock">备货 {{ stockCount(batch) }}</span>
                </template>
              </span>
            </div>

            <!-- Capacity Progress Bar -->
            <div 
              class="batch-capacity-bar" 
              :title="`容量: ${capacityLabel(batch)} (已订: ${orderedCount(batch)}, 备货: ${stockCount(batch)}, 空槽: ${emptySlotLabel(batch)})`"
            >
              <div class="bar-segment segment-ordered" :style="{ width: capacityPercent(batch, orderedCount(batch)) + '%' }"></div>
              <div class="bar-segment segment-stock" :style="{ width: capacityPercent(batch, stockCount(batch)) + '%' }"></div>
              <div class="bar-segment segment-empty" :style="{ width: capacityPercent(batch, emptySlots(batch)) + '%' }"></div>
            </div>

            <div class="batch-meta batch-meta-due">
              {{ batchDueRangeText(batch) }}
            </div>
            <div class="batch-plan-summary" :class="{ 'has-risk': batchRiskSummary(batch).length }" @click.stop="openBatchDetail(batch)">
              <span class="plan-summary-item">容量 {{ orderedCount(batch) + stockCount(batch) }}/{{ capacityLabel(batch) }}</span>
              <span class="plan-summary-item">空槽 {{ emptySlotLabel(batch) }}</span>
              <button v-if="batchRiskSummary(batch).length" type="button" class="plan-summary-risk" @click.stop="openBatchDetail(batch)">
                风险 {{ batchRiskSummary(batch).length }}
              </button>
            </div>
            <!-- 批次号和预计入库时间的输入放到列顶 -->
            <div v-if="batch.status === 'Predicted'" class="batch-top-inputs" @click.stop>
              <div class="input-row">
                <el-input
                  v-model="batchCodeInputs[batch.batch_id]"
                  placeholder="批次号"
                  style="width: 170px"
                />
                <el-date-picker
                  v-model="inboundDateInputs[batch.batch_id]"
                  type="date"
                  value-format="YYYY-MM-DD"
                  placeholder="预计入库日期"
                  style="width: 190px"
                  clearable
                />
              </div>
            </div>
            <button v-if="isTargetOptimizedBatch(batch)" type="button" class="stock-recommendation" @click.stop="openBatchDetail(batch)">
              建议补货 {{ recommendationStockCount(batch) }} 台
            </button>
            <div class="batch-meta batch-meta-models">
              <template v-if="batchModelSummaryRows(batch).length">
                <div
                  v-for="row in batchModelSummaryRows(batch)"
                  :key="row.model"
                  class="batch-model-row"
                >
                  <span class="batch-model-name">{{ row.model }}</span>
                  <span v-if="row.ordered > 0" class="model-count-ordered">已订{{ row.ordered }}</span>
                  <span v-if="row.stock > 0" class="model-count-stock">备货{{ row.stock }}</span>
                </div>
              </template>
              <template v-else>机型数量: -</template>
            </div>
          </div>
        </div>
        <div v-if="canEditBatchStock(batch) && stockEditRows(batch).length" class="stock-editor" @click.stop>
          <div
            v-for="row in stockEditRows(batch)"
            :key="row.model"
            class="stock-editor-row"
          >
            <span class="stock-editor-model">{{ row.model }}</span>
            <el-input-number
              v-model="stockEdits[batch.batch_id][row.model]"
              size="small"
              :min="0"
              :step="1"
              :precision="0"
              controls-position="right"
              class="stock-editor-input"
            />
          </div>
          <div v-if="stockEditError(batch)" class="stock-editor-error">
            {{ stockEditError(batch) }}
          </div>
          <div class="stock-editor-actions">
            <el-button size="small" text @click.stop="resetBatchStockEdit(batch)">重置</el-button>
            <el-button
              size="small"
              type="primary"
              :loading="Boolean(stockSaving[batch.batch_id])"
              :disabled="Boolean(stockEditError(batch)) || !isBatchStockDirty(batch)"
              @click.stop="saveBatchStockEdit(batch)"
            >
              保存
            </el-button>
          </div>
        </div>
        <VueDraggable
          :model-value="batch.units || []"
          :group="{ name: batch.model_type, pull: true, put: true }"
          item-key="unit_id"
          :animation="180"
          :disabled="!canEditSandbox"
          draggable=".unit-card"
          filter=".locked"
          ghost-class="unit-ghost"
          chosen-class="unit-chosen"
          class="batch-units"
          @start="(evt: any) => onDragStart(evt, batch)"
          @add="(evt: any) => onUnitMoved(evt, batch)"
          @update="(evt: any) => onUnitMoved(evt, batch)"
          @end="onDragEnd"
        >
          <template v-for="u in batch.units" :key="u.unit_id">
            <UnitCard
              :class="{ 
                'hidden-card': !getStockPlaceholderStackInfo(u, batch).show,
                'unit-risk-highlight': activeRiskUnitIds.has(String(u.unit_id)),
                'unit-stock-placeholder': isNonTargetStockPlaceholder(u, batch),
                'unit-stacked-card': getStockPlaceholderStackInfo(u, batch).isStacked,
                'is-active-dropzone': dragging && isValidDragTargetBatch(batch) && (isUnitEmptySlot(u) || isStockUnit(u))
              }"
              :unit="{ ...u, batch_model_type: batch.model_type, model_family: u.model_family || modelFamilyMap[String(u.model_type || '').toUpperCase()] || '' }"
              :stock-placeholder="isNonTargetStockPlaceholder(u, batch)"
              :show-cross-lane="isCrossLanePlacement(u, batch)"
              :disable-progress-color="true"
              :stack-count="getStockPlaceholderStackInfo(u, batch).count"
              @edit="openEditDrawer"
              @contextmenu="onContextMenu"
            />
          </template>
        </VueDraggable>
        <button
          v-if="canAddSpecialCard(batch)"
          class="special-card-add"
          type="button"
          @click.stop="openSpecialAddDrawer(batch)"
        >
          <el-icon><Plus /></el-icon>
          <span>添加卡片</span>
        </button>
      </div>
    </div>

    <el-drawer v-model="editVisible" title="信息强改" size="400px">
      <el-form v-if="editingUnit" label-width="80px" size="small">
        <el-form-item label="合同号">
          <el-input v-model="editForm.contract_no" disabled />
        </el-form-item>
        <el-form-item label="客户">
          <el-input v-model="editForm.customer" />
        </el-form-item>
        <el-form-item label="经销商">
          <el-input v-model="editForm.dealer_name" />
        </el-form-item>
        <el-form-item label="机型">
          <el-select
            v-model="editForm.model_type"
            filterable
            default-first-option
            style="width:100%"
          >
            <el-option v-for="m in editModelTypes" :key="m" :label="m" :value="m" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="editForm.order_remark" type="textarea" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="saveEdit" :loading="saving">保存并锁定</el-button>
        </el-form-item>
      </el-form>
    </el-drawer>

    <el-drawer v-model="specialAddVisible" title="新增特殊卡片" size="420px">
      <el-form label-width="80px" size="small">
        <el-form-item label="合同号">
          <el-input v-model="specialAddForm.contract_no" />
        </el-form-item>
        <el-form-item label="客户">
          <el-input v-model="specialAddForm.customer" />
        </el-form-item>
        <el-form-item label="经销商">
          <el-input v-model="specialAddForm.dealer_name" />
        </el-form-item>
        <el-form-item label="机型" required>
          <el-select v-model="specialAddForm.model_type" filterable allow-create default-first-option style="width:100%">
            <el-option v-for="m in specialModelTypes" :key="m" :label="m" :value="m" />
          </el-select>
        </el-form-item>
        <el-form-item label="交期">
          <el-date-picker
            v-model="specialAddForm.due_date"
            type="date"
            value-format="YYYY-MM-DD"
            style="width:100%"
          />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="specialAddForm.order_remark" type="textarea" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="submitSpecialCard" :loading="specialAddSaving">提交</el-button>
        </el-form-item>
      </el-form>
    </el-drawer>

    <el-drawer v-model="manualPredictedVisible" title="新增预测产线" size="420px">
      <el-form label-width="90px" size="small">
        <el-form-item label="机型族" required>
          <el-select v-model="manualPredictedForm.model_family" placeholder="请选择明确机型族" style="width:100%">
            <el-option v-for="item in manualFamilyOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="数量" required>
          <el-input-number v-model="manualPredictedForm.quantity" :min="1" :max="manualFamilyCapacity" controls-position="right" style="width:100%" />
        </el-form-item>
        <el-form-item label="备注"><el-input v-model="manualPredictedForm.remark" type="textarea" /></el-form-item>
        <el-form-item><el-button type="primary" @click="submitManualPredictedBatch" :loading="manualPredictedSaving">保存</el-button></el-form-item>
      </el-form>
    </el-drawer>

    <el-drawer v-model="batchDetailVisible" :title="batchDetail?.batch_id ? `预测列 · ${batchDetail.batch_id}` : '预测列'" size="440px">
      <template v-if="batchDetail">
        <div class="batch-detail-overview">
          <div class="batch-detail-stat">
            <span>容量</span>
            <strong>{{ batchDetail.ordered_count + batchDetail.stock_count }}/{{ capacityLabel(batchDetail) }}</strong>
          </div>
          <div class="batch-detail-stat">
            <span>空槽</span>
            <strong>{{ emptySlotLabel(batchDetail) }}</strong>
          </div>
          <div class="batch-detail-stat batch-detail-inbound">
            <span>预计入库</span>
            <strong>{{ batchDetail.expected_inbound_date || '待填写' }}</strong>
            <small>{{ batchDetail.expected_inbound_source || '人工填写' }}</small>
          </div>
        </div>
        <div v-if="batchDetail.syncStatus?.status === 'failed'" class="batch-detail-sync-status">
          <strong>同步失败，可重试</strong>
          <span v-if="batchDetail.syncStatus.last_error" class="sync-error">{{ batchDetail.syncStatus.last_error }}</span>
          <el-button v-if="batchDetail.syncStatus.status === 'failed' && batchDetail.status === 'Confirmed'" size="small" type="primary" @click="retryBatchSync">重试同步</el-button>
        </div>
        <div v-if="batchDetail.recommendation" class="batch-detail-recommendation">
          <strong>建议补货 {{ batchDetail.recommendation.suggested_stock_count ?? '未知' }} 台</strong>
          <span>{{ batchDetail.recommendation.name || '未知' }} · 当前 {{ formatPercent(batchDetail.recommendation.current_pct) }} / 目标 {{ formatPercent(batchDetail.recommendation.target_pct) }}</span>
        </div>
        <el-alert v-if="batchDetail.risks?.length" title="待处理问题" type="error" :closable="false" show-icon />
        <div v-for="risk in batchDetail.risks || []" :key="risk.code" class="batch-detail-risk">
          <strong>{{ risk.message }}</strong>
          <small v-if="risk.unit_ids?.length">影响 {{ risk.unit_ids.length }} 张卡片</small>
        </div>
        <details v-if="batchDetail.recomputeJob" class="batch-detail-history">
          <summary>重算记录</summary>
          <div class="batch-detail-history-content">
            <span>{{ batchDetail.recomputeJob.completed_at || batchDetail.recomputeJob.created_at || '时间未知' }}</span>
            <span>{{ batchDetail.recomputeJob.parameters?.is_clicked ? '按选中列' : '全量' }}重算 · {{ recomputeResultSummary(batchDetail.recomputeJob.result) }}</span>
          </div>
        </details>
        <details v-if="batchDetail.audit?.baseline || batchDetail.audit?.changes?.length" class="batch-detail-history">
          <summary>变更记录</summary>
          <div class="batch-detail-history-content">
            <span v-if="batchDetail.audit?.baseline">首次调整前 {{ batchDetail.audit.baseline.units?.length || 0 }} 张卡片</span>
            <span v-if="batchDetail.audit?.difference_summary">新增 {{ batchDetail.audit.difference_summary.added_count }} · 删除 {{ batchDetail.audit.difference_summary.removed_count }} · 变更 {{ batchDetail.audit.difference_summary.changed_count }}</span>
            <span v-for="change in batchDetail.audit?.changes || []" :key="change.id">{{ change.operated_at }} · {{ change.operated_by || '未知' }} · {{ change.action_type }}</span>
          </div>
        </details>
        <el-button v-if="batchDetail.status === 'Confirmed'" type="primary" plain @click="openProductionKanban(batchDetail.batch_id)">进入生产看板派工</el-button>
      </template>
    </el-drawer>

    <el-dialog
      v-model="confirmationVisible"
      title="确认预测批次"
      width="560px"
      :close-on-click-modal="false"
      @closed="resetConfirmationPreview"
    >
      <template v-if="confirmationPreview">
        <div class="confirmation-summary">
          <span>批次号：{{ confirmationPreview.batch_code }}</span>
          <span>预计入库：{{ confirmationPreview.expected_inbound_date || '待填写' }}</span>
          <span>待排产：{{ confirmationPreview.sync_count }} 条</span>
        </div>
        <el-alert v-if="confirmationPreview.risks?.length" title="存在阻塞问题，处理后才能确认" type="error" :closable="false" show-icon />
        <div v-for="risk in confirmationPreview.risks || []" :key="risk.code" class="confirmation-risk">
          <strong>{{ risk.message }}</strong>
          <span v-if="risk.unit_ids?.length">涉及 {{ risk.unit_ids.length }} 张卡片</span>
        </div>
      </template>
      <template #footer>
        <el-button @click="confirmationVisible = false">取消</el-button>
        <el-button type="warning" :loading="confirming" :disabled="!canSubmitConfirmation" @click="submitBatchConfirmation">
          确认并同步
        </el-button>
      </template>
    </el-dialog>

    <div
      v-if="contextMenu.visible"
      :style="{ position: 'fixed', left: contextMenu.x + 'px', top: contextMenu.y + 'px', zIndex: 9999 }"
      style="background:#fff;border-radius:6px;box-shadow:0 4px 12px rgba(0,0,0,0.15);padding:4px 0;min-width:120px;"
    >
      <div v-if="contextMenu.unit?.is_locked" class="ctx-item" @click="handleUnlock">解锁</div>
      <div v-if="canConvertToRush(contextMenu.unit)" class="ctx-item" @click="handleConvertToRush">转为急单</div>
      <div v-if="canMoveToSpecial(contextMenu.unit)" class="ctx-item" @click="handleMoveToSpecial">转移到特殊批次</div>
      <div class="ctx-item" @click="handleMarkSpot">标记现货</div>
      <div class="ctx-item" @click="handleInsertEmptySlot">在此前插入空位</div>
      <div class="ctx-item" @click="contextMenu.visible = false">取消</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, onActivated, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { VueDraggable } from 'vue-draggable-plus'
import { ElMessage, ElMessageBox, ElDatePicker } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { useBatchStore } from '../../stores/useSandboxBatchStore'
import { useUserStore } from '../../store/user'
import * as sandboxApi from '../../services/sandboxApi'
import { getApiErrorMessage } from '../../utils/request'
import UnitCard from '../../components/sandbox/UnitCard.vue'
import CapacityRatioEditor from '../../components/sandbox/CapacityRatioEditor.vue'
import { connect as wsConnect, disconnect as wsDisconnect, onEvent } from '../../services/sandboxWs'
import { categoryOfModel, normalizeMajorFamily } from '../../utils/sandboxCategory'

const batchStore = useBatchStore()
const userStore = useUserStore()
const router = useRouter()
const canEditSandbox = computed(() => userStore.hasPermission('SANDBOX_EDIT'))
const recomputing = ref(false)
const optimizedTargetSlotNo = ref(1)
const manualAdjustedBatchIds = ref<Set<string>>(new Set())
const latestAchievementCategories = ref<any[]>([])
const pendingRecomputeJobId = ref(sessionStorage.getItem('sandbox_recompute_job_id') || '')
const recomputeStartedAt = ref(Number(sessionStorage.getItem('sandbox_recompute_started_at') || 0))
const recomputeElapsedSeconds = ref(0)
let recomputeElapsedTimer: number | null = null

const selectedBatches = ref<string[]>([])
const batchCodeInputs = ref<Record<string, string>>({})
const inboundDateInputs = ref<Record<string, string>>({})
const lastBatchCodeFromDB = ref('')



function initBatchInputs() {
  for (const batch of batchStore.batches) {
    if (String(batch.status || '') === 'Predicted') {
      const id = batch.batch_id
      if (batchCodeInputs.value[id] === undefined) {
        batchCodeInputs.value[id] = ''
      }
      if (inboundDateInputs.value[id] === undefined) {
        // Keep the algorithm-derived date visible and editable at the column top.
        inboundDateInputs.value[id] = String(batch.expected_inbound_date || '').slice(0, 10)
      }
    }
  }
}

async function fetchLastBatchCode() {
  try {
    const res: any = await sandboxApi.getLastBatchCode()
    lastBatchCodeFromDB.value = res?.last_batch_code || ''
  } catch {
    lastBatchCodeFromDB.value = ''
  }
}

const selectedRecomputeTarget = computed(() => {
  if (selectedBatches.value.length !== 1) return null
  const selectedBatchId = selectedBatches.value[0]
  const batch = batchStore.batches.find((b: any) => String(b.batch_id) === selectedBatchId)
  if (!batch || String(batch.status || '') !== 'Predicted' || isSpecialBatch(batch)) return null
  return batch
})
const recomputeButtonText = computed(() => {
  return selectedRecomputeTarget.value ? '按选中列重算' : '全量重算'
})
const selectedBatchBlockingReason = computed(() => {
  if (selectedBatches.value.length !== 1) return '确认前请仅勾选 1 个待确认批次'
  const batch = batchStore.batches.find((item: any) => String(item?.batch_id) === selectedBatches.value[0])
  if (!batch) return '所选预测批次不存在或已刷新'
  if (String(batch.status || '') !== 'Predicted') return '仅待确认预测批次可以确认'
  const blocking = batchRiskSummary(batch).filter((risk) => risk.blocking)
  return blocking.length ? `请先处理阻塞风险：${blocking.map((risk) => risk.message).join('；')}` : ''
})
const editVisible = ref(false)
const editingUnit = ref<any>(null)
const saving = ref(false)
const specialAddVisible = ref(false)
const specialAddSaving = ref(false)
const specialAddBatch = ref<any>(null)
const manualPredictedVisible = ref(false)
const manualPredictedSaving = ref(false)
const batchDetailVisible = ref(false)
const batchDetail = ref<any>(null)
const activeRiskUnitIds = ref<Set<string>>(new Set())
const confirmationVisible = ref(false)
const confirmationPreview = ref<any>(null)
const confirming = ref(false)
const contextMenu = ref<{ visible: boolean; x: number; y: number; unit: any }>({ visible: false, x: 0, y: 0, unit: null })
const dragging = ref(false)
const moving = ref(false)
const pendingRefresh = ref(false)
const suspendAutoSort = ref(false)
const pinnedBatchOrder = ref<string[]>([])
const dragSource = ref<{ unit: any; sourceBatchId: string } | null>(null)
const dragFamily = ref<string>('')
const dragLane = ref<string>('')
const modelTypes = ref<string[]>([])
const modelFamilyMap = ref<Record<string, string>>({})
const modelSortOrderMap = ref<Record<string, number>>({})
const selectedSeriesFilters = ref<string>('')
const hasDataUpdate = ref(false)
const lastBatchDataFingerprint = ref('')
const stockEdits = ref<Record<string, Record<string, number>>>({})
const stockSaving = ref<Record<string, boolean>>({})

const canSubmitConfirmation = computed(() =>
  Boolean(confirmationPreview.value) &&
  !confirmationPreview.value?.risks?.some((risk: any) => risk?.blocking),
)

function compareModelDictionaryOrder(a: string, b: string): number {
  const orderA = modelSortOrderMap.value[String(a || '').trim().toUpperCase()]
  const orderB = modelSortOrderMap.value[String(b || '').trim().toUpperCase()]
  const normalizedA = Number.isFinite(orderA) ? orderA : Number.MAX_SAFE_INTEGER
  const normalizedB = Number.isFinite(orderB) ? orderB : Number.MAX_SAFE_INTEGER
  return normalizedA - normalizedB || String(a).localeCompare(String(b), 'zh-CN')
}

const topScrollRef = ref<HTMLElement | null>(null)
const batchesContainerRef = ref<HTMLElement | null>(null)
const syncingScroll = ref(false)
const edgeAutoScrollTimer = ref<number | null>(null)
const topScrollWidth = ref(1200)

const editForm = ref({ contract_no: '', customer: '', dealer_name: '', model_type: '', order_remark: '' })
const specialAddForm = ref({ contract_no: '', customer: '', dealer_name: '', model_type: '', due_date: '', order_remark: '' })
const manualPredictedForm = ref({ model_family: '中大型XS', quantity: 10, remark: '' })
const manualFamilyOptions = [
  { label: '中小型G', value: '中小型G', capacity: 30 },
  { label: '中小型XS', value: '中小型XS', capacity: 30 },
  { label: '中大型XS', value: '中大型XS', capacity: 16 },
  { label: '中小型AUTO', value: '中小型AUTO', capacity: 27 },
  { label: '中大型AUTO', value: '中大型AUTO', capacity: 16 },
  { label: '特殊', value: '特殊', capacity: 15 },
]
const manualFamilyCapacity = computed(() => manualFamilyOptions.find((item) => item.value === manualPredictedForm.value.model_family)?.capacity || 30)
// 已确认批次属于待排产队列，由生产看板管理，不再出现在预测沙盘。
const SANDBOX_STATUS = 'Predicted'
const SANDBOX_STATUS_SET = new Set(SANDBOX_STATUS.split(','))
const predictedBatchCount = computed(() => filteredBatches.value.filter((b: any) => b.status === 'Predicted').length)
const confirmedBatchCount = computed(() => filteredBatches.value.filter((b: any) => b.status === 'Confirmed').length)
const contractUnitCount = computed(() => filteredBatches.value.reduce((sum: number, b: any) => sum + (Array.isArray(b.units) ? b.units.filter((u: any) => String(u?.contract_no || '').trim()).length : 0), 0))
const stockUnitCount = computed(() => filteredBatches.value.reduce((sum: number, b: any) => sum + (Array.isArray(b.units) ? b.units.filter((u: any) => !String(u?.contract_no || '').trim()).length : 0), 0))

const filteredBatches = computed(() => {
  let batches = [...batchStore.filteredBatches].filter((b: any) => SANDBOX_STATUS_SET.has(String(b?.status || '')))
  if (selectedSeriesFilters.value) {
    batches = batches.filter((b: any) => displayBatchCategory(b) === selectedSeriesFilters.value)
  }
  const pinnedIndex = new Map<string, number>()
  if (suspendAutoSort.value && pinnedBatchOrder.value.length > 0) {
    pinnedBatchOrder.value.forEach((id, idx) => pinnedIndex.set(String(id), idx))
  }
  if (!suspendAutoSort.value) {
    // 预测列排序：
    // 1) 按交期范围起始日期升序
    // 2) 有合同的批次排在无合同批次前
    // 3) 再按 slot_no / batch_no 稳定兜底
    batches.sort((a: any, b: any) => {
      const da = batchDueStartTime(a)
      const db = batchDueStartTime(b)
      if (da !== db) return da - db
      const ha = hasAnyContract(a) ? 1 : 0
      const hb = hasAnyContract(b) ? 1 : 0
      if (ha !== hb) return hb - ha
      const sa = batchSlotOrder(a)
      const sb = batchSlotOrder(b)
      if (sa !== sb) return sa - sb
      return (Number(a.batch_no) || 0) - (Number(b.batch_no) || 0)
    })
  } else if (pinnedIndex.size > 0) {
    batches.sort((a: any, b: any) => {
      const ia = pinnedIndex.get(String(a?.batch_id || ''))
      const ib = pinnedIndex.get(String(b?.batch_id || ''))
      if (ia !== undefined && ib !== undefined) return ia - ib
      if (ia !== undefined) return -1
      if (ib !== undefined) return 1
      return (Number(a?.batch_no) || 0) - (Number(b?.batch_no) || 0)
    })
  }
  return batches
})

function batchSlotOrder(batch: any): number {
  // Use forecast_slot_no for ordering, but ensure uniqueness by combining with status
  const slotNo = Number(batch?.forecast_slot_no)
  if (Number.isFinite(slotNo) && slotNo > 0) return slotNo
  return Number(batch?.batch_no || 0)
}

// Get unique identifier for batch selection (use batch_id instead of slot number)
function getBatchUniqueId(batch: any): string {
  return String(batch?.batch_id || '')
}

// 根据大类库存缺口自动推断本次备货建议列
// categories 来自 recompute 响应的 achievement.categories
// 找出 gap_pct 最小（最缺）的大类对应的第一个预测列
function findSuggestedSlotByGap(categories?: any[]): number {
  const productionCats = ['中小型G', '中小型XS', '中大型XS', '中小型AUTO', '中大型AUTO']
  const catToFamily: Record<string, string> = {
    '中小型G': 'G',
    '中小型XS': 'XS',
    '中大型XS': 'XS',
    '中小型AUTO': 'AUTO',
    '中大型AUTO': 'AUTO',
  }
  if (!categories || categories.length === 0) return 1
  // 仅考虑有目标占比的大类
  const valid = categories.filter(
    (c: any) => productionCats.includes(c.name) && (c.target_pct ?? 0) > 0
  )
  if (valid.length === 0) return 1
  // 找 gap_pct 最小（最缺货）的大类，gap_pct = current_pct - target_pct
  valid.sort((a: any, b: any) => (a.gap_pct ?? 0) - (b.gap_pct ?? 0))
  const mostNeeded = valid[0]
  const targetFamily = catToFamily[mostNeeded.name] ?? 'XS'
  // 在当前 batches 中找到该 family 下排在最前的预测列
  const candidates = batchStore.batches.filter(
    (b: any) => String(b.status || '') === 'Predicted' &&
      !isSpecialBatch(b) &&
      String(b.model_type || '').toUpperCase() === targetFamily.toUpperCase()
  )
  if (candidates.length === 0) return 1
  candidates.sort((a: any, b: any) => batchSlotOrder(a) - batchSlotOrder(b))
  return batchSlotOrder(candidates[0])
}

function isTargetOptimizedBatch(batch: any) {
  return String(batch?.status || '') === 'Predicted' &&
    !isSpecialBatch(batch) &&
    batchSlotOrder(batch) === optimizedTargetSlotNo.value
}

function isSelectedRecomputeTarget(batch: any) {
  return Boolean(batch?.batch_id && selectedRecomputeTarget.value?.batch_id === batch.batch_id)
}

function targetBadgeText(batch: any) {
  if (isSelectedRecomputeTarget(batch)) return '重算目标'
  if (isTargetOptimizedBatch(batch)) return '本次备货建议'
  return ''
}

function isNonTargetPredictedBatch(batch: any) {
  return String(batch?.status || '') === 'Predicted' &&
    !isSpecialBatch(batch) &&
    !isTargetOptimizedBatch(batch)
}

function batchDueStartTime(batch: any): number {
  const units = Array.isArray(batch?.units) ? batch.units : []
  const times = units
    .map((u: any) => String(u?.due_date || '').slice(0, 10))
    .filter((d: string) => /^\d{4}-\d{2}-\d{2}$/.test(d))
    .map((d: string) => new Date(`${d}T00:00:00`).getTime())
    .filter((t: number) => Number.isFinite(t))
  if (!times.length) return Number.MAX_SAFE_INTEGER
  return Math.min(...times)
}

function hasAnyContract(batch: any): boolean {
  const units = Array.isArray(batch?.units) ? batch.units : []
  return units.some((u: any) => String(u?.contract_no || '').trim() !== '')
}

async function runRecompute(targetSlotNo: number, isClicked: boolean): Promise<any> {
  const accepted: any = await sandboxApi.recompute(targetSlotNo, isClicked)
  if (!accepted?.job_id) return accepted
  pendingRecomputeJobId.value = String(accepted.job_id)
  recomputeStartedAt.value = Date.now()
  sessionStorage.setItem('sandbox_recompute_job_id', pendingRecomputeJobId.value)
  sessionStorage.setItem('sandbox_recompute_started_at', String(recomputeStartedAt.value))
  startRecomputeElapsedTimer()
  const started = Date.now()
  while (Date.now() - started < 30000) {
    const job: any = await sandboxApi.getRecomputeJob(pendingRecomputeJobId.value)
    if (job.status === 'succeeded') return job.result || {}
    if (job.status === 'failed') throw new Error(job.error_message || '重算失败')
    await new Promise(resolve => setTimeout(resolve, 800))
  }
  throw new Error(`重算仍在进行，任务 ${pendingRecomputeJobId.value} 已保存，可离开页面后稍后查询`)
}

function clearPendingRecomputeJob() {
  pendingRecomputeJobId.value = ''
  recomputeStartedAt.value = 0
  recomputeElapsedSeconds.value = 0
  sessionStorage.removeItem('sandbox_recompute_job_id')
  sessionStorage.removeItem('sandbox_recompute_started_at')
  stopRecomputeElapsedTimer()
}

function updateRecomputeElapsed() {
  if (!pendingRecomputeJobId.value || !recomputeStartedAt.value) {
    recomputeElapsedSeconds.value = 0
    return
  }
  recomputeElapsedSeconds.value = Math.max(0, Math.floor((Date.now() - recomputeStartedAt.value) / 1000))
}

function startRecomputeElapsedTimer() {
  stopRecomputeElapsedTimer()
  updateRecomputeElapsed()
  recomputeElapsedTimer = window.setInterval(updateRecomputeElapsed, 1000)
}

function stopRecomputeElapsedTimer() {
  if (recomputeElapsedTimer !== null) {
    window.clearInterval(recomputeElapsedTimer)
    recomputeElapsedTimer = null
  }
}

async function resumePendingRecompute() {
  const jobID = pendingRecomputeJobId.value
  if (!jobID) return
  try {
    const job: any = await sandboxApi.getRecomputeJob(jobID)
    if (job.status === 'succeeded') {
      latestAchievementCategories.value = job?.result?.achievement?.categories || []
      clearPendingRecomputeJob()
      await refresh()
      ElMessage.success('重算任务已完成，预测列已刷新')
      return
    }
    if (job.status === 'failed') {
      clearPendingRecomputeJob()
      ElMessage.error(job.error_message || '重算任务失败')
      return
    }
    ElMessage.info(`任务仍在${job.status === 'queued' ? '排队' : '执行'}，可继续处理其他工作`)
  } catch (e: any) {
    ElMessage.error(getApiErrorMessage(e) || '读取重算任务失败')
  }
}

type BatchRisk = { code: string; message: string; blocking: boolean; severity?: string; unit_ids?: string[] }

async function openBatchDetail(batch: any, clickedRisk?: BatchRisk) {
  const inboundDate = String(inboundDateInputs.value[batch?.batch_id] || batch?.expected_inbound_date || '').slice(0, 10)
  try {
    const preview: any = await sandboxApi.previewBatchImpact(String(batch?.batch_id || ''), inboundDate)
    const visibleRisks = actionableRisks(preview?.risks)
    const id = String(batch?.batch_id || '')
    const audit: any = await sandboxApi.getBatchAudit(id).catch(() => null)
    const syncStatus: any = await sandboxApi.getBatchSyncStatus(id).catch(() => null)
    const recomputeJobResponse: any = await sandboxApi.getLatestRecomputeJob().catch(() => null)
    batchDetail.value = { ...preview, risks: visibleRisks, audit, syncStatus, recomputeJob: recomputeJobResponse?.job || null, recommendation: recommendationForBatch(batch) }
    activeRiskUnitIds.value = new Set(
      (clickedRisk ? visibleRisks.filter((risk: any) => risk.code === clickedRisk.code) : visibleRisks)
        .flatMap((risk: any) => risk.unit_ids || [])
        .map((id: any) => String(id))
    )
  } catch (e: any) {
    // The local summary still provides a useful fallback when the read-only preview is unavailable.
    batchDetail.value = {
      batch_id: batch?.batch_id,
      status: batch?.status,
      ordered_count: orderedCount(batch),
      stock_count: stockCount(batch),
      empty_count: emptySlots(batch),
      earliest_due_date: batchDueRangeText(batch),
      expected_inbound_date: inboundDate,
      expected_inbound_source: inboundDate ? '本次人工填写' : '待人工填写',
      risks: batchRiskSummary(batch).map((risk) => ({ ...risk, unit_ids: [] })),
      last_recompute_at: '',
      recomputeJob: null,
      recommendation: recommendationForBatch(batch),
      syncStatus: await sandboxApi.getBatchSyncStatus(String(batch?.batch_id || '')).catch(() => null),
    }
    activeRiskUnitIds.value = new Set()
  }
  batchDetailVisible.value = true
}

async function retryBatchSync() {
  const detail = batchDetail.value
  if (!detail?.batch_id) return
  const batchCode = String(batchCodeInputs.value[detail.batch_id] || detail.batch_code || '').trim()
  try {
    await sandboxApi.syncBatchToPlan(String(detail.batch_id), batchCode)
    detail.syncStatus = await sandboxApi.getBatchSyncStatus(String(detail.batch_id))
    ElMessage.success('同步已完成')
    await refresh()
  } catch (e: any) {
    detail.syncStatus = await sandboxApi.getBatchSyncStatus(String(detail.batch_id)).catch(() => ({ status: 'failed', last_error: getApiErrorMessage(e) }))
    ElMessage.error(getApiErrorMessage(e) || '同步失败，请稍后重试')
  }
}

function recommendationForBatch(batch: any) {
  if (!isTargetOptimizedBatch(batch)) return null
  const category = displayBatchCategory(batch)
  const item = latestAchievementCategories.value.find((entry: any) => String(entry?.name || '') === category)
  if (!item) return null
  // Older recompute records do not persist the count; keep the detail drawer
  // consistent with the visible column recommendation in that case.
  return {
    ...item,
    suggested_stock_count: item.suggested_stock_count ?? Math.max(
      0,
      Math.round(Number(item.gap_pct || 0) * -Number(batch?.capacity || 0) / 100),
    ),
  }
}

function recommendationStockCount(batch: any): string | number {
  const item = recommendationForBatch(batch)
  return item?.suggested_stock_count ?? '未知'
}

function openProductionKanban(batchId: string) {
  batchDetailVisible.value = false
  router.push({ path: '/production-kanban', query: { batch_id: batchId } })
}

function formatPercent(value: unknown): string {
  const number = Number(value)
  return Number.isFinite(number) ? `${number.toFixed(1)}%` : '未知'
}

function recomputeResultSummary(result: any): string {
  if (!result || typeof result !== 'object') return '结果摘要未知'
  const candidates = [result.message, result.summary, result.affected_batches, result.updated_batches, result.batch_count]
  const value = candidates.find((item) => item !== undefined && item !== null && String(item).trim() !== '')
  if (value === undefined) return '已完成，未返回数量摘要'
  return typeof value === 'number' ? `影响 ${value} 个批次` : String(value)
}

function resetConfirmationPreview() {
  confirmationPreview.value = null
  confirming.value = false
}

async function submitBatchConfirmation() {
  const preview = confirmationPreview.value
  if (!preview?.batch_id || !canSubmitConfirmation.value || confirming.value) return
  confirming.value = true
  try {
    await batchStore.confirmBatch(preview.batch_id, preview.batch_code, preview.expected_inbound_date)
    try {
      const syncResult = await sandboxApi.syncBatchToPlan(preview.batch_id, preview.batch_code)
      ElMessage.success(`预测批次已确认，已同步 ${syncResult.count} 条至生产看板待排产队列`)
    } catch (syncErr: any) {
      const detail = getApiErrorMessage(syncErr) || syncErr?.message || '未知错误'
      ElMessage.error(`预测批次已确认，但同步生产看板失败：${detail}。可在列详情中重试同步。`)
    }
    confirmationVisible.value = false
    selectedBatches.value = []
    await refresh()
  } catch (e: any) {
    ElMessage.error(getApiErrorMessage(e) || e?.message || '确认预测批次失败')
  } finally {
    confirming.value = false
  }
}

function batchRiskSummary(batch: any): BatchRisk[] {
  const risks = new Map<string, BatchRisk>()
  const serverRisks = Array.isArray(batch?.risks) ? batch.risks : []
  // Column risks are calculated by the sandbox service. Retaining them avoids
  // drift when new constraints, such as locked-card conflicts, are added.
  for (const risk of serverRisks) {
    if (!risk?.code || risk.code === 'due_risk' || risk.code === 'stock_placeholder') continue
    risks.set(String(risk.code), {
      code: String(risk.code),
      message: String(risk.message || '风险原因未知'),
      blocking: Boolean(risk.blocking),
      severity: String(risk.severity || ''),
      unit_ids: Array.isArray(risk.unit_ids) ? risk.unit_ids.map(String) : [],
    })
  }
  const units = Array.isArray(batch?.units) ? batch.units : []
  const capacity = batchCapacity(batch)
  const activeUnits = units.filter((u: any) => !isSpecialPlaceholder(u))
  // Older Go deployments may not return risks yet. Keep a narrow local
  // fallback for those responses, but prefer the authoritative payload above.
  if (!serverRisks.length) {
    if (capacity !== null && activeUnits.length > capacity) {
      risks.set('capacity_overflow', { code: 'capacity_overflow', message: `超容量 ${activeUnits.length - capacity} 台`, blocking: true })
    }
  }
  return Array.from(risks.values())
}

function actionableRisks(risks: any): BatchRisk[] {
  if (!Array.isArray(risks)) return []
  return risks
    .filter((risk: any) => risk?.code && risk.code !== 'due_risk' && risk.code !== 'stock_placeholder')
    .map((risk: any) => ({
      code: String(risk.code),
      message: String(risk.message || '风险原因未知'),
      blocking: Boolean(risk.blocking),
      severity: String(risk.severity || ''),
      unit_ids: Array.isArray(risk.unit_ids) ? risk.unit_ids.map(String) : [],
    }))
}

function isBatchManuallyAdjusted(batch: any): boolean {
  return Boolean(batch?.is_manually_adjusted || manualAdjustedBatchIds.value.has(String(batch?.batch_id || '')))
}

const isEditingSpecialBatch = computed(() => {
  if (!editingUnit.value) return false
  const batch = batchStore.batches.find((b: any) => b.batch_id === editingUnit.value?.batch_id)
  if (!batch) return false
  return String(batch?.model_type || '').trim().toUpperCase() === 'SPECIAL' || displayBatchCategory(batch) === '特殊'
})

function isFamilyToken(modelType: string) {
  const upper = String(modelType || '').trim().toUpperCase()
  return upper === 'G' || upper === 'XS' || upper === 'AUTO' || upper === 'SPECIAL'
}

// 信息强改允许选择任意启用的具体机型；族类占位符仍由后端拒绝。
const editModelTypes = computed(() => {
  const merged = new Set<string>([...modelTypes.value, ...batchStore.modelTypes])
  return [...merged]
    .map((m) => String(m || '').trim())
    .filter(Boolean)
    .filter((m) => !isFamilyToken(m))
    .sort(compareModelDictionaryOrder)
})

const specialModelTypes = computed(() => {
  const merged = new Set<string>([...modelTypes.value, ...batchStore.modelTypes])
  return [...merged]
    .filter(Boolean)
    .filter((m: string) => {
      const family = modelFamilyMap.value[String(m).toUpperCase()] || ''
      return normalizeMajorFamily(family) === 'SPECIAL' || family.includes('特殊') || family.includes('鐗规畩')
    })
    .sort(compareModelDictionaryOrder)
})

const seriesFilterOptions = ['中小型G', '中小型XS', '中大型XS', '中小型AUTO', '中大型AUTO', '特殊']

function displayBatchCategory(batch: any) {
  const batchModel = String(batch?.model_type || '').trim()
  const batchUpper = batchModel.toUpperCase()
  if (batchUpper.includes('SPECIAL')) return '特殊'

  const batchFamily = majorFamilyOfModel(batchModel)
  const capacity = Number(batch?.capacity || 0)
  if (batchFamily === 'G') return '中小型G'
  if (batchFamily === 'XS') return capacity === 16 ? '中大型XS' : '中小型XS'
  if (batchFamily === 'AUTO') return capacity === 16 ? '中大型AUTO' : '中小型AUTO'

  const units = Array.isArray(batch?.units) ? batch.units : []
  const count: Record<string, number> = {}
  for (const u of units) {
    const mt = String(u?.model_type || '').trim()
    const c = categoryOfModel(mt, modelFamilyMap.value[mt.toUpperCase()] || '')
    if (!c) continue
    count[c] = Number(count[c] || 0) + 1
  }
  const priority: Record<string, number> = {
    特殊: 6, 中大型AUTO: 5, 中小型AUTO: 4, 中大型XS: 3, 中小型XS: 2, 中小型G: 1
  }
  let best = ''
  let bestN = -1
  for (const k of Object.keys(count)) {
    const cur = Number(count[k] || 0)
    const bestP = Number(priority[best] || 0)
    const curP = Number(priority[k] || 0)
    if (cur > bestN || (cur === bestN && curP > bestP)) {
      best = k
      bestN = cur
    }
  }
  if (best) {
    return best
  }
  const direct = categoryOfModel(batchModel, '')
  if (direct) return direct
  const family = majorFamilyOfModel(batchModel)
  if (family === 'G') return '中小型G'
  if (family === 'XS') return '中小型XS'
  if (family === 'AUTO') return '中小型AUTO'
  if (family === 'SPECIAL') return '特殊'
  return String(batch?.model_type || '-')
}

function majorFamilyOfModel(modelType: string) {
  const model = String(modelType || '').trim()
  if (!model) return ''
  const byDict = modelFamilyMap.value[model.toUpperCase()]
  return normalizeMajorFamily(byDict || model)
}

function isStockUnit(unit: any) {
  return Boolean(unit?.is_stock || unit?.stock || !unit?.contract_no)
}

function isNonTargetStockPlaceholder(unit: any, batch: any) {
  return isStockUnit(unit) && !isSpecialPlaceholder(unit) && isNonTargetPredictedBatch(batch)
}

function isUnitEmptySlot(unit: any) {
  const hasContract = !!unit.contract_no
  const hasModel = !!String(unit.model_type_detail || unit.model_type || '').trim()
  return !hasContract && !hasModel
}

function getStockPlaceholderStackInfo(unit: any, batch: any) {
  if (!batch || !Array.isArray(batch.units)) {
    return { isStacked: false, count: 1, show: true };
  }

  const isStock = isStockUnit(unit) && !isSpecialPlaceholder(unit);
  if (!isStock) {
    return { isStacked: false, count: 1, show: true };
  }

  const units = batch.units;
  const idx = units.findIndex((u: any) => u.unit_id === unit.unit_id);
  if (idx === -1) {
    return { isStacked: false, count: 1, show: true };
  }

  const currentModel = String(unit.model_type || '').trim().toUpperCase();

  const firstIdx = units.findIndex((u: any) => {
    return isStockUnit(u) && !isSpecialPlaceholder(u) && String(u.model_type || '').trim().toUpperCase() === currentModel;
  });
  if (idx > firstIdx) {
    return { isStacked: true, count: 0, show: false };
  }

  let count = 0;
  for (let i = 0; i < units.length; i++) {
    const u = units[i];
    if (isStockUnit(u) && !isSpecialPlaceholder(u) && String(u.model_type || '').trim().toUpperCase() === currentModel) {
      count++;
    }
  }

  return {
    isStacked: count > 1,
    count: count,
    show: true
  };
}

function isValidDragTargetBatch(targetBatch: any) {
  if (!dragging.value || !dragSource.value) return false
  const unit = dragSource.value.unit
  const sourceBatchId = dragSource.value.sourceBatchId

  // 1. Stock units cannot drag across batches
  if (isStockUnit(unit) && sourceBatchId && sourceBatchId !== targetBatch.batch_id) {
    return false
  }

  // 2. Family matching check
  if (isUnitFamilyMismatch(unit, targetBatch)) {
    const canContractFirstOccupy = sourceBatchId && sourceBatchId !== targetBatch.batch_id && hasUnboundPlaceholder(targetBatch)
    if (!canContractFirstOccupy) {
      return false
    }
  }

  // 3. Lane matching check
  const sourceBatch = batchStore.batches.find((b: any) => b.batch_id === sourceBatchId)
  if (sourceBatch && laneKeyOfBatch(sourceBatch) !== laneKeyOfBatch(targetBatch) && !canMoveAcrossLanes(sourceBatch, targetBatch, unit)) {
    return false
  }

  return true
}

function sortBatchUnitsInPlace() {
  for (const batch of batchStore.batches) {
    if (Array.isArray(batch.units)) {
      batch.units.sort((a: any, b: any) => Number(a.slot_index ?? 0) - Number(b.slot_index ?? 0))
    }
  }
}

function batchDueRangeText(batch: any) {
  const inbound = String(batch?.expected_inbound_date || '').slice(0, 10)
  if (inbound) return `预计入库: ${inbound}`

  const dates = (batch.units || [])
    .map((u: any) => String(u?.due_date || '').slice(0, 10))
    .filter((d: string) => d && d !== 'null' && d !== 'undefined')
    .sort()
  if (!dates.length) return '-'
  return dates[0] === dates[dates.length - 1] ? dates[0] : `${dates[0]} ~ ${dates[dates.length - 1]}`
}

function batchModelSummaryRows(batch: any) {
  const units = Array.isArray(batch?.units) ? batch.units : []
  const counter = new Map<string, { model: string; ordered: number; stock: number }>()
  for (const u of units) {
    if (isSpecialPlaceholder(u)) continue
    const model = String(u?.model_type || '').trim()
    if (!model) continue
    const current = counter.get(model) || { model, ordered: 0, stock: 0 }
    if (isStockUnit(u)) {
      current.stock += 1
    } else {
      current.ordered += 1
    }
    counter.set(model, current)
  }
  return [...counter.values()]
    .filter((row) => row.ordered > 0 || row.stock > 0)
    .sort((a, b) => compareModelDictionaryOrder(a.model, b.model))
}

function orderedCount(batch: any) {
  if (displayBatchCategory(batch) === '特殊') return specialContractCount(batch)
  return (batch.units || []).filter((u: any) => !isStockUnit(u)).length
}

function stockCount(batch: any) {
  if (displayBatchCategory(batch) === '特殊') return 0
  return (batch.units || []).filter((u: any) => isStockUnit(u)).length
}

function canEditBatchStock(batch: any) {
  return canEditSandbox.value && isTargetOptimizedBatch(batch) && displayBatchCategory(batch) !== seriesFilterOptions[5]
}

function batchCapacity(batch: any): number | null {
  const value = Number(batch?.capacity)
  return Number.isFinite(value) && value > 0 ? value : null
}

function capacityLabel(batch: any): string {
  return batchCapacity(batch) === null ? '未知' : String(batchCapacity(batch))
}

function emptySlots(batch: any): number | null {
  const capacity = batchCapacity(batch)
  return capacity === null ? null : Math.max(0, capacity - orderedCount(batch) - stockCount(batch))
}

function emptySlotLabel(batch: any): string {
  const value = emptySlots(batch)
  return value === null ? '未知' : String(value)
}

function capacityPercent(batch: any, count: number | null): number {
  const capacity = batchCapacity(batch)
  return capacity && count !== null ? Math.min(100, Math.max(0, count / capacity * 100)) : 0
}

function currentStockCounts(batch: any) {
  const counts: Record<string, number> = {}
  const units = Array.isArray(batch?.units) ? batch.units : []
  for (const u of units) {
    if (!isStockUnit(u) || isSpecialPlaceholder(u)) continue
    const model = String(u?.model_type || '').trim()
    if (!model) continue
    counts[model] = Number(counts[model] || 0) + 1
  }
  return counts
}

function orderedModelNames(batch: any) {
  const models = new Set<string>()
  const units = Array.isArray(batch?.units) ? batch.units : []
  for (const u of units) {
    if (isStockUnit(u) || isSpecialPlaceholder(u)) continue
    const model = String(u?.model_type || '').trim()
    if (model) models.add(model)
  }
  return [...models]
}

function resetBatchStockEdit(batch: any) {
  const batchId = String(batch?.batch_id || '')
  if (!batchId) return
  const counts = { ...currentStockCounts(batch) }
  for (const model of orderedModelNames(batch)) {
    if (counts[model] === undefined) counts[model] = 0
  }
  stockEdits.value[batchId] = counts
}

function resetAllStockEdits() {
  const next: Record<string, Record<string, number>> = {}
  for (const batch of batchStore.batches) {
    const batchId = String(batch?.batch_id || '')
    if (!batchId) continue
    next[batchId] = { ...currentStockCounts(batch) }
  }
  stockEdits.value = next
}

function ensureBatchStockEdit(batch: any) {
  const batchId = String(batch?.batch_id || '')
  if (!batchId) return {}
  if (!stockEdits.value[batchId]) {
    resetBatchStockEdit(batch)
  }
  const category = displayBatchCategory(batch)
  if (category !== '特殊') {
    for (const model of modelTypes.value) {
      if (categoryOfModel(model, modelFamilyMap.value[model.toUpperCase()]) === category
        && stockEdits.value[batchId][model] === undefined) {
        stockEdits.value[batchId][model] = 0
      }
    }
  }
  return stockEdits.value[batchId] || {}
}

function stockEditRows(batch: any) {
  const edit = ensureBatchStockEdit(batch)
  const current = currentStockCounts(batch)
  const models = new Set<string>([...orderedModelNames(batch), ...Object.keys(current), ...Object.keys(edit)])
  return [...models]
    .filter(Boolean)
    .sort(compareModelDictionaryOrder)
    .map((model) => ({ model }))
}

function stockEditTotal(batch: any) {
  const edit = ensureBatchStockEdit(batch)
  return Object.values(edit).reduce((sum, n) => sum + Math.max(0, Number(n) || 0), 0)
}

function stockEditError(batch: any) {
  const ordered = orderedCount(batch)
  const stock = stockEditTotal(batch)
  const capacity = Number(batch?.capacity || 0)
  if (ordered + stock > capacity) {
    return `已订 ${ordered} + 备货 ${stock} 超过本批次容量 ${capacity}`
  }
  return ''
}

function isBatchStockDirty(batch: any) {
  const edit = ensureBatchStockEdit(batch)
  const current = currentStockCounts(batch)
  const models = new Set<string>([...Object.keys(current), ...Object.keys(edit)])
  for (const model of models) {
    if ((Number(edit[model]) || 0) !== (Number(current[model]) || 0)) return true
  }
  return false
}

async function saveBatchStockEdit(batch: any) {
  const batchId = String(batch?.batch_id || '')
  if (!batchId || stockEditError(batch)) return
  const edit = ensureBatchStockEdit(batch)
  const stocks = Object.keys(edit)
    .sort(compareModelDictionaryOrder)
    .map((model) => ({ model_type: model, count: Math.max(0, Math.trunc(Number(edit[model]) || 0)) }))
  stockSaving.value[batchId] = true
  try {
    await sandboxApi.updateBatchStockModels(batchId, stocks)
    ElMessage.success('备货数量已保存')
    await refresh()
  } catch (e: any) {
    resetBatchStockEdit(batch)
    ElMessage.error(getApiErrorMessage(e) || e.message || '备货数量保存失败')
  } finally {
    stockSaving.value[batchId] = false
  }
}

function isSpecialBatch(batch: any) {
  return String(batch?.model_type || '').trim().toUpperCase() === 'SPECIAL'
}

function isLargeMachineBatch(batch: any) {
  const category = displayBatchCategory(batch)
  return category === '中大型XS' || category === '中大型AUTO'
}

function laneKeyOfBatch(batch: any) {
  if (!batch) return ''
  if (isSpecialBatch(batch)) return 'SPECIAL'
  const family = majorFamilyOfModel(batch?.model_type || '')
  if (!family) return ''
  if (family === 'G') return 'G-SMALL'
  const size = isLargeMachineBatch(batch) ? 'LARGE' : 'SMALL'
  return `${family}-${size}`
}

function canMoveAcrossLanes(sourceBatch: any, targetBatch: any, unit: any) {
  if (!sourceBatch || !targetBatch || !unit) return false
  if (sourceBatch?.status !== 'Predicted' || targetBatch?.status !== 'Predicted') return false
  const sourceSpecial = isSpecialBatch(sourceBatch)
  const targetSpecial = isSpecialBatch(targetBatch)
  if (sourceSpecial === targetSpecial) return false
  if (!sourceSpecial && !isLargeMachineBatch(sourceBatch)) return false
  if (!targetSpecial && !isLargeMachineBatch(targetBatch)) return false
  if (isStockUnit(unit) || isSpecialPlaceholder(unit)) return false
  const uf = majorFamilyOfModel(String(unit?.model_type || ''))
  if (!uf || (uf !== 'XS' && uf !== 'AUTO')) return false
  const anchorFamily = sourceSpecial
    ? majorFamilyOfModel(String(targetBatch?.model_type || ''))
    : majorFamilyOfModel(String(sourceBatch?.model_type || ''))
  return uf === anchorFamily
}

function isUnitFamilyMismatch(unit: any, batch: any) {
  if (!unit || !batch) return false
  if (isSpecialPlaceholder(unit)) return false
  if (isCrossLanePlacement(unit, batch)) return false
  const uf = majorFamilyOfModel(String(unit?.model_type || ''))
  const bf = majorFamilyOfModel(String(batch?.model_type || ''))
  if (!uf || !bf) return false
  return uf !== bf
}

function hasUnboundPlaceholder(batch: any) {
  const units = Array.isArray(batch?.units) ? batch.units : []
  return units.some((u: any) => isStockUnit(u) && !isSpecialPlaceholder(u))
}

function specialContractCount(batch: any) {
  return (batch?.units || []).filter((u: any) => !isSpecialPlaceholder(u)).length
}

function ownershipLaneKeyOfUnit(unit: any) {
  const model = String(unit?.model_type || '').trim()
  if (!model) return ''
  const category = categoryOfModel(model, modelFamilyMap.value[model.toUpperCase()] || '')
  if (category === '特殊') return 'SPECIAL'
  if (category === '中大型XS') return 'XS-LARGE'
  if (category === '中小型XS') return 'XS-SMALL'
  if (category === '中大型AUTO') return 'AUTO-LARGE'
  if (category === '中小型AUTO') return 'AUTO-SMALL'
  if (category === '中小型G') return 'G-SMALL'
  const family = majorFamilyOfModel(model)
  if (family === 'SPECIAL') return 'SPECIAL'
  if (family === 'G') return 'G-SMALL'
  if (family === 'XS') return 'XS-SMALL'
  if (family === 'AUTO') return 'AUTO-SMALL'
  return ''
}

function isCrossLanePlacement(unit: any, batch: any) {
  if (!unit || !batch || isSpecialPlaceholder(unit)) return false
  const placed = laneKeyOfBatch(batch)
  const owner = ownershipLaneKeyOfUnit(unit)
  if (!placed || !owner || placed === owner) return false
  const ownerIsSpecial = owner === 'SPECIAL'
  const placedIsSpecial = placed === 'SPECIAL'
  if (ownerIsSpecial === placedIsSpecial) return false
  const otherLane = ownerIsSpecial ? placed : owner
  return otherLane === 'XS-LARGE' || otherLane === 'AUTO-LARGE'
}

function canAddSpecialCard(batch: any) {
  return Boolean(batch && batch.status === 'Predicted' && isSpecialBatch(batch) && specialContractCount(batch) < 15)
}

function isSpecialPlaceholder(unit: any) {
  const model = String(unit?.model_type || '').trim().toUpperCase()
  return model === 'SPECIAL' &&
    !String(unit?.contract_no || '').trim() &&
    !String(unit?.customer || '').trim() &&
    !String(unit?.dealer_name || '').trim() &&
    !String(unit?.due_date || '').trim() &&
    !String(unit?.order_remark || '').trim()
}

function batchOfUnit(unit: any) {
  if (!unit?.batch_id) return null
  return batchStore.batches.find((b: any) => b.batch_id === unit.batch_id) || null
}

function canMoveToSpecial(unit: any) {
  if (!unit || isStockUnit(unit)) return false
  const batch = batchOfUnit(unit)
  if (!batch || batch.status !== 'Predicted') return false
  if (isSpecialBatch(batch)) return false
  const category = categoryOfModel(String(unit?.model_type || ''), modelFamilyMap.value[String(unit?.model_type || '').toUpperCase()] || '')
  return category === '中大型XS' || category === '中大型AUTO'
}

function canConvertToRush(unit: any) {
  if (!unit || isStockUnit(unit) || isSpecialPlaceholder(unit)) return false
  if (!String(unit?.contract_no || '').trim()) return false
  if (!String(unit?.model_type || '').trim()) return false
  const batch = batchOfUnit(unit)
  return Boolean(batch && batch.status === 'Predicted')
}

function formatBatchCode(batchNo: any) {
  const n = Number(batchNo)
  if (!Number.isFinite(n) || n <= 0) return `第 ${batchNo || '-'} 批`
  const whole = Math.trunc(n)
  if (whole >= 101) {
    const month = Math.floor(whole / 100)
    const seq = whole % 100
    if (month >= 1 && month <= 12 && seq >= 1) {
      return `${String(month).padStart(2, '0')}-${String(seq).padStart(2, '0')}`
    }
  }
  return `第 ${String(whole).padStart(2, '0')} 批`
}

const canRevoke = computed(() => {
  if (selectedBatches.value.length !== 1) return false
  const selectedBatchId = selectedBatches.value[0]
  const batch = batchStore.batches.find((b: any) => String(b.batch_id) === selectedBatchId)
  return batch?.status === 'Confirmed'
})

async function batchRevoke() {
  if (selectedBatches.value.length !== 1) return
  const selectedBatchId = selectedBatches.value[0]
  const batch = batchStore.batches.find((b: any) => String(b.batch_id) === selectedBatchId)
  if (!batch) {
    selectedBatches.value = []
    ElMessage.warning('该预测列已被重算替换，请刷新后选择最新预测列')
    await refresh()
    return
  }
  const selectedId = batch.batch_id
  try {
    await ElMessageBox.confirm('撤销确认将删除 plan_import 中该批次的记录并恢复为待确认状态，确认？', '撤销确认', {
      confirmButtonText: '确认撤销',
      cancelButtonText: '取消',
      type: 'warning'
    })
    await sandboxApi.revokeBatch(selectedId)
    ElMessage.success('已撤销确认，批次恢复为待确认')
    selectedBatches.value = []
    await refresh()
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error(e.message || '撤销失败')
  }
}

function displayBatchCode(batch: any) {
  const explicit = String(batch?.batch_code || '').trim()
  if (explicit) return explicit
  return formatBatchCode(batch.batch_no)
}

async function toggleSelect(batchId: string) {
  if (recomputing.value || batchStore.loading) return
  const isSelected = selectedBatches.value[0] === batchId
  selectedBatches.value = isSelected ? [] : [batchId]
  if (isSelected || !canEditSandbox.value) return
  const batch = batchStore.batches.find((b: any) => getBatchUniqueId(b) === batchId)
  if (!batch || String(batch.status || '') !== 'Predicted' || isSpecialBatch(batch)) return
  const slotNo = batchSlotOrder(batch)
  if (slotNo <= 0 || slotNo === optimizedTargetSlotNo.value) return
  await handleRecompute(true)
}

async function onSeriesFilterChange() {
  await syncScrollMetrics()
}

function batchDataFingerprint(batches: any[]): string {
  return batches
    .map((batch: any) => ({
      id: String(batch?.batch_id || ''),
      updated_at: String(batch?.updated_at || ''),
      status: String(batch?.status || ''),
      unit_count: Array.isArray(batch?.units) ? batch.units.length : null,
    }))
    .sort((a, b) => a.id.localeCompare(b.id))
    .map((item) => `${item.id}|${item.updated_at}|${item.status}|${item.unit_count ?? ''}`)
    .join(';')
}

async function refresh(options: { markDataUpdate?: boolean } = {}) {
  if (dragging.value || moving.value) {
    pendingRefresh.value = true
    return
  }
  await batchStore.fetchBatches({ status: SANDBOX_STATUS })
  const liveIds = new Set(batchStore.batches.map((batch: any) => String(batch?.batch_id || '')))
  const staleSelected = selectedBatches.value.filter((id) => !liveIds.has(String(id)))
  if (staleSelected.length) {
    selectedBatches.value = selectedBatches.value.filter((id) => liveIds.has(String(id)))
    if (batchDetail.value && !liveIds.has(String(batchDetail.value.batch_id || ''))) {
      batchDetail.value = null
      batchDetailVisible.value = false
    }
    ElMessage.warning('预测方案已重算，原预测列已替换，请重新选择最新预测列')
  }
  for (const key of Object.keys(batchCodeInputs.value)) if (!liveIds.has(key)) delete batchCodeInputs.value[key]
  for (const key of Object.keys(inboundDateInputs.value)) if (!liveIds.has(key)) delete inboundDateInputs.value[key]
  const nextFingerprint = batchDataFingerprint(batchStore.batches)
  if (options.markDataUpdate && lastBatchDataFingerprint.value && nextFingerprint !== lastBatchDataFingerprint.value) {
    hasDataUpdate.value = true
  }
  lastBatchDataFingerprint.value = nextFingerprint
  sortBatchUnitsInPlace()
  initBatchInputs()
  resetAllStockEdits()
  if (!latestAchievementCategories.value.length) {
    try {
      const achievement: any = await sandboxApi.getForecastAchievement()
      latestAchievementCategories.value = achievement?.achievement?.categories || []
    } catch { /* keep the recommendation basis explicitly unavailable */ }
  }
  await syncScrollMetrics()
}

async function handleManualRefresh() {
  suspendAutoSort.value = false
  pinnedBatchOrder.value = []
  await refresh()
  hasDataUpdate.value = false
}

function openManualPredictedDrawer() {
  manualPredictedForm.value = { model_family: '中大型XS', quantity: 10, remark: '' }
  manualPredictedVisible.value = true
}

async function submitManualPredictedBatch() {
  const family = String(manualPredictedForm.value.model_family || '').trim()
  const option = manualFamilyOptions.find((item) => item.value === family)
  const quantity = Number(manualPredictedForm.value.quantity)
  if (!option) return ElMessage.warning('请选择明确机型族')
  if (!Number.isInteger(quantity) || quantity <= 0) return ElMessage.warning('数量必须是大于 0 的整数')
  if (quantity > option.capacity) return ElMessage.warning(`${option.label} 单条产线最多 ${option.capacity} 台`)
  manualPredictedSaving.value = true
  try {
    const res = await sandboxApi.createManualPredictedBatch({ model_family: family, quantity, remark: String(manualPredictedForm.value.remark || '').trim() }) as any
    ElMessage.success('新增预测产线已保存')
    manualPredictedVisible.value = false
    await refresh()
    const batchId = String(res?.batch?.batch_id || '')
    if (batchId) selectedBatches.value = [batchId]
  } catch (e: any) {
    ElMessage.error(getApiErrorMessage(e) || e.message || '新增预测产线失败')
  } finally { manualPredictedSaving.value = false }
}

async function forceRefresh() {
  pendingRefresh.value = false
  await batchStore.fetchBatches({ status: SANDBOX_STATUS })
  sortBatchUnitsInPlace()
  initBatchInputs()
  resetAllStockEdits()
  await syncScrollMetrics()
}

async function flushPendingRefresh() {
  if (dragging.value || moving.value || !pendingRefresh.value) return
  pendingRefresh.value = false
  await batchStore.fetchBatches({ status: SANDBOX_STATUS })
  sortBatchUnitsInPlace()
  initBatchInputs()
  resetAllStockEdits()
  await syncScrollMetrics()
}

async function loadModelTypes() {
  try {
    const res = await sandboxApi.getModelTypes() as any
    const list = Array.isArray(res) ? res : (res?.model_types || res?.types || [])
    if (Array.isArray(list)) {
      const nextMap: Record<string, string> = {}
      const nextSortOrderMap: Record<string, number> = {}
      modelTypes.value = list
        .map((item: any) => {
          if (typeof item === 'string') return item
          if (item && typeof item === 'object') {
            const mt = String(item.model_type || '').trim()
            const mf = String(item.model_family || '').trim()
            if (mt && mf) nextMap[mt.toUpperCase()] = mf
            const rawSortOrder = item.sort_order
            const sortOrder = Number(rawSortOrder)
            if (mt && rawSortOrder !== null && rawSortOrder !== undefined && Number.isFinite(sortOrder)) {
              nextSortOrderMap[mt.toUpperCase()] = sortOrder
            }
            return mt
          }
          return ''
        })
        .filter(Boolean)
      modelFamilyMap.value = nextMap
      modelSortOrderMap.value = nextSortOrderMap
    } else {
      modelTypes.value = []
      modelFamilyMap.value = {}
      modelSortOrderMap.value = {}
    }
  } catch {
    modelTypes.value = []
    modelFamilyMap.value = {}
    modelSortOrderMap.value = {}
  }
}

async function handleRecompute(preserveSelection = false) {
  if (recomputing.value) return
  if (!canEditSandbox.value) {
    ElMessage.warning('当前账号没有预测沙盒编辑权限')
    return
  }
  let targetSlotNo: number | undefined
  let isClicked = false
  if (selectedBatches.value.length === 1) {
    const selectedBatchId = selectedBatches.value[0]
    const selectedBatch = batchStore.batches.find((b: any) => String(b.batch_id) === selectedBatchId)
    if (!selectedBatch || String(selectedBatch.status || '') !== 'Predicted') {
      ElMessage.warning('请选择 1 个待确认预测批次作为重算目标列')
      return
    }
    targetSlotNo = batchSlotOrder(selectedBatch)
    isClicked = true
  }
  if (!targetSlotNo || targetSlotNo <= 0) {
    targetSlotNo = 1
    isClicked = false
  }
  recomputing.value = true
  const affectedManualBatches = batchStore.batches.filter((batch: any) => {
    if (String(batch?.status || '') !== 'Predicted' || !batch?.is_manually_adjusted) return false
    return !isClicked || batchSlotOrder(batch) === targetSlotNo
  })
  if (affectedManualBatches.length) {
    try {
      await ElMessageBox.confirm(
        `本次重算会覆盖 ${affectedManualBatches.length} 个未锁定的人工调整列；锁定卡片和已确认批次不会被覆盖。是否继续？`,
        '确认重算影响',
        { type: 'warning', confirmButtonText: '继续重算', cancelButtonText: '取消' }
      )
    } catch {
      recomputing.value = false
      return
    }
  }
  try {
    const recomputeRes: any = await runRecompute(targetSlotNo, isClicked)
    clearPendingRecomputeJob()
    latestAchievementCategories.value = recomputeRes?.achievement?.categories || []
    if (!preserveSelection) selectedBatches.value = []
    ElMessage.success('已按目标列优化备货比例，其他预测列备货仅作占位参考')
    await refresh()
    if (isClicked) {
      // 点击单列：直接标记选中列为备货建议
      optimizedTargetSlotNo.value = targetSlotNo ?? 1
    } else {
      // 全量重算：根据大类缺口自动找最需要备货的列
      const suggestedSlot = findSuggestedSlotByGap(recomputeRes?.achievement?.categories)
      optimizedTargetSlotNo.value = suggestedSlot
    }
  } catch (e: any) {
    const status = Number(e?.response?.status || 0)
    if (status === 409) {
      ElMessage.warning('已有全量重算任务执行中，请稍后再试')
    } else if (status === 504) {
      ElMessage.warning('全量重算仍在执行或超时，请稍后刷新重试')
    } else {
      ElMessage.error(e.message || '全量重算失败')
    }
  } finally {
    recomputing.value = false
  }
}

async function batchConfirm() {
  if (selectedBatches.value.length !== 1) {
    ElMessage.warning('确认前请勾选 1 个待确认批次')
    return
  }
  const selectedBatchId = selectedBatches.value[0]
  const batch = batchStore.batches.find((b: any) => String(b.batch_id) === selectedBatchId)
  if (!batch) return
  const selectedId = batch.batch_id

  // 从列顶获取输入的批次号和预计入库时间
  const batchCode = String(batchCodeInputs.value[selectedId] || '').trim()
  if (!batchCode) {
    ElMessage.warning('请在列顶输入批次号')
    return
  }
  const codePattern = /^(0[1-9]|1[0-2])-\d{2}[\u4e00-\u9fa5A-Za-z0-9_-]{0,20}$/
  if (!codePattern.test(batchCode)) {
    ElMessage.warning('批次号格式错误：必须以 MM-SS 开头，后面可追加20字以内中文/字母/数字/下划线/中划线')
    return
  }

  const inboundDate = String(inboundDateInputs.value[selectedId] || '').trim()
  if (!inboundDate) {
    ElMessage.warning('请在列顶选择预计入库时间')
    return
  }

  // Use the server-side validation result as the confirmation source of truth.
  let impact: any
  try {
    impact = await sandboxApi.previewBatchImpact(selectedId, inboundDate)
    const blockingRisks = (impact?.risks || []).filter((risk: any) => risk.blocking)
    if (blockingRisks.length) {
      batchDetail.value = impact
      activeRiskUnitIds.value = new Set(blockingRisks.flatMap((risk: any) => risk.unit_ids || []).map((id: any) => String(id)))
      batchDetailVisible.value = true
      ElMessage.warning(`存在阻塞风险，暂不能确认：${blockingRisks.map((risk: any) => risk.message).join('；')}`)
      return
    }
    const preview: any = await sandboxApi.previewSyncToPlan(selectedId, batchCode)
    confirmationPreview.value = {
      ...impact,
      batch_code: batchCode,
      sync_count: preview?.count ?? impact?.sync_count ?? 0,
      sync_preview: preview,
      audit: await sandboxApi.getBatchAudit(selectedId).catch(() => null),
    }
    confirmationVisible.value = true
  } catch {
    // A network failure must not bypass server-side validation.
    ElMessage.error('无法获取确认前校验，请恢复服务后重试')
    return
  }

}

function onDragStart(evt: any, sourceBatch: any) {
  dragging.value = true
  const idx = evt?.oldDraggableIndex ?? evt?.oldIndex
  const unit = getDraggedData(evt) || sourceBatch?.units?.[idx]
  dragSource.value = unit?.unit_id
    ? { unit, sourceBatchId: sourceBatch?.batch_id || unit.batch_id }
    : null
  dragFamily.value = majorFamilyOfModel(sourceBatch?.model_type || '')
  dragLane.value = laneKeyOfBatch(sourceBatch)
}

async function onDragEnd() {
  dragging.value = false
  dragFamily.value = ''
  dragLane.value = ''
  dragSource.value = null
  stopEdgeAutoScroll()
  await flushPendingRefresh()
}

function getDraggedData(evt: any) {
  return evt?.data || evt?.clonedData || evt?.item?.__draggable_context?.element
}

function getNewSlot(evt: any) {
  const idx = evt?.newDraggableIndex ?? evt?.newIndex
  if (idx === undefined || idx === null) return 0
  return idx + 1
}

async function onUnitMoved(evt: any, targetBatch: any) {
  const unit = dragSource.value?.unit || getDraggedData(evt)
  const sourceBatchId = dragSource.value?.sourceBatchId || unit?.batch_id
  const targetSlot = getNewSlot(evt)
  if (!unit?.unit_id || !targetBatch?.batch_id || !targetSlot) {
    await forceRefresh()
    return
  }
  if (isStockUnit(unit) && sourceBatchId && sourceBatchId !== targetBatch.batch_id) {
    ElMessage.warning('备货卡片不可跨批拖拽')
    await forceRefresh()
    return
  }
  if (isUnitFamilyMismatch(unit, targetBatch)) {
    const canContractFirstOccupy = sourceBatchId && sourceBatchId !== targetBatch.batch_id && hasUnboundPlaceholder(targetBatch)
    if (!canContractFirstOccupy) {
      ElMessage.warning('仅允许同系列机型在同系列批次内移动')
      await forceRefresh()
      return
    }
  }
  const sourceBatch = batchStore.batches.find((b: any) => b.batch_id === sourceBatchId)
  if (sourceBatch && laneKeyOfBatch(sourceBatch) !== laneKeyOfBatch(targetBatch) && !canMoveAcrossLanes(sourceBatch, targetBatch, unit)) {
    ElMessage.warning('仅允许在同列（同系列且同大类）内拖拽')
    await forceRefresh()
    return
  }
  moving.value = true
  try {
    if (sourceBatchId === targetBatch.batch_id) {
      await sandboxApi.reorderUnitSlot(unit.unit_id, targetSlot)
    } else {
      await sandboxApi.moveUnitBatch(unit.unit_id, targetBatch.batch_id, targetSlot)
    }
    if (!suspendAutoSort.value) {
      pinnedBatchOrder.value = filteredBatches.value.map((b: any) => String(b?.batch_id || ''))
    }
    suspendAutoSort.value = true
    const adjusted = new Set(manualAdjustedBatchIds.value)
    if (sourceBatchId) adjusted.add(String(sourceBatchId))
    adjusted.add(String(targetBatch.batch_id))
    manualAdjustedBatchIds.value = adjusted
    ElMessage.success('卡片位置已更新')
    await forceRefresh()
  } catch (e: any) {
    ElMessage.error('移动失败: ' + (e.message || '未知错误'))
    await forceRefresh()
  } finally {
    moving.value = false
    await flushPendingRefresh()
  }
}

function openEditDrawer(unit: any) {
  editingUnit.value = unit
  editForm.value = {
    contract_no: unit.contract_no || '',
    customer: unit.customer || '',
    dealer_name: unit.dealer_name || '',
    model_type: unit.model_type || '',
    order_remark: unit.order_remark || ''
  }
  if (isEditingSpecialBatch.value && isFamilyToken(editForm.value.model_type)) {
    editForm.value.model_type = ''
  }
  editVisible.value = true
}

async function saveEdit() {
  if (!editingUnit.value) return
  saving.value = true
  try {
    const { contract_no: _, ...data } = editForm.value as any
    await sandboxApi.updateUnit(editingUnit.value.unit_id, data)
    const adjusted = new Set(manualAdjustedBatchIds.value)
    adjusted.add(String(editingUnit.value.batch_id || ''))
    manualAdjustedBatchIds.value = adjusted
    ElMessage.success('已保存并锁定')
    editVisible.value = false
    refresh()
  } catch (e: any) {
    ElMessage.error(e.message)
  } finally {
    saving.value = false
  }
}

function openSpecialAddDrawer(batch: any) {
  specialAddBatch.value = batch
  specialAddForm.value = { contract_no: '', customer: '', dealer_name: '', model_type: '', due_date: '', order_remark: '' }
  specialAddVisible.value = true
}

async function submitSpecialCard() {
  const batch = specialAddBatch.value
  if (!batch?.batch_id) return
  const payload = {
    batch_id: batch.batch_id,
    contract_no: String(specialAddForm.value.contract_no || '').trim(),
    customer: String(specialAddForm.value.customer || '').trim(),
    dealer_name: String(specialAddForm.value.dealer_name || '').trim(),
    model_type: String(specialAddForm.value.model_type || '').trim(),
    due_date: String(specialAddForm.value.due_date || '').trim(),
    order_remark: String(specialAddForm.value.order_remark || '').trim()
  }
  if (!payload.model_type) {
    ElMessage.warning('请选择机型')
    return
  }
  specialAddSaving.value = true
  try {
    await sandboxApi.createSpecialCard(payload)
    ElMessage.success('特殊卡片已添加')
    specialAddVisible.value = false
    await refresh()
  } catch (e: any) {
    ElMessage.error(getApiErrorMessage(e) || e.message || '添加特殊卡片失败')
  } finally {
    specialAddSaving.value = false
  }
}

function onContextMenu({ event, unit }: { event: MouseEvent; unit: any }) {
  contextMenu.value = { visible: true, x: event.clientX, y: event.clientY, unit }
  setTimeout(() => {
    const close = () => { contextMenu.value.visible = false; document.removeEventListener('click', close) }
    document.addEventListener('click', close)
  }, 100)
}

async function handleUnlock() {
  const unit = contextMenu.value.unit
  if (!unit) return
  try {
    await sandboxApi.unlockUnit(unit.unit_id)
    ElMessage.success('已解锁')
    refresh()
  } catch (e: any) {
    ElMessage.error(e.message)
  }
  contextMenu.value.visible = false
}

async function handleMarkSpot() {
  const unit = contextMenu.value.unit
  if (!unit) return
  try {
    await ElMessageBox.confirm('确认将此卡片标记为现货（清除订单信息）？', '确认', { type: 'warning' })
    const res: any = await sandboxApi.markSpot(unit.unit_id)
    if (res && res.blocked_or_warned_units && res.blocked_or_warned_units.length > 0) {
      ElMessage.warning(`已标记为现货，但同合同下仍有 ${res.blocked_or_warned_units.length} 台设备已确认或生产中，需人工处理`)
    } else {
      ElMessage.success('已标记为现货，同合同计划已取消')
    }
    refresh()
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error(e.message)
  }
  contextMenu.value.visible = false
}

async function handleConvertToRush() {
  const unit = contextMenu.value.unit
  contextMenu.value.visible = false
  if (!unit) return
  try {
    await ElMessageBox.confirm(
      `确认将合同 ${unit.contract_no || '-'} 的这张卡片转为急单？原沙盘卡片会清空为占位。`,
      '转为急单',
      { type: 'warning', confirmButtonText: '转为急单', cancelButtonText: '取消' }
    )
    await sandboxApi.convertUnitToRush(unit.unit_id)
    ElMessage.success('已转为急单，可在生产看板急单队列中处理')
    await refresh()
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error(getApiErrorMessage(e) || e.message || '转为急单失败')
  }
}

async function handleInsertEmptySlot() {
  const unit = contextMenu.value.unit
  contextMenu.value.visible = false
  if (!unit) return
  try {
    await sandboxApi.insertEmptySlot(unit.batch_id, unit.slot_index)
    ElMessage.success('空位已在此卡片前插入')
    refresh()
  } catch (e: any) {
    ElMessage.error(e.message || '插入空位失败')
  }
}

async function handleMoveToSpecial() {
  const unit = contextMenu.value.unit
  contextMenu.value.visible = false
  if (!unit) return
  try {
    await sandboxApi.moveUnitToSpecial(unit.unit_id)
    ElMessage.success('已转移到特殊批次')
    await refresh()
  } catch (e: any) {
    ElMessage.error(getApiErrorMessage(e) || e.message || '转移到特殊批次失败')
  }
}

async function syncScrollMetrics() {
  await nextTick()
  const body = batchesContainerRef.value
  if (!body) return
  topScrollWidth.value = body.scrollWidth
}

function onTopScroll() {
  const top = topScrollRef.value
  const body = batchesContainerRef.value
  if (!top || !body || syncingScroll.value) return
  syncingScroll.value = true
  body.scrollLeft = top.scrollLeft
  requestAnimationFrame(() => { syncingScroll.value = false })
}

function onBodyScroll() {
  const top = topScrollRef.value
  const body = batchesContainerRef.value
  if (!top || !body || syncingScroll.value) return
  syncingScroll.value = true
  top.scrollLeft = body.scrollLeft
  requestAnimationFrame(() => { syncingScroll.value = false })
}

function stopEdgeAutoScroll() {
  if (edgeAutoScrollTimer.value) {
    window.clearInterval(edgeAutoScrollTimer.value)
    edgeAutoScrollTimer.value = null
  }
}

function onEdgeHover(e: MouseEvent) {
  if (!dragging.value) {
    stopEdgeAutoScroll()
    return
  }
  const body = batchesContainerRef.value
  if (!body) return
  const rect = body.getBoundingClientRect()
  const edge = 50
  const speed = 18
  let dir = 0
  if (e.clientX < rect.left + edge) dir = -1
  if (e.clientX > rect.right - edge) dir = 1
  if (!dir) {
    stopEdgeAutoScroll()
    return
  }
  if (edgeAutoScrollTimer.value) return
  edgeAutoScrollTimer.value = window.setInterval(() => {
    body.scrollLeft += dir * speed
    onBodyScroll()
  }, 16)
}

let cleanupFns: (() => void)[] = []

onMounted(async () => {
  if (pendingRecomputeJobId.value) startRecomputeElapsedTimer()
  await loadModelTypes()
  await fetchLastBatchCode()
  await refresh()
  wsConnect()
  cleanupFns.push(onEvent('unit:updated', () => refresh({ markDataUpdate: true })))
  cleanupFns.push(onEvent('batch:updated', () => refresh({ markDataUpdate: true })))
  cleanupFns.push(onEvent('batch:confirmed', () => refresh({ markDataUpdate: true })))
  window.addEventListener('resize', syncScrollMetrics)
})

onActivated(async () => {
  await refresh({ markDataUpdate: true })
})

onUnmounted(() => {
  cleanupFns.forEach(fn => fn())
  cleanupFns = []
  window.removeEventListener('resize', syncScrollMetrics)
  stopEdgeAutoScroll()
  stopRecomputeElapsedTimer()
  wsDisconnect()
})
</script>

<style scoped>
.sandbox-summary { display: grid; grid-template-columns: repeat(4, minmax(120px, 1fr)); gap: 1px; background: #e8edf2; border-bottom: 1px solid #e8edf2; }
.sandbox-summary > div { padding: 12px 18px; background: #fff; }
.sandbox-summary span, .sandbox-summary strong { display: block; }
.sandbox-summary span { color: #667085; font-size: 12px; }
.sandbox-summary strong { margin-top: 4px; color: #1d2939; font-size: 22px; }
.sandbox-settings { background: #fff; border-bottom: 1px solid #e8edf2; }
.sandbox-settings summary { padding: 10px 24px; color: #475467; font-size: 13px; font-weight: 600; cursor: pointer; }
.sandbox-settings .sandbox-header { padding: 0 24px 14px; }
@media (max-width: 700px) { .sandbox-summary { grid-template-columns: repeat(2, minmax(120px, 1fr)); } .sandbox-summary > div { padding: 10px 14px; } .sandbox-settings summary { padding-inline: 16px; } .sandbox-settings .sandbox-header { padding-inline: 16px; } }
.top-scroll {
  overflow-x: auto;
  overflow-y: hidden;
  height: 14px;
  margin-bottom: 4px;
  border-radius: 4px;
}
.sandbox-batches {
  /* 隐藏原生底部滚动条，统一使用顶部 top-scroll */
  scrollbar-width: none;
}
.sandbox-batches::-webkit-scrollbar {
  display: none;
}
.ctx-item {
  padding: 6px 16px;
  cursor: pointer;
  font-size: 13px;
}
.ctx-item:hover { background: #f5f5f5; }

.batch-header-main {
  min-width: 0;
  flex: 1 1 auto;
}

.batch-headline {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  width: 100%;
  white-space: nowrap;
  line-height: 1.25;
}

.batch-select {
  flex: 0 0 auto;
  margin-right: 2px;
}

.batch-headline .batch-title {
  flex: 0 1 auto;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.25;
  font-size: 17px;
  font-weight: 700;
}

.batch-counts {
  flex: 0 0 auto;
  max-width: 100%;
  white-space: nowrap;
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 15px;
  font-weight: 700;
  padding-left: 8px;
  border-left: 1px solid #d7dce5;
  line-height: 1.25;
  overflow: hidden;
}

.batch-count {
  line-height: 1.25;
}

.batch-count-ordered {
  color: #0f766e;
}

.batch-count-stock {
  color: #d97706;
}

.batch-count-separator {
  color: #c4c9d4;
  font-weight: 700;
}

.batch-status-top-right {
  position: absolute;
  top: 0;
  right: 0;
  z-index: 10;
}

.batch-target-badge {
  position: absolute;
  top: 0;
  left: 0;
  z-index: 10;
  padding: 2px 8px;
  border-bottom-right-radius: 8px;
  background: #2563eb;
  color: #fff;
  font-size: 12px;
  font-weight: 700;
  line-height: 20px;
}

.batch-target-slot,
.batch-recompute-target {
  box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.35) inset;
}

.corner-tag {
  border-top-left-radius: 0;
  border-bottom-right-radius: 0;
  border-top-right-radius: 8px;
  border-bottom-left-radius: 8px;
  border-top: none;
  border-right: none;
  font-weight: 700;
}
.manual-adjusted-tag {
  margin-right: 4px;
  border-radius: 0 0 6px 6px;
  font-weight: 700;
}

.batch-meta-due {
  display: block;
  text-align: center;
  font-size: 13.5px;
  color: #4b5563;
  font-weight: 600;
}
.batch-meta-provenance {
  display: flex;
  justify-content: center;
  gap: 12px;
  margin-top: 3px;
  color: #667085;
  font-size: 12px;
}

.batch-plan-summary {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 7px;
  margin-top: 5px;
  color: #64748b;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}
.plan-summary-item + .plan-summary-item { border-left: 1px solid #d7dce5; padding-left: 7px; }
.plan-summary-risk { color: #b42318; font-weight: 700; }
.batch-risk-list {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 3px;
  color: #b42318;
  font-size: 11px;
}
.batch-risk-item {
  max-width: 145px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  appearance: none;
  border: 0;
  padding: 0;
  background: transparent;
  color: inherit;
  cursor: pointer;
  font: inherit;
}
.batch-risk-item:hover { text-decoration: underline; }
.batch-risk-item + .batch-risk-item { border-left: 1px solid #f1b5b0; padding-left: 4px; }
.batch-risk-more { color: #667085; }

.unit-risk-highlight {
  box-shadow: 0 0 0 3px #f59e0b inset !important;
  border-radius: 6px;
}
.batch-detail-overview {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 14px;
}
.batch-detail-stat {
  display: grid;
  gap: 3px;
  min-width: 0;
  padding: 10px 12px;
  border: 1px solid #e4e7ec;
  border-radius: 4px;
  color: #475467;
  font-size: 12px;
}
.batch-detail-stat strong {
  overflow: hidden;
  color: #182230;
  font-size: 16px;
  line-height: 1.25;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.batch-detail-inbound {
  grid-column: 1 / -1;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
}
.batch-detail-inbound small { color: #667085; font-size: 12px; white-space: nowrap; }
.batch-detail-risk {
  display: grid;
  gap: 4px;
  padding: 12px 0;
  border-bottom: 1px solid #eaecf0;
  color: #b42318;
}
.batch-detail-risk small { color: #667085; }
.batch-detail-sync-status {
  display: grid;
  gap: 5px;
  margin: 12px 0;
  padding: 10px 12px;
  border: 1px solid #d0d5dd;
  border-radius: 6px;
  color: #344054;
  font-size: 13px;
}
.batch-detail-sync-status .sync-error { color: #b42318; white-space: pre-wrap; }
.batch-detail-note {
  margin-top: 18px;
  color: #667085;
  font-size: 12px;
  line-height: 1.6;
}

.batch-meta-models {
  display: block;
  text-align: left;
  color: #1f2d3d;
  font-size: 15px;
  font-weight: 700;
  margin-top: 4px;
  padding: 6px 12px;
  border-radius: 10px;
  background: #eef3ff;
  border: 1px solid #c9d7ff;
  height: 86px;
  overflow-y: auto;
}

.recompute-job-status { display: inline-flex; align-items: center; gap: 4px; color: #946200; font-size: 12px; }
.sandbox-data-update { display: inline-flex; align-items: center; min-height: 24px; padding: 0 8px; border: 1px solid #b8d7ff; border-radius: 4px; color: #2563eb; background: #eff6ff; font-size: 12px; white-space: nowrap; }
.stock-recommendation {
  display: grid;
  width: 100%;
  gap: 2px;
  margin-top: 6px;
  padding: 7px 10px;
  border: 1px solid #93c5fd;
  border-radius: 4px;
  background: #eff6ff;
  color: #1d4ed8;
  text-align: left;
  cursor: pointer;
  font-size: 12px;
}
.stock-recommendation span { color: #475467; }
.batch-detail-recommendation {
  display: grid;
  gap: 6px;
  margin: 12px 0;
  padding: 10px 12px;
  border: 1px solid #d0d5dd;
  border-radius: 4px;
  color: #344054;
  font-size: 13px;
  line-height: 1.45;
}
.batch-detail-history {
  margin-top: 8px;
  border-top: 1px solid #eaecf0;
  color: #475467;
  font-size: 13px;
}
.batch-detail-history summary {
  padding: 10px 0;
  color: #344054;
  cursor: pointer;
  font-weight: 600;
}
.batch-detail-history-content {
  display: grid;
  gap: 6px;
  padding: 0 0 10px;
  color: #667085;
  line-height: 1.45;
}
.confirmation-summary {
  display: grid;
  gap: 8px;
  margin-bottom: 14px;
  color: #344054;
  font-size: 14px;
}
.confirmation-risk {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 0;
  color: #b42318;
  font-size: 13px;
}
.confirmation-risk span { color: #667085; white-space: nowrap; }
.batch-placeholder-slot {
  opacity: 0.82;
}

.batch-model-row {
  display: flex;
  align-items: baseline;
  justify-content: center;
  gap: 8px;
  line-height: 1.55;
  white-space: normal;
  word-break: break-all;
}

.batch-model-name {
  min-width: 0;
}

.model-count-ordered {
  color: #0f766e;
  font-weight: 600;
}

.model-count-stock {
  color: #d97706;
  font-weight: 600;
}

.stock-editor {
  margin: 8px 8px 0;
  padding: 8px;
  border: 1px solid #d7dce5;
  border-radius: 6px;
  background: #fff;
}

.stock-editor-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 118px;
  gap: 8px;
  align-items: center;
  min-height: 32px;
}

.stock-editor-row + .stock-editor-row {
  margin-top: 6px;
}

.stock-editor-model {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  font-weight: 700;
  color: #1f2d3d;
}

.stock-editor-input {
  width: 118px;
}

.stock-editor-error {
  margin-top: 6px;
  color: #d4380d;
  font-size: 12px;
  line-height: 1.4;
}

.stock-editor-actions {
  display: flex;
  justify-content: flex-end;
  gap: 6px;
  margin-top: 8px;
}

.special-card-add {
  width: 100%;
  min-height: 54px;
  margin-top: 8px;
  border: 1px dashed #d81b60;
  border-radius: 6px;
  background: #fff7fb;
  color: #b81250;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  font-size: 13px;
}

.special-card-add:hover {
  background: #ffeaf3;
  border-color: #b81250;
}

.mismatch-text {
  color: #d4380d;
  font-weight: 600;
}

/* 沙盘批次列内的卡片需要撑满列宽（生产看板不适用此规则，所以在此处局部覆盖） */
.batch-units :deep(.unit-card) {
  width: calc(100% - 8px) !important;
  box-sizing: border-box !important;
}

.unit-lane-mismatch :deep(.unit-card) {
  box-shadow: 0 0 0 2px rgba(212, 56, 13, 0.45) inset;
}

.unit-stock-placeholder :deep(.unit-card) {
  border-style: dashed;
  opacity: 0.72;
}

.batch-top-inputs {
  margin-top: 8px;
  margin-bottom: 6px;
  padding: 0 4px;
}

.batch-top-inputs :deep(.el-input),
.batch-top-inputs :deep(.el-date-editor) {
  height: 38px !important;
}

.batch-top-inputs :deep(.el-input__wrapper) {
  height: 38px !important;
  box-sizing: border-box !important;
  padding: 4px 10px !important;
}

.batch-top-inputs :deep(.el-input__inner) {
  height: 100% !important;
  font-size: 13px !important;
  font-weight: 700 !important;
  color: #0f172a !important;
}

.batch-top-inputs :deep(.el-input__inner::placeholder) {
  color: #475569 !important;
  opacity: 1 !important;
}
.batch-top-inputs :deep(.el-input__inner::-webkit-input-placeholder) {
  color: #475569 !important;
}
.batch-top-inputs :deep(.el-input__inner::-moz-placeholder) {
  color: #475569 !important;
}
.batch-top-inputs :deep(.el-input__inner:-ms-input-placeholder) {
  color: #475569 !important;
}

.input-row {
  display: flex;
  align-items: center;
  gap: 8px;
  justify-content: space-between;
}

.series-tabs :deep(.el-radio-button__inner) {
  min-height: 38px !important;
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
  font-size: var(--font-size-base) !important;
  font-weight: 500 !important;
  padding: 6px 16px !important;
  transition: all 0.3s cubic-bezier(0.2, 0, 0, 1) !important;
}

.series-tabs :deep(.el-radio-button:first-child .el-radio-button__inner) {
  border-top-left-radius: var(--radius-md) !important;
  border-bottom-left-radius: var(--radius-md) !important;
}

.series-tabs :deep(.el-radio-button:last-child .el-radio-button__inner) {
  border-top-right-radius: var(--radius-md) !important;
  border-bottom-right-radius: var(--radius-md) !important;
}

/* Batch capacity and confirmation status styling updates */
.batch-card.batch-confirmed {
  background-color: #f0fdf4 !important; /* soft green success background */
  border: 1px solid #bbf7d0 !important;
  box-shadow: 0 4px 10px rgba(16, 185, 129, 0.04) !important;
}

.batch-capacity-bar {
  display: flex;
  height: 6px;
  background-color: #f1f5f9;
  border-radius: 3px;
  overflow: hidden;
  margin: 8px 0;
  width: 100%;
  box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.05);
}

.bar-segment {
  height: 100%;
  transition: width 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.segment-ordered {
  background-color: #10b981; /* Emerald Green */
}

.segment-stock {
  background-color: #f59e0b; /* Warm Amber */
}

.segment-empty {
  background-color: #cbd5e1; /* Slate/Gray */
}

.batch-top-inputs :deep(.el-input__wrapper),
.batch-top-inputs :deep(.el-date-editor) {
  background-color: #ffffff !important;
  border: 1.5px solid #94a3b8 !important;
  box-shadow: none !important;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}

.batch-top-inputs :deep(.el-input__wrapper:hover),
.batch-top-inputs :deep(.el-input__wrapper.is-focus) {
  background-color: #ffffff !important;
  border-color: #2563eb !important;
  box-shadow: 0 0 0 1px #2563eb !important;
}

/* Drag and drop interactive guides */
.batch-card.is-valid-drop-target {
  box-shadow: 0 0 0 2.5px #10b981, 0 4px 12px rgba(16, 185, 129, 0.08) !important;
  background-color: #f0fdf4 !important;
  transition: all 0.25s ease !important;
}

.batch-card.is-invalid-drop-target {
  opacity: 0.35 !important;
  pointer-events: none !important;
  transition: all 0.25s ease !important;
}

:deep(.unit-card.is-active-dropzone) {
  border: 2px dashed #10b981 !important;
  background: #f0fdf4 !important;
  animation: dropzone-pulse 2s infinite ease-in-out !important;
}

:deep(.hidden-card) {
  display: none !important;
}

@keyframes dropzone-pulse {
  0%, 100% {
    box-shadow: 0 0 0 0px rgba(16, 185, 129, 0.2);
  }
  50% {
    box-shadow: 0 0 0 4px rgba(16, 185, 129, 0.4);
  }
}
</style>
