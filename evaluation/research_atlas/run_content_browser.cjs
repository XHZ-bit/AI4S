/* Desktop engineering acceptance. Start prepare_content_fixture.py, offline API and Vite first.
 * Usage: node evaluation/research_atlas/run_content_browser.cjs [fixture directory] [base URL]
 * The fixture uses authored teaching material and deterministic model HTTP responses.
 * Runtime actions use local checks/manual review only; no live model requests are allowed.
 */
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const {chromium} = require('../../frontend/node_modules/playwright');
const directory = path.resolve(process.argv[2] || '.ui_validation/content-platform-20261116');
const base = process.argv[3] || 'http://127.0.0.1:15296';
const fixture = JSON.parse(fs.readFileSync(path.join(directory, 'fixture.json'), 'utf8').replace(/^\uFEFF/, ''));
const report = {started_at: new Date().toISOString(), fixture: directory, source_kind: fixture.source_kind,
  model_stub: fixture.model_stub, real_provider_calls: fixture.real_provider_calls, checks: [], screenshots: [],
  page_errors: [], http_errors: [], blocked_external: [], model_requests: []};
const output = path.join(directory, 'browser'); fs.mkdirSync(output, {recursive: true});
let browser, page;
async function check(name, action) {
  const started = Date.now();
  try {const detail = await action(); report.checks.push({name, passed: true, milliseconds: Date.now()-started, detail}); console.log('PASS', name);}
  catch (error) {report.checks.push({name, passed: false, error: String(error.stack || error)}); throw error;}
}
async function textContains(locator, text) {await locator.filter({hasText: text}).first().waitFor({state: 'visible'});}
async function learn(id) {await page.goto(`${base}/research/${fixture.project_id}?view=learning&node=${id}`); await page.locator('.kw-learning-view').waitFor();}
async function openDetails(locator) {if (!(await locator.getAttribute('open') !== null)) await locator.locator(':scope > summary').click();}
async function theme(value) {
  await page.evaluate(value => {localStorage.setItem('research-atlas-theme', value); window.dispatchEvent(new StorageEvent('storage', {key: 'research-atlas-theme', newValue: value}));}, value);
  await page.locator(`html[data-theme="${value}"]`).waitFor();
}
async function shot(name, locator) {
  if (locator) await locator.evaluate(element => {
    element.scrollIntoView({block:'start'});
    const offset=88;
    let parent=element.parentElement;
    while(parent && parent!==document.documentElement){
      if(/auto|scroll/.test(getComputedStyle(parent).overflowY) && parent.scrollHeight>parent.clientHeight){parent.scrollBy(0,-offset);return;}
      parent=parent.parentElement;
    }
    window.scrollBy(0,-offset);
  });
  const file = path.join(output, name + '.png'); await page.screenshot({path: file, fullPage: false});
  report.screenshots.push(file); return file;
}
async function api(url) {const response = await page.request.get(`${base}/api/projects/${fixture.project_id}/${url}`); assert.equal(response.status(), 200); return response.json();}
(async () => {
 try {
  browser = await chromium.launch({headless: true, channel: 'chrome'});
  const context = await browser.newContext({viewport: {width: 1366, height: 768}, reducedMotion: 'reduce', acceptDownloads: true});
  await context.route('**/*', route => {
    const url = new URL(route.request().url());
    if (['127.0.0.1', 'localhost'].includes(url.hostname)) return route.continue();
    report.blocked_external.push(url.href); return route.abort();
  });
  page = await context.newPage(); page.setDefaultTimeout(30000); page.setDefaultNavigationTimeout(60000);
  page.on('pageerror', error => report.page_errors.push(String(error)));
  page.on('response', response => {if (!response.ok() && response.url().includes('/api/')) report.http_errors.push({status:response.status(),url:response.url()});});
  page.on('request', request => {
    if (request.method() === 'POST' && /\/(generate|supplement|question|summary|analyze)$|\/learning$/.test(new URL(request.url()).pathname)) report.model_requests.push(request.url());
  });
  const attention = fixture.nodes.attention['缩放点积注意力'], softmax = fixture.nodes.attention.Softmax;
  await check('scaled_attention_real_numeric_input', async () => {
    await learn(attention); await page.locator('.kw-demo .ant-select-selector').click();
    await page.locator('.ant-select-item-option').filter({hasText:'从点积分数到注意力权重'}).click();
    assert.equal(await page.getByTestId('scaled-score-0').innerText(), '4.0000');
    await textContains(page.locator('.kw-demo'), '0.8668');
    await shot('1366-light-scaled-attention', page.locator('.kw-demo'));
    await page.getByRole('spinbutton', {name:'键向量维度 d_k'}).fill('16'); await page.getByRole('spinbutton', {name:'键向量维度 d_k'}).blur();
    await textContains(page.getByTestId('scaled-score-0'), '2.0000');
    await textContains(page.locator('.kw-demo'), '0.6652');
    return {default_score:4, dimension_16_score:2, default_weights:[0.8668,0.1173,0.0159], modified_weights:[0.6652,0.2447,0.09]};
  });
  await check('misconception_recommendation_reopen_dismiss', async () => {
    const component = page.locator('.kw-learning-check'); await openDetails(component);
    await component.getByRole('radio', {name:'这个位置已经得到的注意力概率', exact:true}).check();
    await component.getByRole('textbox', {name:'教学检查我的理由'}).fill('先把缩放分数误认为概率，检查平台是否指出归一化这一步。');
    await component.getByRole('button', {name:'保存回答并看建议',exact:true}).click();
    await textContains(component.locator('.kw-check-feedback'), 'softmax');
    const before = await api('knowledge/checks/recommendation'); assert.ok(before.recommendation);
    assert.equal(before.recommendation.source_node_id, attention);
    await page.reload(); await page.locator('.kw-learning-view').waitFor();
    await openDetails(page.locator('.kw-learning-check')); await openDetails(page.locator('.kw-check-history'));
    await page.locator('.kw-check-history').getByRole('button', {name:'不再根据这条回答推荐'}).first().click();
    await textContains(page.locator('.kw-check-history'), '已反馈建议不适合');
    const after = await api('knowledge/checks/recommendation'); assert.equal(after.recommendation, null);
    return {recommendation_before:before.recommendation, recommendation_after:after.recommendation};
  });
  await check('research_design_and_sample_boundary', async () => {
    await learn(fixture.nodes.study['研究设计与对照']);
    await textContains(page.getByRole('region', {name:'研究条件反馈'}), '两组学习时长不同');
    await page.getByRole('spinbutton', {name:'回忆组学习分钟'}).fill('5'); await page.getByRole('spinbutton', {name:'回忆组学习分钟'}).blur();
    await page.getByLabel('回忆组测试间隔', {exact:true}).selectOption('即时');
    await page.getByLabel('进入各组的方式').selectOption('随机');
    await textContains(page.getByRole('region', {name:'研究条件反馈'}), '列出的时间条件已对齐');
    await shot('1366-light-research-design', page.locator('.kw-demo'));
    await learn(fixture.nodes.study['样本与总体']);
    await textContains(page.locator('.kw-foundation-result'), '30.0%');
    await page.getByRole('spinbutton', {name:'总体人数 N'}).fill('20'); await page.getByRole('spinbutton', {name:'总体人数 N'}).blur();
    await textContains(page.locator('.kw-foundation-result'), '100.0%');
    await page.getByLabel('抽样方式').selectOption('random');
    await textContains(page.getByRole('region', {name:'抽样范围反馈'}), '抽样不确定性');
    return {sample_default_percent:30, clamped_N_n_k:[20,20,20], clamped_percent:100};
  });
  await check('cross_source_two_sided_review_refresh_source_return', async () => {
    await learn(softmax); const panel = page.locator('.kw-concept-correspondence'); await openDetails(panel);
    await panel.locator('.kw-concept-manual select option').filter({hasText:'归一化指数'}).first().waitFor({state:'attached'});
    const candidate = panel.locator('.kw-concept-candidates > li').filter({has: page.locator('strong', {hasText:/^归一化指数$/})});
    if(await candidate.count()) await candidate.getByRole('button', {name:'核对这两个概念'}).click();
    else await panel.locator('.kw-concept-decisions').getByRole('button', {name:'归一化指数 · 条件有差异'}).click();
    const review = page.getByRole('region', {name:'概念双侧核对'});
    assert.equal(await review.locator('.kw-concept-side').count(),2);
    await textContains(review.locator('.kw-concept-side').nth(0),fixture.sources.attention.title);
    await textContains(review.locator('.kw-concept-side').nth(1),fixture.sources.temperature.title);
    assert.ok(await review.locator('.kw-concept-side').nth(0).locator('.kw-evidence-list button').count());
    assert.ok(await review.locator('.kw-concept-side').nth(1).locator('.kw-evidence-list button').count());
    await page.getByLabel('概念核对结果').selectOption('conditions_differ');
    await page.getByLabel('概念核对说明').fill('二者都对候选分数归一化，但A固定温度1，B使用温度2；数值与适用条件需要分别核对。');
    await page.getByRole('button', {name:'保存概念核对',exact:true}).click();
    await textContains(review,'个人判断已保存');
    await page.reload(); await page.locator('.kw-learning-view').waitFor(); await openDetails(page.locator('.kw-concept-correspondence'));
    await textContains(page.locator('.kw-concept-decisions'), '归一化指数 · 条件有差异');
    await page.locator('.kw-concept-decisions').getByRole('button', {name:'归一化指数 · 条件有差异'}).click();
    assert.equal(await page.getByLabel('概念核对结果').inputValue(),'conditions_differ');
    await shot('1366-light-cross-source', page.locator('.kw-concept-review'));
    await page.locator('.kw-concept-side').nth(0).locator('.kw-evidence-list button').first().click();
    await page.locator('.kw-source-reader').waitFor();
    await page.getByRole('button', {name:'返回原位置',exact:true}).click(); await page.locator('.kw-learning-view').waitFor();
    await textContains(page.locator('.kw-concept-review'), '温度2');
    const saved = await api(`knowledge/nodes/${softmax}/concept-correspondences`);
    assert.equal(saved.items[0].status, 'conditions_differ');
    assert.ok(saved.items[0].left.evidence.length && saved.items[0].right.evidence.length);
    return {status:saved.items[0].status, revision:saved.items[0].revision, left_evidence:saved.items[0].left.evidence.length, right_evidence:saved.items[0].right.evidence.length};
  });
  await check('formula_symbols_conditions_from_source_reader', async () => {
    await page.locator('.kw-concept-side').nth(0).locator('.kw-evidence-list button').first().click();
    await page.locator('.kw-reading-formula-tools').waitFor();
    await page.getByText('查看公式符号与条件', {exact:true}).click();
    const symbols = page.getByRole('region', {name:'本式符号与条件'});
    await textContains(symbols, '候选位置的缩放分数'); await textContains(symbols, '键向量维度');
    await textContains(symbols, '温度');
    await shot('1366-light-reader-symbols', symbols);
    return {symbols:['s_i','p_i','d_k'], conditions:'候选轴3、温度1'};
  });
  await check('coverage_manual_missing_decision_survives_reload', async () => {
    await page.goto(`${base}/research/${fixture.project_id}?view=materials`);
    let source = page.locator('.kw-source-list > li').filter({hasText:fixture.sources.study.title});
    await openDetails(source.locator('.kw-source-coverage'));
    let limitation = source.locator('.kw-coverage-items > li').filter({has:page.getByText('局限与范围',{exact:true})});
    await limitation.getByRole('button', {name:'记录我的判断'}).click();
    await page.getByRole('textbox', {name:'覆盖判断理由：局限与范围'}).fill('逐段检查这份自编教学材料，只报告设计与样本，未给出研究局限段落。');
    await limitation.getByRole('button', {name:'保存判断',exact:true}).click();
    await textContains(limitation, '用户标记未报告');
    await page.reload(); source = page.locator('.kw-source-list > li').filter({hasText:fixture.sources.study.title});
    await openDetails(source.locator('.kw-source-coverage'));
    limitation = source.locator('.kw-coverage-items > li').filter({has:page.getByText('局限与范围',{exact:true})});
    await textContains(limitation, '用户标记未报告'); await textContains(limitation, '逐段检查');
    const value = await api(`sources/${fixture.sources.study.id}/coverage`);
    const item = value.items.find(item=>item.category==='limitation'); assert.equal(item.decision.status,'not_reported');
    return {status:item.decision.status, reason:item.decision.reason, model_available:value.model_available};
  });
  await check('desktop_themes_and_overflow', async () => {
    const measurements=[];
    for (const width of [1366,1920]) {
      await page.setViewportSize({width,height:width===1366?768:1080});
      await learn(softmax); await openDetails(page.locator('.kw-concept-correspondence'));
      await page.locator('.kw-concept-decisions').getByRole('button',{name:'归一化指数 · 条件有差异'}).click();
      for (const color of ['light','dark']) {
        await theme(color); await page.mouse.move(0,0); await shot(`${width}-${color}-cross-source`, page.locator('.kw-concept-review'));
        const geometry=await page.evaluate(()=>{
          const button=document.querySelector('.kw-concept-decisions button');
          const swatch=document.createElement('span'); swatch.style.color='var(--atlas-accent-strong)';document.body.append(swatch);
          const expectedDecisionColor=getComputedStyle(swatch).color; swatch.remove();
          return {viewport:innerWidth,document:document.documentElement.scrollWidth,
            decisionColor:getComputedStyle(button).color,expectedDecisionColor};
        });
        assert.ok(geometry.document<=geometry.viewport+1,JSON.stringify(geometry)); measurements.push({width,color,...geometry});
        assert.equal(geometry.decisionColor,geometry.expectedDecisionColor,'Saved judgement should use a readable theme-aware accent');
      }
    }
    return measurements;
  });
  await check('no_runtime_model_or_javascript_http_errors', async () => {
    assert.deepEqual(report.model_requests,[]); assert.deepEqual(report.page_errors,[]); assert.deepEqual(report.http_errors,[]);
    return {runtime_model_requests:0,javascript_errors:0,http_errors:0};
  });
  report.passed=true;
 } catch(error) {
  report.passed=false; report.error=String(error.stack||error);
  if(page) {await page.screenshot({path:path.join(output,'failure.png'),fullPage:true}).catch(()=>{}); fs.writeFileSync(path.join(output,'failure.html'),await page.content().catch(()=>''));}
  console.error(report.error); process.exitCode=1;
 } finally {
  report.finished_at=new Date().toISOString(); fs.writeFileSync(path.join(output,'report.json'),JSON.stringify(report,null,2));
  if(browser) await browser.close(); console.log('Report:',path.join(output,'report.json'));
 }
})();
