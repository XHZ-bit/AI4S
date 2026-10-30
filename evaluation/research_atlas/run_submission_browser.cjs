// Isolated real-browser acceptance: saved facts, decisions, conflicts and exports.
const fs = require('node:fs');
const path = require('node:path');
const net = require('node:net');
const assert = require('node:assert/strict');
const { spawn, spawnSync } = require('node:child_process');
const { chromium } = require(process.env.ATLAS_PLAYWRIGHT_PATH || '../../frontend/node_modules/playwright');
const root = path.resolve(__dirname, '../..');
const output = path.resolve(process.argv[2]);
assert(output.startsWith(path.join(root, '.ui_validation') + path.sep));
assert(!fs.existsSync(output), 'Use a new output directory; never overwrite previous evidence');
fs.mkdirSync(output, { recursive: true });
const directory = path.join(output, 'data');
const python = process.env.ATLAS_PYTHON || path.join(root, 'backend/.venv/Scripts/python.exe');
const apiPort = 18054, frontPort = 15224;
const api = `http://127.0.0.1:${apiPort}`, base = `http://127.0.0.1:${frontPort}`;
const identity = `submission-${Date.now()}`;
const env = { ...process.env, ATLAS_ENV_FILE: '', DATA_DIR: directory, ACCESS_MODE: 'local', OFFLINE_MODE: 'true', DASHSCOPE_API_KEY: '', RESEARCH_MODEL_ENABLED: 'false', RUNTIME_MODE: 'local', RUNTIME_ID: identity, NEO4J_URI: 'bolt://127.0.0.1:1', GROBID_BASE_URL: 'http://127.0.0.1:1' };
const children = [];
const report = { fixture: 'original synthetic', real_browser: true, model_calls: 0, checks: {}, errors: [], screenshots: [] };
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
async function freePort(port) {
  await new Promise((resolve, reject) => { const server = net.createServer(); server.once('error', reject); server.listen(port, '127.0.0.1', () => server.close(resolve)); });
}
function launch(binary, args, options) {
  const child = spawn(binary, args, { windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'], ...options });
  children.push(child);
  child.on('error', error => report.errors.push(error.message));
  for (const stream of [child.stdout, child.stderr]) stream.on('data', chunk => fs.appendFileSync(path.join(output, 'server.log'), chunk));
  return child;
}
async function stop(child) {
  if (child.exitCode !== null || child.signalCode !== null) return;
  await new Promise(resolve => { child.once('exit', resolve); child.kill(); });
}
async function ready() {
  for (let attempt = 0; attempt < 80; attempt++) {
    try {
      const session = await fetch(`${base}/api/auth/session`, { signal: AbortSignal.timeout(1500) });
      if (session.ok) {
        const response = await fetch(`${base}/api/system/status`, { signal: AbortSignal.timeout(12000) });
        if (response.ok && (await response.json()).runtime_id === identity) return;
      }
    } catch {}
    await pause(250);
  }
  throw Error('Isolated runtime did not start');
}
(async () => {
  let browser;
  try {
    await freePort(apiPort); await freePort(frontPort);
    const prepared = spawnSync(python, ['backend/scripts/prepare_demo.py', '--data-dir', directory, '--synthetic-only'], { cwd: root, env, windowsHide: true, encoding: 'utf8' });
    assert.equal(prepared.status, 0, prepared.stderr);
    const fixture = JSON.parse(prepared.stdout);
    assert.equal(fixture.real_paper_count, 0);
    const startBackend = () => launch(python, ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', String(apiPort)], { cwd: path.join(root, 'backend'), env });
    let server = startBackend();
    launch(process.execPath, ['node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', String(frontPort), '--strictPort'], { cwd: path.join(root, 'frontend'), env: { ...env, ATLAS_API_TARGET: api } });
    await ready();
    browser = await chromium.launch({ headless: true, ...(process.env.ATLAS_CHROME_PATH ? { executablePath: process.env.ATLAS_CHROME_PATH } : {}) });
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' });
    await context.route('**/*', route => ['127.0.0.1', 'localhost'].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort());
    const page = await context.newPage(); page.setDefaultTimeout(20000);
    page.on('pageerror', error => report.errors.push(error.message));
    const projectUrl = `${base}/research/${fixture.project_id}?tab=overview`;
    const get = async route => { const response = await page.request.get(`${api}${route}`); assert(response.ok(), route); return response.json(); };
    const savedBefore = await get(`/api/projects/${fixture.project_id}/snapshots/${fixture.snapshot_id}`);
    const beforeFacts = await get(`/api/projects/${fixture.project_id}/facts`);
    const method = beforeFacts.methods[0];
    await page.goto(projectUrl);
    await page.getByText('研究决策总览', { exact: true }).waitFor();
    const overview = page.locator('.research-decision-overview');
    assert(await overview.getByText('用户保存的选择理由', { exact: true }).isVisible());
    await page.screenshot({ path: path.join(output, 'decision-overview.png'), fullPage: true }); report.screenshots.push('decision-overview.png');
    report.checks.saved_decision_plan_and_snapshot_visible = true;
    await page.getByRole('tab', { name: '资料与证据', exact: true }).click();
    await page.getByRole('button', { name: '修订内容', exact: true }).first().click();
    const dialog = page.getByRole('dialog');
    await dialog.getByLabel('修订内容', { exact: true }).fill('Revised SyntheticProbe');
    await dialog.getByLabel('修订人', { exact: true }).fill('Browser acceptance');
    await dialog.getByLabel('修订理由', { exact: true }).fill('Original synthetic name correction');
    await dialog.getByRole('button', { name: '保存新版本', exact: true }).click();
    await dialog.waitFor({ state: 'hidden' });
    await page.reload();
    await page.getByText('Revised SyntheticProbe', { exact: true }).waitFor();
    const afterFacts = await get(`/api/projects/${fixture.project_id}/facts`);
    assert.equal(afterFacts.methods[0].name, 'Revised SyntheticProbe');
    assert.equal(afterFacts.methods[0].version, method.version + 1);
    assert.equal(afterFacts.methods[0].source_kind, 'user_input');
    assert.equal(afterFacts.methods[0].status, 'candidate');
    const stale = await page.request.patch(`${api}/api/projects/${fixture.project_id}/facts/${method.id}`, { data: { expected_version: method.version, changes: { name: 'Stale overwrite' }, evidence_ids: [], actor: 'Old browser', reason: 'Stale edit' } });
    assert.equal(stale.status(), 409);
    const savedAfter = await get(`/api/projects/${fixture.project_id}/snapshots/${fixture.snapshot_id}`);
    assert.deepEqual(savedAfter.plan, savedBefore.plan); assert.deepEqual(savedAfter.frozen_facts, savedBefore.frozen_facts);
    assert.equal(savedAfter.review_status, 'needs_review');
    report.checks.correction_persisted_with_conflict_and_snapshot_protection = true;
    await stop(server); server = startBackend(); await ready();
    await page.goto(projectUrl); await overview.getByText('Revised SyntheticProbe', { exact: true }).waitFor();
    report.checks.restart_retains_revision = true;
    await page.setViewportSize({ width: 390, height: 844 });
    await page.waitForTimeout(200);
    const width = await page.evaluate(() => ({ page: document.documentElement.scrollWidth, screen: innerWidth }));
    assert(width.page <= width.screen + 1, `Mobile overflow: ${JSON.stringify(width)}`);
    await page.screenshot({ path: path.join(output, 'decision-mobile.png'), fullPage: true }); report.screenshots.push('decision-mobile.png');
    report.checks.mobile_overview_fits = true;
    await overview.getByRole('link', { name: /查看快照/ }).click();
    await page.getByText('不可变快照 v1', { exact: true }).waitFor();
    report.checks.snapshot_print_route_opens = true;
    assert.deepEqual(report.errors, []);
  } catch (error) { report.errors.push(error.stack || error.message); process.exitCode = 1; }
  finally {
    if (browser) await browser.close();
    for (const child of children.reverse()) await stop(child);
    fs.writeFileSync(path.join(output, 'acceptance.json'), JSON.stringify(report, null, 2));
    console.log(JSON.stringify(report, null, 2));
  }
})();
