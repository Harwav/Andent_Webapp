import path from 'node:path';
import { expect, test } from '@playwright/test';

test('row hooks and preset sync are stable for browser automation', async ({ page }) => {
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

  await page.locator('#file-input').setInputFiles([
    path.resolve('tests/release_gate/fixtures/manual_edit/20260409_CASE555_Tooth_46.stl'),
  ]);

  const row = page.locator('[data-file-name="20260409_CASE555_Tooth_46.stl"][data-row-status="Ready"]');
  await expect(row).toBeVisible();
  await expect(row.locator('[data-testid="status-chip"]')).toHaveText('Ready');

  await row.locator('[data-testid="model-type-select"]').selectOption('Ortho - Solid');
  await expect(row.locator('[data-testid="preset-select"]')).toHaveValue('Ortho Solid - Flat, No Supports');
});
