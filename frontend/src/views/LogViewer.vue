<template>
  <div class="page">
    <div class="head">
      <h1>📜 系统日志中心</h1>
      <el-button type="primary" :loading="loading" @click="refreshLogs">刷新数据</el-button>
    </div>
    <div class="tip">当前仅展示近 14 天日志，支持分页和虚拟滚动浏览。</div>

    <el-tabs v-model="activeTab">
      <el-tab-pane v-if="canViewAudit" label="操作日志" name="audit" />
      <el-tab-pane label="系统日志" name="transaction" />
    </el-tabs>

    <div v-if="activeTab === 'audit'" class="filters audit-filters">
      <el-input v-model="auditFilters.user" placeholder="按姓名搜索" clearable />
      <el-input v-model="auditFilters.module" placeholder="按模块搜索" clearable />
      <el-input v-model="auditFilters.operation" placeholder="按操作类型搜索" clearable />
      <el-input v-model="auditFilters.bizType" placeholder="按业务对象搜索" clearable />
      <el-input v-model="auditFilters.serialNo" placeholder="按流水号搜索" clearable />
      <el-input v-model="auditFilters.contractNo" placeholder="按合同号搜索" clearable />
      <el-input v-model="auditFilters.orderNo" placeholder="按订单号搜索" clearable />
    </div>

    <div v-if="activeTab === 'transaction'" class="vtable tlog">
      <div class="vhead">
        <div class="c time">时间</div>
        <div class="c type">操作类型</div>
        <div class="c sn">流水号</div>
        <div class="c user">操作员</div>
      </div>
      <VirtualScrollList :items="transactionLogs" :height="620" :item-height="44" item-key="__rowKey" :overscan="10">
        <template #default="{ item }">
          <div class="vrow">
            <div class="c time">{{ item['时间'] || '-' }}</div>
            <div class="c type">{{ item['操作类型'] || '-' }}</div>
            <div class="c sn">{{ item['流水号'] || '-' }}</div>
            <div class="c user">{{ item['操作员'] || '-' }}</div>
          </div>
        </template>
      </VirtualScrollList>
    </div>

    <div v-else class="vtable alog">
      <div class="vhead">
        <div class="c time">时间</div>
        <div class="c user">姓名</div>
        <div class="c module">模块</div>
        <div class="c biz">业务对象</div>
        <div class="c op">操作类型</div>
        <div class="c detail">操作内容</div>
      </div>
      <VirtualScrollList :items="auditLogs" :height="620" :item-height="52" item-key="__rowKey" :overscan="10">
        <template #default="{ item }">
          <div class="vrow audit-row">
            <div class="c time">{{ item['时间'] || '-' }}</div>
            <div class="c user">{{ item['姓名'] || '-' }}</div>
            <div class="c module">{{ item['模块'] || '-' }}</div>
            <div class="c biz">{{ item['业务对象'] || '-' }}</div>
            <div class="c op">{{ item['操作类型'] || '-' }}</div>
            <div class="c detail" :title="item['操作内容'] || ''">{{ item['操作内容'] || '-' }}</div>
          </div>
        </template>
      </VirtualScrollList>
    </div>

    <div class="pager">
      <el-pagination
        :current-page="pager.page"
        :page-size="pager.pageSize"
        :page-sizes="[20, 50, 100]"
        :total="pager.total"
        layout="total, sizes, prev, pager, next"
        @update:current-page="onPageChange"
        @update:page-size="onPageSizeChange"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { apiGet, getApiErrorMessage } from '../utils/request'
import VirtualScrollList from '../components/VirtualScrollList.vue'
import { useUserStore } from '../store/user'

type ListResponse<T = any> = { data: T[]; total: number; page: number; page_size: number; days: number }
const LOG_DAYS = 14

const userStore = useUserStore()
const canViewAudit = ref(userStore.userInfo?.role === 'Admin' || userStore.userInfo?.role === 'Boss')

const loading = ref(false)
const activeTab = ref<'transaction' | 'audit'>(canViewAudit.value ? 'audit' : 'transaction')
const transactionLogs = ref<any[]>([])
const auditLogs = ref<any[]>([])
const hasLoadedTransaction = ref(false)
const transactionCache = new Map<string, { data: any[]; total: number }>()
const auditFilters = reactive({
  user: '',
  module: '',
  operation: '',
  bizType: '',
  serialNo: '',
  contractNo: '',
  orderNo: '',
})
const auditCache = new Map<string, { data: any[]; total: number }>()
const pager = reactive({
  page: 1,
  pageSize: 50,
  total: 0,
})
let auditFilterTimer: ReturnType<typeof setTimeout> | null = null

const normalizeTransactionLogs = (rows: any[]) => {
  return (rows || []).map((row, idx) => ({
    ...row,
    __rowKey: [
      pager.page,
      idx,
      String(row?.['时间'] || ''),
      String(row?.['操作类型'] || ''),
      String(row?.['流水号'] || ''),
      String(row?.['操作员'] || ''),
    ].join('::'),
  }))
}

const normalizeAuditLogs = (rows: any[]) => {
  return (rows || []).map((row, idx) => ({
    ...row,
    __rowKey: [
      pager.page,
      idx,
      String(row?.['时间'] || ''),
      String(row?.['姓名'] || ''),
      String(row?.['模块'] || ''),
      String(row?.['业务对象'] || ''),
      String(row?.['操作类型'] || ''),
      String(row?.['操作内容'] || ''),
    ].join('::'),
  }))
}

const getTransactionCacheKey = () => JSON.stringify({ page: pager.page, pageSize: pager.pageSize, days: LOG_DAYS })

const getAuditCacheKey = () => {
  return JSON.stringify({
    page: pager.page,
    pageSize: pager.pageSize,
    days: LOG_DAYS,
    user: auditFilters.user.trim(),
    module: auditFilters.module.trim(),
    operation: auditFilters.operation.trim(),
    bizType: auditFilters.bizType.trim(),
    serialNo: auditFilters.serialNo.trim(),
    contractNo: auditFilters.contractNo.trim(),
    orderNo: auditFilters.orderNo.trim(),
  })
}

const loadLogs = async (force = false) => {
  const currentTab = activeTab.value
  if (currentTab === 'transaction' && !force) {
    const cached = transactionCache.get(getTransactionCacheKey())
    if (cached) {
      transactionLogs.value = cached.data
      pager.total = cached.total
      hasLoadedTransaction.value = true
      return
    }
  }
  if (currentTab === 'audit' && !force) {
    const cached = auditCache.get(getAuditCacheKey())
    if (cached) {
      auditLogs.value = cached.data
      pager.total = cached.total
      return
    }
  }
  loading.value = true
  try {
    if (currentTab === 'transaction') {
      const res = await apiGet<ListResponse>('/logs/transactions', {
        params: { page: pager.page, page_size: pager.pageSize, days: LOG_DAYS },
      })
      transactionLogs.value = normalizeTransactionLogs(res.data || [])
      pager.total = Number(res.total || 0)
      hasLoadedTransaction.value = true
      transactionCache.set(getTransactionCacheKey(), { data: transactionLogs.value, total: pager.total })
    } else {
      const cacheKey = getAuditCacheKey()
      const res = await apiGet<ListResponse>('/logs/audit', {
        params: {
          page: pager.page,
          page_size: pager.pageSize,
          days: LOG_DAYS,
          user: auditFilters.user.trim(),
          module: auditFilters.module.trim(),
          operation: auditFilters.operation.trim(),
          biz_type: auditFilters.bizType.trim(),
          serial_no: auditFilters.serialNo.trim(),
          contract_no: auditFilters.contractNo.trim(),
          order_no: auditFilters.orderNo.trim(),
        },
      })
      auditLogs.value = normalizeAuditLogs(res.data || [])
      pager.total = Number(res.total || 0)
      auditCache.set(cacheKey, { data: auditLogs.value, total: pager.total })
    }
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '读取日志失败')
  } finally {
    loading.value = false
  }
}

watch(activeTab, () => {
  pager.page = 1
  loadLogs()
})

watch(
  () => [
    auditFilters.user,
    auditFilters.module,
    auditFilters.operation,
    auditFilters.bizType,
    auditFilters.serialNo,
    auditFilters.contractNo,
    auditFilters.orderNo,
  ],
  () => {
    if (activeTab.value !== 'audit') return
    if (auditFilterTimer) clearTimeout(auditFilterTimer)
    auditFilterTimer = setTimeout(() => {
      pager.page = 1
      loadLogs()
    }, 300)
  },
)

const onPageChange = (page: number) => {
  pager.page = page
  loadLogs()
}

const onPageSizeChange = (size: number) => {
  pager.pageSize = size
  pager.page = 1
  loadLogs()
}

const refreshLogs = () => {
  if (activeTab.value === 'transaction') {
    hasLoadedTransaction.value = false
    transactionCache.clear()
  } else {
    auditCache.clear()
  }
  loadLogs(true)
}

onBeforeUnmount(() => {
  if (auditFilterTimer) clearTimeout(auditFilterTimer)
})

loadLogs()
</script>

<style scoped>
.head{display:flex;justify-content:space-between;align-items:center;margin-bottom: var(--space-2)}.head h1{margin:0;font-size:30px}
.tip{margin-bottom:var(--space-2);color:var(--color-gray-500)}
.filters{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:var(--space-2);margin-bottom:var(--space-2)}
.audit-filters{grid-template-columns:repeat(4,minmax(0,1fr))}
.vtable{border:1px solid var(--el-border-color);border-radius:8px;overflow:hidden;background:#fff}
.vhead,.vrow{display:grid;align-items:center}
.vhead{background:var(--color-gray-50);font-weight:600;border-bottom:1px solid var(--el-border-color)}
.vrow{border-bottom:1px solid var(--el-border-color-lighter);min-height:44px}
.audit-row{min-height:52px}
.c{padding:10px 12px;font-size:14px;color:var(--color-gray-700);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.tlog .vhead,.tlog .vrow{grid-template-columns:180px 180px 1fr 140px}
.alog .vhead,.alog .vrow{grid-template-columns:180px 120px 140px 120px 140px minmax(320px,1fr)}
.detail{white-space:normal;word-break:break-all;line-height:1.4}
.pager{display:flex;justify-content:flex-end;margin-top:var(--space-2)}
</style>
