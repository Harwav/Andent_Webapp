import { expect, test } from './helpers/fixtures.js';

test('runtime starts live and dead-port app instances', async ({ request, liveApp, deadApp }) => {
  const liveHealth = await request.get(`${liveApp.baseURL}/health`);
  expect(liveHealth.ok()).toBeTruthy();

  const deadHealth = await request.get(`${deadApp.baseURL}/health`);
  expect(deadHealth.ok()).toBeTruthy();
});
