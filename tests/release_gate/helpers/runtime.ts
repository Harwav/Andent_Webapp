import { spawn, type ChildProcess } from 'node:child_process';
import fs from 'node:fs/promises';
import net from 'node:net';
import path from 'node:path';

export type AppInstance = {
  baseURL: string;
  dataDir: string;
  databasePath: string;
  preformUrl: string;
  process: ChildProcess;
};

type StartAppOptions = {
  dataDir: string;
  preformUrl: string;
};

async function getFreePort(): Promise<number> {
  return await new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.on('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const address = server.address();
      if (!address || typeof address === 'string') {
        server.close();
        reject(new Error('Could not resolve an ephemeral port.'));
        return;
      }
      const { port } = address;
      server.close((error) => {
        if (error) {
          reject(error);
          return;
        }
        resolve(port);
      });
    });
  });
}

async function waitForHealth(url: string): Promise<void> {
  const deadline = Date.now() + 60_000;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok) {
        return;
      }
    } catch {
      // Retry until timeout.
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`Timed out waiting for ${url}`);
}

async function seedManagedInstall(dataDir: string): Promise<void> {
  const appDataDir = path.resolve(dataDir, 'appdata', 'Andent Web', 'PreFormServer');
  await fs.mkdir(appDataDir, { recursive: true });
  await fs.writeFile(path.join(appDataDir, 'PreFormServer.exe'), 'fake exe\n', 'utf8');
  await fs.writeFile(path.join(appDataDir, 'version.txt'), '3.57.2.624\n', 'utf8');
}

export async function startAppInstance(options: StartAppOptions): Promise<AppInstance> {
  const dataDir = path.resolve(options.dataDir);
  const databasePath = path.join(dataDir, 'andent_web.db');
  const port = await getFreePort();
  await fs.rm(dataDir, { recursive: true, force: true });
  await fs.mkdir(dataDir, { recursive: true });
  await seedManagedInstall(dataDir);

  const child = spawn(
    'python',
    ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', String(port)],
    {
      cwd: path.resolve('.'),
      env: {
        ...process.env,
        ANDENT_WEB_DATA_DIR: dataDir,
        ANDENT_WEB_DATABASE_PATH: databasePath,
        ANDENT_WEB_APPDATA_DIR: path.join(dataDir, 'appdata'),
        ANDENT_WEB_PRINT_HOLD_DENSITY_TARGET: '0',
        PREFORM_SERVER_URL: options.preformUrl,
      },
      stdio: 'pipe',
    },
  );

  const baseURL = `http://127.0.0.1:${port}`;
  await waitForHealth(`${baseURL}/health`);

  return {
    baseURL,
    dataDir,
    databasePath,
    preformUrl: options.preformUrl,
    process: child,
  };
}

export async function stopAppInstance(app: AppInstance): Promise<void> {
  if (app.process.killed) {
    return;
  }

  await new Promise<void>((resolve) => {
    app.process.once('exit', () => resolve());
    app.process.kill();
    setTimeout(() => resolve(), 5_000);
  });
}
