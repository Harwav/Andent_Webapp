import path from 'node:path';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';

import { test as base } from '@playwright/test';

import { startAppInstance, stopAppInstance, type AppInstance } from './runtime.js';

const execFileAsync = promisify(execFile);

async function runVerify(args: string[]) {
  const { stdout } = await execFileAsync('python', ['tests/release_gate/helpers/python/release_gate_verify.py', ...args]);
  return JSON.parse(stdout);
}

export const test = base.extend<{
  liveApp: AppInstance;
  deadApp: AppInstance;
  latestPrintJob: (databasePath: string) => Promise<any>;
  sceneStatus: (baseUrl: string, sceneId: string) => Promise<any>;
}>({
  liveApp: [async ({}, use: (app: AppInstance) => Promise<void>) => {
    const app = await startAppInstance({
      dataDir: path.resolve('test-results/release-gate/live-app'),
      preformUrl: 'http://127.0.0.1:44388',
    });
    await use(app);
    await stopAppInstance(app);
  }, { scope: 'test' }],

  deadApp: [async ({}, use: (app: AppInstance) => Promise<void>) => {
    const app = await startAppInstance({
      dataDir: path.resolve('test-results/release-gate/dead-app'),
      preformUrl: 'http://127.0.0.1:59999',
    });
    await use(app);
    await stopAppInstance(app);
  }, { scope: 'test' }],

  latestPrintJob: async ({}, use: (fn: (databasePath: string) => Promise<any>) => Promise<void>) => {
    await use((databasePath) => runVerify(['latest-print-job', '--database-path', databasePath]));
  },

  sceneStatus: async ({}, use: (fn: (baseUrl: string, sceneId: string) => Promise<any>) => Promise<void>) => {
    await use((baseUrl, sceneId) => runVerify(['scene', '--base-url', baseUrl, '--scene-id', sceneId]));
  },
});

export { expect } from '@playwright/test';
