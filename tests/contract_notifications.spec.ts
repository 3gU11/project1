import { test, expect } from '@playwright/test'

const message = {
  contract_id: 'HT-TEST-001',
  created_snapshot: { customer: '测试客户', dealer: '测试代理', due_date: '2026-10-01', models: [{ model: 'FR-500', quantity: 2 }], total: 2 },
  created_by: 'Sales', created_at: '2026-09-24T10:00:00',
  converted_snapshot: null, converted_by: null, converted_at: null,
  order_id: null, latest_at: '2026-09-24T10:00:00', version: 1,
}

async function openAs(page: import('@playwright/test').Page, role: string) {
  await page.addInitScript((value) => {
    localStorage.setItem('v7ex_auth', JSON.stringify({
      token: 'ui-test-token',
      userInfo: { username: 'ui-test', role: value, name: 'UI Test', permissions: ['CONTRACT'] },
      rememberMe: true,
    }))
  }, role)
  await page.route('**/api/v1/**', async route => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ data: [], total: 0 }) })
  })
  await page.goto('http://127.0.0.1:8888/')
}

test('Boss sees two-stage contract message and can mark it read', async ({ page }) => {
  let read = false
  await openAs(page, 'Boss')
  await page.route('**/api/v1/notifications**', async route => {
    const url = new URL(route.request().url())
    if (url.pathname.endsWith('/unread-count')) {
      await route.fulfill({ json: { total: read ? 0 : 1 } })
    } else if (url.pathname.endsWith('/read')) {
      read = true
      await route.fulfill({ json: { ok: true } })
    } else if (url.pathname.endsWith('/read-all')) {
      read = true
      await route.fulfill({ json: { ok: true } })
    } else {
      const data = url.searchParams.get('unread') === 'true' && read ? [] : [{ ...message, unread: !read }]
      await route.fulfill({ json: { data, total: data.length, page: 1, limit: 20 } })
    }
  })
  await page.reload()
  const bell = page.getByRole('button', { name: /合同消息/ })
  await expect(bell).toBeVisible()
  await expect(page.locator('.unread-badge')).toHaveText('1')
  await bell.click()
  await expect(page.getByText('HT-TEST-001')).toBeVisible()
  await page.getByRole('button', { name: /HT-TEST-001/ }).click()
  await expect(page.getByText('待转订单')).toBeVisible()
  await expect(page.locator('.unread-badge')).toHaveCount(0)
  await page.getByRole('tab', { name: '未读' }).click()
  await expect(page.getByText('暂无消息')).toBeVisible()

  await page.setViewportSize({ width: 390, height: 760 })
  await page.getByRole('tab', { name: '全部' }).click()
  const panel = await page.locator('.notification-panel').boundingBox()
  expect(panel).not.toBeNull()
  expect(panel!.x).toBeGreaterThanOrEqual(0)
  expect(panel!.x + panel!.width).toBeLessThanOrEqual(390)
})

test('Sales does not see the bell', async ({ page }) => {
  await openAs(page, 'Sales')
  await expect(page.getByRole('button', { name: /合同消息/ })).toHaveCount(0)
})

test('order progress stays in the same contract message and all-read clears it', async ({ page }) => {
  let read = false
  await openAs(page, 'Boss')
  await page.route('**/api/v1/notifications**', async route => {
    const url = new URL(route.request().url())
    if (url.pathname.endsWith('/unread-count')) {
      await route.fulfill({ json: { total: read ? 0 : 1 } })
    } else if (url.pathname.endsWith('/read-all')) {
      read = true
      await route.fulfill({ json: { ok: true } })
    } else {
      const converted = {
        ...message, order_id: 'SO-TEST-001', converted_by: 'Boss',
        converted_at: '2026-09-24T14:00:00', latest_at: '2026-09-24T14:00:00', version: 2,
        converted_snapshot: { ...message.created_snapshot, models: [{ model: 'FR-500', quantity: 3 }], total: 3 },
        unread: !read,
      }
      await route.fulfill({ json: { data: [converted], total: 1, page: 1, limit: 20 } })
    }
  })
  await page.reload()
  await page.getByRole('button', { name: /合同消息/ }).click()
  await expect(page.locator('.message')).toHaveCount(1)
  await page.getByRole('button', { name: /HT-TEST-001/ }).click()
  await expect(page.getByText('订单 SO-TEST-001')).toBeVisible()
  await expect(page.locator('.stage-detail').first()).toContainText('FR-500 × 2')
  await expect(page.locator('.stage-detail').last()).toContainText('FR-500 × 3')
  await page.getByRole('button', { name: '全部已读' }).click()
  await expect(page.locator('.unread-badge')).toHaveCount(0)
})
