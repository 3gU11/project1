<template>
  <div ref="pageRef" class="screen" :class="{ 'fullscreen-mode': isFullscreen }">
    <template v-if="!isFullscreen">
      <div class="top-bar">
        <div class="title-wrap">
          <div class="title-icon">库</div>
          <div>
            <h1 class="main-title">数字化智能化大屏 · 库位可视化</h1>
            <div class="sub-title">管理员：{{ userNameText }} · 当前时间：{{ nowText }}</div>
          </div>
        </div>
        <div class="head-actions">
          <el-button @click="goHome">返回主页</el-button>
          <el-button @click="layoutDrawerVisible = true">布局配置</el-button>
          <el-button @click="toggleFullscreen">进入全屏</el-button>
          <el-button type="primary" :loading="loading" @click="loadData(true)">刷新</el-button>
        </div>
      </div>

      <div class="metric-row">
        <div class="metric-card idle">
          <div class="metric-label">空闲</div>
          <div class="metric-value">{{ summary.idle }}</div>
        </div>
        <div class="metric-card occupied">
          <div class="metric-label">占用</div>
          <div class="metric-value">{{ summary.occupied }}</div>
        </div>
        <div class="metric-card full">
          <div class="metric-label">满载</div>
          <div class="metric-value">{{ summary.full }}</div>
        </div>
        <div class="metric-card locked">
          <div class="metric-label">锁定/异常</div>
          <div class="metric-value">{{ summary.locked }}</div>
        </div>
      </div>

      <div class="tool-row">
        <div class="tool-item">总计 {{ slotCards.length }} 个库位</div>
        <div class="tool-item">区域数 {{ groupedSlotSections.length }}</div>
        <div class="tool-search">
          <span>搜索库位</span>
          <el-input v-model="searchKeyword" placeholder="A01 / 流水号" clearable />
        </div>
      </div>
      <el-alert
        v-if="loadError"
        class="load-error"
        type="error"
        :closable="false"
        :title="loadError"
        show-icon
      >
        <template #default>
          <el-button size="small" @click="retryLoadData">重试</el-button>
        </template>
      </el-alert>
    </template>

    <PageSkeleton v-if="showInitialSkeleton && !isFullscreen" :blocks="10" min-height="360px" />
    <div v-else class="board-body" :class="{ fullscreen: isFullscreen }">
      <template v-if="isFullscreen">
        <div class="fs-top">
          <div class="fs-metric idle"><span>空闲</span><strong>{{ summary.idle }}</strong></div>
          <div class="fs-metric occupied"><span>占用</span><strong>{{ summary.occupied }}</strong></div>
          <div class="fs-metric full"><span>满载</span><strong>{{ summary.full }}</strong></div>
          <div class="fs-metric locked"><span>锁定/异常</span><strong>{{ summary.locked }}</strong></div>
        </div>
        <div class="fs-meta">管理员：{{ userNameText }}&nbsp;&nbsp; 当前时间：{{ nowText }}</div>

        <section v-for="section in groupedSlotSections" :key="`fs-${section.zone}`" class="zone-section fs-zone-section">
          <div class="zone-title">{{ section.zone }} 区 · {{ section.items.length }} 个库位</div>
          <div class="slot-grid fullscreen-grid">
            <button
              v-for="s in section.items"
              :key="s.code"
              type="button"
              class="slot-card"
              :class="s.statusClass"
              :style="slotStyle(s)"
              @click="handleSlotClick(s)"
            >
              <div class="card-head">
                <div class="code">{{ s.code }}</div>
                <div class="badge" :class="s.statusClass">{{ s.statusText }}</div>
              </div>
              <div class="count-row"><span class="count-num">{{ s.count }}</span><span class="count-max">/ {{ maxCap }}</span></div>
              <div class="bar"><div class="bar-inner" :class="s.statusClass" :style="{ width: `${Math.min(100, (s.count / maxCap) * 100)}%` }" /></div>
              <div class="sns">
                <div v-for="sn in s.serialNos.slice(0, 5)" :key="`${s.code}-${sn}`" class="sn-item">{{ sn }}</div>
                <div v-if="s.serialNos.length === 0" class="sn-item empty">暂无库存</div>
              </div>
            </button>
          </div>
        </section>
      </template>

      <template v-else>
        <section v-for="section in groupedSlotSections" :key="section.zone" class="zone-section">
          <div class="zone-title">{{ section.zone }} 区 · {{ section.items.length }} 个库位</div>
          <div class="slot-grid">
            <button
              v-for="s in section.items"
              :key="s.code"
              type="button"
              class="slot-card"
              :class="s.statusClass"
              :style="slotStyle(s)"
              @click="handleSlotClick(s)"
            >
              <div class="card-head">
                <div class="code">{{ s.code }}</div>
                <div class="badge" :class="s.statusClass">{{ s.statusText }}</div>
              </div>
              <div class="count-row"><span class="count-num">{{ s.count }}</span><span class="count-max">/ {{ maxCap }}</span></div>
              <div class="bar"><div class="bar-inner" :class="s.statusClass" :style="{ width: `${Math.min(100, (s.count / maxCap) * 100)}%` }" /></div>
              <div class="sns">
                <div v-for="sn in s.serialNos.slice(0, 5)" :key="`${s.code}-${sn}`" class="sn-item">{{ sn }}</div>
                <div v-if="s.serialNos.length === 0" class="sn-item empty">暂无库存</div>
              </div>
            </button>
          </div>
        </section>
      </template>
    </div>

    <div v-if="!isFullscreen" class="bottom-legend">
      <span class="dot full" /> 满载
      <span class="dot occupied" /> 占用
      <span class="dot idle" /> 空闲
      <span class="dot locked" /> 锁定/异常
    </div>

    <el-drawer v-model="layoutDrawerVisible" title="库位布局与自动生成" size="360px">
      <div class="panel-title">自动生成布局</div>
      <div class="label">生成模式</div>
      <el-radio-group v-model="layoutMode">
        <el-radio value="row">按行生成（Z字形）</el-radio>
        <el-radio value="col">按列生成（N字形）</el-radio>
      </el-radio-group>
      <el-row :gutter="8" style="margin-top: 8px">
        <el-col :span="12">
          <div class="label">行数</div>
          <el-input-number v-model="layoutRows" :min="1" />
        </el-col>
        <el-col :span="12">
          <div class="label">列数</div>
          <el-input-number v-model="layoutCols" :min="1" />
        </el-col>
      </el-row>
      <div class="label" style="margin-top: 8px">区域前缀（如: A）</div>
      <el-input v-model="layoutPrefix" placeholder="A" />
      <div class="label" style="margin-top: 8px">允许存放机型（逗号分隔）</div>
      <el-input v-model="allowedModels" placeholder="留空不限" />
      <el-checkbox v-model="appendLayout" style="margin-top: 8px">追加到现有布局</el-checkbox>
      <div style="margin-top: 10px">
        <el-button type="primary" :loading="savingLayout" @click="generateLayout">生成布局</el-button>
      </div>
    </el-drawer>

    <el-dialog v-if="!isFullscreen" v-model="dialogVisible" :title="`库位操作: ${currentSlot?.code || ''}`" width="920px">
      <div v-if="currentSlot">
        <el-tabs v-model="dialogTab">
          <el-tab-pane label="在库明细" name="detail">
            <el-table :data="currentSlotMachines" border stripe size="small" height="260">
              <el-table-column prop="流水号" label="流水号" width="170" />
              <el-table-column prop="机型" label="机型" width="140" />
              <el-table-column prop="预计入库时间" label="预计入库时间" width="130" />
              <el-table-column prop="更新时间" label="更新时间" width="160" />
              <el-table-column prop="机台备注/配置" label="机台备注/配置" min-width="180" />
            </el-table>
          </el-tab-pane>
          <el-tab-pane label="存入机台（入库）" name="inbound">
            <div class="label">机台流水号</div>
            <el-input v-model="directSn" placeholder="请输入待入库流水号" />
            <div class="inline-tip" v-if="currentSlot?.statusClass === 'locked'">当前库位为锁定/异常，禁止入库</div>
            <div class="inline-tip" v-else-if="currentSlot?.statusClass === 'full'">当前库位满载，禁止入库</div>
          </el-tab-pane>
          <el-tab-pane label="移出机台（调拨）" name="transfer">
            <el-row :gutter="10">
              <el-col :span="12">
                <div class="label">调拨机台（流水号）</div>
                <el-select v-model="transferSn" clearable placeholder="选择当前库位机台">
                  <el-option v-for="sn in currentSlotSns" :key="sn" :label="sn" :value="sn" />
                </el-select>
              </el-col>
              <el-col :span="12">
                <div class="label">目标库位</div>
                <el-select v-model="targetSlot" clearable placeholder="选择目标库位">
                  <el-option v-for="s in availableTargetSlots" :key="s" :label="s" :value="s" />
                </el-select>
              </el-col>
            </el-row>
          </el-tab-pane>
        </el-tabs>
      </div>
      <template #footer>
        <el-button
          v-if="dialogTab === 'inbound'"
          :loading="saving"
          :disabled="!canInbound"
          type="primary"
          @click="doDirectInbound"
        >确认入库</el-button>
        <el-button
          v-else-if="dialogTab === 'transfer'"
          :loading="saving"
          :disabled="!canTransfer"
          type="primary"
          @click="doTransfer"
        >确认调拨</el-button>
        <el-button v-else @click="dialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { onBeforeRouteLeave, useRouter } from 'vue-router'
import { apiGet, apiGetAll, apiPost, getApiErrorMessage } from '../utils/request'
import PageSkeleton from '../components/PageSkeleton.vue'
import { useCacheStore } from '../store/cache'
import {
  exitFullscreenCompat,
  formatTimeHMS,
  fullscreenChangeEventNames,
  getFullscreenElementCompat,
  requestFullscreenCompat,
} from '../utils/compat'

type Slot = Record<string, any>
type Row = Record<string, any>
type LayoutResponse = { layout_json?: { slots?: Slot[] } }
const router = useRouter()
const maxCap = 5
const cacheStore = useCacheStore()
const loading = ref(false)
const saving = ref(false)
const savingLayout = ref(false)
const loadError = ref('')
const loadedOnce = ref(false)
const isFullscreen = ref(false)
const slots = ref<Slot[]>([])
const inventory = ref<Row[]>([])
const dialogVisible = ref(false)
const currentSlot = ref<Slot | null>(null)
const directSn = ref('')
const transferSn = ref('')
const targetSlot = ref('')
const dialogTab = ref<'detail' | 'inbound' | 'transfer'>('detail')
const layoutMode = ref<'row' | 'col'>('row')
const layoutRows = ref(3)
const layoutCols = ref(4)
const layoutPrefix = ref('A')
const allowedModels = ref('')
const appendLayout = ref(false)
const layoutDrawerVisible = ref(false)
const searchKeyword = ref('')
const nowText = ref('')
const pageRef = ref<HTMLElement | null>(null)
const userNameText = localStorage.getItem('username') || 'Admin'
let clockTimer: number | null = null

const slotCards = computed(() => {
  const fallbackCols = 4
  const fallbackBaseX = 20
  const fallbackBaseY = 20
  const fallbackW = 300
  const fallbackH = 160
  const fallbackGapX = 40
  const fallbackGapY = 40
  const asFinite = (v: any) => {
    const n = Number(v)
    return Number.isFinite(n) ? n : null
  }

  return slots.value.map((s, idx) => {
    const code = String(s.code || '')
    const statusCfg = String(s.status || '正常').trim()
    const row = Math.floor(idx / fallbackCols)
    const col = idx % fallbackCols
    const fallbackX = fallbackBaseX + col * (fallbackW + fallbackGapX)
    const fallbackY = fallbackBaseY + row * (fallbackH + fallbackGapY)
    const rawX = asFinite(s.x)
    const rawY = asFinite(s.y)
    const x = rawX === null ? fallbackX : rawX
    const y = rawY === null ? fallbackY : rawY
    const w = asFinite(s.w) ?? fallbackW
    const h = asFinite(s.h) ?? fallbackH
    const active = inventory.value.filter((r) => String(r['Location_Code'] || '') === code && String(r['状态'] || '').includes('库存中'))
    const count = active.length
    const serialNos = active.map((r) => String(r['流水号'] || '')).filter(Boolean)
    let statusText = '空闲'
    let statusClass = 'idle'
    if (['锁定', '异常'].includes(statusCfg)) {
      statusText = '锁定/异常'
      statusClass = 'locked'
    } else if (count >= maxCap) {
      statusText = '满载'
      statusClass = 'full'
    } else if (count > 0) {
      statusText = '占用'
      statusClass = 'occupied'
    }
    return { ...s, code, x, y, w, h, count, statusText, statusClass, serialNos }
  }).sort((a, b) => String(a.code).localeCompare(String(b.code), 'zh-CN', { numeric: true }))
})

const filteredSlotCards = computed(() => {
  const kw = searchKeyword.value.trim().toUpperCase()
  if (!kw) return slotCards.value
  return slotCards.value.filter((s) => {
    const code = String(s.code || '').toUpperCase()
    const sns = (s.serialNos || []).join(' ').toUpperCase()
    return code.includes(kw) || sns.includes(kw)
  })
})
const groupedSlotSections = computed(() => {
  const groups = new Map<string, any[]>()
  for (const slot of filteredSlotCards.value) {
    const m = String(slot.code || '').match(/^[A-Za-z]+/)
    const zone = m ? m[0].toUpperCase() : '未分区'
    if (!groups.has(zone)) groups.set(zone, [])
    groups.get(zone)!.push(slot)
  }
  return Array.from(groups.entries())
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([zone, items]) => ({ zone, items: items.sort((a, b) => String(a.code).localeCompare(String(b.code), 'zh-CN', { numeric: true })) }))
})

const slotStyle = (_slot: any) => ({})

const summary = computed(() => {
  const s = { idle: 0, occupied: 0, full: 0, locked: 0 }
  for (const c of slotCards.value) {
    if (c.statusClass === 'idle') s.idle++
    else if (c.statusClass === 'occupied') s.occupied++
    else if (c.statusClass === 'full') s.full++
    else s.locked++
  }
  return s
})
const showInitialSkeleton = computed(() => loading.value && !loadedOnce.value && !loadError.value)

const currentSlotMachines = computed(() => {
  const code = String(currentSlot.value?.code || '')
  if (!code) return []
  return inventory.value.filter((r) => String(r['Location_Code'] || '') === code && String(r['状态'] || '').includes('库存中'))
})
const currentSlotSns = computed(() => currentSlotMachines.value.map((r) => String(r['流水号'] || '')).filter(Boolean))
const availableTargetSlots = computed(() => {
  const currentCode = String(currentSlot.value?.code || '')
  return slotCards.value
    .filter((s) => s.code !== currentCode && s.statusClass !== 'locked' && s.count < maxCap)
    .map((s) => String(s.code))
})
const canInbound = computed(() => {
  const slot = currentSlot.value as any
  if (!slot) return false
  if (slot.statusClass === 'locked' || slot.statusClass === 'full') return false
  return !!directSn.value.trim()
})
const canTransfer = computed(() => !!targetSlot.value && !!transferSn.value.trim())

const CACHE_LAYOUT = 'warehouse:layout:default'
const CACHE_INVENTORY = 'warehouse:inventory'
const loadData = async (force = false) => {
  loading.value = true
  loadError.value = ''
  try {
    if (!force) {
      const layoutCached = cacheStore.get<Slot[]>(CACHE_LAYOUT)
      const invCached = cacheStore.get<Row[]>(CACHE_INVENTORY)
      if (layoutCached && invCached) {
        slots.value = layoutCached
        inventory.value = invCached
        return
      }
    }

    const [layoutRes, nextInventory] = await Promise.all([
      apiGet<LayoutResponse>('/inventory/layout/default'),
      apiGetAll<Row>('/inventory/'),
    ])
    const nextSlots = layoutRes.layout_json?.slots || []
    slots.value = nextSlots
    inventory.value = nextInventory
    cacheStore.set(CACHE_LAYOUT, nextSlots, 10_000)
    cacheStore.set(CACHE_INVENTORY, nextInventory, 10_000)
  } catch (err: any) {
    loadError.value = getApiErrorMessage(err) || '读取库位数据失败'
    ElMessage.error(loadError.value)
  } finally {
    loading.value = false
    loadedOnce.value = true
  }
}
const retryLoadData = () => {
  void loadData(true)
}

const openSlot = (slot: Slot) => {
  currentSlot.value = slot
  directSn.value = ''
  transferSn.value = ''
  targetSlot.value = ''
  dialogTab.value = slot.statusClass === 'idle' ? 'inbound' : 'detail'
  dialogVisible.value = true
}
const handleSlotClick = (slot: Slot) => {
  if (isFullscreen.value) return
  openSlot(slot)
}

const doDirectInbound = async () => {
  if (!currentSlot.value || !directSn.value.trim()) return
  saving.value = true
  try {
    await apiPost('/inventory/inbound-to-slot', { serial_no: directSn.value.trim(), slot_code: currentSlot.value.code })
    ElMessage.success('入库成功')
    directSn.value = ''
    await loadData(true)
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '入库失败')
  } finally {
    saving.value = false
  }
}

const doTransfer = async () => {
  if (!targetSlot.value || !transferSn.value.trim()) {
    ElMessage.warning('请选择调拨机台和目标库位')
    return
  }
  saving.value = true
  try {
    await apiPost('/inventory/inbound-to-slot', { serial_no: transferSn.value.trim(), slot_code: targetSlot.value, is_transfer: true })
    ElMessage.success('调拨成功')
    transferSn.value = ''
    targetSlot.value = ''
    await loadData(true)
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '调拨失败')
  } finally {
    saving.value = false
  }
}

const exitBrowserFullscreen = async () => {
  if (!getFullscreenElementCompat()) {
    isFullscreen.value = false
    return
  }
  try {
    await exitFullscreenCompat()
  } catch {
    // Ignore unsupported browser fullscreen exit errors.
  } finally {
    isFullscreen.value = false
  }
}

const goHome = async () => {
  await exitBrowserFullscreen()
  router.push('/')
}

const toggleFullscreen = async () => {
  try {
    if (!getFullscreenElementCompat()) {
      const node = pageRef.value
      if (!node) {
        ElMessage.warning('当前环境不支持全屏')
        return
      }
      await requestFullscreenCompat(node)
      isFullscreen.value = true
    } else {
      await exitFullscreenCompat()
      isFullscreen.value = false
    }
  } catch {
    ElMessage.warning('当前环境不支持全屏')
  }
}

const generateLayout = async () => {
  const prefix = layoutPrefix.value.trim()
  if (!prefix) {
    ElMessage.warning('请先填写区域前缀')
    return
  }

  const existing = Array.isArray(slots.value) ? [...slots.value] : []
  const prefixSlots = existing.filter((s) => String(s.code || '').trim().startsWith(prefix))
  const otherSlots = existing.filter((s) => !String(s.code || '').trim().startsWith(prefix))

  const width = 300
  const height = 160
  const gapX = 40
  const gapY = 40
  const areaGap = 20

  let finalSlots: any[] = []
  let baseX = 20
  let baseY = 20
  if (!appendLayout.value) {
    finalSlots = []
  } else if (prefixSlots.length > 0) {
    finalSlots = otherSlots
    baseX = Math.min(...prefixSlots.map((s) => Number(s.x ?? 0) || 0))
    baseY = Math.min(...prefixSlots.map((s) => Number(s.y ?? 0) || 0))
  } else {
    finalSlots = existing
    if (finalSlots.length > 0) {
      const maxBottom = Math.max(...finalSlots.map((s) => (Number(s.y ?? 0) || 0) + (Number(s.h ?? 160) || 160)))
      baseY = maxBottom + areaGap
    }
  }

  let maxIdNum = 0
  for (const s of finalSlots) {
    const sid = String(s.id || '').trim()
    const n = Number(sid.split('-').pop() || '0')
    if (Number.isFinite(n)) maxIdNum = Math.max(maxIdNum, n)
  }

  const generated: any[] = []
  if (layoutMode.value === 'row') {
    for (let r = 0; r < layoutRows.value; r++) {
      for (let c = 0; c < layoutCols.value; c++) {
        const seq = generated.length + 1
        const channelGap = Math.floor(c / 2) * 40
        maxIdNum += 1
        generated.push({
          id: `slot-${maxIdNum}`,
          code: `${prefix}${String(seq).padStart(2, '0')}`,
          x: baseX + c * (width + gapX) + channelGap,
          y: baseY + r * (height + gapY),
          w: width,
          h: height,
          status: '正常',
          allowed_models: allowedModels.value.trim(),
        })
      }
    }
  } else {
    for (let c = 0; c < layoutCols.value; c++) {
      for (let r = 0; r < layoutRows.value; r++) {
        const seq = generated.length + 1
        const channelGap = Math.floor(c / 2) * 40
        maxIdNum += 1
        generated.push({
          id: `slot-${maxIdNum}`,
          code: `${prefix}${String(seq).padStart(2, '0')}`,
          x: baseX + c * (width + gapX) + channelGap,
          y: baseY + r * (height + gapY),
          w: width,
          h: height,
          status: '正常',
          allowed_models: allowedModels.value.trim(),
        })
      }
    }
  }

  savingLayout.value = true
  try {
    await apiPost('/inventory/layout/save', {
      layout_id: 'default',
      layout_json: { slots: [...finalSlots, ...generated] },
    })
    ElMessage.success(`布局已生成，共 ${finalSlots.length + generated.length} 个库位`)
    await loadData(true)
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '生成布局失败')
  } finally {
    savingLayout.value = false
  }
}

const syncFullscreen = () => {
  isFullscreen.value = !!pageRef.value && getFullscreenElementCompat() === pageRef.value
}
const updateNowText = () => {
  nowText.value = formatTimeHMS()
}

loadData()
onMounted(() => {
  for (const evt of fullscreenChangeEventNames) {
    document.addEventListener(evt, syncFullscreen as EventListener)
  }
  updateNowText()
  clockTimer = window.setInterval(updateNowText, 1000)
})
onBeforeUnmount(() => {
  void exitBrowserFullscreen()
  for (const evt of fullscreenChangeEventNames) {
    document.removeEventListener(evt, syncFullscreen as EventListener)
  }
  if (clockTimer) {
    window.clearInterval(clockTimer)
    clockTimer = null
  }
})
onBeforeRouteLeave(async () => {
  await exitBrowserFullscreen()
})
watch(isFullscreen, (v) => {
  if (v) {
    dialogVisible.value = false
    layoutDrawerVisible.value = false
  }
})
</script>

<style scoped>
.screen {
  min-height: 100vh;
  color: #e2e8f0;
  background: radial-gradient(circle at 20% 20%, #10213b, #020817 55%, #000510);
  padding: 14px 16px 10px;
}
.top-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border: 1px solid rgba(148, 163, 184, 0.22);
  border-radius: 12px;
  background: rgba(2, 6, 23, 0.8);
  padding: 12px 14px;
}
.title-wrap { display: flex; align-items: center; gap: 10px; }
.title-icon {
  width: 34px;
  height: 34px;
  border-radius: 9px;
  display: grid;
  place-items: center;
  background: linear-gradient(135deg, #22c55e, #0ea5e9);
  color: #fff;
  font-weight: 700;
}
.main-title { margin: 0; font-size: 24px; font-weight: 700; color: #f8fafc; }
.sub-title { margin-top: 3px; font-size: 13px; color: #93c5fd; }
.head-actions { display: flex; gap: 8px; }

.metric-row {
  margin-top: 10px;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}
.metric-card {
  border-radius: 12px;
  border: 1px solid rgba(148, 163, 184, 0.22);
  background: rgba(2, 6, 23, 0.72);
  padding: 12px;
}
.metric-label { font-size: 13px; color: #94a3b8; }
.metric-value { margin-top: 5px; font-size: 34px; line-height: 1; font-weight: 700; }
.metric-card.idle .metric-value { color: #34d399; }
.metric-card.occupied .metric-value { color: #38bdf8; }
.metric-card.full .metric-value { color: #f87171; }
.metric-card.locked .metric-value { color: #fbbf24; }

.tool-row {
  margin-top: 10px;
  display: grid;
  grid-template-columns: 180px 160px 1fr;
  gap: 10px;
}
.tool-item {
  border-radius: 10px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  background: rgba(2, 6, 23, 0.66);
  font-size: 14px;
  color: #cbd5e1;
  padding: 10px 12px;
}
.tool-search {
  display: grid;
  grid-template-columns: 72px 1fr;
  align-items: center;
  gap: 10px;
  border-radius: 10px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  background: rgba(2, 6, 23, 0.66);
  padding: 8px 10px;
}
.tool-search span { color: #93c5fd; font-size: 13px; }
.load-error { margin-top: 10px; }

.board-body { margin-top: 12px; }
.zone-section + .zone-section { margin-top: 12px; }
.zone-title { font-size: 14px; color: #94a3b8; margin-bottom: 8px; }
.slot-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(210px, 1fr));
  gap: 10px;
}
.fullscreen-grid {
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  padding: 2px 0;
}
.slot-card {
  border-radius: 12px;
  border: 1px solid rgba(100, 116, 139, 0.5);
  background: rgba(3, 11, 28, 0.9);
  color: #e2e8f0;
  text-align: left;
  padding: 12px;
  min-height: 170px;
  cursor: pointer;
  transition: transform .15s ease, box-shadow .15s ease;
}
.slot-card:hover { transform: translateY(-1px); box-shadow: 0 10px 24px rgba(0, 0, 0, 0.28); }
.slot-card.idle { border-color: rgba(16, 185, 129, 0.85); }
.slot-card.occupied { border-color: rgba(59, 130, 246, 0.9); }
.slot-card.full { border-color: rgba(239, 68, 68, 0.9); }
.slot-card.locked { border-color: rgba(245, 158, 11, 0.9); }
.card-head { display: flex; justify-content: space-between; align-items: center; }
.code { font-size: clamp(22px, 2vw, 30px); font-weight: 800; color: #f8fafc; line-height: 1.1; }
.badge { font-size: 12px; border-radius: 6px; padding: 2px 8px; border: 1px solid transparent; }
.badge.idle { color: #34d399; border-color: rgba(52, 211, 153, 0.45); background: rgba(5, 46, 34, 0.55); }
.badge.occupied { color: #38bdf8; border-color: rgba(56, 189, 248, 0.45); background: rgba(7, 35, 69, 0.55); }
.badge.full { color: #f87171; border-color: rgba(248, 113, 113, 0.45); background: rgba(69, 10, 10, 0.5); }
.badge.locked { color: #fbbf24; border-color: rgba(251, 191, 36, 0.45); background: rgba(69, 39, 6, 0.5); }
.count-row { margin-top: 8px; display: flex; align-items: baseline; gap: 5px; }
.count-num { font-size: clamp(36px, 3.5vw, 46px); line-height: 1; font-weight: 800; color: #f8fafc; }
.count-max { font-size: clamp(16px, 1.2vw, 20px); color: #94a3b8; }
.bar { margin-top: 6px; height: 6px; border-radius: 99px; background: rgba(71, 85, 105, 0.45); overflow: hidden; }
.bar-inner { height: 100%; border-radius: 99px; }
.bar-inner.idle { background: #34d399; }
.bar-inner.occupied { background: #38bdf8; }
.bar-inner.full { background: #f87171; }
.bar-inner.locked { background: #fbbf24; }
.sns { margin-top: 10px; display: grid; gap: 4px; }
.sn-item { font-size: clamp(13px, 1vw, 15px); color: #cbd5e1; line-height: 1.2; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.sn-item.empty { color: #64748b; text-align: center; margin-top: 8px; }

.bottom-legend {
  margin-top: 10px;
  display: flex;
  gap: 14px;
  align-items: center;
  font-size: 13px;
  color: #94a3b8;
}

.fs-top {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin: 0 0 8px;
}
.fs-metric {
  border: 1px solid rgba(148, 163, 184, 0.25);
  border-radius: 10px;
  background: rgba(3, 11, 28, 0.82);
  padding: 6px 10px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
}
.fs-metric strong { font-size: 34px; line-height: 1; }
.fs-metric.idle strong { color: #34d399; }
.fs-metric.occupied strong { color: #38bdf8; }
.fs-metric.full strong { color: #f87171; }
.fs-metric.locked strong { color: #fbbf24; }
.fs-meta {
  color: #8ec5ff;
  font-size: 34px;
  line-height: 1.05;
  font-weight: 700;
  margin: 2px 0 10px;
}
.fs-zone-section {
  border-top: 1px solid rgba(148, 163, 184, 0.2);
  padding-top: 10px;
  margin-top: 8px;
}
.dot { width: 8px; height: 8px; border-radius: 999px; display: inline-block; margin-right: 4px; }
.dot.full { background: #ef4444; }
.dot.occupied { background: #3b82f6; }
.dot.idle { background: #10b981; }
.dot.locked { background: #f59e0b; }

.fullscreen-mode {
  padding: 0;
  width: 100vw;
  height: 100vh;
  overflow: auto;
  background: radial-gradient(circle at 20% 20%, #0b1a2f, #020617 55%, #00040f);
}
.fullscreen-mode .board-body {
  margin: 0;
  min-height: 100vh;
  padding: 8px;
}

.label { font-size: 12px; color: #6b7280; margin-bottom: 4px; }
.panel-title { font-weight: 700; margin-bottom: 6px; color: #111827; }
.inline-tip { font-size: 12px; color: #f97316; margin-top: 8px; }
</style>
