import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/release_gate',
  timeout: 60_000,
  expect: {
    timeout: 10_000,
  },
  reporter: [
    ['line'],
    ['json', { outputFile: 'test-results/release-gate/results.json' }],
  ],
  outputDir: 'test-results/playwright',
  use: {
    baseURL: 'http://127.0.0.1:8090',
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
    video: 'retain-on-failure',
  },
  webServer: {
    command: `python -c "import os, shutil; from pathlib import Path; data_dir = Path('test-results/playwright-app'); shutil.rmtree(data_dir, ignore_errors=True); os.environ['ANDENT_WEB_DATA_DIR'] = str(data_dir); os.environ['ANDENT_WEB_DATABASE_PATH'] = str(data_dir / 'andent_web.db'); os.environ['ANDENT_WEB_APPDATA_DIR'] = str(data_dir / 'appdata'); import uvicorn; uvicorn.run('app.main:app', host='127.0.0.1', port=8090)"`,
    url: 'http://127.0.0.1:8090/health',
    reuseExistingServer: true,
    timeout: 60_000,
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
      },
    },
  ],
});
