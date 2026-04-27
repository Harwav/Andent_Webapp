import { expect, test } from '@playwright/test';

type QueueRow = {
  row_id: number;
  file_name: string;
  case_id: string;
  model_type: string;
  preset: string;
  confidence: string;
  status: string;
  dimensions: null;
  volume_ml: null;
  structure: null;
  structure_confidence: null;
  structure_reason: null;
  structure_metrics: null;
  structure_locked: boolean;
  review_required: boolean;
  review_reason: null;
  current_event_at: null;
  created_at: null;
  printer: null;
  person: null;
  thumbnail_url: null;
  file_url: null;
};

function makeRow(rowId: number, status: string): QueueRow {
  return {
    row_id: rowId,
    file_name: `CASE${rowId}_UpperJaw.stl`,
    case_id: `CASE${rowId}`,
    model_type: 'Ortho - Solid',
    preset: 'Ortho Solid - Flat, No Supports',
    confidence: 'high',
    status,
    dimensions: null,
    volume_ml: null,
    structure: null,
    structure_confidence: null,
    structure_reason: null,
    structure_metrics: null,
    structure_locked: false,
    review_required: false,
    review_reason: null,
    current_event_at: null,
    created_at: null,
    printer: null,
    person: null,
    thumbnail_url: null,
    file_url: null,
  };
}

test('bulk dropdowns are inline self-applying controls', async ({ page }) => {
  const rows = [makeRow(1, 'Ready'), makeRow(2, 'Ready')];
  const bulkUpdates: unknown[] = [];

  await page.route('/api/uploads/queue', async (route) => {
    await route.fulfill({ json: { active_rows: rows, processed_rows: [] } });
  });
  await page.route('/api/print-queue/jobs', async (route) => {
    await route.fulfill({ json: { jobs: [] } });
  });
  await page.route('/api/preform-setup/status', async (route) => {
    await route.fulfill({
      json: {
        readiness: 'ready',
        install_path: 'managed',
        managed_executable_path: 'managed/PreFormServer.exe',
        detected_version: '3.57.2.624',
        expected_version_min: '3.57.0',
        expected_version_max: null,
        last_health_check_at: null,
        last_error_code: null,
        last_error_message: null,
      },
    });
  });
  await page.route('/api/uploads/rows/bulk-update', async (route) => {
    bulkUpdates.push(route.request().postDataJSON());
    await route.fulfill({ json: rows });
  });

  await page.goto('/');
  await page.locator('[data-testid="row-select"]').first().check();

  await expect(page.getByRole('button', { name: 'Change Model Type' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Change Preset' })).toHaveCount(0);

  const modelSelect = page.getByLabel('Change Model Type');
  const presetSelect = page.getByLabel('Change Preset');
  const printerSelect = page.getByLabel('Change Printer');
  await expect(modelSelect).toBeVisible();
  await expect(presetSelect).toBeVisible();
  await expect(printerSelect).toBeVisible();

  const deleteTop = await page.getByRole('button', { name: 'Delete (1)' }).evaluate((el) => el.getBoundingClientRect().top);
  const modelTop = await modelSelect.evaluate((el) => el.getBoundingClientRect().top);
  const presetTop = await presetSelect.evaluate((el) => el.getBoundingClientRect().top);
  const printerTop = await printerSelect.evaluate((el) => el.getBoundingClientRect().top);
  expect(Math.abs(modelTop - deleteTop)).toBeLessThan(6);
  expect(Math.abs(presetTop - deleteTop)).toBeLessThan(6);
  expect(Math.abs(printerTop - deleteTop)).toBeLessThan(6);

  await modelSelect.selectOption('Splint');
  await expect.poll(() => bulkUpdates.length).toBe(1);
  expect(bulkUpdates[0]).toEqual({ row_ids: [1], model_type: 'Splint' });

  await presetSelect.selectOption('Splint - Flat, No Supports');
  await expect.poll(() => bulkUpdates.length).toBe(2);
  expect(bulkUpdates[1]).toEqual({ row_ids: [1], preset: 'Splint - Flat, No Supports' });

  await printerSelect.selectOption('Form 4B');
  await expect.poll(() => bulkUpdates.length).toBe(3);
  expect(bulkUpdates[2]).toEqual({ row_ids: [1], printer: 'Form 4B' });
});

test('bulk duplicate approval and print submission post selected ready rows', async ({ page }) => {
  const rows = [makeRow(1, 'Duplicate'), makeRow(2, 'Ready'), makeRow(3, 'Ready')];
  const posts: Record<string, unknown[]> = {
    duplicates: [],
    print: [],
  };

  await page.route('/api/uploads/queue', async (route) => {
    await route.fulfill({ json: { active_rows: rows, processed_rows: [] } });
  });
  await page.route('/api/print-queue/jobs', async (route) => {
    await route.fulfill({ json: { jobs: [] } });
  });
  await page.route('/api/preform-setup/status', async (route) => {
    await route.fulfill({
      json: {
        readiness: 'ready',
        install_path: 'managed',
        managed_executable_path: 'managed/PreFormServer.exe',
        detected_version: '3.57.2.624',
        expected_version_min: '3.57.0',
        expected_version_max: null,
        last_health_check_at: null,
        last_error_code: null,
        last_error_message: null,
      },
    });
  });
  await page.route('/api/uploads/rows/allow-duplicate', async (route) => {
    posts.duplicates.push(route.request().postDataJSON());
    rows[0].status = 'Ready';
    await route.fulfill({ json: [rows[0]] });
  });
  await page.route('/api/uploads/rows/send-to-print', async (route) => {
    posts.print.push(route.request().postDataJSON());
    await route.fulfill({ json: rows });
  });

  await page.goto('/');
  for (const checkbox of await page.locator('[data-testid="row-select"]').all()) {
    await checkbox.check();
  }

  await page.getByRole('button', { name: 'Allow Duplicate (1)' }).click();
  await expect.poll(() => posts.duplicates.length).toBe(1);
  expect(posts.duplicates[0]).toEqual({ row_ids: [1] });

  await page.getByRole('button', { name: 'Send to Print (3)' }).click();
  await expect.poll(() => posts.print.length).toBe(1);
  expect(posts.print[0]).toEqual({ row_ids: [1, 2, 3] });
});
