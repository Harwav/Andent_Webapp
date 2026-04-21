import { expect, test } from './helpers/fixtures.js';

test('runtime harness starts isolated app instances', async ({ request, liveApp, deadApp }) => {
  const liveHealth = await request.get(`${liveApp.baseURL}/health`);
  const deadHealth = await request.get(`${deadApp.baseURL}/health`);

  expect(liveHealth.ok()).toBeTruthy();
  expect(deadHealth.ok()).toBeTruthy();
  expect(liveApp.baseURL).not.toBe(deadApp.baseURL);
  expect(liveApp.dataDir).not.toBe(deadApp.dataDir);
});
