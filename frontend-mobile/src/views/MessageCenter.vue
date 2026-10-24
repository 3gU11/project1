<template>
  <div class="page">
    <van-nav-bar title="消息中心" fixed placeholder />

    <div class="card toolbar">
      <div class="toolbar-row">
        <van-switch v-model="unreadOnly" size="20px" @change="reload" />
        <span class="toolbar-label">仅看未读</span>
        <span class="toolbar-count">未读 {{ unreadCount }}</span>
        <van-button size="mini" plain type="primary" :disabled="!unreadCount" @click="readAll">全部已读</van-button>
      </div>
    </div>

    <van-pull-refresh v-model="refreshing" @refresh="reload">
      <van-list v-model:loading="loading" :finished="finished" finished-text="没有更多了" @load="onLoad">
        <div v-for="item in items" :key="item.message_key" class="card message" :class="{ unread: item.unread }" @click="open(item)">
          <div class="message-head">
            <span class="message-title">{{ item.title }}</span>
            <span v-if="item.unread" class="dot" />
          </div>
          <div class="message-content">{{ item.content }}</div>
          <div class="message-time">{{ formatTime(item.event_at) }}</div>
        </div>
      </van-list>
      <van-empty v-if="!loading && !items.length" description="暂无消息" />
    </van-pull-refresh>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { showToast } from 'vant'
import { workflowApi, type PersonalMessage } from '@/api/workflow'

const router = useRouter()
const items = ref<PersonalMessage[]>([])
const unreadCount = ref(0)
const unreadOnly = ref(false)
const loading = ref(false)
const finished = ref(false)
const refreshing = ref(false)
const page = ref(0)
const PAGE_SIZE = 20

const formatTime = (value?: string) => String(value || '').replace('T', ' ').slice(0, 16)

const fetchPage = async (pageNo: number) => {
  const res = await workflowApi.getPersonalMessages({ page: pageNo, limit: PAGE_SIZE, unread: unreadOnly.value })
  unreadCount.value = Number(res.unread_count || 0)
  return res
}

const onLoad = async () => {
  try {
    const res = await fetchPage(page.value + 1)
    const rows = res.data || []
    items.value = page.value === 0 ? rows : [...items.value, ...rows]
    page.value += 1
    finished.value = items.value.length >= Number(res.total || 0) || rows.length === 0
  } catch {
    finished.value = true
  } finally {
    loading.value = false
    refreshing.value = false
  }
}

const reload = async () => {
  page.value = 0
  items.value = []
  finished.value = false
  loading.value = true
  refreshing.value = true
  await onLoad()
}

const readAll = async () => {
  try {
    await workflowApi.readAllPersonalMessages()
    showToast('已全部标记为已读')
    await reload()
  } catch { /* 拦截器已提示 */ }
}

const open = async (item: PersonalMessage) => {
  if (item.unread) {
    try {
      await workflowApi.readPersonalMessage(item.message_key)
      item.unread = false
      unreadCount.value = Math.max(0, unreadCount.value - 1)
    } catch { /* 保持未读状态 */ }
  }
  // 重入库任务的来源页在 PC 是 /inbound，移动端对应「成品入库 → 重新入库」分区。
  if (String(item.target || '') === '/inbound') {
    router.push({ path: '/query', query: { tab: 'derived' } })
  }
}

onMounted(() => { void reload() })
</script>

<style scoped>
.page {
  padding-bottom: 12px;
}
.toolbar {
  padding: 10px 12px;
}
.toolbar-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.toolbar-label {
  font-size: 14px;
  color: #323233;
}
.toolbar-count {
  margin-left: auto;
  font-size: 13px;
  color: #969799;
}
.message {
  padding: 12px 14px;
}
.message.unread {
  border-left: 3px solid #1989fa;
}
.message-head {
  display: flex;
  align-items: center;
  gap: 6px;
}
.message-title {
  font-size: 15px;
  font-weight: 600;
  color: #323233;
}
.dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #ee0a24;
}
.message-content {
  margin-top: 4px;
  font-size: 13px;
  color: #646566;
  line-height: 1.5;
  word-break: break-all;
}
.message-time {
  margin-top: 6px;
  font-size: 12px;
  color: #969799;
}
</style>
