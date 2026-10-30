// UI checks use only a new synthetic workspace and loopback services.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { spawn, spawnSync } = require('node:child_process');
const root = path.resolve(__dirname, '../..');
const { chromium } = require(process.env.ATLAS_PLAYWRIGHT_PATH || path.join(root, 'frontend/node_modules/playwright'));
const directory = path.resolve(process.argv[2] || path.join(root, '.ui_validation', `ui-${Date.now()}`));
const allowed = ['.tmp', '.ui_validation'].map(name => path.join(fs.realpathSync(root), name));
assert(allowed.some(base => directory.startsWith(`${base}${path.sep}`)), 'Choose a new output inside .tmp/ or .ui_validation/');
assert(!fs.existsSync(directory), 'The output directory must not exist');
let parent = path.dirname(directory);
const parts = [path.basename(directory)];
while (!fs.existsSync(parent)) { parts.unshift(path.basename(parent)); parent = path.dirname(parent); }
assert(allowed.some(base => path.resolve(fs.realpathSync(parent), ...parts).startsWith(`${base}${path.sep}`)), 'Output must resolve inside the fixture roots');
const python = process.env.ATLAS_PYTHON || path.join(root, 'backend/.venv/Scripts/python.exe');
const api = 'http://127.0.0.1:18040', base = 'http://127.0.0.1:15210';
const env = { ...process.env, ATLAS_ENV_FILE: '', DATA_DIR: directory, ACCESS_MODE: 'local', OFFLINE_MODE: 'true',
  DASHSCOPE_API_KEY: '', RESEARCH_MODEL_ENABLED: 'false', RUNTIME_MODE: 'local', NEO4J_URI: 'bolt://127.0.0.1:1', GROBID_BASE_URL: 'http://127.0.0.1:1' };
const children = [], report = { fixture: 'synthetic-ui', checks: {}, errors: [], screenshots: [] };
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
function launch(binary, args, options) {
  const child = spawn(binary, args, { windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'], ...options });
  children.push(child);
  for (const stream of [child.stdout, child.stderr]) stream.on('data', chunk => fs.appendFileSync(path.join(directory, 'server.log'), chunk));
  return child;
}
async function stop(child) {
  if (child.exitCode !== null || child.signalCode !== null) return;
  const done = new Promise(resolve => child.once('exit', resolve)); child.kill(); await done;
}
(async () => {
  let browser, page;
  try {
    const prepared = spawnSync(python, [path.join(__dirname, 'prepare_platform_fixture.py'), '--output-dir', directory], { cwd: root, env, encoding: 'utf8', windowsHide: true });
    assert.equal(prepared.status, 0, prepared.stderr);
    const fixture = JSON.parse(prepared.stdout.trim());
    launch(python, ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '18040'], { cwd: path.join(root, 'backend'), env });
    launch(process.execPath, ['node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', '15210', '--strictPort'], { cwd: path.join(root, 'frontend'), env: { ...process.env, ATLAS_API_TARGET: api } });
    let ready = false;
    for (let i = 0; i < 100; i++) {
      try { const response = await fetch(`${base}/api/auth/session`, { signal: AbortSignal.timeout(1000) }); if (response.ok && (await response.json()).mode === 'local') { ready = true; break; } } catch {}
      await pause(300);
    }
    assert(ready, 'The isolated UI services did not become ready');
    browser = await chromium.launch({ headless: true, ...(process.env.ATLAS_CHROME_PATH ? { executablePath: process.env.ATLAS_CHROME_PATH } : {}) });
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' });
    await context.route('**/*', route => ['localhost', '127.0.0.1'].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort());
    page = await context.newPage(); page.setDefaultTimeout(20000);
    page.on('pageerror', error => report.errors.push(error.message));
    const shot = async (name, fullPage = false) => { const file = `${name}.png`; await page.screenshot({ path: path.join(directory, file), fullPage }); report.screenshots.push(file); };
    const fits = async label => {
      await page.waitForTimeout(180);
      const sizes = await page.evaluate(() => ({ viewport: innerWidth, content: document.documentElement.scrollWidth }));
      assert(sizes.content <= sizes.viewport + 1, `${label} overflows: ${JSON.stringify(sizes)}`);
    };
    assert((await page.request.patch(`${base}/api/library/papers/${fixture.paper_uid}`, { data: { starred: true, read_later: true } })).ok());
    await page.goto(base);
    await page.getByRole('heading', { name: '研究工作台', exact: true }).waitFor();
    await page.getByRole('region', { name: '稍后阅读预览' }).waitFor();
    await page.getByRole('link', { name: '导入研究资料', exact: true }).waitFor();
    const details = page.locator('.atlas-runtime-details');
    assert.equal(await details.getAttribute('open'), null);
    const skip = page.getByRole('link', { name: '跳到主要内容', exact: true });
    await skip.focus(); await skip.press('Enter');
    assert.equal(await page.evaluate(() => document.activeElement.id), 'atlas-main-content');
    await fits('desktop home'); await shot('ui-home-desktop');
    report.checks.home_prioritizes_real_work_and_collapses_service_details = true;

    await page.goto(`${base}/manage`);
    await page.getByRole('heading', { name: '我的论文', exact: true }).waitFor();
    await page.getByRole('button', { name: /^取消收藏：/ }).waitFor();
    const collection = page.getByRole('button', { name: /从 arXiv 采集/ });
    assert.equal(await collection.getAttribute('aria-expanded'), 'false');
    assert.equal(await page.getByRole('button', { name: /^采\s*集$/, exact: true }).count(), 0);
    await collection.click();
    await page.getByRole('button', { name: /^采\s*集$/, exact: true }).waitFor();
    await collection.click();
    const keyword = page.getByLabel('论文库关键词', { exact: true });
    await keyword.fill('no-such-ui-paper'); await keyword.press('Enter');
    await page.getByText('没有符合筛选条件的论文。', { exact: true }).waitFor();
    await page.getByRole('button', { name: '清空筛选', exact: true }).click();
    await page.getByRole('button', { name: /^取消收藏：/ }).waitFor();
    assert.equal(new URL(page.url()).searchParams.has('q'), false);
    await fits('desktop library'); await shot('ui-library-desktop');
    report.checks.library_filters_reset_and_arxiv_is_progressive_disclosure = true;

    const uploaded = page.waitForResponse(response => response.url().endsWith('/api/papers/upload-async') && response.request().method() === 'POST');
    const payload = fs.readFileSync(fixture.user_upload).toString('base64');
    await page.locator('.atlas-upload-dropzone').evaluate((element, encoded) => {
      const transfer = new DataTransfer();
      transfer.items.add(new File([Uint8Array.from(atob(encoded), letter => letter.charCodeAt(0))], 'ui-dropped-paper.pdf', { type: 'application/pdf' }));
      element.dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: transfer }));
    }, payload);
    const receipt = await (await uploaded).json(); assert(receipt.uid && receipt.task_id);
    await page.getByText('本地队列 1 份 · 解析完成 1 份', { exact: true }).waitFor({ timeout: 60000 });
    await shot('ui-upload-feedback-desktop');
    report.checks.real_pdf_drop_uses_queue_and_reaches_readable_completion = true;

    await page.goto(`${base}/papers/${receipt.uid}?tab=reading`);
    await page.locator('.atlas-canvas .atlas-reader canvas').first().waitFor();
    await shot('ui-reading-top-light-desktop');
    await page.getByRole('button', { name: '切换到深色主题' }).click();
    assert.equal(await page.locator('html').getAttribute('data-theme'), 'dark');
    assert.equal(await page.locator('.atlas-pdf-page').first().evaluate(element => getComputedStyle(element).backgroundColor), 'rgb(255, 255, 255)');
    await shot('ui-reading-top-dark-desktop');
    await page.reload();
    await page.locator('.atlas-canvas .atlas-reader canvas').first().waitFor();
    assert.equal(await page.locator('html').getAttribute('data-theme'), 'dark');
    await page.getByRole('button', { name: '切换到浅色主题' }).click();
    report.checks.theme_switch_persists_and_pdf_page_stays_white = true;
    assert.equal(await page.locator('.atlas-paper-options .ant-collapse-header').getAttribute('aria-expanded'), 'false');
    await page.getByText('资料与处理选项', { exact: true }).click();
    await page.getByRole('button', { name: '修正元数据', exact: true }).waitFor();
    await page.getByText('资料与处理选项', { exact: true }).click();
    await page.getByRole('navigation', { name: '阅读页内导航' }).getByRole('link', { name: '理解检查' }).click();
    await fits('desktop reading'); await shot('ui-reading-desktop');
    report.checks.reading_focuses_original_and_has_section_jumps = true;

    await page.setViewportSize({ width: 1024, height: 900 }); await page.goto(base);
    await page.getByRole('heading', { name: '研究工作台', exact: true }).waitFor();
    await fits('tablet home'); await shot('ui-home-tablet');
    report.checks.tablet_sidebar_keeps_navigation_reachable = true;

    await page.setViewportSize({ width: 390, height: 844 }); await page.goto(`${base}/manage`);
    await page.getByRole('button', { name: /^取消收藏：/ }).waitFor();
    assert.equal(await page.locator('.atlas-library table').count(), 0);
    assert((await page.locator('.atlas-library-paper').count()) > 0);
    await fits('mobile library'); await shot('ui-library-mobile', true);
    await page.getByRole('button', { name: '更多页面', exact: true }).click();
    const menu = page.getByRole('navigation', { name: '更多页面', exact: true }); await menu.waitFor();
    await shot('ui-mobile-more');
    await menu.getByRole('link', { name: '自动行动清单', exact: true }).click();
    await page.waitForURL(url => url.pathname === '/actions');
    await menu.waitFor({ state: 'hidden' }); await fits('mobile actions');
    report.checks.mobile_library_cards_and_more_navigation_are_usable = true;

    await page.getByRole('button', { name: '更多页面', exact: true }).click(); await menu.waitFor();
    await page.keyboard.press('Control+k');
    await page.getByRole('dialog', { name: '快速查找与跳转', exact: true }).waitFor();
    await menu.waitFor({ state: 'hidden' }); await page.waitForTimeout(450);
    assert(await page.getByRole('combobox', { name: '查找论文或页面' }).evaluate(element => element === document.activeElement));
    await page.keyboard.press('Escape');
    report.checks.mobile_menu_hands_keyboard_focus_to_global_search = true;

    const routes = ['/', '/research', '/workflow', '/actions', '/tasks', '/roadmap', '/cases/diffusion-policy-intro', '/graph', `/papers/${receipt.uid}?tab=reading`];
    for (const route of routes) {
      await page.goto(`${base}${route}`); await page.locator('#atlas-main-content').waitFor();
      await page.locator('#atlas-main-content h1, #atlas-main-content h2').first().waitFor();
      await page.waitForLoadState('networkidle');
      await fits(`mobile ${route}`);
    }
    await page.goto(base); await page.getByRole('heading', { name: '研究工作台', exact: true }).waitFor();
    await page.getByRole('region', { name: '稍后阅读预览' }).waitFor();
    await page.getByText(/^待执行 \d+ 项/).waitFor();
    await page.locator('.home-paper').first().waitFor();
    await page.locator('.home-runtime > summary').click();
    await page.getByText('本地数据库：可用', { exact: true }).waitFor();
    await shot('ui-home-mobile', true);
    report.checks.core_routes_fit_mobile_viewport = true;
    assert.deepEqual(report.errors, []); report.passed = true;
  } catch (error) {
    report.passed = false; report.errors.push(error.message); process.exitCode = 1;
    if (page) await page.screenshot({ path: path.join(directory, 'failure.png'), fullPage: true }).catch(() => {});
  } finally {
    await browser?.close(); for (const child of children.reverse()) await stop(child);
    fs.mkdirSync(directory, { recursive: true }); fs.writeFileSync(path.join(directory, 'ui-browser-report.json'), JSON.stringify(report, null, 2));
    console.log(JSON.stringify(report));
  }
})();
