import { chromium } from 'playwright-core';

async function runTest() {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();
  
  console.log('🚀 Starting Kanban Batch Data Test for 96-05-338...');

  // Login
  await page.goto('http://localhost:3000');
  await page.fill('input[placeholder="请输入账号"]', 'boss');
  await page.fill('input[placeholder="请输入密码"]', '888');
  await page.click('button:has-text("登录")');
  await page.waitForSelector('text=当前用户：');

  const sn = '96-05-338';
  const batchId = 'BATCH-202605-G-001-04409285';
  const testRemark = 'FinalVerify_' + Date.now();

  // 1. Update in Main System
  console.log(`Step 1: Setting ${sn} remark to "${testRemark}" in Main System...`);
  await page.evaluate(async ({ sn, remark }) => {
    const authRaw = localStorage.getItem('v7ex_auth') || '{}';
    const token = JSON.parse(authRaw).token;
    await fetch(`/api/v1/inventory/machine-edit/${sn}`, {
      method: 'PUT',
      headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ note: remark })
    });
  }, { sn, remark: testRemark });

  // 2. Fetch Batch Units (This is what Kanban uses)
  console.log(`Step 2: Fetching units for batch ${batchId} from Go API...`);
  await new Promise(r => setTimeout(r, 1000));
  
  const data = await page.evaluate(async (bid) => {
    const authRaw = localStorage.getItem('v7ex_auth') || '{}';
    const token = JSON.parse(authRaw).token;
    const res = await fetch(`/api/v1/sandbox/batches/${bid}/units`, { headers: { 'Authorization': `Bearer ${token}` } });
    return await res.json();
  }, batchId);

  const units = data.units || [];
  const targetUnit = units.find(u => u.forecast_serial_no === sn || u.serial_no === sn);
  
  if (targetUnit) {
    console.log(`Target Unit Found! SN: ${sn}, Remark in API: "${targetUnit.order_remark}"`);
    if (targetUnit.order_remark === testRemark) {
      console.log('✅ BATCH API SYNC SUCCESS!');
    } else {
      console.error(`❌ BATCH API SYNC FAILED! Expected "${testRemark}", but got "${targetUnit.order_remark}"`);
    }
  } else {
    console.error(`❌ Unit ${sn} not found in batch ${batchId}`);
  }

  await browser.close();
}

runTest().catch(console.error);
