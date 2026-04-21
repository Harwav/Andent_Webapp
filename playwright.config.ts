import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/release_gate',
  timeout: 60_000,
  expect: {
    timeout: 10_000,
  },
  outputDir: 'test-results/playwright',
  use: {
    baseURL: 'http://127.0.0.1:8090',
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
    video: 'retain-on-failure',
  },
  webServer: {
    command: 'python -m uvicorn app.main:app --host 127.0.0.1 --port 8090',
    url: 'http://127.0.0.1:8090/health',
    reuseExistingServer: false,
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
