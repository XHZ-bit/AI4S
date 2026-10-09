// Run both local servers and browser in one process tree, then always stop them.
const { spawn } = require('node:child_process');
const path = require('node:path');
const root = path.resolve(__dirname, '../..');
const directory = path.resolve(process.argv[2]);
const children = [];
function run(binary, args, options = {}) { const child = spawn(binary, args, { stdio: 'inherit', ...options }); children.push(child); return child; }
const pause = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  try {
    run(process.env.ATLAS_PYTHON || 'python', ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '18000'], { cwd: path.join(root, 'backend'), env: { ...process.env, DATA_DIR: directory, RESEARCH_MODEL_ENABLED: 'false', DASHSCOPE_API_KEY: '', NEO4J_URI: 'bolt://127.0.0.1:1', NEO4J_PASSWORD: 'isolated-test', GROBID_BASE_URL: 'http://127.0.0.1:1' } });
    run(process.execPath, ['node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', '15174', '--strictPort'], { cwd: path.join(root, 'frontend'), env: { ...process.env, ATLAS_API_TARGET: 'http://127.0.0.1:18000' } });
    let ready = false;
    for (let i = 0; i < 25; i++) {
      try { const api = await fetch('http://127.0.0.1:18000/api/cases', { signal: AbortSignal.timeout(1000) }); if (!api.ok) continue; const r = await fetch('http://127.0.0.1:15174/api/cases', { signal: AbortSignal.timeout(1000) }); if (r.ok) { ready = true; break; } } catch {}
      await pause(300);
    }
    if (!ready) throw Error('Local test servers did not become reachable');
    const browser = run(process.execPath, [path.join(__dirname, 'assistant_browser.cjs'), directory], { env: { ...process.env, ATLAS_BROWSER_BASE: 'http://127.0.0.1:15174' } });
    process.exitCode = await new Promise(resolve => browser.on('exit', code=>resolve(code??1)));
  } finally { children.forEach(child => child.kill()); }
})().catch(e => { console.error(e); process.exitCode = 1; });
