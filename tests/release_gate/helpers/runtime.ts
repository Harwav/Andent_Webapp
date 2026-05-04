import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process';
import fs from 'node:fs/promises';
import path from 'node:path';

export type AppInstance = {
  baseURL: string;
  dataDir: string;
  databasePath: string;
  preformUrl: string;
  process: ChildProcessWithoutNullStreams;
};

async function waitForHealth(url: string, timeoutMs = 60_000): Promise<void> {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    try {
      const response = await fetch(url);
      if (response.ok) {
        return;
      }
    } catch {}
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`Timed out waiting for health: ${url}`);
}

export async function startAppInstance(opts: {
  port: number;
  dataDir: string;
  preformUrl: string;
}): Promise<AppInstance> {
  await fs.rm(opts.dataDir, { recursive: true, force: true });
  await fs.mkdir(opts.dataDir, { recursive: true });
  const databasePath = path.join(opts.dataDir, 'formflow.db');
  const child = spawn(
    'python',
    ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', String(opts.port)],
    {
      cwd: process.cwd(),
      env: {
        ...process.env,
        FORMFLOW_WEB_DATA_DIR: opts.dataDir,
        FORMFLOW_WEB_DATABASE_PATH: databasePath,
        FORMFLOW_WEB_APPDATA_DIR: path.join(opts.dataDir, 'appdata'),
        FORMFLOW_WEB_PRINT_HOLD_DENSITY_TARGET: '0.0',
        PREFORM_SERVER_URL: opts.preformUrl,
      },
      stdio: 'pipe',
    },
  );

  const baseURL = `http://127.0.0.1:${opts.port}`;
  await waitForHealth(`${baseURL}/health`);

  return { baseURL, dataDir: opts.dataDir, databasePath, preformUrl: opts.preformUrl, process: child };
}

export async function stopAppInstance(app: AppInstance): Promise<void> {
  app.process.kill();
}
