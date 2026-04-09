<template>
  <div class="layout">
    <button v-if="isMobile" type="button" class="mobile-menu-btn" @click="toggleMobileMenu">☰ 菜单</button>
    <div v-if="isMobile && mobileMenuOpen" class="mobile-mask" @click="closeMobileMenu" />
    <aside class="sidebar" :class="{ collapsed: sidebarCollapsed, mobile: isMobile, 'mobile-open': mobileMenuOpen }">
      <button type="button" class="collapse-tip" @click="toggleSidebar">
        {{ sidebarCollapsed ? '»' : '«' }}
      </button>
      <div v-if="!sidebarCollapsed" class="logo">🏭 管理系统 V7.0</div>

      <div v-if="!sidebarCollapsed" class="menu-group">
        <div class="group-title">👤 系统管理</div>
        <router-link class="menu-item active-home" to="/">🏠 首页</router-link>
      </div>

      <div class="user-info" v-if="userStore.userInfo && !sidebarCollapsed">
        <p class="user-name">角色: {{ roleLabel }}</p>
        <p class="user-role">用户: {{ userStore.userInfo.name }}</p>
        <button @click="handleLogout">🚪 退出登录</button>
      </div>

      <div v-if="!sidebarCollapsed" class="menu-group">
        <div class="group-title">👑 管理功能</div>
        <button
          v-for="item in visibleMenus"
          :key="item.path"
          type="button"
          class="menu-btn"
          :class="{ active: isActive(item.path) }"
          @mouseenter="preloadRoute(item.path)"
          @click="go(item.path)"
        >
          {{ item.label }}
        </button>
      </div>
    </aside>
    <main class="main-content" :class="{ expanded: sidebarCollapsed }">
      <router-view />
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '../store/user'
import { getAccessibleMenus } from '../router'
import { cancelIdleRun, runWhenIdle } from '../utils/compat'
import { normalizeRole } from '../utils/roles'

const userStore = useUserStore()
const router = useRouter()
const sidebarCollapsed = ref(false)
const isMobile = ref(false)
const mobileMenuOpen = ref(false)
let warmupHandle: number | null = null

const visibleMenus = computed(() => {
  const onHome = router.currentRoute.value.path === '/'
  return getAccessibleMenus(userStore.userInfo?.role).filter((m) => {
    if (onHome) return Boolean(m.isManagement) || ['/warehouse-dashboard', '/logs'].includes(m.path)
    return true
  })
})
const roleLabel = computed(() => userStore.userInfo?.role || '-')
const warmedPaths = new Set<string>()

const preloadRoute = (path: string) => {
  if (!path || warmedPaths.has(path)) return
  const resolved = router.resolve(path)
  for (const record of resolved.matched) {
    const component = record.components?.default
    if (typeof component === 'function') {
      void (component as () => Promise<unknown>)()
    }
  }
  warmedPaths.add(path)
}

const warmupByRole = () => {
  const role = normalizeRole(userStore.userInfo?.role || '')
  const common = ['/inventory', '/warehouse-dashboard']
  const byRole: Record<string, string[]> = {
    Admin: ['/users', '/logs', '/planning', '/contracts'],
    Boss: ['/planning', '/contracts', '/sales-orders', '/order-allocation'],
    Sales: ['/sales-orders', '/order-allocation', '/contracts'],
    Prod: ['/inbound', '/machine-archive', '/machine-edit', '/shipping-review'],
    Inbound: ['/inbound', '/warehouse-dashboard', '/inventory'],
  }
  const targets = [...common, ...(byRole[role] || [])]
  for (const p of targets) preloadRoute(p)
}

const toggleSidebar = () => {
  sidebarCollapsed.value = !sidebarCollapsed.value
}
const syncViewport = () => {
  const mobile = window.innerWidth < 992
  isMobile.value = mobile
  if (!mobile) mobileMenuOpen.value = false
  if (mobile) sidebarCollapsed.value = false
}
const toggleMobileMenu = () => {
  mobileMenuOpen.value = !mobileMenuOpen.value
}
const closeMobileMenu = () => {
  mobileMenuOpen.value = false
}

const go = (path: string) => {
  router.push(path)
  if (isMobile.value) closeMobileMenu()
}

const isActive = (path: string) => router.currentRoute.value.path === path

const handleLogout = () => {
  userStore.logout()
  router.push('/login')
}

onMounted(() => {
  syncViewport()
  window.addEventListener('resize', syncViewport)
  warmupHandle = runWhenIdle(() => warmupByRole(), 400)
})
onBeforeUnmount(() => {
  cancelIdleRun(warmupHandle)
  warmupHandle = null
  window.removeEventListener('resize', syncViewport)
})
watch(() => router.currentRoute.value.path, () => {
  if (isMobile.value) closeMobileMenu()
})
</script>

<style scoped>
.layout {
  display: flex;
  min-height: 100vh;
  position: relative;
}
.sidebar {
  width: 220px;
  background: var(--panel-bg);
  border-right: 1px solid #e5e7eb;
  color: var(--text-color);
  display: flex;
  flex-direction: column;
  padding: 10px 8px;
  gap: 12px;
  transition: width 0.2s ease, padding 0.2s ease;
}
.sidebar.collapsed {
  width: 28px;
  padding: 10px 2px;
}
.collapse-tip {
  width: 100%;
  text-align: center;
  color: #9ca3af;
  font-size: 16px;
  border: none;
  background: transparent;
  cursor: pointer;
  padding: 0;
}
.logo {
  padding: 8px 6px;
  font-size: 22px;
  font-weight: bold;
  color: #1f2937;
}
.menu-group {
  border-top: 1px solid #e5e7eb;
  padding-top: 10px;
}
.group-title {
  color: #6b7280;
  font-size: 12px;
  margin-bottom: 8px;
  font-weight: 700;
}
.menu-item {
  display: block;
  text-decoration: none;
  border: 1px solid #d1fae5;
  background: #ecfdf5;
  color: #047857;
  padding: 8px 10px;
  border-radius: 8px;
  font-size: 13px;
}
.menu-btn {
  width: 100%;
  text-align: left;
  padding: 8px 10px;
  border: 1px solid #e5e7eb;
  background: #ffffff;
  border-radius: 8px;
  color: #374151;
  font-size: 13px;
  margin-bottom: 8px;
  cursor: pointer;
}
.menu-btn:hover {
  border-color: #93c5fd;
}
.menu-btn.active {
  border-color: #60a5fa;
  background: #eff6ff;
  color: #1d4ed8;
}
.user-info {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 8px;
  background: #fff;
}
.user-info button {
  margin-top: 8px;
  width: 100%;
  padding: 6px 10px;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  background: #fff;
  cursor: pointer;
  font-size: 12px;
}
.user-name,
.user-role {
  margin: 2px 0;
  font-size: 12px;
  color: #6b7280;
}
.main-content {
  flex-grow: 1;
  padding: 18px 20px;
  background-color: var(--panel-bg);
  overflow-y: auto;
  transition: padding 0.2s ease;
}
.main-content.expanded {
  padding-left: 14px;
}
.mobile-menu-btn {
  position: fixed;
  top: 10px;
  left: 10px;
  z-index: 1201;
  border: 1px solid #d1d5db;
  background: #fff;
  border-radius: 8px;
  padding: 6px 10px;
  font-size: 13px;
  cursor: pointer;
}
.mobile-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.4);
  z-index: 1198;
}
@media (max-width: 991px) {
  .sidebar.mobile {
    position: fixed;
    top: 0;
    left: 0;
    height: 100vh;
    z-index: 1200;
    transform: translateX(-100%);
    width: 240px;
    transition: transform 0.2s ease;
    box-shadow: 6px 0 24px rgba(0, 0, 0, 0.16);
  }
  .sidebar.mobile.mobile-open {
    transform: translateX(0);
  }
  .main-content {
    width: 100%;
    padding: 54px 10px 10px;
  }
  .main-content.expanded {
    padding-left: 10px;
  }
}
</style>
