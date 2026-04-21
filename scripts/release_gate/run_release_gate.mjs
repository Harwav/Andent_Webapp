import { spawn } from 'node:child_process';
import fs from 'node:fs/promises';

const resultsFile = 'test-results/release-gate/results.json';

const exitCode = await new Promise((resolve) => {
  const command = 'npx playwright test tests/release_gate/release_gate.spec.ts --project=chromium';
  const child = spawn(
    command,
    [],
    { stdio: 'inherit', shell: true },
  );
  child.on('exit', (code) => resolve(code ?? 1));
});

try {
  const report = JSON.parse(await fs.readFile(resultsFile, 'utf8'));
  const suites = report.suites ?? [];
  const stack = [...suites];
  const specs = [];
  while (stack.length > 0) {
    const suite = stack.shift();
    if (!suite) {
      continue;
    }
    specs.push(...(suite.specs ?? []));
    stack.push(...(suite.suites ?? []));
  }

  for (const spec of specs) {
    const tests = spec.tests ?? [];
    for (const item of tests) {
      const result = item.results?.[0];
      console.log(`[release-gate] ${spec.title}: ${result?.status ?? 'unknown'}`);
    }
  }
} catch (error) {
  console.error(`[release-gate] could not read ${resultsFile}: ${error}`);
}

process.exit(exitCode);
