<template>
  <div class="home-page">
    <header class="home-head">
      <div>
        <h1 class="page-title">🏭 成品整机管理系统 <span>V8betaVer1.0</span></h1>
        <p class="subtitle">当前用户：{{ userName }} · 角色：{{ userRole }}</p>
      </div>
      <button type="button" class="refresh-btn" :disabled="loading" @click="loadCounts">
        {{ loading ? "读取中…" : "刷新待办" }}
      </button>
    </header>

    <section v-if="cards.length" class="todo-grid">
      <button
        v-for="card in cards"
        :key="card.key"
        type="button"
        class="todo-card"
        :class="`tone-${card.tone}`"
        @click="go(card.path)"
      >
        <span class="todo-icon">{{ card.icon }}</span>
        <span class="todo-main">
          <span class="todo-title">{{ card.title }}</span>
          <span class="todo-count">{{ card.count }}<small>{{ card.unit }}</small></span>
          <span class="todo-hint">{{ card.hint }}</span>
        </span>
        <span class="todo-arrow">→</span>
      </button>
    </section>

    <p v-if="loading && !cards.length" class="state-tip">正在读取待办…</p>
    <p v-else-if="!cards.length" class="state-tip">当前账号暂无待办，请使用左侧菜单进入业务功能。</p>

    <p class="menu-tip">全部功能统一收在左侧菜单；首页只展示需要处理的待办。</p>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { useUserStore } from "../store/user";
import { apiGet } from "../utils/request";

const router = useRouter();
const userStore = useUserStore();

const userName = computed(() => userStore.userInfo?.name || "-");
const userRole = computed(() => userStore.userInfo?.role || "-");
const loading = ref(false);

const dealerPending = ref(0);
const shippingPending = ref(0);
const deliveryPending = ref(0);
const workflowPending = ref(0);

const can = (permission?: string) =>
  !permission || Boolean(userStore.hasPermission(permission));

const isWorkflowOperator = computed(() => {
  const role = String(userStore.userInfo?.role || "").toLowerCase();
  return ["admin", "boss"].includes(role);
});

const cards = computed(() => {
  const items: Array<{
    key: string;
    title: string;
    count: number;
    unit: string;
    hint: string;
    path: string;
    icon: string;
    tone: string;
  }> = [];
  if (can("DEALER_ORDER_REVIEW")) {
    items.push({
      key: "dealer-orders",
      title: "经销商订单待审核",
      count: dealerPending.value,
      unit: "单",
      hint: "审核经销商提交的订货单",
      path: "/dealer-orders",
      icon: "🧾",
      tone: "amber",
    });
  }
  if (can("SHIP_CONFIRM")) {
    items.push({
      key: "shipping-review",
      title: "待发货复核",
      count: shippingPending.value,
      unit: "台",
      hint: "核对机台并确认发货",
      path: "/shipping-review",
      icon: "🚚",
      tone: "green",
    });
  }
  if (can("QUERY")) {
    items.push({
      key: "delivery-uploads",
      title: "交付信息待处理",
      count: deliveryPending.value,
      unit: "份",
      hint: "识别合同并关联机台",
      path: "/customer-finished-goods",
      icon: "📄",
      tone: "blue",
    });
  }
  if (isWorkflowOperator.value || workflowPending.value > 0) {
    items.push({
      key: "workflow",
      title: "流程任务待处理",
      count: workflowPending.value,
      unit: "项",
      hint: "查看分配给我的流程任务",
      path: isWorkflowOperator.value ? "/workflow/tasks" : "/approval-center",
      icon: "✅",
      tone: "violet",
    });
  }
  return items;
});

const loadCounts = async () => {
  loading.value = true;
  const tasks: Promise<void>[] = [];
  if (can("DEALER_ORDER_REVIEW")) {
    tasks.push(
      apiGet<{ total?: number }>("/dealer-orders/pending-count")
        .then((res) => {
          dealerPending.value = Number(res.total || 0);
        })
        .catch(() => {
          dealerPending.value = 0;
        }),
    );
  }
  if (can("SHIP_CONFIRM")) {
    tasks.push(
      apiGet<{ data?: any[] }>("/inventory/shipping/pending")
        .then((res) => {
          shippingPending.value = (res.data || []).length;
        })
        .catch(() => {
          shippingPending.value = 0;
        }),
    );
  }
  if (can("QUERY")) {
    tasks.push(
      apiGet<{ data?: any[] }>("/inventory/delivery-info-uploads", {
        params: { status: "pending", limit: 100 },
      })
        .then((res) => {
          deliveryPending.value = (res.data || []).length;
        })
        .catch(() => {
          deliveryPending.value = 0;
        }),
    );
  }
  tasks.push(
    apiGet<{ data?: any[] }>("/workflows/tasks", {
      params: { status: "待处理", limit: 500 },
    })
      .then((res) => {
        const username = String(userStore.userInfo?.username || "");
        workflowPending.value = (res.data || []).filter(
          (task: any) => String(task.assignee_id || "") === username,
        ).length;
      })
      .catch(() => {
        workflowPending.value = 0;
      }),
  );
  await Promise.allSettled(tasks);
  loading.value = false;
};

const go = (path: string) => {
  router.push(path);
};

onMounted(() => {
  void loadCounts();
});
</script>

<style scoped>
.home-page {
  padding: 32px 40px;
  max-width: 1280px;
  margin: 0 auto;
  min-height: calc(100vh - 44px);
  box-sizing: border-box;
}
.home-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 26px;
}
.page-title {
  margin: 0;
  font-size: 28px;
  font-weight: 700;
  color: var(--color-gray-900);
  letter-spacing: -0.01em;
  line-height: 1.25;
}
.page-title span {
  font-size: 18px;
  font-weight: 500;
  color: var(--color-gray-400);
}
.subtitle {
  margin: 8px 0 0;
  color: var(--color-gray-500);
  font-size: 12px;
}
.refresh-btn {
  flex: none;
  height: 34px;
  padding: 0 14px;
  border: 1px solid rgba(15, 23, 42, 0.1);
  border-radius: 9px;
  background: #fff;
  color: #475569;
  font-size: 13px;
  cursor: pointer;
}
.refresh-btn:hover:not(:disabled) {
  border-color: rgba(37, 99, 235, 0.35);
  color: #1d4ed8;
}
.refresh-btn:disabled {
  opacity: 0.6;
  cursor: default;
}
.todo-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 16px;
}
.todo-card {
  display: flex;
  align-items: center;
  gap: 14px;
  min-height: 118px;
  padding: 18px 18px 16px;
  border: 1px solid rgba(15, 23, 42, 0.07);
  border-radius: 16px;
  background: #fff;
  box-shadow: 0 4px 16px rgba(15, 23, 42, 0.04);
  text-align: left;
  cursor: pointer;
  transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
}
.todo-card:hover {
  transform: translateY(-2px);
  border-color: rgba(37, 99, 235, 0.22);
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.08);
}
.todo-icon {
  display: grid;
  place-items: center;
  flex: none;
  width: 46px;
  height: 46px;
  border-radius: 13px;
  background: #f1f5f9;
  font-size: 22px;
}
.todo-main {
  display: grid;
  gap: 5px;
  min-width: 0;
}
.todo-title {
  color: #334155;
  font-size: 13px;
  font-weight: 600;
}
.todo-count {
  color: #0f172a;
  font-size: 30px;
  font-weight: 800;
  line-height: 1;
  font-variant-numeric: tabular-nums;
}
.todo-count small {
  margin-left: 4px;
  color: #94a3b8;
  font-size: 12px;
  font-weight: 500;
}
.todo-hint {
  color: #94a3b8;
  font-size: 11px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.todo-arrow {
  margin-left: auto;
  align-self: center;
  color: #cbd5e1;
  font-size: 18px;
}
.tone-amber .todo-icon {
  background: #fff7e6;
}
.tone-green .todo-icon {
  background: #e9f8f1;
}
.tone-blue .todo-icon {
  background: #eaf2ff;
}
.tone-violet .todo-icon {
  background: #f1ecff;
}
.state-tip,
.menu-tip {
  margin: 18px 0 0;
  color: #94a3b8;
  font-size: 13px;
}
.menu-tip {
  padding-top: 18px;
  border-top: 1px dashed rgba(15, 23, 42, 0.08);
  margin-top: 28px;
  font-size: 12px;
}
@media (max-width: 768px) {
  .home-page {
    padding: 18px;
  }
  .home-head {
    flex-direction: column;
  }
  .page-title {
    font-size: 22px;
  }
  .todo-grid {
    grid-template-columns: 1fr;
  }
}
</style>
