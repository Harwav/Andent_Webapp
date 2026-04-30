import path from 'node:path';
import { expect, test } from './helpers/fixtures.js';

test.use({
  launchOptions: { slowMo: 650 },
  viewport: { width: 1440, height: 900 },
});

test('headed operator walkthrough with real Andent test data', async ({ page, liveApp }) => {
  test.setTimeout(300_000);

  const testDataDir = process.env.ANDENT_TEST_DATA_DIR;
  if (!testDataDir) {
    test.skip(true, 'Set ANDENT_TEST_DATA_DIR to the local test data folder to run this test.');
  }
  const upperFile = path.join(testDataDir!, '20260407_8424827_TARUNA__XAVIER_UnsectionedModel_UpperJaw.stl');
  const lowerFile = path.join(testDataDir!, '20260407_8424827_TARUNA__XAVIER_UnsectionedModel_LowerJaw.stl');

  await page.goto(liveApp.baseURL);
  await expect(page.getByRole('heading', { name: 'Active Queue' })).toBeVisible();
  await page.waitForTimeout(1500);

  const debugToggle = page.locator('#preform-dispatch-toggle');
  if (!(await debugToggle.isChecked())) {
    await page.getByText('Virtual printer debug').click();
  }
  await expect(debugToggle).toBeChecked();
  await expect(page.locator('#preform-dispatch-summary')).toContainText('virtual', { ignoreCase: true });
  await page.waitForTimeout(1000);

  await page.locator('#file-input').setInputFiles([upperFile, lowerFile]);

  const upperRow = page.locator('[data-file-name="20260407_8424827_TARUNA__XAVIER_UnsectionedModel_UpperJaw.stl"]');
  const lowerRow = page.locator('[data-file-name="20260407_8424827_TARUNA__XAVIER_UnsectionedModel_LowerJaw.stl"]');
  await expect(upperRow.locator('[data-testid="status-chip"]')).toHaveText('Ready', { timeout: 120_000 });
  await expect(lowerRow.locator('[data-testid="status-chip"]')).toHaveText('Ready', { timeout: 120_000 });
  await page.waitForTimeout(1500);

  await upperRow.locator('[data-testid="row-select"]').check();
  await expect(page.locator('[data-testid="send-to-print-button"]')).toContainText('Send to Print (2)');
  await page.waitForTimeout(1000);
  await page.locator('[data-testid="send-to-print-button"]').click();

  await expect(page.locator('#status-text')).toContainText('Moved 2 file(s) into In Progress', { timeout: 120_000 });
  await page.waitForTimeout(1500);

  await page.getByRole('tab', { name: /History/ }).click();
  await expect(page.locator('#history-body tr').first()).toContainText('8424827', { timeout: 30_000 });
  await page.waitForTimeout(2000);

  await page.getByRole('tab', { name: /Print Queue/ }).click();
  const printJobRow = page.locator('#print-queue-body tr').first();
  await expect(printJobRow).toBeVisible({ timeout: 30_000 });
  await expect(printJobRow).toContainText('260');
  await page.waitForTimeout(2000);

  const screenshotButton = printJobRow.locator('.job-screenshot-button');
  if (await screenshotButton.isEnabled()) {
    await screenshotButton.click();
    await expect(page.locator('#screenshot-modal')).not.toHaveClass(/hidden/);
    await page.waitForTimeout(8000);
  } else {
    await expect(screenshotButton).toContainText(/Generating preview|No Preview/);
    await page.waitForTimeout(8000);
  }
});
