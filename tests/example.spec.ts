import { test, expect } from '@playwright/test';

test('打开百度', async ({ page }) => {
  await page.goto('https://www.baidu.com');
  await expect(page).toHaveTitle(/百度/);
});