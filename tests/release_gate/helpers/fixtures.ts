import { execFile } from 'node:child_process';
import path from 'node:path';
import { test as base } from '@playwright/test';
import { promisify } from 'node:util';
import { startAppInstance, stopAppInstance, type AppInstance } from './runtime';

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

  latestPrintJob: async ({}, use) => {
    await use((databasePath) => runVerify(['latest-print-job', '--database-path', databasePath]));
  },
  sceneStatus: async ({}, use) => {
    await use((baseUrl, sceneId) => runVerify(['scene', '--base-url', baseUrl, '--scene-id', sceneId]));
  },
});

export { expect } from '@playwright/test';
