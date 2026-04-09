import { createRouter, createWebHistory, RouteRecordRaw } from 'vue-router'
import { useUserStore } from '../store/user'
import { ElMessage } from 'element-plus'
import { normalizeRole, roleIn } from '../utils/roles'

export type AppMenuItem = {
  path: string
  label: string
  roles?: string[]
  isManagement?: boolean
}

type AppRouteDef = {
  path: string
  name: string
  label: string
  title: string
  roles?: string[]
  isManagement?: boolean
  component: () => Promise<unknown>
}

const appRouteDefs: AppRouteDef[] = [
  { path: '/planning', name: 'Planning', label: '👑 生产统筹/订单规划', title: '生产统筹', roles: ['Admin', 'Boss', 'Sales'], isManagement: true, component: () => import('../views/BossPlanning.vue') },
  { path: '/contracts', name: 'Contracts', label: '📊 合同管理', title: '合同管理', roles: ['Admin', 'Boss', 'Sales'], isManagement: true, component: () => import('../views/ContractManage.vue') },
  { path: '/users', name: 'Users', label: '👤 用户管理', title: '用户管理', roles: ['Admin'], isManagement: true, component: () => import('../views/UserManagement.vue') },
  { path: '/sales-orders', name: 'SalesOrders', label: '📌 销售下单', title: '销售下单', roles: ['Admin', 'Boss', 'Sales'], component: () => import('../views/SalesOrder.vue') },
  { path: '/order-allocation', name: 'OrderAllocation', label: '📦 订单配货', title: '订单配货', roles: ['Admin', 'Boss', 'Sales', 'Prod'], component: () => import('../views/OrderAllocation.vue') },
  { path: '/shipping-review', name: 'ShippingReview', label: '📗 发货复核', title: '发货复核', roles: ['Admin', 'Boss', 'Prod'], component: () => import('../views/ShippingReview.vue') },
  { path: '/machine-archive', name: 'MachineArchive', label: '🔧 机台档案', title: '机台档案', roles: ['Admin', 'Boss', 'Prod'], component: () => import('../views/MachineArchive.vue') },
  { path: '/machine-edit', name: 'MachineEdit', label: '🛠️ 机台编辑', title: '机台编辑', roles: ['Admin', 'Boss', 'Prod'], component: () => import('../views/MachineEdit.vue') },
  { path: '/warehouse-dashboard', name: 'WarehouseDashboard', label: '🖥️ 库位大屏', title: '库位大屏', roles: ['Admin', 'Boss', 'Prod', 'Inbound', 'Sales'], component: () => import('../views/WarehouseDashboard.vue') },
  { path: '/logs', name: 'Logs', label: '📜 交易日志', title: '交易日志', roles: ['Admin', 'Boss', 'Sales'], component: () => import('../views/LogViewer.vue') },
  { path: '/inventory', name: 'Inventory', label: '🔎 库存查询', title: '库存查询', roles: ['Admin', 'Boss', 'Sales', 'Prod', 'Inbound'], component: () => import('../views/InventoryQuery.vue') },
  { path: '/inbound', name: 'Inbound', label: '📦 成品入库', title: '成品入库', roles: ['Admin', 'Prod', 'Inbound'], component: () => import('../views/Inbound.vue') },
]

export const appMenus: AppMenuItem[] = appRouteDefs.map((r) => ({
  path: r.path,
  label: r.label,
  roles: r.roles,
  isManagement: r.isManagement,
}))

const appChildRoutes: RouteRecordRaw[] = appRouteDefs.map((r) => ({
  path: r.path.slice(1),
  name: r.name,
  component: r.component,
  meta: { title: r.title, roles: r.roles, requiresAuth: true },
}))

const dynamicRouteNames = new Set<string>()
let injectedRole = ''

const resetDynamicRoutes = () => {
  for (const name of dynamicRouteNames) {
    if (router.hasRoute(name)) router.removeRoute(name)
  }
  dynamicRouteNames.clear()
  injectedRole = ''
}

const ensureDynamicRoutes = (role?: string | null) => {
  const nextRole = normalizeRole(role)
  if (!nextRole) {
    resetDynamicRoutes()
    return
  }
  if (injectedRole === nextRole && dynamicRouteNames.size > 0) return

  resetDynamicRoutes()
  for (const route of appChildRoutes) {
    const roles = route.meta?.roles as string[] | undefined
    if (roles && roles.length > 0 && !roleIn(nextRole, roles)) continue
    router.addRoute('Layout', route)
    dynamicRouteNames.add(String(route.name))
  }
  injectedRole = nextRole
}

export const getAccessibleMenus = (role?: string | null) => {
  const nextRole = normalizeRole(role)
  if (!nextRole) return [] as AppMenuItem[]
  return appMenus.filter((m) => !m.roles || roleIn(nextRole, m.roles))
}

export const canAccessPath = (path: string, role?: string | null) => {
  const cleanPath = String(path || '').split('?')[0].split('#')[0]
  const menu = appMenus.find((m) => m.path === cleanPath)
  if (!menu) return true
  if (!menu.roles || menu.roles.length === 0) return true
  return roleIn(role, menu.roles)
}

const isKnownAppPath = (path: string) => {
  const cleanPath = String(path || '').split('?')[0].split('#')[0]
  return appMenus.some((m) => m.path === cleanPath)
}

const routes: Array<RouteRecordRaw> = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/Login.vue'),
    meta: { title: '登录' }
  },
  {
    path: '/403',
    name: 'Forbidden',
    component: () => import('../views/Forbidden.vue'),
    meta: { requiresAuth: true, title: '无权限访问' }
  },
  {
    path: '/',
    name: 'Layout',
    component: () => import('../components/Layout.vue'),
    meta: { requiresAuth: true },
    children: [
      {
        path: '',
        name: 'Home',
        component: () => import('../views/Home.vue'),
        meta: { title: '首页' }
      },
    ]
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

// Navigation guard
router.beforeEach((to, _from, next) => {
  const userStore = useUserStore()

  if (!userStore.isAuthenticated) {
    resetDynamicRoutes()
  } else {
    ensureDynamicRoutes(userStore.userInfo?.role)
  }

  if (to.meta.requiresAuth && !userStore.isAuthenticated) {
    next({ name: 'Login', query: { redirect: to.fullPath } })
    return
  }
  if (to.name === 'Login' && userStore.isAuthenticated) {
    const redirect = typeof to.query.redirect === 'string' ? to.query.redirect : '/'
    next(redirect)
    return
  }

  if (to.matched.length === 0) {
    if (!userStore.isAuthenticated) {
      next({ name: 'Login', query: { redirect: to.fullPath } })
      return
    }
    if (!isKnownAppPath(to.path)) {
      next({ name: 'Home' })
      return
    }
    if (!canAccessPath(to.path, userStore.userInfo?.role)) {
      ElMessage.error('没有操作权限')
      next({ name: 'Forbidden' })
      return
    }
    next({ path: to.fullPath, replace: true })
    return
  }

  const roles = to.meta.roles as string[] | undefined
  if (roles && roles.length > 0 && !userStore.hasRole(roles)) {
    ElMessage.error('没有操作权限')
    next({ name: 'Forbidden' })
    return
  }
  if (!canAccessPath(to.path, userStore.userInfo?.role)) {
    ElMessage.error('没有操作权限')
    next({ name: 'Forbidden' })
    return
  }
  next()
})

router.afterEach((to) => {
  const title = typeof to.meta.title === 'string' ? to.meta.title : '管理系统'
  document.title = `${title} - V7ex`
})

export default router
