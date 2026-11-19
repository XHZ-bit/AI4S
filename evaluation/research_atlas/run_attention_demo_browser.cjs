/* Classic Attention acceptance against the isolated 18179/15379 profile only.
 * Authored teaching material and automated review are engineering acceptance,
 * not fresh AI output or the user's final scientific verification.
 */
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const {createHash} = require('node:crypto');
const {execFileSync} = require('node:child_process');
const {chromium} = require('../../frontend/node_modules/playwright');

const root = path.resolve(__dirname, '../..');
const positional = process.argv.slice(2).filter(argument=>!argument.startsWith('--'));
const directory = path.resolve(positional[0] || path.join(root, '.ui_validation/attention-final-20261117'));
const expectedDirectory = path.join(root, '.ui_validation/attention-final-20261117');
const base = positional[1] || 'http://127.0.0.1:15379';
const apiBase = 'http://127.0.0.1:18179';
assert.equal(directory.toLowerCase(), expectedDirectory.toLowerCase(), 'Only the isolated Attention profile may be changed');
assert.equal(new URL(base).origin, 'http://127.0.0.1:15379', 'The normal frontend is forbidden');
const manifestPath = path.join(directory, 'attention-demo.json');
const smoke = process.argv.includes('--smoke');
const readManifest = () => JSON.parse(fs.readFileSync(manifestPath, 'utf8').replace(/^\uFEFF/, ''));
let fixture = readManifest();
assert.equal(fixture.kind, 'attention-classic-offline-demo');
assert.equal(new URL(fixture.api).origin, apiBase, 'The normal API/database is forbidden');
assert.equal(fixture.real_provider_calls, 0);
const pid = fixture.project_id;
assert.match(pid, /^project-[a-f0-9]{32}$/);
const nodeId = fixture.node_id || fixture.nodes?.formula || fixture.nodes?.scaled_attention;
assert.ok(nodeId, 'The preparation phase must publish the formula node_id before running the browser');
const output = path.join(directory, 'browser');
fs.mkdirSync(output, {recursive:true});
const reviewNotice = '工程验收操作，由开发助手执行；预置教学示例待用户最终核对，不代表用户已完成科学验收。';
const report = {
  started_at:new Date().toISOString(), mode:smoke?'read_only_restored_profile_smoke':'classic_attention_acceptance',profile:directory, project_id:pid, node_id:nodeId,
  source_kind:'classic_original_paper_with_authored_teaching_examples',
  teaching_notice:fixture.notice, review_notice:reviewNotice, real_provider_calls:0,
  checks:[], screenshots:[], geometry:[], math:[], engineering_review_actions:[],
  runtime_assets:[], model_requests:[], external_requests:[], page_errors:[], console_errors:[], http_errors:[],
  request_failures:[], local_api_checks:[], unexpected_mutations:[],
};
const allowedOrigins = new Set([new URL(base).origin, new URL(apiBase).origin]);
const knowledge = `/api/projects/${pid}/knowledge`;
const implementations = `${knowledge}/nodes/${nodeId}/implementations`;
const outcomePath = `/api/workbench/projects/${pid}/nodes/${nodeId}/outcomes`;
const workspace = query => `${base}/research/${pid}?${query}`;
let browser, context, page, teaching, wrong, practice, runFour, runTwo, savedNote, noteBody, exported;

function isModelRequest(request) {
  if (request.method() !== 'POST') return false;
  const name = new URL(request.url()).pathname;
  return /\/(?:generate|supplement|question|summary|review|analyze|transcribe)$/.test(name)
    || /\/knowledge\/nodes\/[^/]+\/(?:learning|practice)$/.test(name)
    || /\/knowledge\/comparisons$/.test(name)
    || /\/knowledge\/learning-route(?:\/generate)?$/.test(name);
}
async function quiet() {
  await page.waitForLoadState('networkidle');
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
}
async function until(predicate, label, timeout=20000) {
  const started = Date.now();
  while (Date.now() - started < timeout) {
    if (await predicate()) return;
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw Error('Timed out: ' + label);
}
async function api(suffix) {
  assert.ok(suffix.startsWith(knowledge + '/') || suffix === implementations || suffix.startsWith(outcomePath), 'API read outside this demo project');
  const response = await page.request.get(apiBase + suffix);
  report.local_api_checks.push({path:suffix, status:response.status()});
  assert.ok(response.ok(), `${response.status()} ${suffix}: ${await response.text()}`);
  return response.json();
}
async function check(name, action) {
  try {
    const result = await action();
    report.checks.push({name, passed:true, result});
    console.log('PASS', name);
    return result;
  } catch (error) {
    report.checks.push({name, passed:false, error:String(error.stack || error)});
    throw error;
  }
}
async function theme(value) {
  await page.evaluate(value => {
    localStorage.setItem('research-atlas-theme', value);
    window.dispatchEvent(new StorageEvent('storage', {key:'research-atlas-theme', newValue:value}));
  }, value);
  await page.locator(`html[data-theme="${value}"]`).waitFor();
}
async function audit(name, selector) {
  const measurement = await page.evaluate(({name, selector}) => {
    const box = element => {
      if (!element || !element.getClientRects().length) return null;
      const rect = element.getBoundingClientRect();
      return {x:rect.x, y:rect.y, width:rect.width, height:rect.height, bottom:rect.bottom, right:rect.right};
    };
    const raw = [], walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let text;
    while ((text = walker.nextNode())) {
      const element = text.parentElement;
      // Source code, editable data and compact evidence selectors stay literal.
      if (!element || element.closest('.katex,pre,code,textarea,input,label,script,style,annotation,.kw-source-text,.kw-code-document,.atlas-pdf-text-layer')) continue;
      const style = getComputedStyle(element);
      if (!element.getClientRects().length || style.visibility === 'hidden' || style.display === 'none') continue;
      if (/\\(?:frac|sqrt|begin|operatorname|mathsf|left|right)\b/.test(text.textContent || '')) raw.push(text.textContent.trim().slice(0,240));
    }
    return {name, url:location.href, viewport:[innerWidth,innerHeight], document_width:document.documentElement.scrollWidth,
      core:box(document.querySelector(selector)), katex_errors:[...document.querySelectorAll('.katex-error')].filter(e=>e.getClientRects().length).map(e=>e.textContent),
      visible_raw_tex:raw, rendered_math:document.querySelectorAll('.katex').length};
  }, {name, selector});
  report.geometry.push({name, viewport:measurement.viewport, document_width:measurement.document_width, core:measurement.core});
  report.math.push({name, katex_errors:measurement.katex_errors, visible_raw_tex:measurement.visible_raw_tex, rendered_math:measurement.rendered_math});
  assert.ok(measurement.document_width <= measurement.viewport[0] + 1, name + ' horizontal document overflow');
  assert.deepEqual(measurement.katex_errors, [], name + ' invalid rendered mathematics');
  assert.deepEqual(measurement.visible_raw_tex, [], name + ' raw TeX outside literal/source regions');
  assert.ok(measurement.core, name + ' main surface missing');
  assert.ok(measurement.core.y>=0&&measurement.core.bottom<=measurement.viewport[1]+2,name+' main surface outside the viewport');
  return measurement;
}
async function shot(name, selector) {
  await quiet();
  await audit(name, selector);
  const target = path.join(output, name + '.png');
  await page.screenshot({path:target});
  report.screenshots.push(target);
}
async function learningReady() {
  await page.locator('.kw-learning-workspace').waitFor();
  await until(async()=>!await page.locator('.kw-learning-preparing').count(), 'saved authored lesson without generation');
  assert.equal(new URL(page.url()).searchParams.get('node'), nodeId);
}
async function readTab(name) {
  await page.getByRole('tablist',{name:'学习阅读分区',exact:true}).getByRole('tab',{name,exact:true}).click();
}
async function mappingPanel() {
  await learningReady();
  await readTab('练习与实现');
  const panel = page.locator('.kw-implementation');
  await panel.waitFor();
  if (!await panel.evaluate(element=>element.open)) await panel.locator(':scope > summary').click();
  await panel.locator('.kw-implementation-item').first().waitFor();
  return panel;
}
const mappingItem = (panel,id) => panel.locator(`[data-mapping-id="${id}"]`);
async function returnFromSource() {
  await page.getByRole('button',{name:'返回原位置',exact:true}).click();
  await learningReady();
  assert.equal(new URL(page.url()).searchParams.get('view'), 'learning');
}
async function chooseTask(name) {
  await page.getByRole('tablist',{name:'练习任务分区',exact:true}).getByRole('tab',{name,exact:true}).click();
}
async function chooseNotes() {
  await learningReady();
  const shortcut = page.getByRole('button',{name:'打开笔记工具',exact:true});
  if (await shortcut.isVisible()) await shortcut.click();
  else await page.getByRole('tablist',{name:'随手学习工具分区',exact:true}).getByRole('tab',{name:'笔记',exact:true}).click();
  await page.getByRole('textbox',{name:'我的理解',exact:true}).waitFor();
  await until(()=>page.getByRole('textbox',{name:'我的理解',exact:true}).isEnabled(),'node notebook loaded');
}
async function runScaled(dk, expected) {
  await chooseTask('输入');
  const input = JSON.stringify({dot:8,d_k:dk},null,2);
  await page.getByLabel('练习输入 JSON',{exact:true}).fill(input);
  const prediction = `开发助手工程验收：预测 8 / sqrt(${dk}) = ${expected.toFixed(1)}，这是 softmax 之前的缩放分数，待用户最终核对。`;
  await page.getByLabel('运行前预测',{exact:true}).fill(prediction);
  const code = await page.getByLabel('节点练习 Python 代码',{exact:true}).inputValue();
  const pending = page.waitForResponse(response => response.url().endsWith(`${knowledge}/practice/${practice.id}/runs`) && response.request().method()==='POST', {timeout:75000});
  await page.getByRole('button',{name:'运行代码',exact:true}).click();
  const response = await pending;
  assert.equal(response.status(),201);
  let run = await response.json();
  assert.equal(run.status,'success');
  assert.equal(run.origin,'browser_teaching_run');
  assert.match(run.output,new RegExp(`scaled\\s*=\\s*${expected.toFixed(1).replace('.', '\\.')}(?:\\D|$)`));
  assert.equal(run.code,code);
  assert.deepEqual(JSON.parse(run.input_json),{dot:8,d_k:dk});
  assert.equal(run.prediction,prediction);
  assert.equal(run.mapping_id,teaching.id);
  assert.equal(run.mapping_revision,teaching.revision);
  assert.ok(Number.isInteger(run.practice_revision) && run.practice_revision > 0, 'Actual run must preserve its practice revision');
  await page.getByRole('tablist',{name:'练习结果分区',exact:true}).getByRole('tab',{name:'运行结果',exact:true}).click();
  const explanation = `开发助手工程验收：dot=8、d_k=${dk}，8 / sqrt(${dk}) = ${expected.toFixed(1)}。检验的是 softmax 之前的缩放分数；教学实现与论文原实现分别标注，待用户最终核对。`;
  await page.getByLabel('运行后的解释',{exact:true}).fill(explanation);
  const saved = page.waitForResponse(r=>r.url().endsWith(`/runs/${run.id}`)&&r.request().method()==='PATCH');
  await page.getByRole('button',{name:'保存运行解释',exact:true}).click();
  const savedResponse = await saved;
  assert.ok(savedResponse.ok());
  run = await savedResponse.json();
  assert.equal(run.explanation,explanation);
  await page.getByText('解释已保存到运行记录。',{exact:true}).waitFor();
  await page.locator('#kw-practice-result-output-panel').evaluate(element=>{element.scrollTop=0;});
  return run;
}

async function readOnlySmoke() {
  await check('restored_profile_is_the_explicit_isolated_copy',async()=>{
    const response=await page.request.get(apiBase+'/api/system/status');assert.ok(response.ok());
    const status=await response.json(),expected=path.join(directory,'restored-data');
    assert.equal(path.resolve(status.data_dir).toLowerCase(),expected.toLowerCase());
    report.restored_data_dir=status.data_dir;
    return {data_dir:status.data_dir,read_only:true};
  });
  await check('default_focused_canvas_and_all_content_expose_the_formula_without_search',async()=>{
    const detail=await api(`${knowledge}/nodes/${nodeId}`),all=await api(`${knowledge}/graph?limit=240&overview=false`);
    assert.ok(all.nodes.every(node=>node.project_id===pid),'The API graph must contain only this project');
    await page.goto(workspace('view=graph'));await page.locator('.kw-graph-view').waitFor();
    await page.getByRole('button',{name:'切换完整图谱',exact:true}).waitFor();
    const entry=page.locator(`[data-node-id="${nodeId}"]`);await entry.waitFor();
    assert.equal(await page.getByLabel('搜索图谱知识',{exact:true}).inputValue(),'');
    await shot('1366-light-11-default-formula-discovery','.kw-graph-view');
    await page.getByRole('button',{name:'内容列表',exact:true}).click();
    let listed=page.getByRole('button',{name:'公式：'+detail.node.label,exact:true});
    while(!await listed.count()&&await page.getByRole('button',{name:'显示更多内容',exact:true}).isVisible())await page.getByRole('button',{name:'显示更多内容',exact:true}).click();
    await listed.waitFor();
    const structural=all.nodes.find(node=>node.kind==='formula'&&node.id!==nodeId&&node.metadata?.structural);
    if(structural) {
      const other=page.getByRole('button',{name:'公式：'+structural.label,exact:true});
      while(!await other.count()&&await page.getByRole('button',{name:'显示更多内容',exact:true}).isVisible())await page.getByRole('button',{name:'显示更多内容',exact:true}).click();
      await other.waitFor();
    }
    await page.getByRole('button',{name:'结构图',exact:true}).click();await entry.click();
    await page.getByRole('button',{name:'深入学习',exact:true}).click();await learningReady();await readTab('讲解');
    await shot('1366-light-12-default-entry-formula-lesson','.kw-learning-workspace');
    return {entry_kind:'default_focused_graph',search_required:false,formula_in_all_content:true,ordinary_structural_formula_in_all_content:structural?.id||null};
  });
  await check('saved_real_outputs_remain_visible_without_new_execution',async()=>{
    const saved=await api(`${knowledge}/practice/${fixture.practice_id}`);
    assert.deepEqual(JSON.parse(saved.input_json),{dot:8,d_k:4});
    const expected=[4,2].map(number=>saved.runs.find(run=>run.status==='success'&&run.output.includes('scaled='+number.toFixed(1))));
    assert.ok(expected.every(Boolean),'Both earlier real browser runs must exist');
    await page.setViewportSize({width:1440,height:900});await theme('dark');
    await page.goto(workspace(`view=practice&node=${nodeId}&mapping=${fixture.mappings.teaching.id}`));
    await page.getByLabel('节点练习 Python 代码',{exact:true}).waitFor();await chooseTask('学习记录');
    const history=page.locator('.kw-practice-history');await history.locator(':scope > summary').click();
    for(const [number,run]of[[4,expected[0]],[2,expected[1]]]) {
      const value=history.getByText('scaled='+number.toFixed(1),{exact:true});await value.scrollIntoViewIfNeeded();
      const box=await value.boundingBox();assert.ok(box&&box.y>=0&&box.y+box.height<=900,'The actual saved numeric result must be visible');
      await shot('1440-dark-13-saved-python-'+number.toFixed(1),'.kw-practice-ide');
      assert.ok(run.explanation.startsWith('开发助手工程验收：'));assert.ok(run.code&&run.input_json&&run.practice_revision);
    }
    return {default_input:{dot:8,d_k:4},run_ids:expected.map(run=>run.id),new_execution:false};
  });
  await check('read_only_local_boundary_and_rendering_checks',async()=>{
    for(const key of['unexpected_mutations','model_requests','external_requests','page_errors','console_errors','http_errors'])assert.deepEqual(report[key],[],key);
    return {api_writes:0,new_python_executions:0,model_requests:0,external_requests:0};
  });
}

async function runAcceptance() {
  await check('focused_project_graph_opens_the_formula_lesson',async()=>{
    const detail = await api(`${knowledge}/nodes/${nodeId}`);
    assert.equal(detail.node.source_id,fixture.imports.paper.source_id);
    assert.equal(detail.node.kind,'formula');
    const collection = await api(implementations);
    teaching = collection.items.find(item=>item.code_source_id===fixture.imports.teaching.source_id);
    wrong = collection.items.find(item=>item.code_source_id===fixture.imports.counterexample.source_id);
    assert.ok(teaching&&wrong,'Two authored candidates must be prepared');
    assert.equal(teaching.implementation_kind,'teaching');
    assert.ok(!teaching.stale&&!wrong.stale,'Both candidate versions must still match the real imported sources');
    report.initial_mapping_versions = {teaching:teaching.revision,counterexample:wrong.revision};
    await page.goto(workspace('view=graph'));
    await page.locator('.kw-graph-view').waitFor();
    const focus = page.getByRole('button',{name:'围绕当前问题',exact:true});
    if (await focus.isVisible()) await focus.click();
    await page.getByRole('button',{name:'切换完整图谱',exact:true}).waitFor();
    await shot('1366-light-01-focused-graph','.kw-graph-view');
    let entry = page.locator(`[data-node-id="${nodeId}"]`);
    let entryKind='focused_graph';
    if (!await entry.count()) {
      // Parsed formula regions are structural; the normal focused overview may
      // show only semantic concepts. Use the actual graph search to reveal it.
      entryKind='graph_search';
      const search=page.getByLabel('搜索图谱知识',{exact:true});
      await search.fill(detail.node.label);await search.press('Enter');
      entry=page.locator(`[data-node-id="${nodeId}"]`);
    }
    await entry.click();
    await page.locator('.kw-node-inspector').waitFor();
    await page.getByRole('button',{name:'深入学习',exact:true}).click();
    await learningReady();
    await readTab('讲解');
    await page.locator('#kw-learning-read-lesson-panel .katex-display').first().waitFor();
    const tex=await page.locator('#kw-learning-read-lesson-panel .katex-mathml annotation').allTextContents();
    assert.ok(tex.some(value=>/sqrt|\\sqrt/.test(value)&&/frac|\\frac/.test(value)),'The scaled-attention denominator must be rendered');
    await shot('1366-light-02-formula-lesson','.kw-learning-workspace');
    return {formula_node:nodeId,label:detail.node.label,entry_kind:entryKind,rendered_formula:true};
  });
  await check('full_original_pdf_page_four_and_teaching_code_roundtrip',async()=>{
    let panel=await mappingPanel();
    await mappingItem(panel,teaching.id).getByRole('button',{name:'查看原文',exact:true}).click();
    await page.locator('[data-pdf-page="4"] canvas').first().waitFor();
    await until(async()=>await page.getByLabel('PDF 页码',{exact:true}).inputValue()==='4','exact original PDF page 4');
    const url=new URL(page.url());
    assert.equal(url.searchParams.get('source'),fixture.imports.paper.source_id);
    assert.equal(url.searchParams.get('targetPage'),'4');
    await page.getByLabel('原文定位区域',{exact:true}).waitFor();
    await shot('1366-light-03-original-paper-page-4','.atlas-pdf-pages');
    const pdf=Number((await page.locator('.ps-pdf-page-count').innerText()).replace(/\D/g,''));
    assert.ok(pdf>4,'Open the complete original paper, not a single-page teaching substitute');
    await returnFromSource();
    panel=await mappingPanel();
    await mappingItem(panel,teaching.id).getByRole('button',{name:'查看代码来源',exact:true}).click();
    await page.getByRole('article',{name:'源码阅读区',exact:true}).waitFor();
    const codeUrl=new URL(page.url()),locator=teaching.code_evidence.locator;
    assert.equal(codeUrl.searchParams.get('source'),fixture.imports.teaching.source_id);
    assert.equal(codeUrl.searchParams.get('line'),String(locator.start_line));
    assert.equal(codeUrl.searchParams.get('endLine'),String(locator.end_line));
    const highlighted=await page.locator('.kw-code-document .kw-source-highlight').allTextContents();
    assert.match(highlighted.join('\n'),/sqrt/);
    assert.ok(locator.start_line<=11&&locator.end_line>=11,'The known scaling line 11 must be included');
    await shot('1366-light-04-teaching-code-location','.kw-code-document');
    await returnFromSource();
    return {pdf_page:4,pdf_page_count:pdf,formula_block:fixture.formula.block_id,code_lines:[locator.start_line,locator.end_line],returned_node:nodeId};
  });
  await check('engineering_review_confirms_teaching_and_rejects_same_name_counterexample',async()=>{
    const panel=await mappingPanel();
    for(const [item,status,label] of [[teaching,'confirmed','确认对应'],[wrong,'rejected','否定对应']]) {
      const before=item.revision;
      const rationale=item.id===teaching.id
        ? '教学函数第8–11行在第11行除以sqrt(d_k)，对应论文第4页式(1)的缩放项；这是教学实现，不是论文官方源码。'
        : '同名函数第7–8行乘以d_k，与论文除以sqrt(d_k)不符，因此否定此对应。';
      const explanation='开发助手工程验收：'+rationale+'预置教学示例，待用户最终核对。';
      if(item.explanation!==explanation) {
        await mappingItem(panel,item.id).getByRole('button',{name:/^编\s*辑$/}).click();
        await panel.getByLabel('对应说明',{exact:true}).fill(explanation);
        const edited=page.waitForResponse(r=>r.url().endsWith(implementations+'/'+item.id)&&r.request().method()==='PATCH');
        await panel.getByRole('button',{name:/^保\s*存$/}).click();
        const response=await edited;assert.ok(response.ok());Object.assign(item,await response.json());
      }
      if(item.status!==status) {
        const pending=page.waitForResponse(r=>r.url().endsWith(implementations+'/'+item.id)&&r.request().method()==='PATCH');
        await mappingItem(panel,item.id).getByRole('button',{name:label,exact:true}).click();
        const response=await pending;assert.ok(response.ok());Object.assign(item,await response.json());
      }
      assert.equal(item.status,status);
      report.engineering_review_actions.push({id:item.id,source_id:item.code_source_id,status,before_revision:before,after_revision:item.revision,actor:'developer_assistant_browser_acceptance',notice:reviewNotice});
    }
    const saved=await api(implementations);
    assert.equal(saved.items.find(item=>item.id===teaching.id).status,'confirmed');
    assert.equal(saved.items.find(item=>item.id===wrong.id).status,'rejected');
    await shot('1366-light-05-reviewed-correspondences','.kw-learning-workspace');
    const python=process.env.PAPERSTRIDE_PYTHON||path.join(root,'backend/.venv/Scripts/python.exe');
    const preparation=execFileSync(python,[path.join(__dirname,'prepare_attention_demo.py'),directory,'--phase','bind-practice','--api',apiBase],{cwd:root,encoding:'utf8',timeout:60000});
    fs.writeFileSync(path.join(output,'bind-practice.log'),preparation);
    fixture=readManifest();
    assert.equal(fixture.project_id,pid);assert.equal(fixture.real_provider_calls,0);
    await mappingItem(panel,teaching.id).getByRole('button',{name:'用于练习',exact:true}).click();
    await page.locator('.kw-practice-ide').waitFor();
    assert.equal(new URL(page.url()).searchParams.get('mapping'),teaching.id);
    practice=await api(`${knowledge}/nodes/${nodeId}/practice?difficulty=foundation&mapping_id=${teaching.id}&mapping_revision=${teaching.revision}`);
    assert.equal(practice.status,'starter','Authored material must not impersonate freshly generated AI content');
    assert.equal(practice.mapping_snapshot.revision,teaching.revision);
    assert.ok(!practice.mapping_stale);
    return {teaching_status:teaching.status,counterexample_status:wrong.status,practice_id:practice.id,practice_status:practice.status,notice:reviewNotice};
  });
  await check('real_browser_python_changes_scaling_and_saves_both_explanations',async()=>{
    runFour=await runScaled(4,4);
    await shot('1366-light-06-python-scaled-4','.kw-practice-ide');
    runTwo=await runScaled(16,2);
    assert.ok(runTwo.practice_revision>=runFour.practice_revision);
    await shot('1366-light-07-python-scaled-2','.kw-practice-ide');
    assert.ok(report.runtime_assets.some(asset=>asset.path.endsWith('.wasm')&&asset.status===200),'A real local WASM Python runtime must load');
    await page.reload();await page.locator('.kw-practice-ide').waitFor();await chooseTask('学习记录');
    const history=page.locator('.kw-practice-history');
    await history.locator(':scope > summary').click();
    await history.getByText(runFour.explanation,{exact:false}).waitFor();
    await history.getByText(runTwo.explanation,{exact:false}).waitFor();
    const reopened=await api(`${knowledge}/practice/${practice.id}`);
    for(const expected of[runFour,runTwo]) {
      const actual=reopened.runs.find(run=>run.id===expected.id);
      assert.ok(actual);for(const key of['code','input_json','output','prediction','explanation','practice_revision','mapping_revision'])assert.equal(actual[key],expected[key],key);
    }
    // Preserve both real runs, but leave the user's first-open example at 4.0.
    // Export is checked after this change so the 2.0 run cannot borrow current input.
    await chooseTask('输入');await page.getByLabel('练习输入 JSON',{exact:true}).fill(JSON.stringify({dot:8,d_k:4},null,2));
    const draft=page.waitForResponse(r=>r.url().endsWith(`${knowledge}/practice/${practice.id}`)&&r.request().method()==='PATCH');
    await page.getByRole('button',{name:'保存编辑稿',exact:true}).click();
    const draftResponse=await draft;assert.ok(draftResponse.ok());const restored=await draftResponse.json();
    assert.deepEqual(JSON.parse(restored.input_json),{dot:8,d_k:4});
    report.final_default_input={dot:8,d_k:4};
    return {runtime:'local_pyodide_wasm',runs:[runFour,runTwo],reopened:true,final_default_input:report.final_default_input,final_practice_revision:restored.revision};
  });
  await check('saved_understanding_exports_actual_code_inputs_and_versions',async()=>{
    await page.goto(workspace('view=learning&node='+nodeId));await chooseNotes();
    noteBody='开发助手工程验收：预置教学示例由开发助手整理，待用户最终核对。原文为《Attention Is All You Need》第4页式(1)。固定点积8时，d_k=4得到4.0，d_k=16得到2.0；检验的是softmax之前的缩放分数。教学代码的除以sqrt(d_k)与同名反例分别核对，历史运行应保留各自代码、输入和版本。';
    await page.getByRole('textbox',{name:'我的理解',exact:true}).fill(noteBody);
    const saved=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/workbench/records'&&r.request().method()==='POST');
    await page.getByRole('button',{name:'保存笔记',exact:true}).click();
    savedNote=await(await saved).json();assert.equal(savedNote.body,noteBody);
    await page.getByRole('button',{name:'导出学习成果',exact:true}).click();
    const choices=page.getByLabel('选择学习成果导出内容',{exact:true});await choices.waitFor();
    const catalog=await api(outcomePath);
    await choices.getByRole('checkbox',{name:savedNote.title,exact:true}).check();
    const evidence=choices.getByRole('checkbox',{name:/^原文依据 · 第 4 页$/});
    assert.ok(await evidence.count());for(const item of await evidence.all())await item.check();
    const practiceIndex=catalog.practices.findIndex(item=>item.id===practice.id);
    assert.ok(practiceIndex>=0);await choices.getByRole('checkbox',{name:/^练习 ·/}).nth(practiceIndex).check();
    const mappingIndex=catalog.mappings.findIndex(item=>item.id===teaching.id);
    assert.ok(mappingIndex>=0);await choices.getByRole('checkbox',{name:/^论文与代码映射 ·/}).nth(mappingIndex).check();
    const preview=page.waitForResponse(r=>r.url().endsWith(outcomePath+'/preview')&&r.request().method()==='POST');
    await choices.getByRole('button',{name:'预览所选内容',exact:true}).click();
    const response=await preview;assert.ok(response.ok());exported=await response.json();
    const selection=response.request().postDataJSON();
    assert.ok(selection.practice_ids.includes(practice.id)&&selection.note_ids.includes(savedNote.id));
    assert.ok(selection.mappings.some(item=>item.id===teaching.id&&item.revision===teaching.revision));
    for(const run of[runFour,runTwo]) {
      for(const value of[run.id,run.code.trim(),run.input_json,run.output.trim(),run.explanation])assert.ok(exported.markdown.includes(value),'Export lost actual run snapshot: '+value.slice(0,100));
      assert.ok(exported.markdown.includes('运行所关联的练习修订：'+run.practice_revision));
    }
    assert.ok(exported.markdown.includes(fixture.imports.paper.source_version));
    assert.ok(exported.markdown.includes('浏览器报告的教学运行，未独立验证。'));
    await page.getByLabel('学习成果导出预览',{exact:true}).waitFor();
    await page.setViewportSize({width:1440,height:900});await theme('dark');
    await shot('1440-dark-08-learning-outcome-preview','.kw-learning-workspace');
    const pendingDownload=page.waitForEvent('download');await page.getByRole('button',{name:'下载 Markdown',exact:true}).click();
    const download=await pendingDownload,target=path.join(output,'attention-selected-learning-outcome.md');
    await download.saveAs(target);assert.equal(fs.readFileSync(target,'utf8'),exported.markdown);
    fs.writeFileSync(path.join(output,'outcome-selection.json'),JSON.stringify(selection,null,2));
    report.export_selection=selection;
    report.selected_outcome={filename:path.basename(target),path:target,bytes:fs.statSync(target).size,sha256:createHash('sha256').update(fs.readFileSync(target)).digest('hex')};
    return {note_id:savedNote.id,note_version:savedNote.version,selected_count:exported.selected_count,run_ids:[runFour.id,runTwo.id],download:target};
  });
  await check('refresh_reopens_notes_mapping_decisions_and_real_run_history',async()=>{
    await page.reload();await chooseNotes();
    assert.equal(await page.getByRole('textbox',{name:'我的理解',exact:true}).inputValue(),noteBody);
    const saved=await api(implementations);
    assert.equal(saved.items.find(item=>item.id===teaching.id).status,'confirmed');
    assert.equal(saved.items.find(item=>item.id===wrong.id).status,'rejected');
    await readTab('讲解');await shot('1440-dark-09-reopened-formula-lesson','.kw-learning-workspace');
    await page.goto(workspace(`view=practice&node=${nodeId}&mapping=${teaching.id}`));
    await page.getByLabel('节点练习 Python 代码',{exact:true}).waitFor();await chooseTask('输入');
    assert.deepEqual(JSON.parse(await page.getByLabel('练习输入 JSON',{exact:true}).inputValue()),{dot:8,d_k:4});
    assert.equal(await page.getByLabel('节点练习 Python 代码',{exact:true}).inputValue(),runTwo.code);
    await chooseTask('学习记录');const history=page.locator('.kw-practice-history');await history.locator(':scope > summary').click();
    await history.getByText(runFour.explanation,{exact:false}).waitFor();await history.getByText(runTwo.explanation,{exact:false}).waitFor();
    await shot('1440-dark-10-reopened-run-history','.kw-practice-ide');
    return {notes_reopened:true,confirmed_and_rejected_preserved:true,run_history_preserved:true};
  });
  await check('only_local_requests_and_no_model_or_console_errors',async()=>{
    await quiet();
    for(const key of['model_requests','external_requests','page_errors','console_errors','http_errors'])assert.deepEqual(report[key],[],key);
    assert.equal(readManifest().real_provider_calls,0);
    return {real_provider_calls:0,model_requests:0,external_requests:0,local_runtime_assets:[...new Set(report.runtime_assets.map(asset=>asset.path))],notice:reviewNotice};
  });
}

(async()=>{
  try {
    browser=await chromium.launch({headless:true,channel:process.env.ATLAS_BROWSER_CHANNEL||'chrome'});
    context=await browser.newContext({viewport:{width:1366,height:768},reducedMotion:'reduce',acceptDownloads:true,serviceWorkers:'block'});
    await context.route('**/*',route=>{
      const request=route.request(),url=new URL(request.url());
      if(isModelRequest(request)) {report.model_requests.push({url:url.href,method:request.method()});return route.abort('blockedbyclient');}
      if(smoke&&url.pathname.startsWith('/api/')&&!['GET','HEAD','OPTIONS'].includes(request.method())) {report.unexpected_mutations.push({url:url.href,method:request.method()});return route.abort('blockedbyclient');}
      if(['data:','blob:','about:'].includes(url.protocol)||allowedOrigins.has(url.origin))return route.continue();
      report.external_requests.push(url.href);return route.abort('blockedbyclient');
    });
    page=await context.newPage();page.setDefaultTimeout(25000);page.setDefaultNavigationTimeout(60000);
    page.on('pageerror',error=>report.page_errors.push(String(error)));
    page.on('console',message=>{if(message.type()==='error')report.console_errors.push(message.text());});
    page.on('requestfailed',request=>report.request_failures.push({url:request.url(),error:request.failure()?.errorText}));
    page.on('response',response=>{
      const url=new URL(response.url());
      if(!response.ok())report.http_errors.push({url:url.href,status:response.status()});
      if(url.pathname.startsWith('/python-runtime/')||url.pathname==='/knowledge-practice-worker.js')report.runtime_assets.push({path:url.pathname,status:response.status()});
    });
    await page.goto(base);await theme('light');
    if(smoke)await readOnlySmoke();else await runAcceptance();report.passed=true;
  } catch(error) {
    report.passed=false;report.error=String(error.stack||error);process.exitCode=1;
    if(page) {
      await page.screenshot({path:path.join(output,smoke?'smoke-failure.png':'failure.png')}).catch(()=>{});
      report.failure_url=page.url();
      report.failure_visible_text=await page.locator('body').innerText().catch(()=>'');
    }
    console.error(error);
  } finally {
    report.finished_at=new Date().toISOString();
    fs.writeFileSync(path.join(output,smoke?'attention-demo-smoke.json':'attention-demo-browser.json'),JSON.stringify(report,null,2));
    if(browser)await browser.close();
  }
})();
