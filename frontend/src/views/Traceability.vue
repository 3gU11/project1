<template>
  <div class="traceability-page">
    <PageHeader title="🔍 汇总与追溯" :small="true" />
    
    <el-card class="mb-4">
      <template #header>
        <div class="card-header">
          <span>1. 全局搜索</span>
        </div>
      </template>
      <el-row :gutter="20">
        <el-col :span="16">
          <el-input
            v-model="searchKeyword"
            placeholder="输入流水号、客户、代理商、合同号或订单号，例如: 95-04-222, 吴龙, HT-2026..."
            clearable
            @keyup.enter="handleSearch"
          >
            <template #append>
              <el-button @click="handleSearch">搜索</el-button>
            </template>
          </el-input>
        </el-col>
      </el-row>
      
      <div v-if="hasSearched" class="mt-4">
        <el-table
          :data="summaryList"
          v-loading="loading"
          border
          stripe
          max-height="300"
          @row-click="onSummaryRowClick"
        >
          <el-table-column prop="机型" label="机型" min-width="140" />
          <el-table-column prop="状态" label="状态" width="120" />
          <el-table-column prop="流水号" label="流水号" min-width="140" />
          <el-table-column prop="机台状态" label="机台状态" min-width="180" />
          <el-table-column prop="客户" label="客户" min-width="220" />
          <el-table-column prop="代理商" label="代理商" width="120" />
          <el-table-column prop="预计入库时间" label="预计入库时间" width="180" />
        </el-table>
        <div v-if="summaryList.length === 0 && !loading" class="text-gray-500 mt-2">未找到相关数据。</div>
      </div>
    </el-card>

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
                    <p>流水号: {{ log.流水号 || '-' }}</p>
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
import { computed, ref } from 'vue'
import { apiGet, getApiErrorMessage } from '../utils/request'
import PageHeader from '../components/PageHeader.vue'

const searchKeyword = ref('')
const hasSearched = ref(false)
const loading = ref(false)
const summaryList = ref<any[]>([])

const targetId = ref('')
const targetContractNo = ref('')
const targetOrderNo = ref('')
const selectedModel = ref('')
const detailLoading = ref(false)
const statusList = ref<any[]>([])
const timelineList = ref<any[]>([])
const expandedGroups = ref<string[]>([])

const groupedTimeline = computed(() => {
  const groups = new Map<string, { action: string; count: number; latestAt: string; items: any[] }>()
  for (const log of timelineList.value) {
    const action = String(log?.action || '未知操作')
    const createdAt = String(log?.created_at || '')
    if (!groups.has(action)) {
      groups.set(action, { action, count: 0, latestAt: createdAt, items: [] })
    }
    const group = groups.get(action)!
    group.items.push(log)
    group.count += 1
    if (!group.latestAt) group.latestAt = createdAt
  }
  return Array.from(groups.values())
})

const getTraceTarget = (row: any) => {
  const sn = String(row?.流水号 || '').trim()
  if (sn) return sn
  const orderId = String(row?.订单号 || '').trim()
  if (orderId) return orderId
  return String(row?.合同号 || '').trim()
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
</style>
