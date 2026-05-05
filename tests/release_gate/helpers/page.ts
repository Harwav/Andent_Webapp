import path from 'node:path';
import { expect, type Page } from '@playwright/test';

export async function waitForRowReady(page: Page, fileName: string): Promise<void> {
  const row = page.locator(`[data-file-name="${fileName}"]`);
  await expect(row).toBeVisible();
  await expect(row.locator('[data-testid="status-chip"]')).toHaveText('Ready');
}

export async function uploadStlFolder(page: Page, folderPath: string): Promise<string[]> {
  const fs = await import('node:fs/promises');
  const entries = await fs.readdir(folderPath);
  const files = entries
    .filter((entry) => entry.toLowerCase().endsWith('.stl'))
    .sort((a, b) => a.localeCompare(b))
    .map((entry) => path.join(folderPath, entry));
  if (files.length === 0) {
    throw new Error(`No STL files found in ${folderPath}`);
  }
  await page.locator('#file-input').setInputFiles(files);
  return files.map((file) => path.basename(file));
}

export async function waitForClassificationToSettle(page: Page, expectedMinimumRows: number): Promise<void> {
  await expect(page.locator('[data-testid="status-chip"]').first()).toBeVisible({ timeout: 120_000 });
  await page.waitForFunction(
    ({ minimumRows }) => {
      const chips = Array.from(document.querySelectorAll('[data-testid="status-chip"]'));
      if (chips.length < minimumRows) return false;
      return chips.every((chip) => !/Processing|Analyzing/i.test((chip as HTMLElement).innerText));
    },
    { minimumRows: expectedMinimumRows },
    { timeout: 180_000 },
  );
}

export async function writeClassificationSummary(page: Page, outputPath: string): Promise<void> {
  const fs = await import('node:fs/promises');
  const statuses = await page.locator('[data-testid="status-chip"]').allTextContents();
  const counts = statuses.reduce<Record<string, number>>((acc, status) => {
    const key = status.trim() || 'Unknown';
    acc[key] = (acc[key] ?? 0) + 1;
    return acc;
  }, {});
  await fs.mkdir(path.dirname(outputPath), { recursive: true });
  await fs.writeFile(outputPath, JSON.stringify({ counts, total: statuses.length }, null, 2), 'utf8');
}
