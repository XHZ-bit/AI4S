// Opt-in Chromium interaction validation. Requires an isolated fixture/server.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.ATLAS_PLAYWRIGHT_PATH || 'playwright');

(async () => {
  const dir = path.resolve(process.argv[2]);
  const manifest = JSON.parse(fs.readFileSync(path.join(dir, 'browser-fixture.json'), 'utf8'));
  assert.equal(manifest.fixture_kind, 'synthetic_browser_validation');
  const browser = await chromium.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  // External traffic is blocked; localhost uses the real application/API.
  await context.route('**/*', route => {
    const url = new URL(route.request().url());
    return ['127.0.0.1', 'localhost'].includes(url.hostname) ? route.continue() : route.abort();
  });
  const base = 'http://127.0.0.1:15173';
  const url = `${base}/research/${manifest.project_id}?tab=plans`;
  const report = { real_chromium: true, synthetic_input: true, checks: {}, errors };
  try {
    await page.goto(url);
    await page.getByLabel('方案标题', { exact: true }).waitFor();
    await page.getByRole('button', {name:'人工创建空白草稿', exact:true}).click();
    const title = '真实浏览器人工方案：刷新与保存验收';
    await page.getByLabel('方案标题', {exact:true}).click();
    await page.keyboard.type(title);
    await page.getByLabel('方案目标', {exact:true}).click();
    await page.keyboard.type('仅验证产品交互；显存、耗时和科研结果保持未知。');
    await page.getByRole('button', {name:'添加步骤', exact:true}).click();
    await page.getByPlaceholder('步骤标题', {exact:true}).fill('核对来源与未知项');
    await page.getByPlaceholder('目的', {exact:true}).fill('保留文献报告与用户输入区别');
    await page.getByPlaceholder('操作，每行一步', {exact:true}).fill('阅读证据\n记录未知项');
    await page.getByPlaceholder('验收标准，每行一项', {exact:true}).fill('两个设置不混合');
    await page.reload();
    await page.getByLabel('方案标题', {exact:true}).waitFor();
    assert.equal(await page.getByLabel('方案标题', {exact:true}).inputValue(), title);
    assert.equal(await page.getByPlaceholder('步骤标题', {exact:true}).inputValue(), '核对来源与未知项');
    report.checks.unsaved_refresh_recovery = true;
    await page.getByRole('button', {name:'确认保存', exact:true}).click();
    const response = page.waitForResponse(r => r.request().method() === 'PUT' && r.url().includes('/plans/'));
    await page.getByRole('button', {name:'保存新版本', exact:true}).click();
    const savedResponse = await response;
    assert.equal(savedResponse.status(), 200);
    const saved = await savedResponse.json();
    assert.equal(saved.source_kind, 'user_input');
    assert.equal(saved.title, title);
    report.checks.mouse_keyboard_edit_save = true;
    report.saved_plan_id = saved.id;
    await page.reload();
    await page.getByLabel('方案标题', {exact:true}).waitFor();
    assert.equal(await page.getByLabel('方案标题', {exact:true}).inputValue(), title);
    report.checks.saved_refresh_recovery = true;
    await page.screenshot({path:path.join(dir,'desktop-interaction.png'),fullPage:true});
    await page.setViewportSize({width:390,height:844});
    await page.getByLabel('方案标题', {exact:true}).scrollIntoViewIfNeeded();
    const dimensions = await page.evaluate(() => ({width:innerWidth,scroll:document.documentElement.scrollWidth}));
    report.checks.narrow_dimensions = dimensions;
    await page.screenshot({path:path.join(dir,'narrow-interaction.png'),fullPage:true});
    assert(dimensions.scroll <= dimensions.width + 1, `Narrow overflow: ${JSON.stringify(dimensions)}`);
    await page.getByLabel('方案目标', {exact:true}).click();
    await page.keyboard.press('End');
    await page.keyboard.type(' 窄屏编辑保留。');
    // Actual browser network-offline mode: preserve the already-loaded editable draft.
    await context.setOffline(true);
    await page.getByRole('button', {name:'确认保存', exact:true}).click();
    await page.getByRole('button', {name:'保存新版本', exact:true}).click();
    await page.getByText('方案操作失败', {exact:true}).waitFor();
    assert((await page.getByLabel('方案目标', {exact:true}).inputValue()).includes('窄屏编辑保留'));
    report.checks.offline_failed_save_preserves_draft = true;
    await context.setOffline(false);
    await page.reload();
    await page.getByLabel('方案目标', {exact:true}).waitFor();
    assert((await page.getByLabel('方案目标', {exact:true}).inputValue()).includes('窄屏编辑保留'));
    report.checks.reconnect_refresh_recovers_draft = true;
    await page.setViewportSize({width:1440,height:1000});
    await page.goto(`${base}/research/${manifest.project_id}/print/${manifest.snapshot_id}`);
    await page.getByText('冻结引用', {exact:true}).waitFor();
    await page.evaluate(() => document.fonts.ready);
    await page.pdf({path:path.join(dir,'validated-snapshot.pdf'),format:'A4',printBackground:true});
    await page.screenshot({path:path.join(dir,'print-page.png'),fullPage:true});
    report.checks.print_pdf = true;
    assert.deepEqual(errors, []);
  } finally {
    fs.writeFileSync(path.join(dir,'live-browser.json'),JSON.stringify(report,null,2));
    await browser.close();
  }
  console.log(JSON.stringify(report));
})().catch(error => { console.error(error); process.exitCode=1; });
