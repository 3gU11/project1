import { chromium } from 'playwright-core';

async function run() {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();
  
  await page.goto('http://localhost:3000');
  await page.fill('input[placeholder="请输入账号"]', 'boss');
  await page.fill('input[placeholder="请输入密码"]', '888');
  await page.click('button:has-text("登录")');
  await page.waitForSelector('text=当前用户：');
  
  const unitId = 'BATCH-202605-G-001-04409285-S03';
  const data = await page.evaluate(async (id) => {
    const authRaw = localStorage.getItem('v7ex_auth') || '{}';
    const token = JSON.parse(authRaw).token;
    const res = await fetch(`/api/v1/sandbox/units/${id}`, { headers: { 'Authorization': `Bearer ${token}` } });
    return await res.json();
  }, unitId);
  
  console.log('Unit Detail:', JSON.stringify(data, null, 2));
  await browser.close();
}

run().catch(console.error);
