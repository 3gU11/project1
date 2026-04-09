<template>
  <div class="planning-container">
    <el-card class="box-card" shadow="hover">
      <template #header>
        <div class="card-header">
          <span class="title">👑 生产统筹 & 订单资源分配</span>
          <el-button type="primary" :icon="Refresh" @click="fetchData(true)" :loading="loading">刷新</el-button>
        </div>
      </template>
      <el-alert
        v-if="loadError"
        class="load-error"
        type="error"
        :closable="false"
        :title="loadError"
        show-icon
      >
        <template #default>
          <el-button size="small" @click="retryFetchData">重试</el-button>
        </template>
      </el-alert>
      <PageSkeleton v-if="showInitialSkeleton" :blocks="8" min-height="320px" />

      <el-row v-else :gutter="16">
        <el-col :span="8">
          <el-tabs v-model="activeTab">
            <el-tab-pane :label="`📄 待审合同 (${pendingTotalQuick})`" name="pending" lazy>
              <el-input v-model="searchPending" placeholder="搜索待审合同(合同号/客户)" clearable />
              <div class="filter-tip">📊 共 {{ pendingTotal }} 单，{{ pendingMonthGroups.length }} 个月分组</div>
              <el-collapse v-model="expandedPending" class="month-list">
                <el-collapse-item v-for="group in pendingMonthGroups" :key="group.key" :name="group.key">
                  <template #title>📅 {{ group.key }} ({{ group.items.length }} 单)</template>
                  <div class="item-list">
                    <button
                      v-for="item in group.items"
                      :key="`pending-${item.id}`"
                      type="button"
                      class="item-btn"
                      :class="{ active: selectedType === 'contract' && selectedId === item.id }"
                      @click="selectContract(item.id)"
                    >
                      🏢 {{ item.customer }}
                      <div class="item-sub">{{ item.modelSummary }}</div>
                    </button>
                  </div>
                </el-collapse-item>
              </el-collapse>
              <div v-if="pendingMonthGroups.length === 0" class="filter-tip">暂无待审合同</div>
            </el-tab-pane>

            <el-tab-pane :label="`🎯 待规划 (${planningTotalQuick})`" name="planning" lazy>
              <el-input v-model="searchPlanning" placeholder="搜索待规划(合同/客户)" clearable />
              <div class="filter-tip">📊 共 {{ planningTotal }} 单，{{ planningMonthGroups.length }} 个月分组</div>
              <el-collapse v-model="expandedPlanning" class="month-list">
                <el-collapse-item v-for="group in planningMonthGroups" :key="group.key" :name="group.key">
                  <template #title>📅 {{ group.key }} ({{ group.items.length }} 单)</template>
                  <div class="item-list">
                    <button
                      v-for="item in group.items"
                      :key="`planning-${item.id}`"
                      type="button"
                      class="item-btn"
                      :class="{ active: selectedType === 'contract' && selectedId === item.id }"
                      @click="selectContract(item.id)"
                    >
                      🎯 {{ item.id }}
                      <div class="item-sub">{{ item.customer }} | {{ item.modelSummary }}</div>
                    </button>
                  </div>
                </el-collapse-item>
              </el-collapse>
              <div v-if="planningMonthGroups.length === 0" class="filter-tip">暂无待规划合同</div>
            </el-tab-pane>

            <el-tab-pane :label="`📦 现有订单 (${ordersTotal})`" name="orders" lazy>
              <el-input v-model="searchOrders" placeholder="搜索合同/订单/客户" clearable />
              <div class="filter-tip">📊 共 {{ ordersTotal }} 条，合同订单 {{ ordersContractTotal }} 条，独立订单 {{ ordersStandaloneTotal }} 条</div>
              <el-collapse v-model="expandedOrders" class="month-list">
                <el-collapse-item v-for="group in ordersMonthGroups" :key="`o-${group.key}`" :name="group.key">
                  <template #title>📅 {{ group.key }} ({{ group.items.length }} 单)</template>
                  <div class="item-list">
                    <button
                      v-for="item in group.items"
                      :key="`order-contract-${item.id}`"
                      type="button"
                      class="item-btn"
                      :class="{ active: selectedType === 'contract' && selectedId === item.id }"
                      @click="selectContract(item.id)"
                    >
                      📦 {{ item.id }}
                      <div class="item-sub">{{ item.customer }} {{ item.extra ? `| ${item.extra}` : '' }}</div>
                    </button>
                  </div>
                </el-collapse-item>
              </el-collapse>
              <div v-if="ordersMonthGroups.length === 0" class="filter-tip">暂无合同关联订单</div>
              <div class="orders-block-title">🧾 独立订单（无合同）</div>
              <div class="item-list">
                <button
                  v-for="item in ordersStandaloneList"
                  :key="`order-standalone-${item.id}`"
                  type="button"
                  class="item-btn"
                  :class="{ active: selectedType === 'order' && selectedId === item.id }"
                  @click="selectOrder(item.id)"
                >
                  📝 {{ item.id }}
                  <div class="item-sub">{{ item.customer }} {{ item.extra ? `| ${item.extra}` : '' }}</div>
                </button>
                <div v-if="ordersStandaloneList.length === 0" class="filter-tip">暂无独立订单</div>
              </div>
            </el-tab-pane>
          </el-tabs>
        </el-col>

        <el-col :span="16">
          <el-empty v-if="!selectedType" description="👈 请从左侧选择一个项目以查看详情" />

          <div v-else-if="selectedType === 'contract'">
            <div class="detail-head">
              <h3>📄 合同详情: {{ selectedId }}</h3>
            </div>
            <EditModePanel
              v-if="isPendingContract"
              :active="editMode"
              title="合同编辑模式"
              subtitle="可修改客户信息、交期与机型明细；保存后自动刷新列表"
              :disabled="saving"
              @toggle="editMode = !editMode"
            />

            <div class="detail-card">
              <template v-if="!editMode">
                <p><b>客户:</b> {{ contractFirst?.['客户名'] || '-' }} | <b>代理:</b> {{ contractFirst?.['代理商'] || '-' }}</p>
                <p><b>交期:</b> {{ contractFirst?.['要求交期'] || '-' }}</p>
                <p><b>备注:</b> {{ contractFirst?.['备注'] || '-' }}</p>
              </template>
              <template v-else>
                <el-row :gutter="10">
                  <el-col :span="8"><el-input v-model="editForm.customer" placeholder="客户名" /></el-col>
                  <el-col :span="8"><el-input v-model="editForm.agent" placeholder="代理商" /></el-col>
                  <el-col :span="8"><el-date-picker v-model="editForm.deadline" type="date" value-format="YYYY-MM-DD" /></el-col>
                </el-row>
              </template>
            </div>

            <el-table v-if="!editMode" :data="selectedContractRows" border stripe>
              <el-table-column prop="机型" label="机型" />
              <el-table-column prop="排产数量" label="排产数量" width="100" />
              <el-table-column prop="要求交期" label="要求交期" width="120" />
              <el-table-column prop="备注" label="备注" />
            </el-table>
            <el-table v-else :data="editForm.items" border stripe>
              <el-table-column label="机型">
                <template #default="scope"><el-input v-model="scope.row.机型" /></template>
              </el-table-column>
              <el-table-column label="数量" width="120">
                <template #default="scope"><el-input-number v-model="scope.row.排产数量" :min="1" /></template>
              </el-table-column>
              <el-table-column label="备注">
                <template #default="scope"><el-input v-model="scope.row.备注" /></template>
              </el-table-column>
              <el-table-column label="操作" width="90">
                <template #default="scope"><el-button type="danger" size="small" @click="removeEditItem(scope.$index)">删</el-button></template>
              </el-table-column>
            </el-table>

            <div v-if="editMode" class="ops-row">
              <el-button @click="addEditItem">+ 增加机型</el-button>
              <el-button type="primary" :loading="saving" @click="saveContractEdit">💾 保存修改</el-button>
            </div>

            <div v-if="isPendingContract" class="ops-row major">
              <el-button type="primary" :loading="saving" @click="approveToPlanning">🚀 前往规划</el-button>
              <el-button type="danger" :loading="saving" @click="rejectContract">❌ 驳回/取消</el-button>
            </div>

            <template v-if="showPlanningPanel">
              <el-divider />
              <h4>🎯 规划详情 (现货/批次分配)</h4>
              <div v-for="item in visibleContractPlanRows" :key="`plan-${item.key}`" class="plan-card">
                <div class="plan-title">机型：{{ item.model }}（需 {{ item.need }} 台）</div>
                <div class="plan-grid">
                  <div class="plan-left">
                    <el-input-number
                      :model-value="item.spotValue"
                      @update:model-value="(v) => updateContractSpot(item.row, v)"
                      :min="0"
                      :max="item.maxSpot"
                      :disabled="item.spotLocked"
                      controls-position="right"
                    />
                    <span class="plan-hint">现货可用 {{ item.spotAvailable }} 台</span>
                  </div>
                  <div class="plan-right">
                    <div
                      v-for="batch in item.batches"
                      :key="`batch-${item.key}-${batch.name}`"
                      class="batch-row"
                    >
                      <span class="batch-label">{{ batch.name }} (余{{ batch.count }})</span>
                      <el-input-number
                        :model-value="batch.value"
                        @update:model-value="(v) => updateContractBatch(item.row, batch.name, batch.count, v)"
                        :min="0"
                        :max="batch.max"
                        :disabled="batch.locked"
                        controls-position="right"
                      />
                    </div>
                  </div>
                </div>
              <el-progress
                :percentage="item.progress"
                :status="item.progress >= 100 ? undefined : 'warning'"
                :stroke-width="16"
                :text-inside="true"
                :format="() => item.progressText"
              />
              </div>
              <div v-if="hasMoreContractPlanRows" class="ops-row">
                <el-button size="small" @click="loadMoreContractPlanRows">加载更多机型</el-button>
              </div>
              <div class="ops-row">
                <el-button type="primary" :loading="savingPlan" @click="savePlanning">💾 保存规划 (Save Plan)</el-button>
                <el-button
                  v-if="canShowDirectAllocation"
                  type="success"
                  :loading="directAllocating"
                  @click="goDirectAllocation"
                >
                  🚚 {{ linkedOrderId ? '直通配货（已有关联订单）' : '直通配货（自动生成销售订单）' }}
                </el-button>
              </div>
            </template>

            <template v-if="isContractSelected">
              <el-divider />
              <h4>📎 合同附件管理</h4>
              <el-upload
                :show-file-list="false"
                :auto-upload="false"
                :on-change="onPickFile"
              >
                <el-button type="primary" size="small">选择附件</el-button>
              </el-upload>
              <el-button
                size="small"
                style="margin-left: 8px"
                :disabled="!pickedFile"
                :loading="uploading"
                @click="uploadFile"
              >
                上传
              </el-button>
              <el-table :data="sortedContractFiles" border stripe size="small" style="margin-top: 8px" empty-text="暂无附件">
                <el-table-column prop="file_name" label="文件名" />
                <el-table-column prop="uploader" label="上传人" width="120" />
                <el-table-column prop="upload_time" label="上传时间" width="170" />
                <el-table-column label="操作" width="220">
                  <template #default="scope">
                    <el-button size="small" @click="downloadFile(scope.row.file_name)">下载</el-button>
                    <el-button size="small" @click="previewFile(scope.row.file_name)">预览</el-button>
                    <el-button type="danger" size="small" @click="deleteFile(scope.row.file_name)">删除</el-button>
                  </template>
                </el-table-column>
              </el-table>
            </template>

            <template v-if="showContractPreviewPanel">
              <el-divider />
              <h4>👁 合同预览</h4>
              <div v-if="!previewState.fileName" class="preview-empty">请选择附件并点击“预览”</div>
              <div v-else class="preview-wrap">
                <div class="preview-head">正在预览：{{ previewState.fileName }}</div>
                <iframe
                  v-if="previewState.type === 'url' && previewState.ext === '.pdf'"
                  :src="previewState.url"
                  class="preview-frame"
                />
                <img
                  v-else-if="previewState.type === 'url'"
                  :src="previewState.url"
                  class="preview-image"
                />
                <div
                  v-else-if="previewState.type === 'html'"
                  class="preview-html"
                  v-html="previewState.html"
                />
                <div v-else class="preview-empty">当前文件暂不支持在线预览</div>
              </div>
            </template>
          </div>

          <div v-else>
            <div class="detail-head">
              <h3>🧾 独立订单详情: {{ selectedId }}</h3>
            </div>
            <div class="detail-card">
              <p><b>📝 独立订单规划:</b> {{ selectedId }}</p>
              <p><b>客户:</b> {{ selectedOrderFirst?.['客户名'] || '-' }} | <b>代理:</b> {{ selectedOrderFirst?.['代理商'] || '-' }}</p>
              <p><b>发货时间:</b> {{ selectedOrderFirst?.['发货时间'] || '-' }} | <b>备注:</b> {{ selectedOrderFirst?.['备注'] || '-' }}</p>
            </div>

            <div v-for="item in visibleOrderPlanRows" :key="`order-plan-${selectedId}-${item.key}`" class="plan-card">
              <div class="plan-title">
                ⏳ {{ item.model }}（需 {{ item.need }} 台）
              </div>
              <div class="plan-hint" style="margin-bottom: 8px">ℹ 实际未配货 {{ item.allocated }} 台</div>
              <div class="plan-grid">
                <div class="plan-left">
                  <div>现货 (余{{ item.spotAvailable }})</div>
                  <el-input-number
                    :model-value="item.spotValue"
                    @update:model-value="(v) => updateOrderSpot(item.row, v)"
                    :min="0"
                    :max="item.maxSpot"
                    :disabled="item.spotLocked"
                    controls-position="right"
                  />
                  <span class="plan-hint">现货可用 {{ item.spotAvailable }} 台</span>
                </div>
                <div class="plan-right">
                  <template v-if="item.batches.length > 0">
                    <div
                      v-for="batch in item.batches"
                      :key="`order-batch-${item.key}-${batch.name}`"
                      class="batch-row"
                    >
                      <span class="batch-label">{{ batch.name }} (余{{ batch.count }})</span>
                      <el-input-number
                        :model-value="batch.value"
                        @update:model-value="(v) => updateOrderBatch(item.row, batch.name, batch.count, v)"
                        :min="0"
                        :max="batch.max"
                        :disabled="batch.locked"
                        controls-position="right"
                      />
                    </div>
                  </template>
                  <div v-else class="plan-hint">无批次库存</div>
                </div>
              </div>
              <el-progress
                :percentage="item.progress"
                :status="item.progress >= 100 ? undefined : 'warning'"
                :stroke-width="16"
                :text-inside="true"
                :format="() => item.progressText"
              />
            </div>
            <div v-if="hasMoreOrderPlanRows" class="ops-row">
              <el-button size="small" @click="loadMoreOrderPlanRows">加载更多机型</el-button>
            </div>
            <div class="ops-row major">
              <el-button type="danger" :loading="savingPlan" @click="saveOrderPlanning">💾 保存订单规划</el-button>
            </div>
          </div>
        </el-col>
      </el-row>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import { apiDelete, apiGet, apiPost, apiPut, getApiErrorMessage } from '../utils/request'
import PageSkeleton from '../components/PageSkeleton.vue'
import EditModePanel from '../components/EditModePanel.vue'
import { useFormSubmit } from '../composables/useFormSubmit'
import { usePlanningStore } from '../store/planning'
import { formatYearMonth, toTimestampSafe } from '../utils/compat'
type FileListResponse = { data: any[] }
type PreviewResponse = { type?: '' | 'url' | 'html'; url?: string; html?: string; ext?: string }

type ContractListItem = { id: string; customer: string; modelSummary: string; extra?: string }
type OrderListItem = { id: string; customer: string; extra?: string; kind: 'order' | 'contract' }

const activeTab = ref('pending')
const searchPending = ref('')
const searchPlanning = ref('')
const searchOrders = ref('')
const searchPendingDebounced = ref('')
const searchPlanningDebounced = ref('')
const searchOrdersDebounced = ref('')
let searchPendingTimer: number | null = null
let searchPlanningTimer: number | null = null
let searchOrdersTimer: number | null = null
const loading = ref(false)
const loadError = ref('')
const loadedOnce = ref(false)
const showSkeletonDelayed = ref(false)
let skeletonTimer: number | null = null
const saving = ref(false)
const uploading = ref(false)
const planList = ref<any[]>([])
const orderList = ref<any[]>([])
const inventoryList = ref<any[]>([])
const selectedType = ref<'contract' | 'order' | ''>('')
const selectedId = ref('')
const expandedPending = ref<string[]>([])
const expandedPlanning = ref<string[]>([])
const expandedOrders = ref<string[]>([])
const editMode = ref(false)
const contractFiles = ref<any[]>([])
const pickedFile = ref<File | null>(null)
const savingPlan = ref(false)
const directAllocating = ref(false)
const PLAN_RENDER_STEP = 8
const contractPlanRenderCount = ref(PLAN_RENDER_STEP)
const orderPlanRenderCount = ref(PLAN_RENDER_STEP)
const { submitWithLock } = useFormSubmit()
const planningStore = usePlanningStore()
const router = useRouter()
const planDraft = reactive<Record<string, { spot: number; batches: Record<string, number> }>>({})
const orderPlanDraft = reactive<Record<string, { spot: number; batches: Record<string, number> }>>({})
const orderAllocations = ref<any[]>([])
const previewState = reactive({
  fileName: '',
  type: '' as '' | 'url' | 'html',
  url: '',
  html: '',
  ext: '',
})

const editForm = reactive({
  customer: '',
  agent: '',
  deadline: '',
  items: [] as Array<{ 机型: string; 排产数量: number; 备注: string }>,
})

const hasRenderableData = computed(
  () => planList.value.length > 0 || orderList.value.length > 0 || inventoryList.value.length > 0,
)

const fetchData = async (force = false) => {
  // 若 store 中已有快照，先回填，避免页面先出现整块骨架
  if (!hasRenderableData.value) {
    if (planningStore.planList.length || planningStore.orderList.length || planningStore.inventoryList.length) {
      planList.value = [...planningStore.planList]
      orderList.value = [...planningStore.orderList]
      inventoryList.value = [...planningStore.inventoryList]
      loadedOnce.value = true
    }
  }

  if (skeletonTimer) window.clearTimeout(skeletonTimer)
  showSkeletonDelayed.value = false
  loading.value = true
  loadError.value = ''
  if (!hasRenderableData.value) {
    skeletonTimer = window.setTimeout(() => {
      showSkeletonDelayed.value = true
    }, 180)
  }
  try {
    const data = await planningStore.fetchPlanningDashboard(force)
    planList.value = data.planList
    orderList.value = data.orderList
    inventoryList.value = data.inventoryList
  } catch (error) {
    console.error('Fetch planning data failed', error)
    loadError.value = getApiErrorMessage(error) || '读取统筹数据失败'
    ElMessage.error(loadError.value)
  } finally {
    if (skeletonTimer) {
      window.clearTimeout(skeletonTimer)
      skeletonTimer = null
    }
    showSkeletonDelayed.value = false
    loading.value = false
    loadedOnce.value = true
  }
}
const retryFetchData = () => {
  void fetchData(true)
}

watch(searchPending, (v) => {
  if (searchPendingTimer) window.clearTimeout(searchPendingTimer)
  searchPendingTimer = window.setTimeout(() => {
    searchPendingDebounced.value = v
  }, 180)
})
watch(searchPlanning, (v) => {
  if (searchPlanningTimer) window.clearTimeout(searchPlanningTimer)
  searchPlanningTimer = window.setTimeout(() => {
    searchPlanningDebounced.value = v
  }, 180)
})
watch(searchOrders, (v) => {
  if (searchOrdersTimer) window.clearTimeout(searchOrdersTimer)
  searchOrdersTimer = window.setTimeout(() => {
    searchOrdersDebounced.value = v
  }, 180)
})

const monthKey = (dateStr: string) => {
  return formatYearMonth(dateStr, 'Unknown')
}

const groupByMonth = <T extends { month: string }>(rows: T[]) => {
  const map = new Map<string, T[]>()
  for (const r of rows) {
    if (!map.has(r.month)) map.set(r.month, [])
    map.get(r.month)!.push(r)
  }
  const keys = Array.from(map.keys()).sort()
  return keys.map((k) => ({ key: k, items: map.get(k)! }))
}

const uniqueContracts = (rows: any[]) => {
  const map = new Map<string, any[]>()
  for (const row of rows) {
    const id = String(row['合同号'] || '')
    if (!id) continue
    if (!map.has(id)) map.set(id, [])
    map.get(id)!.push(row)
  }
  return map
}

const planRowsByStatus = computed(() => {
  const pending: any[] = []
  const planning: any[] = []
  const done: any[] = []
  for (const r of planList.value) {
    const s = String(r['状态'] || '')
    if (s === '未下单') pending.push(r)
    else if (s === '待规划') planning.push(r)
    else if (s === '已规划' || s === '已转订单' || s === '已下单' || s === '已配货') done.push(r)
  }
  return { pending, planning, done }
})

const pendingTotalQuick = computed(() => {
  const term = searchPendingDebounced.value.trim().toLowerCase()
  const set = new Set<string>()
  for (const r of planRowsByStatus.value.pending) {
    const id = String(r['合同号'] || '')
    if (!id || set.has(id)) continue
    if (term) {
      const customer = String(r['客户名'] || '-').toLowerCase()
      if (!id.toLowerCase().includes(term) && !customer.includes(term)) continue
    }
    set.add(id)
  }
  return set.size
})

const planningTotalQuick = computed(() => {
  const term = searchPlanningDebounced.value.trim().toLowerCase()
  const set = new Set<string>()
  for (const r of planRowsByStatus.value.planning) {
    const id = String(r['合同号'] || '')
    if (!id || set.has(id)) continue
    if (term) {
      const customer = String(r['客户名'] || '-').toLowerCase()
      if (!id.toLowerCase().includes(term) && !customer.includes(term)) continue
    }
    set.add(id)
  }
  return set.size
})

const pendingMonthGroups = computed(() => {
  const term = searchPendingDebounced.value.trim().toLowerCase()
  const groups = uniqueContracts(planRowsByStatus.value.pending)
  const list: Array<ContractListItem & { month: string }> = []
  for (const [id, rs] of groups.entries()) {
    const first = rs[0]
    const customer = String(first['客户名'] || '-')
    if (term && !id.toLowerCase().includes(term) && !customer.toLowerCase().includes(term)) continue
    const modelSummary = rs.map((x) => `${x['机型']} x${x['排产数量']}`).join(' / ')
    list.push({ id, customer, modelSummary, month: monthKey(String(first['要求交期'] || '')) })
  }
  const grouped = groupByMonth(list)
  if (grouped.length > 0 && !pendingCollapseInitialized.value) {
    expandedPending.value = [grouped[0].key]
    pendingCollapseInitialized.value = true
  }
  return grouped
})
const pendingTotal = computed(() => pendingMonthGroups.value.reduce((sum, g) => sum + g.items.length, 0))

const planningMonthGroups = computed(() => {
  const term = searchPlanningDebounced.value.trim().toLowerCase()
  const groups = uniqueContracts(planRowsByStatus.value.planning)
  const list: Array<ContractListItem & { month: string }> = []
  for (const [id, rs] of groups.entries()) {
    const first = rs[0]
    const customer = String(first['客户名'] || '-')
    if (term && !id.toLowerCase().includes(term) && !customer.toLowerCase().includes(term)) continue
    const modelSummary = rs.map((x) => String(x['机型'] || '')).join(', ')
    list.push({ id, customer, modelSummary, month: monthKey(String(first['要求交期'] || '')) })
  }
  const grouped = groupByMonth(list)
  if (grouped.length > 0 && !planningCollapseInitialized.value) {
    expandedPlanning.value = [grouped[0].key]
    planningCollapseInitialized.value = true
  }
  return grouped
})
const planningTotal = computed(() => planningMonthGroups.value.reduce((sum, g) => sum + g.items.length, 0))

const pendingCollapseInitialized = ref(false)
const planningCollapseInitialized = ref(false)
const ordersCollapseInitialized = ref(false)

const shippedCountByOrder = computed(() => {
  const map = new Map<string, number>()
  for (const i of inventoryList.value) {
    if (String(i['状态'] || '') !== '已出库') continue
    const oid = String(i['占用订单号'] || '')
    if (!oid) continue
    map.set(oid, (map.get(oid) || 0) + 1)
  }
  return map
})

// 辅助函数：判断订单是否已完结（已出库数量 >= 需求数量）
const isOrderCompleted = (oid: string, reqQty: number): boolean => {
  if (!oid || reqQty <= 0) return false
  const shippedCount = shippedCountByOrder.value.get(oid) || 0
  return shippedCount >= reqQty
}

const buildOrdersData = () => {
  const term = searchOrdersDebounced.value.trim().toLowerCase()
  const doneGroups = uniqueContracts(planRowsByStatus.value.done)
  const doneItems: Array<OrderListItem & { month: string }> = []
  const doneOrderIdSet = new Set<string>()

  // 过滤掉已完结的合同订单
  for (const [id, rs] of doneGroups.entries()) {
    const first = rs[0]
    const oid = String(first['订单号'] || '')
    // 如果有关联订单，检查是否已完结
    if (oid) {
      const reqQty = toInt(first['排产数量'] || 0)
      if (isOrderCompleted(oid, reqQty)) continue
    }
    const customer = String(first['客户名'] || '-')
    const hit = `${id} ${customer} ${oid}`.toLowerCase()
    if (term && !hit.includes(term)) continue
    doneItems.push({ id, customer, extra: oid, kind: 'contract', month: monthKey(String(first['要求交期'] || '')) })
    if (oid) doneOrderIdSet.add(oid)
  }

  const activeOrders = orderList.value.filter((o: any) => {
    const s = String(o.status || '')
    return ['active', 'ready', 'packed'].includes(s)
  })
  const manualOrderItems: Array<OrderListItem> = []
  for (const o of activeOrders) {
    const oid = String(o['订单号'] || '')
    if (!oid) continue
    if (doneOrderIdSet.has(oid)) continue
    // 过滤掉已完结的独立订单
    const reqQty = toInt(o['需求数量'] || 0)
    if (isOrderCompleted(oid, reqQty)) continue
    const customer = String(o['客户名'] || '-')
    const hit = `${oid} ${customer}`.toLowerCase()
    if (term && !hit.includes(term)) continue
    manualOrderItems.push({ id: oid, customer, extra: String(o['需求数量'] || ''), kind: 'order' })
  }

  const grouped = groupByMonth(doneItems)
  if (grouped.length > 0 && !ordersCollapseInitialized.value) {
    expandedOrders.value = [grouped[0].key]
    ordersCollapseInitialized.value = true
  }
  return { grouped, manualOrderItems }
}

const ordersData = computed(() => buildOrdersData())
const ordersMonthGroups = computed(() => ordersData.value.grouped)
const ordersStandaloneList = computed(() => ordersData.value.manualOrderItems)
const ordersContractTotal = computed(() => ordersMonthGroups.value.reduce((sum, g) => sum + g.items.length, 0))
const ordersStandaloneTotal = computed(() => ordersStandaloneList.value.length)
const ordersTotal = computed(() => ordersContractTotal.value + ordersStandaloneTotal.value)

const selectContract = (id: string) => {
  selectedType.value = 'contract'
  selectedId.value = id
}

const selectOrder = (id: string) => {
  selectedType.value = 'order'
  selectedId.value = id
}

const selectedContractRows = computed(() => planList.value.filter((r: any) => String(r['合同号'] || '') === selectedId.value))
const selectedOrderRows = computed(() => orderList.value.filter((r: any) => String(r['订单号'] || '') === selectedId.value))
const expandedOrderPlanRows = computed(() => {
  const rows: any[] = []
  for (const orderRow of selectedOrderRows.value) {
    const rawModel = String(orderRow['需求机型'] || '')
    const totalNeed = Math.max(1, toInt(orderRow['需求数量']))
    const parts = rawModel.split(/[;；/,，]/g).map((s) => s.trim()).filter(Boolean)
    const parsed: Array<{ model: string; qty: number; high: boolean }> = []
    for (const p of parts) {
      // 支持 "FR-400XS(PRO):1" / "FR-400XS(PRO)x1" / "FR-400XS(PRO)×1"
      const m1 = p.match(/[:：]\s*(\d+)\s*$/)
      const m2 = p.match(/[x×]\s*(\d+)\s*$/i)
      const qty = m1 ? toInt(m1[1]) : m2 ? toInt(m2[1]) : 1
      const high = String(p).includes('加高') || String(rawModel).includes('加高')
      const model = normalizeModel(
        p.replace(/[:：]\s*\d+\s*$/, '').replace(/[x×]\s*\d+\s*$/i, '').replace(/\[[^\]]*]/g, '').trim(),
      )
      if (model) parsed.push({ model, qty: Math.max(1, qty), high })
    }
    if (parsed.length === 0) {
      parsed.push({ model: normalizeModel(rawModel), qty: totalNeed, high: String(rawModel).includes('加高') })
    }
    const sumQty = parsed.reduce((s, x) => s + x.qty, 0)
    // 若拆分数量异常，退回总数量，避免规划总量与订单不一致
    if (sumQty <= 0) parsed[0].qty = totalNeed
    parsed.forEach((p, idx) => {
      rows.push({
        ...orderRow,
        _planModel: p.model,
        _planNeed: p.qty,
        _planHigh: p.high,
        _planIdx: idx,
      })
    })
  }
  return rows
})
const contractFirst = computed(() => selectedContractRows.value[0] || null)
const selectedOrderFirst = computed(() => selectedOrderRows.value[0] || null)
const sortedContractFiles = computed(() => {
  return [...contractFiles.value].sort((a: any, b: any) => {
    const ta = toTimestampSafe(String(a?.upload_time || ''), 0)
    const tb = toTimestampSafe(String(b?.upload_time || ''), 0)
    return tb - ta
  })
})
const showPlanningPanel = computed(() => {
  const s = String(contractFirst.value?.['状态'] || '')
  return ['待规划', '已规划', '已转订单', '已下单', '已配货'].includes(s)
})
const isContractSelected = computed(() => selectedType.value === 'contract')
const isPendingContract = computed(() => activeTab.value === 'pending' && selectedType.value === 'contract')
const showContractPreviewPanel = computed(() => isContractSelected.value)
const showInitialSkeleton = computed(
  () => showSkeletonDelayed.value && loading.value && !loadError.value && !hasRenderableData.value,
)
const contractPlanRowsView = computed(() => {
  return selectedContractRows.value.map((row: any) => {
    const key = String(row._idx)
    const draft = planDraft[key] || { spot: 0, batches: {} }
    const batchesRaw = availableBatches(row)
    const progress = rowProgress(row)
    return {
      key,
      row,
      model: String(row['机型'] || '-'),
      need: Math.max(1, toInt(row['排产数量'])),
      spotValue: toInt(draft.spot),
      spotAvailable: availableSpot(row),
      maxSpot: maxSpotForContractRow(row),
      spotLocked: isContractSpotLocked(row),
      batches: batchesRaw.map((b) => ({
        name: b.name,
        count: b.count,
        value: toInt(draft.batches?.[b.name] || 0),
        max: maxBatchForContractRow(row, b.name, b.count),
        locked: isContractBatchLocked(row, b.name, b.count),
      })),
      progress,
      progressText: rowProgressText(row),
    }
  })
})
const visibleContractPlanRows = computed(() => contractPlanRowsView.value.slice(0, contractPlanRenderCount.value))
const hasMoreContractPlanRows = computed(() => contractPlanRowsView.value.length > contractPlanRenderCount.value)
const loadMoreContractPlanRows = () => {
  contractPlanRenderCount.value += PLAN_RENDER_STEP
}
const orderPlanRowsView = computed(() => {
  return expandedOrderPlanRows.value.map((row: any) => {
    const key = orderRowKey(row)
    const draft = orderPlanDraft[key] || { spot: 0, batches: {} }
    const batchesRaw = availableOrderBatches(row)
    const progress = orderRowProgress(row)
    return {
      key,
      row,
      model: modelOfOrderRow(row) || '-',
      need: needOfOrderRow(row),
      allocated: allocatedCountForOrderRow(row),
      spotValue: toInt(draft.spot),
      spotAvailable: availableOrderSpot(row),
      maxSpot: maxSpotForOrderRow(row),
      spotLocked: isOrderSpotLocked(row),
      batches: batchesRaw.map((b) => ({
        name: b.name,
        count: b.count,
        value: toInt(draft.batches?.[b.name] || 0),
        max: maxBatchForOrderRow(row, b.name, b.count),
        locked: isOrderBatchLocked(row, b.name, b.count),
      })),
      progress,
      progressText: orderRowProgressText(row),
    }
  })
})
const visibleOrderPlanRows = computed(() => orderPlanRowsView.value.slice(0, orderPlanRenderCount.value))
const hasMoreOrderPlanRows = computed(() => orderPlanRowsView.value.length > orderPlanRenderCount.value)
const loadMoreOrderPlanRows = () => {
  orderPlanRenderCount.value += PLAN_RENDER_STEP
}
const linkedOrderId = computed(() => {
  const oid = String(contractFirst.value?.['订单号'] || '').trim()
  return oid
})
const contractPlanSaved = computed(() => {
  const s = String(contractFirst.value?.['状态'] || '')
  return ['已规划', '已转订单', '已下单', '已配货'].includes(s)
})
const contractPlanReady = computed(() => {
  if (!isContractSelected.value) return false
  if (selectedContractRows.value.length === 0) return false
  return selectedContractRows.value.every((r: any) => rowProgress(r) >= 100)
})
const canShowDirectAllocation = computed(() => contractPlanSaved.value && contractPlanReady.value)

const loadEditForm = () => {
  const first = contractFirst.value
  if (!first) return
  editForm.customer = String(first['客户名'] || '')
  editForm.agent = String(first['代理商'] || '')
  editForm.deadline = String(first['要求交期'] || '')
  editForm.items = selectedContractRows.value.map((r: any) => ({
    机型: String(r['机型'] || ''),
    排产数量: Number(r['排产数量'] || 1) || 1,
    备注: String(r['备注'] || ''),
  }))
}
const orderRowKey = (row: any) =>
  `${String(row['订单号'] || '')}::${String(row._planModel || row['需求机型'] || '')}::${String(row._planIdx ?? 0)}`
const modelOfOrderRow = (row: any) => String(row._planModel || row['需求机型'] || '')
const needOfOrderRow = (row: any) => Math.max(1, toInt(row._planNeed ?? row['需求数量']))
const availableOrderSpot = (row: any) => {
  return inventoryIndex.value.spotCountByKey.get(modelKeyFromOrderRow(row)) || 0
}
const availableOrderBatches = (row: any) => {
  const map = inventoryIndex.value.batchCountByKey.get(modelKeyFromOrderRow(row)) || new Map<string, number>()
  return Array.from(map.entries()).map(([name, count]) => ({ name, count }))
}
const allocatedCountForOrderRow = (row: any) => {
  const key = modelKeyFromOrderRow(row)
  return orderAllocationsByKey.value.get(key) || 0
}
const initOrderPlanDraft = () => {
  for (const row of expandedOrderPlanRows.value) {
    const key = orderRowKey(row)
    if (!orderPlanDraft[key]) orderPlanDraft[key] = { spot: 0, batches: {} }
  }
}
const getOrderDraft = (row: any) => {
  const key = orderRowKey(row)
  if (!orderPlanDraft[key]) orderPlanDraft[key] = { spot: 0, batches: {} }
  return orderPlanDraft[key]
}
const updateOrderSpot = (row: any, value: number | undefined) => {
  getOrderDraft(row).spot = Math.min(toInt(value || 0), maxSpotForOrderRow(row))
}
const updateOrderBatch = (row: any, batchName: string, batchCount: number, value: number | undefined) => {
  getOrderDraft(row).batches[batchName] = Math.min(
    toInt(value || 0),
    maxBatchForOrderRow(row, batchName, batchCount),
  )
}
const contractAllocatedTotal = (row: any) => {
  const key = String(row._idx)
  const draft = planDraft[key] || { spot: 0, batches: {} }
  let total = toInt(draft.spot)
  for (const v of Object.values(draft.batches || {})) total += toInt(v)
  return total
}
const maxSpotForContractRow = (row: any) => {
  const key = String(row._idx)
  const draft = planDraft[key] || { spot: 0, batches: {} }
  const need = Math.max(1, toInt(row['排产数量']))
  const other = contractAllocatedTotal(row) - toInt(draft.spot)
  const quota = Math.max(0, need - other)
  return Math.min(availableSpot(row), quota)
}
const maxBatchForContractRow = (row: any, batchName: string, batchCount: number) => {
  const key = String(row._idx)
  const draft = planDraft[key] || { spot: 0, batches: {} }
  const current = toInt(draft.batches?.[batchName] || 0)
  const need = Math.max(1, toInt(row['排产数量']))
  const other = contractAllocatedTotal(row) - current
  const quota = Math.max(0, need - other)
  return Math.min(batchCount, quota)
}
const isContractSpotLocked = (row: any) => {
  const current = toInt(getContractDraft(row).spot)
  return current <= 0 && maxSpotForContractRow(row) <= 0
}
const isContractBatchLocked = (row: any, batchName: string, batchCount: number) => {
  const current = toInt(getContractDraft(row).batches[batchName] || 0)
  return current <= 0 && maxBatchForContractRow(row, batchName, batchCount) <= 0
}
const orderAllocatedTotal = (row: any) => {
  const key = orderRowKey(row)
  const draft = orderPlanDraft[key] || { spot: 0, batches: {} }
  let total = toInt(draft.spot)
  for (const v of Object.values(draft.batches || {})) total += toInt(v)
  return total
}
const maxSpotForOrderRow = (row: any) => {
  const key = orderRowKey(row)
  const draft = orderPlanDraft[key] || { spot: 0, batches: {} }
  const need = needOfOrderRow(row)
  const other = orderAllocatedTotal(row) - toInt(draft.spot)
  const quota = Math.max(0, need - other)
  return Math.min(availableOrderSpot(row), quota)
}
const maxBatchForOrderRow = (row: any, batchName: string, batchCount: number) => {
  const key = orderRowKey(row)
  const draft = orderPlanDraft[key] || { spot: 0, batches: {} }
  const current = toInt(draft.batches?.[batchName] || 0)
  const need = needOfOrderRow(row)
  const other = orderAllocatedTotal(row) - current
  const quota = Math.max(0, need - other)
  return Math.min(batchCount, quota)
}
const isOrderSpotLocked = (row: any) => {
  const current = toInt(getOrderDraft(row).spot)
  return current <= 0 && maxSpotForOrderRow(row) <= 0
}
const isOrderBatchLocked = (row: any, batchName: string, batchCount: number) => {
  const current = toInt(getOrderDraft(row).batches[batchName] || 0)
  return current <= 0 && maxBatchForOrderRow(row, batchName, batchCount) <= 0
}
const orderRowProgress = (row: any) => {
  const key = orderRowKey(row)
  const draft = orderPlanDraft[key] || { spot: 0, batches: {} }
  const need = needOfOrderRow(row)
  let allocated = toInt(draft.spot)
  for (const v of Object.values(draft.batches || {})) allocated += toInt(v)
  return Math.min(100, Math.round((allocated / need) * 100))
}
const orderRowProgressText = (row: any) => {
  const key = orderRowKey(row)
  const draft = orderPlanDraft[key] || { spot: 0, batches: {} }
  const need = needOfOrderRow(row)
  let allocated = toInt(draft.spot)
  for (const v of Object.values(draft.batches || {})) allocated += toInt(v)
  return `${Math.min(allocated, need)}/${need}`
}
const loadOrderAllocations = async () => {
  if (selectedType.value !== 'order' || !selectedId.value) {
    orderAllocations.value = []
    return
  }
  try {
    const res = await apiGet<{ data: any[] }>(`/planning/orders/${encodeURIComponent(selectedId.value)}/allocations`)
    orderAllocations.value = res.data || []
  } catch {
    orderAllocations.value = []
  }
}

const toInt = (v: any) => {
  const n = Number(v)
  return Number.isFinite(n) ? Math.max(0, Math.floor(n)) : 0
}

const isHighModel = (model: string) => String(model || '').includes('(加高)')
const normalizeModel = (model: string) => String(model || '').replace('(加高)', '').trim()
const inventoryModelKey = (real: string, high: boolean) => `${real}::${high ? 1 : 0}`
const modelKeyFromRowModel = (model: string) => inventoryModelKey(normalizeModel(model), isHighModel(model))
const modelKeyFromOrderRow = (row: any) =>
  inventoryModelKey(String(row._planModel || modelOfOrderRow(row) || ''), Boolean(row._planHigh))

const inventoryIndex = computed(() => {
  const spotCountByKey = new Map<string, number>()
  const batchCountByKey = new Map<string, Map<string, number>>()
  const spotSerialsByKey = new Map<string, string[]>()
  const batchSerialsByKey = new Map<string, Map<string, string[]>>()

  for (const i of inventoryList.value) {
    if (String(i['占用订单号'] || '') !== '') continue
    const real = normalizeModel(String(i['机型'] || ''))
    if (!real) continue
    const high = String(i['机台备注/配置'] || '').includes('加高')
    const key = inventoryModelKey(real, high)
    const status = String(i['状态'] || '')
    const serial = String(i['流水号'] || '').trim()

    if (status === '库存中') {
      spotCountByKey.set(key, (spotCountByKey.get(key) || 0) + 1)
      if (serial) {
        if (!spotSerialsByKey.has(key)) spotSerialsByKey.set(key, [])
        spotSerialsByKey.get(key)!.push(serial)
      }
      continue
    }

    if (status === '待入库') {
      const batch = String(i['批次号'] || '无批次').trim() || '无批次'
      if (!batchCountByKey.has(key)) batchCountByKey.set(key, new Map())
      const bc = batchCountByKey.get(key)!
      bc.set(batch, (bc.get(batch) || 0) + 1)

      if (serial) {
        if (!batchSerialsByKey.has(key)) batchSerialsByKey.set(key, new Map())
        const bs = batchSerialsByKey.get(key)!
        if (!bs.has(batch)) bs.set(batch, [])
        bs.get(batch)!.push(serial)
      }
    }
  }

  return { spotCountByKey, batchCountByKey, spotSerialsByKey, batchSerialsByKey }
})
const orderAllocationsByKey = computed(() => {
  const map = new Map<string, number>()
  for (const i of orderAllocations.value) {
    const real = normalizeModel(String(i['机型'] || ''))
    if (!real) continue
    const high = String(i['机台备注/配置'] || '').includes('加高')
    const key = inventoryModelKey(real, high)
    map.set(key, (map.get(key) || 0) + 1)
  }
  return map
})

const availableSpot = (row: any) => {
  return inventoryIndex.value.spotCountByKey.get(modelKeyFromRowModel(String(row['机型'] || ''))) || 0
}

const availableBatches = (row: any) => {
  const key = modelKeyFromRowModel(String(row['机型'] || ''))
  const map = inventoryIndex.value.batchCountByKey.get(key) || new Map<string, number>()
  return Array.from(map.entries()).map(([name, count]) => ({ name, count }))
}

const initPlanDraft = () => {
  for (const row of selectedContractRows.value) {
    const key = String(row._idx)
    const src = (row['指定批次/来源'] || {}) as Record<string, any>
    const batches: Record<string, number> = {}
    let spot = 0
    for (const [k, v] of Object.entries(src)) {
      const qty = toInt(v)
      if (qty <= 0) continue
      if (k === '现货(Spot)') spot = qty
      else batches[k] = qty
    }
    planDraft[key] = { spot, batches }
  }
}
const getContractDraft = (row: any) => {
  const key = String(row._idx)
  if (!planDraft[key]) planDraft[key] = { spot: 0, batches: {} }
  return planDraft[key]
}
const updateContractSpot = (row: any, value: number | undefined) => {
  getContractDraft(row).spot = Math.min(toInt(value || 0), maxSpotForContractRow(row))
}
const updateContractBatch = (row: any, batchName: string, batchCount: number, value: number | undefined) => {
  getContractDraft(row).batches[batchName] = Math.min(
    toInt(value || 0),
    maxBatchForContractRow(row, batchName, batchCount),
  )
}

const rowProgress = (row: any) => {
  const key = String(row._idx)
  const need = Math.max(1, toInt(row['排产数量']))
  const draft = planDraft[key] || { spot: 0, batches: {} }
  let total = toInt(draft.spot)
  for (const v of Object.values(draft.batches || {})) total += toInt(v)
  return Math.min(100, Math.round((total / need) * 100))
}
const rowProgressText = (row: any) => {
  const key = String(row._idx)
  const need = Math.max(1, toInt(row['排产数量']))
  const draft = planDraft[key] || { spot: 0, batches: {} }
  let total = toInt(draft.spot)
  for (const v of Object.values(draft.batches || {})) total += toInt(v)
  return `${Math.min(total, need)}/${need}`
}

const addEditItem = () => {
  editForm.items.push({ 机型: '', 排产数量: 1, 备注: '' })
}

const removeEditItem = (idx: number) => {
  editForm.items.splice(idx, 1)
}

const saveContractEdit = async () => {
  if (!selectedId.value) return
  await submitWithLock(saving, async () => {
    await apiPut(`/planning/contract/${encodeURIComponent(selectedId.value)}`, {
      客户名: editForm.customer,
      代理商: editForm.agent,
      要求交期: editForm.deadline,
      items: editForm.items,
    })
    await fetchData(true)
    editMode.value = false
  }, { successMessage: '合同修改已保存', errorMessage: '保存失败' })
}
const saveOrderPlanning = async () => {
  if (!selectedId.value) return
  const pickSerials: string[] = []
  const spotPoolByKey = new Map<string, string[]>()
  for (const [k, list] of inventoryIndex.value.spotSerialsByKey.entries()) {
    spotPoolByKey.set(k, [...list])
  }
  const batchPoolByKey = new Map<string, Map<string, string[]>>()
  for (const [k, bm] of inventoryIndex.value.batchSerialsByKey.entries()) {
    const copied = new Map<string, string[]>()
    for (const [b, list] of bm.entries()) copied.set(b, [...list])
    batchPoolByKey.set(k, copied)
  }

  for (const row of expandedOrderPlanRows.value) {
    const key = orderRowKey(row)
    const modelKey = modelKeyFromOrderRow(row)
    const draft = orderPlanDraft[key] || { spot: 0, batches: {} }
    const need = needOfOrderRow(row)
    let total = toInt(draft.spot)
    for (const v of Object.values(draft.batches || {})) total += toInt(v)
    if (total > need) {
      ElMessage.error(`机型 ${modelOfOrderRow(row)} 分配超量：${total}/${need}`)
      return
    }
    if (total <= 0) {
      ElMessage.error(`机型 ${modelOfOrderRow(row)} 还未分配来源`)
      return
    }
    const spotCandidates = spotPoolByKey.get(modelKey) || []
    if (toInt(draft.spot) > spotCandidates.length) {
      ElMessage.error(`机型 ${modelOfOrderRow(row)} 现货不足`)
      return
    }
    pickSerials.push(...spotCandidates.splice(0, toInt(draft.spot)))
    for (const [batchName, batchQtyRaw] of Object.entries(draft.batches || {})) {
      const batchQty = toInt(batchQtyRaw)
      if (batchQty <= 0) continue
      const batchCandidates = batchPoolByKey.get(modelKey)?.get(batchName) || []
      if (batchQty > batchCandidates.length) {
        ElMessage.error(`机型 ${modelOfOrderRow(row)} 批次 ${batchName} 库存不足`)
        return
      }
      pickSerials.push(...batchCandidates.splice(0, batchQty))
    }
  }

  await submitWithLock(savingPlan, async () => {
    await apiPost(`/planning/orders/${encodeURIComponent(selectedId.value)}/release`, { all: true })
    await apiPost(`/planning/orders/${encodeURIComponent(selectedId.value)}/allocate`, {
      selected_serial_nos: pickSerials,
    })
    await fetchData(true)
    await loadOrderAllocations()
    initOrderPlanDraft()
  }, { successMessage: '订单规划已保存', errorMessage: '保存订单规划失败' })
}

const approveToPlanning = async () => {
  if (!selectedId.value) return
  const targetId = selectedId.value
  await submitWithLock(saving, async () => {
    await apiPost(`/planning/contract/${encodeURIComponent(targetId)}/status`, { status: '待规划' })
    await fetchData(true)
    activeTab.value = 'planning'
    selectedType.value = 'contract'
    selectedId.value = targetId
  }, { successMessage: '已批准，进入待规划', errorMessage: '状态更新失败' })
}

const rejectContract = async () => {
  if (!selectedId.value) return
  await submitWithLock(saving, async () => {
    await apiPost(`/planning/contract/${encodeURIComponent(selectedId.value)}/status`, { status: '已取消' })
    ElMessage.success('合同已取消')
    selectedId.value = ''
    selectedType.value = ''
    await fetchData(true)
  }, { errorMessage: '状态更新失败' })
}

const loadContractFiles = async () => {
  if (!isContractSelected.value || !selectedId.value) {
    contractFiles.value = []
    return
  }
  try {
    const res = await apiGet<FileListResponse>(`/planning/contract/${encodeURIComponent(selectedId.value)}/files`)
    contractFiles.value = res.data || []
  } catch {
    contractFiles.value = []
  }
}

const onPickFile = (uploadFile: any) => {
  pickedFile.value = uploadFile.raw || null
}

const uploadFile = async () => {
  if (!pickedFile.value || !selectedId.value) return
  const file = pickedFile.value
  await submitWithLock(uploading, async () => {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('customer_name', String(contractFirst.value?.['客户名'] || selectedId.value))
    fd.append('uploader_name', 'WebUser')
    await apiPost(`/planning/contract/${encodeURIComponent(selectedId.value)}/files`, fd)
    pickedFile.value = null
    await loadContractFiles()
  }, { successMessage: '附件上传成功', errorMessage: '上传失败' })
}

const deleteFile = async (fileName: string) => {
  if (!selectedId.value) return
  try {
    await apiDelete(`/planning/contract/${encodeURIComponent(selectedId.value)}/files/${encodeURIComponent(fileName)}`)
    ElMessage.success('附件已删除')
    await loadContractFiles()
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '删除失败')
  }
}

const downloadFile = (fileName: string) => {
  if (!selectedId.value) return
  const url = `/api/v1/planning/contract/${encodeURIComponent(selectedId.value)}/files/${encodeURIComponent(fileName)}/download`
  window.open(url, '_blank')
}

const previewFile = async (fileName: string) => {
  if (!selectedId.value) return
  try {
    const res = await apiGet<PreviewResponse>(`/planning/contract/${encodeURIComponent(selectedId.value)}/files/${encodeURIComponent(fileName)}/preview`)
    previewState.fileName = fileName
    previewState.type = res.type || ''
    previewState.url = res.url || ''
    previewState.html = res.html || ''
    previewState.ext = res.ext || ''
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '预览失败')
  }
}

watch([selectedType, selectedId], () => {
  contractPlanRenderCount.value = PLAN_RENDER_STEP
  orderPlanRenderCount.value = PLAN_RENDER_STEP
  if (selectedType.value === 'contract' && selectedId.value) {
    loadEditForm()
    initPlanDraft()
    loadContractFiles()
    previewState.fileName = ''
    previewState.type = ''
    previewState.url = ''
    previewState.html = ''
    previewState.ext = ''
  } else {
    contractFiles.value = []
  }
  if (selectedType.value === 'order' && selectedId.value) {
    loadOrderAllocations()
    initOrderPlanDraft()
  }
})

watch(activeTab, () => {
  if (activeTab.value !== 'pending') editMode.value = false
})

watch(editMode, (v) => {
  if (v) loadEditForm()
})

const savePlanning = async () => {
  if (!selectedId.value) return
  for (const row of selectedContractRows.value) {
    const key = String(row._idx)
    const draft = planDraft[key] || { spot: 0, batches: {} }
    let allocated = toInt(draft.spot)
    for (const qty of Object.values(draft.batches || {})) allocated += toInt(qty)
    const need = toInt(row['排产数量'])
    if (allocated > need) {
      ElMessage.error(`机型 ${row['机型']} 分配超量：${allocated}/${need}`)
      return
    }
    if (allocated < need) {
      ElMessage.error(`机型 ${row['机型']} 规划未完成：${allocated}/${need}`)
      return
    }
    if (allocated <= 0) {
      ElMessage.error(`机型 ${row['机型']} 还未分配来源`)
      return
    }
  }

  await submitWithLock(savingPlan, async () => {
    const rows = selectedContractRows.value.map((row: any) => {
      const key = String(row._idx)
      const draft = planDraft[key] || { spot: 0, batches: {} }
      const allocation: Record<string, number> = {}
      if (toInt(draft.spot) > 0) allocation['现货(Spot)'] = toInt(draft.spot)
      for (const [k, v] of Object.entries(draft.batches || {})) {
        const qty = toInt(v)
        if (qty > 0) allocation[k] = qty
      }
      return { row_index: Number(row._idx), allocation }
    })
    await apiPost(`/planning/contract/${encodeURIComponent(selectedId.value)}/save-plan`, {
      rows,
      mark_to_planned: true,
    })
    await fetchData(true)
    initPlanDraft()
  }, { successMessage: '规划已保存', errorMessage: '保存规划失败' })
}

const goDirectAllocation = async () => {
  if (!selectedId.value || selectedContractRows.value.length === 0) return
  if (!contractPlanReady.value || !contractPlanSaved.value) {
    ElMessage.warning('请先完成规划并点击“保存规划”后，再直通配货')
    return
  }
  await submitWithLock(directAllocating, async () => {
    if (linkedOrderId.value) {
      ElMessage.success(`检测到已关联订单 ${linkedOrderId.value}，正在跳转配货`)
      await router.push({
        path: '/order-allocation',
        query: { order_id: linkedOrderId.value, contract_id: selectedId.value },
      })
      return
    }

    const rows = selectedContractRows.value
    const customer = String(contractFirst.value?.['客户名'] || '')
    const agent = String(contractFirst.value?.['代理商'] || '')
    const due = String(contractFirst.value?.['要求交期'] || '')
    const note = String(contractFirst.value?.['备注'] || '')
    const demandParts: string[] = []
    let totalNeed = 0
    for (const r of rows) {
      const model = String(r['机型'] || '').trim()
      const qty = Math.max(0, toInt(r['排产数量']))
      if (!model || qty <= 0) continue
      demandParts.push(`${model}:${qty}`)
      totalNeed += qty
    }
    if (demandParts.length === 0 || totalNeed <= 0) {
      ElMessage.error('当前合同没有可生成订单的机型/数量')
      return
    }

    const createRes = await apiPost<{ order_id?: string; message?: string }>('/planning/orders', {
      客户名: customer,
      代理商: agent,
      需求机型: demandParts.join(';'),
      需求数量: totalNeed,
      发货时间: due || '',
      备注: `合同${selectedId.value}自动生成；${note}`.slice(0, 500),
      包装选项: '',
    })
    const orderId = String(createRes.order_id || '').trim()
    if (!orderId) {
      throw new Error('自动生成订单失败：未返回订单号')
    }

    await apiPost(`/planning/contract/${encodeURIComponent(selectedId.value)}/link-order`, { order_id: orderId })
    await fetchData(true)
    ElMessage.success(`已生成订单 ${orderId}，正在跳转配货`)
    await router.push({ path: '/order-allocation', query: { order_id: orderId, contract_id: selectedId.value } })
  }, { errorMessage: '直通配货失败' })
}

onMounted(() => {
  fetchData()
})
</script>

<style scoped>
.planning-container {
  height: 100%;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.title {
  font-size: 18px;
  font-weight: bold;
  color: #303133;
}
.load-error {
  margin-bottom: 10px;
}
.month-list {
  margin-top: 8px;
  max-height: 650px;
  overflow: auto;
}
.filter-tip {
  margin-top: 6px;
  margin-bottom: 2px;
  color: #64748b;
  font-size: 12px;
}
.orders-block-title {
  margin-top: 8px;
  margin-bottom: 4px;
  color: #334155;
  font-size: 13px;
  font-weight: 700;
}
.item-list {
  display: grid;
  gap: 8px;
}
.item-btn {
  width: 100%;
  text-align: left;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #fff;
  padding: 8px 10px;
  color: #334155;
  cursor: pointer;
}
.item-btn.active {
  border-color: #ef4444;
  background: #ef4444;
  color: #fff;
}
.item-sub {
  margin-top: 4px;
  color: #6b7280;
  font-size: 12px;
}
.item-btn.active .item-sub {
  color: #fff;
}
.detail-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.detail-card {
  border: 1px solid #fef3c7;
  background: #fffbeb;
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 10px;
}
.ops-row {
  margin-top: 10px;
  display: flex;
  gap: 10px;
}
.ops-row.major :deep(.el-button) {
  min-width: 128px;
}
.plan-card {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 10px;
  margin-bottom: 10px;
}
.plan-title {
  font-weight: 700;
  margin-bottom: 8px;
}
.plan-grid {
  display: grid;
  grid-template-columns: 220px 1fr;
  gap: 12px;
  margin-bottom: 8px;
}
.plan-left {
  display: grid;
  gap: 6px;
  align-content: start;
}
.plan-hint {
  color: #6b7280;
  font-size: 12px;
}
.plan-right {
  display: grid;
  gap: 8px;
}
.batch-row {
  display: grid;
  grid-template-columns: 1fr auto;
  align-items: center;
  gap: 8px;
}
.batch-label {
  color: #334155;
  font-size: 13px;
}
.preview-empty {
  margin-top: 6px;
  border: 1px dashed #d1d5db;
  border-radius: 8px;
  padding: 10px 12px;
  color: #6b7280;
  font-size: 13px;
}
.preview-wrap {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  overflow: hidden;
}
.preview-head {
  background: #eff6ff;
  color: #1e40af;
  font-size: 12px;
  padding: 8px 10px;
}
.preview-frame {
  width: 100%;
  height: 520px;
  border: none;
}
.preview-image {
  display: block;
  max-width: 100%;
  max-height: 600px;
  margin: 0 auto;
}
.preview-html {
  max-height: 560px;
  overflow: auto;
  padding: 12px;
  background: #fff;
  color: #111827;
}
</style>
