/* Real isolated API and fixed model transport; fixed-node desktop QA.
 * Usage: node this-file [prepared fixture directory] [isolated Vite URL].
 */
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('../../frontend/node_modules/playwright');
const directory=path.resolve(process.argv[2]||'.ui_validation/learning-desk-20261117');
const base=process.argv[3]||'http://127.0.0.1:15329';
assert.ok(directory.includes(path.sep+'.ui_validation'+path.sep));assert.ok(['127.0.0.1','localhost'].includes(new URL(base).hostname));assert.ok(!['5173','8000'].includes(new URL(base).port));
const fixture=JSON.parse(fs.readFileSync(path.join(directory,'fixture.json'),'utf8').replace(/^\uFEFF/,''));
const captureEvidence=process.argv.includes('--capture-evidence');
const output=path.join(directory,'desk-browser');fs.mkdirSync(output,{recursive:true});
const report={started_at:new Date().toISOString(),fixture:directory,source_kind:'authored_teaching_material',model_stub:'fixed_http_transport',real_provider_calls:0,checks:[],screenshots:[],matrix:[],page_errors:[],console_errors:[],http_errors:[],expected_aborts:[],unexpected_request_failures:[],external_requests:[],learning_posts:[]};
let browser,page;
const draft='本节点未保存的笔记草稿：注意力缩放分数与归一化权重要分别核对。';
const question='草稿问题：为什么需要先按键向量维度缩放？';
const article=()=>page.locator('.kw-learning-view');
const tools=()=>page.getByRole('complementary',{name:'随手学习工具',exact:true});
const mainTab=name=>page.getByRole('tablist',{name:'学习阅读分区',exact:true}).getByRole('tab',{name,exact:true});
const toolTab=name=>tools().getByRole('tablist',{name:'随手学习工具分区',exact:true}).getByRole('tab',{name,exact:true});
const panel=name=>article().getByRole('tabpanel',{name,exact:true});
const reader=()=>article().locator('.kw-learning-reader-scroll:visible').first();
const primary=()=>article().getByRole('button',{name:'生成个性化讲解',exact:true});
const workspace=(key='goal')=>`${base}/research/${fixture.project_id}?view=learning&node=${fixture.nodes[key]}`;
async function api(url,method='GET',data){const response=await page.request.fetch(base+url,{method,data});assert.ok(response.ok(),`${response.status()} ${await response.text()}`);return response.json();}
const nodeApi=(key='goal')=>`/api/projects/${fixture.project_id}/knowledge/nodes/${fixture.nodes[key]}`;
async function waitUntil(action,message,timeout=25000){const start=Date.now();while(Date.now()-start<timeout){const value=await action();if(value)return value;await new Promise(resolve=>setTimeout(resolve,100));}throw new Error('Timed out: '+message);}
async function check(name,action){const start=Date.now();try{const detail=await action();report.checks.push({name,passed:true,milliseconds:Date.now()-start,detail});console.log('PASS',name);}catch(error){report.checks.push({name,passed:false,error:String(error.stack||error)});throw error;}}
async function quiet(){await page.waitForLoadState('networkidle');}
async function open(key='goal'){await page.goto(workspace(key));await article().getByRole('heading',{name:fixture.labels[key],exact:true}).waitFor();await tools().waitFor();await quiet();}
async function readTab(name){const tab=mainTab(name);if(await tab.getAttribute('aria-selected')!=='true')await tab.click();await panel(name).waitFor();}
async function chooseTool(name){const tab=toolTab(name);if(await tab.getAttribute('aria-selected')!=='true')await tab.click();await panel(name).waitFor();}
async function theme(value){await page.evaluate(value=>{localStorage.setItem('research-atlas-theme',value);window.dispatchEvent(new StorageEvent('storage',{key:'research-atlas-theme',newValue:value}));},value);await page.locator(`html[data-theme="${value}"]`).waitFor();}
async function shot(name){await quiet();const file=path.join(output,name+'.png');await page.screenshot({path:file,fullPage:false});report.screenshots.push(file);}
async function box(locator){const r=await locator.boundingBox();assert.ok(r);return r;}
async function visibleInViewport(locator,label){const b=await box(locator),viewport=page.viewportSize();assert.ok(b.y>=0&&b.y+b.height<=viewport.height+2,`${label}: ${JSON.stringify(b)} versus ${viewport.height}`);assert.ok(b.x>=0&&b.x+b.width<=viewport.width+2,`${label}: horizontal overflow`);return b;}
async function scrollReader(distance){await reader().hover();await page.mouse.wheel(0,distance);await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));return reader().evaluate(element=>element.scrollTop);}
async function metrics(){return page.evaluate(()=>({width:innerWidth,height:innerHeight,document_width:document.documentElement.scrollWidth,document_height:document.documentElement.scrollHeight,readers:[...document.querySelectorAll('.kw-learning-reader-scroll')].filter(element=>element.getClientRects().length).map(element=>({height:element.clientHeight,scroll_height:element.scrollHeight,top:element.getBoundingClientRect().top,bottom:element.getBoundingClientRect().bottom,scroll_top:element.scrollTop}))}));}
(async()=>{try{
 browser=await chromium.launch({headless:true,channel:'chrome'});const context=await browser.newContext({viewport:{width:1366,height:768},reducedMotion:'reduce'});
 await context.route('**/*',route=>{const url=new URL(route.request().url());if(['127.0.0.1','localhost'].includes(url.hostname))return route.continue();report.external_requests.push(url.href);return route.abort();});
 page=await context.newPage();page.setDefaultTimeout(25000);page.setDefaultNavigationTimeout(60000);
 page.on('pageerror',error=>report.page_errors.push(String(error)));page.on('console',message=>{if(message.type()==='error')report.console_errors.push(message.text());});
 page.on('response',response=>{if(!response.ok()&&response.url().includes('/api/'))report.http_errors.push({status:response.status(),url:response.url()});});
 page.on('request',request=>{if(request.method()==='POST'&&/\/knowledge\/nodes\/[^/]+\/learning$/.test(new URL(request.url()).pathname))report.learning_posts.push({url:request.url(),body:request.postDataJSON()});});
 page.on('requestfailed',request=>{const item={url:request.url(),method:request.method(),error:request.failure()?.errorText};if(/ABORT|CANCEL/i.test(item.error||'')&&item.url.startsWith(base+'/api/')&&(['GET','HEAD'].includes(item.method)||/\/learning(?:\?|$)/.test(item.url)))report.expected_aborts.push(item);else report.unexpected_request_failures.push(item);});
 if(captureEvidence){await page.setViewportSize({width:1920,height:1080});await open();await theme('light');await readTab('原文依据');await panel('原文依据').getByRole('button',{name:/^当前知识的直接依据/}).click();await chooseTool('学习记录');await panel('学习记录').getByRole('status').waitFor();await tools().getByRole('button',{name:'查看学习小结',exact:true}).waitFor();const summary=await panel('学习记录').getByRole('status').innerText();assert.ok(summary.length>10);await shot('1920-light-long-evidence');report.checks.push({name:'fixed_evidence_and_loaded_summary_capture',passed:true,summary});report.passed=true;return;}
 await check('primary_generation_and_learning_tools_are_available_on_entry',async()=>{
  await open();await readTab('讲解');assert.equal(report.learning_posts.length,0);const button=await visibleInViewport(primary(),'primary generation');const status=await visibleInViewport(tools().getByLabel('我的学习状态'),'learning status');for(const name of ['提问','笔记','学习记录'])await visibleInViewport(toolTab(name),name);
  const details=article().locator('details.kw-learning-customize');if(await details.count())assert.equal(await details.evaluate(element=>element.open),false);
  await chooseTool('提问');await visibleInViewport(tools().getByLabel('节点问题'),'question field');await shot('1366-light-learning-desk');return {button,status,automatic_model_posts:0};
 });
 await check('bare_aligned_and_nested_matrices_render_with_recoverable_fallback',async()=>{
  await readTab('讲解');const section=panel('讲解').locator('#kw-learning-derivation');await section.scrollIntoViewIfNeeded();const annotations=await section.locator('.katex-display annotation').allTextContents();assert.ok(annotations.some(text=>text.includes('MultiHead')&&text.includes('aligned')));assert.ok(annotations.some(text=>text.includes('bmatrix')));assert.equal(await section.locator('.katex-error').count(),0);
  const fallback=section.locator('.learning-math-fallback').filter({hasText:'公式排版未完成'});await fallback.getByRole('button',{name:'查看原式',exact:true}).click();assert.ok((await fallback.locator('.learning-math-original').textContent()).includes(fixture.invalid));await fallback.getByRole('button',{name:'收起原式',exact:true}).click();
  await chooseTool('笔记');await tools().getByLabel('我的理解',{exact:true}).fill(draft);await panel('讲解').getByLabel('跳转讲解章节').selectOption('kw-learning-derivation');await theme('dark');await shot('1366-dark-math-and-notes');return {display_math:annotations.length,bare_aligned_rendered:true,nested_matrix_rendered:true,invalid_source_recoverable:true};
 });
 await check('long_evidence_is_separate_bounded_and_returns_to_the_reading_position',async()=>{
  await readTab('原文依据');const evidence=panel('原文依据');const before=await metrics();assert.ok(before.document_height<=before.height*1.5);assert.ok(before.readers.every(item=>item.bottom<=before.height+2));
  const cards=evidence.locator('.kw-learning-evidence-card');assert.ok(await cards.count()<=6);const count=await cards.count();assert.ok(count>0);await evidence.getByRole('button',{name:/^同篇相关上下文/}).click();const initialContext=await cards.count();assert.ok(initialContext>0&&initialContext<=6);const more=evidence.getByRole('button',{name:/^显示更多依据/});if(await more.count()){await more.click();assert.ok(await cards.count()<=12);}
  const last=cards.last();if(!await last.evaluate(element=>element.open))await last.locator('summary').click();const sourceButton=last.getByRole('button',{name:/打开原文|定位原文|查看原文/}).first();await sourceButton.scrollIntoViewIfNeeded();const scroll=await reader().evaluate(element=>element.scrollTop);await sourceButton.click();await page.locator('.kw-source-reader').waitFor();const original=new URL(page.url());assert.equal(original.searchParams.get('view'),'reading');assert.equal(original.searchParams.get('source'),fixture.long_source_id);assert.ok(original.searchParams.get('block'));
  const savedScroll=await page.evaluate(key=>JSON.parse(sessionStorage.getItem(key)||'null')?.scroll?.evidence,'paperstride:learning-reader:'+JSON.stringify(['local',fixture.project_id,fixture.nodes.goal]));assert.equal(typeof savedScroll,'number');
  await page.getByRole('button',{name:'返回原位置',exact:true}).click();await article().getByRole('heading',{name:fixture.labels.goal,exact:true}).waitFor();await panel('原文依据').waitFor();await quiet();const restored=await reader().evaluate(element=>element.scrollTop);assert.ok(Math.abs(restored-savedScroll)<=3,`Reading scroll before click=${scroll}, saved=${savedScroll} -> ${restored}`);
  assert.equal(await evidence.getByRole('button',{name:/^同篇相关上下文/}).getAttribute('aria-pressed'),'true');return {initial_direct_cards:count,initial_context_cards:initialContext,evidence_count:fixture.learning_evidence_count,before_source_scroll:scroll,navigation_saved_scroll:savedScroll,restored_scroll:restored,...before};
 });
 await check('tabs_preserve_question_note_and_unsaved_lesson_revision',async()=>{
  await chooseTool('提问');await tools().getByLabel('节点问题').fill(question);await chooseTool('笔记');assert.equal(await tools().getByLabel('我的理解',{exact:true}).inputValue(),draft);await readTab('练习与实现');await readTab('讲解');await chooseTool('提问');assert.equal(await tools().getByLabel('节点问题').inputValue(),question);await chooseTool('笔记');assert.equal(await tools().getByLabel('我的理解',{exact:true}).inputValue(),draft);
  await panel('讲解').getByRole('button',{name:'修订讲解：公式与推导',exact:true}).click();const revised=fixture.manual_derivation+'\n未保存的讲解修订草稿。';await panel('讲解').getByLabel('公式与推导内容',{exact:true}).fill(revised);await readTab('原文依据');await readTab('讲解');assert.equal(await panel('讲解').getByLabel('公式与推导内容',{exact:true}).inputValue(),revised);await panel('讲解').getByRole('button',{name:'取消修订',exact:true}).click();
  return {question_preserved:true,note_preserved:true,lesson_revision_preserved:true};
 });
 await check('status_summary_and_node_scoped_notes_save_and_reopen',async()=>{
  const status=tools().getByLabel('我的学习状态');await waitUntil(()=>status.isEnabled(),'progress available');await status.selectOption('understood');await tools().getByText('学习状态已保存：自评理解',{exact:true}).waitFor();assert.equal((await api(nodeApi()+'/progress')).status,'understood');await tools().getByRole('button',{name:'查看学习小结',exact:true}).click();await panel('学习记录').waitFor();await quiet();assert.equal(await toolTab('学习记录').getAttribute('aria-selected'),'true');
  await open('multihead');await chooseTool('提问');assert.equal(await tools().getByLabel('节点问题').inputValue(),'');await chooseTool('笔记');assert.equal(await tools().getByLabel('我的理解',{exact:true}).inputValue(),'');assert.equal((await api(nodeApi('multihead')+'/progress')).status,'not_started');
  await open();await chooseTool('笔记');await waitUntil(async()=>await tools().getByLabel('我的理解',{exact:true}).inputValue()===draft,'A note draft restored');assert.equal((await api(nodeApi()+'/progress')).status,'understood');await tools().getByRole('button',{name:'保存笔记',exact:true}).click();await tools().locator('.kw-node-note-actions [role="status"]').filter({hasText:'已保存'}).waitFor();await page.reload();await article().getByRole('heading',{name:fixture.labels.goal,exact:true}).waitFor();await chooseTool('笔记');await waitUntil(async()=>await tools().getByLabel('我的理解',{exact:true}).inputValue()===draft,'saved note reopens');
  const records=await api(`/api/workbench/records?project_id=${fixture.project_id}&knowledge_node_id=${fixture.nodes.goal}`);assert.ok(records.items.some(item=>item.body===draft));return {status:'understood',summary_opened_once:true,note_saved:true,other_node_clean:true};
 });
 await check('primary_action_remains_visible_and_generates_without_opening_options',async()=>{
  await readTab('讲解');await scrollReader(100000);await visibleInViewport(primary(),'scrolled primary action');const before=report.learning_posts.length;await primary().click();await waitUntil(()=>report.learning_posts.length===before+1,'primary action sends one POST');await quiet();const saved=await api(nodeApi()+'/learning');assert.equal(saved.sections.derivation,fixture.manual_derivation);await visibleInViewport(primary(),'primary action after generation');return {posts:1,manual_math_preserved:true};
 });
 await check('fixed_node_desktop_theme_matrix_keeps_the_workspace_in_view',async()=>{
  for(const [width,height] of [[1366,768],[1440,900],[1920,1080]])for(const color of ['light','dark']){await page.setViewportSize({width,height});await theme(color);await open();await readTab('讲解');const data=await metrics();assert.ok(data.document_width<=width+1);assert.ok(data.readers.every(item=>item.bottom<=height+2));const button=await visibleInViewport(primary(),'primary');const dock=await visibleInViewport(tools().getByLabel('我的学习状态'),'status');for(const name of ['提问','笔记','学习记录'])await visibleInViewport(toolTab(name),name);report.matrix.push({width,height,color,button,status:dock,...data});}
  await page.setViewportSize({width:1920,height:1080});await theme('light');await open();await readTab('原文依据');await chooseTool('学习记录');await shot('1920-light-long-evidence');return report.matrix;
 });
 await check('no_unexpected_runtime_or_external_errors',async()=>{
  for(const key of ['page_errors','console_errors','http_errors','unexpected_request_failures','external_requests'])assert.deepEqual(report[key],[],key);const model=await api('/api/__acceptance__/learning/stats');assert.equal(model.real_provider_calls,0);report.fixed_model_calls=model.calls;return {real_provider_calls:0,expected_cancellations:report.expected_aborts.length,fixed_model_calls:model.calls.length};
 });report.passed=true;
}catch(error){report.passed=false;report.error=String(error.stack||error);console.error(error);if(page)await shot('failure').catch(()=>{});process.exitCode=1;}
finally{report.finished_at=new Date().toISOString();fs.writeFileSync(path.join(output,captureEvidence?'report-evidence-capture.json':'report.json'),JSON.stringify(report,null,2));if(browser)await browser.close();}})();
