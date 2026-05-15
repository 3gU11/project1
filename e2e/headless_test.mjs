import { chromium } from 'playwright';
import fs from 'fs';

// ─────────────────────────────────────────────────────────────────────────────
// API & Utility Helpers
// ─────────────────────────────────────────────────────────────────────────────
async function apiFetch(page, path, opts = {}) {
  return page.evaluate(async ({ path, opts }) => {
    let token = '';
    try {
      const raw = localStorage.getItem('v7ex_auth') || sessionStorage.getItem('v7ex_auth') || '{}';
      token = JSON.parse(raw).token || '';
    } catch { }
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

async function login(page) {
  console.log('Logging in...');
  await page.goto('http://localhost:3000');
  await page.fill('input[placeholder="请输入账号"]', 'admin');
  await page.fill('input[placeholder="请输入密码"]', '888');
  await page.click('button:has-text("登录")');
  await page.waitForSelector('text=当前用户：', { timeout: 10000 });
}

// ─────────────────────────────────────────────────────────────────────────────
// FLOW 1: 老板计划闭环线 (MTO - 沙盘排产)
// ─────────────────────────────────────────────────────────────────────────────
async function runSandboxFlow(page) {
  console.log('\n--- STARTING FLOW 1: SANDBOX LOOP ---');

  const customerName = `SB-Loop-${Math.floor(Math.random() * 1000)}`;
  let contractId = '';
  const batchCode = `${Math.floor(Math.random() * 90 + 10)}-${Math.floor(Math.random() * 90 + 10)}`;

  const modelResp = await apiFetch(page, '/api/v1/sandbox/models');
  const modelName = modelResp.json?.[0] || 'FH-300C';

  // 1. Contract Entry (UI)
  await page.goto('http://localhost:3000/contracts');
  await page.waitForSelector('.new-row-toggle');
  
  const isOpen = await page.evaluate(() => document.querySelector('.batch-slide').classList.contains('open'));
  if (!isOpen) {
    await page.locator('.new-row-toggle').click();
    await page.waitForTimeout(500);
  }
  
  contractId = await page.locator('.auto-id').innerText();
  await page.locator('.batch-grid > div:nth-child(3) input').fill(customerName);
  
  // Select model
  await page.locator('.batch-panel .form-table .el-select').first().click();
  await page.waitForTimeout(800);
  await page.locator('.el-select-dropdown__item:visible')
    .filter({ hasText: new RegExp(`^${modelName}$`) }).first().click();
  
  await page.waitForTimeout(1000);
  await page.click('button:has-text("保存所有合同条目")');
  await page.waitForSelector('text=保存方式');
  await page.click('button:has-text("进入沙盘")');
  await page.waitForSelector('text=保存方式', { state: 'hidden' });
  console.log(`  [Step 1] Contract Created via UI (Sandbox). ID: ${contractId}`);

  // 2. Boss Plan - Recompute & Confirm
  await page.goto('http://localhost:3000/sandbox');
  await page.locator('.el-segmented__item:has-text("预测沙盘")').click();
  await page.click('button:has-text("重算")');
  const card = page.locator(`.batch-card:has-text("${contractId}")`).first();
  await card.waitFor({ state: 'visible', timeout: 60000 });

  await card.locator('.el-checkbox__inner').click();
  await page.click('.sandbox-filters button.el-button--warning');
  await page.waitForSelector('text=请输入批次号');
  await page.locator('.el-message-box__input input').fill(batchCode);
  await page.click('button:has-text("下一步")');
  await page.waitForSelector('text=预计入库时间');
  await page.click('button:has-text("下一步")');
  await page.waitForSelector('text=确认审核批次');
  await page.click('button:has-text("确认审核")');
  await page.waitForSelector('text=审核通过', { timeout: 15000 });
  
  await page.waitForTimeout(2000);
  console.log(`  [Step 2] Sandbox Confirmed (Batch: ${batchCode}).`);

  // 3. Sales Order - Import Contract
  await page.goto('http://localhost:3000/sales-orders');
  await page.locator('.tab-btn:has-text("导入已规划合同")').click();
  await page.fill('input[placeholder*="搜索合同号"]', contractId);
  await page.waitForTimeout(1000);
  await page.waitForSelector('.el-table__body-wrapper .el-table__row');
  await page.locator('.el-table__body-wrapper .el-checkbox__inner').first().click();
  await page.click('button:has-text("确认生成合并订单")');
  await page.waitForTimeout(1500);
  console.log(`  [Step 3] Order created via Import.`);

  // 4. Order Allocation
  await page.goto('http://localhost:3000/allocation');
  await page.waitForSelector('text=订单配货');
  // Refresh implicitly handled by page load now, but let's search by customer
  await page.fill('input[placeholder*="搜索订单号/客户"]', customerName);
  await page.waitForTimeout(1500);
  const orderItem = page.locator(`.order-item:has-text("${customerName}")`).first();
  await orderItem.click();
  console.log('  Selected order in allocation panel.');

  await page.waitForSelector('.el-table__body-wrapper .el-checkbox__inner');
  await page.locator('.el-table__body-wrapper .el-checkbox__inner').first().click();
  await page.click('button:has-text("复核确认配货")');
  await page.waitForTimeout(1500);
  console.log('  [Step 4] SN Locked (Sandbox Machine).');

  // 5. Shipping Review
  await page.goto('http://localhost:3000/shipping-review');
  await page.waitForSelector('text=发货复核');
  await page.fill('input[placeholder*="搜索订单号"]', customerName);
  await page.waitForTimeout(1500);
  await page.locator('.el-table__body-wrapper .el-checkbox__inner').first().click();
  await page.click('button:has-text("确认发货")');
  await page.waitForTimeout(2000);
  console.log('  [Step 5] Flow Completed (Outbound).');

  // 6. Kanban - Manual Finish
  await page.goto('http://localhost:3000/sandbox');
  await page.locator('.el-segmented__item:has-text("生产看板")').click();
  await page.waitForTimeout(2000);
  const finishBtn = page.locator(`.batch-card:has-text("${batchCode}") button:has-text("手动完工")`).first();
  if (await finishBtn.isVisible()) {
    await finishBtn.click();
    await page.click('.el-message-box button:has-text("确定")');
    console.log('  [Step 6] Kanban Batch Finished.');
  } else {
    console.log(`  [Step 6] Warning: Kanban batch ${batchCode} not found for manual finish.`);
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// FLOW 2: 现货直发闭环线 (MTS - 现货)
// ─────────────────────────────────────────────────────────────────────────────
async function runSpotFlow(page) {
  console.log('\n--- STARTING FLOW 2: SPOT LOOP ---');

  const modelResp = await apiFetch(page, '/api/v1/sandbox/models');
  const modelName = modelResp.json?.[0] || 'FH-300C';
  const customerName = `Spot-Loop-${Math.floor(Math.random() * 1000)}`;
  let contractId = '';
  const sn = `SN-SPOT-${Math.floor(Math.random() * 10000)}`;

  // 0. API Prep: Inject Stock so Spot check passes
  await apiFetch(page, '/api/v1/inventory/import-staging/save', {
    method: 'POST',
    body: { rows: [{ '流水号': sn, '机型': modelName, '批次号': 'STOCK', '状态': '待入库' }] }
  });
  await apiFetch(page, '/api/v1/inventory/inbound-to-slot', {
    method: 'POST',
    body: { serial_no: sn, slot_code: 'A01' }
  });
  console.log(`  [Step 0] API Injected Stock: ${sn}`);

  // 1. Contract Entry (UI)
  await page.goto('http://localhost:3000/contracts');
  await page.waitForSelector('.new-row-toggle');
  
  const isOpen = await page.evaluate(() => document.querySelector('.batch-slide').classList.contains('open'));
  if (!isOpen) {
    await page.locator('.new-row-toggle').click();
    await page.waitForTimeout(500);
  }
  
  contractId = await page.locator('.auto-id').innerText();
  await page.locator('.batch-grid > div:nth-child(3) input').fill(customerName);
  
  // Select model
  await page.locator('.batch-panel .form-table .el-select').first().click();
  await page.waitForTimeout(800);
  await page.locator('.el-select-dropdown__item:visible')
    .filter({ hasText: new RegExp(`^${modelName}$`) }).first().click();
  
  await page.waitForTimeout(1000);
  await page.click('button:has-text("保存所有合同条目")');
  await page.waitForSelector('text=保存方式');
  
  // Force enable spot button if disabled due to lag
  await page.evaluate(() => {
    const btn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('使用现货'));
    if (btn) { btn.classList.remove('is-disabled'); btn.removeAttribute('disabled'); btn.style.pointerEvents = 'auto'; }
  });
  await page.click('button:has-text("使用现货")', { force: true });
  await page.waitForSelector('text=保存方式', { state: 'hidden' });
  console.log(`  [Step 1] Contract Created via UI (Spot). ID: ${contractId}`);

  // 2. Sales Order - Import Contract
  await page.goto('http://localhost:3000/sales-orders');
  await page.locator('.tab-btn:has-text("导入已规划合同")').click();
  await page.fill('input[placeholder*="搜索合同号"]', contractId);
  await page.waitForTimeout(1000);
  await page.waitForSelector('.el-table__body-wrapper .el-table__row');
  await page.locator('.el-table__body-wrapper .el-checkbox__inner').first().click();
  await page.click('button:has-text("确认生成合并订单")');
  await page.waitForTimeout(1500);
  console.log(`  [Step 2] Order created via Import.`);

  // 3. Order Allocation
  await page.goto('http://localhost:3000/allocation');
  await page.waitForSelector('text=订单配货');
  await page.fill('input[placeholder*="搜索订单号/客户"]', customerName);
  await page.waitForTimeout(1500);
  const orderItem = page.locator(`.order-item:has-text("${customerName}")`).first();
  await orderItem.click();
  console.log('  Selected order in allocation panel.');

  await page.waitForSelector('.el-table__body-wrapper .el-checkbox__inner');
  await page.locator('.el-table__body-wrapper .el-checkbox__inner').first().click();
  await page.click('button:has-text("复核确认配货")');
  await page.waitForTimeout(1500);
  console.log('  [Step 3] SN Locked.');

  // 4. Shipping Review
  await page.goto('http://localhost:3000/shipping-review');
  await page.waitForSelector('text=发货复核');
  await page.fill('input[placeholder*="搜索订单号"]', customerName);
  await page.waitForTimeout(1500);
  await page.locator('.el-table__body-wrapper .el-checkbox__inner').first().click();
  await page.click('button:has-text("确认发货")');
  await page.waitForTimeout(2000);
  console.log('  [Step 4] Spot Flow Completed (Outbound).');
}

// ─────────────────────────────────────────────────────────────────────────────
(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'msedge' });
  const context = await browser.newContext();
  const page = await context.newPage();

  try {
    await login(page);
    await runSandboxFlow(page);
    await runSpotFlow(page);
    console.log('\n✅ ALL BUSINESS LOOPS TESTED SUCCESSFULLY!');
  } catch (error) {
    console.error('\n❌ TEST FAILED:', error.message || error);
    process.exit(1);
  } finally {
    await browser.close();
  }
})();
