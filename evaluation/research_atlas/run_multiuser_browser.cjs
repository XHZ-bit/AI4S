// Synthetic identities and independent data; never writes credentials to the report.
const fs = require('node:fs');
const path = require('node:path');
const { spawn, spawnSync } = require('node:child_process');
const { randomBytes } = require('node:crypto');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../..');
const { chromium } = require(process.env.ATLAS_PLAYWRIGHT_PATH || path.join(root, 'frontend/node_modules/playwright'));
const directory = path.resolve(process.argv[2] || path.join(root, '.tmp', `multiuser-browser-${Date.now()}`));
const allowedRoots = ['.tmp', '.ui_validation'].map(name => path.join(fs.realpathSync(root), name));
assert(allowedRoots.some(allowed => directory.startsWith(`${allowed}${path.sep}`)), 'Output must be a new directory inside workspace .tmp/ or .ui_validation/');
assert(!fs.existsSync(directory), 'Output directory already exists; use a fresh fixture directory');
let ancestor = path.dirname(directory);
const missing = [path.basename(directory)];
while (!fs.existsSync(ancestor)) { missing.unshift(path.basename(ancestor)); ancestor = path.dirname(ancestor); }
const resolvedOutput = path.resolve(fs.realpathSync(ancestor), ...missing);
assert(allowedRoots.some(allowed => resolvedOutput.startsWith(`${allowed}${path.sep}`)), 'Output resolves outside the allowed fixture roots');
fs.mkdirSync(directory, { recursive: true });
const python = process.env.ATLAS_PYTHON || 'python';
const api = 'http://127.0.0.1:18030', base = 'http://127.0.0.1:15200';
const secrets = { admin: randomBytes(20).toString('base64url'), alice: randomBytes(20).toString('base64url'), bob: randomBytes(20).toString('base64url'), charlie: randomBytes(20).toString('base64url'), changed: randomBytes(20).toString('base64url') };
const redact = value => Object.values(secrets).reduce((text, secret) => text.split(secret).join('[redacted]'), String(value));
const env = { ...process.env, ATLAS_ENV_FILE: '', DATA_DIR: directory, ACCESS_MODE: 'multiuser', SESSION_SECURE_COOKIE: 'false', DASHSCOPE_API_KEY: '', RESEARCH_MODEL_ENABLED: 'false', RUNTIME_MODE: 'local', NEO4J_URI: 'bolt://127.0.0.1:1', GROBID_BASE_URL: 'http://127.0.0.1:1' };
const report = { fixture: 'synthetic-isolated-multiuser', checks: {}, errors: [], screenshots: [] };
const children = [];
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
function launch(binary, args, options) {
  const child = spawn(binary, args, { windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'], ...options });
  children.push(child);
  for (const stream of [child.stdout, child.stderr]) stream.on('data', chunk => fs.appendFileSync(path.join(directory, 'server.log'), redact(chunk.toString())));
  return child;
}
async function stop(child) {
  if (child.exitCode !== null || child.signalCode !== null) return;
  const exited = new Promise(resolve => child.once('exit', resolve));
  child.kill(); await exited;
}
async function login(page, username, password) {
  await page.goto(base);
  await page.getByLabel('用户名', { exact: true }).fill(username);
  await page.getByLabel('密码', { exact: true }).fill(password);
  await page.getByRole('button', { name: /^登\s*录$/ }).click();
  await page.getByText(`当前账号：${username}`, { exact: true }).waitFor();
}
async function task(request, id) {
  const end = Date.now() + 60000;
  while (Date.now() < end) {
    const response = await request.get(`${base}/api/learning/tasks/${id}`);
    assert(response.ok(), `Task polling HTTP ${response.status()}`);
    const value = await response.json();
    if (['done', 'failed', 'cancelled', 'interrupted'].includes(value.status)) return value;
    await pause(200);
  }
  throw Error('Synthetic PDF parsing did not finish in 60 seconds');
}
(async () => {
  let browser, page;
  try {
    const prepared = spawnSync(python, ['-c', `import json,sys\nfrom pathlib import Path\nimport pymupdf\nfrom app.accounts import create_user\nfrom app.config import get_settings\nsecrets=json.load(sys.stdin)\nfor name in ('admin','alice','bob'): create_user(name,secrets[name],'admin' if name=='admin' else 'user')\np=Path(get_settings().data_dir)/'synthetic-input.pdf'\nwith pymupdf.open() as pdf:\n page=pdf.new_page();page.insert_text((72,72),'Synthetic personal research input');page.insert_text((72,110),'This is an acceptance fixture, not a scientific result.');[pdf.new_page().insert_text((72,72),f'Synthetic continuation page {i}') for i in (2,3)];pdf.save(p)\nsecond=p.with_name('synthetic-companion.pdf')\nwith pymupdf.open() as pdf:\n page=pdf.new_page();page.insert_text((72,72),'Synthetic queue companion');pdf.save(second)\nbad=p.with_name('synthetic-invalid.pdf');bad.write_bytes(b'Not a PDF acceptance fixture')\nprint(json.dumps({'pdf':str(p),'second_pdf':str(second),'invalid_pdf':str(bad)}))`], { cwd: path.join(root, 'backend'), env, input: JSON.stringify(secrets), encoding: 'utf8', windowsHide: true });
    assert.equal(prepared.status, 0, redact(prepared.stderr));
    const fixture = JSON.parse(prepared.stdout.trim());
    launch(python, ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '18030'], { cwd: path.join(root, 'backend'), env });
    launch(process.execPath, ['node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', '15200', '--strictPort'], { cwd: path.join(root, 'frontend'), env: { ...process.env, ATLAS_API_TARGET: api } });
    let ready = false;
    for (let i = 0; i < 100; i++) {
      try {
        const response = await fetch(`${base}/api/auth/session`, { signal: AbortSignal.timeout(1000) });
        if (response.ok && (await response.json()).mode === 'multiuser') { ready = true; break; }
      } catch { /* Wait for the isolated processes to become ready. */ }
      await pause(300);
    }
    assert(ready, 'The isolated multiuser environment did not become ready');
    browser = await chromium.launch({ headless: true, ...(process.env.ATLAS_CHROME_PATH ? { executablePath: process.env.ATLAS_CHROME_PATH } : {}) });
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' });
    await context.route('**/*', route => ['localhost', '127.0.0.1'].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort());
    page = await context.newPage(); page.setDefaultTimeout(20000);
    page.on('pageerror', error => report.errors.push(redact(error.message)));
    const shot = async name => { await page.screenshot({ path: path.join(directory, `${name}.png`), fullPage: true }); report.screenshots.push(`${name}.png`); };
    await page.goto(base); await page.getByRole('button', { name: /^登\s*录$/ }).waitFor();
    assert.equal((await page.request.get(`${base}/api/papers`)).status(), 401);
    report.checks.anonymous_api_and_workspace_blocked = true;
    await login(page, 'alice', secrets.alice);
    await page.goto(`${base}/manage`);
    await page.getByText(/^当前上传配额：/).waitFor();
    assert.equal(await page.getByRole('button', { name: /^采\s*集$/ }).count(), 0);
    await page.getByText('多人试用暂未开放联网采集，请上传 PDF 添加到自己的论文库。', { exact: true }).waitFor();
    assert(await page.getByRole('button', { name: '批量抽取', exact: true }).isDisabled());
    report.checks.actual_upload_limits_and_restricted_actions_explained = true;
    const uploading = page.waitForResponse(response => response.url().endsWith('/api/papers/upload-async') && response.request().method() === 'POST');
    await page.locator('input[type=file]').setInputFiles(fixture.pdf);
    const uploaded = await (await uploading).json(); assert(uploaded.uid && uploaded.task_id);
    assert.equal((await task(page.request, uploaded.task_id)).status, 'done');
    await page.getByRole('button', { name: '刷新列表', exact: true }).click();
    const starred = page.waitForResponse(response => response.url().includes(`/api/library/papers/${uploaded.uid}`) && response.request().method() === 'PATCH');
    await page.getByRole('button', { name: /^收藏：/ }).click();
    assert.equal((await (await starred).json()).starred, true);
    await page.getByRole('button', { name: /^取消收藏：/ }).waitFor();
    const later = page.waitForResponse(response => response.url().includes(`/api/library/papers/${uploaded.uid}`) && response.request().method() === 'PATCH');
    await page.getByRole('button', { name: /^加入稍后阅读：/ }).click();
    assert.equal((await (await later).json()).read_later, true);
    await page.reload();
    await page.getByRole('button', { name: /^取消收藏：/ }).waitFor();
    await page.getByRole('button', { name: /^移出稍后阅读：/ }).waitFor();
    await page.getByText('收藏', { exact: true }).click(); // AntD's radio label is the visible click target.
    await page.waitForURL(url => url.searchParams.get('filter') === 'starred');
    assert.equal(new URL(page.url()).searchParams.get('filter'), 'starred');
    await page.getByRole('button', { name: /^取消收藏：/ }).waitFor();
    await page.goto(base);
    await page.getByRole('region', { name: '稍后阅读预览' }).waitFor();
    await shot('multiuser-read-later-home');
    report.checks.library_flags_persist_after_reload_and_home_preview = true;
    await page.keyboard.press('Control+k');
    const launcher = page.getByRole('combobox', { name: '查找论文或页面' });
    await launcher.fill('personal');
    await page.getByRole('option').filter({ hasText: 'Synthetic personal research input' }).waitFor();
    await page.keyboard.press('Enter');
    await page.waitForURL(url => url.pathname === `/papers/${uploaded.uid}`);
    await page.getByRole('checkbox', { name: 'Page 1', exact: true }).waitFor();
    await page.getByRole('checkbox', { name: 'Page 1', exact: true }).focus();
    await page.keyboard.press('Control+Shift+k');
    await page.getByRole('dialog', { name: '在当前工作空间中查找' }).waitFor();
    await page.keyboard.press('Control+k');
    await page.getByRole('dialog', { name: '快速查找与跳转' }).waitFor();
    await page.getByRole('dialog', { name: '在当前工作空间中查找' }).waitFor({ state: 'hidden' });
    await page.waitForTimeout(400); // Finish the old dialog's focus-restoration animation.
    assert(await launcher.evaluate(element => element === document.activeElement), 'The new launcher must keep keyboard focus after switching dialogs');
    await page.keyboard.press('Escape');
    await page.getByRole('dialog', { name: '快速查找与跳转' }).waitFor({ state: 'hidden' });
    await page.getByRole('checkbox', { name: 'Page 1', exact: true }).focus();
    await page.keyboard.press('Control+k');
    await launcher.waitFor();
    await page.keyboard.press('Control+Shift+k');
    const contextSearch = page.getByRole('dialog', { name: '在当前工作空间中查找' });
    await contextSearch.waitFor();
    await page.waitForTimeout(400);
    assert(await contextSearch.getByPlaceholder('查找资源、缺口和下一步…').evaluate(element => element === document.activeElement), 'A reopened context search must retain input focus after switching from the launcher');
    await page.keyboard.press('Escape');
    await contextSearch.waitFor({ state: 'hidden' });
    report.checks.global_keyboard_search_and_workspace_shortcuts_do_not_stack = true;
    await page.setViewportSize({ width: 390, height: 844 });
    await page.getByRole('button', { name: '快速查找与跳转', exact: true }).click();
    await launcher.fill('处理进度');
    const narrowDialog = page.getByRole('dialog', { name: '快速查找与跳转' });
    const bounds = await narrowDialog.boundingBox();
    assert(bounds && bounds.x >= 0 && bounds.x + bounds.width <= 391);
    await shot('multiuser-mobile-quick-launcher');
    await page.getByRole('option').filter({ hasText: '处理进度' }).first().click();
    await page.waitForURL(url => url.pathname === '/tasks');
    await page.goto(`${base}/manage?filter=starred`);
    await page.getByRole('button', { name: /^取消收藏：/ }).waitFor();
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), 'The mobile library must keep horizontal scrolling inside the table');
    await page.setViewportSize({ width: 1440, height: 1000 });
    report.checks.mobile_launcher_reaches_navigation_outside_bottom_bar = true;
    await page.goto(`${base}/manage`);
    const search = page.getByRole('searchbox', { name: '论文检索关键词' });
    await search.fill('personal');
    const searched = page.waitForResponse(response => response.url().includes('/api/search/v2?') && response.request().method() === 'GET');
    await search.press('Enter');
    const matches = await (await searched).json();
    const match = matches.items.find(item => item.uid === uploaded.uid);
    assert(match?.passage_id && match.quote.includes('personal') && match.page === 1);
    await page.getByRole('link', { name: '查看原文', exact: true }).click();
    await page.getByRole('heading', { name: '来源定位', exact: true }).waitFor();
    assert.equal(new URL(page.url()).searchParams.get('focus'), match.passage_id);
    assert.equal(new URL(page.url()).searchParams.get('page'), '1');
    await page.locator('.atlas-pdf-page canvas').first().waitFor({ timeout: 30000 });
    await shot('multiuser-search-source');
    report.checks.personal_search_quote_page_and_source_navigation = true;
    await page.goto(`${base}/papers/${uploaded.uid}?tab=reading`);
    await page.getByRole('checkbox', { name: 'Page 1', exact: true }).check();
    await page.getByText('记录已保存', { exact: true }).waitFor();
    const saved = await (await page.request.get(`${base}/api/learning/papers/${uploaded.uid}`)).json();
    assert(Object.values(saved.state.reading).some(Boolean));
    assert.equal((await page.request.get(`${base}/api/papers/${uploaded.uid}/file`)).status(), 200);
    await page.locator('.atlas-pdf-page canvas').first().waitFor({ timeout: 30000 });
    await shot('multiuser-alice-reading');
    report.checks.personal_pdf_upload_parse_reading_save_and_original = true;
    const documentId = saved.documents[0].id;
    const mainReader = page.locator('.atlas-canvas .atlas-reader');
    const pageNumber = mainReader.getByRole('spinbutton', { name: 'PDF 页码' });
    const moved = page.waitForResponse(response => response.url().includes('/reading-position') && response.request().method() === 'PUT');
    await pageNumber.fill('2'); await pageNumber.press('Enter');
    assert.equal((await (await moved).json()).position.page, 2);
    await page.getByText('阅读位置已保存：第 2 页。', { exact: true }).waitFor();
    await page.goto(`${base}/papers/${uploaded.uid}?tab=reading`);
    await page.getByText('已恢复上次阅读位置：第 2 页。', { exact: true }).waitFor();
    assert.equal(new URL(page.url()).searchParams.get('page'), '2');
    await pageNumber.waitFor(); assert.equal(await pageNumber.inputValue(), '2');
    await page.goto(`${base}/papers/${uploaded.uid}?tab=reading&page=1`);
    await pageNumber.waitFor(); assert.equal(await pageNumber.inputValue(), '1');
    const zoom = mainReader.getByRole('combobox', { name: 'PDF 缩放' });
    await zoom.focus(); await zoom.press('ArrowDown'); await page.locator('.ant-select-dropdown:visible').getByText('100%', { exact: true }).click();
    await page.setViewportSize({ width: 390, height: 844 }); await page.waitForTimeout(300);
    assert.equal(await mainReader.locator('.ant-select-selection-item').textContent(), '100%');
    await page.setViewportSize({ width: 1440, height: 1000 }); await page.waitForTimeout(300);
    assert.equal(await mainReader.locator('.ant-select-selection-item').textContent(), '100%');
    await zoom.focus(); await zoom.press('ArrowDown'); await page.locator('.ant-select-dropdown:visible').getByText('适应宽度', { exact: true }).click();
    assert.equal(await mainReader.locator('.ant-select-selection-item').textContent(), '适应宽度');
    assert.equal((await (await page.request.get(`${base}/api/papers/${uploaded.uid}/reading-position?document_id=${documentId}`)).json()).position.page, 2);
    await shot('multiuser-reading-resume-and-zoom');
    report.checks.reading_position_resumes_but_explicit_evidence_page_wins = true;
    report.checks.fixed_pdf_zoom_survives_mobile_and_desktop_resize = true;

    await page.getByRole('link', { name: '生成自动行动清单', exact: true }).click();
    await page.getByLabel('行动清单名称').fill('Synthetic personal action list');
    await page.getByRole('button', { name: '预览自动行动清单', exact: true }).click();
    await page.getByRole('button', { name: '保存自动行动清单', exact: true }).click();
    await page.locator('.ant-card-head-title').filter({ hasText: 'Synthetic personal action list · v1' }).waitFor();
    await page.reload();
    await page.locator('.ant-card-head-title').filter({ hasText: 'Synthetic personal action list · v1' }).waitFor();
    report.checks.personal_action_preview_save_and_reload = true;
    await page.evaluate(() => localStorage.setItem('atlas:paper-input:private', 'synthetic private draft'));
    await page.getByRole('button', { name: '退出登录', exact: true }).click();
    await page.getByRole('button', { name: /^登\s*录$/ }).waitFor();
    assert.equal(await page.evaluate(() => localStorage.getItem('atlas:paper-input:private')), null);
    await login(page, 'bob', secrets.bob);
    const bobPapers = await (await page.request.get(`${base}/api/papers`)).json();
    assert.equal(bobPapers.total, 0);
    assert.deepEqual(await (await page.request.get(`${base}/api/library/summary`)).json(), { all: 0, starred: 0, read_later: 0 });
    assert.equal((await (await page.request.get(`${base}/api/library/papers?filter=read_later`)).json()).total, 0);
    assert.equal((await page.request.get(`${base}/api/papers/${uploaded.uid}/file`)).status(), 404);
    assert.equal((await (await page.request.get(`${base}/api/actions/v1`)).json()).total, 0);
    await shot('multiuser-bob-isolated');
    report.checks.logout_clears_drafts_and_second_user_cannot_access_saved_data = true;
    report.checks.second_user_cannot_see_library_flags = true;
    assert.equal((await page.request.get(`${base}/api/papers/${uploaded.uid}/reading-position?document_id=${documentId}`)).status(), 404);
    report.checks.second_user_cannot_read_another_reading_position = true;
    await page.getByRole('button', { name: '退出登录', exact: true }).click();
    await login(page, 'admin', secrets.admin);
    await page.getByRole('button', { name: '账号管理', exact: true }).click();
    await page.getByLabel('新账号用户名').fill('charlie');
    await page.getByLabel('新账号初始密码').fill(secrets.charlie);
    await page.getByRole('button', { name: '创建用户账号', exact: true }).click();
    const row = page.getByRole('row').filter({ has: page.getByRole('cell', { name: 'charlie', exact: true }) });
    await row.waitFor();
    const second = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' });
    const charlie = await second.newPage(); charlie.setDefaultTimeout(20000);
    await login(charlie, 'charlie', secrets.charlie);
    await row.getByRole('button', { name: '停用账号', exact: true }).click();
    await row.getByRole('cell', { name: '已停用', exact: true }).waitFor();
    assert.equal((await charlie.request.get(`${base}/api/papers`)).status(), 401);
    await charlie.reload(); await charlie.getByRole('button', { name: /^登\s*录$/ }).waitFor();
    await shot('multiuser-admin-accounts');
    report.checks.admin_creation_disabling_and_immediate_session_revocation = true;
    await second.close();
    await page.getByRole('button', { name: /^(Close|关闭)$/ }).click();
    await page.getByRole('button', { name: '退出登录', exact: true }).click();
    await login(page, 'alice', secrets.alice);
    await page.getByRole('button', { name: '修改密码', exact: true }).click();
    await page.getByLabel('当前密码', { exact: true }).fill(secrets.alice);
    await page.getByLabel('新密码', { exact: true }).fill(secrets.changed);
    await page.getByRole('button', { name: '保存新密码并退出', exact: true }).click();
    await page.getByText('密码已修改，全部会话已退出，请重新登录。', { exact: true }).waitFor();
    await login(page, 'alice', secrets.changed);
    assert.equal((await (await page.request.get(`${base}/api/papers`)).json()).total, 1);
    const retainedFlags = await (await page.request.get(`${base}/api/library/papers?filter=read_later`)).json();
    assert.equal(retainedFlags.total, 1);
    assert.equal(retainedFlags.items[0].starred, true);
    assert.equal(retainedFlags.items[0].read_later, true);
    report.checks.library_flags_survive_logout_password_change_and_relogin = true;
    report.checks.password_change_reauthentication_and_data_persistence = true;
    assert.equal((await (await page.request.get(`${base}/api/papers/${uploaded.uid}/reading-position?document_id=${documentId}`)).json()).position.page, 2);
    await page.goto(`${base}/manage`);
    let unblock, held;
    const gate = new Promise(resolve => { unblock = resolve; });
    const firstPoll = new Promise(resolve => { held = resolve; });
    let holdUsed = false, uploadRequests = 0;
    const countUploads = request => { if (request.method() === 'POST' && request.url().endsWith('/api/papers/upload-async')) uploadRequests++; };
    page.on('request', countUploads);
    await page.route('**/api/learning/tasks/*', async route => {
      if (!holdUsed) { holdUsed = true; held(); await gate; }
      await route.continue();
    });
    await page.locator('input[type=file]').setInputFiles([fixture.pdf, fixture.invalid_pdf, fixture.second_pdf]);
    try {
      await Promise.race([firstPoll, pause(20000).then(() => { throw Error('Queue did not poll its accepted task'); })]);
      await pause(250);
      assert.equal(uploadRequests, 1, 'The second file must wait until the first parse task reaches a terminal state');
    } finally { unblock(); }
    await page.getByText(/本地队列 3 份 · 解析完成 2 份/).waitFor({ timeout: 60000 });
    assert.equal(uploadRequests, 3);
    await page.getByText('服务器拒绝本次提交：文件不是有效的 PDF', { exact: true }).waitFor();
    assert.equal((await (await page.request.get(`${base}/api/papers`)).json()).total, 2);
    await page.unroute('**/api/learning/tasks/*'); page.removeListener('request', countUploads);
    await page.setViewportSize({ width: 390, height: 844 });
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), 'The mobile upload queue must remain inside the viewport');
    await shot('multiuser-sequential-upload-queue');
    report.checks.batch_upload_waits_for_parse_and_continues_after_invalid_pdf = true;

    assert.deepEqual(report.errors, []);
    report.passed = true;
  } catch (error) {
    report.passed = false; report.errors.push(redact(error.message)); process.exitCode = 1;
    if (page) await page.screenshot({ path: path.join(directory, 'failure.png'), fullPage: true }).catch(() => {});
  }
  finally {
    await browser?.close();
    for (const child of children.reverse()) await stop(child);
    fs.writeFileSync(path.join(directory, 'multiuser-browser-report.json'), JSON.stringify(report, null, 2));
    console.log(JSON.stringify(report));
  }
})();
