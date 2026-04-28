import { expect, test } from '@playwright/test';

test.describe('Legend Filters', () => {
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

    // Return files with various statuses
    await page.route('/api/uploads/queue', async (route) => {
      await route.fulfill({
        json: {
          active_rows: [
            {
              id: 'file-1',
              row_id: 'file-1',
              file_name: 'file-ready.stl',
              case_id: 'CASE001',
              model_type: 'Upper',
              status: 'Ready',
              is_temp: false
            },
            {
              id: 'file-2',
              row_id: 'file-2',
              file_name: 'file-analyzing.stl',
              case_id: 'CASE002',
              model_type: 'Upper',
              status: 'Analyzing',
              is_temp: false
            },
            {
              id: 'file-3',
              row_id: 'file-3',
              file_name: 'file-error.stl',
              case_id: 'CASE003',
              model_type: 'Upper',
              status: 'Error',
              is_temp: false
            },
            {
              id: 'file-4',
              row_id: 'file-4',
              file_name: 'file-complete.stl',
              case_id: 'CASE004',
              model_type: 'Upper',
              status: 'Complete',
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

  test('legend renders with all status chips', async ({ page }) => {
    // Wait for legend to be visible
    const legend = page.locator('#status-legend');
    await expect(legend).toBeVisible();

    // Legend should contain status chips for different statuses
    await expect(legend).toContainText('Ready');
    await expect(legend).toContainText('Analyzing');
    await expect(legend).toContainText('Error');
    await expect(legend).toContainText('Complete');
  });

  test('clicking filter updates active filters', async ({ page }) => {
    // Wait for legend and rows
    await expect(page.locator('#status-legend')).toBeVisible();
    await expect(page.locator('#active-body tr')).toHaveCount(4, { timeout: 10000 });

    // Initially, all 4 files should be visible
    await expect(page.locator('#active-body')).toContainText('file-ready.stl');
    await expect(page.locator('#active-body')).toContainText('file-analyzing.stl');
    await expect(page.locator('#active-body')).toContainText('file-error.stl');
    await expect(page.locator('#active-body')).toContainText('file-complete.stl');

    // Click on "Ready" legend item to toggle it
    const readyChip = page.locator('.legend-item').filter({ hasText: 'Ready' });
    await readyChip.click();

    // Wait for filter to apply
    await page.waitForTimeout(500);

    // Only "Ready" file should be hidden (3 rows visible)
    await expect(page.locator('#active-body tr')).toHaveCount(3);
    await expect(page.locator('#active-body')).not.toContainText('file-ready.stl');

    // Click again to re-enable
    await readyChip.click();

    // All files should be visible again
    await page.waitForTimeout(500);
    await expect(page.locator('#active-body tr')).toHaveCount(4);
  });

  test('filtered rows are shown', async ({ page }) => {
    // Wait for rows
    await expect(page.locator('#active-body tr')).toHaveCount(4, { timeout: 10000 });

    // Click on "Error" legend item
    const errorChip = page.locator('.legend-item').filter({ hasText: 'Error' });
    await errorChip.click();

    // Wait for filter to apply
    await page.waitForTimeout(500);

    // Only "Error" file should be visible (1 row)
    await expect(page.locator('#active-body tr')).toHaveCount(1);
    await expect(page.locator('#active-body')).toContainText('file-error.stl');
  });

  test('multiple filters can be active', async ({ page }) => {
    // Wait for rows
    await expect(page.locator('#active-body tr')).toHaveCount(4, { timeout: 10000 });

    // Enable "Ready" and "Complete" filters, disable others
    await page.locator('.legend-item').filter({ hasText: 'Analyzing' }).click();
    await page.locator('.legend-item').filter({ hasText: 'Error' }).click();

    // Wait for filter to apply
    await page.waitForTimeout(500);

    // Only "Ready" and "Complete" files should be visible (2 rows)
    await expect(page.locator('#active-body tr')).toHaveCount(2);
    await expect(page.locator('#active-body')).toContainText('file-ready.stl');
    await expect(page.locator('#active-body')).toContainText('file-complete.stl');
  });

  test('filter chip shows active state', async ({ page }) => {
    // Wait for legend
    await expect(page.locator('#status-legend')).toBeVisible();

    const readyChip = page.locator('.legend-item').filter({ hasText: 'Ready' });

    // Initially, chip should not have active class (no filter active)
    await expect(readyChip).not.toHaveClass(/legend-item-active/);

    // Click to activate
    await readyChip.click();

    // Chip should now have active class
    await expect(readyChip).toHaveClass(/legend-item-active/);

    // Click to deactivate
    await readyChip.click();

    // Chip should no longer have active class
    await expect(readyChip).not.toHaveClass(/legend-item-active/);
  });
});
