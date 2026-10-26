<template>
  <div class="page">
    <van-nav-bar title="消息中心" fixed placeholder />

    <div class="card toolbar">
      <div class="toolbar-row">
        <van-switch v-model="unreadOnly" size="20px" @change="onFilterChange" />
        <span class="toolbar-label">仅看未读</span>
        <span class="toolbar-count">未读 {{ unreadCount }}</span>
        <van-button size="mini" plain type="primary" :disabled="!unreadCount" @click="readAll">全部已读</van-button>
      </div>
    </div>

    <van-pull-refresh v-model="refreshing" @refresh="refresh">
      <div v-if="loading" class="loading-wrap">
        <van-loading size="20px">加载中...</van-loading>
      </div>

      <template v-else-if="items.length">
        <div
          v-for="item in items"
          :key="item.message_key"
          class="card message"
          :class="{ unread: item.unread }"
          @click="open(item)"
        >
          <div class="message-head">
            <span class="message-title">{{ item.title }}</span>
            <span v-if="item.unread" class="dot" />
          </div>
          <div class="message-content">{{ item.content }}</div>
          <div class="message-time">{{ formatTime(item.event_at) }}</div>
        </div>

        <div class="pager">
          <div class="pager-total">共 {{ total }} 条 · 每页 {{ PAGE_SIZE }} 条</div>
          <van-pagination
            v-model="currentPage"
            :total-items="total"
            :items-per-page="PAGE_SIZE"
            hide-on-single-page
            @change="loadPage"
          />
        </div>
      </template>

      <van-empty v-else description="暂无消息" />
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
const refreshing = ref(false)
const total = ref(0)
const currentPage = ref(1)
// 移动端一屏最多显示 8 行，避免长列表把翻页入口挤到屏幕外。
const PAGE_SIZE = 8

const formatTime = (value?: string) => String(value || '').replace('T', ' ').slice(0, 16)

const loadPage = async (pageNo: number = currentPage.value) => {
  loading.value = true
  try {
    const res = await workflowApi.getPersonalMessages({
      page: pageNo,
      limit: PAGE_SIZE,
      unread: unreadOnly.value,
    })
    const rows = res.data || []
    const totalItems = Number(res.total || 0)
    unreadCount.value = Number(res.unread_count || 0)
    total.value = totalItems

    // 标记已读或切换筛选后，当前页可能已经越界，回退到最后一页。
    const lastPage = Math.max(1, Math.ceil(totalItems / PAGE_SIZE))
    if (!rows.length && pageNo > lastPage) {
      currentPage.value = lastPage
      await loadPage(lastPage)
      return
    }

    currentPage.value = pageNo
    items.value = rows
  } catch {
    items.value = []
    total.value = 0
  } finally {
    loading.value = false
    refreshing.value = false
  }
}

const reload = async () => {
  currentPage.value = 1
  await loadPage(1)
}

/** 下拉刷新只刷新当前页，不把用户踢回第一页。 */
const refresh = async () => {
  refreshing.value = true
  await loadPage(currentPage.value)
}

const onFilterChange = async () => {
  currentPage.value = 1
  await loadPage(1)
}

/** 通知底部导航刷新未读徽标（Layout 监听该事件）。 */
const notifyInboxChanged = () => {
  window.dispatchEvent(new Event('workflow-inbox-updated'))
}

const readAll = async () => {
  try {
    await workflowApi.readAllPersonalMessages()
    showToast('已全部标记为已读')
    notifyInboxChanged()
    await reload()
  } catch { /* 拦截器已提示 */ }
}

const open = async (item: PersonalMessage) => {
  if (item.unread) {
    try {
      await workflowApi.readPersonalMessage(item.message_key)
      item.unread = false
      unreadCount.value = Math.max(0, unreadCount.value - 1)
      notifyInboxChanged()
      // 仅看未读时，读完的这条要立刻从当前页移除，并补齐该页条数。
      if (unreadOnly.value) await loadPage(currentPage.value)
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
.loading-wrap {
  display: flex;
  justify-content: center;
  padding: 40px 0;
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
.pager {
  padding: 12px 0 4px;
}
.pager-total {
  margin-bottom: 8px;
  text-align: center;
  font-size: 12px;
  color: #969799;
}
</style>
