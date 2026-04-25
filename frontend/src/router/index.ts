import { createRouter, createWebHistory, RouteRecordRaw } from 'vue-router'
import { useUserStore } from '../store/user'
import { ElMessage } from 'element-plus'

export type AppMenuItem = {
  path: string
  label: string
  permission?: string
  isManagement?: boolean
}

type AppRouteDef = {
  path: string
  name: string
  label: string
  title: string
  permission?: string
  isManagement?: boolean
  component: () => Promise<unknown>
}

const appRouteDefs: AppRouteDef[] = [
  { path: '/planning', name: 'Planning', label: '👑 生产统筹/订单规划', title: '生产统筹', permission: 'PLANNING', isManagement: true, component: () => import('../views/BossPlanning.vue') },
  { path: '/contracts', name: 'Contracts', label: '📊 合同管理', title: '合同管理', permission: 'CONTRACT', isManagement: true, component: () => import('../views/ContractManage.vue') },
  { path: '/model-dictionary', name: 'ModelDictionary', label: '📚 机型字典', title: '机型字典', permission: 'MODEL_DICTIONARY', isManagement: true, component: () => import('../views/ModelDictionary.vue') },
  { path: '/users', name: 'Users', label: '👤 用户管理', title: '用户管理', permission: 'USER_MANAGE', isManagement: true, component: () => import('../views/UserManagement.vue') },
  { path: '/sales-orders', name: 'SalesOrders', label: '📌 销售下单', title: '销售下单', permission: 'SALES_CREATE', component: () => import('../views/SalesOrder.vue') },
  { path: '/order-allocation', name: 'OrderAllocation', label: '📋 订单配货', title: '订单配货', permission: 'SALES_ALLOC', component: () => import('../views/OrderAllocation.vue') },
  { path: '/shipping-review', name: 'ShippingReview', label: '📗 发货复核', title: '发货复核', permission: 'SHIP_CONFIRM', component: () => import('../views/ShippingReview.vue') },
  { path: '/machine-archive', name: 'MachineArchive', label: '🔧 机台档案', title: '机台档案', permission: 'ARCHIVE', component: () => import('../views/MachineArchive.vue') },
  { path: '/machine-edit', name: 'MachineEdit', label: '🛠️ 机台编辑', title: '机台编辑', permission: 'MACHINE_EDIT', component: () => import('../views/MachineEdit.vue') },
  { path: '/warehouse-dashboard', name: 'WarehouseDashboard', label: '🖥️ 库位大屏', title: '库位大屏', permission: 'WAREHOUSE_MAP', component: () => import('../views/WarehouseDashboard.vue') },
  { path: '/logs', name: 'Logs', label: '📜 交易日志', title: '交易日志', permission: 'LOG_VIEW', component: () => import('../views/LogViewer.vue') },
  { path: '/inventory', name: 'Inventory', label: '🔎 库存查询', title: '库存查询', permission: 'QUERY', component: () => import('../views/InventoryQuery.vue') },
  { path: '/inbound', name: 'Inbound', label: '⬇️ 成品入库', title: '成品入库', permission: 'INBOUND', component: () => import('../views/Inbound.vue') },
  { path: '/traceability', name: 'Traceability', label: '🔍 汇总与追溯', title: '汇总与追溯', permission: 'TRACEABILITY', isManagement: true, component: () => import('../views/Traceability.vue') },
]

export const appMenus: AppMenuItem[] = appRouteDefs.map((r) => ({
  path: r.path,
  label: r.label,
  permission: r.permission,
  isManagement: r.isManagement,
}))

const appChildRoutes: RouteRecordRaw[] = appRouteDefs.map((r) => ({
  path: r.path.slice(1),
  name: r.name,
  component: r.component,
  meta: { title: r.title, permission: r.permission, requiresAuth: true },
}))

const dynamicRouteNames = new Set<string>()
let injectedPermissionKey = ''

const resetDynamicRoutes = () => {
  for (const name of dynamicRouteNames) {
    if (router.hasRoute(name)) router.removeRoute(name)
  }
  dynamicRouteNames.clear()
  injectedPermissionKey = ''
}

const ensureDynamicRoutes = (permissions?: string[] | null) => {
  const permissionKey = (permissions || []).map((p) => String(p).trim()).filter(Boolean).sort().join('|')
  if (!permissionKey) {
    resetDynamicRoutes()
    return
  }
  if (injectedPermissionKey === permissionKey && dynamicRouteNames.size > 0) return

  const userStore = useUserStore()
  resetDynamicRoutes()
  for (const route of appChildRoutes) {
    const permission = route.meta?.permission as string | undefined
    if (permission && !userStore.hasPermission(permission)) continue
    router.addRoute('Layout', route)
    dynamicRouteNames.add(String(route.name))
  }
  injectedPermissionKey = permissionKey
}

export const getAccessibleMenus = (permissions?: string[] | null) => {
  const permissionSet = new Set((permissions || []).map((p) => String(p).trim()).filter(Boolean))
  return appMenus.filter((m) => !m.permission || permissionSet.has(m.permission))
}

export const canAccessPath = (path: string, permissions?: string[] | null) => {
  const cleanPath = String(path || '').split('?')[0].split('#')[0]
  const menu = appMenus.find((m) => m.path === cleanPath)
  if (!menu) return true
  if (!menu.permission) return true
  const permissionList = Array.isArray(permissions) ? permissions : []
  return permissionList.map((p) => String(p).trim()).includes(menu.permission)
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
    ensureDynamicRoutes(userStore.userInfo?.permissions)
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
    if (!canAccessPath(to.path, userStore.userInfo?.permissions)) {
      ElMessage.error('没有操作权限')
      next({ name: 'Forbidden' })
      return
    }
    next({ path: to.fullPath, replace: true })
    return
  }

  const permission = to.meta.permission as string | undefined
  if (permission && !userStore.hasPermission(permission)) {
    ElMessage.error('没有操作权限')
    next({ name: 'Forbidden' })
    return
  }
  if (!canAccessPath(to.path, userStore.userInfo?.permissions)) {
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
