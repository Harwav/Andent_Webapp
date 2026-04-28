import { expect, test } from '@playwright/test';

test.describe('Polling', () => {
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

  test('work queue polls', async ({ page }) => {
    let requestCount = 0;

    // Track requests to uploads/queue
    await page.route('/api/uploads/queue', async (route) => {
      requestCount++;
      await route.fulfill({
        json: {
          active_rows: [],
          processed_rows: []
        }
      });
    });

    // Wait for polling to occur (default polling interval is 5 seconds)
    await page.waitForTimeout(6000);

    // Verify multiple requests were made (polling occurred)
    expect(requestCount).toBeGreaterThan(1);
  });

  test('print queue polls', async ({ page }) => {
    let requestCount = 0;

    // Track requests to print-queue/jobs
    await page.route('/api/print-queue/jobs', async (route) => {
      requestCount++;
      await route.fulfill({ json: { jobs: [] } });
    });

    // Wait for polling to occur
    await page.waitForTimeout(6000);

    // Verify multiple requests were made
    expect(requestCount).toBeGreaterThan(1);
  });

  test('polling respects paused state', async ({ page }) => {
    let uploadRequestCount = 0;
    let printRequestCount = 0;

    await page.route('/api/uploads/queue', async (route) => {
      uploadRequestCount++;
      await route.fulfill({
        json: {
          active_rows: [],
          processed_rows: []
        }
      });
    });

    await page.route('/api/print-queue/jobs', async (route) => {
      printRequestCount++;
      await route.fulfill({ json: { jobs: [] } });
    });

    // Wait for initial polling
    await page.waitForTimeout(3000);

    const initialUploadCount = uploadRequestCount;
    const initialPrintCount = printRequestCount;

    // Pause button - if UI provides pause functionality
    const pauseButton = page.locator('#pause-polling');
    if (await pauseButton.isVisible()) {
      await pauseButton.click();

      // Wait for another polling cycle
      await page.waitForTimeout(6000);

      // Polling should not have increased significantly when paused
      const uploadDelta = uploadRequestCount - initialUploadCount;
      const printDelta = printRequestCount - initialPrintCount;

      // At most 1 additional request should occur (race condition)
      expect(uploadDelta).toBeLessThanOrEqual(1);
      expect(printDelta).toBeLessThanOrEqual(1);
    } else {
      // If no pause button, verify polling continues
      await page.waitForTimeout(6000);
      expect(uploadRequestCount).toBeGreaterThan(initialUploadCount);
      expect(printRequestCount).toBeGreaterThan(initialPrintCount);
    }
  });

  test('polling updates UI with new data', async ({ page }) => {
    let requestIndex = 0;

    // First request returns empty, second returns data
    await page.route('/api/uploads/queue', async (route) => {
      requestIndex++;
      if (requestIndex === 1) {
        await route.fulfill({
          json: {
            active_rows: [],
            processed_rows: []
          }
        });
      } else {
        await route.fulfill({
          json: {
            active_rows: [{
              row_id: 'test-123',
              file_name: 'polled-file.stl',
              case_id: 'CASE001',
              model_type: 'Upper',
              status: 'Ready',
              is_temp: false
            }],
            processed_rows: []
          }
        });
      }
    });

    // Initial load
    await page.waitForTimeout(500);

    // Wait for polling to fetch new data
    await page.waitForTimeout(6000);

    // New data should appear in the queue
    await expect(page.locator('#active-body')).toContainText('polled-file.stl');
  });
});
