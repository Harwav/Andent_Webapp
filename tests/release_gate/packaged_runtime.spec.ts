import { spawn } from 'node:child_process';
import fs from 'node:fs/promises';
import path from 'node:path';
import { expect, test } from './helpers/fixtures.js';
import { findPackagedExecutable, waitForHealth } from './helpers/runtime.js';

test('packaged EXE starts an isolated browser-reachable FormFlow app', async ({ page }) => {
  test.setTimeout(180_000);

  const evidenceDir = process.env.FORMFLOW_RELEASE_EVIDENCE_DIR ?? 'test-results/release-gate';
  const dataDir = path.resolve('test-results/release-gate/packaged-runtime');
  const appDataDir = path.join(dataDir, 'appdata');
  const databasePath = path.join(dataDir, 'formflow.db');
  const port = Number(process.env.FORMFLOW_RELEASE_PACKAGED_PORT ?? '8297');
  const baseURL = `http://127.0.0.1:${port}`;
  const executablePath = await findPackagedExecutable();

  await fs.rm(dataDir, { recursive: true, force: true });
  await fs.mkdir(dataDir, { recursive: true });

  const child = spawn(executablePath, [], {
    cwd: path.dirname(executablePath),
    env: {
      ...process.env,
      FORMFLOW_WEB_OPEN_BROWSER: '0',
      FORMFLOW_WEB_HOST: '127.0.0.1',
      FORMFLOW_WEB_PORT: String(port),
      FORMFLOW_WEB_APPDATA_DIR: appDataDir,
      FORMFLOW_WEB_DATA_DIR: dataDir,
      FORMFLOW_WEB_DATABASE_PATH: databasePath,
      FORMFLOW_WEB_PRINT_DISPATCH_MODE: 'virtual',
      ANDENT_WEB_PRINT_DISPATCH_MODE: 'virtual',
    },
    stdio: 'pipe',
  });

  const stderr: string[] = [];
  child.stderr.setEncoding('utf8');
  child.stderr.on('data', (chunk) => stderr.push(String(chunk)));

  try {
    await waitForHealth(`${baseURL}/health`, 90_000);
    await page.goto(baseURL);
    await expect(page.getByRole('heading', { name: 'Active Queue' })).toBeVisible();

    await fs.mkdir(evidenceDir, { recursive: true });
    await fs.writeFile(
      path.join(evidenceDir, 'packaged-runtime.json'),
      JSON.stringify(
        {
          executable_path: executablePath,
          base_url: baseURL,
          data_dir: dataDir,
          database_path: databasePath,
          browser_reachable: true,
        },
        null,
        2,
      ),
      'utf8',
    );
  } catch (error) {
    const detail = stderr.join('').slice(-4000);
    throw new Error(`${error instanceof Error ? error.message : String(error)}\n\nPackaged stderr:\n${detail}`);
  } finally {
    child.kill();
  }
});
