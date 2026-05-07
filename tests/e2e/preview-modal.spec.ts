import { expect, test } from '@playwright/test';

test.describe('Preview Modal', () => {
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
          active_rows: [{
            row_id: 'test-1',
            file_name: 'test-preview.stl',
            file_url: '/fixtures/test-preview.stl',
            case_id: 'CASE001',
            model_type: 'Upper',
            status: 'Ready',
            is_temp: false
          }],
          processed_rows: []
        }
      });
    });

    await page.route('/fixtures/test-preview.stl', async (route) => {
      await route.fulfill({
        contentType: 'application/sla',
        body: [
          'solid preview',
          'facet normal 0 0 1',
          'outer loop',
          'vertex 0 0 0',
          'vertex 1 0 0',
          'vertex 0 1 0',
          'endloop',
          'endfacet',
          'endsolid preview',
        ].join('\n'),
      });
    });

    await page.route('/api/print-queue/jobs', async (route) => {
      await route.fulfill({ json: { jobs: [] } });
    });

    await page.goto('/');
    await expect(page.getByRole('heading', { name: 'Active Queue' })).toBeVisible();
  });

  test('modal opens on thumbnail click', async ({ page }) => {
    // Wait for file to appear
    await expect(page.locator('#active-body tr')).toBeVisible({ timeout: 10000 });

    // Click on thumbnail button to open modal
    const thumbnailButton = page.locator('.thumbnail-button').first();
    await expect(thumbnailButton).toBeEnabled();
    await thumbnailButton.click();

    // Modal should be visible
    const modal = page.locator('#preview-modal');
    await expect(modal).not.toHaveClass(/hidden/);
    await expect(modal).toHaveAttribute('aria-hidden', 'false');
  });

  test('modal closes', async ({ page }) => {
    // Wait for file to appear
    await expect(page.locator('#active-body tr')).toBeVisible({ timeout: 10000 });

    // Open modal
    const thumbnailButton = page.locator('.thumbnail-button').first();
    await expect(thumbnailButton).toBeEnabled();
    await thumbnailButton.click();
    await expect(page.locator('#preview-modal')).not.toHaveClass(/hidden/);

    // Close modal using the close button
    await page.locator('#close-preview').click();

    // Modal should be hidden
    await expect(page.locator('#preview-modal')).toHaveClass(/hidden/);
    await expect(page.locator('#preview-modal')).toHaveAttribute('aria-hidden', 'true');
  });

  test('modal closes on backdrop click', async ({ page }) => {
    // Wait for file to appear
    await expect(page.locator('#active-body tr')).toBeVisible({ timeout: 10000 });

    // Open modal
    const thumbnailButton = page.locator('.thumbnail-button').first();
    await expect(thumbnailButton).toBeEnabled();
    await thumbnailButton.click();
    await expect(page.locator('#preview-modal')).not.toHaveClass(/hidden/);

    // Click exposed backdrop outside the centered modal card.
    await page.mouse.click(8, 8);

    // Modal should be hidden
    await expect(page.locator('#preview-modal')).toHaveClass(/hidden/);
  });
});
