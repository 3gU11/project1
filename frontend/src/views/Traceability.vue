<template>
  <div class="traceability-page">
    <div class="search-hero">
      <div class="hero-header">
        <h1 class="hero-title">🔍 汇总与追溯</h1>
        <p class="hero-subtitle">全局搜索流水号、客户、代理商、合同号或订单号进行全链路深度追溯</p>
      </div>

      <div class="search-box-wrapper">
        <el-input
          v-model="searchKeyword"
          placeholder="例如: 95-04-222, 吴龙, HT-2026..."
          class="hero-search-input"
          clearable
          @keyup.enter="handleSearch"
        >
          <template #append>
            <el-button type="primary" @click="handleSearch">搜 索</el-button>
          </template>
        </el-input>
      </div>

      <div v-if="hasSearched" class="search-result-area">
        <el-table
          :data="summaryList"
          :key="lastSearchWasSerial ? 'serial-view' : 'summary-view'"
          v-loading="loading"
          border
          stripe
          class="elegant-table"
          max-height="400"
          @row-click="onSummaryRowClick"
        >
          <el-table-column prop="机型" label="机型" min-width="160" />
          <el-table-column prop="状态" label="状态" width="120" />
          <el-table-column label="流水号" min-width="160" show-overflow-tooltip>
            <template #default="{ row }">
              <span v-if="row.流水号">{{ row.流水号 }}</span>
              <span v-else class="text-gray-400">-</span>
            </template>
          </el-table-column>
          <el-table-column prop="机台状态" label="机台状态" width="120" />
          <el-table-column prop="客户" label="客户" min-width="180" />
          <el-table-column prop="代理商" label="代理商" width="120" />
          <el-table-column prop="要求交期" label="合同要求交期" width="140" />
          <el-table-column prop="发货时间" label="订单发货时间" width="120" />
          <el-table-column v-if="!lastSearchWasSerial" label="合同附件" width="110" align="center">
            <template #default="{ row }">
              <el-popover
                v-if="row.合同号"
                :visible="visiblePopover === row.合同号"
                placement="bottom"
                :width="220"
                trigger="contextmenu"
              >
                <template #reference>
                  <el-button
                    type="primary"
                    link
                    :icon="Download"
                    @click.stop="handleSmartDownload(row.合同号)"
                    :loading="filesLoadingMap[row.合同号]"
                  >
                    下载
                  </el-button>
                </template>
                <div v-click-outside="() => visiblePopover = ''" class="popover-file-list">
                  <div class="popover-tip">请选择要下载的文件：</div>
                  <div
                    v-for="file in filesMap[row.合同号]"
                    :key="file.file_name"
                    class="file-item"
                    @click="handleFileItemClick(row.合同号, file.file_name)"
                  >
                    <el-icon><Document /></el-icon>
                    <span class="file-name">{{ file.file_name }}</span>
                  </div>
                </div>
              </el-popover>
              <span v-else>-</span>
            </template>
          </el-table-column>
        </el-table>
        <div v-if="summaryList.length === 0 && !loading" class="text-gray-500 mt-2">未找到相关数据。</div>
      </div>
    </div>

    <el-card v-if="targetId">
      <template #header>
        <div class="card-header">
          <span>
            2. 追溯目标：<strong>{{ targetContractNo || '-' }}</strong>
            <template v-if="targetOrderNo"> （关联单号：<strong>{{ targetOrderNo }}</strong>）</template>
          </span>
        </div>
      </template>
      
      <el-row :gutter="20" v-loading="detailLoading">
        <el-col :span="8">
          <h4 class="status-title">📊 实时状态分布</h4>
          <div v-if="statusList.length > 0" class="status-metrics">
            <el-card v-for="item in statusList" :key="item.状态" shadow="hover" class="metric-card">
              <el-statistic :title="`${selectedModel || '机型'} - ${item.状态}`" :value="item.数量" />
            </el-card>
          </div>
          <div v-else class="text-gray-500">暂无关联的机台库存状态。</div>
        </el-col>
        
        <el-col :span="16">
          <h4>⏱ 时间轴 (流转历史)</h4>
          <el-collapse v-if="groupedTimeline.length > 0" v-model="expandedGroups">
            <el-collapse-item
              v-for="(group, idx) in groupedTimeline"
              :key="group.action"
              :name="group.action + '_' + idx"
            >
              <template #title>
                <div class="group-title">
                  <span class="group-action">{{ group.action }}</span>
                  <span class="group-meta">共 {{ group.count }} 条，最近：{{ group.latestAt || '-' }}</span>
                </div>
              </template>

              <el-timeline>
                <el-timeline-item
                  v-for="(log, index) in group.items"
                  :key="`${group.action}-${index}`"
                  :timestamp="log.created_at"
                  placement="top"
                >
                  <el-card>
                    <h4>{{ log.action }}</h4>
                    <p>操作人: {{ log.operator || '系统' }}</p>
                    <p v-if="log.contract_no">合同号: <span class="font-bold">{{ log.contract_no }}</span></p>
                    <p v-if="log.order_no">订单号: <span class="font-bold">{{ log.order_no }}</span></p>
                    <p v-if="log.流水号">{{ isOrderAction(log.action, log.流水号) ? '单号' : '流水号' }}: {{ log.流水号 }}</p>
                    <div v-if="log.content" class="log-content-box">
                      <span class="content-label">详情:</span>
                      <div class="content-text">{{ log.content }}</div>
                    </div>
                    <p class="text-xs text-gray-400">日志 ID: {{ log.id || '-' }}</p>
                  </el-card>
                </el-timeline-item>
              </el-timeline>
            </el-collapse-item>
          </el-collapse>
          <div v-else class="text-gray-500">暂无流转记录。</div>
        </el-col>
      </el-row>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, reactive } from 'vue'
import { ElMessage, ClickOutside as vClickOutside } from 'element-plus'
import { Download, Document } from '@element-plus/icons-vue'
import { apiGet, apiDownloadBlob, getApiErrorMessage } from '../utils/request'
import PageHeader from '../components/PageHeader.vue'

const searchKeyword = ref('')
const hasSearched = ref(false)
const loading = ref(false)
const summaryList = ref<any[]>([])
const lastSearchWasSerial = ref(false)

const targetId = ref('')
const targetContractNo = ref('')
const targetOrderNo = ref('')
const selectedModel = ref('')
const detailLoading = ref(false)
const statusList = ref<any[]>([])
const timelineList = ref<any[]>([])
const expandedGroups = ref<string[]>([])

// 附件下载相关
const filesMap = reactive<Record<string, any[]>>({})
const filesLoadingMap = reactive<Record<string, boolean>>({})
const visiblePopover = ref('')

const handleSmartDownload = async (contractId: string) => {
  if (filesMap[contractId]) {
    processDownload(contractId)
    return
  }
  
  filesLoadingMap[contractId] = true
  try {
    const res = await apiGet(`/planning/contract/${encodeURIComponent(contractId)}/files`)
    const files = res.data || []
    filesMap[contractId] = files
    processDownload(contractId)
  } catch (e) {
    ElMessage.error('获取附件失败')
  } finally {
    filesLoadingMap[contractId] = false
  }
}

const processDownload = (contractId: string) => {
  const files = filesMap[contractId] || []
  if (files.length === 0) {
    ElMessage.warning('该合同暂无附件')
    return
  }
  if (files.length === 1) {
    doDownload(contractId, files[0].file_name)
  } else {
    // 多个文件，打开气泡选择
    visiblePopover.value = contractId
  }
}

const handleFileItemClick = (contractId: string, fileName: string) => {
  visiblePopover.value = ''
  doDownload(contractId, fileName)
}

const doDownload = async (contractId: string, fileName: string) => {
  try {
    await apiDownloadBlob(
      `/planning/contract/${encodeURIComponent(contractId)}/files/${encodeURIComponent(fileName)}/download`,
      fileName
    )
    ElMessage.success(`${fileName} 下载完成`)
  } catch (e) {
    ElMessage.error(getApiErrorMessage(e) || '文件下载失败，请稍后重试')
  }
}

const groupedTimeline = computed(() => {
  const groups = new Map<string, { action: string; count: number; latestAt: string; items: any[] }>()
  for (const log of timelineList.value) {
    const action = String(log?.action || '未知操作')
    const createdAt = String(log?.created_at || '')
    if (!groups.has(action)) {
      groups.set(action, { action, count: 0, latestAt: '', items: [] })
    }
    const group = groups.get(action)!
    group.items.push(log)
    group.count += 1
    if (createdAt && (!group.latestAt || createdAt > group.latestAt)) {
      group.latestAt = createdAt
    }
  }
  // Sort groups by latest timestamp ascending (earliest action group first)
  const result = Array.from(groups.values())
  result.sort((a, b) => (a.latestAt || '').localeCompare(b.latestAt || ''))
  // Sort items within each group by created_at ascending
  for (const g of result) {
    g.items.sort((x: any, y: any) => String(x.created_at || '').localeCompare(String(y.created_at || '')))
  }
  return result
})

const getTraceTarget = (row: any) => {
  const sn = String(row?.流水号 || '').trim()
  if (sn) return sn
  const orderId = String(row?.订单号 || '').trim()
  if (orderId) return orderId
  return String(row?.合同号 || '').trim()
}

const isOrderAction = (actionName: string, sn: string) => {
  const n = String(actionName || '')
  const s = String(sn || '')
  if (s.startsWith('SO-') || s.startsWith('HT')) return true
  return n.includes('合同') || n.includes('订单') || n.includes('批量录入') || n === '新增' || n === '修改'
}

const onSummaryRowClick = (row: any) => {
  const target = getTraceTarget(row)
  if (!target) return
  
  const sn = String(row?.流水号 || '').trim()
  if (sn) {
    targetContractNo.value = sn // 复用这块区域展示流水号
    targetOrderNo.value = String(row?.订单号 || '').trim()
  } else {
    targetContractNo.value = String(row?.合同号 || '').trim()
    targetOrderNo.value = String(row?.订单号 || '').trim()
  }
  selectedModel.value = String(row?.机型 || '').trim()
  handleTrace(target, selectedModel.value)
}

const handleSearch = async () => {
  const keyword = searchKeyword.value.trim()
  if (!keyword) return
  loading.value = true
  hasSearched.value = true
  try {
    const params = new URLSearchParams()
    params.set('keyword', keyword)
    // 提前识别搜索类型，防止渲染刷新过慢
    lastSearchWasSerial.value = /^\d/.test(keyword)

    const res = await apiGet(`/traceability/search?${params.toString()}`)
    summaryList.value = res.data || []
  } catch (e: any) {
    summaryList.value = []
    ElMessage.error(getApiErrorMessage(e) || '追溯搜索失败')
  } finally {
    loading.value = false
  }
}

const handleTrace = async (id: string, model = '') => {
  targetId.value = id
  detailLoading.value = true
  try {
    const [statusRes, timelineRes] = await Promise.all([
      apiGet(`/traceability/${encodeURIComponent(id)}/status?model=${encodeURIComponent(model)}`),
      apiGet(`/traceability/${encodeURIComponent(id)}/timeline`)
    ])
    statusList.value = statusRes.data || []
    timelineList.value = timelineRes.data || []
    expandedGroups.value = []
  } catch (e) {
    statusList.value = []
    timelineList.value = []
    expandedGroups.value = []
  } finally {
    detailLoading.value = false
  }
}
</script>

<style scoped>
.traceability-page {
  padding-bottom: 40px;
}
.mb-4 {
  margin-bottom: 16px;
}
.mt-4 {
  margin-top: 16px;
}
.mt-2 {
  margin-top: var(--space-2);
}
.text-gray-500 {
  color: #909399;
}
.text-gray-400 {
  color: #c0c4cc;
}
.text-xs {
  font-size: var(--font-size-sm);
}
.status-metrics {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.metric-card {
  text-align: center;
}
.status-title {
  text-align: center;
}
.group-title {
  display: flex;
  gap: var(--space-3);
  align-items: center;
}
.group-action {
  font-weight: 600;
  color: var(--color-gray-800);
}
.group-meta {
  font-size: var(--font-size-sm);
  color: var(--color-gray-500);
}
.search-hero {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 48px 24px 40px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.9) 0%, rgba(250, 251, 253, 0.6) 100%);
  border-radius: 20px;
  box-shadow: 0 4px 24px rgba(0,0,0,0.03);
  border: 1px solid rgba(0,0,0,0.04);
  margin-bottom: 24px;
}
.hero-title {
  margin: 0;
  font-size: 36px;
  font-weight: 800;
  color: var(--color-gray-900);
}
.hero-subtitle {
  margin: 12px 0 32px;
  font-size: 16px;
  color: var(--color-gray-500);
}
.search-box-wrapper {
  width: 100%;
  max-width: 680px;
}
.hero-search-input :deep(.el-input__wrapper) {
  min-height: 56px !important;
  border-radius: 28px 0 0 28px !important;
  font-size: 16px !important;
  box-shadow: inset 0 0 0 1.5px var(--border-color-strong) !important;
  padding: 0 24px !important;
  transition: all 0.3s ease;
}
.hero-search-input :deep(.el-input__wrapper.is-focus) {
  box-shadow: inset 0 0 0 2px var(--color-primary-500) !important;
}
.hero-search-input :deep(.el-input-group__append) {
  border-radius: 0 28px 28px 0 !important;
  background-color: var(--color-primary-500);
  color: white;
  border: none;
  box-shadow: none !important;
  padding: 0 32px;
  font-weight: 700;
  font-size: 16px;
  min-width: 100px;
}
.search-result-area {
  margin-top: 32px;
  width: 100%;
}
.elegant-table {
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 4px 16px rgba(0,0,0,0.06);
}
.log-content-box {
  margin-top: 8px;
  margin-bottom: 8px;
  background: var(--color-gray-50);
  border: 1px solid var(--border-color-light);
  border-radius: var(--radius-sm);
  padding: 8px 12px;
}
.content-label {
  font-size: 12px;
  color: var(--color-gray-500);
  font-weight: 600;
  display: block;
  margin-bottom: 4px;
}
.content-text {
  font-size: 13px;
  color: var(--color-gray-800);
  white-space: pre-wrap;
  line-height: 1.5;
  word-break: break-all;
}

.popover-file-list {
  min-height: 40px;
}
.popover-tip {
  font-size: 12px;
  color: var(--color-gray-500);
  padding: 4px 8px 8px;
  border-bottom: 1px solid var(--border-color-light);
  margin-bottom: 4px;
}
.file-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px;
  cursor: pointer;
  border-radius: 4px;
  transition: background 0.2s;
}
.file-item:hover {
  background: var(--color-primary-50);
  color: var(--color-primary-600);
}
.file-name {
  font-size: 13px;
  word-break: break-all;
}
.no-files {
  padding: 12px;
  text-align: center;
  color: var(--color-gray-400);
  font-size: 13px;
}
</style>
