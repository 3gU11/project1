<template>
  <div class="notification-box">
    <el-button class="bell-button" :icon="Bell" circle :aria-label="`合同消息，${unreadCount} 条未读`" title="合同消息" @click="togglePanel" />
    <span v-if="unreadCount" class="unread-badge">{{ unreadCount > 99 ? '99+' : unreadCount }}</span>
    <div v-if="open" class="notification-panel">
      <div class="panel-head">
        <strong>合同消息</strong>
        <el-button text size="small" :disabled="!unreadCount || loading" @click="readAll">全部已读</el-button>
      </div>
      <div class="panel-tabs" role="tablist" aria-label="消息筛选">
        <button type="button" role="tab" :aria-selected="!unreadOnly" :class="{ selected: !unreadOnly }" @click="setFilter(false)">全部</button>
        <button type="button" role="tab" :aria-selected="unreadOnly" :class="{ selected: unreadOnly }" @click="setFilter(true)">未读</button>
      </div>
      <div class="panel-list" v-loading="loading">
        <el-alert v-if="error" type="error" title="消息加载失败" :closable="false">
          <template #default><el-button text size="small" @click="loadList">重试</el-button></template>
        </el-alert>
        <el-empty v-else-if="!loading && !items.length" description="暂无消息" :image-size="64" />
        <div v-for="item in items" :key="item.contract_id" class="message" :class="{ unread: item.unread }">
          <button class="message-summary" type="button" :aria-expanded="expanded === item.contract_id" @click="expand(item)">
            <span class="summary-first"><span class="contract-id">{{ item.contract_id }}</span><span class="stage">{{ latestStage(item) }}</span></span>
            <span class="summary-customer">{{ currentSnapshot(item)?.customer || '客户未填写' }}<span v-if="currentSnapshot(item)?.dealer"> · {{ currentSnapshot(item)?.dealer }}</span></span>
            <span class="summary-model">{{ models(currentSnapshot(item)) }}<span v-if="currentSnapshot(item)?.due_date"> · 交期 {{ currentSnapshot(item)?.due_date }}</span></span>
            <span class="summary-time">{{ formatTime(item.latest_at) }}</span>
          </button>
          <div v-if="expanded === item.contract_id" class="message-detail">
            <div class="stage-detail">
              <strong>合同已录入</strong>
              <template v-if="item.created_at">
                <span>{{ item.created_by || '未知操作人' }} · {{ formatTime(item.created_at) }}</span>
                <span>{{ models(item.created_snapshot) }}<template v-if="item.created_snapshot?.due_date"> · 交期 {{ item.created_snapshot.due_date }}</template></span>
              </template>
              <span v-else>上线前已录入</span>
            </div>
            <div class="stage-detail">
              <strong>已规划</strong>
              <template v-if="item.planned_at">
                <span>{{ item.planned_by || '未知操作人' }} · {{ formatTime(item.planned_at) }}</span>
                <span>{{ models(item.planned_snapshot) }}<template v-if="item.planned_snapshot?.due_date"> · 交期 {{ item.planned_snapshot.due_date }}</template></span>
              </template>
              <span v-else>待规划</span>
            </div>
            <div class="stage-detail">
              <strong>{{ item.order_id ? '已转订单' : '待转订单' }}</strong>
              <template v-if="item.order_id">
                <span>{{ item.converted_by || '未知操作人' }} · {{ formatTime(item.converted_at) }}</span>
                <span>订单 {{ item.order_id }}</span>
                <span>{{ models(item.converted_snapshot) }}<template v-if="item.converted_snapshot?.due_date"> · 交期 {{ item.converted_snapshot.due_date }}</template></span>
              </template>
              <span v-else>尚未生成订单</span>
            </div>
          </div>
        </div>
      </div>
      <div v-if="total > pageSize" class="panel-footer">
        <el-pagination small layout="prev, pager, next" :total="total" :page-size="pageSize" :current-page="page" @current-change="changePage" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { Bell } from '@element-plus/icons-vue'
import { apiGet, apiPost } from '../utils/request'

type Snapshot = { customer: string; dealer: string; due_date: string; models: { model: string; quantity: number }[]; total: number }
type Message = {
  contract_id: string; created_snapshot: Snapshot | null; created_by: string | null; created_at: string | null
  planned_snapshot: Snapshot | null; planned_by: string | null; planned_at: string | null
  converted_snapshot: Snapshot | null; converted_by: string | null; converted_at: string | null
  order_id: string | null; latest_at: string; version: number; unread: boolean
}
const pageSize = 20
const open = ref(false)
const loading = ref(false)
const error = ref(false)
const unreadOnly = ref(false)
const unreadCount = ref(0)
const items = ref<Message[]>([])
const total = ref(0)
const page = ref(1)
const expanded = ref('')
let timer: ReturnType<typeof setInterval> | null = null
let requestSerial = 0

const currentSnapshot = (item: Message) => item.converted_snapshot || item.planned_snapshot || item.created_snapshot
const latestStage = (item: Message) => item.order_id ? '已转订单' : item.planned_at ? '已规划' : '已录入'
const models = (snapshot: Snapshot | null) => snapshot?.models?.map((entry) => `${entry.model} × ${entry.quantity}`).join('、') || '需求未记录'
const formatTime = (value: string | null) => value ? value.replace('T', ' ').slice(0, 16) : ''

async function refreshCount() {
  if (document.hidden) return
  try {
    const result = await apiGet<{ total: number }>('/notifications/unread-count')
    unreadCount.value = result.total
    if (open.value) await loadList()
  } catch { /* The request interceptor reports the error. */ }
}

async function loadList() {
  if (!open.value) return
  const serial = ++requestSerial
  loading.value = true
  error.value = false
  try {
    const result = await apiGet<{ data: Message[]; total: number }>(`/notifications?page=${page.value}&limit=${pageSize}&unread=${unreadOnly.value}`)
    if (serial !== requestSerial) return
    items.value = result.data
    total.value = result.total
    if (page.value > 1 && !items.value.length) { page.value--; void loadList() }
  } catch {
    if (serial === requestSerial) error.value = true
  } finally {
    if (serial === requestSerial) loading.value = false
  }
}

function togglePanel() {
  open.value = !open.value
  if (open.value) { page.value = 1; void loadList(); void refreshCount() }
}
function setFilter(value: boolean) { unreadOnly.value = value; page.value = 1; expanded.value = ''; void loadList() }
function changePage(value: number) { page.value = value; expanded.value = ''; void loadList() }
async function expand(item: Message) {
  expanded.value = expanded.value === item.contract_id ? '' : item.contract_id
  if (!expanded.value || !item.unread) return
  try {
    await apiPost(`/notifications/${encodeURIComponent(item.contract_id)}/read`, { version: item.version })
    item.unread = false
    await refreshCount()
  } catch { /* Keep unread when the write fails. */ }
}
async function readAll() {
  try {
    await apiPost('/notifications/read-all', {})
    expanded.value = ''
    await refreshCount()
    await loadList()
  } catch { /* Keep the current state when the write fails. */ }
}
function onVisibility() { if (!document.hidden) void refreshCount() }
onMounted(() => {
  void refreshCount()
  timer = setInterval(() => { void refreshCount() }, 30000)
  document.addEventListener('visibilitychange', onVisibility)
})
onBeforeUnmount(() => {
  requestSerial++
  if (timer) clearInterval(timer)
  document.removeEventListener('visibilitychange', onVisibility)
})
</script>

<style scoped>
.notification-box { position: relative; }
.bell-button { width: 34px; height: 34px; }
.unread-badge { position: absolute; top: -4px; right: -9px; min-width: 18px; height: 18px; padding: 0 4px; border-radius: 9px; background: #c03632; color: white; font-size: 11px; line-height: 18px; text-align: center; pointer-events: none; }
.notification-panel { position: absolute; right: 0; top: 42px; z-index: 1300; width: min(420px, calc(100vw - 20px)); max-height: min(680px, calc(100vh - 80px)); display: flex; flex-direction: column; background: white; border: 1px solid #d9e0e5; border-radius: 6px; box-shadow: 0 12px 32px #17212a30; color: #28313a; }
.panel-head { min-height: 48px; padding: 8px 14px; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #e5e8eb; }
.panel-tabs { display: flex; gap: 16px; padding: 0 14px; border-bottom: 1px solid #e5e8eb; }
.panel-tabs button { border: 0; border-bottom: 2px solid transparent; padding: 10px 3px 8px; background: none; color: #5c6670; cursor: pointer; }
.panel-tabs button.selected { color: #176553; border-bottom-color: #176553; font-weight: 600; }
.panel-list { min-height: 100px; overflow-y: auto; }
.message { border-bottom: 1px solid #edf0f1; }
.message.unread { background: #f4faf8; }
.message-summary { width: 100%; min-height: 100px; display: flex; flex-direction: column; align-items: stretch; gap: 4px; padding: 10px 14px; border: 0; background: transparent; text-align: left; cursor: pointer; color: inherit; }
.message-summary:hover { background: #edf6f3; }
.summary-first { display: flex; justify-content: space-between; gap: 10px; }
.contract-id { font-weight: 700; overflow-wrap: anywhere; }
.stage { color: #176553; white-space: nowrap; font-size: 12px; }
.summary-customer, .summary-model { color: #4c5862; font-size: 13px; overflow-wrap: anywhere; }
.summary-time { color: #78828a; font-size: 12px; }
.message-detail { padding: 0 14px 12px; display: grid; gap: 10px; }
.stage-detail { border-left: 2px solid #c5d9d2; padding-left: 10px; display: flex; flex-direction: column; gap: 3px; font-size: 12px; color: #52606a; overflow-wrap: anywhere; }
.stage-detail strong { color: #28313a; font-size: 13px; }
.panel-footer { display: flex; justify-content: center; padding: 8px; border-top: 1px solid #e5e8eb; }
</style>
