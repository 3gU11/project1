<template>
  <div class="report-management">
    <h2 class="page-title">📊 报表管理</h2>

    <!-- Tab Navigation -->
    <el-tabs v-model="activeTab" type="card" class="report-tabs">
      <!-- Tab 1: 完工报表（产出统计） -->
      <el-tab-pane label="✅ 完工报表" name="completion">
        <div class="report-content">
          <div class="report-desc-box">
            <p class="report-desc">📊 统计所选时间段内产出的机台数量</p>
            <div class="report-detail">
              <p><strong>统计说明：</strong></p>
              <ul>
                <li>统计所有产出并入库的机台</li>
                <li>包含所有入库方式：手动入库、配货自动入库</li>
                <li>数据来源：入库历史记录（完整、准确、可追溯）</li>
                <li>适用于产量统计和财务对账</li>
              </ul>
            </div>
          </div>
          <el-form :model="completionForm" label-width="100px" class="report-form">
            <el-row :gutter="20">
              <el-col :span="6">
                <el-form-item label="查询方式">
                  <el-radio-group v-model="completionForm.queryType">
                    <el-radio value="daterange">日期范围</el-radio>
                    <el-radio value="month">按月份</el-radio>
                  </el-radio-group>
                </el-form-item>
              </el-col>
              <el-col :span="6">
                <el-form-item label="日期范围" required v-if="completionForm.queryType === 'daterange'">
                  <el-date-picker
                    v-model="completionForm.dateRange"
                    type="daterange"
                    range-separator="至"
                    start-placeholder="开始日期"
                    end-placeholder="结束日期"
                    value-format="YYYY-MM-DD"
                    style="width: 100%"
                  />
                </el-form-item>
                <el-form-item label="选择月份" required v-else>
                  <el-date-picker
                    v-model="completionForm.month"
                    type="month"
                    placeholder="选择月份"
                    value-format="YYYY-MM"
                    style="width: 100%"
                  />
                </el-form-item>
              </el-col>
              <el-col :span="4">
                <el-form-item label="机型">
                  <el-select v-model="completionForm.modelType" clearable placeholder="全部机型" style="width: 100%">
                    <el-option v-for="m in availableModels" :key="m" :label="m" :value="m" />
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :span="4">
                <el-form-item label="客户">
                  <el-select v-model="completionForm.customer" clearable placeholder="全部客户" filterable style="width: 100%">
                    <el-option v-for="c in availableCustomers" :key="c" :label="c" :value="c" />
                  </el-select>
                </el-form-item>
              </el-col>
            </el-row>
            <el-form-item>
              <el-button type="primary" @click="queryCompletionReport" :loading="completionLoading" size="large">
                查询
              </el-button>
              <el-button type="success" @click="exportCompletionReport" :loading="completionLoading" :disabled="!completionData.length" size="large">
                导出Excel
              </el-button>
            </el-form-item>
          </el-form>

          <!-- Data Preview Table -->
          <div v-if="completionData.length > 0" class="data-preview">
            <h3 class="preview-title">数据预览 (共 {{ completionData.length }} 种机型，总产量: {{ totalQuantity }} 台)</h3>
            <el-table :data="completionData" border stripe max-height="500" show-summary :summary-method="getSummaries">
              <el-table-column prop="机型" label="机型" min-width="250" />
              <el-table-column prop="数量" label="数量" width="150" align="center" />
              <el-table-column prop="占比" label="占总产量百分比" width="180" align="center" />
            </el-table>

            <!-- Model Category Summary -->
            <div class="category-summary">
              <h4 class="category-title">机型大类汇总</h4>
              <el-table :data="categorySummary" border stripe>
                <el-table-column prop="类别" label="机型大类" width="200" />
                <el-table-column prop="数量" label="数量" width="150" align="center" />
                <el-table-column prop="占比" label="占总产量百分比" width="180" align="center" />
              </el-table>
            </div>
          </div>
        </div>
      </el-tab-pane>

      <!-- Tab 2: 订单报表 -->
      <el-tab-pane label="📋 订单报表" name="order">
        <div class="report-content">
          <p class="report-desc">销售订单分析，包含履约状态</p>
          <el-form :model="orderForm" label-width="100px" class="report-form">
            <el-row :gutter="20">
              <el-col :span="6">
                <el-form-item label="查询方式">
                  <el-radio-group v-model="orderForm.queryType">
                    <el-radio value="daterange">日期范围</el-radio>
                    <el-radio value="month">按月份</el-radio>
                  </el-radio-group>
                </el-form-item>
              </el-col>
              <el-col :span="6">
                <el-form-item label="日期范围" required v-if="orderForm.queryType === 'daterange'">
                  <el-date-picker
                    v-model="orderForm.dateRange"
                    type="daterange"
                    range-separator="至"
                    start-placeholder="开始日期"
                    end-placeholder="结束日期"
                    value-format="YYYY-MM-DD"
                    style="width: 100%"
                  />
                </el-form-item>
                <el-form-item label="选择月份" required v-else>
                  <el-date-picker
                    v-model="orderForm.month"
                    type="month"
                    placeholder="选择月份"
                    value-format="YYYY-MM"
                    style="width: 100%"
                  />
                </el-form-item>
              </el-col>
              <el-col :span="4">
                <el-form-item label="客户">
                  <el-select v-model="orderForm.customer" clearable placeholder="全部客户" filterable style="width: 100%">
                    <el-option v-for="c in availableCustomers" :key="c" :label="c" :value="c" />
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :span="4">
                <el-form-item label="代理商">
                  <el-select v-model="orderForm.dealer" clearable placeholder="全部代理商" filterable style="width: 100%">
                    <el-option v-for="d in availableDealers" :key="d" :label="d" :value="d" />
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :span="4">
                <el-form-item label="状态">
                  <el-select v-model="orderForm.status" clearable placeholder="全部状态" style="width: 100%">
                    <el-option label="进行中" value="active" />
                    <el-option label="已完结" value="done" />
                    <el-option label="已删除" value="deleted" />
                  </el-select>
                </el-form-item>
              </el-col>
            </el-row>
            <el-form-item>
              <el-button type="primary" @click="queryOrderReport" :loading="orderLoading" size="large">
                查询
              </el-button>
              <el-button type="success" @click="exportOrderReport" :loading="orderLoading" :disabled="!orderData.length" size="large">
                导出Excel
              </el-button>
            </el-form-item>
          </el-form>

          <!-- Data Preview Table -->
          <div v-if="orderData.length > 0" class="data-preview">
            <h3 class="preview-title">数据预览 (共 {{ orderData.length }} 条)</h3>
            <el-table :data="orderData" border stripe max-height="500">
              <el-table-column prop="订单号" label="订单号" width="180" />
              <el-table-column prop="下单日期" label="下单日期" width="120" />
              <el-table-column prop="客户名" label="客户名" min-width="150" />
              <el-table-column prop="代理商" label="代理商" min-width="150" />
              <el-table-column prop="需求机型" label="需求机型" width="150" />
              <el-table-column prop="需求数量" label="需求数量" width="100" align="center" />
              <el-table-column prop="订单状态" label="订单状态" width="100" />
            </el-table>
            <ReportAppendices :appendices="orderAppendices" :dealer-summary="orderDealerSummary" />
          </div>
        </div>
      </el-tab-pane>

      <!-- Tab 3: 出货报表 -->
      <el-tab-pane label="🚚 出货报表" name="shipment">
        <div class="report-content">
          <p class="report-desc">出货历史追踪，包含历史和当前出货数据</p>
          <el-form :model="shipmentForm" label-width="100px" class="report-form">
            <el-row :gutter="20">
              <el-col :span="6">
                <el-form-item label="查询方式">
                  <el-radio-group v-model="shipmentForm.queryType">
                    <el-radio value="daterange">日期范围</el-radio>
                    <el-radio value="month">按月份</el-radio>
                  </el-radio-group>
                </el-form-item>
              </el-col>
              <el-col :span="6">
                <el-form-item label="日期范围" required v-if="shipmentForm.queryType === 'daterange'">
                  <el-date-picker
                    v-model="shipmentForm.dateRange"
                    type="daterange"
                    range-separator="至"
                    start-placeholder="开始日期"
                    end-placeholder="结束日期"
                    value-format="YYYY-MM-DD"
                    style="width: 100%"
                  />
                </el-form-item>
                <el-form-item label="选择月份" required v-else>
                  <el-date-picker
                    v-model="shipmentForm.month"
                    type="month"
                    placeholder="选择月份"
                    value-format="YYYY-MM"
                    style="width: 100%"
                  />
                </el-form-item>
              </el-col>
              <el-col :span="4">
                <el-form-item label="客户">
                  <el-select v-model="shipmentForm.customer" clearable placeholder="全部客户" filterable style="width: 100%">
                    <el-option v-for="c in availableCustomers" :key="c" :label="c" :value="c" />
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :span="4">
                <el-form-item label="代理商">
                  <el-select v-model="shipmentForm.dealer" clearable placeholder="全部代理商" filterable style="width: 100%">
                    <el-option v-for="d in availableDealers" :key="d" :label="d" :value="d" />
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :span="4">
                <el-form-item label="机型">
                  <el-select v-model="shipmentForm.modelType" clearable placeholder="全部机型" style="width: 100%">
                    <el-option v-for="m in availableModels" :key="m" :label="m" :value="m" />
                  </el-select>
                </el-form-item>
              </el-col>
            </el-row>
            <el-form-item>
              <el-button type="primary" @click="queryShipmentReport" :loading="shipmentLoading" size="large">
                查询
              </el-button>
              <el-button type="success" @click="exportShipmentReport" :loading="shipmentLoading" :disabled="!shipmentData.length" size="large">
                导出Excel
              </el-button>
            </el-form-item>
          </el-form>

          <!-- Data Preview Table -->
          <div v-if="shipmentData.length > 0" class="data-preview">
            <h3 class="preview-title">数据预览 (共 {{ shipmentData.length }} 条)</h3>
            <el-table :data="shipmentData" border stripe max-height="500">
              <el-table-column prop="出货日期" label="出货日期" width="120" />
              <el-table-column prop="客户" label="客户" min-width="150" />
              <el-table-column prop="代理商" label="代理商" min-width="150" />
              <el-table-column prop="机型" label="机型" width="150" />
              <el-table-column prop="出货数量" label="出货数量" width="100" align="center" />
              <el-table-column prop="订单号" label="订单号" width="180" />
              <el-table-column prop="合同号" label="合同号" min-width="150" />
              <el-table-column prop="批次号" label="批次号" width="150" />
            </el-table>
            <ReportAppendices :appendices="shipmentAppendices" />
          </div>
        </div>
      </el-tab-pane>

      <!-- Tab 4: 跟踪单 -->
      <el-tab-pane label="📝 跟踪单" name="tracking">
        <div class="report-content">
          <p class="report-desc">生产跟踪单，包含批次和机台编号</p>
          <el-alert type="info" :closable="false" show-icon style="margin-bottom: 20px">
            此报表已在生产看板中实现，点击下方按钮直接生成
          </el-alert>
          <el-button type="primary" @click="generateTrackingSheet" :loading="trackingLoading" size="large">
            生成跟踪单
          </el-button>
        </div>
      </el-tab-pane>

      <!-- Tab 6: 生产报表 -->
      <el-tab-pane label="🏭 生产报表" name="production">
        <div class="report-content">
          <p class="report-desc">排产台账，包含批次和机型汇总</p>
          <el-alert type="info" :closable="false" show-icon style="margin-bottom: 20px">
            此报表已在生产看板中实现，点击下方按钮直接生成
          </el-alert>
          <el-button type="primary" @click="generateProductionReport" :loading="productionLoading" size="large">
            生成生产报表
          </el-button>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { apiGet, apiDownloadBlob } from '../utils/request'
import ReportAppendices from '../components/ReportAppendices.vue'

// Active tab
const activeTab = ref('completion')

// Form data
const inboundForm = ref({
  queryType: 'month',
  dateRange: [] as string[],
  month: '',
  modelType: '',
  customer: ''
})

const orderForm = ref({
  queryType: 'month',
  dateRange: [] as string[],
  month: '',
  customer: '',
  dealer: '',
  status: ''
})

const shipmentForm = ref({
  queryType: 'month',
  dateRange: [] as string[],
  month: '',
  customer: '',
  dealer: '',
  modelType: ''
})

const completionForm = ref({
  queryType: 'month',
  dateRange: [] as string[],
  month: '',
  modelType: '',
  customer: ''
})

// Loading states
const inboundLoading = ref(false)
const orderLoading = ref(false)
const shipmentLoading = ref(false)
const completionLoading = ref(false)
const trackingLoading = ref(false)
const productionLoading = ref(false)

// Data states for preview
const inboundData = ref<any[]>([])
const orderData = ref<any[]>([])
const shipmentData = ref<any[]>([])
const completionData = ref<any[]>([])
const orderAppendices = ref<Record<string, any[]>>({})
const shipmentAppendices = ref<Record<string, any[]>>({})
const orderDealerSummary = ref<any[]>([])

// Computed total quantity for completion report
const totalQuantity = computed(() => {
  return completionData.value.reduce((sum, item) => sum + (item.数量 || 0), 0)
})

// Extract model category from model name using model dictionary
const getModelCategory = (modelName: string): string => {
  if (!modelName) return '其他'

  // Get category from model dictionary (model_family)
  const category = modelCategoryMap.value.get(modelName.trim())
  if (category) return category

  // If not found in dictionary, return '其他'
  return '其他'
}

// Computed category summary
const categorySummary = computed(() => {
  const categoryMap = new Map<string, number>()

  completionData.value.forEach(item => {
    const category = getModelCategory(item.机型)
    const count = item.数量 || 0
    categoryMap.set(category, (categoryMap.get(category) || 0) + count)
  })

  const total = totalQuantity.value
  const result = Array.from(categoryMap.entries()).map(([category, count]) => ({
    类别: category,
    数量: count,
    占比: total > 0 ? `${(count / total * 100).toFixed(2)}%` : '0%'
  }))

  // Sort by quantity descending
  result.sort((a, b) => b.数量 - a.数量)

  return result
})

// Summary method for completion table
const getSummaries = (param: any) => {
  const { columns, data } = param
  const sums: string[] = []
  columns.forEach((column: any, index: number) => {
    if (index === 0) {
      sums[index] = '总计'
      return
    }
    if (column.property === '数量') {
      const values = data.map((item: any) => Number(item[column.property]))
      sums[index] = values.reduce((prev: number, curr: number) => prev + curr, 0).toString()
    } else if (column.property === '占比') {
      sums[index] = '100%'
    } else {
      sums[index] = ''
    }
  })
  return sums
}

// Filter options
const availableCustomers = ref<string[]>([])
const availableDealers = ref<string[]>([])
const availableModels = ref<string[]>([])

// Model dictionary for category mapping
const modelDictionary = ref<any[]>([])
const modelCategoryMap = ref<Map<string, string>>(new Map())
const modelSortOrderMap = ref<Map<string, number>>(new Map())

// Load filter options
const loadFilterOptions = async () => {
  try {
    const res = await apiGet<{customers: string[], dealers: string[], models: string[]}>('/reports/filters')
    availableCustomers.value = res.customers || []
    availableDealers.value = res.dealers || []
    availableModels.value = res.models || []
  } catch (error) {
    console.error('Failed to load filter options:', error)
  }
}

// Load model dictionary for category mapping
const loadModelDictionary = async () => {
  try {
    const res = await apiGet<{data: any[]}>('/model-dictionary/')
    modelDictionary.value = res.data || []

    // Build category map: model_name -> model_family
    const categoryMap = new Map<string, string>()
    const sortOrderMap = new Map<string, number>()

    modelDictionary.value.forEach(item => {
      const modelName = String(item.model_name || '').trim()
      const family = String(item.model_family || '').trim()
      const sortOrder = Number(item.sort_order || 0)

      if (modelName) {
        if (family) {
          categoryMap.set(modelName, family)
        }
        sortOrderMap.set(modelName, sortOrder)
      }
    })

    modelCategoryMap.value = categoryMap
    modelSortOrderMap.value = sortOrderMap
  } catch (error) {
    console.error('Failed to load model dictionary:', error)
  }
}

// Helper function to get date range from form
const getDateRange = (queryType: string, dateRange: string[], month: string): [string, string] | null => {
  if (queryType === 'daterange') {
    if (!dateRange || dateRange.length !== 2) {
      return null
    }
    return [dateRange[0], dateRange[1]]
  } else {
    if (!month) {
      return null
    }
    const year = parseInt(month.split('-')[0])
    const monthNum = parseInt(month.split('-')[1])
    const startDate = `${year}-${String(monthNum).padStart(2, '0')}-01`
    const lastDay = new Date(year, monthNum, 0).getDate()
    const endDate = `${year}-${String(monthNum).padStart(2, '0')}-${String(lastDay).padStart(2, '0')}`
    return [startDate, endDate]
  }
}

// Query functions (fetch data for preview)
const queryInboundReport = async () => {
  const dateRange = getDateRange(inboundForm.value.queryType, inboundForm.value.dateRange, inboundForm.value.month)
  if (!dateRange) {
    ElMessage.warning(inboundForm.value.queryType === 'daterange' ? '请选择日期范围' : '请选择月份')
    return
  }

  const [startDate, endDate] = dateRange
  inboundLoading.value = true
  try {
    const params = new URLSearchParams({
      start_date: startDate,
      end_date: endDate,
      model_type: inboundForm.value.modelType || '',
      customer: inboundForm.value.customer || '',
      format: 'json'
    })

    const res = await apiGet<{data: any[], total: number}>(`/reports/inbound?${params.toString()}`)
    inboundData.value = res.data || []
    ElMessage.success(`查询成功，共 ${res.total} 条数据`)
  } catch (error) {
    ElMessage.error('查询失败')
    inboundData.value = []
  } finally {
    inboundLoading.value = false
  }
}

const queryOrderReport = async () => {
  const dateRange = getDateRange(orderForm.value.queryType, orderForm.value.dateRange, orderForm.value.month)
  if (!dateRange) {
    ElMessage.warning(orderForm.value.queryType === 'daterange' ? '请选择日期范围' : '请选择月份')
    return
  }

  const [startDate, endDate] = dateRange
  orderLoading.value = true
  try {
    const params = new URLSearchParams({
      start_date: startDate,
      end_date: endDate,
      customer: orderForm.value.customer || '',
      dealer: orderForm.value.dealer || '',
      status: orderForm.value.status || '',
      format: 'json'
    })

    const res = await apiGet<{data: any[], total: number, appendices?: Record<string, any[]>, dealer_summary?: any[]}>(`/reports/orders?${params.toString()}`)
    orderData.value = res.data || []
    orderAppendices.value = res.appendices || {}
    orderDealerSummary.value = res.dealer_summary || []
    ElMessage.success(`查询成功，共 ${res.total} 条数据`)
  } catch (error) {
    ElMessage.error('查询失败')
    orderData.value = []
    orderAppendices.value = {}
    orderDealerSummary.value = []
  } finally {
    orderLoading.value = false
  }
}

const queryShipmentReport = async () => {
  const dateRange = getDateRange(shipmentForm.value.queryType, shipmentForm.value.dateRange, shipmentForm.value.month)
  if (!dateRange) {
    ElMessage.warning(shipmentForm.value.queryType === 'daterange' ? '请选择日期范围' : '请选择月份')
    return
  }

  const [startDate, endDate] = dateRange
  shipmentLoading.value = true
  try {
    const params = new URLSearchParams({
      start_date: startDate,
      end_date: endDate,
      customer: shipmentForm.value.customer || '',
      dealer: shipmentForm.value.dealer || '',
      model_type: shipmentForm.value.modelType || '',
      format: 'json'
    })

    const res = await apiGet<{data: any[], total: number, appendices?: Record<string, any[]>}>(`/reports/shipments?${params.toString()}`)
    shipmentData.value = res.data || []
    shipmentAppendices.value = res.appendices || {}
    ElMessage.success(`查询成功，共 ${res.total} 条数据`)
  } catch (error) {
    ElMessage.error('查询失败')
    shipmentData.value = []
    shipmentAppendices.value = {}
  } finally {
    shipmentLoading.value = false
  }
}

const queryCompletionReport = async () => {
  const dateRange = getDateRange(completionForm.value.queryType, completionForm.value.dateRange, completionForm.value.month)
  if (!dateRange) {
    ElMessage.warning(completionForm.value.queryType === 'daterange' ? '请选择日期范围' : '请选择月份')
    return
  }

  const [startDate, endDate] = dateRange
  completionLoading.value = true
  try {
    const params = new URLSearchParams({
      start_date: startDate,
      end_date: endDate,
      model_type: completionForm.value.modelType || '',
      customer: completionForm.value.customer || '',
      format: 'json'
    })

    const res = await apiGet<{data: any[], total: number}>(`/reports/completions?${params.toString()}`)
    completionData.value = res.data || []
    ElMessage.success(`查询成功，共 ${res.total} 条数据`)
  } catch (error) {
    ElMessage.error('查询失败')
    completionData.value = []
  } finally {
    completionLoading.value = false
  }
}

// Export functions (download Excel)
const exportInboundReport = async () => {
  const dateRange = getDateRange(inboundForm.value.queryType, inboundForm.value.dateRange, inboundForm.value.month)
  if (!dateRange) {
    ElMessage.warning(inboundForm.value.queryType === 'daterange' ? '请选择日期范围' : '请选择月份')
    return
  }

  const [startDate, endDate] = dateRange
  inboundLoading.value = true
  try {
    const params = new URLSearchParams({
      start_date: startDate,
      end_date: endDate,
      model_type: inboundForm.value.modelType || '',
      customer: inboundForm.value.customer || '',
      format: 'excel'
    })

    await apiDownloadBlob(`/reports/inbound?${params.toString()}`, `入库报表_${startDate}_${endDate}.xlsx`)
    ElMessage.success('入库报表导出成功')
  } catch (error) {
    ElMessage.error('导出失败')
  } finally {
    inboundLoading.value = false
  }
}

const exportOrderReport = async () => {
  const dateRange = getDateRange(orderForm.value.queryType, orderForm.value.dateRange, orderForm.value.month)
  if (!dateRange) {
    ElMessage.warning(orderForm.value.queryType === 'daterange' ? '请选择日期范围' : '请选择月份')
    return
  }

  const [startDate, endDate] = dateRange
  orderLoading.value = true
  try {
    const params = new URLSearchParams({
      start_date: startDate,
      end_date: endDate,
      customer: orderForm.value.customer || '',
      dealer: orderForm.value.dealer || '',
      status: orderForm.value.status || '',
      format: 'excel'
    })

    await apiDownloadBlob(`/reports/orders?${params.toString()}`, `订单报表_${startDate}_${endDate}.xlsx`)
    ElMessage.success('订单报表导出成功')
  } catch (error) {
    ElMessage.error('导出失败')
  } finally {
    orderLoading.value = false
  }
}

const exportShipmentReport = async () => {
  const dateRange = getDateRange(shipmentForm.value.queryType, shipmentForm.value.dateRange, shipmentForm.value.month)
  if (!dateRange) {
    ElMessage.warning(shipmentForm.value.queryType === 'daterange' ? '请选择日期范围' : '请选择月份')
    return
  }

  const [startDate, endDate] = dateRange
  shipmentLoading.value = true
  try {
    const params = new URLSearchParams({
      start_date: startDate,
      end_date: endDate,
      customer: shipmentForm.value.customer || '',
      dealer: shipmentForm.value.dealer || '',
      model_type: shipmentForm.value.modelType || '',
      format: 'excel'
    })

    await apiDownloadBlob(`/reports/shipments?${params.toString()}`, `出货报表_${startDate}_${endDate}.xlsx`)
    ElMessage.success('出货报表导出成功')
  } catch (error) {
    ElMessage.error('导出失败')
  } finally {
    shipmentLoading.value = false
  }
}

const exportCompletionReport = async () => {
  const dateRange = getDateRange(completionForm.value.queryType, completionForm.value.dateRange, completionForm.value.month)
  if (!dateRange) {
    ElMessage.warning(completionForm.value.queryType === 'daterange' ? '请选择日期范围' : '请选择月份')
    return
  }

  const [startDate, endDate] = dateRange
  completionLoading.value = true
  try {
    const params = new URLSearchParams({
      start_date: startDate,
      end_date: endDate,
      model_type: completionForm.value.modelType || '',
      customer: completionForm.value.customer || '',
      format: 'excel'
    })

    await apiDownloadBlob(`/reports/completions?${params.toString()}`, `完工报表_${startDate}_${endDate}.xlsx`)
    ElMessage.success('完工报表导出成功')
  } catch (error) {
    ElMessage.error('导出失败')
  } finally {
    completionLoading.value = false
  }
}

// Report generation functions (legacy - kept for tracking and production reports)
const generateTrackingSheet = async () => {
  trackingLoading.value = true
  try {
    await apiDownloadBlob('/planning/export-production-history?sheet=tracking', `生产跟踪单_${new Date().toISOString().slice(0, 10)}.xlsx`)
    ElMessage.success('跟踪单生成成功')
  } catch (error) {
    ElMessage.error('生成报表失败')
  } finally {
    trackingLoading.value = false
  }
}

const generateProductionReport = async () => {
  productionLoading.value = true
  try {
    await apiDownloadBlob('/planning/export-production-history?sheet=ledger', `排产台账_${new Date().toISOString().slice(0, 10)}.xlsx`)
    ElMessage.success('生产报表生成成功')
  } catch (error) {
    ElMessage.error('生成报表失败')
  } finally {
    productionLoading.value = false
  }
}

onMounted(() => {
  loadFilterOptions()
  loadModelDictionary()
})
</script>

<style scoped>
.report-management {
  padding: 24px;
  max-width: 1400px;
  margin: 0 auto;
}

.page-title {
  font-size: 24px;
  font-weight: 600;
  margin-bottom: 24px;
  color: #1f2937;
}

.report-tabs {
  background: white;
  border-radius: 8px;
  padding: 20px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.report-content {
  padding: 20px 0;
}

.report-desc {
  color: #6b7280;
  font-size: 14px;
  margin-bottom: 24px;
  line-height: 1.5;
}

.report-desc-box {
  background: #f0f9ff;
  border-left: 4px solid #3b82f6;
  padding: 16px;
  margin-bottom: 20px;
  border-radius: 4px;
}

.report-desc-box .report-desc {
  font-size: 15px;
  font-weight: 600;
  color: #1e40af;
  margin-bottom: 12px;
}

.report-desc-box .report-detail {
  font-size: 13px;
  color: #475569;
}

.report-desc-box .report-detail p {
  margin: 0 0 8px 0;
  font-weight: 600;
}

.report-desc-box .report-detail ul {
  margin: 0;
  padding-left: 20px;
}

.report-desc-box .report-detail li {
  margin: 4px 0;
  line-height: 1.6;
}

.report-form {
  max-width: 100%;
}

:deep(.el-tabs__item) {
  font-size: 15px;
  padding: 0 24px;
  height: 44px;
  line-height: 44px;
}

:deep(.el-tabs__nav) {
  border: none;
}

:deep(.el-tabs__item.is-active) {
  background: #0a73fb;
  color: white;
  border-radius: 6px 6px 0 0;
}

:deep(.el-tabs__item:hover) {
  color: #0a73fb;
}

:deep(.el-tabs__item.is-active:hover) {
  color: white;
}

@media (max-width: 768px) {
  .report-management {
    padding: 16px;
  }

  :deep(.el-tabs__item) {
    padding: 0 12px;
    font-size: 13px;
  }

  .report-form :deep(.el-col) {
    margin-bottom: 12px;
  }
}

.category-summary {
  margin-top: 30px;
  padding: 20px;
  background: #f8fafc;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
}

.category-title {
  font-size: 16px;
  font-weight: 600;
  color: #1f2937;
  margin: 0 0 16px 0;
}

.data-preview {
  margin-top: 20px;
}

.preview-title {
  font-size: 15px;
  font-weight: 600;
  color: #374151;
  margin-bottom: 12px;
}

</style>
