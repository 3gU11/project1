import { test, expect, type APIRequestContext, type Page } from '@playwright/test';

const USERNAME = 'admin';
const PASSWORD = '888';

type DictRow = Record<string, any>;
type ApiListResponse<T> = { data?: T[]; total?: number };

// ---------------------------------------------------------------------------
// API helpers (same pattern as overall_flow.spec.ts)
// ---------------------------------------------------------------------------

async function apiLogin(request: APIRequestContext): Promise<string> {
  const response = await request.post('/api/v1/auth/login', {
    form: { username: USERNAME, password: PASSWORD },
  });
  expect(response.ok()).toBeTruthy();
  const json = await response.json();
  expect(json.access_token).toBeTruthy();
  return String(json.access_token);
}

async function apiGetJson<T>(request: APIRequestContext, token: string, url: string): Promise<T> {
  const response = await request.get(url, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(response.ok(), `GET ${url} failed with status ${response.status()}`).toBeTruthy();
  return await response.json();
}

async function apiPostJson<T>(request: APIRequestContext, token: string, url: string, data?: any): Promise<T> {
  const response = await request.post(url, {
    headers: { Authorization: `Bearer ${token}` },
    data,
  });
  expect(response.ok(), `POST ${url} failed with status ${response.status()}`).toBeTruthy();
  return await response.json();
}

async function fetchAllRows<T>(request: APIRequestContext, token: string, url: string, pageSize = 500): Promise<T[]> {
  const rows: T[] = [];
  let skip = 0;
  let total = Number.POSITIVE_INFINITY;
  while (skip < total) {
    const sep = url.includes('?') ? '&' : '?';
    const json = await apiGetJson<ApiListResponse<T>>(request, token, `${url}${sep}skip=${skip}&limit=${pageSize}`);
    const chunk = json.data || [];
    rows.push(...chunk);
    total = Number.isFinite(Number(json.total)) ? Number(json.total) : rows.length;
    if (chunk.length === 0 || chunk.length < pageSize) break;
    skip += chunk.length;
  }
  return rows;
}

async function fetchDealerOrders(request: APIRequestContext, token: string, orderNo: string): Promise<DictRow | null> {
  const json = await apiGetJson<ApiListResponse<DictRow>>(
    request,
    token,
    `/api/v1/dealer-orders/?keyword=${encodeURIComponent(orderNo)}&page=1&page_size=10`,
  );
  return json.data?.[0] || null;
}

async function fetchInventoryRows(request: APIRequestContext, token: string): Promise<DictRow[]> {
  return await fetchAllRows<DictRow>(request, token, '/api/v1/inventory/');
}

async function fetchPlanningRows(request: APIRequestContext, token: string, contractId: string): Promise<DictRow[]> {
  return await fetchAllRows<DictRow>(request, token, `/api/v1/planning/?contract_id=${encodeURIComponent(contractId)}`);
}

async function fetchOrderRows(request: APIRequestContext, token: string): Promise<DictRow[]> {
  return await fetchAllRows<DictRow>(request, token, '/api/v1/planning/orders');
}

async function fetchRushOrders(request: APIRequestContext, token: string, contractNo: string): Promise<DictRow[]> {
  const json = await apiGetJson<ApiListResponse<DictRow>>(
    request,
    token,
    `/api/v1/sandbox/rush-orders?status=pending`,
  );
  return (json.data || []).filter((r) => String(r.contract_no || '') === contractNo);
}

async function fetchFactoryPlanByContract(request: APIRequestContext, token: string, contractNo: string): Promise<DictRow[]> {
  return await fetchAllRows<DictRow>(request, token, `/api/v1/planning/?contract_id=${encodeURIComponent(contractNo)}`);
}

const isFreeFlowMachine = (row: DictRow) => {
  const serialNo = String(row['流水号'] || '').trim();
  const model = String(row['机型'] || '').trim();
  const occupiedOrderId = String(row['占用订单号'] || '').trim();
  const status = String(row['状态'] || '').trim();
  return Boolean(serialNo && model && !occupiedOrderId && (status === '待入库' || status.startsWith('库存中')));
};

// ---------------------------------------------------------------------------
// UI helpers
// ---------------------------------------------------------------------------

async function loginByUi(page: Page) {
  await page.goto('/login');
  await page.getByPlaceholder('请输入账号').fill(USERNAME);
  await page.getByPlaceholder('请输入密码').fill(PASSWORD);
  await page.locator('button:has-text("登录")').click();
  await expect(page.locator('text=当前用户：')).toBeVisible({ timeout: 15000 });
}

async function waitForToast(page: Page, text: RegExp) {
  await expect(page.locator('.el-message').last()).toContainText(text, { timeout: 15000 });
}

async function fillInputNextToLabel(page: Page, label: string, value: string) {
  const input = page.locator(`xpath=//div[normalize-space(.)='${label}']/following-sibling::*[1]//input`).first();
  await expect(input).toBeVisible();
  await input.fill(value);
}

async function clickVisibleTableCheckboxByText(page: Page, text: string) {
  const row = page.locator('.el-table__body-wrapper tbody tr').filter({ hasText: text }).first();
  await expect(row).toBeVisible({ timeout: 15000 });
  await row.locator('.el-checkbox').first().click({ force: true });
}

async function selectVisibleOrder(page: Page, orderId: string) {
  await page.getByPlaceholder('搜索订单号/客户').fill(orderId);
  const orderButton = page.locator('button.order-item').filter({ hasText: orderId }).first();
  await expect(orderButton).toBeVisible({ timeout: 15000 });
  await orderButton.click();
}

// ---------------------------------------------------------------------------
// Test config
// ---------------------------------------------------------------------------

test.use({
  trace: 'retain-on-failure',
  screenshot: 'only-on-failure',
  video: 'retain-on-failure',
});

// ---------------------------------------------------------------------------
// Dealer Order Flow: 经销商订单审核 → 转合同 → 现货 → 订单配货 → 发货复核
// ---------------------------------------------------------------------------

test.describe('经销商订单审核全流程', () => {

  test('经销商订单审核 → 转合同(现货) → 订单配货 → 发货复核', async ({ page, request }) => {
    test.slow();

    const token = await apiLogin(request);

    // 1. Find a free machine in inventory whose model is also in the model dictionary
    const inventoryRows = await fetchInventoryRows(request, token);
    const dictRows = await fetchAllRows<DictRow>(request, token, '/api/v1/model-dictionary/');
    const dictModels = new Set(dictRows.map((r) => String(r.model_name || '').trim()).filter(Boolean));
    const selectedMachine = inventoryRows.find(
      (row) => isFreeFlowMachine(row) && dictModels.has(String(row['机型'] || '').trim()),
    );
    test.skip(!selectedMachine, '当前环境没有字典中且空闲的机台');

    const serialNo = String(selectedMachine!['流水号'] || '').trim();
    const modelName = String(selectedMachine!['机型'] || '').trim();
    const needInbound = String(selectedMachine!['状态'] || '').trim() === '待入库';

    const runId = `${Date.now()}`;
    const customerName = `E2E经销商客户-${runId}`;
    const contactName = `E2E经销商联系人-${runId}`;
    const dealerName = `E2E经销商-${runId}`;
    const contractNote = `E2E经销商流程-${runId}`;

    let orderNo = '';
    let contractId = '';
    let orderId = '';

    await loginByUi(page);

    // -----------------------------------------------------------------------
    // Step 1: Seed a test dealer order via API
    // -----------------------------------------------------------------------
    await test.step('创建测试经销商订单', async () => {
      const seedRes = await apiPostJson<{ message?: string; order_no?: string }>(
        request,
        token,
        '/api/v1/dealer-orders/test-seed',
        {
          customer_name: customerName,
          contact_name: contactName,
          model: modelName,
          batch_no: 'FINISHED-STOCK',
          inventory_type: 'finished',
          quantity: 1,
          delivery_date: new Date().toISOString().slice(0, 10),
          remark: 'E2E自动测试订单',
          dealer_name: dealerName,
        },
      );
      orderNo = String(seedRes.order_no || '').trim();
      expect(orderNo).toBeTruthy();
    });

    // -----------------------------------------------------------------------
    // Step 2: Approve the dealer order via UI
    // -----------------------------------------------------------------------
    await test.step('经销商订单审核通过', async () => {
      await page.goto('/dealer-orders');
      await expect(page.getByRole('heading', { name: '经销商订单审核' })).toBeVisible();

      // Search for our order
      await page.locator('.keyword input').fill(orderNo);
      await page.getByRole('button', { name: '查询', exact: true }).click();

      // Wait for the row to appear
      const row = page.locator('.el-table__body-wrapper tbody tr').filter({ hasText: orderNo }).first();
      await expect(row).toBeVisible({ timeout: 15000 });

      // Click "通过" button
      const approveBtn = row.locator('button:has-text("通过")');
      await expect(approveBtn).toBeVisible();
      await approveBtn.click();

      // Fill optional note
      const promptBox = page.locator('.el-message-box').last();
      await expect(promptBox).toBeVisible();
      await promptBox.locator('textarea').fill('E2E自动审核通过');
      await promptBox.locator('button:has-text("通过")').click();
      await waitForToast(page, /审核通过/);

      // Verify status changed to approved
      await expect.poll(async () => {
        const order = await fetchDealerOrders(request, token, orderNo);
        return String(order?.status || '');
      }).toBe('approved');
    });

    // -----------------------------------------------------------------------
    // Step 3: Convert to contract (spot mode) via the new "转合同" dialog
    // -----------------------------------------------------------------------
    await test.step('经销商订单转合同(使用现货)', async () => {
      await page.goto('/dealer-orders');
      await page.locator('.keyword input').fill(orderNo);
      // Switch to approved filter to find it faster
      await page.locator('.status-filter').click();
      await page.locator('.el-select-dropdown:visible .el-select-dropdown__item').filter({ hasText: '已通过' }).click();
      await page.getByRole('button', { name: '查询', exact: true }).click();

      const row = page.locator('.el-table__body-wrapper tbody tr').filter({ hasText: orderNo }).first();
      await expect(row).toBeVisible({ timeout: 15000 });

      // Click "转合同" button
      const convertBtn = row.locator('button:has-text("转合同")');
      await expect(convertBtn).toBeVisible();
      await convertBtn.click();

      // Wait for the convert dialog
      const dialog = page.locator('.el-dialog').filter({ hasText: '转为合同' }).last();
      await expect(dialog).toBeVisible({ timeout: 10000 });

      // Read the auto-generated contract ID
      contractId = String((await dialog.locator('input[placeholder="自动生成"]').inputValue()) || '').trim();
      if (!contractId) {
        // Fallback: use the displayed value
        const contractInput = dialog.locator('.convert-grid .el-input input').first();
        contractId = String((await contractInput.inputValue()) || '').trim();
      }

      // Ensure customer and agent are filled
      const customerInput = dialog.locator('input').nth(2); // customer field
      const agentInput = dialog.locator('input').nth(3); // agent field

      // Ensure delivery date is set
      const dateInput = dialog.locator('.convert-grid .el-date-editor input').first();
      if (!(await dateInput.inputValue())) {
        await dateInput.fill(new Date().toISOString().slice(0, 10));
      }

      // Fill contract note
      const noteInput = dialog.locator('textarea, input[placeholder="可选"]').last();
      if (await noteInput.isVisible()) {
        await noteInput.fill(contractNote);
      }

      // Click "使用现货" to save
      const spotBtn = dialog.locator('button:has-text("使用现货")');
      await expect(spotBtn).toBeVisible();
      await spotBtn.click();
      await waitForToast(page, /转合同成功|已按.*现货.*处理/);
    });

    // -----------------------------------------------------------------------
    // Step 4: Verify dealer order is now contracted
    // -----------------------------------------------------------------------
    await test.step('校验经销商订单状态为已转合同', async () => {
      await expect.poll(async () => {
        const order = await fetchDealerOrders(request, token, orderNo);
        return String(order?.status || '');
      }).toBe('contracted');

      // Verify contract exists in factory_plan
      await expect.poll(async () => {
        const rows = await fetchPlanningRows(request, token, contractId);
        return String(rows[0]?.['状态'] || '');
      }).toBe('已规划');
    });

    // -----------------------------------------------------------------------
    // Step 5: If needed, complete inbound
    // -----------------------------------------------------------------------
    await test.step('必要时完成成品入库', async () => {
      if (!needInbound) {
        await expect.poll(async () => {
          const rows = await fetchInventoryRows(request, token);
          const hit = rows.find((row) => String(row['流水号'] || '').trim() === serialNo);
          return String(hit?.['状态'] || '');
        }).toContain('库存中');
        return;
      }

      await page.goto('/inbound');
      await expect(page.locator('text=设备入库登记')).toBeVisible();
      await page.getByPlaceholder('请输入批次号或流水号进行检索').fill(serialNo);
      await clickVisibleTableCheckboxByText(page, serialNo);
      await expect(page.locator('.slot-btn:not([disabled])').first()).toBeVisible();
      await page.locator('.slot-btn:not([disabled])').first().click();
      await waitForToast(page, /入库成功|入库完成/);

      await expect.poll(async () => {
        const rows = await fetchInventoryRows(request, token);
        const hit = rows.find((row) => String(row['流水号'] || '').trim() === serialNo);
        return String(hit?.['状态'] || '');
      }).toContain('库存中');
    });

    // -----------------------------------------------------------------------
    // Step 6: Generate sales order from contract
    // -----------------------------------------------------------------------
    await test.step('从已规划合同生成订单', async () => {
      await page.goto('/sales-orders');
      await expect(page.locator('text=销售订单管理')).toBeVisible();

      await page.locator('button:has-text("导入已规划合同")').click();
      await page.getByPlaceholder('搜索合同号/客户名（模糊）').fill(contractId);
      await clickVisibleTableCheckboxByText(page, contractId);
      await expect(page.locator('text=确认合并订单信息')).toBeVisible();
      await page.locator('button:has-text("确认生成合并订单")').click();
      await waitForToast(page, /订单|成功/);

      await expect.poll(async () => {
        const rows = await fetchOrderRows(request, token);
        const hit = rows.find((row) => String(row['客户名'] || '').trim() === customerName);
        if (!hit) return '';
        orderId = String(hit['订单号'] || '').trim();
        return orderId;
      }).not.toBe('');
    });

    // -----------------------------------------------------------------------
    // Step 7: Allocate and complete allocation
    // -----------------------------------------------------------------------
    await test.step('订单配货并完成配货', async () => {
      await page.goto('/order-allocation');
      await expect(page.locator('text=订单列表（进行中）')).toBeVisible();

      await selectVisibleOrder(page, orderId);
      await expect(page.locator('text=应配机台清单')).toBeVisible();
      await clickVisibleTableCheckboxByText(page, serialNo);
      await page.locator('button:has-text("复核确认配货")').click();
      await waitForToast(page, /配货复核已确认|配货成功/);

      await expect.poll(async () => {
        const rows = await fetchInventoryRows(request, token);
        const hit = rows.find((row) => String(row['流水号'] || '').trim() === serialNo);
        return `${String(hit?.['状态'] || '')}|${String(hit?.['占用订单号'] || '')}`;
      }).toContain(orderId);

      await page.locator('button:has-text("配货完成")').click();
      await waitForToast(page, /配货完成|订单已满足/);

      await expect.poll(async () => {
        const rows = await fetchOrderRows(request, token);
        const hit = rows.find((row) => String(row['订单号'] || '').trim() === orderId);
        return String(hit?.status || '');
      }).toBe('ready');
    });

    // -----------------------------------------------------------------------
    // Step 8: Verify dealer order auto-sync: partial_allocated → allocated
    // -----------------------------------------------------------------------
    await test.step('校验经销商订单自动同步为已配货', async () => {
      // After sales_order is ready, the dealer_order should auto-sync to "allocated"
      await expect.poll(async () => {
        const order = await fetchDealerOrders(request, token, orderNo);
        return `${String(order?.status || '')}|${Number(order?.allocated_qty || 0)}`;
      }).toBe('allocated|1');
    });

    // -----------------------------------------------------------------------
    // Step 9: Ship and complete
    // -----------------------------------------------------------------------
    await test.step('发货复核并确认订单完结', async () => {
      await page.goto('/shipping-review');
      await expect(page.locator('.card-head').filter({ hasText: '待发货订单' })).toBeVisible();

      await selectVisibleOrder(page, orderId);
      await expect(page.locator('text=待发货机台清单')).toBeVisible();
      await clickVisibleTableCheckboxByText(page, serialNo);
      await page.locator('button:has-text("确认发货")').click();
      await waitForToast(page, /发货|成功/);

      await expect.poll(async () => {
        const rows = await fetchOrderRows(request, token);
        const hit = rows.find((row) => String(row['订单号'] || '').trim() === orderId);
        return String(hit?.status || '');
      }).toBe('done');

      await expect.poll(async () => {
        const rows = await fetchInventoryRows(request, token);
        const hit = rows.find((row) => String(row['流水号'] || '').trim() === serialNo);
        return String(hit?.['状态'] || '');
      }).toBe('已出库');
    });

    // -----------------------------------------------------------------------
    // Step 10: Verify dealer order auto-syncs to completed
    // -----------------------------------------------------------------------
    await test.step('校验经销商订单自动同步为已完成', async () => {
      // After sales_order is done + all machines shipped, dealer_order → completed
      await expect.poll(async () => {
        const order = await fetchDealerOrders(request, token, orderNo);
        return String(order?.status || '');
      }, { timeout: 30000 }).toBe('completed');
    });

    // -----------------------------------------------------------------------
    // Step 11: Verify completed order does NOT appear in pending lists
    // -----------------------------------------------------------------------
    await test.step('校验已完成的经销商订单不在待审核列表', async () => {
      await page.goto('/dealer-orders');
      await page.locator('.status-filter').click();
      await page.locator('.el-select-dropdown:visible .el-select-dropdown__item').filter({ hasText: '待审核' }).click();
      await page.locator('.keyword input').fill(orderNo);
      await page.getByRole('button', { name: '查询', exact: true }).click();

      // The order should not appear in pending list
      await expect(
        page.locator('.el-table__body-wrapper tbody tr').filter({ hasText: orderNo }),
      ).toHaveCount(0);

      // But it should appear in completed list
      await page.locator('.status-filter').click();
      await page.locator('.el-select-dropdown:visible .el-select-dropdown__item').filter({ hasText: '已完成' }).click();
      const completedRow = page.locator('.el-table__body-wrapper tbody tr').filter({ hasText: orderNo }).first();
      await expect(completedRow).toBeVisible({ timeout: 10000 });

      // And should NOT have "已配货" / "转合同" buttons (already completed)
      await expect(completedRow.locator('button:has-text("转合同")')).toBeDisabled();
    });
  });

  // -----------------------------------------------------------------------
  // Sandbox mode (进入沙盘) — contract gets 待规划 status, needs forecast recompute
  // -----------------------------------------------------------------------
  test('经销商订单审核 → 转合同(沙盘) → 验证待规划', async ({ page, request }) => {
    test.slow();

    const token = await apiLogin(request);

    // Pick a free machine whose model is in dictionary
    const inventoryRows = await fetchInventoryRows(request, token);
    const dictRows = await fetchAllRows<DictRow>(request, token, '/api/v1/model-dictionary/');
    const dictModels = new Set(dictRows.map((r) => String(r.model_name || '').trim()).filter(Boolean));
    const selectedMachine = inventoryRows.find(
      (row) => isFreeFlowMachine(row) && dictModels.has(String(row['机型'] || '').trim()),
    );
    test.skip(!selectedMachine, '当前环境没有字典中且空闲的机台');

    const modelName = String(selectedMachine!['机型'] || '').trim();
    const runId = `${Date.now()}`;
    const customerName = `E2E沙盘客户-${runId}`;
    const dealerName = `E2E沙盘经销商-${runId}`;

    let orderNo = '';
    let contractId = '';

    await loginByUi(page);

    // Step 1: Seed test dealer order
    await test.step('创建测试经销商订单', async () => {
      const seedRes = await apiPostJson<{ message?: string; order_no?: string }>(
        request, token, '/api/v1/dealer-orders/test-seed',
        {
          customer_name: customerName,
          contact_name: `E2E联系人-${runId}`,
          model: modelName,
          batch_no: 'FINISHED-STOCK',
          inventory_type: 'finished',
          quantity: 1,
          delivery_date: new Date().toISOString().slice(0, 10),
          remark: 'E2E沙盘测试',
          dealer_name: dealerName,
        },
      );
      orderNo = String(seedRes.order_no || '').trim();
      expect(orderNo).toBeTruthy();
    });

    // Step 2: Approve
    await test.step('经销商订单审核通过', async () => {
      await page.goto('/dealer-orders');
      await expect(page.getByRole('heading', { name: '经销商订单审核' })).toBeVisible();
      await page.locator('.keyword input').fill(orderNo);
      await page.getByRole('button', { name: '查询', exact: true }).click();

      const row = page.locator('.el-table__body-wrapper tbody tr').filter({ hasText: orderNo }).first();
      await expect(row).toBeVisible({ timeout: 15000 });

      const approveBtn = row.locator('button:has-text("通过")');
      await expect(approveBtn).toBeVisible();
      await approveBtn.click();

      const promptBox = page.locator('.el-message-box').last();
      await expect(promptBox).toBeVisible();
      await promptBox.locator('textarea').fill('E2E沙盘审核通过');
      await promptBox.locator('button:has-text("通过")').click();
      await waitForToast(page, /审核通过/);
    });

    // Step 3: Convert to contract via sandbox mode (进入沙盘)
    await test.step('经销商订单转合同(进入沙盘)', async () => {
      await page.goto('/dealer-orders');
      await page.locator('.keyword input').fill(orderNo);
      // Switch to approved filter
      await page.locator('.status-filter').click();
      await page.locator('.el-select-dropdown:visible .el-select-dropdown__item').filter({ hasText: '已通过' }).click();
      await page.getByRole('button', { name: '查询', exact: true }).click();

      const row = page.locator('.el-table__body-wrapper tbody tr').filter({ hasText: orderNo }).first();
      await expect(row).toBeVisible({ timeout: 15000 });

      const convertBtn = row.locator('button:has-text("转合同")');
      await expect(convertBtn).toBeVisible();
      await convertBtn.click();

      const dialog = page.locator('.el-dialog').filter({ hasText: '转为合同' }).last();
      await expect(dialog).toBeVisible({ timeout: 10000 });

      // Read the auto-generated contract ID
      contractId = String((await dialog.locator('input[placeholder="自动生成"]').inputValue()) || '').trim();
      if (!contractId) {
        const contractInput = dialog.locator('.convert-grid .el-input input').first();
        contractId = String((await contractInput.inputValue()) || '').trim();
      }

      // Ensure delivery date is set
      const dateInput = dialog.locator('.convert-grid .el-date-editor input').first();
      if (!(await dateInput.inputValue())) {
        await dateInput.fill(new Date().toISOString().slice(0, 10));
      }

      // Fill contract note
      const noteInput = dialog.locator('textarea, input[placeholder="可选"]').last();
      if (await noteInput.isVisible()) {
        await noteInput.fill(`E2E沙盘测试-${runId}`);
      }

      // Click "进入沙盘" to save
      const sandboxBtn = dialog.locator('button:has-text("进入沙盘")');
      await expect(sandboxBtn).toBeVisible();
      await sandboxBtn.click();
      await waitForToast(page, /进入沙盘/);
    });

    // Step 4: Verify contract is in factory_plan with status "待规划"
    await test.step('校验合同状态为待规划', async () => {
      // Dealer order should be contracted
      await expect.poll(async () => {
        const order = await fetchDealerOrders(request, token, orderNo);
        return String(order?.status || '');
      }).toBe('contracted');

      // factory_plan should have the contract with status "待规划"
      await expect.poll(async () => {
        const rows = await fetchFactoryPlanByContract(request, token, contractId);
        return String(rows[0]?.['状态'] || '');
      }).toBe('待规划');
    });
  });

  // -----------------------------------------------------------------------
  // Sandbox + Rush (急单) — contract enters sandbox AND generates rush order queue entries
  // -----------------------------------------------------------------------
  test('经销商订单审核 → 转合同(沙盘+急单) → 验证急单队列', async ({ page, request }) => {
    test.slow();

    const token = await apiLogin(request);

    const inventoryRows = await fetchInventoryRows(request, token);
    const dictRows = await fetchAllRows<DictRow>(request, token, '/api/v1/model-dictionary/');
    const dictModels = new Set(dictRows.map((r) => String(r.model_name || '').trim()).filter(Boolean));
    const selectedMachine = inventoryRows.find(
      (row) => isFreeFlowMachine(row) && dictModels.has(String(row['机型'] || '').trim()),
    );
    test.skip(!selectedMachine, '当前环境没有字典中且空闲的机台');

    const modelName = String(selectedMachine!['机型'] || '').trim();
    const runId = `${Date.now()}`;
    const customerName = `E2E急单客户-${runId}`;
    const dealerName = `E2E急单经销商-${runId}`;

    let orderNo = '';
    let contractId = '';

    await loginByUi(page);

    // Step 1: Seed test dealer order with rush hint in remark
    await test.step('创建测试经销商订单(急单)', async () => {
      const seedRes = await apiPostJson<{ message?: string; order_no?: string }>(
        request, token, '/api/v1/dealer-orders/test-seed',
        {
          customer_name: customerName,
          contact_name: `E2E联系人-${runId}`,
          model: modelName,
          batch_no: 'FINISHED-STOCK',
          inventory_type: 'finished',
          quantity: 1,
          delivery_date: new Date().toISOString().slice(0, 10),
          remark: 'E2E急单测试 加急',
          dealer_name: dealerName,
        },
      );
      orderNo = String(seedRes.order_no || '').trim();
      expect(orderNo).toBeTruthy();
    });

    // Step 2: Approve
    await test.step('经销商订单审核通过', async () => {
      await page.goto('/dealer-orders');
      await expect(page.getByRole('heading', { name: '经销商订单审核' })).toBeVisible();
      await page.locator('.keyword input').fill(orderNo);
      await page.getByRole('button', { name: '查询', exact: true }).click();

      const row = page.locator('.el-table__body-wrapper tbody tr').filter({ hasText: orderNo }).first();
      await expect(row).toBeVisible({ timeout: 15000 });

      await row.locator('button:has-text("通过")').click();
      const promptBox = page.locator('.el-message-box').last();
      await expect(promptBox).toBeVisible();
      await promptBox.locator('textarea').fill('E2E急单审核通过');
      await promptBox.locator('button:has-text("通过")').click();
      await waitForToast(page, /审核通过/);
    });

    // Step 3: Convert to contract with sandbox + rush
    await test.step('经销商订单转合同(沙盘+急单)', async () => {
      await page.goto('/dealer-orders');
      await page.locator('.keyword input').fill(orderNo);
      await page.locator('.status-filter').click();
      await page.locator('.el-select-dropdown:visible .el-select-dropdown__item').filter({ hasText: '已通过' }).click();
      await page.getByRole('button', { name: '查询', exact: true }).click();

      const row = page.locator('.el-table__body-wrapper tbody tr').filter({ hasText: orderNo }).first();
      await expect(row).toBeVisible({ timeout: 15000 });

      await row.locator('button:has-text("转合同")').click();

      const dialog = page.locator('.el-dialog').filter({ hasText: '转为合同' }).last();
      await expect(dialog).toBeVisible({ timeout: 10000 });

      contractId = String((await dialog.locator('input[placeholder="自动生成"]').inputValue()) || '').trim();
      if (!contractId) {
        const contractInput = dialog.locator('.convert-grid .el-input input').first();
        contractId = String((await contractInput.inputValue()) || '').trim();
      }

      // Verify isRush switch is toggled on (remark contains "急")
      const rushSwitch = dialog.locator('.el-switch').filter({ hasText: '是' }).first();
      await expect(rushSwitch).toBeVisible({ timeout: 5000 });

      const dateInput = dialog.locator('.convert-grid .el-date-editor input').first();
      if (!(await dateInput.inputValue())) {
        await dateInput.fill(new Date().toISOString().slice(0, 10));
      }

      const noteInput = dialog.locator('textarea, input[placeholder="可选"]').last();
      if (await noteInput.isVisible()) {
        await noteInput.fill(`E2E急单测试-${runId}`);
      }

      // Click "进入沙盘"
      const sandboxBtn = dialog.locator('button:has-text("进入沙盘")');
      await expect(sandboxBtn).toBeVisible();
      await sandboxBtn.click();
      await waitForToast(page, /进入沙盘/);
    });

    // Step 4: Verify contract + rush order queue
    await test.step('校验合同待规划且急单队列已生成', async () => {
      await expect.poll(async () => {
        const order = await fetchDealerOrders(request, token, orderNo);
        return String(order?.status || '');
      }).toBe('contracted');

      // factory_plan status should be 待规划
      await expect.poll(async () => {
        const rows = await fetchFactoryPlanByContract(request, token, contractId);
        return String(rows[0]?.['状态'] || '');
      }).toBe('待规划');

      // rush_order_queue should have at least 1 pending entry for this contract
      await expect.poll(async () => {
        const rushRows = await fetchRushOrders(request, token, contractId);
        return rushRows.length;
      }, { timeout: 15000 }).toBeGreaterThan(0);
    });
  });

});
