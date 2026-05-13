import { chromium } from 'playwright-core';

(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const page = await browser.newPage();
  
  await page.goto('http://localhost:3000');
  await page.fill('input[placeholder="请输入账号"]', 'boss');
  await page.fill('input[placeholder="请输入密码"]', '888');
  await page.click('button:has-text("登录")');
  await page.waitForSelector('text=当前用户：');

  const invResp = await page.evaluate(async () => {
    const raw = localStorage.getItem('v7ex_auth') || '{}';
    const token = JSON.parse(raw).token || '';
    const res = await fetch('/api/v1/inventory/');
    return await res.json();
  });

  console.log('--- Inventory Data ---');
  const stock = Array.isArray(invResp) ? invResp : (invResp.data || []);
  console.log(JSON.stringify(stock.slice(0, 10), null, 2));
  
  const statusCounts = {};
  stock.forEach(s => {
    const status = s['状态'] || 'Unknown';
    statusCounts[status] = (statusCounts[status] || 0) + 1;
  });
  console.log('\n--- Status Counts ---');
  console.log(statusCounts);

  await browser.close();
})();
