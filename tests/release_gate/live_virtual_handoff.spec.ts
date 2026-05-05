import fs from 'node:fs/promises';
import path from 'node:path';
import { expect, test } from './helpers/fixtures.js';
import {
  uploadStlFolder,
  waitForClassificationToSettle,
} from './helpers/page.js';

test('canonical dataset uploads, classifies, and persists in live browser app', async ({ page, liveApp, queueSummary }) => {
  test.setTimeout(300_000);

  const datasetDir = process.env.FORMFLOW_RELEASE_TEST_DATA_DIR;
  const evidenceDir = process.env.FORMFLOW_RELEASE_EVIDENCE_DIR ?? 'test-results/release-gate';
  if (!datasetDir) {
    throw new Error('FORMFLOW_RELEASE_TEST_DATA_DIR must point at the canonical release dataset.');
  }

  await page.goto(liveApp.baseURL);
  await expect(page.getByRole('heading', { name: 'Active Queue' })).toBeVisible();

  const uploadedNames = await uploadStlFolder(page, datasetDir);
  await waitForClassificationToSettle(page, 1);

  await expect.poll(async () => {
    const summary = await queueSummary(liveApp.databasePath);
    return summary.rows.reduce((total: number, row: any) => total + row.count, 0);
  }, { timeout: 120_000 }).toBe(uploadedNames.length);

  const summary = await queueSummary(liveApp.databasePath);
  await fs.mkdir(evidenceDir, { recursive: true });
  await fs.writeFile(
    path.join(evidenceDir, 'classification-summary.json'),
    JSON.stringify(summary, null, 2),
    'utf8',
  );
  const totalRows = summary.rows.reduce((total: number, row: any) => total + row.count, 0);
  expect(totalRows).toBe(uploadedNames.length);

  await page.reload({ waitUntil: 'networkidle' });
  await expect(page.locator('[data-testid="status-chip"]').first()).toBeVisible({ timeout: 30_000 });
});
