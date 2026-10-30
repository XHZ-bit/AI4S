// Current graph workspace acceptance. All data is original and isolated; no model calls.
const fs = require('node:fs');
const path = require('node:path');
const net = require('node:net');
const assert = require('node:assert/strict');
const {spawn, spawnSync} = require('node:child_process');
const root = path.resolve(__dirname, '../..');
const {chromium} = require(process.env.ATLAS_PLAYWRIGHT_PATH || path.join(root, 'frontend/node_modules/playwright'));
const output = path.resolve(process.argv[2] || path.join(root, '.ui_validation', `knowledge-${Date.now()}`));
assert(output.startsWith(path.join(root, '.ui_validation') + path.sep));
assert(!fs.existsSync(output), 'Choose a fresh acceptance directory');
fs.mkdirSync(output, {recursive: true});
const data = path.join(output, 'data');
const python = process.env.ATLAS_PYTHON || path.join(root, 'backend/.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
const api = 'http://127.0.0.1:18064', base = 'http://127.0.0.1:15264';
const env = {...process.env, ATLAS_ENV_FILE: '', DATA_DIR: data, ACCESS_MODE: 'local', REQUIRE_LOGIN: 'false',
  OFFLINE_MODE: 'true', DASHSCOPE_API_KEY: '', RESEARCH_MODEL_ENABLED: 'false',
  NEO4J_URI: 'bolt://127.0.0.1:1', GROBID_BASE_URL: 'http://127.0.0.1:1'};
const children = [], report = {fixture: 'original synthetic', model_calls: 0, checks: {}, errors: [], screenshots: []};
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
async function free(port) {
  await new Promise((resolve, reject) => {const server = net.createServer(); server.once('error', reject); server.listen(port, '127.0.0.1', () => server.close(resolve));});
}
function start(binary, args, cwd, childEnv) {
  const child = spawn(binary, args, {cwd, env: childEnv, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe']});
  children.push(child);
  child.on('error', e => report.errors.push(e.message));
  for (const stream of [child.stdout, child.stderr]) stream.on('data', chunk => fs.appendFileSync(path.join(output, 'servers.log'), chunk));
}
async function run() {
  let browser, page;
  try {
    await free(18064); await free(15264);
    const prepared = spawnSync(python, ['backend/scripts/prepare_demo.py', '--synthetic-only', '--data-dir', data], {cwd: root, env, encoding: 'utf8'});
    assert.equal(prepared.status, 0, prepared.stderr || prepared.stdout);
    const fixture = JSON.parse(fs.readFileSync(path.join(data, 'demo-manifest.json'), 'utf8'));
    const demo = fixture.unified_demo, pid = fixture.project_id, node = demo.node_ids['bounded:method'];
    start(python, ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '18064'], path.join(root, 'backend'), env);
    start(process.execPath, ['node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', '15264', '--strictPort'], path.join(root, 'frontend'), {...process.env, ATLAS_API_TARGET: api});
    let ready = false;
    for (let i = 0; i < 100; i++) {
      try {const response = await fetch(`${base}/api/system/status`, {signal: AbortSignal.timeout(2000)}); if (response.ok) {ready = true; break;}} catch {}
      await pause(200);
    }
    assert(ready, 'Isolated workspace did not become ready');
    browser = await chromium.launch({headless: true, ...(process.env.ATLAS_CHROME_PATH ? {executablePath: process.env.ATLAS_CHROME_PATH} : {})});
    const context = await browser.newContext({viewport: {width: 1440, height: 1000}, reducedMotion: 'reduce'});
    await context.route('**/*', route => ['127.0.0.1', 'localhost'].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort());
    page = await context.newPage(); page.setDefaultTimeout(15000);
    page.on('pageerror', error => report.errors.push(error.message));
    const shot = async name => {await page.screenshot({path: path.join(output, `${name}.png`), fullPage: true}); report.screenshots.push(`${name}.png`);};
    const project = `${base}/research/${pid}`;
    const graph = `${project}?view=graph&node=${node}`;
    await page.goto(base);
    await page.getByRole('heading', {name: '研究工作台', exact: true}).waitFor();
    await page.goto(graph);
    const inspector = page.getByRole('complementary', {name: '知识节点详情'});
    await inspector.getByRole('heading', {name: '方案 B：有界残差', exact: true}).waitFor();
    assert(await page.locator('.kw-graph-node').count() > 0);
    await shot('graph-desktop');
    await inspector.getByRole('button', {name: '阅读原文', exact: true}).click();
    await page.locator('.kw-source-highlight').waitFor();
    assert.equal(new URL(page.url()).searchParams.get('source'), demo.source_ids.bounded);
    await page.getByRole('button', {name: '返回原位置', exact: true}).click();
    await inspector.getByRole('heading', {name: '方案 B：有界残差', exact: true}).waitFor();
    report.checks.graph_node_evidence_and_return = true;

    await inspector.getByRole('button', {name: '深入学习', exact: true}).click();
    const progress = page.getByLabel('我的学习状态', {exact: true});
    const progressSaved = page.waitForResponse(response => response.url().endsWith(`/knowledge/nodes/${node}/progress`) && response.request().method() === 'PATCH' && response.ok());
    await progress.selectOption('in_progress');
    await progressSaved;
    await page.reload();
    await page.waitForFunction(() => document.querySelector('select[aria-label="我的学习状态"]')?.value === 'in_progress');
    await page.locator('.kw-prerequisite-map').waitFor();
    await page.locator('.kw-resource-explorer summary').click();
    await page.getByLabel('筛选学习资料类型').selectOption('image');
    await page.getByRole('button', {name: '查看图片', exact: true}).first().click();
    const image = page.locator('.kw-resource-preview img');
    await image.waitFor();
    await page.waitForFunction(() => {const img = document.querySelector('.kw-resource-preview img'); return img?.naturalWidth > 0;});
    assert.equal(await image.evaluate(img => img.naturalWidth), 600);
    await shot('learning-resources');
    report.checks.learning_progress_prerequisites_and_real_source_image = true;

    await page.goto(`${project}?view=compare&comparison=${demo.comparison_id}`);
    const rows = page.locator('.kw-comparison-table tbody tr');
    await rows.first().waitFor(); assert.equal(await rows.count(), 4);
    const row = rows.filter({hasText: '残差边界'});
    await row.getByRole('button', {name: '联动关系', exact: true}).click();
    await row.getByRole('button', {name: '修改或补充', exact: true}).last().click();
    const revision = 'CI 人工核对：仅残差有界，真实任务效果未知。';
    await page.getByLabel('比较内容', {exact: true}).fill(revision);
    await page.getByRole('button', {name: '保存修订', exact: true}).click();
    await page.getByText(revision, {exact: true}).waitFor();
    await page.reload(); await page.getByText(revision, {exact: true}).waitFor();
    report.checks.comparison_relation_and_revision_survive_reload = true;

    await page.goto(`${project}?view=practice&node=${node}`);
    const inputs = page.getByLabel('练习输入 JSON', {exact: true});
    await inputs.fill('{"alpha":0.5}');
    await page.getByRole('button', {name: '运行代码', exact: true}).click();
    await page.getByRole('heading', {name: '教学运行完成', exact: true}).waitFor({timeout: 60000});
    await page.locator('.kw-practice-result').getByText('2.482014', {exact: true}).first().waitFor();
    await inputs.fill('{"alpha":0}');
    await page.getByRole('button', {name: '运行代码', exact: true}).click();
    await page.getByRole('heading', {name: '教学运行完成', exact: true}).waitFor({timeout: 60000});
    const calculation = page.locator('.kw-practice-result > figure').filter({hasText: '同条件计算与导数核对'});
    assert.deepEqual(await calculation.locator('tbody tr').last().locator('td').allTextContents(), ['2', '2', '2', '1', '1']);
    assert.equal(await progress.inputValue(), 'in_progress');
    await page.getByRole('button', {name: '保存编辑稿', exact: true}).click();
    await page.reload(); await inputs.waitFor(); assert.equal(JSON.parse(await inputs.inputValue()).alpha, 0);
    await shot('practice');
    report.checks.real_python_recalculation_draft_persistence_and_no_auto_mastery = true;

    await page.goto(`${project}?view=materials`);
    await page.getByLabel('上传研究资料', {exact: true}).setInputFiles({name: 'ci-original-note.md', mimeType: 'text/markdown', buffer: Buffer.from('# CI 原创上传验收\n\n## 方法说明\n这里只检验原文保存和结构解析，不代表模型抽取成功。')});
    const uploaded = page.locator('.kw-source-list > li').filter({hasText: 'ci-original-note.md'});
    await uploaded.locator('.kw-stage-list li[data-status="done"]').first().waitFor({timeout: 30000});
    // All four phases must terminate; an unavailable model is explicitly partial.
    for (let i = 0; i < 120; i++) {
      if (await uploaded.locator('.kw-stage-list li[data-status="done"]').count() === 3 && await uploaded.locator('.kw-stage-list li[data-status="partial"]').count() === 1) break;
      await pause(250);
    }
    assert.equal(await uploaded.locator('.kw-stage-list li[data-status="done"]').count(), 3);
    assert.equal(await uploaded.locator('.kw-stage-list li[data-status="partial"]').count(), 1);
    await uploaded.getByRole('button', {name: '查看新增知识', exact: true}).click();
    await page.locator('.kw-graph-node').first().waitFor();
    assert(new URL(page.url()).searchParams.get('source'));
    report.checks.real_file_upload_stages_and_source_scoped_graph = true;

    await page.goto(graph); await inspector.getByRole('button', {name: '修订内容', exact: true}).click();
    const summary = 'CI 原创人工修订：残差有界不能推出总输出有界。';
    await page.getByLabel('节点解释', {exact: true}).fill(summary);
    await page.getByRole('button', {name: '保存修订', exact: true}).click();
    await inspector.getByText(summary, {exact: true}).waitFor();
    await page.reload(); await inspector.getByText(summary, {exact: true}).waitFor();
    await page.setViewportSize({width: 390, height: 844});
    await page.getByRole('button', {name: '切换到深色主题', exact: true}).click();
    await page.waitForFunction(() => document.documentElement.scrollWidth <= window.innerWidth + 1);
    await shot('graph-mobile-dark');
    report.checks.node_revision_and_mobile_dark_layout = true;
    assert.deepEqual(report.errors, []);
    report.passed = true;
  } catch (error) {
    report.passed = false; report.error = error.stack; process.exitCode = 1;
    if (page) await page.screenshot({path: path.join(output, 'failure.png'), fullPage: true}).catch(() => {});
  } finally {
    if (browser) await browser.close();
    for (const child of children.reverse()) if (child.exitCode === null) {
      const stopped = new Promise(resolve => child.once('exit', resolve)); child.kill(); await Promise.race([stopped, pause(2000)]);
    }
    fs.writeFileSync(path.join(output, 'report.json'), JSON.stringify(report, null, 2));
    console.log(JSON.stringify(report, null, 2));
  }
}
run().catch(error => {console.error(error); process.exitCode = 1;});
