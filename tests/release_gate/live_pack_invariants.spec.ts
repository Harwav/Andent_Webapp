import fs from 'node:fs/promises';
import path from 'node:path';
import { expect, test } from './helpers/fixtures.js';
import { uploadStlFolder, waitForClassificationToSettle } from './helpers/page.js';

type PreFormDevice = Record<string, unknown>;

function virtualDeviceKeys(devicesPayload: unknown): Set<string> {
  const devices = Array.isArray(devicesPayload)
    ? devicesPayload
    : Array.isArray((devicesPayload as { devices?: unknown[] })?.devices)
      ? (devicesPayload as { devices: unknown[] }).devices
      : [];
  const keys = new Set<string>();
  for (const device of devices as PreFormDevice[]) {
    const haystack = `${device.connection_type ?? ''} ${device.status ?? ''} ${device.firmware_version ?? ''}`.toLowerCase();
    if (!haystack.includes('virtual')) {
      continue;
    }
    for (const key of ['id', 'device_id', 'name', 'device_name', 'product_name']) {
      const value = device[key];
      if (value) {
        keys.add(String(value).toLowerCase());
      }
    }
  }
  return keys;
}

function targetLooksVirtual(job: any, virtualKeys: Set<string>): boolean {
  const id = String(job.printer_device_id ?? '').toLowerCase();
  const name = String(job.printer_device_name ?? '').toLowerCase();
  const target = `${id} ${name}`;
  if (target.includes('virtual') || target.includes('debug')) {
    return true;
  }
  return virtualKeys.has(id) || virtualKeys.has(name);
}

test('canonical dataset virtual dispatch records manifests and avoids physical dispatch', async ({ page, liveApp, printJobSummary, queueSummary, sceneStatus }) => {
  test.setTimeout(600_000);

  const datasetDir = process.env.FORMFLOW_RELEASE_TEST_DATA_DIR;
  const evidenceDir = process.env.FORMFLOW_RELEASE_EVIDENCE_DIR ?? 'test-results/release-gate';
  if (!datasetDir) {
    throw new Error('FORMFLOW_RELEASE_TEST_DATA_DIR must point at the canonical release dataset.');
  }

  await page.goto(liveApp.baseURL);
  const uploadedNames = await uploadStlFolder(page, datasetDir);
  await waitForClassificationToSettle(page, 1);
  await expect.poll(async () => {
    const summary = await queueSummary(liveApp.databasePath);
    return summary.rows
      .filter((row: any) => row.status === 'Ready')
      .reduce((total: number, row: any) => total + row.count, 0);
  }, { timeout: 240_000 }).toBe(uploadedNames.length);
  await page.reload({ waitUntil: 'networkidle' });

  const readyRows = page.locator('#active-body tr').filter({
    has: page.locator('[data-testid="status-chip"]', { hasText: 'Ready' }),
  });
  const readyCount = await readyRows.count();
  expect(readyCount).toBeGreaterThan(0);

  await readyRows.first().locator('[data-testid="row-select"]').check();
  await page.locator('[data-testid="bulk-printer-select"]').selectOption({ label: 'Form 4BL (Form 4BL, Virtual Printer)' });
  await expect(page.locator('[data-testid="send-to-print-button"]')).toBeEnabled({ timeout: 30_000 });
  await page.locator('[data-testid="send-to-print-button"]').click();
  await expect(page.locator('#status-text')).toContainText(/Moved|Submitted|Holding/i, { timeout: 180_000 });

  const summary = await printJobSummary(liveApp.databasePath);
  await fs.mkdir(evidenceDir, { recursive: true });
  await fs.writeFile(path.join(evidenceDir, 'print-job-evidence.json'), JSON.stringify(summary, null, 2), 'utf8');

  expect(summary.jobs.length).toBeGreaterThan(0);

  const devicesResponse = await page.request.get(`${liveApp.preformUrl}/devices/`);
  expect(devicesResponse.ok()).toBeTruthy();
  const virtualKeys = virtualDeviceKeys(await devicesResponse.json());
  expect(virtualKeys.size).toBeGreaterThan(0);

  const physicalIndicators = summary.jobs.filter((job: any) => !targetLooksVirtual(job, virtualKeys));
  expect(physicalIndicators).toEqual([]);

  const firstJobWithScene = summary.jobs.find((job: any) => job.scene_id);
  expect(firstJobWithScene).toBeTruthy();
  const scene = await sceneStatus(liveApp.preformUrl, firstJobWithScene.scene_id);
  await fs.writeFile(path.join(evidenceDir, 'preform-scene-evidence.json'), JSON.stringify(scene, null, 2), 'utf8');
  expect(scene.scene_id).toBe(firstJobWithScene.scene_id);

  const heldByCompatibility = new Map<string, number>();
  for (const job of summary.jobs) {
    if (job.status === 'Holding for More Cases') {
      heldByCompatibility.set(job.compatibility_key, (heldByCompatibility.get(job.compatibility_key) ?? 0) + 1);
    }
    expect(job.manifest.case_ids?.length ?? job.case_ids.length).toBeGreaterThan(0);
  }
  for (const count of heldByCompatibility.values()) {
    expect(count).toBeLessThanOrEqual(1);
  }

  await fs.writeFile(path.join(evidenceDir, 'no-physical-dispatch.json'), JSON.stringify({
    pass: physicalIndicators.length === 0,
    checked_jobs: summary.jobs.length,
    virtual_targets: Array.from(virtualKeys).sort(),
  }, null, 2), 'utf8');
});
