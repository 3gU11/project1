import { createRouter, createWebHistory } from 'vue-router'
import { showToast } from 'vant'
import { useUserStore } from '@/store/user'
import Layout from '@/components/layout/Layout.vue'

const routes = [
  { path: '/login', component: () => import('@/views/Login.vue'), meta: { requiresAuth: false } },
  {
    path: '/',
    component: Layout,
    meta: { requiresAuth: true },
    children: [
      { path: '', redirect: '/inbound' },
      { path: 'inbound', component: () => import('@/views/InboundWork.vue'), meta: { title: '入库作业', roles: ['inbound', 'admin'] } },
      {
        path: 'inventory-query',
        component: () => import('@/views/InventoryQuery.vue'),
        meta: { title: '库存查询', roles: ['inbound', 'warehouse', 'admin'] },
      },
      { path: 'slot-management', component: () => import('@/views/SlotManagement.vue'), meta: { title: '库位管理', roles: ['warehouse', 'admin'] } },
      { path: 'dashboard', component: () => import('@/views/Dashboard.vue'), meta: { title: '库位大屏', roles: ['warehouse', 'admin'] } },
      { path: 'profile', component: () => import('@/views/Profile.vue'), meta: { title: '个人中心' } },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  const userStore = useUserStore()
  if (to.meta.requiresAuth !== false && !userStore.isAuthed) {
    return '/login'
  }
  const roles = to.meta.roles as string[] | undefined
  if (roles && roles.length > 0 && !userStore.hasRole(roles)) {
    showToast('没有操作权限')
    return '/profile'
  }
  return true
})

router.afterEach((to) => {
  document.title = String(to.meta.title || 'V7ex仓储移动端')
})

export default router
