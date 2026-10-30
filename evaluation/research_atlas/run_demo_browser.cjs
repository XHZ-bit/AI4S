// Real Chromium and real localhost APIs. Uses a prepared, isolated demo database.
const fs = require('node:fs');
const path = require('node:path');
const net = require('node:net');
const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const { chromium } = require(process.env.ATLAS_PLAYWRIGHT_PATH || '../../frontend/node_modules/playwright');

const root = path.resolve(__dirname, '../..');
const directory = path.resolve(process.argv[2] || '');
const output = path.resolve(process.argv[3] || '');
const manifest = JSON.parse(fs.readFileSync(path.join(directory, 'demo-manifest.json'), 'utf8'));
assert(directory.startsWith(path.join(root, '.ui_validation') + path.sep), 'Use an isolated acceptance directory');
assert(output.startsWith(path.join(root, '.ui_validation') + path.sep), 'Keep evidence in .ui_validation');
assert(manifest.project_id, 'Prepared demo must contain a synthetic project');
fs.mkdirSync(output, { recursive: true });
const apiPort = 18024, frontPort = 15194;
const api = `http://127.0.0.1:${apiPort}`, base = `http://127.0.0.1:${frontPort}`;
const identity = `demo-browser-${Date.now()}`;
const children = [], streams = [];
const report = {
  started_at: new Date().toISOString(), real_chromium: true,
  data_scope: 'pinned public PDFs plus explicitly synthetic project; no model calls',
  checks: {}, errors: [], expected_degradations: [], screenshots: [], blocked_external_requests: [],
};
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));

async function freePort(port) {
  const server = net.createServer();
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(port, '127.0.0.1', resolve); });
  await new Promise(resolve => server.close(resolve));
}
function launch(binary, args, name, options) {
  const log = fs.createWriteStream(path.join(output, `${name}.log`));
  streams.push(log);
  const child = spawn(binary, args, { windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'], ...options });
  child.stdout.pipe(log, { end: false }); child.stderr.pipe(log, { end: false });
  children.push(child); return child;
}
async function ready() {
  for (let attempt = 0; attempt < 60; attempt++) {
    if (children.some(child => child.exitCode !== null)) throw Error('A local server exited; inspect browser logs');
    try {
      const response = await fetch(`${base}/api/system/status`, { signal: AbortSignal.timeout(2500) });
      const status = await response.json();
      if (response.ok && status.runtime_id === identity) return status;
    } catch {}
    await pause(300);
  }
  throw Error('Local demo servers did not become ready');
}
async function stop(child) {
  if (child.exitCode !== null || child.signalCode !== null) return;
  const done = new Promise(resolve => child.once('exit', resolve));
  child.kill(); await done;
}

(async () => {
  let browser, page;
  const shot = async name => {
    const filename = `${name}.png`;
    await page.screenshot({ path: path.join(output, filename), fullPage: true });
    report.screenshots.push(filename);
  };
  const overflow = async () => {
    const widths = await page.evaluate(() => ({ viewport: innerWidth, content: document.documentElement.scrollWidth }));
    assert(widths.content <= widths.viewport + 1, JSON.stringify(widths));
    return widths;
  };
  try {
    await freePort(apiPort); await freePort(frontPort);
    launch(process.env.ATLAS_PYTHON || 'python', ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', String(apiPort)], 'backend', {
      cwd: path.join(root, 'backend'), env: {
        ...process.env, ATLAS_ENV_FILE: '', DATA_DIR: directory,
        DASHSCOPE_API_KEY: '', RESEARCH_MODEL_ENABLED: 'false',
        RUNTIME_MODE: 'local', RUNTIME_ID: identity,
        NEO4J_URI: 'bolt://127.0.0.1:1', GROBID_BASE_URL: 'http://127.0.0.1:1',
      },
    });
    launch(process.execPath, ['node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', String(frontPort), '--strictPort'], 'frontend', {
      cwd: path.join(root, 'frontend'), env: { ...process.env, ATLAS_API_TARGET: api },
    });
    const state = await ready();
    assert.equal(state.services.model.status, 'unconfigured');
    assert.equal(state.capabilities.research_model, false);
    assert.equal(state.services.database.status, 'available');
    report.checks.isolated_offline_runtime = true;
    const downloads = path.join(output, 'downloads');
    fs.mkdirSync(downloads, { recursive: true });
    browser = await chromium.launch({ headless: true, downloadsPath: downloads, executablePath: process.env.ATLAS_CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe' });
    report.browser_version = browser.version();
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce', acceptDownloads: true });
    await context.route('**/*', route => {
      const url = new URL(route.request().url());
      if (['127.0.0.1', 'localhost'].includes(url.hostname)) return route.continue();
      report.blocked_external_requests.push(url.origin);
      return route.abort();
    });
    context.on('page', opened => opened.on('pageerror', error => report.errors.push(error.message)));
    page = await context.newPage(); page.setDefaultTimeout(20000);
    page.on('response', response => {
      const pathname = new URL(response.url()).pathname;
      if (response.status() === 503 && !state.capabilities.graph && /^\/api\/projects\/[^/]+\/graph$/.test(pathname)) {
        if (!report.expected_degradations.includes('Neo4j snapshot projection unavailable in offline demo')) {
          report.expected_degradations.push('Neo4j snapshot projection unavailable in offline demo');
        }
      } else if (response.status() >= 500) report.errors.push(`HTTP ${response.status()} ${pathname}`);
    });

    console.log('Checking home and personalized route previews');
    await page.goto(base);
    await page.getByText('本地数据库：可用', { exact: true }).waitFor();
    await page.getByRole('link', { name: '体验个性化路线', exact: true }).click();
    const left = page.locator('.ant-card').filter({ has: page.locator('.ant-card-head-title', { hasText: '学习者 A · 机器人方向' }) });
    const right = page.locator('.ant-card').filter({ has: page.locator('.ant-card-head-title', { hasText: '学习者 B · 生成模型方向' }) });
    await left.getByRole('button', { name: '原文依据', exact: true }).first().waitFor();
    await right.getByRole('button', { name: '原文依据', exact: true }).first().waitFor();
    const phases = { robotics: await left.locator('strong').allTextContents(), generative: await right.locator('strong').allTextContents() };
    assert(phases.robotics.length >= 2 && phases.generative.length >= 2);
    assert.notDeepEqual(phases.robotics, phases.generative);
    report.initial_routes = phases; report.checks.profiles_produce_different_routes = true;
    await shot('personalized-desktop');
    await left.getByRole('button', { name: '原文依据', exact: true }).first().click();
    const modal = page.getByRole('dialog'); await modal.waitFor();
    assert((await modal.innerText()).includes('文档版本'));
    assert((await modal.locator('.ant-typography').innerText()).length > 40);
    report.checks.original_passage_modal = true; await shot('personalized-evidence');
    await modal.locator('.ant-modal-close').click();
    const changed = page.waitForResponse(response => response.url().endsWith('/api/roadmap/preview') && response.request().method() === 'POST');
    await left.locator('.ant-select-selection-item-remove').first().click();
    const changedResponse = await changed; assert.equal(changedResponse.status(), 200);
    const changedRoute = await changedResponse.json();
    assert(changedRoute.phases.length > phases.robotics.length);
    await left.getByText('未声明已掌握概念', { exact: false }).waitFor();
    report.checks.profile_edit_recomputes_route = true;
    for (const [width, height] of [[1280, 720], [390, 844]]) {
      await page.setViewportSize({ width, height }); await overflow(); await shot(`personalized-${width}`);
    }
    report.checks.personalized_projection_and_mobile_fit = true;
    await page.setViewportSize({ width: 1440, height: 1000 });
    await left.getByRole('link', { name: '论文工作区 ↗', exact: true }).first().click();
    await page.locator('.atlas-pdf-page .textLayer span').first().waitFor();
    const originalUid = new URL(page.url()).pathname.split('/')[2];
    assert(originalUid.startsWith('arxiv-'));
    const pdfResponse = await page.request.get(`${base}/api/papers/${originalUid}/file`);
    assert.equal(pdfResponse.status(), 200); assert((await pdfResponse.body()).subarray(0, 4).equals(Buffer.from('%PDF')));
    report.checks.original_paper_link_and_pdf_render = true; await shot('original-paper');

    console.log('Checking manual draft, save, refresh, snapshots and exports');
    await page.goto(`${base}/research/${manifest.project_id}?tab=plans`);
    await page.getByLabel('方案标题', { exact: true }).waitFor();
    await page.getByRole('button', { name: '人工创建空白草稿', exact: true }).click();
    const title = `浏览器验收人工方案：保存与快照 ${Date.now()}`;
    await page.getByLabel('方案标题', { exact: true }).fill(title);
    await page.getByLabel('方案目标', { exact: true }).fill('合成资料中的界面验收；不代表科学结论或实验成功。');
    await page.getByRole('button', { name: '添加步骤', exact: true }).click();
    await page.getByPlaceholder('步骤标题', { exact: true }).fill('核对原文与条件');
    await page.getByPlaceholder('目的', { exact: true }).fill('保留来源与未知项');
    await page.getByPlaceholder('操作，每行一步', { exact: true }).fill('阅读已保存原文\n记录比较条件');
    await page.getByPlaceholder('验收标准，每行一项', { exact: true }).fill('来源可定位\n没有编造实测成绩');
    await page.reload(); await page.getByLabel('方案标题', { exact: true }).waitFor();
    assert.equal(await page.getByLabel('方案标题', { exact: true }).inputValue(), title);
    assert.equal(await page.getByPlaceholder('步骤标题', { exact: true }).inputValue(), '核对原文与条件');
    report.checks.unsaved_draft_survives_refresh = true;
    const save = async () => {
      await page.getByRole('button', { name: '确认保存', exact: true }).click();
      const saving = page.waitForResponse(response => response.request().method() === 'PUT' && response.url().includes('/plans/'));
      await page.getByRole('button', { name: '保存新版本', exact: true }).click();
      const response = await saving; assert.equal(response.status(), 200);
      await page.getByRole('dialog').waitFor({ state: 'hidden' });
      return response.json();
    };
    const saved = await save(); assert.equal(saved.source_kind, 'user_input');
    await page.reload(); await page.getByLabel('方案标题', { exact: true }).waitFor();
    assert.equal(await page.getByLabel('方案标题', { exact: true }).inputValue(), title);
    report.checks.manual_save_and_saved_refresh = true;
    const snapshotResponse = page.waitForResponse(response => response.request().method() === 'POST' && response.url().endsWith('/snapshots'));
    await page.locator('.ant-timeline-item-content').filter({ hasText: title }).getByRole('button', { name: '创建不可变快照', exact: true }).click();
    const created = await snapshotResponse; assert.equal(created.status(), 201);
    const snapshot = await created.json(); report.snapshot_id = snapshot.id;
    const snapshotCard = page.locator('.ant-card-small').filter({ has: page.getByRole('button', { name: `快照 v${snapshot.snapshot_version}`, exact: true }) });
    await snapshotCard.waitFor(); report.checks.snapshot_created_through_ui = true;
    await page.getByText('课题图谱尚未接入', { exact: true }).waitFor();
    report.checks.snapshot_available_when_graph_is_unavailable = true;
    const download = async (label, filename) => {
      const pending = page.waitForEvent('download');
      await snapshotCard.getByRole('link', { name: label, exact: true }).click();
      const item = await pending; await item.saveAs(path.join(output, filename));
      assert.equal(await item.failure(), null);
      return fs.readFileSync(path.join(output, filename), 'utf8');
    };
    const jsonText = await download('导出 JSON', 'snapshot.json');
    const json = JSON.parse(jsonText); assert.equal(json.plan.title, title); assert.equal(json.plan.source_kind, 'user_input');
    const markdown = await download('导出 Markdown', 'snapshot.md'); assert(markdown.includes(title));
    report.checks.json_and_markdown_downloads = true;
    await shot('plan-snapshot-desktop');
    const popup = context.waitForEvent('page');
    await snapshotCard.getByRole('link', { name: '打印 / 保存 PDF', exact: true }).click();
    const printed = await popup; await printed.getByText('冻结引用', { exact: true }).waitFor();
    await printed.evaluate(() => document.fonts.ready);
    await printed.pdf({ path: path.join(output, 'snapshot.pdf'), format: 'A4', printBackground: true });
    await printed.screenshot({ path: path.join(output, 'snapshot-print.png'), fullPage: true });
    report.screenshots.push('snapshot-print.png'); await printed.close();
    report.checks.snapshot_pdf_export = true;
    await page.getByLabel('方案标题', { exact: true }).fill(`${title}（后续版本）`);
    const saved2 = await save(); assert.equal(saved2.version, saved.version + 1);
    const frozenResponse = await page.request.get(`${base}/api/projects/${manifest.project_id}/snapshots/${snapshot.id}/export?format=json`);
    assert.equal(frozenResponse.status(), 200);
    const updatedSnapshot = await frozenResponse.json();
    // The frozen payload stays immutable; its live review annotation changes.
    const { review_status: previousStatus, review_reasons: previousReasons, ...beforePayload } = json;
    const { review_status: currentStatus, review_reasons: currentReasons, ...afterPayload } = updatedSnapshot;
    assert.equal(previousStatus, 'current'); assert.deepEqual(previousReasons, []);
    assert.equal(currentStatus, 'needs_review'); assert(currentReasons.includes('验证方案已产生新版本'));
    assert.deepEqual(afterPayload, beforePayload);
    report.checks.old_snapshot_unchanged_after_plan_edit = true;
    report.checks.old_snapshot_review_flag_updates = true;
    await page.setViewportSize({ width: 390, height: 844 }); await overflow(); await shot('plan-mobile');
    report.checks.plan_mobile_fit = true;
    const versionSelect = page.locator('.research-plan-version .ant-select-selector');
    await versionSelect.evaluate(element => element.scrollIntoView({ block: 'center' }));
    await versionSelect.click();
    const options = page.locator('.research-plan-version-popup:visible');
    await options.waitFor();
    assert((await options.innerText()).includes(`${title}（后续版本）`));
    await overflow(); await shot('plan-mobile-versions');
    await page.keyboard.press('Escape');
    report.checks.long_version_titles_readable_on_mobile = true;
    assert.deepEqual(report.errors, []); report.passed = true;
  } catch (error) {
    report.failure = error.stack || String(error);
    if (page && !page.isClosed()) await shot('failure').catch(() => {});
    throw error;
  } finally {
    if (browser) await browser.close();
    await Promise.all(children.map(stop));
    await Promise.all(streams.map(stream => new Promise(resolve => stream.end(resolve))));
    report.finished_at = new Date().toISOString();
    fs.writeFileSync(path.join(output, 'demo-browser.json'), JSON.stringify(report, null, 2));
    console.log(JSON.stringify(report, null, 2));
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
