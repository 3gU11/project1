<template>
  <div class="ratio-editor-layout">
    <div class="ratio-editor-left">
      <button class="ratio-collapse-toggle" :class="{ 'is-active': expanded }" type="button" @click="expanded = !expanded">
        <span>机型目标比例配置</span>
        <span class="arrow" :class="{ open: expanded }">▾</span>
      </button>

      <div v-show="expanded" class="ratio-collapse-body">
        <div class="ratio-config-panel">
            <div class="section-block">
              <strong>机型族目标比例（G、XS、AUTO 合计 100%）</strong>
              <div class="ratio-row">
                <div class="ratio-item" v-for="group in familyRatioGroups" :key="`l1-${group.family}`">
                  <label>{{ group.label }}:</label>
                  <el-input-number
                    :model-value="getFamilyValue(group.family)"
                    @update:model-value="(v:number | undefined) => setFamilyValue(group.family, v)"
                    :min="0"
                    :max="100"
                    :controls="false"
                    size="small"
                    style="width:60px"
                  />%
                </div>
                <span :class="['sum-badge', sumLevel1NoSpecial === 100 ? 'is-valid' : 'is-invalid']">
                  目标合计: {{ sumLevel1NoSpecial }}%
                  <span class="status-icon">{{ sumLevel1NoSpecial === 100 ? '✓' : '⚠' }}</span>
                </span>
              </div>
            </div>

            <div v-for="group in familyModelGroups" :key="`l2-${group.family}`" class="section-block">
              <strong>
                {{ group.label }}机型目标比例
                <span v-if="group.family !== 'G'">（中小型与中大型合计 100%）</span>
              </strong>
              <div class="ratio-row">
                <div class="ratio-item" v-for="item in group.models" :key="`${group.family}-${item.model}`">
                  <label>{{ item.model }}:</label>
                  <el-input-number
                    :model-value="getFamilyModelValue(group.family, item.model)"
                    @update:model-value="(v:number | undefined) => setFamilyModelValue(group.family, item.model, v)"
                    :min="0"
                    :max="100"
                    :controls="false"
                    size="small"
                    style="width:60px"
                  />%
                </div>
                <span :class="['sum-badge', sumFamilyModels(group.family) === 100 ? 'is-valid' : 'is-invalid']">
                  目标合计: {{ sumFamilyModels(group.family) }}% / 100%
                  <span class="status-icon">{{ sumFamilyModels(group.family) === 100 ? '✓' : '⚠' }}</span>
                </span>
              </div>
            </div>

            <div class="panel-actions">
              <el-button @click="fillFromHistoricalData" :loading="autoFilling">按往期数据自动填入</el-button>
              <el-button type="primary" @click="save" :loading="saving">保存目标比例</el-button>
              <transition name="fade">
                <span v-if="msg" class="message-bubble" :style="{ backgroundColor: msgBgColor, borderColor: msgBorderColor, color: msgColor }">
                  {{ msg }}
                </span>
              </transition>
            </div>
        </div>
      </div>
    </div>

    <!-- Inventory Section (Always Visible on the Right, Minimized Height by Default) -->
    <div class="inventory-ratio-panel" :class="{ 'is-dragging': isDragging, 'is-zoomed': isZoomed }" :style="{ transform: 'translate(' + dragPos.x + 'px, ' + dragPos.y + 'px)' }" @mousedown="handleDragStart">
      <div class="inventory-ratio-header">
        <div class="header-title-area">
          <strong>库存机型分布</strong>
          <span>G / XS / AUTO 库存，共 {{ inventoryTotal }} 台</span>
        </div>
        <button class="header-zoom-button" type="button" @click.stop="isZoomed = !isZoomed">
          <svg v-if="!isZoomed" class="zoom-icon" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"/></svg>
          <svg v-else class="zoom-icon" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M4 14h6v6M20 10h-6V4M14 10l7-7M10 14l-7 7"/></svg>
          <span>{{ isZoomed ? '收起' : '放大' }}</span>
        </button>
      </div>
      <div class="inventory-table-shell">
        <div v-loading="inventoryLoading" class="inventory-family-groups">
          <section v-for="group in inventoryFamilyGroups" :key="group.family" class="inventory-family-group">
            <div class="inventory-family-title">
              <strong>{{ group.label }}</strong>
              <span>族内库存 {{ group.total }} 台</span>
            </div>
            <el-table
              :data="group.rows"
              size="small"
              :height="isZoomed ? undefined : undefined"
              stripe
              empty-text="暂无该族库存"
            >
              <el-table-column prop="name" label="机型" min-width="120" show-overflow-tooltip />
              <el-table-column label="数量" width="56" align="center">
                <template #default="{ row }">
                  <span v-if="row.current_qty > 0" style="font-weight: 800; color: #d4380d; background: #fff2e8; padding: 2px 6px; border-radius: 4px; display: inline-block;">{{ row.current_qty }}</span>
                  <span v-else style="color: #dcdfe6;">-</span>
                </template>
              </el-table-column>
              <el-table-column label="加高" width="56" align="center">
                <template #default="{ row }">
                  <span v-if="row.high_qty > 0" style="font-weight: 800; color: #0f172a; background: #f1f5f9; padding: 2px 6px; border-radius: 4px; display: inline-block;">{{ row.high_qty }}</span>
                  <span v-else style="color: #dcdfe6;">-</span>
                </template>
              </el-table-column>
              <el-table-column label="同族占比" width="78" align="center">
                <template #default="{ row }">
                  <span v-if="row.current_pct > 0" style="font-weight: 800; color: #475569; background: #f8fafc; padding: 2px 4px; border-radius: 4px; display: inline-block; font-size: 11px;">{{ formatPct(row.current_pct) }}</span>
                  <span v-else style="color: #dcdfe6;">-</span>
                </template>
              </el-table-column>
            </el-table>
          </section>
        </div>
        <button v-if="!isZoomed" class="inventory-zoom-overlay" type="button" @click="isZoomed = true">
          <span class="inventory-zoom-icon"></span>
          <span>放大查看</span>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import * as sandboxApi from '../../services/sandboxApi'
import { useInventoryStore } from '../../store/inventory'
import { buildModelInventoryRatios, getActiveInventoryRows } from '../../utils/inventoryStats'
import { compareModels } from '../../utils/modelOrder'
import { apiGet } from '../../utils/request'

type MajorFamily = 'G' | 'XS' | 'AUTO' | 'SPECIAL'
const majorFamilies: MajorFamily[] = ['G', 'XS', 'AUTO', 'SPECIAL']
const SPECIAL = '特殊'

const CAT_TO_MAJOR: Record<string, MajorFamily> = {
  中小型G: 'G',
  中小型XS: 'XS',
  中大型XS: 'XS',
  中小型AUTO: 'AUTO',
  中大型AUTO: 'AUTO',
  特殊: 'SPECIAL'
}

const groupsByFamily = ref<Record<MajorFamily, Array<{ category: string; models: string[] }>>>({
  G: [{ category: '中小型G', models: ['FR-400G', 'FR-500G', 'FR-600G', 'FH-300C'] }],
  XS: [{ category: '中小型XS', models: ['FR-400XS(PRO)', 'FR-500XS(PRO)'] }, { category: '中大型XS', models: ['FR-600XS(PRO)'] }],
  AUTO: [{ category: '中小型AUTO', models: ['FR-400AUTO', 'FR-500AUTO'] }, { category: '中大型AUTO', models: ['FR-600AUTO'] }],
  SPECIAL: [{ category: SPECIAL, models: [SPECIAL] }]
})

const form = reactive({
  level2: { G: {}, XS: {}, AUTO: {}, SPECIAL: {} } as Record<MajorFamily, Record<string, number>>,
  level3: {} as Record<string, Record<string, number>>
})
const globalLevel2 = reactive<Record<string, number>>({
  中小型G: 24,
  中小型XS: 38,
  中大型XS: 38,
  中小型AUTO: 0,
  中大型AUTO: 0,
  特殊: 0
})
const familyLevel1 = reactive<Record<MajorFamily, number>>({ G: 24, XS: 76, AUTO: 0, SPECIAL: 0 })
const familyModelRatios = reactive<Record<MajorFamily, Record<string, number>>>({
  G: {}, XS: {}, AUTO: {}, SPECIAL: {}
})

const saving = ref(false)
const autoFilling = ref(false)
const msg = ref('')
const msgColor = ref('#67c23a')
const msgBgColor = computed(() => {
  return msgColor.value === '#67c23a' ? '#f0fdf4' : '#fef2f2'
})
const msgBorderColor = computed(() => {
  return msgColor.value === '#67c23a' ? '#bbf7d0' : '#fecaca'
})
const expanded = ref(false)
const isZoomed = ref(false)

const dragPos = ref({ x: 0, y: 0 })
const isDragging = ref(false)

function handleDragStart(e: MouseEvent) {
  if (e.button !== 0) return
  const target = e.target as HTMLElement
  if (target.closest('button') || target.closest('.el-scrollbar__bar') || target.closest('.el-scrollbar__thumb')) return
  isDragging.value = true
  const startX = e.clientX
  const startY = e.clientY
  const startOffsetX = dragPos.value.x
  const startOffsetY = dragPos.value.y

  const handleDragMove = (moveEvent: MouseEvent) => {
    if (!isDragging.value) return
    moveEvent.preventDefault() // 拖动时阻止文本选中
    dragPos.value = {
      x: startOffsetX + (moveEvent.clientX - startX),
      y: startOffsetY + (moveEvent.clientY - startY)
    }
  }

  const handleDragEnd = () => {
    isDragging.value = false
    window.removeEventListener('mousemove', handleDragMove)
    window.removeEventListener('mouseup', handleDragEnd)
  }

  window.addEventListener('mousemove', handleDragMove)
  window.addEventListener('mouseup', handleDragEnd)
}
const inventoryLoading = ref(false)
const inventoryTotal = ref(0)
const inventoryRatioRows = ref<Array<{ name: string; current_qty: number; high_qty: number; current_pct: number }>>([])
const specialModelSet = ref<Set<string>>(new Set())
const inventoryStore = useInventoryStore()
const inventoryFamilyGroups = computed(() => {
  const labels: Record<string, string> = { AUTO: 'AUTO 族', G: 'G 族', XS: 'XS 族' }
  return (['AUTO', 'G', 'XS'] as MajorFamily[]).map((family) => {
    const rows = inventoryRatioRows.value.filter((row) => row.family === family)
    return { family, label: labels[family], total: rows.reduce((sum, row) => sum + row.current_qty, 0), rows }
  })
})

const sumLevel1NoSpecial = computed(
  () => Number(familyLevel1.G || 0) + Number(familyLevel1.XS || 0) + Number(familyLevel1.AUTO || 0)
)
const familyRatioGroups = [
  { family: 'G' as MajorFamily, label: 'G 族' },
  { family: 'XS' as MajorFamily, label: 'XS 族' },
  { family: 'AUTO' as MajorFamily, label: 'AUTO 族' }
]
const familyModelGroups = computed(() => familyRatioGroups.map(({ family, label }) => ({
  family,
  label,
  models: (groupsByFamily.value[family] || []).flatMap((group) =>
    (group.models || []).map((model) => ({ model, category: group.category }))
  )
})))

function ensureShape() {
  for (const f of majorFamilies) {
    if (!form.level2[f]) form.level2[f] = {}
    for (const g of groupsByFamily.value[f] || []) {
      if (form.level2[f][g.category] === undefined) form.level2[f][g.category] = 0
      if (!form.level3[g.category]) form.level3[g.category] = {}
      for (const m of g.models) {
        if (form.level3[g.category][m] === undefined) form.level3[g.category][m] = Math.floor(100 / Math.max(1, g.models.length))
        if (familyModelRatios[f][m] === undefined) familyModelRatios[f][m] = 0
      }
    }
  }
  if (!form.level2.SPECIAL) form.level2.SPECIAL = {}
  form.level2.SPECIAL[SPECIAL] = 0
  if (!form.level3[SPECIAL]) form.level3[SPECIAL] = {}
  form.level3[SPECIAL][SPECIAL] = 0
}

function getFamilyValue(family: MajorFamily) {
  return Number(familyLevel1[family] || 0)
}

function setFamilyValue(family: MajorFamily, value: number | undefined) {
  familyLevel1[family] = Number(value || 0)
}

function sumFamilyModels(family: MajorFamily) {
  return Object.values(familyModelRatios[family] || {}).reduce((s, v) => s + Number(v || 0), 0)
}

function formatPct(v: number) {
  return `${Number(v || 0).toFixed(1)}%`
}

function getFamilyModelValue(family: MajorFamily, model: string) {
  if (familyModelRatios[family][model] === undefined) familyModelRatios[family][model] = 0
  return Number(familyModelRatios[family][model] || 0)
}

function setFamilyModelValue(family: MajorFamily, model: string, value: number | undefined) {
  familyModelRatios[family][model] = Number(value || 0)
}

function apportionToTarget(keys: string[], source: Record<string, number>, target: number) {
  const out: Record<string, number> = {}
  if (!keys.length) return out
  const safeTarget = Math.max(0, Math.round(Number(target || 0)))
  const vals = keys.map((k) => Math.max(0, Number(source[k] || 0)))
  const sum = vals.reduce((s, v) => s + v, 0)
  const base = new Array<number>(keys.length).fill(0)
  const frac: Array<{ i: number; f: number }> = []
  if (sum <= 0) {
    const per = Math.floor(safeTarget / keys.length)
    let rem = safeTarget - per * keys.length
    for (let i = 0; i < keys.length; i += 1) {
      base[i] = per + (rem > 0 ? 1 : 0)
      if (rem > 0) rem -= 1
    }
  } else {
    let used = 0
    for (let i = 0; i < keys.length; i += 1) {
      const exact = safeTarget * (vals[i] / sum)
      base[i] = Math.floor(exact)
      frac.push({ i, f: exact - base[i] })
      used += base[i]
    }
    let rem = safeTarget - used
    frac.sort((a, b) => b.f - a.f)
    for (const x of frac) {
      if (rem <= 0) break
      base[x.i] += 1
      rem -= 1
    }
  }
  keys.forEach((k, i) => {
    out[k] = base[i]
  })
  return out
}

function buildBackendPayload() {
  const payload = JSON.parse(JSON.stringify(form)) as {
    level2_global?: Record<string, number>
    level2: Record<string, Record<string, number>>
    level3: Record<string, Record<string, number>>
  }
  const categoryGlobalWeights: Record<string, number> = {}
  for (const family of ['G', 'XS', 'AUTO'] as MajorFamily[]) {
    const groups = groupsByFamily.value[family] || []
    const groupKeys = groups.map((g) => g.category)
    const categoryModelWeights: Record<string, number> = {}
    for (const group of groups) {
      categoryModelWeights[group.category] = (group.models || []).reduce(
        (sum, model) => sum + Number(familyModelRatios[family]?.[model] || 0),
        0
      )
      categoryGlobalWeights[group.category] = Number(familyLevel1[family] || 0) * categoryModelWeights[group.category] / 100
    }
    const level2Local = apportionToTarget(groupKeys, categoryModelWeights, 100)
    payload.level2[family] = level2Local
    for (const g of groups) {
      const modelKeys = g.models || []
      payload.level3[g.category] = apportionToTarget(modelKeys, familyModelRatios[family] || {}, 100)
    }
  }
  const categoryKeys = ['中小型G', '中小型XS', '中大型XS', '中小型AUTO', '中大型AUTO']
  payload.level2_global = { ...apportionToTarget(categoryKeys, categoryGlobalWeights, 100), 特殊: 0 }
  payload.level2.SPECIAL = { [SPECIAL]: 0 }
  payload.level3[SPECIAL] = { [SPECIAL]: 0 }
  return payload
}

function normalizeCategory(v: string) {
  const aliases: Record<string, string> = {
    小机G: '中小型G',
    小机XS: '中小型XS',
    '小机/XS': '中小型XS',
    小机AUTO: '中小型AUTO',
    大机XS: '中大型XS',
    大机AUTO: '中大型AUTO',
    SPECIAL: SPECIAL
  }
  return aliases[v] || v
}

function categoryOfModel(modelType: string, modelFamily?: string) {
  const mf = normalizeCategory(String(modelFamily || '').trim())
  if (mf) return mf
  const mt = String(modelType || '').toUpperCase()
  if (mt === 'FH-300C') return '中小型G'
  if (mt.includes('AUTO')) return mt.includes('7055') || mt.includes('8055') || mt.includes('8060') ? '中大型AUTO' : '中小型AUTO'
  if (mt.includes('XS')) return mt.includes('7055') || mt.includes('8055') || mt.includes('8060') ? '中大型XS' : '中小型XS'
  if (mt.endsWith('G')) return '中小型G'
  if (mt === SPECIAL || mt.includes('特殊')) return SPECIAL
  return SPECIAL
}

async function loadModelTypes() {
  const res = await sandboxApi.getModelTypes() as any
  const list = Array.isArray(res) ? res : (res?.model_types || [])
  const byCat: Record<string, string[]> = {}
  const specialModels = new Set<string>()
  for (const item of list) {
    if (!item || typeof item !== 'object') continue
    const model = String(item.model_type || '').trim()
    if (!model) continue
    const modelFamily = String(item.model_family || '').trim()
    const cat = categoryOfModel(model, modelFamily)
    if (cat === SPECIAL) specialModels.add(model.toUpperCase())
    if (!byCat[cat]) byCat[cat] = []
    byCat[cat].push(model)
  }
  specialModelSet.value = specialModels
  const uniqueInOrder = (items: string[]) => {
    const seen = new Set<string>()
    const out: string[] = []
    for (const item of items) {
      const key = String(item || '').trim().toUpperCase()
      if (!key || seen.has(key)) continue
      seen.add(key)
      out.push(item)
    }
    return out
  }
  const next: Record<MajorFamily, Array<{ category: string; models: string[] }>> = { G: [], XS: [], AUTO: [], SPECIAL: [] }
  for (const cat of ['中小型G', '中小型XS', '中大型XS', '中小型AUTO', '中大型AUTO', SPECIAL]) {
    const major = CAT_TO_MAJOR[cat]
    if (!major) continue
    const models = uniqueInOrder(byCat[cat] || [])
    if (models.length) next[major].push({ category: cat, models })
  }
  const smallG = next.G.find((g) => g.category === '中小型G')
  if (smallG) {
    smallG.models = uniqueInOrder([...smallG.models, 'FH-300C'])
  } else {
    next.G.unshift({ category: '中小型G', models: ['FR-400G', 'FH-300C'] })
  }
  if (!next.XS.length) next.XS = [{ category: '中小型XS', models: ['FR-400XS(PRO)'] }, { category: '中大型XS', models: ['FR-600XS(PRO)'] }]
  if (!next.AUTO.length) next.AUTO = [{ category: '中小型AUTO', models: ['FR-400AUTO'] }, { category: '中大型AUTO', models: ['FR-600AUTO'] }]
  if (!next.SPECIAL.length) next.SPECIAL = [{ category: SPECIAL, models: [SPECIAL] }]
  groupsByFamily.value = next
  ensureShape()
}

function loadFromRatio(ratio: any) {
  const normalizedRatio = normalizeRatioPayload(ratio || {})
  form.level2 = { G: {}, XS: {}, AUTO: {}, SPECIAL: {}, ...(normalizedRatio?.level2 || {}) }
  if (!form.level2.SPECIAL || typeof form.level2.SPECIAL !== 'object') form.level2.SPECIAL = {}
  if (form.level2.SPECIAL[SPECIAL] === undefined) form.level2.SPECIAL[SPECIAL] = 0
  form.level3 = { ...(normalizedRatio?.level3 || {}) }
  ensureShape()

  for (const f of majorFamilies) {
    for (const g of groupsByFamily.value[f] || []) {
      if (normalizedRatio?.level3?.[g.category]) {
        const keys = g.models || []
        form.level3[g.category] = apportionToTarget(keys, form.level3[g.category] || {}, 100)
        continue
      }
      if (g.models.length) {
        const base = Math.floor(100 / g.models.length)
        let rem = 100 - base * g.models.length
        for (const m of g.models) {
          form.level3[g.category][m] = base + (rem > 0 ? 1 : 0)
          if (rem > 0) rem -= 1
        }
      }
    }
  }

  const l2g = normalizedRatio?.level2_global || {}
  if (Object.keys(l2g).length > 0) {
    globalLevel2['中小型G'] = Number(l2g['中小型G'] || 0)
    globalLevel2['中小型XS'] = Number(l2g['中小型XS'] || 0)
    globalLevel2['中大型XS'] = Number(l2g['中大型XS'] || 0)
    globalLevel2['中小型AUTO'] = Number(l2g['中小型AUTO'] || 0)
    globalLevel2['中大型AUTO'] = Number(l2g['中大型AUTO'] || 0)
  } else {
    const l1 = normalizedRatio?.level1 || {}
    const gTotal = Number(l1.G || 24)
    const xsTotal = Number(l1.XS || 76)
    const autoTotal = Number(l1.AUTO || 0)
    const xsLocal = form.level2.XS || {}
    const autoLocal = form.level2.AUTO || {}
    globalLevel2['中小型G'] = Math.max(0, Math.round(gTotal))
    globalLevel2['中小型XS'] = Math.max(0, Math.round(xsTotal * (Number(xsLocal['中小型XS'] || 0) / 100)))
    globalLevel2['中大型XS'] = Math.max(0, Math.round(xsTotal * (Number(xsLocal['中大型XS'] || 0) / 100)))
    globalLevel2['中小型AUTO'] = Math.max(0, Math.round(autoTotal * (Number(autoLocal['中小型AUTO'] || 0) / 100)))
    globalLevel2['中大型AUTO'] = Math.max(0, Math.round(autoTotal * (Number(autoLocal['中大型AUTO'] || 0) / 100)))
  }
  const fixed = apportionToTarget(['中小型G', '中小型XS', '中大型XS', '中小型AUTO', '中大型AUTO'], globalLevel2, 100)
  for (const k of Object.keys(fixed)) globalLevel2[k] = fixed[k]
  globalLevel2[SPECIAL] = 0

  for (const family of ['G', 'XS', 'AUTO'] as MajorFamily[]) {
    const groups = groupsByFamily.value[family] || []
    const familyTotal = groups.reduce((sum, group) => sum + Number(globalLevel2[group.category] || 0), 0)
    familyLevel1[family] = familyTotal
    const source: Record<string, number> = {}
    const localCategories = form.level2[family] || {}
    for (const group of groups) {
      const categoryBasis = familyTotal > 0
        ? Number(globalLevel2[group.category] || 0)
        : Number(localCategories[group.category] || 0)
      for (const model of group.models || []) {
        source[model] = categoryBasis * Number(form.level3[group.category]?.[model] || 0) / 100
      }
    }
    const models = groups.flatMap((group) => group.models || [])
    const merged = apportionToTarget(models, source, 100)
    for (const key of Object.keys(familyModelRatios[family])) delete familyModelRatios[family][key]
    Object.assign(familyModelRatios[family], merged)
  }
  familyLevel1.SPECIAL = 0
}

function normalizeRatioPayload(ratio: any) {
  const out = JSON.parse(JSON.stringify(ratio || {}))
  const normalizeFlat = (source: Record<string, any> = {}) => {
    const next: Record<string, number> = {}
    for (const [key, value] of Object.entries(source || {})) {
      const cat = normalizeCategory(key)
      next[cat] = Number(next[cat] || 0) + Number(value || 0)
    }
    return next
  }
  const normalizeLevel2 = (source: Record<string, Record<string, any>> = {}) => {
    const next: Record<string, Record<string, number>> = {}
    for (const [family, values] of Object.entries(source || {})) {
      next[family] = normalizeFlat(values || {})
    }
    return next
  }
  const normalizeLevel3 = (source: Record<string, Record<string, any>> = {}) => {
    const next: Record<string, Record<string, number>> = {}
    for (const [category, values] of Object.entries(source || {})) {
      const cat = normalizeCategory(category)
      next[cat] = { ...(next[cat] || {}), ...(values || {}) }
    }
    return next
  }
  out.level2_global = normalizeFlat(out.level2_global || {})
  out.level2 = normalizeLevel2(out.level2 || {})
  out.level3 = normalizeLevel3(out.level3 || {})
  return out
}

type HistoricalAppendices = {
  '总族类比例'?: Array<Record<string, unknown>>
  '丝杆订货需求比例'?: Array<Record<string, unknown>>
}

function historicalNumber(value: unknown) {
  const parsed = Number(value)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 0
}

function historicalModelKey(value: unknown) {
  return String(value || '').trim().replace(/\s+/g, '').toUpperCase()
}

function collectHistoricalScrewDemand(rows: Array<Record<string, unknown>>, family: MajorFamily) {
  const column = family === 'G' ? 'g' : family.toLowerCase()
  const demand: Record<string, number> = {}
  for (const row of rows) {
    const name = String(row[`${column}_name`] || '').trim()
    if (!name || name.endsWith('合计')) continue
    const key = historicalModelKey(name)
    if (!key) continue
    demand[key] = Number(demand[key] || 0) + historicalNumber(row[`${column}_quantity`])
  }
  return demand
}

async function fillFromHistoricalData() {
  try {
    await ElMessageBox.confirm(
      '将以不限日期的历史订单统计覆盖当前未保存比例；完成后仍需点击“保存目标比例”才会生效。是否继续？',
      '按往期数据自动填入',
      { type: 'warning', confirmButtonText: '自动填入', cancelButtonText: '取消' }
    )
  } catch {
    return
  }

  autoFilling.value = true
  try {
    const result = await apiGet<{ appendices?: HistoricalAppendices }>('/reports/orders?format=json')
    const appendices = result.appendices || {}
    const familyQuantities: Record<MajorFamily, number> = { G: 0, XS: 0, AUTO: 0, SPECIAL: 0 }
    const categoryFamily: Record<string, MajorFamily> = {
      中小型G: 'G',
      中小型XS: 'XS',
      中大型XS: 'XS',
      中小型AUTO: 'AUTO',
      中大型AUTO: 'AUTO',
    }
    for (const row of appendices['总族类比例'] || []) {
      const family = categoryFamily[String(row['总族类'] || '').trim()]
      if (family) familyQuantities[family] += historicalNumber(row['累计出货'])
    }
    const historicalTotal = familyQuantities.G + familyQuantities.XS + familyQuantities.AUTO
    if (historicalTotal <= 0) {
      throw new Error('历史订单中没有可用于 G、XS、AUTO 族的统计数据')
    }

    const familyValues = apportionToTarget(['G', 'XS', 'AUTO'], familyQuantities, 100)
    familyLevel1.G = familyValues.G
    familyLevel1.XS = familyValues.XS
    familyLevel1.AUTO = familyValues.AUTO

    const missingFamilies: string[] = []
    const screwRows = appendices['丝杆订货需求比例'] || []
    for (const family of ['G', 'XS', 'AUTO'] as MajorFamily[]) {
      const models = (groupsByFamily.value[family] || []).flatMap((group) => group.models || [])
      const demand = collectHistoricalScrewDemand(screwRows, family)
      const source: Record<string, number> = {}
      for (const model of models) source[model] = Number(demand[historicalModelKey(model)] || 0)

      if (Object.values(source).some((value) => value > 0)) {
        for (const key of Object.keys(familyModelRatios[family])) delete familyModelRatios[family][key]
        Object.assign(familyModelRatios[family], apportionToTarget(models, source, 100))
      } else {
        missingFamilies.push(family)
      }
    }

    const suffix = missingFamilies.length
      ? `；${missingFamilies.join('、')} 族没有匹配的历史丝杆需求，保留原机型分配`
      : ''
    ElMessage.success(`已按不限日期的往期订单数据填入${suffix}`)
  } catch (error: any) {
    ElMessage.error(error?.message || '自动填入失败')
  } finally {
    autoFilling.value = false
  }
}

function validate() {
  if (sumLevel1NoSpecial.value !== 100) return `大类比例合计必须等于 100，当前为 ${sumLevel1NoSpecial.value}`
  for (const group of familyModelGroups.value) {
    const sum = sumFamilyModels(group.family)
    if (sum !== 100) return `${group.label}机型比例合计必须等于 100，当前为 ${sum}`
  }
  return null
}

async function loadRatio() {
  const data = await sandboxApi.getCapacityRatio() as any
  const ratio = data?.ratio || data || {}
  loadFromRatio(ratio)
}

function isSpecialInventoryModel(name: string) {
  const raw = String(name || '').trim()
  const upper = raw.toUpperCase()
  return specialModelSet.value.has(upper) ||
    upper === 'SPECIAL'
}

async function loadInventoryRatios() {
  inventoryLoading.value = true
  try {
    const inventoryRows = await inventoryStore.fetchInventory()
    const activeRows = getActiveInventoryRows(inventoryRows)
    const ratioRows = buildModelInventoryRatios(activeRows)
    const highCounts = new Map<string, number>()
    for (const item of activeRows) {
      const model = String(item['机型'] || '').trim()
      const status = String(item['状态'] || '')
      const highHint = `${model}|${String(item['合同备注'] || '')}`
      if (model && (status.startsWith('库存中') || status === '待入库') && highHint.includes('加高')) {
        const key = model.toUpperCase()
        highCounts.set(key, (highCounts.get(key) || 0) + 1)
      }
    }
    const modelFamilyMap = new Map<string, MajorFamily>()
    for (const group of groupsByFamily.value.G.concat(groupsByFamily.value.XS, groupsByFamily.value.AUTO)) {
      const family = CAT_TO_MAJOR[group.category]
      if (!family) continue
      for (const model of group.models || []) modelFamilyMap.set(String(model).trim().toUpperCase(), family)
    }
    const modelRows: Array<{ name: string; family: MajorFamily; current_qty: number; high_qty: number }> = []
    for (const row of ratioRows) {
      if (!row.model || isSpecialInventoryModel(row.model)) continue
      const category = categoryOfModel(row.model)
      const family = modelFamilyMap.get(String(row.model).trim().toUpperCase()) || CAT_TO_MAJOR[category]
      if (!family || family === 'SPECIAL') continue
      const currentQty = row.inStock + row.pending
      if (currentQty <= 0) continue
      modelRows.push({
        name: row.model,
        family,
        current_qty: currentQty,
        high_qty: highCounts.get(String(row.model).trim().toUpperCase()) || 0
      })
    }
    const familyTotals: Record<string, number> = {}
    for (const row of modelRows) familyTotals[row.family] = (familyTotals[row.family] || 0) + row.current_qty
    inventoryTotal.value = Object.values(familyTotals).reduce((sum, count) => sum + count, 0)
    inventoryRatioRows.value = modelRows
      .map((row) => ({
        ...row,
        current_pct: familyTotals[row.family] > 0 ? (row.current_qty / familyTotals[row.family]) * 100 : 0
      }))
      .sort((a, b) => a.family.localeCompare(b.family) || compareModels(a.name, b.name))
  } catch {
    inventoryTotal.value = 0
    inventoryRatioRows.value = []
  } finally {
    inventoryLoading.value = false
  }
}

async function save() {
  const err = validate()
  if (err) {
    msg.value = err
    msgColor.value = '#f56c6c'
    return
  }
  saving.value = true
  try {
    const payload = buildBackendPayload()
    await sandboxApi.updateCapacityRatio(payload)
    msg.value = '保存成功'
    msgColor.value = '#67c23a'
  } catch (e: any) {
    msg.value = e.message || '保存失败'
    msgColor.value = '#f56c6c'
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  ensureShape()
  await loadModelTypes()
  await Promise.all([loadInventoryRatios(), loadRatio()])
})
</script>

<style scoped>
.ratio-editor-layout {
  position: relative;
  width: 100%;
}
.ratio-editor-left {
  width: calc(100% - 420px);
  min-width: 0;
}
.ratio-collapse-toggle {
  width: 240px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 14px;
  font-weight: 600;
  color: #374151;
  background: #ffffff;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  padding: 8px 16px;
  cursor: pointer;
  transition: all 0.2s ease;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
}
.ratio-collapse-toggle:hover {
  border-color: #3b82f6;
  color: #1d4ed8;
  background: #f8fafc;
}
.ratio-collapse-toggle.is-active {
  border-color: #3b82f6;
  background: #f8fafc;
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.1);
}
.ratio-collapse-toggle .arrow { 
  transition: transform 0.24s cubic-bezier(0.4, 0, 0.2, 1); 
  font-size: 12px;
  color: #9ca3af;
}
.ratio-collapse-toggle:hover .arrow {
  color: #3b82f6;
}
.ratio-collapse-toggle .arrow.open { 
  transform: rotate(180deg); 
  color: #3b82f6;
}

.ratio-collapse-body {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 16px;
  margin-top: 8px;
  box-shadow: 0 4px 10px rgba(0, 0, 0, 0.03);
}

.ratio-config-panel { 
  min-width: 0; 
}
.inventory-ratio-panel {
  position: absolute;
  top: 0;
  right: 0;
  z-index: 1000;
  width: 400px;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 16px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08);
  transition: box-shadow 0.2s, border-color 0.2s;
  cursor: grab;
}
.inventory-ratio-panel :deep(.el-table),
.inventory-ratio-panel :deep(.el-table tr),
.inventory-ratio-panel :deep(.el-table td) {
  cursor: grab;
}
.inventory-ratio-panel.is-zoomed {
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.12);
}
.inventory-ratio-panel.is-zoomed :deep(.el-table),
.inventory-ratio-panel.is-zoomed :deep(.el-table__inner-wrapper),
.inventory-ratio-panel.is-zoomed :deep(.el-table__body-wrapper),
.inventory-ratio-panel.is-zoomed :deep(.el-scrollbar),
.inventory-ratio-panel.is-zoomed :deep(.el-scrollbar__wrap) {
  height: auto !important;
  max-height: none !important;
}
.inventory-ratio-panel.is-dragging {
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.15), 0 10px 10px -5px rgba(0, 0, 0, 0.1);
  border-color: #3b82f6;
  cursor: grabbing;
}
.inventory-ratio-panel.is-dragging :deep(.el-table),
.inventory-ratio-panel.is-dragging :deep(.el-table tr),
.inventory-ratio-panel.is-dragging :deep(.el-table td) {
  cursor: grabbing;
}
.inventory-ratio-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
  border-bottom: 1px solid #e2e8f0;
  padding-bottom: 8px;
  user-select: none;
}
.header-title-area {
  display: flex;
  align-items: baseline;
  gap: 12px;
}
.header-title-area strong {
  font-size: 14px;
  color: #1f2937;
}
.header-title-area span {
  color: #6b7280;
  font-size: 11px;
}
.header-zoom-button {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  background: #ffffff;
  color: #4b5563;
  font-size: 11px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  user-select: none;
}
.header-zoom-button:hover {
  background: #f3f4f6;
  border-color: #3b82f6;
  color: #2563eb;
}
.header-zoom-button:active {
  background: #e5e7eb;
}
.header-zoom-button .zoom-icon {
  flex-shrink: 0;
  color: currentColor;
}
.section-block { 
  background: #fdfdfd;
  border: 1px solid #f3f4f6;
  border-radius: 8px;
  padding: 12px 16px;
  margin-bottom: 12px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.01);
}
.section-block strong {
  display: block;
  font-size: 13px;
  color: #374151;
  margin-bottom: 10px;
  border-left: 3px solid #3b82f6;
  padding-left: 8px;
}
.group-block { margin-top: 8px; margin-bottom: 6px; }
.ratio-row { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin-top: 6px; }
.ratio-item { 
  display: flex; 
  align-items: center; 
  gap: 6px;
  background: #f9fafb;
  padding: 4px 8px;
  border-radius: 6px;
  border: 1px solid #f3f4f6;
  transition: all 0.2s ease;
}
.ratio-item:hover {
  background: #f3f4f6;
  border-color: #e5e7eb;
}
.ratio-item label {
  font-size: 12px;
  font-weight: 500;
  color: #4b5563;
}
.sum-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: 4px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  transition: all 0.2s ease;
}
.sum-badge.is-valid {
  background-color: #f0fdf4;
  color: #16a34a;
  border: 1px solid #bbf7d0;
}
.sum-badge.is-invalid {
  background-color: #fef2f2;
  color: #dc2626;
  border: 1px solid #fecaca;
}
.sum-badge .status-icon {
  font-size: 12px;
}
.panel-actions {
  display: flex;
  align-items: center;
  margin-top: 16px;
}
.message-bubble {
  margin-left: 12px;
  font-size: 13px;
  font-weight: 500;
  padding: 6px 12px;
  border-radius: 6px;
  border: 1px solid transparent;
  display: inline-flex;
  align-items: center;
  transition: all 0.3s ease;
}
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}
.inventory-table-shell {
  position: relative;
  border-radius: 6px;
  overflow: hidden;
}
.inventory-family-groups {
  max-height: 260px;
  overflow-y: auto;
  background: #fff;
}
.inventory-family-group + .inventory-family-group {
  margin-top: 10px;
  border-top: 1px solid #e5e7eb;
  padding-top: 8px;
}
.inventory-family-title {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  padding: 0 8px 6px;
}
.inventory-family-title strong {
  color: #1f2937;
  font-size: 12px;
}
.inventory-family-title span {
  color: #6b7280;
  font-size: 10px;
}
.inventory-family-group :deep(.el-table__header-wrapper th) {
  background: #f8fafc;
}
.inventory-ratio-panel.is-zoomed .inventory-family-groups {
  max-height: none;
  overflow: visible;
}
.inventory-zoom-overlay {
  position: absolute;
  inset: 0;
  z-index: 20;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  border: none;
  background: rgba(15, 23, 42, 0.18);
  backdrop-filter: blur(3px);
  color: #0f172a;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.18s ease;
}
.inventory-table-shell:hover .inventory-zoom-overlay {
  opacity: 1;
}
.inventory-zoom-icon {
  position: relative;
  width: 54px;
  height: 54px;
  border: 4px solid #2563eb;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.86);
  box-shadow: 0 10px 26px rgba(37, 99, 235, 0.24);
}
.inventory-zoom-icon::after {
  content: '';
  position: absolute;
  width: 22px;
  height: 4px;
  right: -16px;
  bottom: 4px;
  border-radius: 999px;
  background: #2563eb;
  transform: rotate(45deg);
  transform-origin: center;
}
.inventory-zoom-overlay span:last-child {
  padding: 6px 14px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.9);
  color: #1f2937;
  font-size: 14px;
  font-weight: 800;
  box-shadow: 0 8px 22px rgba(15, 23, 42, 0.12);
}
@media (max-width: 1000px) {
  .ratio-editor-layout {
    display: flex;
    flex-direction: column;
    align-items: stretch;
  }
  .ratio-editor-left {
    width: 100%;
  }
  .inventory-ratio-panel {
    position: static;
    width: 100%;
    margin-top: 12px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
  }
}
</style>
