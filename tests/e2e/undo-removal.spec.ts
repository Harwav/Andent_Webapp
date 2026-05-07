import { expect, test } from '@playwright/test';

test.describe('Undo Removal', () => {
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

    await page.route('/api/uploads/queue', async (route) => {
      await route.fulfill({
        json: {
          active_rows: [],
          processed_rows: []
        }
      });
    });

    await page.route('/api/print-queue/jobs', async (route) => {
      await route.fulfill({ json: { jobs: [] } });
    });

    await page.goto('/');
    await expect(page.getByRole('heading', { name: 'Active Queue' })).toBeVisible();
  });

  test('undo button appears after delete', async ({ page }) => {
    // Mock queue with a file ready
    await page.route('/api/uploads/queue', async (route) => {
      await route.fulfill({
        json: {
          active_rows: [{
            row_id: 'test-1',
            file_name: 'test-file.stl',
            case_id: 'CASE001',
            model_type: 'Upper',
            status: 'Ready',
            is_temp: false
          }],
          processed_rows: []
        }
      });
    });

    // Reload to get the mocked data
    await page.reload();
    await expect(page.locator('#active-body tr')).toHaveCount(1, { timeout: 10000 });

    // Click delete button (remove button)
    const deleteButton = page.locator('#active-body tr').first().locator('.remove-button');
    await expect(deleteButton).toBeVisible();
    await deleteButton.click();

    // Undo button should appear
    const undoButton = page.locator('#active-body tr').first().locator('.undo-button');
    await expect(undoButton).toBeVisible();
  });

  test('undo restores deleted row', async ({ page }) => {
    // Mock queue with a file ready
    await page.route('/api/uploads/queue', async (route) => {
      await route.fulfill({
        json: {
          active_rows: [{
            row_id: 'test-1',
            file_name: 'test-restore.stl',
            case_id: 'CASE001',
            model_type: 'Upper',
            status: 'Ready',
            is_temp: false
          }],
          processed_rows: []
        }
      });
    });

    await page.reload();
    await expect(page.locator('#active-body tr')).toHaveCount(1, { timeout: 10000 });

    // Delete the row
    await page.locator('#active-body tr').first().locator('.remove-button').click();

    // Verify undo button is visible
    await expect(page.locator('#active-body tr').first().locator('.undo-button')).toBeVisible();

    // Click undo
    await page.locator('#active-body tr').first().locator('.undo-button').click();

    // Row should still be visible
    await expect(page.locator('#active-body tr')).toHaveCount(1);
    await expect(page.locator('#active-body')).toContainText('test-restore.stl');
  });

  test('undo expires after 5 seconds', async ({ page }) => {
    let deleted = false;
    // Mock queue with a file ready
    await page.route('/api/uploads/queue', async (route) => {
      await route.fulfill({
        json: {
          active_rows: deleted ? [] : [{
            row_id: 'test-1',
            file_name: 'test-expiry.stl',
            case_id: 'CASE001',
            model_type: 'Upper',
            status: 'Ready',
            is_temp: false
          }],
          processed_rows: []
        }
      });
    });

    // Mock the DELETE API call
    await page.route(/\/api\/uploads\/rows\/test-1/, async (route) => {
      deleted = true;
      await route.fulfill({ status: 204, body: '' });
    });

    await page.reload();
    await expect(page.locator('#active-body tr')).toHaveCount(1, { timeout: 10000 });

    // Delete the row
    await page.locator('#active-body tr').first().locator('.remove-button').click();

    // Undo button should be visible initially
    await expect(page.locator('#active-body tr').first().locator('.undo-button')).toBeVisible();

    // Wait for undo to expire (5 seconds + buffer)
    await page.waitForTimeout(5500);

    // Undo button should be gone and row should be permanently deleted
    await expect(page.locator('#active-body tr').first().locator('.undo-button')).not.toBeVisible();
    await expect(page.getByText('Add STL files or folders to start the queue.')).toBeVisible({ timeout: 5000 });
    await expect(page.locator('#active-body')).not.toContainText('test-expiry.stl');
  });
});
