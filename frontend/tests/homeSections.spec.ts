import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import Home from '../src/views/Home.vue'
import { appMenus } from '../src/router'
import {
  appSectionOrder,
  groupMenusBySection,
  splitMenuLabel,
} from '../src/utils/homeSections'
import { useUserStore } from '../src/store/user'

/** 管理员常见权限集合：用于渲染「全部可访问模块」的首页。 */
const ALL_PERMISSIONS = [
  'CONTRACT',
  'MODEL_DICTIONARY',
  'USER_MANAGE',
  'DEALER_ORDER_REVIEW',
  'SALES_CREATE',
  'SALES_ALLOC',
  'SHIP_CONFIRM',
  'ARCHIVE',
  'MACHINE_EDIT',
  'QUERY',
  'WAREHOUSE_MAP',
  'LOG_VIEW',
  'INBOUND',
  'TRACEABILITY',
  'KANBAN_VIEW',
  'SANDBOX_VIEW',
  'REPORT_VIEW',
]

const SECTION_TITLES = [
  '管理与统筹',
  '订单与合同',
  '生产与设备档案',
  '库存与仓储',
  '发货与交付',
  '流程与审批',
  '系统与基础数据',
]

const createTestContext = async (permissions: string[], role = 'Admin') => {
  const pinia = createPinia()
  setActivePinia(pinia)
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: { template: '<div />' } }],
  })
  await router.push('/')
  await router.isReady()
  const userStore = useUserStore()
  userStore.userInfo = { username: 'tester', name: '测试用户', role, permissions }
  userStore.token = 'test-token'
  return { pinia, router }
}

describe('homeSections 分组工具', () => {
  it('把 "📊 合同管理" 拆成图标与文字', () => {
    expect(splitMenuLabel('📊 合同管理')).toEqual({ icon: '📊', text: '合同管理' })
    expect(splitMenuLabel('无图标菜单')).toEqual({ icon: '•', text: '无图标菜单' })
  })

  it('全部可见菜单都出现在分栏中且仅出现一次', () => {
    const sections = groupMenusBySection(appMenus)
    const paths = sections.flatMap((section) => section.items.map((item) => item.path))
    expect(paths).toHaveLength(appMenus.length)
    expect(new Set(paths).size).toBe(appMenus.length)
    expect([...paths].sort()).toEqual(appMenus.map((menu) => menu.path).sort())
  })

  it('分栏按业务顺序排列，未配置分栏的模块进入「其他功能」而不是被丢弃', () => {
    const sections = groupMenusBySection([
      { path: '/unknown-module', label: '🧪 未知模块', section: 'not-exist' },
      ...appMenus,
    ])
    expect(sections.map((section) => section.key)).toEqual([...appSectionOrder, 'other'])
    const other = sections[sections.length - 1]
    expect(other.title).toBe('其他功能')
    expect(other.items.map((item) => item.path)).toContain('/unknown-module')
  })

  it('分栏内卡片按业务优先顺序排列，未列出的模块排在末尾', () => {
    const sections = groupMenusBySection(appMenus)
    const management = sections.find((section) => section.key === 'management')
    expect(management?.items.map((item) => item.path)).toEqual([
      '/prediction-sandbox',
      '/production-kanban',
      '/traceability',
      '/reports',
    ])
  })
})

describe('首页按业务性质分栏渲染', () => {
  it('管理员首页展示全部业务分栏与模块入口（含新增的客户成品/审批中心）', async () => {
    const { pinia, router } = await createTestContext(ALL_PERMISSIONS)
    const wrapper = mount(Home, { global: { plugins: [pinia, router] } })

    const panels = wrapper.findAll('.section-panel')
    expect(panels).toHaveLength(SECTION_TITLES.length)
    expect(panels.map((panel) => panel.find('.section-name').text())).toEqual(SECTION_TITLES)

    const buttons = wrapper.findAll('.module-btn')
    expect(buttons).toHaveLength(appMenus.length)

    expect(wrapper.find('[data-path="/customer-finished-goods"]').exists()).toBe(true)
    expect(wrapper.find('[data-path="/approval-center"]').exists()).toBe(true)
    expect(wrapper.find('[data-path="/prediction-sandbox"]').exists()).toBe(true)
  })

  it('点击首页模块跳转到对应路由', async () => {
    const { pinia, router } = await createTestContext(ALL_PERMISSIONS)
    const wrapper = mount(Home, { global: { plugins: [pinia, router] } })
    const push = vi.spyOn(router, 'push').mockResolvedValue(undefined)

    await wrapper.find('[data-path="/customer-finished-goods"]').trigger('click')
    expect(push).toHaveBeenCalledWith('/customer-finished-goods')
  })

  it('权限不足的模块不会出现在首页分栏中', async () => {
    const { pinia, router } = await createTestContext(
      ['SALES_CREATE', 'SALES_ALLOC', 'CONTRACT', 'ARCHIVE', 'QUERY'],
      'Sales',
    )
    const wrapper = mount(Home, { global: { plugins: [pinia, router] } })

    expect(wrapper.find('[data-path="/users"]').exists()).toBe(false)
    expect(wrapper.find('[data-path="/logs"]').exists()).toBe(false)
    expect(wrapper.find('[data-path="/prediction-sandbox"]').exists()).toBe(false)
    expect(wrapper.find('[data-path="/sales-orders"]').exists()).toBe(true)
  })
})
