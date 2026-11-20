<template>
  <div class="dealer-review-page">
    <PageHeader title="经销商订单审核">
      <template #actions>
        <el-button :loading="syncing" @click="syncCloudOrders">立即拉取订单</el-button>
        <el-button :loading="inventorySyncing" @click="syncCloudInventory">推送库存快照</el-button>
        <el-button :loading="machineSyncing" @click="syncMachineSnapshot">机台快照同步</el-button>
        <el-button @click="openSyncChannels">同步通道</el-button>
        <el-button type="primary" :loading="loading" @click="loadOrders">刷新</el-button>
      </template>
    </PageHeader>

    <ContractDraftReview
      ref="contractDraftReview"
      :confirm-order-approve="approveContractReviewOrder"
      :confirm-order-reject="rejectContractReviewOrder"
      :can-approve-order="!!contractReviewOrder && canApprove(contractReviewOrder)"
      @done="onContractReviewDone"
      @approve-order="onApproveWithoutContract"
    />
    <div v-if="cloudSyncStatus.pending || cloudSyncStatus.failed" class="cloud-sync-strip">
      <span>Cloud pending: <strong>{{ cloudSyncStatus.pending }}</strong></span>
      <span>Failed: <strong :class="{ danger: cloudSyncStatus.failed > 0 }">{{ cloudSyncStatus.failed }}</strong></span>
      <span v-if="cloudSyncStatus.recent_failed?.length" class="last-error">
        <span :title="cloudSyncLastError">Last failed: {{ cloudSyncLastSummary }}</span>
      </span>
      <el-button v-if="cloudSyncStatus.failed > 0" size="small" :loading="retryingCloudSync" @click="retryCloudSync">Retry</el-button>
    </div>

    <div class="filters">
      <el-input
        v-model="filters.keyword"
        clearable
        placeholder="搜索订单号 / 经销商 / 联系人 / 机型"
        class="keyword"
        @keyup.enter="loadOrders"
        @clear="loadOrders"
      />
      <el-radio-group v-model="filters.status" class="status-tabs" @change="onStatusChange">
        <el-radio-button value="">全部订单</el-radio-button>
        <el-radio-button value="todo">待审核</el-radio-button>
        <el-radio-button value="approved">已通过</el-radio-button>
        <el-radio-button value="contracted">已转合同</el-radio-button>
        <el-radio-button value="partial_allocated">部分配货</el-radio-button>
        <el-radio-button value="allocated">已配货</el-radio-button>
        <el-radio-button value="rejected">已驳回</el-radio-button>
        <el-radio-button value="cancelled">已取消</el-radio-button>
        <el-radio-button value="completed">已完成</el-radio-button>
      </el-radio-group>
      <el-button @click="loadOrders">查询</el-button>
    </div>

    <div class="todo-summary">
      <span>待办总数 <strong>{{ todoStats.total }}</strong></span>
      <span>新备注审核中 <strong class="warning-count">{{ todoStats.factoryPending }}</strong></span>
      <span>待审核 <strong>{{ todoStats.pending }}</strong></span>
    </div>

    <el-table
      v-loading="loading"
      :data="tableRows"
      :span-method="mergeOrderCells"
      row-key="_row_key"
      border
      stripe
      size="small"
      height="620"
      highlight-current-row
      @row-click="selectOrder"
    >
      <el-table-column prop="status" label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="rowStatusMeta(row).type">{{ rowStatusMeta(row).text }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="dealer_name" label="经销商" width="90" show-overflow-tooltip />
      <el-table-column prop="customer_name" label="客户名" min-width="390" show-overflow-tooltip>
        <template #default="{ row }">{{ customerDisplay(row) }}</template>
      </el-table-column>
      <el-table-column prop="model" label="机型明细" min-width="150" show-overflow-tooltip />
      <el-table-column prop="batch_no" label="批次/来源" width="120" show-overflow-tooltip>
        <template #default="{ row }">{{ displayBatch(row.batch_no, row.inventory_type) }}</template>
      </el-table-column>
      <el-table-column prop="quantity" label="数量" width="70" align="center">
        <template #default="{ row }">
          <el-tooltip content="点击局部刷新该订单数据" placement="top" :show-after="500">
            <span
              class="qty-highlight"
              :class="{ 'is-refreshing': refreshingOrders[row.order_no] }"
              @click.stop="refreshSingleOrder(row.order_no)"
            >
              <el-icon v-if="refreshingOrders[row.order_no]" class="is-loading"><Loading /></el-icon>
              <template v-else>{{ row.quantity }}</template>
            </span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column prop="remark" label="原备注" min-width="120" show-overflow-tooltip />
      <el-table-column prop="extra_remark" label="附加备注" min-width="120" show-overflow-tooltip />
      <el-table-column prop="ERMQ" label="需改数量" width="80" align="center" />
      <el-table-column label="操作" width="420" align="center" fixed="right">
        <template #default="{ row }">
          <div class="op-buttons">
            <el-button size="small" type="success" :disabled="!canViewContract(row)" @click.stop="openContractReview(row)">
              {{ reviewButtonLabel(row) }}
            </el-button>
            <el-button size="small" type="danger" :disabled="!canReject(row)" @click.stop="rejectOrder(row)">驳回</el-button>
            <el-button
              size="small"
              type="warning"
              :disabled="!canConvertDealerOrder(row)"
              :title="canConvertDealerOrder(row) ? '' : '请先审核通过后再转合同'"
              @click.stop="openConvertDialog(row._order || row)"
            >
              转合同
            </el-button>
            <el-button
              size="small"
              type="danger"
              plain
              :loading="cancelPreviewLoading"
              :disabled="!canCancelDealerOrder(row)"
              :title="canCancelDealerOrder(row) ? '' : '仅已通过 / 已转合同 / 部分配货 / 已配货且无待审核新备注的订单可取消'"
              @click.stop="openCancelDialog(row._order || row)"
            >
              取消订单
            </el-button>
          </div>
        </template>
      </el-table-column>
    </el-table>

    <div class="pager-row">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="total"
        :page-sizes="[20, 50, 100]"
        layout="total, sizes, prev, pager, next"
        @current-change="loadOrders"
        @size-change="onSizeChange"
      />
    </div>

    <el-drawer v-model="drawerOpen" title="订单审核详情" size="720px">
      <el-empty v-if="!selectedOrder" description="请选择订单" />
      <template v-else>
        <div class="detail-grid">
          <span>订单号</span><strong>{{ selectedOrder.order_no }}</strong>
          <span>经销商</span><strong>{{ selectedOrder.dealer_name || '-' }}</strong>
          <span>客户</span><strong>{{ selectedOrder.customer_name || '-' }}</strong>
          <span>地址</span><strong>{{ selectedOrder.delivery_address || '-' }}</strong>
          <span>客户名（地址合并）</span><strong>{{ customerDisplay(selectedOrder) }}</strong>
          <span>办事处</span><strong>{{ selectedOrder.office_name || '-' }}</strong>
          <span>办事处联系人</span><strong>{{ selectedOrder.office_contact || '-' }}</strong>
          <span>办事处联系方式</span><strong>{{ selectedOrder.office_phone || '-' }}</strong>
          <span>联系人</span><strong>{{ selectedOrder.contact_name || '-' }}</strong>
          <span>电话</span><strong>{{ selectedOrder.contact_phone || '-' }}</strong>
          <span>结算方式及期限</span><strong>{{ selectedOrder.settlement_terms || '-' }}</strong>
          <span>其他特殊要求</span><strong>{{ selectedOrder.special_requirements || '-' }}</strong>
          <span>当前状态</span><strong>{{ statusMeta(selectedOrder).text }}</strong>
          <span>总数量</span><strong>{{ selectedOrder.quantity }}</strong>
          <span>已配货</span><strong>{{ selectedOrder.allocated_qty ?? 0 }}</strong>
          <span v-if="selectedOrder.contract_no">合同号</span><strong v-if="selectedOrder.contract_no">{{ selectedOrder.contract_no }}</strong>
        </div>

        <el-divider />
        <el-table :data="detailItems" border size="small">
          <el-table-column prop="line_no" label="行号" width="70" align="right" />
          <el-table-column prop="model" label="机型" min-width="150" show-overflow-tooltip />
          <el-table-column prop="batch_no" label="批次/来源" min-width="130" show-overflow-tooltip>
            <template #default="{ row }">{{ displayBatch(row.batch_no, row.inventory_type) }}</template>
          </el-table-column>
          <el-table-column prop="quantity" label="数量" width="80" align="right" />
          <el-table-column prop="allocated_qty" label="已配" width="80" align="right" />
          <el-table-column label="可用" width="90" align="right">
            <template #default="{ row }">
              <span v-if="row.is_preorder">无货预订</span>
              <span v-else :class="{ danger: Number(row.available_qty || 0) < Number(row.quantity || 0) - Number(row.allocated_qty || 0) }">
                {{ row.available_qty ?? '-' }}
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="status" label="状态" width="120">
            <template #default="{ row }">
              <el-tag :type="statusMeta(row).type">{{ statusMeta(row).text }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="remark" label="原备注" min-width="130" show-overflow-tooltip />
          <el-table-column prop="extra_remark" label="附加备注" min-width="130" show-overflow-tooltip />
          <el-table-column prop="ERMQ" label="需改数量" width="100" align="right" />
        </el-table>

        <el-divider />
        <div class="availability">
          <div>
            <span>库存总量</span>
            <strong>{{ preview?.summary_qty ?? selectedOrder.summary_qty ?? '-' }}</strong>
          </div>
          <div>
            <span>已占用</span>
            <strong>{{ preview?.occupied_qty ?? selectedOrder.occupied_qty ?? '-' }}</strong>
          </div>
          <div>
            <span>最小可审</span>
            <strong :class="{ danger: hasInsufficientItem(selectedOrder) }">
              {{ preview?.available_qty ?? selectedOrder.available_qty ?? '-' }}
            </strong>
          </div>
        </div>

        <el-divider />
        <div class="note-title">订单备注</div>
        <div class="note-box">{{ selectedOrder.remark || '-' }}</div>
        <div class="note-title">附加备注</div>
        <div class="note-box">{{ selectedOrder.extra_remark || '-' }}</div>
        <div class="note-title">审核备注</div>
        <div class="note-box">{{ selectedOrder.review_note || '-' }}</div>

        <div class="drawer-actions">
          <el-button :disabled="!canViewContract(selectedOrder)" @click="openContractReview(selectedOrder)">
            {{ reviewButtonLabel(selectedOrder) }}
          </el-button>
          <el-button type="danger" :disabled="!canReject(selectedOrder)" @click="rejectOrder(selectedOrder)">驳回</el-button>
          <el-button
            type="warning"
            :disabled="!canConvertDealerOrder(selectedOrder)"
            :title="canConvertDealerOrder(selectedOrder) ? '' : '请先审核通过后再转合同'"
            @click="openConvertDialog(selectedOrder)"
          >转合同</el-button>
          <el-button
            type="danger"
            plain
            :loading="cancelPreviewLoading"
            :disabled="!canCancelDealerOrder(selectedOrder)"
            :title="canCancelDealerOrder(selectedOrder) ? '' : '仅已通过 / 已转合同 / 部分配货 / 已配货且无待审核新备注的订单可取消'"
            @click="openCancelDialog(selectedOrder)"
          >取消订单</el-button>
        </div>
      </template>
    </el-drawer>

    <el-dialog
      v-model="convertDialogVisible"
      title="经销商订单转合同"
      width="860px"
      :close-on-click-modal="false"
      :close-on-press-escape="false"
    >
      <div class="convert-grid">
        <div>
          <div class="ops-label">合同号</div>
          <el-input v-model="convertForm.contractNo" placeholder="自动生成" />
        </div>
        <div>
          <div class="ops-label">期望交付日期</div>
          <el-date-picker v-model="convertForm.deliveryDate" type="date" value-format="YYYY-MM-DD" style="width:100%" />
        </div>
        <div>
          <div class="ops-label">客户名称</div>
          <el-input v-model="convertForm.customer" />
        </div>
        <div>
          <div class="ops-label">代理商</div>
          <el-input v-model="convertForm.agent" />
        </div>
      </div>

      <el-divider />
      <div class="ops-label">机型明细</div>
      <el-table :data="convertForm.items" border size="small" class="form-table">
        <el-table-column label="#" width="50">
          <template #default="scope">{{ scope.$index + 1 }}</template>
        </el-table-column>
        <el-table-column label="机型" min-width="160">
          <template #default="scope">
            <el-select v-model="scope.row.model" filterable placeholder="机型" style="width:100%">
              <el-option v-for="m in modelOptions" :key="m" :label="m" :value="m" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="数量" width="90">
          <template #default="scope">
            <el-input-number v-model="scope.row.qty" :min="1" :controls="false" style="width:100%" />
          </template>
        </el-table-column>
        <el-table-column label="加高" width="70">
          <template #default="scope">
            <el-checkbox v-model="scope.row.high" />
          </template>
        </el-table-column>
        <el-table-column label="路径" width="170">
          <template #default="scope">
            <el-tag :type="convertPathTagType(scope.row)" size="small">{{ convertLinePathLabel(scope.row) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="原备注" min-width="120">
          <template #default="scope">
            <el-input v-model="scope.row.remark" placeholder="原备注" />
          </template>
        </el-table-column>
        <el-table-column label="附加备注" min-width="120">
          <template #default="scope">
            <el-input v-model="scope.row.extraRemark" placeholder="附加备注" />
          </template>
        </el-table-column>
        <el-table-column label="需改数量" width="110">
          <template #default="scope">
            <el-input-number v-model="scope.row.ermq" :min="0" :controls="false" style="width:100%" />
          </template>
        </el-table-column>
      </el-table>

      <el-divider />
      <div class="ops-label">合同总备注</div>
      <el-input v-model="convertForm.contractNote" placeholder="可选" />

      <el-divider />
      <div class="ops-label">📎 附加合同文件 (可选)</div>
      <el-upload
        ref="convertUploadRef"
        :auto-upload="false"
        :show-file-list="true"
        multiple
        :on-change="onConvertFileChange"
        :on-remove="onConvertFileRemove"
      >
        <el-button>选择文件</el-button>
      </el-upload>

      <div class="save-mode-section">
        <div class="ops-label">路径（按明细批次/来源自动判定）</div>
        <div class="save-mode-hint">按去向生成合同：现货行合成一张「已规划」合同（到「销售订单 → 导入已规划合同」建单后在「订单配货」人工分配机台）；在制指定批次行单独一张合同，自动执行「按批次规划并配货」预占机台（订单待二次确认，失败回退已规划人工配货）；无货预订行单独一张「待规划」合同并进入沙盘排产。混合订单最多生成三张合同。</div>
      </div>

      <template #footer>
        <el-button @click="convertDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="convertSaving" @click="submitConvert()">确认转合同</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="cancelDialogVisible"
      title="取消经销商订单"
      width="640px"
      :close-on-click-modal="false"
      :close-on-press-escape="!cancelSubmitting"
    >
      <el-empty v-if="!cancelPreview" description="暂无可取消信息" />
      <template v-else>
        <div class="detail-grid cancel-grid">
          <span>订单号</span><strong>{{ cancelPreview.order_no }}</strong>
          <span>当前状态</span><strong>{{ statusMeta(cancelPreview.status).text }}</strong>
          <span>合同号</span><strong>{{ cancelListText(cancelPreview.contracts) }}</strong>
          <span>销售订单</span><strong>{{ cancelListText(cancelPreview.sales_orders) }}</strong>
          <span>待释放机台</span>
          <strong>
            库存现货 {{ cancelPreview.machines?.stock ?? 0 }} 台 / 在产预占 {{ cancelPreview.machines?.production ?? 0 }} 台 /
            合计 {{ cancelPreview.machines?.total ?? 0 }} 台
          </strong>
          <span>机台流水号</span>
          <div>
            <div class="cancel-serial-summary">{{ cancelSerialsSummary }}</div>
            <el-collapse v-if="cancelSerialRows.length > 10" class="cancel-serial-collapse">
              <el-collapse-item title="查看全部流水号" name="serials">
                <div class="cancel-serial-list">{{ cancelSerialRows.join('、') }}</div>
              </el-collapse-item>
            </el-collapse>
          </div>
        </div>
        <div v-if="cancelPreview.warnings?.length" class="cancel-warnings">
          <div v-for="(item, idx) in cancelPreview.warnings" :key="idx">⚠ {{ item }}</div>
        </div>
        <div class="cancel-danger-hint">
          取消后会释放未出库配货、取消合同与销售订单，并把小程序订单置为已取消（已出库机台不会自动回滚）。
        </div>
        <div class="ops-label cancel-reason-label">取消原因</div>
        <el-input
          v-model="cancelReason"
          type="textarea"
          :rows="3"
          maxlength="200"
          show-word-limit
          placeholder="选填，填写取消原因便于追踪（如客户变更需求）"
        />
      </template>
      <template #footer>
        <el-button :disabled="cancelSubmitting" @click="cancelDialogVisible = false">取消</el-button>
        <el-button type="danger" :loading="cancelSubmitting" :disabled="!cancelPreview" @click="confirmCancelOrder">
          确认取消
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="channelsDialogVisible"
      title="同步通道"
      width="min(1280px, 96vw)"
      class="sync-channels-dialog"
      @closed="stopChannelsAutoRefresh"
    >
      <div class="channels-hint">
        与云端「同步监控 → V8 桥接上传」同一套通道口径；云端监控仍是最终判据，这里展示本地最近成功/失败与待发送事件。
        <span v-if="channelsServerTime">（本地时间 {{ channelsServerTime }}）</span>
      </div>
      <el-table v-loading="channelsLoading" :data="syncChannels" size="small" border>
        <el-table-column prop="label" label="同步通道" min-width="220">
          <template #default="scope">
            <div>{{ scope.row.label }}</div>
            <div class="channel-desc">{{ scope.row.description }}</div>
          </template>
        </el-table-column>
        <el-table-column prop="direction" label="方向" width="160" />
        <el-table-column prop="interval_label" label="设定周期" width="90" align="center" />
        <el-table-column label="最近成功" width="170">
          <template #default="scope">
            <span>{{ scope.row.last_success_at || '-' }}</span>
            <el-tag v-if="scope.row.last_trigger === 'manual'" size="small" type="info" class="channel-trigger">手动</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="expected_next_at" label="预计下次" width="170">
          <template #default="scope">{{ scope.row.expected_next_at || '—' }}</template>
        </el-table-column>
        <el-table-column label="偏差" width="100" align="center">
          <template #default="scope">
            <span v-if="scope.row.overdue_seconds > 0" class="channel-overdue">超期 {{ formatOverdue(scope.row.overdue_seconds) }}</span>
            <span v-else>未超期</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100" align="center">
          <template #default="scope">
            <el-tag :type="channelStateTagType(scope.row.state)" size="small">{{ scope.row.state_label }}</el-tag>
            <span v-if="scope.row.failed > 0" class="channel-failed">失败 {{ scope.row.failed }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120" align="center">
          <template #default="scope">
            <el-button
              v-if="scope.row.manual_action"
              size="small"
              :loading="channelActionLoading === scope.row.manual_action"
              @click="runChannelAction(scope.row.manual_action)"
            >{{ scope.row.manual_action === 'reconcile-order-status' ? '立即对账' : '立即同步' }}</el-button>
            <span v-else class="channel-desc">自动触发</span>
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="loadSyncChannels">刷新</el-button>
        <el-button @click="channelsDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import PageHeader from '../components/PageHeader.vue'
import ContractDraftReview from '../components/ContractDraftReview.vue'
import { apiGet, apiPost, getApiErrorMessage } from '../utils/request'
import { isModelInDictionary } from '../utils/modelOrder'
import { normalizeDealerOrderItems, resolveDealerOrderRowNotes, convertLinePathLabel, isPreorderLine, type ConvertItemRow } from '../utils/dealerOrderItems'
import { useModelDictionaryStore } from '../store/modelDictionary'
import { hasText, isPositiveInteger } from '../utils/formRules'
import { buildCloudAttachmentNotice, type CloudAttachmentSyncSummary } from '../utils/cloudAttachmentNotice'
const contractDraftReview = ref<InstanceType<typeof ContractDraftReview>>()

type DealerOrder = {
  id: number
  order_no: string
  line_no?: number
  line_count?: number
  dealer_openid?: string
  dealer_name?: string
  dealer_phone?: string
  regional_manager_name?: string
  customer_name?: string
  delivery_address?: string
  office_name?: string
  office_contact?: string
  office_phone?: string
  contact_name?: string
  contact_phone?: string
  settlement_terms?: string
  special_requirements?: string
  model: string
  batch_no?: string
  expected_inbound_time?: string
  inventory_type?: string
  quantity: number
  approved_qty?: number
  allocated_qty?: number
  delivery_date?: string
  contract_no?: string
  status: string
  remark?: string
  extra_remark?: string
  factory_remark?: string
  ERMQ?: number
  factory_pending?: number
  review_note?: string
  regional_review_note?: string
  reviewed_at?: string
  reviewed_by?: string
  created_at?: string
  updated_at?: string
  summary_qty?: number
  occupied_qty?: number
  available_qty?: number
  route?: 'spot' | 'batch' | 'preorder'
  is_preorder?: boolean
  items?: DealerOrder[]
}

type DealerOrderTableRow = DealerOrder & {
  _row_key: string
  _order: DealerOrder
}

type OrderListResponse = {
  data: DealerOrder[]
  total: number
}

type PreviewResponse = {
  order: DealerOrder
  items: DealerOrder[]
  summary_qty: number
  occupied_qty: number
  available_qty: number
  can_approve: boolean
}

type DealerOrderCancelPreview = {
  order_no: string
  status: string
  cancellable: boolean
  blockers: string[]
  warnings: string[]
  contracts: string[]
  sales_orders: string[]
  machines: {
    total: number
    stock: number
    production: number
    serials: string[]
  }
  shipped_machines: string[]
  lines: number
}

type DealerOrderCancelResult = {
  // 取消执行器输出：机台流水号 / 合同号 / 销售订单号均为数组（兼容旧版数字计数）。
  released_serials?: number | string[]
  stock?: number
  production?: number
  contracts?: number | string[]
  sales_orders?: number | string[]
  dealer_lines?: number
  cloud_event?: string | Record<string, any>
}

type DealerOrderCancelResponse = {
  message?: string
  warning?: string
  status?: string
  approval_pending?: boolean
  instance_no?: string
  preview?: DealerOrderCancelPreview
  result?: DealerOrderCancelResult
}

type CloudSyncStatus = {
  pending: number
  failed: number
  recent_failed: Array<{
    id?: number
    event_type?: string
    biz_key?: string
    last_error?: string
    retry_count?: number
    next_retry_at?: string
    updated_at?: string
  }>
}

type SyncChannel = {
  key: string
  label: string
  direction: string
  description: string
  interval_seconds: number | null
  interval_label: string
  last_success_at: string | null
  last_trigger: string | null
  last_error: string | null
  pending: number
  failed: number
  manual_action: string | null
  expected_next_at: string | null
  overdue_seconds: number
  state: string
  state_label: string
}

type SyncChannelsResponse = {
  server_time: string
  channels: SyncChannel[]
}

const loading = ref(false)
const syncing = ref(false)
const inventorySyncing = ref(false)
const machineSyncing = ref(false)
const retryingCloudSync = ref(false)
const cloudSyncStatus = ref<CloudSyncStatus>({ pending: 0, failed: 0, recent_failed: [] })
const channelsDialogVisible = ref(false)
const channelsLoading = ref(false)
const channelsServerTime = ref('')
const syncChannels = ref<SyncChannel[]>([])
const channelActionLoading = ref('')
const orders = ref<DealerOrder[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(50)
const selectedOrderNo = ref('')
const drawerOpen = ref(false)
const preview = ref<PreviewResponse | null>(null)
const filters = reactive({
  keyword: '',
  status: '',
})
const todoStats = reactive({
  total: 0,
  factoryPending: 0,
  pending: 0,
})

const cloudSyncLastError = computed(() => {
  const item = cloudSyncStatus.value.recent_failed?.[0]
  if (!item) return ''
  return [item.biz_key, item.last_error].filter(Boolean).join(' ')
})

const cloudSyncLastSummary = computed(() => {
  const item = cloudSyncStatus.value.recent_failed?.[0]
  if (!item) return '-'
  const orderNo = String(item.biz_key || '').trim()
  const eventType = String(item.event_type || '').replace(/^dealer_order_/, '')
  return [orderNo, eventType || 'sync'].filter(Boolean).join(' / ')
})

const selectedOrder = computed(() => orders.value.find((row) => row.order_no === selectedOrderNo.value) || null)
const detailItems = computed(() => preview.value?.items || selectedOrder.value?.items || (selectedOrder.value ? [selectedOrder.value] : []))
const statusRank = (status: string) => ({
  pending: 0,
  approved: 1,
  contracted: 2,
  partial_allocated: 3,
  allocated: 4,
  rejected: 5,
  cancelled: 6,
  complete: 7,
  completed: 7,
}[status] ?? 9)

const rowPriority = (row: DealerOrder) => {
  const status = String(row.status || '')
  if (Number(row.factory_pending || 0) === 1 && !['complete', 'completed'].includes(status)) return -1
  return statusRank(status)
}

/**
 * 先按「订单」排序，再展开订单下的机型明细行。
 * 这样同一订单的多行一定连续，才能把经销商 / 客户名 / 操作等订单级单元格合并。
 */
const sortedOrders = computed<DealerOrder[]>(() =>
  [...orders.value].sort((a, b) => {
    const priorityDiff = rowPriority(a) - rowPriority(b)
    if (priorityDiff !== 0) return priorityDiff
    const bTime = String(b.updated_at || b.created_at || '')
    const aTime = String(a.updated_at || a.created_at || '')
    if (bTime !== aTime) return bTime.localeCompare(aTime)
    return String(b.order_no || '').localeCompare(String(a.order_no || ''))
  }),
)

const tableRows = computed<DealerOrderTableRow[]>(() =>
  sortedOrders.value.flatMap((order) => {
    const items = order.items?.length ? order.items : [order]
    return items.map((item, index) => {
      const rowNotes = resolveDealerOrderRowNotes(items.length, item, order)
      return {
        ...order,
        ...item,
        // 多明细订单只展示行级备注；订单级汇总值只在单明细/无明细时兜底，避免备注串行。
        remark: rowNotes.remark,
        extra_remark: rowNotes.extra_remark,
        factory_remark: item.factory_remark || item.extra_remark || order.factory_remark || order.extra_remark || '',
        ERMQ: Number(item.ERMQ ?? order.ERMQ ?? 0),
        factory_pending: Number(item.factory_pending ?? order.factory_pending ?? 0),
        review_note: item.review_note || order.review_note || '',
        regional_review_note: item.regional_review_note || order.regional_review_note || '',
        items: order.items?.length ? order.items : [order],
        line_count: order.line_count,
        _order: order,
        _row_key: `${order.order_no}-${item.line_no || index + 1}`,
      }
    })
  }),
)

/**
 * 同一订单在表格中占用的连续行组（订单 → 起始行 + 行数），供单元格合并使用。
 */
const orderRowGroups = computed(() => {
  const groups = new Map<string, { start: number; span: number }>()
  const rows = tableRows.value
  let index = 0
  while (index < rows.length) {
    const orderNo = String(rows[index].order_no || '')
    let end = index + 1
    while (end < rows.length && String(rows[end].order_no || '') === orderNo) end += 1
    // 组内每一行都登记同一组信息：合并判断时用 rowIndex === start 区分首行。
    for (let cursor = index; cursor < end; cursor += 1) {
      groups.set(rows[cursor]._row_key, { start: index, span: end - index })
    }
    index = end
  }
  return groups
})

/** 订单级列：同一订单只显示一次（状态、经销商、客户名、操作），其余列保留行级明细。 */
const MERGED_ORDER_COLUMN_PROPS = new Set(['status', 'dealer_name', 'customer_name'])
const isMergedOrderColumn = (column: any) =>
  MERGED_ORDER_COLUMN_PROPS.has(String(column?.property || '')) || column?.label === '操作'

/**
 * el-table 合并单元格：同一订单的第一行返回 [行数, 1]，其余行返回 [0, 0] 隐藏。
 * 状态 / 经销商 / 客户名合并后整单只显示一次；操作列合并后整单只有一组按钮，
 * 避免同一订单重复出现审核 / 转合同 / 取消入口。
 */
const mergeOrderCells = ({ row, column, rowIndex }: { row: DealerOrderTableRow; column: any; rowIndex: number }) => {
  if (!isMergedOrderColumn(column)) return
  const group = orderRowGroups.value.get(row._row_key)
  if (!group || group.span <= 1) return
  if (rowIndex !== group.start) return [0, 0]
  return [group.span, 1]
}

const statusMeta = (rowOrStatus: DealerOrder | string) => {
  const status = typeof rowOrStatus === 'string' ? rowOrStatus : rowOrStatus.status
  const factoryPending = typeof rowOrStatus === 'string' ? 0 : Number(rowOrStatus.factory_pending || 0)
  if (factoryPending === 1 && !['complete', 'completed'].includes(status)) return { text: '新备注审核中', type: 'warning' as const }
  const map: Record<string, { text: string; type: 'primary' | 'success' | 'warning' | 'danger' | 'info' }> = {
    pending: { text: '待审核', type: 'warning' },
    approved: { text: '已通过', type: 'primary' },
    contracted: { text: '已转合同', type: 'success' },
    partial_allocated: { text: '部分配货', type: 'success' },
    allocated: { text: '已配货', type: 'success' },
    rejected: { text: '已驳回', type: 'danger' },
    cancelled: { text: '已取消', type: 'info' },
    complete: { text: '已完成', type: 'success' },
    completed: { text: '已完成', type: 'success' },
  }
  return map[status] || { text: status || '-', type: 'info' }
}

/**
 * 合并后的状态单元格取整个订单的状态：
 * 任一行有新备注待审（factory_pending）就整单提示「新备注审核中」，避免合并后漏掉行级提示。
 */
const rowStatusMeta = (row: DealerOrderTableRow) => {
  const group = orderRowGroups.value.get(row._row_key)
  const rowsInGroup = group ? tableRows.value.slice(group.start, group.start + group.span) : [row]
  const anyFactoryPending = rowsInGroup.some(
    (item) => Number(item.factory_pending || 0) === 1 && !['complete', 'completed'].includes(String(item.status || '')),
  )
  if (anyFactoryPending) return { text: '新备注审核中', type: 'warning' as const }
  return statusMeta(String(rowsInGroup[0]?.status || row.status || ''))
}

const displayBatch = (batchNo?: string, inventoryType?: string) => {
  if (isPreorderLine({ batch_no: batchNo, inventory_type: inventoryType })) return '无货预订'
  if (String(inventoryType || '').trim().toLowerCase() === 'finished') return '库存中'
  if (!batchNo) return '-'
  if (batchNo === 'FINISHED-STOCK') return '库存中'
  return batchNo
}

const hasInsufficientItem = (row: DealerOrder) => {
  const items = row.items?.length ? row.items : [row]
  return items.some((item) => !item.is_preorder && Number(item.available_qty || 0) < Number(item.quantity || 0) - Number(item.allocated_qty || 0))
}

const hasFactoryRemark = (row: DealerOrder) => {
  if (String(row.factory_remark || row.extra_remark || '').trim()) return true
  const items = row.items?.length ? row.items : []
  return items.some((item) => String(item.factory_remark || item.extra_remark || '').trim())
}

const isFactoryPending = (row: DealerOrder) => Number(row.factory_pending || 0) === 1 && !['complete', 'completed'].includes(row.status)
const canApprove = (row: DealerOrder) => isFactoryPending(row) || row.status === 'pending'
const canReject = (row: DealerOrder) => (isFactoryPending(row) ? hasFactoryRemark(row) : ['pending', 'approved'].includes(row.status))
const canConvertDealerOrder = (row: DealerOrder) => String(row.status || '').trim() === 'approved' && !isFactoryPending(row)
// 已通过 / 已转合同 / 部分配货 / 已配货的订单可取消；待审核、已取消、已完成等状态不显示可用取消。
const canCancelDealerOrder = (row: DealerOrder) => {
  // 表格行是「订单 + 明细」合并行：取消针对整单，状态取订单级 _order，新备注审核中则行级也要看。
  const target = (row as DealerOrderTableRow)._order || row
  const status = String(target.status || '').trim()
  return ['approved', 'contracted', 'partial_allocated', 'allocated'].includes(status)
    && !isFactoryPending(target)
    && !isFactoryPending(row)
}
// 合同附件是只读资料：待审核走"预览并审批"，其它状态（已通过/已转合同/已驳回等）也要能打开只读查看。
const canViewContract = (row: DealerOrder) => !!String(row.order_no || '').trim()

// 待审核显示"预览并审批"，其它状态一律只读查看合同附件。
const reviewButtonLabel = (row: DealerOrder) => {
  if (isFactoryPending(row)) return '通过'
  return canApprove(row) ? '预览并审批' : '查看合同'
}

const modelDictionaryStore = useModelDictionaryStore()
const modelOptions = computed(() => modelDictionaryStore.rows
  .filter((row) => row.enabled && row.model_name)
  .slice()
  .sort((a, b) => a.sort_order - b.sort_order)
  .map((row) => row.model_name))
const router = useRouter()
const convertDialogVisible = ref(false)
const convertSaving = ref(false)
const convertForm = reactive({
  contractNo: '',
  deliveryDate: '',
  customer: '',
  agent: '',
  items: [] as ConvertItemRow[],
  contractNote: '',
  sourceOrderNo: '',
})

/** 路径标签配色：库存行 success，批次行 info。 */
const convertPathTagType = (item?: { batch_no?: string; inventory_type?: string } | null) =>
  convertLinePathLabel(item).startsWith('库存') ? 'success' : 'info'

const convertPickedFiles = ref<File[]>([])
const convertUploadRef = ref<any>(null)

const onConvertFileChange = (uploadFile: any) => {
  const raw = uploadFile.raw as File | undefined
  if (!raw) return
  convertPickedFiles.value.push(raw)
}

const onConvertFileRemove = (uploadFile: any) => {
  const raw = uploadFile.raw as File | undefined
  if (!raw) return
  convertPickedFiles.value = convertPickedFiles.value.filter((f) => !(f.name === raw.name && f.size === raw.size))
}

const todayYmd = () => new Date().toISOString().slice(0, 10)
const fetchNextContractId = async () => {
  const res = await apiGet<{ contract_no: string }>('/planning/contracts/next-id')
  return String(res.contract_no || '').trim()
}

const customerDisplay = (order: DealerOrder | Record<string, any>) => {
  const customer = String((order as any).customer_name || '').trim()
  const address = String((order as any).delivery_address || '').trim()
  if (!address) return customer || '-'
  return `${address}（${customer || '-'}）`
}

const openConvertDialog = async (order: DealerOrder) => {
  if (!canConvertDealerOrder(order)) {
    ElMessage.warning('只有审核通过的经销商订单可以转合同，请先在「预览并审批」中完成审核')
    return
  }
  const rows = normalizeDealerOrderItems(order)
  if (rows.length === 0) {
    ElMessage.warning('该经销商订单没有可转合同的机型明细')
    return
  }
  convertForm.contractNo = ''
  convertForm.deliveryDate = String(order.delivery_date || '').slice(0, 10) || todayYmd()
  convertForm.customer = String(order.customer_name || '').trim()
  // 「代理商」取大区经理（历史合同口径）；客户联系人 contact_name 不能拿来填代理商。
  convertForm.agent = String(order.regional_manager_name || '').trim()
  convertForm.items = rows
  convertForm.contractNote = String(order.review_note || order.regional_review_note || '').trim()
  convertForm.sourceOrderNo = String(order.order_no || '').trim()
  try {
    convertForm.contractNo = await fetchNextContractId()
  } catch (err) {
    ElMessage.error(getApiErrorMessage(err) || '生成合同号失败')
    return
  }
  
  // 重置上传的文件
  convertPickedFiles.value = []
  convertUploadRef.value?.clearFiles()

  convertDialogVisible.value = true
}

const loadPreview = async (orderNo: string) => {
  preview.value = await apiGet<PreviewResponse>(`/dealer-orders/${encodeURIComponent(orderNo)}/preview`)
}

const loadTodoStats = async () => {
  try {
    const res = await apiGet<{ pending: number; factory_pending: number; total: number }>('/dealer-orders/pending-count')
    const changed = todoStats.total !== (res.total || 0) ||
                    todoStats.factoryPending !== (res.factory_pending || 0) ||
                    todoStats.pending !== (res.pending || 0)
    todoStats.total = res.total || 0
    todoStats.factoryPending = res.factory_pending || 0
    todoStats.pending = res.pending || 0
    if (changed) {
      window.dispatchEvent(new CustomEvent('dealer-orders-updated', { detail: res }))
    }
  } catch {
    todoStats.total = 0
    todoStats.factoryPending = 0
    todoStats.pending = 0
  }
}

const loadOrders = async (silent: boolean | any = false) => {
  const isSilent = silent === true
  if (!isSilent) {
    loading.value = true
  }
  try {
    const res = await apiGet<OrderListResponse>('/dealer-orders/', {
      params: {
        status: filters.status || undefined,
        keyword: filters.keyword || undefined,
        page: page.value,
        page_size: pageSize.value,
      },
    })
    orders.value = res.data || []
    total.value = Number(res.total || 0)
    if (selectedOrderNo.value && !orders.value.some((row) => row.order_no === selectedOrderNo.value)) {
      selectedOrderNo.value = ''
      preview.value = null
    }
    if (!selectedOrderNo.value && orders.value.length > 0) {
      selectedOrderNo.value = orders.value[0].order_no
      try {
        await loadPreview(selectedOrderNo.value)
      } catch {
        preview.value = null
      }
    }
    void loadTodoStats()
  } finally {
    if (!isSilent) {
      loading.value = false
    }
  }
}

const refreshingOrders = ref<Record<string, boolean>>({})

const refreshSingleOrder = async (orderNo: string) => {
  if (!orderNo || refreshingOrders.value[orderNo]) return
  refreshingOrders.value[orderNo] = true
  try {
    const res = await apiGet<OrderListResponse>('/dealer-orders/', {
      params: {
        keyword: orderNo,
        page: 1,
        page_size: 1,
      },
    })
    const updatedRows = res.data || []
    if (updatedRows.length > 0) {
      const idx = orders.value.findIndex((o) => o.order_no === orderNo)
      if (idx !== -1) {
        orders.value[idx] = updatedRows[0]
      }
    }
  } catch (err: any) {
    ElMessage.error('刷新订单失败: ' + (getApiErrorMessage(err) || err.message))
  } finally {
    refreshingOrders.value[orderNo] = false
  }
}

const loadCloudSyncStatus = async () => {
  try {
    cloudSyncStatus.value = await apiGet<CloudSyncStatus>('/dealer-orders/cloud-sync-status')
  } catch {
    cloudSyncStatus.value = { pending: 0, failed: 0, recent_failed: [] }
  }
}

const selectOrder = async (row: DealerOrder) => {
  selectedOrderNo.value = row.order_no
  drawerOpen.value = true
  try {
    await loadPreview(row.order_no)
  } catch {
    preview.value = null
  }
}

const onSizeChange = () => {
  page.value = 1
  loadOrders()
}

const onStatusChange = () => {
  page.value = 1
  selectedOrderNo.value = ''
  preview.value = null
  loadOrders()
}

const retryCloudSync = async () => {
  retryingCloudSync.value = true
  try {
    const res = await apiPost<{ queued?: number; processed?: number; synced?: number }>('/dealer-orders/cloud-sync-retry', {})
    ElMessage.success(`Retry queued ${res.queued || 0}, processed ${res.processed || 0}, synced ${res.synced || 0}`)
    await loadCloudSyncStatus()
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || 'Cloud sync retry failed')
  } finally {
    retryingCloudSync.value = false
  }
}

const syncCloudOrders = async () => {
  syncing.value = true
  ElMessage.info('正在拉取云端订单，请稍候…')
  try {
    const res = await apiPost<{
      inserted?: number
      updated?: number
      skipped?: number
      factory_pending_orders?: number
      pruned_cloud_deleted_orders?: number
    }>('/dealer-orders/sync-cloud', {
      status: 'all',
      page_size: 100,
      max_pages: 20,
    }, { timeout: 120_000 })
    const prunedText = Number(res.pruned_cloud_deleted_orders || 0) > 0 ? `，清理 ${res.pruned_cloud_deleted_orders}` : ''
    ElMessage.success(`拉取完成：新增 ${res.inserted || 0}，更新 ${res.updated || 0}，跳过 ${res.skipped || 0}${prunedText}`)
    if (Number(res.factory_pending_orders || 0) > 0) filters.status = 'todo'
    page.value = 1
    selectedOrderNo.value = ''
    window.dispatchEvent(new CustomEvent('dealer-orders-updated'))
    await loadCloudSyncStatus()
    await loadOrders()
    if (channelsDialogVisible.value) void loadSyncChannels()
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '拉取云端订单失败')
  } finally {
    syncing.value = false
  }
}

const syncCloudInventory = async () => {
  inventorySyncing.value = true
  ElMessage.info('正在推送库存快照，请稍候…')
  try {
    const res = await apiPost<{ local_rows?: number; pushed_rows?: number }>('/dealer-orders/sync-wechat-batch-summary', {}, { timeout: 180_000 })
    ElMessage.success(`库存快照已推送：本地 ${res.local_rows || 0} 行，推送 ${res.pushed_rows || 0} 行`)
    if (channelsDialogVisible.value) void loadSyncChannels()
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '推送库存快照失败')
  } finally {
    inventorySyncing.value = false
  }
}

const syncMachineSnapshot = async () => {
  machineSyncing.value = true
  ElMessage.info('正在生成并上传机台快照，请稍候…')
  try {
    const res = await apiPost<{
      status?: string
      event_id?: string
      message?: string
      event_status?: { status?: string; last_error?: string } | null
    }>('/dealer-orders/sync-machine-snapshot', {}, { timeout: 180_000 })
    if (res.event_status?.status === 'failed') {
      ElMessage.warning(`${res.message || '机台快照已入队'}：${res.event_status.last_error || ''}`)
    } else {
      ElMessage.success(res.message || '机台快照同步完成')
    }
    if (channelsDialogVisible.value) void loadSyncChannels()
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '机台快照同步失败')
  } finally {
    machineSyncing.value = false
  }
}

const reconcileOrderStatus = async () => {
  try {
    const res = await apiPost<{ scanned?: number; enqueued?: number; window_days?: number }>(
      '/dealer-orders/reconcile-order-status',
      {},
      { timeout: 60_000 },
    )
    const scanned = res?.scanned ?? 0
    const enqueued = res?.enqueued ?? 0
    if (enqueued > 0) {
      ElMessage.success(`对账完成：扫描 ${scanned} 单，补发 ${enqueued} 单并已立即推送`)
    } else {
      ElMessage.success(`对账完成：扫描 ${scanned} 单，云端状态均已一致`)
    }
    if (channelsDialogVisible.value) void loadSyncChannels()
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '订单状态对账失败')
  }
}

let channelsTimer: any = null

const loadSyncChannels = async () => {
  channelsLoading.value = true
  try {
    const res = await apiGet<SyncChannelsResponse>('/dealer-orders/sync-channels')
    syncChannels.value = res.channels || []
    channelsServerTime.value = res.server_time || ''
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '读取同步通道状态失败')
  } finally {
    channelsLoading.value = false
  }
}

const openSyncChannels = async () => {
  channelsDialogVisible.value = true
  await loadSyncChannels()
  if (channelsTimer) clearInterval(channelsTimer)
  channelsTimer = setInterval(() => {
    if (channelsDialogVisible.value) void loadSyncChannels()
  }, 30_000)
}

const stopChannelsAutoRefresh = () => {
  if (channelsTimer) {
    clearInterval(channelsTimer)
    channelsTimer = null
  }
}

const runChannelAction = async (action: string) => {
  channelActionLoading.value = action
  try {
    if (action === 'pull-orders') await syncCloudOrders()
    else if (action === 'push-inventory') await syncCloudInventory()
    else if (action === 'push-machines') await syncMachineSnapshot()
    else if (action === 'reconcile-order-status') await reconcileOrderStatus()
  } finally {
    channelActionLoading.value = ''
    if (channelsDialogVisible.value) void loadSyncChannels()
  }
}

const channelStateTagType = (state: string) => {
  if (state === 'ok') return 'success'
  if (state === 'late' || state === 'pending') return 'warning'
  if (state === 'down' || state === 'failed') return 'danger'
  return 'info'
}

const formatOverdue = (seconds: number) => {
  const value = Number(seconds || 0)
  if (value >= 86400) return `${(value / 86400).toFixed(1)} 天`
  if (value >= 3600) return `${(value / 3600).toFixed(1)} 小时`
  if (value >= 60) return `${Math.round(value / 60)} 分钟`
  return `${value} 秒`
}

const approveOrder = async (row: DealerOrder) => {
  let res: { message?: string; warning?: string }
  try {
    const factoryPending = isFactoryPending(row)
    const note = await ElMessageBox.prompt(factoryPending ? '复审备注（可选）' : '审核备注（可选）', factoryPending ? '新备注复审通过' : '通过订单', {
      inputType: 'textarea',
      inputValue: row.remark || '',
      confirmButtonText: '通过',
      cancelButtonText: '取消',
    })
    const endpoint = factoryPending ? 'extra-review/approve' : 'approve'
    res = await apiPost<{ message?: string; warning?: string }>(`/dealer-orders/${encodeURIComponent(row.order_no)}/${endpoint}`, {
      note: note.value || '',
    })
  } catch (err: any) {
    if (err !== 'cancel') ElMessage.error(getApiErrorMessage(err) || '操作失败')
    return false
  }

  ElMessage.success(res.warning || res.message || (isFactoryPending(row) ? '新备注复审通过' : '已通过'))
  window.dispatchEvent(new CustomEvent('dealer-orders-updated'))
  try {
    await loadOrders()
    if (selectedOrderNo.value) {
      try {
        await loadPreview(selectedOrderNo.value)
      } catch {
        preview.value = null
      }
    }
  } catch {
    preview.value = null
    ElMessage.warning('订单已通过，但订单列表刷新失败')
  }
  return true
}

// 合同附件审批已并入订单行：点"预览并审批"只加载该订单自己的合同附件。
const contractReviewOrder = ref<DealerOrder | null>(null)

const openContractReview = async (row: DealerOrder) => {
  const target = (row as DealerOrderTableRow)._order || row
  // 新备注复审不是合同审批，沿用原来的直接通过。
  if (isFactoryPending(target) && canApprove(target)) {
    await approveOrder(target)
    return
  }
  contractReviewOrder.value = target
  await contractDraftReview.value?.openForOrder(target.order_no)
}

const approveContractReviewOrder = async (): Promise<boolean> => {
  const target = contractReviewOrder.value
  if (!target) throw new Error('未选择订单')
  await apiPost(`/dealer-orders/${encodeURIComponent(target.order_no)}/approve`, {
    note: String(target.remark || ''),
  })
  window.dispatchEvent(new CustomEvent('dealer-orders-updated'))
  void loadOrders(true)
  return true
}

const rejectContractReviewOrder = async (reason: string): Promise<boolean> => {
  const target = contractReviewOrder.value
  if (!target) throw new Error('未选择订单')
  // 订单与合同附件一起驳回；后端会把该订单未归档的草稿同步置为 rejected。
  await apiPost(`/dealer-orders/${encodeURIComponent(target.order_no)}/reject`, { reason })
  window.dispatchEvent(new CustomEvent('dealer-orders-updated'))
  void loadOrders(true)
  return true
}

const onContractReviewDone = async () => {
  contractReviewOrder.value = null
  await loadOrders()
  if (selectedOrderNo.value) {
    try {
      await loadPreview(selectedOrderNo.value)
    } catch {
      preview.value = null
    }
  }
}

const onApproveWithoutContract = async () => {
  const target = contractReviewOrder.value
  contractReviewOrder.value = null
  if (target) await approveOrder(target)
}

const rejectOrder = async (row: DealerOrder) => {
  try {
    const factoryPending = isFactoryPending(row)
    if (factoryPending) {
      await ElMessageBox.confirm(
        '驳回新备注复审后，系统会同步取消该经销商订单已绑定的合同和销售订单，并释放未出库的配货占用。已出库记录不会自动回滚。',
        '确认驳回并同步取消',
        {
          type: 'warning',
          confirmButtonText: '继续驳回',
          cancelButtonText: '取消',
        },
      )
    }
    const reason = await ElMessageBox.prompt(factoryPending ? '请输入新备注复审驳回原因' : '请输入驳回原因', factoryPending ? '新备注复审驳回' : '驳回订单', {
      inputType: 'textarea',
      confirmButtonText: '驳回',
      cancelButtonText: '取消',
      inputValidator: (value) => (String(value || '').trim() ? true : '驳回原因不能为空'),
    })
    const endpoint = factoryPending ? 'extra-review/reject' : 'reject'
    const res = await apiPost<{ message?: string; warning?: string }>(`/dealer-orders/${encodeURIComponent(row.order_no)}/${endpoint}`, {
      reason: reason.value,
    })
    ElMessage.success(res.warning || res.message || (factoryPending ? '新备注复审已驳回' : '已驳回'))
    window.dispatchEvent(new CustomEvent('dealer-orders-updated'))
    await loadOrders()
    if (selectedOrderNo.value) {
      try {
        await loadPreview(selectedOrderNo.value)
      } catch {
        preview.value = null
      }
    }
  } catch (err: any) {
    if (err !== 'cancel') ElMessage.error(getApiErrorMessage(err) || '操作失败')
  }
}

// ===== 经销商订单取消（一键释放配货 / 取消合同与销售订单 / 回传小程序） =====
const cancelDialogVisible = ref(false)
const cancelPreviewLoading = ref(false)
const cancelSubmitting = ref(false)
const cancelPreview = ref<DealerOrderCancelPreview | null>(null)
const cancelReason = ref('')

const cancelSerialRows = computed(() => (cancelPreview.value?.machines?.serials || [])
  .map((item) => String(item || '').trim())
  .filter(Boolean))

// 流水号过多时只展示前 10 个，其余折叠在「查看全部流水号」里。
const cancelSerialsSummary = computed(() => {
  const rows = cancelSerialRows.value
  if (!rows.length) return '-'
  if (rows.length <= 10) return rows.join('、')
  return `${rows.slice(0, 10).join('、')} 等 ${rows.length} 台`
})

const cancelListText = (items?: string[]) => {
  const list = (items || []).map((item) => String(item || '').trim()).filter(Boolean)
  return list.length ? list.join('、') : '-'
}

// 后端取消执行器的 released_serials / contracts / sales_orders 都是数组，兼容数字计数写法。
const countOf = (value: number | string[] | undefined) => (Array.isArray(value) ? value.length : Number(value || 0))

const buildCancelBlockerText = (data: DealerOrderCancelPreview) => {
  const segments: string[] = []
  const blockers = (data.blockers || []).map((item) => String(item || '').trim()).filter(Boolean)
  blockers.forEach((item, index) => segments.push(`${index + 1}. ${item}`))
  const shipped = (data.shipped_machines || []).map((item) => String(item || '').trim()).filter(Boolean)
  // 后端 blockers 里通常已带已出库明细与「发货复核→退换货处理」指引，避免重复拼接。
  const shippedHintIncluded = blockers.some((item) => item.includes('退换货') || item.includes('已出库') || item.includes('已发货'))
  if (shipped.length && !shippedHintIncluded) {
    segments.push(`已出库机台流水号：${shipped.join('、')}`)
    segments.push('请到「发货复核 → 退换货处理」完成已出库机台的退换货后再取消订单')
  }
  if (!segments.length) segments.push('该订单当前不可取消')
  return segments.join('；')
}

const openCancelDialog = async (row: DealerOrder) => {
  const target = (row as DealerOrderTableRow)._order || row
  const orderNo = String(target.order_no || '').trim()
  if (!orderNo || !canCancelDealerOrder(target)) {
    ElMessage.warning('当前订单状态不支持取消，仅已通过 / 已转合同 / 部分配货 / 已配货且无待审核新备注的订单可取消')
    return
  }
  if (cancelPreviewLoading.value) return
  cancelPreviewLoading.value = true
  try {
    const data = await apiGet<DealerOrderCancelPreview>(`/dealer-orders/${encodeURIComponent(orderNo)}/cancel-preview`)
    if (!data.cancellable) {
      await ElMessageBox.alert(buildCancelBlockerText(data), '该订单暂时无法取消', {
        type: 'warning',
        confirmButtonText: '知道了',
      }).catch(() => {})
      return
    }
    cancelPreview.value = data
    cancelReason.value = ''
    cancelDialogVisible.value = true
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '读取取消影响失败')
  } finally {
    cancelPreviewLoading.value = false
  }
}

const confirmCancelOrder = async () => {
  const data = cancelPreview.value
  if (!data || cancelSubmitting.value) return
  cancelSubmitting.value = true
  try {
    const res = await apiPost<DealerOrderCancelResponse>(`/dealer-orders/${encodeURIComponent(data.order_no)}/cancel`, {
      reason: cancelReason.value.trim(),
    })
    if (res.approval_pending) {
      ElMessage.info('已提交取消审批，审批通过后自动释放配货')
    } else if (String(res.status || '') !== 'cancelled') {
      // 执行异常/实例未自动执行：后端已标记流程异常并释放对象锁，但业务数据未变。
      ElMessage.warning(res.message || '取消未完成：流程执行异常，请联系管理员在审批中心重试或作废后重新发起')
    } else {
      const result = res.result || {}
      // released_serials / contracts / sales_orders 均为数组，取长度作为数量；兼容旧版数字计数。
      const released = countOf(result.released_serials)
      const contractCount = countOf(result.contracts)
      const salesOrderCount = countOf(result.sales_orders)
      const parts: string[] = []
      if (released > 0) parts.push(`已释放 ${released} 台机台`)
      if (contractCount > 0) parts.push(`取消 ${contractCount} 个合同`)
      if (salesOrderCount > 0) parts.push(`取消 ${salesOrderCount} 个销售订单`)
      parts.push('已回传小程序')
      ElMessage.success(parts.length > 1 ? parts.join('，') : res.message || '订单已取消，已回传小程序')
    }
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '取消订单失败')
    return
  } finally {
    cancelSubmitting.value = false
  }

  cancelDialogVisible.value = false
  cancelPreview.value = null
  window.dispatchEvent(new CustomEvent('dealer-orders-updated'))
  try {
    await loadOrders()
    if (drawerOpen.value && selectedOrderNo.value) {
      try {
        await loadPreview(selectedOrderNo.value)
      } catch {
        preview.value = null
      }
    }
  } catch {
    ElMessage.warning('订单已取消，但列表刷新失败，请手动刷新')
  }
}

type MessageResponse = {
  message?: string
  warning?: string
  contract_no?: string
  cloud_attachments?: CloudAttachmentSyncSummary
  order_form_attached_contracts?: string[]
  contracts?: Array<{ contract_no: string; path: 'auto' | 'batch-plan' | 'batch-plan-fallback' | 'preorder'; status?: '已规划' | '待规划' | '已转订单'; batch_nos: string[]; path_label: string; row_count: number; qty: number; models: string[] }>
}

const submitConvert = async () => {
  if (!hasText(convertForm.contractNo) || !hasText(convertForm.customer) || !hasText(convertForm.deliveryDate)) {
    ElMessage.warning('请先完整填写合同号、客户名、要求交期')
    return
  }
  const validItems = convertForm.items
    .map((item) => ({
      ...item,
      rowNote: [
        item.remark?.trim() ? `[备注]${item.remark.trim()}` : '',
        item.extraRemark?.trim() ? `[附加]${item.extraRemark.trim()}` : '',
        item.ermq > 0 ? `[改数]${item.ermq}` : '',
      ].filter(Boolean).join(' '),
    }))
    .filter((item) => hasText(item.model) && isPositiveInteger(item.qty))
  if (validItems.length === 0) {
    ElMessage.warning('请至少填写 1 条机型明细')
    return
  }
  const invalidModels = validItems.map((item) => item.model).filter((m) => !isModelInDictionary(m))
  if (invalidModels.length > 0) {
    ElMessage.warning(`以下机型不在字典中：${Array.from(new Set(invalidModels)).join('，')}`)
    return
  }

  convertSaving.value = true
  try {
    const payload = {
      contract_no: convertForm.contractNo.trim(),
      customer_name: convertForm.customer.trim(),
      agent_name: convertForm.agent.trim(),
      delivery_date: convertForm.deliveryDate.trim(),
      items: validItems,
      contract_note: convertForm.contractNote.trim(),
    }
    const res = await apiPost<MessageResponse>(`/dealer-orders/${encodeURIComponent(convertForm.sourceOrderNo)}/convert-to-contract`, payload)
    
    if ((res as any)?.approval_pending) {
      ElMessage.info((res as any).message)
      window.dispatchEvent(new Event('workflow-pending-updated'))
      return
    }
    // 上传附件（如果有选中文件）
    if (convertPickedFiles.value.length > 0) {
      const contractNoStr = res.contract_no || convertForm.contractNo || ''
      const contractIds = contractNoStr.split(/[、,]/).map((s) => s.trim()).filter(Boolean)
      for (const cid of contractIds) {
        for (const f of convertPickedFiles.value) {
          const fd = new FormData()
          fd.append('file', f)
          try {
            await apiPost(`/planning/contract/${encodeURIComponent(cid)}/files`, fd, {
              params: { customer_name: convertForm.customer.trim(), uploader_name: 'Web' },
              headers: { 'Content-Type': 'multipart/form-data' },
            })
          } catch (uploadErr: any) {
            console.error(`Failed to upload attachment ${f.name} to contract ${cid}:`, uploadErr)
            ElMessage.warning(`合同 ${cid} 附件 ${f.name} 上传失败，请稍后在合同管理中重新上传`)
          }
        }
      }
    }

    ElMessage.success(res.warning || res.message || '转合同成功')
    const cloudAttachmentNotice = buildCloudAttachmentNotice(res.cloud_attachments)
    if (cloudAttachmentNotice) {
      if (cloudAttachmentNotice.level === 'warning') ElMessage.warning(cloudAttachmentNotice.text)
      else ElMessage.success(cloudAttachmentNotice.text)
    }
    convertDialogVisible.value = false
    window.dispatchEvent(new CustomEvent('dealer-orders-updated'))
    await loadOrders()
    const contractList = res.contracts || []
    const hasAutoPlannedContract = contractList.some((c) => c.status === '已转订单')
    const hasPlannedContract = contractList.some((c) => c.status === '已规划')
    const hasPreorderContract = contractList.some((c) => c.status === '待规划' && c.path === 'preorder')
    if (hasAutoPlannedContract) {
      // 在制批次已自动预占，去订单配货完成二次确认。
      router.push({ path: '/order-allocation' })
    } else if (hasPlannedContract) {
      // 已规划合同由业务人员导入后到订单配货人工分配机台。
      router.push({ path: '/sales-orders', query: { tab: 'import' } })
    } else if (hasPreorderContract) {
      // 无货预订合同已置待规划，到合同管理查看并进入沙盘排产。
      router.push({ path: '/contracts' })
    }
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '经销商订单转合同失败')
  } finally {
    convertSaving.value = false
  }
}

let pollTimer: any = null

onMounted(async () => {
  await modelDictionaryStore.ensureLoaded()
  await loadTodoStats()
  if (todoStats.total > 0) {
    filters.status = 'todo'
  } else {
    try {
      const res = await apiGet<OrderListResponse>('/dealer-orders/', {
        params: {
          status: 'approved',
          page: 1,
          page_size: 1,
        },
      })
      if (Number(res.total || 0) > 0) {
        filters.status = 'approved'
      } else {
        filters.status = ''
      }
    } catch {
      filters.status = ''
    }
  }
  loadOrders()
  loadCloudSyncStatus()
  
  // 每 5 秒后台无感静默同步一次数据库数据
  pollTimer = setInterval(() => {
    if (!loading.value) {
      loadOrders(true)
    }
  }, 5000)
})

onUnmounted(() => {
  if (pollTimer) {
    clearInterval(pollTimer)
  }
  stopChannelsAutoRefresh()
})
</script>

<style scoped>
.dealer-review-page {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.filters {
  display: flex;
  align-items: center;
  gap: 8px;
}

.keyword {
  max-width: 360px;
}

.status-tabs {
  flex: 1;
  min-width: 520px;
}

.cloud-sync-strip,
.todo-summary {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 36px;
  padding: 8px 10px;
  border: 1px solid var(--color-gray-200);
  border-radius: var(--radius-sm);
  background: var(--color-gray-50);
  color: var(--color-gray-700);
  font-size: 13px;
}

.channels-hint {
  margin-bottom: 10px;
  color: var(--color-gray-600);
  font-size: 12px;
}

.channel-desc {
  color: var(--color-gray-500);
  font-size: 12px;
  line-height: 1.5;
}

.channel-trigger {
  margin-left: 6px;
}

.channel-overdue {
  color: #d97706;
}

.channel-failed {
  display: block;
  margin-top: 2px;
  color: #dc2626;
  font-size: 12px;
}

.todo-summary {
  gap: 16px;
  background: #fffbeb;
  color: var(--color-gray-800);
}

.todo-summary strong {
  margin-left: 4px;
  font-size: 16px;
}

.warning-count {
  color: #d97706;
}

.last-error {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pager-row {
  display: flex;
  justify-content: flex-end;
}

.danger {
  color: #dc2626;
  font-weight: 700;
}

.detail-grid {
  display: grid;
  grid-template-columns: 96px minmax(0, 1fr);
  gap: 10px 12px;
  align-items: start;
}

.detail-grid span,
.availability span {
  color: var(--color-gray-600);
}

.detail-grid strong {
  color: var(--color-gray-900);
  word-break: break-word;
}

.availability {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.availability div {
  border: 1px solid var(--color-gray-200);
  border-radius: var(--radius-sm);
  padding: 10px;
}

.availability strong {
  display: block;
  margin-top: 4px;
  font-size: 20px;
}

.note-title {
  margin-top: 12px;
  font-weight: 700;
}

.note-box {
  margin-top: 6px;
  padding: 10px;
  min-height: 44px;
  border: 1px solid var(--color-gray-200);
  border-radius: var(--radius-sm);
  background: var(--color-gray-50);
  white-space: pre-wrap;
  word-break: break-word;
}

.drawer-actions {
  display: flex;
  gap: 8px;
  margin-top: 18px;
}

.convert-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.ops-label {
  font-weight: 600;
  margin-bottom: 4px;
}

.form-table {
  margin-bottom: 8px;
}

.save-mode-section {
  margin-top: 16px;
}

.save-mode-hint {
  color: var(--color-gray-500);
  font-size: 13px;
  margin: 4px 0 8px;
}

.qty-highlight {
  font-weight: 700;
  color: #2563eb;
  background-color: #eff6ff;
  padding: 2px 8px;
  border-radius: 4px;
  display: inline-block;
  cursor: pointer;
  transition: all 0.2s ease;
}

.qty-highlight:hover {
  background-color: #dbeafe;
  transform: scale(1.05);
}

.qty-highlight.is-refreshing {
  cursor: not-allowed;
  opacity: 0.7;
}

.op-buttons {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 6px;
  flex-wrap: nowrap;
}

/* 四个操作按钮并排时避免文字被截断：去掉 Element Plus 相邻按钮默认的 12px 左边距，
   统一用 gap 控制间距，并允许按钮内文字不换行。 */
.op-buttons :deep(.el-button) {
  padding-left: 9px;
  padding-right: 9px;
  white-space: nowrap;
}

.op-buttons :deep(.el-button + .el-button) {
  margin-left: 0;
}

.cancel-grid {
  row-gap: 8px;
}

.cancel-serial-summary {
  padding: 8px 10px;
  border: 1px solid var(--color-gray-200);
  border-radius: var(--radius-sm);
  background: var(--color-gray-50);
  color: var(--color-gray-800);
  word-break: break-word;
}

.cancel-serial-collapse {
  margin-top: 4px;
  --el-collapse-header-height: 32px;
}

.cancel-serial-list {
  max-height: 140px;
  overflow-y: auto;
  color: var(--color-gray-700);
  word-break: break-word;
}

.cancel-warnings {
  margin-top: 10px;
  padding: 8px 10px;
  border: 1px solid #fde68a;
  border-radius: var(--radius-sm);
  background: #fffbeb;
  color: #b45309;
  font-size: 13px;
  line-height: 1.6;
  word-break: break-word;
}

.cancel-danger-hint {
  margin-top: 10px;
  padding: 10px;
  border: 1px solid #fecaca;
  border-radius: var(--radius-sm);
  background: #fef2f2;
  color: #b91c1c;
  font-size: 13px;
  line-height: 1.6;
}

.cancel-reason-label {
  margin-top: 14px;
}
</style>
