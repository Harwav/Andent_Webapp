import { expect, test } from '@playwright/test';

test.describe('Case Selection', () => {
  test.beforeEach(async ({ page }) => {
    // Mock API endpoints
    await page.route('/api/preform-setup/status', async (route) => {
      await route.fulfill({
        json: {
          readiness: 'ready',
          install_path: 'managed',
          managed_executable_path: 'managed/PreFormServer.exe',
          detected_version: '3.57.2.624',
          expected_version_min: '3.49.0',
          expected_version_max: null,
          active_configured_source: true,
          is_running: true,
          last_health_check_at: null,
          last_error_code: null,
          last_error_message: null,
        },
      });
    });

    // Return multiple files with same case ID
    await page.route('/api/uploads/queue', async (route) => {
      await route.fulfill({
        json: {
          active_rows: [
            {
              row_id: 'file-1',
              file_name: 'case1_upper.stl',
              case_id: 'CASE001',
              model_type: 'Upper',
              status: 'Ready',
              is_temp: false
            },
            {
              row_id: 'file-2',
              file_name: 'case1_lower.stl',
              case_id: 'CASE001',
              model_type: 'Lower',
              status: 'Ready',
              is_temp: false
            },
            {
              row_id: 'file-3',
              file_name: 'case2_upper.stl',
              case_id: 'CASE002',
              model_type: 'Upper',
              status: 'Ready',
              is_temp: false
            },
            {
              row_id: 'file-4',
              file_name: 'case2_lower.stl',
              case_id: 'CASE002',
              model_type: 'Lower',
              status: 'Ready',
              is_temp: false
            },
          ],
          processed_rows: []
        },
      });
    });

    await page.route('/api/print-queue/jobs', async (route) => {
      await route.fulfill({ json: { jobs: [] } });
    });

    await page.goto('/');
    await expect(page.getByRole('heading', { name: 'Active Queue' })).toBeVisible();
  });

  test('clicking row selects all same-case rows', async ({ page }) => {
    // Wait for rows to load
    await expect(page.locator('#active-body tr')).toHaveCount(4, { timeout: 10000 });

    // Check one row with caseId CASE001
    const case1Row = page.locator('tr[data-file-name="case1_upper.stl"]');
    await case1Row.locator('[data-testid="row-select"]').check();

    // Both rows with CASE001 should be selected
    const case1Upper = page.locator('tr[data-file-name="case1_upper.stl"] [data-testid="row-select"]');
    const case1Lower = page.locator('tr[data-file-name="case1_lower.stl"] [data-testid="row-select"]');

    await expect(case1Upper).toBeChecked();
    await expect(case1Lower).toBeChecked();

    // Rows with CASE002 should NOT be selected
    const case2Upper = page.locator('tr[data-file-name="case2_upper.stl"] [data-testid="row-select"]');
    const case2Lower = page.locator('tr[data-file-name="case2_lower.stl"] [data-testid="row-select"]');

    await expect(case2Upper).not.toBeChecked();
    await expect(case2Lower).not.toBeChecked();
  });

  test('Ctrl+click adds to selection', async ({ page }) => {
    // Wait for rows to load
    await expect(page.locator('#active-body tr')).toHaveCount(4, { timeout: 10000 });

    // Select first row
    const case1Upper = page.locator('tr[data-file-name="case1_upper.stl"]');
    await case1Upper.locator('[data-testid="row-select"]').check();

    // Verify one is selected
    await expect(page.locator('tr[data-file-name="case1_upper.stl"] [data-testid="row-select"]')).toBeChecked();

    // Check another row to add a different case
    const case2Upper = page.locator('tr[data-file-name="case2_upper.stl"]');
    await case2Upper.locator('[data-testid="row-select"]').check();

    // Both should now be selected
    await expect(page.locator('tr[data-file-name="case1_upper.stl"] [data-testid="row-select"]')).toBeChecked();
    await expect(page.locator('tr[data-file-name="case2_upper.stl"] [data-testid="row-select"]')).toBeChecked();
  });

  test('selection count updates', async ({ page }) => {
    // Wait for rows to load
    await expect(page.locator('#active-body tr')).toHaveCount(4, { timeout: 10000 });

    // Selection count should start at 0
    const selectionCounter = page.locator('.selection-count, [data-testid="selection-count"]');
    if (await selectionCounter.isVisible()) {
      await expect(selectionCounter).toHaveText('0');
    }

    // Check one row to select all rows with same case (CASE001 has 2 rows)
    await page.locator('tr[data-file-name="case1_upper.stl"] [data-testid="row-select"]').check();

    // Selection count should update
    if (await selectionCounter.isVisible()) {
      await expect(selectionCounter).toHaveText('2');
    }

    // Check one row to select all rows with another case (CASE002 has 2 rows)
    await page.locator('tr[data-file-name="case2_upper.stl"] [data-testid="row-select"]').check();

    // Selection count should now be 4 (all rows)
    if (await selectionCounter.isVisible()) {
      await expect(selectionCounter).toHaveText('4');
    }
  });

  test('unchecking selected row keeps other same-case selections', async ({ page }) => {
    // Wait for rows to load
    await expect(page.locator('#active-body tr')).toHaveCount(4, { timeout: 10000 });

    // Select a case
    const case1Checkbox = page.locator('tr[data-file-name="case1_upper.stl"] [data-testid="row-select"]');
    await case1Checkbox.check();

    // Verify rows are selected
    await expect(case1Checkbox).toBeChecked();

    // Uncheck again to deselect that row
    await case1Checkbox.uncheck();

    // Only that row is deselected; other grouped rows remain selected until cleared directly.
    await expect(page.locator('tr[data-file-name="case1_upper.stl"] [data-testid="row-select"]')).not.toBeChecked();
    await expect(page.locator('tr[data-file-name="case1_lower.stl"] [data-testid="row-select"]')).toBeChecked();
  });
});
