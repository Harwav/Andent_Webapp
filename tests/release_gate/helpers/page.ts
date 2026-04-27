import { expect, type Page } from '@playwright/test';

export async function waitForRowReady(page: Page, fileName: string): Promise<void> {
  const row = page.locator(`[data-file-name="${fileName}"]`);
  await expect(row).toBeVisible();
  await expect(row.locator('[data-testid="status-chip"]')).toHaveText('Ready');
}
