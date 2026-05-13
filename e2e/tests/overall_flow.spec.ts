import { test, expect, type APIRequestContext, type Page } from '@playwright/test';

const USERNAME = 'admin';
const PASSWORD = '888';

type DictRow = Record<string, any>;
type ApiListResponse<T> = { data?: T[]; total?: number };

const isPendingMachine = (row: DictRow) => String(row['状态'] || '').trim() === '待入库';
const isInStockMachine = (row: DictRow) => String(row['状态'] || '').trim().startsWith('库存中');

const isFreeFlowMachine = (row: DictRow) => {
  const serialNo = String(row['流水号'] || '').trim();
  const model = String(row['机型'] || '').trim();
  const occupiedOrderId = String(row['占用订单号'] || '').trim();
  return Boolean(serialNo && model && !occupiedOrderId && (isPendingMachine(row) || isInStockMachine(row)));
};

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

async function fetchInventoryRows(request: APIRequestContext, token: string): Promise<DictRow[]> {
  return await fetchAllRows<DictRow>(request, token, '/api/v1/inventory/');
}

async function fetchPlanningRows(request: APIRequestContext, token: string, contractId: string): Promise<DictRow[]> {
  return await fetchAllRows<DictRow>(request, token, `/api/v1/planning/?contract_id=${encodeURIComponent(contractId)}`);
}

async function fetchOrderRows(request: APIRequestContext, token: string): Promise<DictRow[]> {
  return await fetchAllRows<DictRow>(request, token, '/api/v1/planning/orders');
}

async function fetchSandboxBatches(request: APIRequestContext, token: string): Promise<DictRow[]> {
  const json = await apiGetJson<{ batches?: DictRow[] }>(request, token, '/api/v1/sandbox/batches');
  return json.batches || [];
}

async function fetchSandboxLines(request: APIRequestContext, token: string): Promise<DictRow[]> {
  const json = await apiGetJson<{ lines?: DictRow[] }>(request, token, '/api/v1/sandbox/production-lines');
  return json.lines || [];
}

async function fetchSandboxBatch(request: APIRequestContext, token: string, batchId: string): Promise<DictRow | null> {
  if (!batchId) return null;
  const response = await request.get(`/api/v1/sandbox/batches/${encodeURIComponent(batchId)}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (response.status() === 404) return null;
  expect(response.ok(), `GET /api/v1/sandbox/batches/${batchId} failed with status ${response.status()}`).toBeTruthy();
  const json = await response.json() as { batch?: DictRow; units?: DictRow[] };
  return json.batch || null;
}

async function findSandboxBatchByContract(request: APIRequestContext, token: string, contractId: string): Promise<DictRow | null> {
  const batches = await fetchSandboxBatches(request, token);
  for (const batch of batches) {
    const units = Array.isArray(batch.units) ? batch.units : [];
    if (units.some((unit: DictRow) => String(unit.contract_no || '').trim() === contractId)) return batch;
  }
  for (const batch of batches) {
    const batchId = String(batch.batch_id || '').trim();
    if (!batchId) continue;
    const response = await request.get(`/api/v1/sandbox/batches/${encodeURIComponent(batchId)}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (response.status() === 404) continue;
    expect(response.ok(), `GET /api/v1/sandbox/batches/${batchId} failed with status ${response.status()}`).toBeTruthy();
    const detail = await response.json() as { batch?: DictRow; units?: DictRow[] };
    const units = detail.units || [];
    if (units.some((unit: DictRow) => String(unit.contract_no || '').trim() === contractId)) {
      return { ...batch, units };
    }
  }
  return null;
}

function nextBatchCode(lastBatchCode: string): string {
  if (/^\d{2}-\d{2}$/.test(lastBatchCode)) {
    const [month, seq] = lastBatchCode.split('-');
    return `${month}-${String(Number(seq) + 1).padStart(2, '0')}`;
  }
  return `${String(new Date().getMonth() + 1).padStart(2, '0')}-01`;
}

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

async function createManualOrder(page: Page, modelName: string, customerName: string, agentName: string) {
  await page.goto('/sales-orders');
  await expect(page.locator('text=销售订单管理')).toBeVisible();
  await page.locator('button:has-text("手动下单")').click();
  await fillInputNextToLabel(page, '客户信息 (Customer)', customerName);
  await fillInputNextToLabel(page, '代理商 (Agent)', agentName);
  await page.locator('.sales-page .el-table .el-select').first().click();
  await page.locator('.el-select-dropdown:visible .el-select-dropdown__item').filter({ hasText: modelName }).first().click();
  await page.locator('.sales-page .el-table .el-input input').first().fill('1');
  await page.locator('button:has-text("生成订单")').click();
  await waitForToast(page, /订单|成功/);
}

async function createContract(page: Page, options: {
  customerName: string;
  agentName: string;
  modelName: string;
  contractNote: string;
  saveMode: 'spot' | 'sandbox';
  deliveryDate?: string;
}): Promise<string> {
  await page.goto('/contracts');
  await expect(page.locator('text=销售合同管理')).toBeVisible();
  await page.locator('button:has-text("录入新合同")').click();
  await expect(page.locator('.auto-id').first()).toBeVisible();
  const contractId = String((await page.locator('.auto-id').first().textContent()) || '').trim();
  expect(contractId).toBeTruthy();

  if (options.deliveryDate) {
    await page.locator('.batch-grid .el-date-editor input').first().fill(options.deliveryDate);
  }
  await fillInputNextToLabel(page, '客户名称', options.customerName);
  await fillInputNextToLabel(page, '代理商名称', options.agentName);
  await page.locator('.form-table .el-select').first().click();
  await page.locator('.el-select-dropdown:visible .el-select-dropdown__item').filter({ hasText: options.modelName }).first().click();
  await page.locator('.form-table .el-input-number input').first().fill('1');
  await page.locator('input[placeholder="可选，应用于所有条目"]').fill(options.contractNote);

  await page.locator('button:has-text("保存所有合同条目")').click();
  await expect(page.locator('.el-message-box')).toBeVisible();
  if (options.saveMode === 'spot') {
    await page.locator('.el-message-box__btns button:has-text("使用现货")').click();
  } else {
    await page.locator('.el-message-box__btns button:has-text("进入沙盘")').click();
  }
  await waitForToast(page, /批量录入完成|批量录入成功|成功/);
  return contractId;
}

async function confirmSandboxBatchByUi(page: Page, contractId: string, batchCode: string, inboundDate: string) {
  const batchCard = page.locator('.batch-card').filter({ hasText: contractId }).filter({ hasText: '待确认' }).first();
  await expect(batchCard).toBeVisible({ timeout: 30000 });
  const confirmButton = page.locator('button:has-text("审核选中批次")');
  await batchCard.evaluate((el) => (el as HTMLElement).click());
  if (!(await confirmButton.isVisible())) {
    await batchCard.locator('.el-checkbox__input').first().click({ force: true });
  }
  await expect(confirmButton).toBeVisible({ timeout: 10000 });
  await confirmButton.click();

  const promptBox = page.locator('.el-message-box').last();
  await expect(promptBox).toBeVisible();
  await promptBox.locator('.el-message-box__input input').fill(batchCode);
  await promptBox.locator('.el-message-box__btns button:has-text("下一步")').click();

  const dateBox = page.locator('.el-message-box').last();
  await expect(dateBox).toBeVisible();
  await dateBox.locator('input[type="date"]').fill(inboundDate);
  await dateBox.locator('.el-message-box__btns button:has-text("下一步")').click();

  const finalBox = page.locator('.el-message-box').last();
  await expect(finalBox).toBeVisible({ timeout: 30000 });
  await finalBox.locator('.el-message-box__btns button:has-text("确认审核")').click();
}

async function assignSandboxBatchByUi(page: Page, batchCode: string) {
  const assignButton = page.locator(
    `xpath=//div[contains(@class,'kanban-right')]//strong[contains(normalize-space(.), '${batchCode}')]/ancestor::div[contains(@style,'display:flex')][1]//button[contains(., '整批分配')]`
  ).first();
  await expect(assignButton).toBeVisible({ timeout: 30000 });
  await assignButton.click();

  const dialog = page.locator('.el-dialog').filter({ hasText: '整批分配' }).last();
  await expect(dialog).toBeVisible();
  await dialog.locator('.el-select').click();
  await page.locator('.el-select-dropdown:visible .el-select-dropdown__item').first().click();
  await dialog.locator('button:has-text("确认分配")').click();
}

test.use({
  trace: 'retain-on-failure',
  screenshot: 'only-on-failure',
  video: 'retain-on-failure',
});

test.describe('系统整体业务流程', () => {
  test('合同录入 -> 成品入库 -> 订单生成 -> 订单配货 -> 发货完成', async ({ page, request }) => {
    test.slow();

    const token = await apiLogin(request);
    const inventoryRows = await fetchInventoryRows(request, token);
    const pendingCandidate = inventoryRows.find((row) => isFreeFlowMachine(row) && isPendingMachine(row));
    const inStockCandidate = inventoryRows.find((row) => isFreeFlowMachine(row) && isInStockMachine(row));
    const selectedMachine = pendingCandidate || inStockCandidate;

    test.skip(!selectedMachine, '当前环境没有可用于整体流程测试的空闲机台（待入库/库存中）');

    const serialNo = String(selectedMachine!['流水号'] || '').trim();
    const modelName = String(selectedMachine!['机型'] || '').trim();
    const needInbound = isPendingMachine(selectedMachine!);

    const runId = `${Date.now()}`;
    const customerName = `E2E客户-${runId}`;
    const agentName = `E2E代理-${runId}`;
    const contractNote = `E2E整体流程-${runId}`;
    let contractId = '';
    let orderId = '';

    await loginByUi(page);

    await test.step('录入现货合同并校验合同状态', async () => {
      await page.goto('/contracts');
      await expect(page.locator('text=销售合同管理')).toBeVisible();

      await page.locator('button:has-text("录入新合同")').click();
      await expect(page.locator('.auto-id').first()).toBeVisible();
      contractId = String((await page.locator('.auto-id').first().textContent()) || '').trim();
      expect(contractId).toBeTruthy();

      await fillInputNextToLabel(page, '客户名称', customerName);
      await fillInputNextToLabel(page, '代理商名称', agentName);
      await page.locator('.form-table .el-select').first().click();
      await page.locator('.el-select-dropdown:visible .el-select-dropdown__item').filter({ hasText: modelName }).first().click();
      await page.locator('.form-table .el-input-number input').first().fill('1');
      await page.locator('input[placeholder="可选，应用于所有条目"]').fill(contractNote);

      await page.locator('button:has-text("保存所有合同条目")').click();
      await expect(page.locator('.el-message-box')).toBeVisible();
      await page.locator('.el-message-box__btns button:has-text("使用现货")').click();
      await waitForToast(page, /批量录入完成|批量录入成功|成功/);

      await expect.poll(async () => {
        const rows = await fetchPlanningRows(request, token, contractId);
        return String(rows[0]?.['状态'] || '');
      }).toBe('已规划');
    });

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

    await test.step('校验已发货订单不再显示在配货与发货待办列表', async () => {
      await page.goto('/order-allocation');
      await page.getByPlaceholder('搜索订单号/客户').fill(orderId);
      await expect(page.locator('button.order-item').filter({ hasText: orderId })).toHaveCount(0);

      await page.goto('/shipping-review');
      await page.getByPlaceholder('搜索订单号/客户').fill(orderId);
      await expect(page.locator('button.order-item').filter({ hasText: orderId })).toHaveCount(0);
    });
  });

  test('手动订单 -> 配货完成 -> 发货撤回后恢复库存状态', async ({ page, request }) => {
    test.slow();

    const token = await apiLogin(request);
    const inventoryRows = await fetchInventoryRows(request, token);
    const pendingCandidate = inventoryRows.find((row) => isFreeFlowMachine(row) && isPendingMachine(row));
    const inStockCandidate = inventoryRows.find((row) => isFreeFlowMachine(row) && isInStockMachine(row));
    const selectedMachine = pendingCandidate || inStockCandidate;

    test.skip(!selectedMachine, '当前环境没有可用于发货撤回测试的空闲机台（待入库/库存中）');

    const serialNo = String(selectedMachine!['流水号'] || '').trim();
    const modelName = String(selectedMachine!['机型'] || '').trim();
    const originalLocation = String(selectedMachine!['Location_Code'] || '').trim();
    const expectedRestoredStatus = originalLocation ? `库存中（${originalLocation}）` : '待入库';

    const runId = `${Date.now()}`;
    const customerName = `E2E撤回客户-${runId}`;
    const agentName = `E2E撤回代理-${runId}`;
    let orderId = '';

    await loginByUi(page);

    await test.step('创建手动订单', async () => {
      await createManualOrder(page, modelName, customerName, agentName);
      await expect.poll(async () => {
        const rows = await fetchOrderRows(request, token);
        const hit = rows.find((row) => String(row['客户名'] || '').trim() === customerName);
        if (!hit) return '';
        orderId = String(hit['订单号'] || '').trim();
        return orderId;
      }).not.toBe('');
    });

    await test.step('完成配货并进入待发货', async () => {
      await page.goto('/order-allocation');
      await expect(page.locator('text=订单列表（进行中）')).toBeVisible();
      await selectVisibleOrder(page, orderId);
      await expect(page.locator('text=应配机台清单')).toBeVisible();
      await clickVisibleTableCheckboxByText(page, serialNo);
      await page.locator('button:has-text("复核确认配货")').click();
      await waitForToast(page, /配货复核已确认|配货成功/);
      await page.locator('button:has-text("配货完成")').click();
      await waitForToast(page, /配货完成|订单已满足/);

      await expect.poll(async () => {
        const rows = await fetchInventoryRows(request, token);
        const hit = rows.find((row) => String(row['流水号'] || '').trim() === serialNo);
        return String(hit?.['状态'] || '');
      }).toBe('待发货');
    });

    await test.step('发货撤回并校验状态恢复', async () => {
      await page.goto('/shipping-review');
      await expect(page.locator('.card-head').filter({ hasText: '待发货订单' })).toBeVisible();
      await selectVisibleOrder(page, orderId);
      await expect(page.locator('text=待发货机台清单')).toBeVisible();
      await clickVisibleTableCheckboxByText(page, serialNo);
      await page.locator('button:has-text("发货撤回")').click();
      await waitForToast(page, /撤回|成功/);

      await expect.poll(async () => {
        const rows = await fetchInventoryRows(request, token);
        const hit = rows.find((row) => String(row['流水号'] || '').trim() === serialNo);
        return `${String(hit?.['状态'] || '')}|${String(hit?.['占用订单号'] || '')}`;
      }).toBe(`${expectedRestoredStatus}|`);

      await page.getByPlaceholder('搜索订单号/客户').fill(orderId);
      await expect(page.locator('button.order-item').filter({ hasText: orderId })).toHaveCount(0);
    });
  });

  test('合同录入(进入老板计划) -> 沙盘排产 -> 订单生成 -> 配货发货', async ({ page, request }) => {
    test.slow();

    const token = await apiLogin(request);
    const runId = `${Date.now()}`;
    const customerName = `E2E沙盘客户-${runId}`;
    const agentName = `E2E沙盘代理-${runId}`;
    const contractNote = `E2E老板计划-${runId}`;
    const deliveryDate = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
    let contractId = '';
    let batchId = '';
    let batchCode = '';
    let lineId = '';
    let serialNo = '';
    let orderId = '';

    await loginByUi(page);

    await test.step('录入合同并进入老板计划', async () => {
      contractId = await createContract(page, {
        customerName,
        agentName,
        modelName: 'FH-300C',
        contractNote,
        saveMode: 'sandbox',
        deliveryDate,
      });

      await expect.poll(async () => {
        const rows = await fetchPlanningRows(request, token, contractId);
        return String(rows[0]?.['状态'] || '');
      }).toBe('待规划');

      await apiPostJson(request, token, '/api/v1/sandbox/forecast/recompute', {});

      await expect.poll(async () => {
        const batch = await findSandboxBatchByContract(request, token, contractId);
        batchId = String(batch?.batch_id || '').trim();
        return batchId;
      }, { timeout: 120000 }).not.toBe('');
    });

    await test.step('在预测沙盘确认批次并同步待排产', async () => {
      await page.goto('/sandbox');
      await expect(page.locator('.boss-plan-header h2')).toHaveText('老板计划');
      await page.getByText('预测沙盘', { exact: true }).click();
      await expect(page.locator('.sandbox-batches')).toContainText(contractId, { timeout: 30000 });

      const lastBatchCodeRes = await apiGetJson<{ last_batch_code?: string }>(request, token, '/api/v1/sandbox/batches/last-batch-code');
      batchCode = nextBatchCode(String(lastBatchCodeRes.last_batch_code || ''));
      await confirmSandboxBatchByUi(page, contractId, batchCode, deliveryDate);

      await expect.poll(async () => {
        const batch = await fetchSandboxBatch(request, token, batchId);
        return String(batch?.status || '');
      }, { timeout: 120000 }).toBe('Confirmed');

      await apiPostJson(request, token, `/api/v1/sandbox/batches/${encodeURIComponent(batchId)}/sync-to-plan`, {
        batch_code: batchCode,
      });
    });

    await test.step('在生产看板分配产线并完工', async () => {
      await page.goto('/sandbox');
      await expect(page.locator('.boss-plan-header h2')).toHaveText('老板计划');
      const lines = await fetchSandboxLines(request, token);
      const idleLine = lines.find((line) => String(line.status || '').trim() === 'Idle');
      expect(idleLine).toBeTruthy();
      lineId = String(idleLine?.production_line_id || '').trim();
      expect(lineId).toBeTruthy();

      try {
        await apiPostJson(request, token, `/api/v1/sandbox/production-lines/${encodeURIComponent(lineId)}/assign`, {
          batch_id: batchId,
        });
      } catch {
        // Some sandbox endpoints may return an error even after state mutation; verify by polling real state.
      }

      await expect.poll(async () => {
        const lines = await fetchSandboxLines(request, token);
        const hit = lines.find((line) => String(line.current_batch_id || '').trim() === batchId);
        lineId = String(hit?.production_line_id || '').trim();
        return lineId;
      }, { timeout: 120000 }).not.toBe('');

      await apiPostJson(request, token, `/api/v1/sandbox/batches/${encodeURIComponent(batchId)}/import-to-finished-goods`, {});

      try {
        await apiPostJson(request, token, `/api/v1/sandbox/production-lines/${encodeURIComponent(lineId)}/manual-complete`, {});
      } catch {
        // Keep polling below to determine whether the line has actually completed.
      }

      await expect.poll(async () => {
        const lines = await fetchSandboxLines(request, token);
        const hit = lines.find((line) => String(line.production_line_id || '').trim() === lineId);
        return String(hit?.status || '');
      }, { timeout: 120000 }).toBe('Idle');

      await expect.poll(async () => {
        const rows = await fetchPlanningRows(request, token, contractId);
        return String(rows[0]?.['状态'] || '');
      }, { timeout: 120000 }).toBe('已规划');

      await expect.poll(async () => {
        const rows = await fetchInventoryRows(request, token);
        const hit = rows.find((row) => String(row['合同号'] || '').trim() === contractId);
        serialNo = String(hit?.['流水号'] || '').trim();
        return serialNo;
      }, { timeout: 120000 }).not.toBe('');
    });

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

      await expect.poll(async () => {
        const rows = await fetchInventoryRows(request, token);
        const hit = rows.find((row) => String(row['流水号'] || '').trim() === serialNo);
        return String(hit?.['占用订单号'] || '');
      }).toBe(orderId);
    });

    await test.step('完成配货并确认发货', async () => {
      await page.goto('/order-allocation');
      await expect(page.locator('text=订单列表（进行中）')).toBeVisible();
      await selectVisibleOrder(page, orderId);
      await expect(page.locator('text=配货面板')).toBeVisible();
      await expect(page.locator('text=' + serialNo)).toBeVisible({ timeout: 20000 });
      await page.locator('button:has-text("配货完成")').click();
      await waitForToast(page, /配货完成|订单已满足/);

      await expect.poll(async () => {
        const rows = await fetchOrderRows(request, token);
        const hit = rows.find((row) => String(row['订单号'] || '').trim() === orderId);
        return String(hit?.status || '');
      }).toBe('ready');

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
  });
});
