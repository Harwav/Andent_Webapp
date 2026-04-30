/**
 * Manual happy-path simulation for issue discovery.
 * Uploads a representative batch of STLs from the 4BL test data folder,
 * observes classification, edits a row, sends to print, and inspects the
 * print queue — all at human speed so issues are visible.
 *
 * Run: npx ts-node --esm tests/manual_happy_path.ts
 *   OR: npx playwright test tests/manual_happy_path.ts --headed --project=chromium
 */
import path from 'node:path';
import { chromium } from '@playwright/test';

const STL_DIR = 'C:/Users/Marcus/Desktop/BM/20260409_Andent_Matt/From 4BL Test Data';
const BASE_URL = 'http://127.0.0.1:8090';
const SLOW_MO = 600; // ms between actions – human pacing

// A representative cross-section: 2 cases with upper+lower, 1 die/tooth case, 1 antag-only
const FILES = [
  // Case 8425071 – upper + lower (Ortho-Solid pair)
  '20260407_8425071_NORTH__HAMISH_UnsectionedModel_LowerJaw.stl',
  '20260407_8425071_NORTH__HAMISH_UnsectionedModel_UpperJaw.stl',
  // Case 8425205 – upper + lower
  '20260407_8425205_VALE__HARRY_UnsectionedModel_LowerJaw.stl',
  '20260407_8425205_VALE__HARRY_UnsectionedModel_UpperJaw.stl',
  // Case 10932522 – full case: upper + antag + two teeth
  '20260407_10932522__SCDL__C1_T_UnsectionedModel_UpperJaw.stl',
  '20260407_10932522__SCDL__C1_T_Antag.stl',
  '20260407_10932522__SCDL__C1_T_Tooth_25.stl',
  '20260407_10932522__SCDL__C1_T_Tooth_26.stl',
  // Case 10936293 – Die+tooth case (DD_A3)
  '20260407_10936293_SCDL_10936293_DD_A3_Antag.stl',
  '20260407_10936293_SCDL_10936293_DD_A3_Tooth_17.stl',
  '20260407_10936293_SCDL_10936293_DD_A3_UnsectionedModel_UpperJaw.stl',
  // Case 8425256 – OPAQUE variant
  '20260407_8425256_1300_Smiles_Sandra_UT_A1_OPAQUE_Antag.stl',
  '20260407_8425256_1300_Smiles_Sandra_UT_A1_OPAQUE_Tooth_45.stl',
  '20260407_8425256_1300_Smiles_Sandra_UT_A1_OPAQUE_UnsectionedModel_LowerJaw.stl',
].map(f => path.join(STL_DIR, f));

(async () => {
  const browser = await chromium.launch({ headless: false, slowMo: SLOW_MO });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();

  console.log('[1] Navigating to app…');
  await page.goto(BASE_URL, { waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);

  // ── Step 1: Verify landing page ──────────────────────────────────────────
  const heading = page.getByRole('heading', { name: /Active Queue/i });
  if (await heading.isVisible()) {
    console.log('[1] ✓ Landing page loaded — Active Queue heading visible');
  } else {
    console.log('[1] ✗ Active Queue heading NOT found — taking screenshot');
    await page.screenshot({ path: 'test-results/issue-landing.png', fullPage: true });
  }

  // ── Step 2: Upload STL files ─────────────────────────────────────────────
  console.log(`[2] Uploading ${FILES.length} STL files…`);
  const fileInput = page.locator('#file-input');
  await fileInput.setInputFiles(FILES);
  await page.waitForTimeout(2000);

  // ── Step 3: Wait for classification to complete ──────────────────────────
  console.log('[3] Waiting for all rows to classify (up to 90s)…');
  // Wait until no row has status "Processing"
  try {
    await page.waitForFunction(() => {
      const chips = document.querySelectorAll('[data-testid="status-chip"]');
      if (chips.length === 0) return false;
      return Array.from(chips).every(c => c.textContent?.trim() !== 'Processing');
    }, { timeout: 90_000 });
    console.log('[3] ✓ All rows classified');
  } catch {
    console.log('[3] ✗ Timeout waiting for classification — taking screenshot');
    await page.screenshot({ path: 'test-results/issue-classification-timeout.png', fullPage: true });
  }

  // Capture the queue state
  await page.screenshot({ path: 'test-results/happy-path-01-classified.png', fullPage: true });
  await page.waitForTimeout(1500);

  // ── Step 4: Observe statuses ─────────────────────────────────────────────
  const statuses = await page.locator('[data-testid="status-chip"]').allTextContents();
  console.log(`[4] Row statuses: ${statuses.join(', ')}`);

  const needsReview = statuses.filter(s => s.includes('Needs Review') || s.includes('Review'));
  if (needsReview.length > 0) {
    console.log(`[4] ⚠ ${needsReview.length} row(s) need review`);
  }

  // ── Step 5: Inspect a "Needs Review" row if any ──────────────────────────
  const reviewRow = page.locator('tr').filter({ hasText: 'Needs Review' }).first();
  if (await reviewRow.isVisible()) {
    console.log('[5] Clicking a Needs-Review row to inspect…');
    await reviewRow.locator('[data-testid="row-select"]').check();
    await page.waitForTimeout(800);

    // Try changing model type
    const modelSelect = reviewRow.locator('select[data-testid="model-type-select"]');
    if (await modelSelect.isVisible()) {
      const options = await modelSelect.locator('option').allTextContents();
      console.log(`[5]   Model type options: ${options.join(', ')}`);
      await modelSelect.selectOption({ index: 1 });
      await page.waitForTimeout(800);
    }
    await page.screenshot({ path: 'test-results/happy-path-02-needs-review.png', fullPage: true });
  }

  // ── Step 6: Select all Ready rows and send to print ──────────────────────
  console.log('[6] Selecting all Ready rows…');
  const readyRows = page.locator('tr').filter({ has: page.locator('[data-testid="status-chip"]', { hasText: 'Ready' }) });
  const readyCount = await readyRows.count();
  console.log(`[6]   Found ${readyCount} Ready rows`);

  for (let i = 0; i < readyCount; i++) {
    const checkbox = readyRows.nth(i).locator('[data-testid="row-select"]');
    if (await checkbox.isVisible() && !(await checkbox.isChecked())) {
      await checkbox.check();
    }
  }
  await page.waitForTimeout(1000);
  await page.screenshot({ path: 'test-results/happy-path-03-selected.png', fullPage: true });

  // ── Step 7: Send to print ────────────────────────────────────────────────
  const sendBtn = page.locator('[data-testid="send-to-print-button"]');
  const sendBtnText = await sendBtn.textContent();
  console.log(`[7] Send-to-print button: "${sendBtnText?.trim()}"`);

  if (readyCount > 0 && await sendBtn.isEnabled()) {
    console.log('[7] Clicking Send to Print…');
    await sendBtn.click();
    await page.waitForTimeout(2000);

    const statusText = page.locator('#status-text');
    if (await statusText.isVisible()) {
      const msg = await statusText.textContent();
      console.log(`[7] Status message: "${msg?.trim()}"`);
    }
    await page.screenshot({ path: 'test-results/happy-path-04-sent.png', fullPage: true });
  } else {
    console.log('[7] ✗ Send to Print button not enabled or no ready rows');
    await page.screenshot({ path: 'test-results/issue-send-btn-disabled.png', fullPage: true });
  }

  await page.waitForTimeout(2000);

  // ── Step 8: Check In Progress tab ───────────────────────────────────────
  console.log('[8] Clicking In Progress tab…');
  const inProgressTab = page.getByRole('tab', { name: /In Progress/i });
  if (await inProgressTab.isVisible()) {
    await inProgressTab.click();
    await page.waitForTimeout(1500);
    const rows = await page.locator('#inprogress-body tr, #in-progress-body tr').count();
    console.log(`[8]   In Progress rows: ${rows}`);
    await page.screenshot({ path: 'test-results/happy-path-05-inprogress.png', fullPage: true });
  }

  // ── Step 9: Check Print Queue tab ───────────────────────────────────────
  console.log('[9] Clicking Print Queue tab…');
  const printQueueTab = page.getByRole('tab', { name: /Print Queue/i });
  if (await printQueueTab.isVisible()) {
    await printQueueTab.click();
    await page.waitForTimeout(2000);
    const jobRows = await page.locator('#print-queue-body tr').count();
    console.log(`[9]   Print queue job rows: ${jobRows}`);

    if (jobRows > 0) {
      const firstJobText = await page.locator('#print-queue-body tr').first().textContent();
      console.log(`[9]   First job: ${firstJobText?.trim().replace(/\s+/g, ' ')}`);
    }
    await page.screenshot({ path: 'test-results/happy-path-06-printqueue.png', fullPage: true });

    // Try screenshot button
    const screenshotBtn = page.locator('.job-screenshot-button').first();
    if (await screenshotBtn.isVisible()) {
      const btnText = await screenshotBtn.textContent();
      console.log(`[9]   Screenshot button: "${btnText?.trim()}"`);
      if (await screenshotBtn.isEnabled()) {
        await screenshotBtn.click();
        await page.waitForTimeout(3000);
        await page.screenshot({ path: 'test-results/happy-path-07-screenshot-modal.png', fullPage: true });
        // Close modal
        const closeBtn = page.locator('#screenshot-modal .close-btn, #screenshot-modal button[aria-label="Close"]').first();
        if (await closeBtn.isVisible()) await closeBtn.click();
      }
    }
  }

  // ── Step 10: Check History tab ───────────────────────────────────────────
  console.log('[10] Clicking History tab…');
  const historyTab = page.getByRole('tab', { name: /History/i });
  if (await historyTab.isVisible()) {
    await historyTab.click();
    await page.waitForTimeout(1500);
    const histRows = await page.locator('#history-body tr').count();
    console.log(`[10]  History rows: ${histRows}`);
    await page.screenshot({ path: 'test-results/happy-path-08-history.png', fullPage: true });
  }

  // ── Step 11: Reload and check persistence ───────────────────────────────
  console.log('[11] Reloading page to verify state persistence…');
  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForTimeout(2000);
  const afterReloadRows = await page.locator('[data-testid="status-chip"]').count();
  console.log(`[11]  Rows visible after reload: ${afterReloadRows}`);
  await page.screenshot({ path: 'test-results/happy-path-09-after-reload.png', fullPage: true });

  console.log('\n[Done] Happy path simulation complete. Screenshots saved to test-results/');
  await page.waitForTimeout(4000);
  await browser.close();
})();
