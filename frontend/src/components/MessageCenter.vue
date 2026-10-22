<template>
  <div class="notification-box" ref="box">
    <el-button class="bell-button" :icon="Bell" circle title="消息中心" :aria-label="`消息中心，${count + contractCount} 条未读`" @click="toggle" />
    <span v-if="count + contractCount" class="unread-badge">{{ count + contractCount > 99 ? '99+' : count + contractCount }}</span>
    <div v-show="open" class="notification-panel">
      <div class="panel-head"><strong>消息中心</strong><el-button text @click="open = false">关闭</el-button></div>
      <div class="panel-tabs">
        <button :class="{ selected: tab === 'mine' }" @click="tab = 'mine'">我的消息 {{ count || '' }}</button>
        <button v-if="canContracts" :class="{ selected: tab === 'contracts' }" @click="tab = 'contracts'">合同动态 {{ contractCount || '' }}</button>
      </div>
      <div v-show="tab === 'mine'" class="personal-panel">
        <div class="panel-head"><el-switch v-model="unread" active-text="仅看未读" @change="page = 1; refresh()" /><el-button text :disabled="!count" @click="readAll">全部已读</el-button></div>
        <div class="panel-list" v-loading="loading">
          <el-alert v-if="error" title="消息加载失败，请重试" type="error" :closable="false"><el-button text @click="refresh">重试</el-button></el-alert>
          <el-empty v-else-if="!items.length" description="暂无消息" :image-size="64" />
          <div v-for="item in items" :key="item.message_key" class="message" :class="{ unread: item.unread }">
            <button class="message-summary" @click="read(item)"><strong>{{ item.title }}</strong><span class="summary-model">{{ item.content }}</span><span class="summary-time">{{ String(item.event_at || '').replace('T', ' ').slice(0, 19) }}</span><span v-if="canOpen(item)" class="stage">查看处理</span></button>
          </div>
        </div>
        <div v-if="total > 20" class="panel-footer"><el-pagination size="small" layout="prev, pager, next" :total="total" :page-size="20" v-model:current-page="page" @current-change="refresh" /></div>
      </div>
      <div v-if="canContracts" v-show="tab === 'contracts'"><ContractNotifications embedded @count="contractCount = $event" /></div>
    </div>
  </div>
</template>
<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Bell } from '@element-plus/icons-vue'
import { apiGet, apiPost } from '../utils/request'
import { useUserStore } from '../store/user'
import { canAccessPath } from '../router'
import ContractNotifications from './ContractNotifications.vue'
const user = useUserStore(), router = useRouter()
const canContracts = computed(() => user.hasPermission('NOTIFICATION_VIEW'))
type Message = { message_key: string; title: string; content: string; event_at: string; unread: boolean; target: string }
const box = ref<HTMLElement>(), open = ref(false), tab = ref('mine'), count = ref(0), contractCount = ref(0)
const page = ref(1), total = ref(0), unread = ref(false), loading = ref(false), error = ref(false), items = ref<Message[]>([])
let timer: ReturnType<typeof setInterval> | undefined
let serial = 0
async function refresh() {
  if (document.hidden) return
  const request = ++serial
  loading.value = true
  try {
    const r = await apiGet<{ data: Message[]; total: number; unread_count: number }>(`/workflows/personal-messages?page=${page.value}&unread=${unread.value}`)
    if (request !== serial) return
    items.value = r.data; total.value = r.total; count.value = r.unread_count; error.value = false
    if (page.value > 1 && !r.data.length) { page.value--; void refresh() }
  } catch { if (request === serial) error.value = true }
  finally { if (request === serial) loading.value = false }
}
function toggle() { open.value = !open.value; if (open.value) void refresh() }
const canOpen = (item: Message) => !!item.target && canAccessPath(item.target, user.userInfo?.permissions)
async function read(item: Message) {
  try {
    await apiPost('/workflows/personal-messages/read', { message_key: item.message_key })
    await refresh()
    if (canOpen(item)) { open.value = false; await router.push(item.target) }
  } catch { /* Preserve unread state on failure. */ }
}
async function readAll() { try { await apiPost('/workflows/personal-messages/read-all', {}); await refresh() } catch {} }
function outside(e: MouseEvent) { if (box.value && !box.value.contains(e.target as Node)) open.value = false }
function visible() { if (!document.hidden) void refresh() }
onMounted(() => { void refresh(); timer = setInterval(refresh, 30000); document.addEventListener('click', outside); document.addEventListener('visibilitychange', visible); window.addEventListener('workflow-pending-updated', visible) })
onBeforeUnmount(() => { serial++; clearInterval(timer); document.removeEventListener('click', outside); document.removeEventListener('visibilitychange', visible); window.removeEventListener('workflow-pending-updated', visible) })
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
.notification-panel.embedded { position: static; width: 100%; border: 0; box-shadow: none; max-height: 520px; }

.personal-panel { display: flex; flex-direction: column; min-height: 0; }
</style>
