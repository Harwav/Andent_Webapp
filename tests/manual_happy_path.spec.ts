import path from 'node:path';
import { test, expect } from '@playwright/test';

const STL_DIR = 'C:/Users/Marcus/Desktop/BM/20260409_Andent_Matt/From 4BL Test Data';
const BASE_URL = 'http://127.0.0.1:8090';

const FILES = [
  '20260407_8425071_NORTH__HAMISH_UnsectionedModel_LowerJaw.stl',
  '20260407_8425071_NORTH__HAMISH_UnsectionedModel_UpperJaw.stl',
  '20260407_8425205_VALE__HARRY_UnsectionedModel_LowerJaw.stl',
  '20260407_8425205_VALE__HARRY_UnsectionedModel_UpperJaw.stl',
  '20260407_10932522__SCDL__C1_T_UnsectionedModel_UpperJaw.stl',
  '20260407_10932522__SCDL__C1_T_Antag.stl',
  '20260407_10932522__SCDL__C1_T_Tooth_25.stl',
  '20260407_10932522__SCDL__C1_T_Tooth_26.stl',
  '20260407_10936293_SCDL_10936293_DD_A3_Antag.stl',
  '20260407_10936293_SCDL_10936293_DD_A3_Tooth_17.stl',
  '20260407_10936293_SCDL_10936293_DD_A3_UnsectionedModel_UpperJaw.stl',
  '20260407_8425256_1300_Smiles_Sandra_UT_A1_OPAQUE_Antag.stl',
  '20260407_8425256_1300_Smiles_Sandra_UT_A1_OPAQUE_Tooth_45.stl',
  '20260407_8425256_1300_Smiles_Sandra_UT_A1_OPAQUE_UnsectionedModel_LowerJaw.stl',
].map(f => path.join(STL_DIR, f));

test.use({
  launchOptions: { slowMo: 600 },
  viewport: { width: 1440, height: 900 },
  baseURL: BASE_URL,
});

test('happy path simulation with 4BL test data', async ({ page }) => {
  test.setTimeout(300_000);

  // ── 1. Landing page ──────────────────────────────────────────────────────
  await page.goto(BASE_URL, { waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);
  await page.screenshot({ path: 'test-results/hp-00-landing.png', fullPage: true });

  const heading = page.getByRole('heading', { name: /Active Queue/i });
  await expect(heading).toBeVisible({ timeout: 10_000 });
  console.log('[1] ✓ Landing page loaded');

  // ── 2. Upload STL files ──────────────────────────────────────────────────
  console.log(`[2] Uploading ${FILES.length} STL files…`);
  const fileInput = page.locator('#file-input');
  await fileInput.setInputFiles(FILES);
  await page.waitForTimeout(2000);
  await page.screenshot({ path: 'test-results/hp-01-after-upload.png', fullPage: true });

  // ── 3. Wait for classification ───────────────────────────────────────────
  console.log('[3] Waiting for classification (up to 90s)…');
  await page.waitForFunction(() => {
    const chips = document.querySelectorAll('[data-testid="status-chip"]');
    if (chips.length === 0) return false;
    return Array.from(chips).every(c => (c as HTMLElement).innerText?.trim() !== 'Processing');
  }, { timeout: 90_000 });
  await page.waitForTimeout(1500);
  await page.screenshot({ path: 'test-results/hp-02-classified.png', fullPage: true });

  const statuses = await page.locator('[data-testid="status-chip"]').allTextContents();
  console.log(`[3] Row statuses: ${statuses.join(', ')}`);

  // ── 4. Inspect any Needs-Review rows ────────────────────────────────────
  const needsReviewRows = page.locator('tr').filter({ has: page.locator('[data-testid="status-chip"]', { hasText: /Review/i }) });
  const reviewCount = await needsReviewRows.count();
  console.log(`[4] Needs-Review rows: ${reviewCount}`);
  if (reviewCount > 0) {
    await page.screenshot({ path: 'test-results/hp-03-needs-review.png', fullPage: true });
    // Inspect the model type dropdown on first review row
    const firstReviewRow = needsReviewRows.first();
    const modelSelect = firstReviewRow.locator('select').first();
    if (await modelSelect.isVisible()) {
      const opts = await modelSelect.locator('option').allTextContents();
      console.log(`[4]   Model type options in review row: ${opts.join(' | ')}`);
    }
  }

  // ── 5. Check preset dropdowns on a Ready row ────────────────────────────
  const readyRows = page.locator('tr').filter({ has: page.locator('[data-testid="status-chip"]', { hasText: 'Ready' }) });
  const readyCount = await readyRows.count();
  console.log(`[5] Ready rows: ${readyCount}`);
  if (readyCount > 0) {
    const firstReady = readyRows.first();
    const presetSel = firstReady.locator('select[data-testid="preset-select"], select[name="preset"]');
    if (await presetSel.isVisible()) {
      const presetOpts = await presetSel.locator('option').allTextContents();
      const selectedPreset = await presetSel.inputValue();
      console.log(`[5]   Preset options: ${presetOpts.join(' | ')} | selected: ${selectedPreset}`);
    }
  }

  // ── 6. Select all Ready rows ─────────────────────────────────────────────
  console.log('[6] Selecting all Ready rows…');
  for (let i = 0; i < readyCount; i++) {
    const cb = readyRows.nth(i).locator('[data-testid="row-select"]');
    if (await cb.isVisible() && !(await cb.isChecked())) {
      await cb.check();
      await page.waitForTimeout(200);
    }
  }
  await page.waitForTimeout(800);
  await page.screenshot({ path: 'test-results/hp-04-selected.png', fullPage: true });

  // ── 7. Read send-to-print button state ──────────────────────────────────
  const sendBtn = page.locator('[data-testid="send-to-print-button"]');
  const sendBtnText = await sendBtn.textContent();
  const sendEnabled = await sendBtn.isEnabled();
  console.log(`[7] Send-to-print: "${sendBtnText?.trim()}" enabled=${sendEnabled}`);

  // ── 8. Send to print ────────────────────────────────────────────────────
  if (readyCount > 0 && sendEnabled) {
    await sendBtn.click();
    await page.waitForTimeout(3000);

    const statusEl = page.locator('#status-text');
    if (await statusEl.isVisible()) {
      console.log(`[8] Status: "${(await statusEl.textContent())?.trim()}"`);
    }
    await page.screenshot({ path: 'test-results/hp-05-sent.png', fullPage: true });
  } else {
    console.log('[8] ✗ Cannot send — button disabled or no ready rows');
    await page.screenshot({ path: 'test-results/hp-05-send-blocked.png', fullPage: true });
  }

  await page.waitForTimeout(2000);

  // ── 9. In Progress tab ───────────────────────────────────────────────────
  const ipTab = page.getByRole('tab', { name: /In Progress/i });
  if (await ipTab.isVisible()) {
    await ipTab.click();
    await page.waitForTimeout(1500);
    const ipRows = await page.locator('tbody tr').count();
    console.log(`[9] In Progress rows: ${ipRows}`);
    await page.screenshot({ path: 'test-results/hp-06-inprogress.png', fullPage: true });
  }

  // ── 10. Print Queue tab ──────────────────────────────────────────────────
  const pqTab = page.getByRole('tab', { name: /Print Queue/i });
  if (await pqTab.isVisible()) {
    await pqTab.click();
    await page.waitForTimeout(2500);
    const pqRows = await page.locator('#print-queue-body tr').count();
    console.log(`[10] Print queue rows: ${pqRows}`);

    if (pqRows > 0) {
      const jobText = await page.locator('#print-queue-body tr').first().textContent();
      console.log(`[10] First job: ${jobText?.replace(/\s+/g, ' ').trim()}`);

      // Try density / hold status
      const holdChips = await page.locator('.hold-chip, [data-testid="hold-chip"], .density-chip').count();
      console.log(`[10] Hold/density chips visible: ${holdChips}`);
    }
    await page.screenshot({ path: 'test-results/hp-07-printqueue.png', fullPage: true });

    // Screenshot button test
    const screenshotBtn = page.locator('.job-screenshot-button').first();
    if (await screenshotBtn.count() > 0) {
      const sBtnText = await screenshotBtn.textContent();
      console.log(`[10] Screenshot btn: "${sBtnText?.trim()}"`);
      if (await screenshotBtn.isEnabled()) {
        await screenshotBtn.click();
        await page.waitForTimeout(4000);
        await page.screenshot({ path: 'test-results/hp-08-screenshot-modal.png', fullPage: true });
        // Dismiss modal
        await page.keyboard.press('Escape');
        await page.waitForTimeout(500);
      }
    }
  }

  // ── 11. History tab ──────────────────────────────────────────────────────
  const histTab = page.getByRole('tab', { name: /History/i });
  if (await histTab.isVisible()) {
    await histTab.click();
    await page.waitForTimeout(1500);
    const histRows = await page.locator('#history-body tr').count();
    console.log(`[11] History rows: ${histRows}`);
    await page.screenshot({ path: 'test-results/hp-09-history.png', fullPage: true });
  }

  // ── 12. Page reload – persistence check ─────────────────────────────────
  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForTimeout(2000);
  const afterReload = await page.locator('[data-testid="status-chip"]').count();
  console.log(`[12] Status chips after reload: ${afterReload} (active queue)`);
  await page.screenshot({ path: 'test-results/hp-10-after-reload.png', fullPage: true });

  console.log('\n✓ Happy path simulation complete.');
});
