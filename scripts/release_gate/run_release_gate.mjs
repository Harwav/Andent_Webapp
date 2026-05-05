import { spawn } from 'node:child_process';

const child = spawn(
  'python',
  ['scripts/release_gate/run_release_gate.py', ...process.argv.slice(2)],
  { stdio: 'inherit', shell: false },
);

child.on('exit', (code) => process.exit(code ?? 1));
