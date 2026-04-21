import path from 'node:path';
import { test as base } from '@playwright/test';
import { startAppInstance, stopAppInstance, type AppInstance } from './runtime';

export const test = base.extend<{
  liveApp: AppInstance;
  deadApp: AppInstance;
}>({
  liveApp: [async ({}, use) => {
    const app = await startAppInstance({
      port: 8091,
      dataDir: path.resolve('test-results/release-gate/live-app'),
      preformUrl: 'http://127.0.0.1:44388',
    });
    await use(app);
    await stopAppInstance(app);
  }, { scope: 'worker' }],

  deadApp: [async ({}, use) => {
    const app = await startAppInstance({
      port: 8092,
      dataDir: path.resolve('test-results/release-gate/dead-app'),
      preformUrl: 'http://127.0.0.1:59999',
    });
    await use(app);
    await stopAppInstance(app);
  }, { scope: 'worker' }],
});

export { expect } from '@playwright/test';
