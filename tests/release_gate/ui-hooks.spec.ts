import path from 'node:path';

import { expect, test } from '@playwright/test';

test('row hooks and preset sync are stable for browser automation', async ({ page }) => {
  await page.goto('/');

  await page.locator('#file-input').setInputFiles([
    path.resolve('tests/release_gate/fixtures/manual_edit/20260409_CASE555_Tooth_46.stl'),
  ]);

  const row = page.locator('[data-file-name="20260409_CASE555_Tooth_46.stl"]');
  await expect(row).toBeVisible();
  await expect(row.locator('[data-testid="status-chip"]')).toHaveText('Ready');

  await row.locator('[data-testid="model-type-select"]').selectOption('Ortho - Solid');
  await expect(row.locator('[data-testid="preset-select"]')).toHaveValue('Ortho Solid - Flat, No Supports');
});
