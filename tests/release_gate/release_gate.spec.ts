import path from 'node:path';
import { expect, test } from './helpers/fixtures.js';

test('straight-through same-case multi-file handoff reaches live PreForm', async ({ page, liveApp, latestPrintJob, sceneStatus }) => {
  const setupStatus = await page.request.get(`${liveApp.baseURL}/api/preform-setup/status`);
  expect(setupStatus.ok()).toBeTruthy();
  expect((await setupStatus.json()).readiness).toBe('ready');

  await page.goto(liveApp.baseURL);
  await page.locator('#file-input').setInputFiles([
    path.resolve('tests/release_gate/fixtures/happy/20260409_CASE123_UnsectionedModel_UpperJaw.stl'),
    path.resolve('tests/release_gate/fixtures/happy/20260409_CASE123_UnsectionedModel_LowerJaw.stl'),
  ]);

  const upperRow = page.locator('[data-file-name="20260409_CASE123_UnsectionedModel_UpperJaw.stl"]');
  const lowerRow = page.locator('[data-file-name="20260409_CASE123_UnsectionedModel_LowerJaw.stl"]');

  await expect(upperRow.locator('[data-testid="status-chip"]')).toHaveText('Ready');
  await expect(lowerRow.locator('[data-testid="status-chip"]')).toHaveText('Ready');

  await upperRow.locator('[data-testid="row-select"]').check();
  await expect(page.locator('[data-testid="send-to-print-button"]')).toContainText('Send to Print (2)');
  await page.locator('[data-testid="send-to-print-button"]').click();
  await expect(page.locator('#status-text')).toContainText('Moved 2 file(s) into In Progress', { timeout: 60000 });

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

  const scene = await sceneStatus(liveApp.preformUrl, job.scene_id);
  expect(scene.scene_id).toBe(job.scene_id);
});
