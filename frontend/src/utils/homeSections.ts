/**
 * 首页「业务性质分栏」的公共定义与分组逻辑。
 *
 * 目标：首页不再手工维护固定按钮，而是把当前账号可访问的全部业务模块
 * 按业务性质分栏展示，新增模块只要在路由里声明 section 就会自动出现在首页，
 * 不会再出现「侧边栏有、首页没有」的隐藏入口。
 *
 * 该文件不依赖 vue-router / pinia，便于单独做单元测试。
 */

export type AppSectionKey =
  | 'management'
  | 'order'
  | 'production'
  | 'inventory'
  | 'delivery'
  | 'workflow'
  | 'system'

export type AppSectionMeta = {
  key: AppSectionKey
  title: string
  icon: string
}

/** 分栏的展示顺序（同时决定首页分区先后）。 */
export const appSectionOrder: AppSectionKey[] = [
  'management',
  'order',
  'production',
  'inventory',
  'delivery',
  'workflow',
  'system',
]

/** 每个分栏的标题与图标。 */
export const appSectionMeta: Record<AppSectionKey, { title: string; icon: string }> = {
  management: { title: '管理与统筹', icon: '👑' },
  order: { title: '订单与合同', icon: '📋' },
  production: { title: '生产与设备档案', icon: '🏭' },
  inventory: { title: '库存与仓储', icon: '📦' },
  delivery: { title: '发货与交付', icon: '🚚' },
  workflow: { title: '流程与审批', icon: '🔄' },
  system: { title: '系统与基础数据', icon: '⚙️' },
}

/**
 * 分栏内卡片的展示顺序。
 * 未列入的模块会排在所属分栏末尾，保证后续新增模块不会因为漏配顺序而被隐藏。
 */
export const appSectionPathOrder: Record<AppSectionKey, string[]> = {
  management: ['/prediction-sandbox', '/production-kanban', '/traceability', '/reports'],
  order: ['/dealer-orders', '/sales-orders', '/order-allocation', '/contracts'],
  production: ['/inbound', '/machine-archive', '/machine-edit'],
  inventory: ['/inventory', '/warehouse-dashboard'],
  delivery: ['/shipping-review', '/customer-finished-goods'],
  workflow: ['/approval-center', '/workflow/tasks', '/workflow/instances', '/workflow/models'],
  system: ['/users', '/model-dictionary', '/logs'],
}

const OTHER_SECTION = { key: 'other', title: '其他功能', icon: '🧰' } as const

/** 首页菜单来源（与 router 中 AppMenuItem 结构兼容）。 */
export type HomeMenuSource = {
  path: string
  label: string
  section?: string
  isManagement?: boolean
}

export type HomeMenuItem = {
  path: string
  label: string
  icon: string
  text: string
  isManagement: boolean
}

export type HomeMenuSection = {
  key: string
  title: string
  icon: string
  items: HomeMenuItem[]
}

/** 菜单 label 形如 "📊 合同管理"，拆成图标与文字。 */
export const splitMenuLabel = (label: string): { icon: string; text: string } => {
  const trimmed = String(label || '').trim()
  const parts = trimmed.split(/\s+/)
  if (parts.length > 1) return { icon: parts[0], text: parts.slice(1).join(' ') }
  return { icon: '•', text: trimmed }
}

const isSectionKey = (value: string | undefined): value is AppSectionKey =>
  Boolean(value) && appSectionOrder.includes(value as AppSectionKey)

/**
 * 把「当前账号可访问的菜单」按业务性质分组。
 * - 只返回非空分栏，并按 appSectionOrder 排序；
 * - section 未配置/配置错误的菜单归入末尾「其他功能」，确保不被吞掉；
 * - 分栏内按 appSectionPathOrder 排序，未列出的模块保留原有顺序排在最后。
 */
export const groupMenusBySection = (menus: HomeMenuSource[]): HomeMenuSection[] => {
  const buckets = new Map<string, HomeMenuItem[]>()
  for (const key of appSectionOrder) buckets.set(key, [])

  for (const menu of menus) {
    const { icon, text } = splitMenuLabel(menu.label)
    const item: HomeMenuItem = {
      path: menu.path,
      label: menu.label,
      icon,
      text,
      isManagement: Boolean(menu.isManagement),
    }
    const key = isSectionKey(menu.section) ? menu.section : OTHER_SECTION.key
    const bucket = buckets.get(key)
    if (bucket) {
      bucket.push(item)
    } else {
      buckets.set(key, [item])
    }
  }

  const sections: HomeMenuSection[] = []
  for (const key of appSectionOrder) {
    const items = buckets.get(key) || []
    if (!items.length) continue
    const pathOrder = appSectionPathOrder[key]
    const rank = (path: string) => {
      const index = pathOrder.indexOf(path)
      return index === -1 ? Number.MAX_SAFE_INTEGER : index
    }
    items.sort((a, b) => rank(a.path) - rank(b.path))
    sections.push({
      key,
      title: appSectionMeta[key].title,
      icon: appSectionMeta[key].icon,
      items,
    })
  }

  const others = buckets.get(OTHER_SECTION.key) || []
  if (others.length) {
    sections.push({ ...OTHER_SECTION, items: others })
  }
  return sections
}
