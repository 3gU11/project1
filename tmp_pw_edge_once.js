const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');
const ROOT = process.cwd();
const OUT = path.join(ROOT, 'tmp-playwright-output');
if (!fs.existsSync(OUT)) fs.mkdirSync(OUT, { recursive: true });
const RESULT = path.join(OUT, 'edge-flow-result.json');
const PROFILE = path.join(OUT, `edge-profile-${Date.now()}`);
fs.mkdirSync(PROFILE, { recursive: true });
const reqStarts = new Map();
const netEvents = [];
function sleep(ms){ return new Promise(r=>setTimeout(r,ms)); }
function t(start){ return Date.now() - start; }
(async()=>{
  let result = null;
  try {
    const context = await chromium.launchPersistentContext(PROFILE, { channel: 'msedge', headless: true, viewport: { width: 1440, height: 960 }, args: ['--disable-features=msEdgeIdentitySupport'] });
    const page = context.pages()[0] || await context.newPage();
    page.setDefaultTimeout(60000);
    page.setDefaultNavigationTimeout(60000);
    page.on('request', req => reqStarts.set(req, Date.now()));
    page.on('response', res => {
      const req = res.request();
      const started = reqStarts.get(req);
      const url = res.url();
      if (url.includes('/api/v1/')) netEvents.push({ url, method: req.method(), status: res.status(), ms: started ? Date.now()-started : null });
    });
    const metrics = {};
    const d = new Date();
    const batchCode = `${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}PW${String(d.getHours()).padStart(2,'0')}${String(d.getMinutes()).padStart(2,'0')}`;
    d.setDate(d.getDate()+7);
    const inboundDate = d.toISOString().slice(0,10);

    const tLogin = Date.now();
    await page.goto('http://127.0.0.1:8000/login', { waitUntil: 'domcontentloaded' });
    await sleep(500);
    if (page.url().includes('/login')) {
      await page.locator('input[placeholder="请输入账号"]').fill('admin');
      await page.locator('input[type="password"]').first().fill('888');
      await Promise.all([
        page.waitForURL(url => !url.pathname.includes('/login')),
        page.locator('button.submit-btn').first().click(),
      ]);
    }
    metrics.loginMs = t(tLogin);

    const tSandbox = Date.now();
    await page.goto('http://127.0.0.1:8000/prediction-sandbox', { waitUntil: 'domcontentloaded' });
    const predictedCard = page.locator('.batch-card').filter({ hasText: '待确认' }).first();
    await predictedCard.waitFor({ state: 'visible' });
    metrics.openSandboxMs = t(tSandbox);
    const selectedBatchText = await predictedCard.innerText();
    const m = selectedBatchText.match(/BATCH-[A-Z0-9-]+/);
    const selectedBatchId = m ? m[0] : null;

    await predictedCard.locator('.batch-header').click();
    await sleep(300);
    const auditButton = page.locator('button').filter({ hasText: '审核选中列' });
    if (!(await auditButton.isVisible().catch(() => false))) {
      await predictedCard.locator('input[type="checkbox"]').first().check({ force: true });
      await sleep(300);
    }
    await predictedCard.locator('input[placeholder="批次号"]').fill(batchCode);
    const dateInput = predictedCard.locator('input[placeholder="预计入库时间"]');
    await dateInput.fill(inboundDate);
    await dateInput.press('Tab');
    await auditButton.waitFor({ state: 'visible' });

    const tOpenAudit = Date.now();
    await auditButton.click();
    const confirmDialog = page.locator('.el-dialog').filter({ hasText: '最终确认' }).last();
    await confirmDialog.waitFor({ state: 'visible' });
    metrics.openAuditDialogMs = t(tOpenAudit);

    const tAudit = Date.now();
    await Promise.all([
      page.waitForResponse(resp => resp.url().includes('/api/v1/sandbox/batches/') && resp.url().includes('/confirm') && resp.request().method() === 'POST'),
      confirmDialog.locator('button').filter({ hasText: '确认审核' }).click(),
    ]);
    await page.locator('.el-message').filter({ hasText: '审核通过' }).first().waitFor({ state: 'visible' });
    metrics.auditFlowMs = t(tAudit);

    const tKanban = Date.now();
    await page.goto('http://127.0.0.1:8000/production-kanban', { waitUntil: 'domcontentloaded' });
    await page.locator('.queue-title').filter({ hasText: '待排产队列' }).waitFor({ state: 'visible' });
    metrics.openKanbanMs = t(tKanban);

    const queueItem = page.locator('.queue-batch-item').filter({ hasText: batchCode }).first();
    await queueItem.waitFor({ state: 'visible' });

    const tOpenAssign = Date.now();
    await queueItem.locator('button').filter({ hasText: '整批分配' }).click();
    const assignDialog = page.locator('.el-dialog').filter({ hasText: '整批分配' }).last();
    await assignDialog.waitFor({ state: 'visible' });
    metrics.openAssignDialogMs = t(tOpenAssign);
    const selectedLineText = await assignDialog.locator('.el-select input').inputValue().catch(() => '');

    const tAssign = Date.now();
    await Promise.all([
      page.waitForResponse(resp => resp.url().includes('/api/v1/sandbox/production-lines/') && resp.url().includes('/assign') && resp.request().method() === 'POST'),
      assignDialog.locator('button').filter({ hasText: '确认分配' }).click(),
    ]);
    await page.locator('.el-message').filter({ hasText: '批次已分配' }).first().waitFor({ state: 'visible' });
    metrics.assignFlowMs = t(tAssign);

    const screenshot = path.join(OUT, `edge-flow-success-${Date.now()}.png`);
    await page.screenshot({ path: screenshot, fullPage: true });
    result = { ok: true, batchCode, inboundDate, selectedBatchId, selectedLineText, metrics, screenshot, relevantNetwork: netEvents.filter(e => e.url.includes('/confirm') || e.url.includes('/assign') || e.url.includes('/sync-to-plan') || e.url.includes('/import-to-finished-goods') || e.url.includes('/production-lines') || e.url.includes('/sandbox/batches')) };
    await context.close();
  } catch (error) {
    result = { ok: false, error: String(error && error.stack || error), recentNetwork: netEvents.slice(-50) };
  }
  fs.writeFileSync(RESULT, JSON.stringify(result, null, 2), 'utf8');
  console.log(JSON.stringify(result, null, 2));
})();
