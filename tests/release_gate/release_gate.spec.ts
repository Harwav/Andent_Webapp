import path from 'node:path';

import { expect, test } from './helpers/fixtures.js';
import { dismissSetupWizardIfPresent, waitForRowReady } from './helpers/page.js';

function manifestSummary(job: any): Record<string, unknown> {
  const importGroups = job.manifest_json?.import_groups ?? [];
  const fileCount = importGroups.reduce(
    (total: number, group: any) => total + (group.files?.length ?? 0),
    0,
  );
  return {
    job_name: job.job_name,
    scene_id: job.scene_id,
    print_job_id: job.print_job_id,
    case_ids: job.case_ids,
    preset_names: job.preset_names,
    compatibility_key: job.compatibility_key,
    import_group_count: importGroups.length,
    file_count: fileCount,
  };
}

test('straight-through same-case multi-file handoff reaches live PreForm', async ({ page, liveApp, latestPrintJob, sceneStatus }) => {
  await page.goto(`${liveApp.baseURL}/`);
  await expect(page.locator('#dropzone')).toBeVisible();
  await page.locator('#file-input').setInputFiles([
    path.resolve('tests/release_gate/fixtures/happy/20260409_CASE123_UnsectionedModel_UpperJaw.stl'),
    path.resolve('tests/release_gate/fixtures/happy/20260409_CASE123_UnsectionedModel_LowerJaw.stl'),
  ]);

  await waitForRowReady(page, '20260409_CASE123_UnsectionedModel_UpperJaw.stl');
  await waitForRowReady(page, '20260409_CASE123_UnsectionedModel_LowerJaw.stl');
  await dismissSetupWizardIfPresent(page);

  const upperRow = page.locator('[data-file-name="20260409_CASE123_UnsectionedModel_UpperJaw.stl"]');
  await upperRow.locator('[data-testid="row-select"]').check();
  await page.locator('[data-testid="send-to-print-button"]').click();
  await expect(page.locator('#status-text')).toContainText('Moved 2 row(s) into Processed as Submitted.');

  const job = await latestPrintJob(liveApp.databasePath);
  expect(job.case_ids).toContain('CASE123');
  expect(job.preset_names).toContain('Ortho Solid - Flat, No Supports');
  expect(job.compatibility_key).toBeTruthy();
  expect(job.manifest_json.case_ids).toContain('CASE123');
  expect(job.manifest_json.planning_status).toBe('planned');
  expect(job.manifest_json.import_groups.length).toBeGreaterThan(0);
  const manifestFiles = job.manifest_json.import_groups.flatMap((group: any) => group.files);
  expect(manifestFiles.map((file: any) => file.file_name)).toEqual(expect.arrayContaining([
    '20260409_CASE123_UnsectionedModel_UpperJaw.stl',
    '20260409_CASE123_UnsectionedModel_LowerJaw.stl',
  ]));
  expect(manifestFiles.every((file: any) => Boolean(file.preform_hint))).toBe(true);
  console.log(`[release-gate-manifest] ${JSON.stringify(manifestSummary(job))}`);

  const scene = await sceneStatus(liveApp.preformUrl, job.scene_id);
  expect(scene.scene_id).toBe(job.scene_id);
});

test('manual model and preset edits still hand off to live PreForm', async ({ page, liveApp, latestPrintJob, sceneStatus }) => {
  await page.goto(`${liveApp.baseURL}/`);
  await expect(page.locator('#dropzone')).toBeVisible();
  await page.locator('#file-input').setInputFiles([
    path.resolve('tests/release_gate/fixtures/manual_edit/20260409_CASE555_Tooth_46.stl'),
  ]);

  await waitForRowReady(page, '20260409_CASE555_Tooth_46.stl');
  await dismissSetupWizardIfPresent(page);
  const row = page.locator('[data-file-name="20260409_CASE555_Tooth_46.stl"]');

  await row.locator('[data-testid="model-type-select"]').selectOption('Ortho - Solid');
  await row.locator('[data-testid="preset-select"]').selectOption('Splint - Flat, No Supports');
  await expect(row.locator('[data-testid="status-chip"]')).toHaveText('Ready');

  await row.locator('[data-testid="row-select"]').check();
  await page.locator('[data-testid="send-to-print-button"]').click();
  await expect(page.locator('#status-text')).toContainText('Moved 1 row(s) into Processed as Submitted.');

  const job = await latestPrintJob(liveApp.databasePath);
  expect(job.case_ids).toContain('CASE555');
  expect(job.preset).toBe('Splint - Flat, No Supports');
  expect(job.preset_names).toContain('Splint - Flat, No Supports');
  expect(job.manifest_json.case_ids).toContain('CASE555');
  const splintGroup = job.manifest_json.import_groups.find(
    (group: any) => group.preset_name === 'Splint - Flat, No Supports',
  );
  expect(splintGroup).toBeTruthy();
  expect(splintGroup?.preform_hint).toBe('splint_v1');
  expect(splintGroup?.files[0].preform_hint).toBe('splint_v1');
  console.log(`[release-gate-manifest] ${JSON.stringify(manifestSummary(job))}`);

  const scene = await sceneStatus(liveApp.preformUrl, job.scene_id);
  expect(scene.scene_id).toBe(job.scene_id);
});

test('ambiguous case stays blocked in Active and cannot be sent', async ({ page, liveApp }) => {
  await page.goto(`${liveApp.baseURL}/`);
  await expect(page.locator('#dropzone')).toBeVisible();
  await dismissSetupWizardIfPresent(page);
  await page.locator('#file-input').setInputFiles([
    path.resolve('tests/release_gate/fixtures/ambiguous/Julie_UpperJaw.stl'),
  ]);

  const row = page.locator('[data-file-name="Julie_UpperJaw.stl"]');
  await expect(row).toBeVisible();
  await expect(row.locator('[data-testid="status-chip"]')).toHaveText('Needs Review');
  await expect(page.locator('[data-testid="send-to-print-button"]')).toHaveCount(0);
});

test('dead-port PreForm configuration stays blocked behind setup gating', async ({ page, deadApp }) => {
  await page.goto(`${deadApp.baseURL}/`);
  await expect(page.locator('#dropzone')).toBeVisible();
  await dismissSetupWizardIfPresent(page);
  await page.locator('#file-input').setInputFiles([
    path.resolve('tests/release_gate/fixtures/happy/20260409_CASE123_UnsectionedModel_UpperJaw.stl'),
  ]);

  await waitForRowReady(page, '20260409_CASE123_UnsectionedModel_UpperJaw.stl');
  await dismissSetupWizardIfPresent(page);
  const row = page.locator('[data-file-name="20260409_CASE123_UnsectionedModel_UpperJaw.stl"]');
  await row.locator('[data-testid="row-select"]').check();

  const button = page.locator('[data-testid="send-to-print-button"]');
  await expect(button).toHaveText(/Setup Required/);
  await button.click();
  await expect(page.locator('#preform-wizard')).toBeVisible();
  await expect(page.locator('#preform-summary')).toContainText('local API is not reachable');
});
