import { expect, test } from '@playwright/test';

test('home page boots in Chromium', async ({ page }) => {
  await page.route('/api/preform-setup/status', async (route) => {
    await route.fulfill({
      json: {
        readiness: 'ready',
        install_path: 'managed',
        managed_executable_path: 'managed/PreFormServer.exe',
        detected_version: '3.57.2.624',
        expected_version_min: '3.49.0',
        expected_version_max: null,
        active_configured_source: true,
        is_running: true,
        last_health_check_at: null,
        last_error_code: null,
        last_error_message: null,
      },
    });
  });
  await page.route('/api/print-queue/jobs', async (route) => {
    await route.fulfill({ json: { jobs: [] } });
  });

  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Active Queue' })).toBeVisible();
  await expect(page.locator('#dropzone')).toBeVisible();
  await expect(page.locator('#status-text')).toHaveText('Queue loaded.');
});
