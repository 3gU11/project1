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

    <section v-if="panels.length" class="todo-grid">
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

    <section v-if="panels.length" class="detail-grid">
      <article v-for="panel in panels" :key="panel.key" class="detail-panel">
        <header class="detail-head">
          <div>
            <h2>{{ panel.title }}</h2>
            <p>{{ panel.hint }}</p>
          </div>
          <button type="button" class="detail-more" @click="go(panel.path)">查看全部 →</button>
        </header>
        <ul v-if="panel.items.length" class="detail-list">
          <li v-for="item in panel.items" :key="item.key">
            <span class="item-main">{{ item.title }}</span>
            <span class="item-meta">{{ item.meta }}</span>
          </li>
        </ul>
        <p v-else class="panel-empty">暂无待办</p>
      </article>
    </section>

    <p v-if="loading && !panels.length" class="state-tip">正在读取待办…</p>
    <p v-else-if="!panels.length" class="state-tip">当前账号暂无待办，请使用左侧菜单进入业务功能。</p>

    <p class="menu-tip">全部功能统一收在左侧菜单；首页只展示需要处理的待办。</p>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { useUserStore } from "../store/user";
import { apiGet } from "../utils/request";

type DetailItem = { key: string; title: string; meta: string };
type Panel = {
  key: string;
  title: string;
  hint: string;
  count: number;
  unit: string;
  path: string;
  icon: string;
  tone: string;
  items: DetailItem[];
};

const router = useRouter();
const userStore = useUserStore();

const userName = computed(() => userStore.userInfo?.name || "-");
const userRole = computed(() => userStore.userInfo?.role || "-");
const loading = ref(false);

const dealerPending = ref(0);
const shippingPending = ref(0);
const deliveryPending = ref(0);
const workflowPending = ref(0);

const dealerItems = ref<DetailItem[]>([]);
const shippingItems = ref<DetailItem[]>([]);
const deliveryItems = ref<DetailItem[]>([]);
const workflowItems = ref<DetailItem[]>([]);

const can = (permission?: string) =>
  !permission || Boolean(userStore.hasPermission(permission));

const isWorkflowOperator = computed(() => {
  const role = String(userStore.userInfo?.role || "").toLowerCase();
  return ["admin", "boss"].includes(role);
});

const formatTime = (value: unknown) => {
  const raw = String(value || "").trim();
  if (!raw) return "";
  return raw.replace("T", " ").slice(5, 16);
};

const panels = computed<Panel[]>(() => {
  const list: Panel[] = [];
  if (can("DEALER_ORDER_REVIEW")) {
    list.push({
      key: "dealer-orders",
      title: "经销商订单待审核",
      hint: "审核经销商提交的订货单",
      count: dealerPending.value,
      unit: "单",
      path: "/dealer-orders",
      icon: "🧾",
      tone: "amber",
      items: dealerItems.value,
    });
  }
  if (can("SHIP_CONFIRM")) {
    list.push({
      key: "shipping-review",
      title: "待发货复核",
      hint: "核对机台并确认发货",
      count: shippingPending.value,
      unit: "台",
      path: "/shipping-review",
      icon: "🚚",
      tone: "green",
      items: shippingItems.value,
    });
  }
  if (can("QUERY")) {
    list.push({
      key: "delivery-uploads",
      title: "交付信息待处理",
      hint: "识别合同并关联机台",
      count: deliveryPending.value,
      unit: "份",
      path: "/customer-finished-goods",
      icon: "📄",
      tone: "blue",
      items: deliveryItems.value,
    });
  }
  if (isWorkflowOperator.value || workflowPending.value > 0) {
    list.push({
      key: "workflow",
      title: "流程任务待处理",
      hint: "查看分配给我的流程任务",
      count: workflowPending.value,
      unit: "项",
      path: isWorkflowOperator.value ? "/workflow/tasks" : "/approval-center",
      icon: "✅",
      tone: "violet",
      items: workflowItems.value,
    });
  }
  return list;
});

const cards = computed(() => panels.value);

const loadCounts = async () => {
  loading.value = true;
  const tasks: Promise<void>[] = [];

  if (can("DEALER_ORDER_REVIEW")) {
    tasks.push(
      apiGet<{ data?: any[]; total?: number }>("/dealer-orders/", {
        params: { status: "todo", page: 1, page_size: 5 },
      })
        .then((res) => {
          const rows = res.data || [];
          dealerPending.value = Number(res.total || rows.length);
          dealerItems.value = rows.slice(0, 5).map((row: any) => ({
            key: String(row.order_no || row.id || row.created_at || Math.random()),
            title: String(row.order_no || "-"),
            meta: [row.customer_name || row.dealer_name, formatTime(row.created_at)]
              .filter(Boolean)
              .join(" · "),
          }));
        })
        .catch(() => {
          dealerPending.value = 0;
          dealerItems.value = [];
        }),
    );
  }

  if (can("SHIP_CONFIRM")) {
    tasks.push(
      apiGet<{ data?: any[] }>("/inventory/shipping/pending")
        .then((res) => {
          const rows = res.data || [];
          shippingPending.value = rows.length;
          const groups = new Map<string, { orderNo: string; customer: string; count: number }>();
          for (const row of rows) {
            const orderNo = String(row["占用订单号"] || "").trim();
            if (!orderNo) continue;
            const current = groups.get(orderNo) || {
              orderNo,
              customer: String(row["客户"] || "").trim(),
              count: 0,
            };
            current.count += 1;
            groups.set(orderNo, current);
          }
          shippingItems.value = [...groups.values()].slice(0, 5).map((group) => ({
            key: group.orderNo,
            title: group.orderNo,
            meta: [group.customer, `${group.count} 台`].filter(Boolean).join(" · "),
          }));
        })
        .catch(() => {
          shippingPending.value = 0;
          shippingItems.value = [];
        }),
    );
  }

  if (can("QUERY")) {
    tasks.push(
      apiGet<{ data?: any[] }>("/inventory/delivery-info-uploads", {
        params: { status: "pending", limit: 100 },
      })
        .then((res) => {
          const rows = res.data || [];
          deliveryPending.value = rows.length;
          deliveryItems.value = rows.slice(0, 5).map((row: any) => ({
            key: String(row.id || row.file_name || Math.random()),
            title: String(row.file_name || "-"),
            meta: [
              row.machine_nos || row.buyer_name || "未识别机台",
              formatTime(row.uploaded_at),
            ]
              .filter(Boolean)
              .join(" · "),
          }));
        })
        .catch(() => {
          deliveryPending.value = 0;
          deliveryItems.value = [];
        }),
    );
  }

  tasks.push(
    apiGet<{ data?: any[] }>("/workflows/tasks", {
      params: { status: "待处理", limit: 500 },
    })
      .then((res) => {
        const username = String(userStore.userInfo?.username || "");
        const mine = (res.data || []).filter(
          (task: any) => String(task.assignee_id || "") === username,
        );
        workflowPending.value = mine.length;
        workflowItems.value = mine.slice(0, 5).map((task: any) => ({
          key: String(task.id || task.instance_id || Math.random()),
          title: String(task.node_type || "流程任务"),
          meta: [task.instance_id ? `实例 ${task.instance_id}` : "", formatTime(task.assigned_at)]
            .filter(Boolean)
            .join(" · "),
        }));
      })
      .catch(() => {
        workflowPending.value = 0;
        workflowItems.value = [];
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
  padding: 30px 40px;
  max-width: 1400px;
  margin: 0 auto;
  min-height: calc(100vh - 44px);
  box-sizing: border-box;
}
.home-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 24px;
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
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}
.todo-card {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 102px;
  padding: 16px;
  border: 1px solid rgba(15, 23, 42, 0.07);
  border-radius: 15px;
  background: #fff;
  box-shadow: 0 3px 12px rgba(15, 23, 42, 0.035);
  text-align: left;
  cursor: pointer;
  transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
}
.todo-card:hover {
  transform: translateY(-2px);
  border-color: rgba(37, 99, 235, 0.22);
  box-shadow: 0 8px 20px rgba(15, 23, 42, 0.07);
}
.todo-icon {
  display: grid;
  place-items: center;
  flex: none;
  width: 42px;
  height: 42px;
  border-radius: 12px;
  background: #f1f5f9;
  font-size: 20px;
}
.todo-main {
  display: grid;
  gap: 4px;
  min-width: 0;
}
.todo-title {
  color: #334155;
  font-size: 13px;
  font-weight: 600;
}
.todo-count {
  color: #0f172a;
  font-size: 27px;
  font-weight: 800;
  line-height: 1;
  font-variant-numeric: tabular-nums;
}
.todo-count small {
  margin-left: 3px;
  color: #94a3b8;
  font-size: 11px;
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
  font-size: 17px;
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
.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  margin-top: 18px;
}
.detail-panel {
  min-height: 220px;
  padding: 18px;
  border: 1px solid rgba(15, 23, 42, 0.07);
  border-radius: 15px;
  background: #fff;
  box-shadow: 0 3px 12px rgba(15, 23, 42, 0.03);
}
.detail-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid rgba(15, 23, 42, 0.06);
}
.detail-head h2 {
  margin: 0;
  color: #1e293b;
  font-size: 14px;
  font-weight: 700;
}
.detail-head p {
  margin: 4px 0 0;
  color: #94a3b8;
  font-size: 11px;
}
.detail-more {
  flex: none;
  border: 0;
  background: transparent;
  color: #2563eb;
  font-size: 12px;
  cursor: pointer;
  padding: 2px 0;
}
.detail-more:hover {
  color: #1d4ed8;
  text-decoration: underline;
}
.detail-list {
  display: grid;
  gap: 0;
  margin: 0;
  padding: 0;
  list-style: none;
}
.detail-list li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 11px 2px;
  border-bottom: 1px dashed rgba(15, 23, 42, 0.06);
}
.detail-list li:last-child {
  border-bottom: 0;
}
.item-main {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #334155;
  font-size: 13px;
  font-weight: 600;
}
.item-meta {
  flex: none;
  max-width: 45%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #94a3b8;
  font-size: 11px;
}
.panel-empty {
  margin: 42px 0 0;
  color: #cbd5e1;
  font-size: 12px;
  text-align: center;
}
.state-tip,
.menu-tip {
  margin: 18px 0 0;
  color: #94a3b8;
  font-size: 13px;
}
.menu-tip {
  padding-top: 16px;
  border-top: 1px dashed rgba(15, 23, 42, 0.08);
  margin-top: 26px;
  font-size: 12px;
}
@media (max-width: 1100px) {
  .todo-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
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
  .todo-grid,
  .detail-grid {
    grid-template-columns: 1fr;
  }
}
</style>
