<template>
  <div class="home-page">
    <h1 class="page-title">🏭 成品整机管理系统 V8betaVer1.0</h1>
    <p class="subtitle">当前用户：{{ userName }} | 角色：{{ userRole }}</p>

    <div v-if="sections.length" class="section-columns">
      <section
        v-for="section in sections"
        :key="section.key"
        class="section-panel"
        :class="`section-${section.key}`"
        :data-section="section.key"
      >
        <h2 class="section-title">
          <span class="section-icon">{{ section.icon }}</span>
          <span class="section-name">{{ section.title }}</span>
          <span class="section-count">{{ section.items.length }}</span>
        </h2>
        <div class="module-grid">
          <button
            v-for="item in section.items"
            :key="item.path"
            type="button"
            class="btn-base module-btn"
            :class="{ 'boss-plan-card': item.path === '/prediction-sandbox' }"
            :data-path="item.path"
            @click="go(item.path)"
          >
            <span class="icon">{{ item.icon }}</span>
            <span class="label">{{ item.text }}</span>
          </button>
        </div>
      </section>
    </div>
    <p v-else class="empty-tip">当前账号暂无可访问的业务模块，请联系管理员分配权限。</p>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '../store/user'
import { getAccessibleMenus } from '../router'
import { groupMenusBySection } from '../utils/homeSections'

const router = useRouter()
const userStore = useUserStore()

const userName = computed(() => userStore.userInfo?.name || '-')
const userRole = computed(() => userStore.userInfo?.role || '-')

/** 首页不再硬编码按钮：按当前账号可访问的菜单 + 业务分栏自动生成。 */
const sections = computed(() =>
  groupMenusBySection(getAccessibleMenus(userStore.userInfo?.permissions, userStore.userInfo?.role)),
)

const go = (path: string) => {
  router.push(path)
}
</script>

<style scoped>
.home-page {
  padding: 32px 40px;
  max-width: 1600px;
  margin: 0 auto;
  container-type: inline-size;
  container-name: home;
  min-height: calc(100vh - 44px);
}
.page-title {
  margin: 0;
  font-size: max(24px, 3.2vw);
  font-weight: 700;
  color: var(--color-gray-900);
  letter-spacing: -0.01em;
}
.subtitle {
  margin: 4px 0 20px;
  color: var(--color-gray-500);
  font-size: 12px;
}

/* 业务分栏：各业务板块作为独立卡片，宽屏多栏、窄屏单栏 */
.section-columns {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
  gap: 20px;
  align-items: start;
}
.section-panel {
  border: 1px solid rgba(15, 23, 42, 0.06);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.78);
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.03);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  padding: 18px 18px 20px;
}
.section-workflow {
  background: linear-gradient(135deg, rgba(239, 246, 255, 0.9), rgba(255, 255, 255, 0.85));
}
.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 14px;
  padding-bottom: 10px;
  border-bottom: 1px solid rgba(15, 23, 42, 0.06);
  font-size: 15px;
  font-weight: 700;
  color: var(--color-gray-900);
}
.section-icon {
  font-size: 18px;
  line-height: 1;
}
.section-name {
  flex: 1;
}
.section-count {
  min-width: 22px;
  padding: 1px 8px;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.06);
  color: var(--color-gray-500);
  font-size: 12px;
  font-weight: 600;
  text-align: center;
}
.module-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(132px, 1fr));
  gap: 12px;
}

.icon {
  margin-bottom: 8px;
  font-size: 26px;
  line-height: 1;
  opacity: 0.9;
  display: block;
  transition: transform 0.3s ease;
}

/* Base Button Styles based on 8pt system and ratios */
.btn-base {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  border: 1px solid rgba(0, 0, 0, 0.04);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.9);
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.03);
  color: var(--color-gray-800);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.25, 0.1, 0.25, 1);
  padding: 14px 10px;
  width: 100%;
}
.module-btn {
  min-height: 92px;
}
.module-btn .label {
  line-height: 1.35;
}
.boss-plan-card {
  background: linear-gradient(135deg, #fff7d6, #ffffff);
  border-color: rgba(218, 165, 32, 0.28);
}
.empty-tip {
  margin: 12px 0;
  color: var(--color-gray-500);
  font-size: 14px;
}

.btn-base:hover {
  transform: translateY(-4px);
  box-shadow: 0 12px 30px rgba(0, 0, 0, 0.08);
  border-color: rgba(0, 0, 0, 0.08);
  background: rgba(255, 255, 255, 1);
}
.btn-base:hover .icon {
  transform: scale(1.1);
}
.btn-base:active {
  transform: scale(0.97);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
}
.btn-base:focus-visible {
  outline: none;
  box-shadow: var(--shadow-focus);
}

/* Responsive Overrides using Container Queries */
@container home (max-width: 900px) {
  .home-page {
    padding: 20px;
  }
  .section-columns {
    grid-template-columns: 1fr;
  }
}
@container home (max-width: 768px) {
  .home-page {
    padding: 16px;
  }
  .section-panel {
    padding: 14px;
  }
  .module-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
  }
  .module-btn {
    min-height: 84px;
  }
}
@container home (max-width: 480px) {
  .module-grid {
    grid-template-columns: 1fr; /* 小屏单列，避免文字挤压 */
  }
}
</style>
