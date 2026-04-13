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
        meta: { roles: ['Inbound', 'Prod'] }
      },
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('../views/Dashboard.vue'),
        meta: { roles: ['Inbound'] }
      },
      {
        path: 'profile',
        name: 'Profile',
        component: () => import('../views/Profile.vue'),
        meta: { roles: ['Inbound', 'Prod'] }
      }
    ]
  },
  {
    path: '/machine-edit/:id',
    name: 'MachineEdit',
    component: () => import('../views/MachineEdit.vue'),
    meta: { requiresAuth: true, roles: ['Inbound', 'Prod'] }
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

router.beforeEach((to, _from, next) => {
  const userStore = useUserStore()
  const isAuth = !!userStore.token

  if (to.meta.requiresAuth && !isAuth) {
    next('/login')
  } else if (to.path === '/login' && isAuth) {
    next('/query')
  } else if (to.path === '/' && isAuth) {
    next('/query')
  } else {
    // Role based guard
    if (to.meta.roles && userStore.userInfo) {
      const allowedRoles = to.meta.roles as string[]
      if (!allowedRoles.includes(userStore.userInfo.role)) {
        next('/query')
        return
      }
    }
    next()
  }
})

export default router
