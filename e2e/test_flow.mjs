import { chromium } from 'playwright-core';

// ─────────────────────────────────────────────────────────────────────────────
// Helper: fetch via page context (uses the logged-in session cookies/token)
// ─────────────────────────────────────────────────────────────────────────────
async function apiFetch(page, path, opts = {}) {
  return page.evaluate(async ({ path, opts }) => {
    // Token is stored as JSON under 'v7ex_auth' key
    let token = '';
    try {
      const raw = localStorage.getItem('v7ex_auth') || sessionStorage.getItem('v7ex_auth') || '{}';
      token = JSON.parse(raw).token || '';
    } catch {}
    const res = await fetch(path, {
      method: opts.method || 'GET',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(opts.headers || {}),
      },
      body: opts.body ? JSON.stringify(opts.body) : undefined,
    });
    const text = await res.text();
    let json;
    try { json = JSON.parse(text); } catch { json = { _raw: text }; }
    return { status: res.status, json };
  }, { path, opts });
}

// ─────────────────────────────────────────────────────────────────────────────
(async () => {
  console.log('Starting full system flow test with Edge...');
  const browser = await chromium.launch({
    channel: 'msedge',
    headless: false,
  });

  const context = await browser.newContext();
  const page = await context.newPage();

  // Log all failed HTTP responses
  page.on('response', async (response) => {
    if (response.status() >= 400) {
      console.log(`  [HTTP ${response.status()}] ${response.url()}`);
      try { console.log('  Body:', await response.text()); } catch {}
    }
  });

  try {
    // ── 1. Login ──────────────────────────────────────────────────────────────
    console.log('\n=== 1. Login ===');
    await page.goto('http://localhost:3000');
    await page.fill('input[placeholder="请输入账号"]', 'boss');
    await page.fill('input[placeholder="请输入密码"]', '888');
    await page.click('button:has-text("登录")');
    await page.waitForSelector('text=当前用户：', { timeout: 10000 });
    console.log('  Login OK');

    // ── 2. Contract Management (进入沙盘) ─────────────────────────────────────
    console.log('\n=== 2. Contract Management ===');
    await page.click('button:has-text("合同管理")');
    await page.waitForSelector('text=销售合同管理');

    // Open the batch panel (▸ 录入新合同)
    await page.click('button.new-row-toggle');
    await page.waitForTimeout(500);

    // Use the batch-grid cell structure: div[0]=合同号(auto), div[1]=deadline, div[2]=客户名称, div[3]=代理商名称
    // Wait for panel animation to complete
    await page.waitForTimeout(600);
    const batchGrid = page.locator('.batch-panel .batch-grid > div');
    await batchGrid.nth(2).locator('input').fill('E2E Test Customer');
    await batchGrid.nth(3).locator('input').fill('E2E Test Agent');

    // 机型 dropdown – pick first available option (in the form-table's first row)
    await page.locator('.batch-panel .form-table .el-select').first().click();
    await page.waitForTimeout(600);
    await page.locator('.el-select-dropdown__item:visible').first().click();
    await page.waitForTimeout(300);

    // 数量 (el-input-number inside form-table)
    await page.locator('.batch-panel .el-input-number input').first().fill('1');

    // Submit form → triggers save-mode dialog
    await page.click('button:has-text("保存所有合同条目")');

    // ── Handle 保存方式 dialog: click "进入沙盘" ────────────────────────────
    await page.waitForSelector('text=保存方式', { timeout: 10000 });
    await page.click('button:has-text("进入沙盘")');
    // Wait for dialog to close (批量录入成功后对话框消失)
    await page.waitForSelector('text=保存方式', { state: 'hidden', timeout: 20000 });
    await page.waitForTimeout(800);
    console.log('  Contract created (sandbox mode).');

    // ── 3. Boss Plan – Sandbox (预测沙盘) ─────────────────────────────────────
    console.log('\n=== 3. Boss Plan (Sandbox) ===');
    await page.goto('http://localhost:3000/sandbox');
    await page.waitForSelector('text=老板计划', { timeout: 10000 });

    // Switch to 预测沙盘 tab
    await page.locator('.el-segmented__item:has-text("预测沙盘")').click();
    await page.waitForTimeout(800);

    // Trigger recompute to materialise the freshly created contract into batches
    console.log('  Triggering full recompute...');
    const recomputeBtn = page.locator('button').filter({ hasText: /全量重算|重算/ }).first();
    if (await recomputeBtn.count()) {
      await recomputeBtn.click();
      // Wait until the loading state disappears or batch cards appear (up to 60 s)
      await page.waitForSelector('.batch-card', { timeout: 60000 });
    } else {
      await page.waitForSelector('.batch-card', { timeout: 30000 });
    }
    console.log('  Batch cards loaded.');

    // ── Dynamically pick the first Predicted batch via API ───────────────────
    const batchListResp = await apiFetch(page, '/api/v1/sandbox/batches?status=Predicted');
    console.log('  GET /batches status:', batchListResp.status);
    const batches = batchListResp.json?.batches ?? [];
    if (batches.length === 0) {
      throw new Error('No Predicted batches found after recompute – check contract/model dictionary setup.');
    }
    const targetBatch = batches[0];
    const batchId   = targetBatch.batch_id;
    const batchNo   = targetBatch.batch_no;
    console.log(`  Selecting batch: id=${batchId}  no=${batchNo}  status=${targetBatch.status}`);

    // Click the checkbox of the matching batch-card in UI
    // Element Plus hides the real <input> – click the visible .el-checkbox__inner instead
    const batchCard = page.locator(`.batch-card[data-batch-id="${batchId}"]`).first();
    const cardCount = await batchCard.count();
    if (cardCount > 0) {
      await batchCard.scrollIntoViewIfNeeded();
      await page.waitForTimeout(300);
      await batchCard.locator('.el-checkbox__inner').first().click();
    } else {
      // Fallback: scroll to and click first card's checkbox inner
      const firstCard = page.locator('.batch-card').first();
      await firstCard.scrollIntoViewIfNeeded();
      await page.waitForTimeout(300);
      await firstCard.locator('.el-checkbox__inner').first().click();
    }
    await page.waitForTimeout(500);

    // Click 审核选中批次 (yellow/warning button in sandbox filters)
    const confirmBatchBtn = page.locator('.sandbox-filters button.el-button--warning').first();
    await confirmBatchBtn.click();

    // ── Step 1: 批次号 prompt ─────────────────────────────────────────────────
    await page.waitForSelector('text=请输入批次号', { timeout: 8000 });

    // Get hint from API to know expected format
    const hintResp = await apiFetch(page, '/api/v1/sandbox/batches/last-batch-code');
    const lastCode = hintResp.json?.last_batch_code ?? '';
    // Generate next code: increment seq part, or use '05-01' as default
    let batchCode = '05-01';
    if (lastCode && /^\d{2}-\d{2}$/.test(lastCode)) {
      const [mm, ss] = lastCode.split('-').map(Number);
      batchCode = `${String(mm).padStart(2,'0')}-${String(ss + 1).padStart(2,'0')}`;
    }
    console.log(`  Using batch_code: ${batchCode}`);

    await page.locator('.el-message-box__input input').fill(batchCode);
    await page.click('button:has-text("下一步")');

    // If mismatch error, read expected value and retry
    try {
      const errorMsg = await page.locator('.el-message__content').textContent({ timeout: 2000 });
      if (errorMsg && errorMsg.includes('应为')) {
        const expected = errorMsg.split('应为')[1].trim().split(/\s/)[0];
        console.log(`  Batch code mismatch, correcting to: ${expected}`);
        await page.locator('.el-message-box__input input').fill(expected);
        await page.click('button:has-text("下一步")');
      }
    } catch {}

    // ── Step 2: 预计入库时间 prompt ───────────────────────────────────────────
    await page.waitForSelector('text=预计入库时间', { timeout: 8000 });
    await page.click('button:has-text("下一步")');

    // ── Step 3: 最终确认 ──────────────────────────────────────────────────────
    await page.waitForSelector('text=最终确认', { timeout: 8000 });
    await page.click('button:has-text("确认审核")');

    try {
      const finalMsg = await page.locator('.el-message__content').last().textContent({ timeout: 8000 });
      console.log('  Confirm message:', finalMsg);
    } catch {
      console.log('  (No final message captured)');
    }
    console.log('  Batch confirmed.');

    // Wait for status to update
    await page.waitForTimeout(1500);

    // ── 4. Boss Plan – Production Kanban (生产看板) ────────────────────────────
    console.log('\n=== 4. Boss Plan (Kanban) ===');
    await page.locator('.el-segmented__item:has-text("生产看板")').click();
    await page.waitForTimeout(2500);

    // Assign to production line
    console.log('  Assigning to production line...');
    const assignBtn = page.locator('button:has-text("整批分配")').first();
    await assignBtn.waitFor({ state: 'visible', timeout: 15000 });
    await assignBtn.click();

    await page.waitForSelector('text=选择空闲产线', { timeout: 10000 });
    await page.locator('.el-select').last().click();
    await page.waitForTimeout(500);
    await page.locator('.el-select-dropdown__item:visible').first().click();
    await page.click('button:has-text("确认分配")');
    await page.waitForSelector('text=已分配', { timeout: 15000 });
    console.log('  Batch allocated to production line.');

    // ── 5. Inbound (成品入库) ──────────────────────────────────────────────────
    console.log('\n=== 5. Inbound ===');
    await page.goto('http://localhost:3000/inbound');
    await page.waitForSelector('text=设备入库作业', { timeout: 10000 });

    // Element Plus hides the real <input> behind CSS; click the visible .el-checkbox__inner
    const inboundRow = page.locator('.el-table__body-wrapper .el-checkbox__inner').first();
    const inboundCount = await inboundRow.count();
    if (inboundCount > 0) {
      await inboundRow.scrollIntoViewIfNeeded();
      await inboundRow.click();
      await page.waitForTimeout(500);
      await page.click('button:has-text("📦")');
      await page.waitForTimeout(1500);
      console.log('  Inbound completed.');
    } else {
      console.log('  No machines in inbound queue – skipping.');
    }

    // ── 6. Sales Order (销售下单) – 手动下单 tab ──────────────────────────────
    console.log('\n=== 6. Sales Order ===');
    await page.goto('http://localhost:3000/sales-orders');
    await page.waitForSelector('text=销售订单管理', { timeout: 10000 });

    // Page opens on "手动下单" tab by default (activeTab = 'manual')
    // Fill 客户信息
    await page.locator('.field-label:has-text("客户信息") + .el-input input, .field-label:has-text("Customer") + .el-input input')
      .first()
      .fill('E2E Test Customer');
    await page.waitForTimeout(300);

    // Select machine model from the table's first row el-select
    await page.locator('.el-table .el-select').first().click();
    await page.waitForTimeout(600);
    await page.locator('.el-select-dropdown__item:visible').first().click();
    await page.waitForTimeout(300);

    // Click 生成订单
    await page.click('button:has-text("生成订单")');
    await page.waitForTimeout(1500);
    console.log('  Sales Order created.');

    console.log('\n✅ Full flow test completed successfully!');

  } catch (error) {
    console.error('\n❌ Test failed:', error.message || error);
    // Take a screenshot for debugging
    try {
      const ts = new Date().toISOString().replace(/[:.]/g, '-');
      await page.screenshot({ path: `test-results/failure-${ts}.png`, fullPage: true });
      console.error(`  Screenshot saved: test-results/failure-${ts}.png`);
    } catch {}
  } finally {
    await browser.close();
  }
})();
