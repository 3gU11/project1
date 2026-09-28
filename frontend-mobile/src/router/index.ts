import { createRouter, createWebHistory } from 'vue-router'
import { useUserStore } from '../store/user'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/Login.vue'),
    meta: { requiresAuth: false }
  },
  {
    path: '/',
    component: () => import('../components/layout/Layout.vue'),
    meta: { requiresAuth: true },
    children: [
      {
        path: 'query',
        name: 'Query',
        component: () => import('../views/InventoryQuery.vue'),
        meta: { roles: ['Inbound', 'Prod', 'AfterSales'] }
      },
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('../views/Dashboard.vue'),
        meta: { roles: ['Inbound'] }
      },
      {
        path: 'locator',
        name: 'InventoryLocator',
        component: () => import('../views/InventoryLocator.vue'),
        meta: { roles: ['Inbound', 'Prod'] }
      },
      {
        path: 'production',
        name: 'MobileProduction',
        component: () => import('../views/ProductionKanban.vue'),
        meta: { roles: ['LineOperator'], permissions: ['MOBILE_KANBAN_VIEW'] }
      },
      {
        path: 'profile',
        name: 'Profile',
        component: () => import('../views/Profile.vue'),
        meta: { roles: ['Inbound', 'Prod', 'AfterSales', 'LineOperator'] }
      }
    ]
  },
  {
    path: '/machine-edit/:id',
    name: 'MachineEdit',
    component: () => import('../views/MachineEdit.vue'),
    meta: { requiresAuth: true, roles: ['Inbound', 'Prod', 'AfterSales'] }
  },
  {
    path: '/photo-tasks/:id',
    name: 'PhotoTasks',
    component: () => import('../views/MachineEdit.vue'),
    meta: { requiresAuth: true, roles: ['Inbound', 'Prod', 'AfterSales'] }
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/login'
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

const defaultPath = () => {
  const userStore = useUserStore()
  if (userStore.userInfo?.role === 'LineOperator' || userStore.hasPermission('MOBILE_KANBAN_VIEW')) {
    return '/production'
  }
  return '/query'
}

router.beforeEach(async (to) => {
  const userStore = useUserStore()
  // The API interceptor can clear storage before a full page reload finishes.
  // Do not let a stale Pinia token send the user back into protected pages.
  const isAuth = !!userStore.token

  if (isAuth && to.path !== '/login') {
    // Reconcile the role on every protected navigation. The layout remains
    // mounted while switching the bottom tabs, so a one-time startup refresh
    // is insufficient and can restore a stale role from persisted state.
    // Refresh at most once per short interval and share concurrent requests.
    // A transient network error should not block navigation with valid cached auth.
    await userStore.refreshUser()
  }

  if (to.meta.requiresAuth && !isAuth) {
    return '/login'
  } else if (to.path === '/login' && isAuth) {
    return defaultPath()
  } else if (to.path === '/' && isAuth) {
    return defaultPath()
  } else {
    // Role based guard
    if (to.meta.roles && userStore.userInfo) {
      const allowedRoles = to.meta.roles as string[]
      const allowedPermissions = (to.meta.permissions || []) as string[]
      const roleAllowed = allowedRoles.includes(userStore.userInfo.role)
      const permissionAllowed = allowedPermissions.length > 0 && userStore.hasAnyPermission(allowedPermissions)
      if (!roleAllowed && !permissionAllowed) {
        const target = defaultPath()
        return to.path === target ? false : target
      }
    }
    return true
  }
})

export default router
