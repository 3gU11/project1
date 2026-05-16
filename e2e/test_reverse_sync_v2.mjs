import { chromium } from 'playwright-core';

async function runTest() {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();
  page.on('console', msg => console.log('BROWSER:', msg.text()));

  console.log('🚀 Starting Deep Reverse Sync Test...');

  // Login
  await page.goto('http://localhost:3000');
  await page.fill('input[placeholder="请输入账号"]', 'boss');
  await page.fill('input[placeholder="请输入密码"]', '888');
  await page.click('button:has-text("登录")');
  await page.waitForSelector('text=当前用户：');

  // Test Machine
  const sn = '96-05-338';
  const unitId = 'BATCH-202605-G-001-04409285-S03';
  const newRemark = 'SyncTest_' + Math.floor(Math.random() * 1000);

  console.log(`Step 1: Updating ${sn} in Main System to "${newRemark}"...`);
  
  const updateRes = await page.evaluate(async ({ sn, remark }) => {
    const authRaw = localStorage.getItem('v7ex_auth') || '{}';
    const token = JSON.parse(authRaw).token;
    const resp = await fetch(`/api/v1/inventory/machine-edit/${sn}`, {
      method: 'PUT',
      headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ note: remark })
    });
    return resp.ok;
  }, { sn, remark: newRemark });

  if (!updateRes) {
    console.error('❌ Failed to update machine in Main System');
    await browser.close();
    return;
  }

  // Check Go
  console.log('Step 2: Checking Go Sandbox via API...');
  await new Promise(r => setTimeout(r, 1000));

  const goData = await page.evaluate(async (id) => {
    const authRaw = localStorage.getItem('v7ex_auth') || '{}';
    const token = JSON.parse(authRaw).token;
    const res = await fetch(`/api/v1/sandbox/units/${id}`, { headers: { 'Authorization': `Bearer ${token}` } });
    return await res.json();
  }, unitId);

  const actualRemark = goData.unit ? goData.unit.order_remark : 'ERROR';
  if (actualRemark === newRemark) {
    console.log(`✅ Success: Remark synced! (Actual: "${actualRemark}")`);
  } else {
    console.error(`❌ Failed: Expected "${newRemark}", but got "${actualRemark}"`);
    console.log('Full unit data:', JSON.stringify(goData.unit, null, 2));
  }

  // Test Case 2: Clearing remark
  console.log('Step 3: Clearing remark in Main System...');
  await page.evaluate(async (sn) => {
    const authRaw = localStorage.getItem('v7ex_auth') || '{}';
    const token = JSON.parse(authRaw).token;
    await fetch(`/api/v1/inventory/machine-edit/${sn}`, {
      method: 'PUT',
      headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ note: '' })
    });
  }, sn);

  await new Promise(r => setTimeout(r, 1000));
  const goDataEmpty = await page.evaluate(async (id) => {
    const authRaw = localStorage.getItem('v7ex_auth') || '{}';
    const token = JSON.parse(authRaw).token;
    const res = await fetch(`/api/v1/sandbox/units/${id}`, { headers: { 'Authorization': `Bearer ${token}` } });
    return await res.json();
  }, unitId);

  const finalRemark = goDataEmpty.unit ? goDataEmpty.unit.order_remark : 'ERROR';
  console.log(`Final remark in Sandbox after clearing in Main System: "${finalRemark}"`);

  await browser.close();
}

runTest().catch(console.error);
