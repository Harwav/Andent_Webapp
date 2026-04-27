import { expect, test } from '@playwright/test';

test('home page boots in Chromium', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Active Queue' })).toBeVisible();
  await expect(page.locator('#dropzone')).toBeVisible();
  await expect(page.locator('#status-text')).toHaveText('Queue loaded.');
});
