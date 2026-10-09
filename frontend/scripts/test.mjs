import { mkdir } from 'node:fs/promises';
import { spawn } from 'node:child_process';
import { resolve } from 'node:path';
const temp = resolve('.tmp/vitest');
await mkdir(temp, { recursive: true });
const child = spawn(process.execPath, ['node_modules/vitest/vitest.mjs', 'run', ...process.argv.slice(2)], { stdio: 'inherit', env: { ...process.env, TEMP: temp, TMP: temp, TMPDIR: temp } });
child.on('exit', code => { process.exitCode = code ?? 1; });
