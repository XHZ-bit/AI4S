/* Real learning business API; only the isolated server's model HTTP transport
 * is deterministic. Prepare fixture, start its evaluation server and Vite first.
 * Usage: node this-file [fixture directory] [isolated Vite URL]
 */
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('../../frontend/node_modules/playwright');
const directory=path.resolve(process.argv[2]||'.ui_validation/learning-entry-20261117');
const base=process.argv[3]||'http://127.0.0.1:15319';
assert.ok(directory.includes(path.sep+'.ui_validation'+path.sep));assert.ok(!['5173','8000'].includes(new URL(base).port));assert.ok(['127.0.0.1','localhost'].includes(new URL(base).hostname));
const fixture=JSON.parse(fs.readFileSync(path.join(directory,'fixture.json'),'utf8').replace(/^\uFEFF/,''));
const output=path.join(directory,'learning-browser');fs.mkdirSync(output,{recursive:true});
const report={started_at:new Date().toISOString(),fixture:directory,source_kind:'authored_teaching_material',model_stub:'fixed_http_transport',real_provider_calls:0,checks:[],screenshots:[],learning_posts:[],page_errors:[],console_errors:[],http_errors:[],expected_aborts:[],unexpected_request_failures:[],blocked_external:[]};
let browser,page;
const root=`/api/projects/${fixture.project_id}/knowledge/nodes/`;
const workspace=(key='goal',view='learning')=>`${base}/research/${fixture.project_id}?view=${view}&node=${fixture.nodes[key]}`;
const article=()=>page.locator('.kw-learning-view');
const primary=()=>article().locator('.kw-learning-request').getByRole('button');
async function openRequestOptions(){const summary=article().locator('summary').filter({hasText:'调整学习目标与深度'});if(await summary.count()&&!await summary.locator('..').evaluate(element=>element.open))await summary.click();}
async function manualGenerate(){await openRequestOptions();await primary().click();}
const posts=key=>report.learning_posts.filter(item=>item.node_id===fixture.nodes[key]);
async function check(name,action){const start=Date.now();try{const detail=await action();report.checks.push({name,passed:true,milliseconds:Date.now()-start,detail});console.log('PASS',name);}catch(error){report.checks.push({name,passed:false,error:String(error.stack||error)});throw error;}}
async function api(suffix,method='GET',data){const response=await page.request.fetch(base+suffix,{method,data});assert.ok(response.ok(),`${response.status()} ${await response.text()}`);return response.json();}
const control=data=>api('/api/__acceptance__/learning/control','POST',data);
const stats=()=>api('/api/__acceptance__/learning/stats');
async function artifact(key){return api(root+fixture.nodes[key]+'/learning');}
async function waitUntil(action,message,timeout=25000){const start=Date.now();while(Date.now()-start<timeout){const value=await action();if(value)return value;await new Promise(resolve=>setTimeout(resolve,120));}throw new Error('Timed out: '+message);}
async function ready(key,status='ready',goal){return waitUntil(async()=>{const a=await artifact(key);return a.status===status&&(goal===undefined||a.goal===goal)?a:false;},`${key} ${status}`);}
async function go(key,view='learning'){await page.goto(workspace(key,view));if(view==='learning')await article().getByRole('heading',{name:fixture.labels[key],exact:true}).waitFor();else await page.getByRole('complementary',{name:'知识节点详情'}).getByRole('heading',{name:fixture.labels[key],exact:true}).waitFor();}
async function quiet(){await page.waitForLoadState('networkidle');}
async function shot(name,allowBusy=false){if(!allowBusy)await quiet();const file=path.join(output,name+'.png');await page.screenshot({path:file,fullPage:false});report.screenshots.push(file);}
async function theme(value){await page.evaluate(value=>{localStorage.setItem('research-atlas-theme',value);window.dispatchEvent(new StorageEvent('storage',{key:'research-atlas-theme',newValue:value}));},value);await page.locator(`html[data-theme="${value}"]`).waitFor();}
async function mainText(){return article().locator('.kw-learning-main').innerText();}
async function finishAttempt(key,before){await waitUntil(()=>posts(key).length>before,'learning POST starts');await waitUntil(async()=>{const calls=(await stats()).calls.filter(call=>call.node_id===fixture.nodes[key]);return calls.length&&calls.every(call=>call.finished);},'fixed model calls finish');await quiet();}
(async()=>{try{
 browser=await chromium.launch({headless:true,channel:'chrome'});const context=await browser.newContext({viewport:{width:1366,height:768},reducedMotion:'reduce'});
 await context.route('**/*',route=>{const url=new URL(route.request().url());if(['127.0.0.1','localhost'].includes(url.hostname))return route.continue();report.blocked_external.push(url.href);return route.abort();});
 page=await context.newPage();page.setDefaultTimeout(25000);page.setDefaultNavigationTimeout(60000);
 page.on('pageerror',error=>report.page_errors.push(String(error)));page.on('console',message=>{if(message.type()==='error')report.console_errors.push(message.text());});
 page.on('response',response=>{if(!response.ok()&&response.url().includes('/api/'))report.http_errors.push({status:response.status(),url:response.url()});});
 page.on('request',request=>{const match=new URL(request.url()).pathname.match(/\/knowledge\/nodes\/([^/]+)\/learning$/);if(request.method()==='POST'&&match)report.learning_posts.push({node_id:decodeURIComponent(match[1]),body:request.postDataJSON(),at:Date.now()});});
 page.on('requestfailed',request=>{const value={url:request.url(),method:request.method(),error:request.failure()?.errorText};const aborted=/ABORT|CANCEL/i.test(value.error||'');if(aborted&&value.url.startsWith(base+'/api/')&&['GET','HEAD'].includes(value.method))report.expected_aborts.push({...value,kind:'cancellable_read_on_navigation'});else if(aborted&&/\/learning(?:\?|$)/.test(value.url))report.expected_aborts.push({...value,kind:'cancelled_learning_wait'});else report.unexpected_request_failures.push(value);});
 await check('first_click_prepares_once_while_rich_basics_remain_readable',async()=>{
  await control({node_id:fixture.nodes.goal,scenario:{hold:true}});await go('goal','graph');await page.getByRole('complementary',{name:'知识节点详情'}).getByRole('button',{name:'深入学习',exact:true}).click();
  await article().getByRole('heading',{name:fixture.labels.goal,exact:true}).waitFor();await waitUntil(()=>posts('goal').length===1,'one automatic POST');
  const primer=article().getByRole('region',{name:'知识基础讲解'});await primer.waitFor();const basic=(await primer.innerText());assert.ok(basic.length>400);assert.ok((await mainText()).length>600);const contentTop=(await primer.boundingBox()).y;
  const optionsSummary=article().locator('summary').filter({hasText:'调整学习目标与深度'});if(await optionsSummary.count())assert.equal(await optionsSummary.locator('..').evaluate(element=>element.open),false);
  assert.equal(await article().getByLabel('深入学习目标').inputValue(),posts('goal')[0].body.goal);await shot('1366-light-preparing-with-basics',true);
  await control({release:[fixture.nodes.goal]});const saved=await ready('goal');await quiet();assert.equal(posts('goal').length,1);assert.ok((await mainText()).includes('已核对教学详解'));
  return {automatic_posts:1,basic_guide_characters:basic.length,basic_content_top:contentTop,request_options_opened:false,status:saved.status,goal:saved.goal,depth:saved.depth};
 });
 await check('ready_lesson_reopens_without_another_model_request',async()=>{
  const before=posts('goal').length;await go('goal','graph');await page.getByRole('complementary',{name:'知识节点详情'}).getByRole('button',{name:'深入学习',exact:true}).click();await article().getByRole('heading',{name:fixture.labels.goal,exact:true}).waitFor();await quiet();
  assert.equal(posts('goal').length,before);assert.ok((await mainText()).includes('已核对教学详解'));await page.reload();await article().getByRole('heading',{name:fixture.labels.goal,exact:true}).waitFor();await quiet();assert.equal(posts('goal').length,before);
  return {reopen_and_reload_posts:0,status:(await artifact('goal')).status};
 });
 await check('failed_refresh_and_manual_edits_preserve_readable_content',async()=>{
  const original=await artifact('goal');await control({node_id:fixture.nodes.goal,scenario:{reject:true}});let before=posts('goal').length;await manualGenerate();await finishAttempt('goal',before);const failed=await ready('goal','partial');
  assert.equal(failed.sections.derivation,original.sections.derivation);assert.ok(failed.last_generation?.message);assert.ok(failed.last_generation?.retryable);assert.ok(failed.last_generation?.retained);
  const text='人工核对：缩放分数4.0位于softmax之前；这是我的已保存推导。';await article().getByRole('button',{name:'修订讲解：公式与推导',exact:true}).click();await article().getByLabel('公式与推导内容',{exact:true}).fill(text);await article().getByRole('button',{name:'保存讲解修订',exact:true}).click();await article().getByRole('status').filter({hasText:'学习内容已保存'}).waitFor();
  const revised=await artifact('goal');assert.equal(revised.sections.derivation,text);before=posts('goal').length;await manualGenerate();await finishAttempt('goal',before);const retained=await artifact('goal');assert.equal(retained.sections.derivation,text);assert.ok(retained.user_edited_sections.includes('derivation'));
  before=posts('goal').length;await page.reload();await article().getByRole('heading',{name:fixture.labels.goal,exact:true}).waitFor();await quiet();assert.equal(posts('goal').length,before);assert.ok((await mainText()).includes(text));
  await control({node_id:fixture.nodes.goal,scenario:{}});await manualGenerate();await finishAttempt('goal',before);const recovered=await ready('goal');assert.equal(recovered.sections.derivation,text);
  return {failed_diagnostic:failed.last_generation,manual_text:text,recovered_status:recovered.status,manual_sections:recovered.user_edited_sections};
 });
 await check('first_review_failure_keeps_basics_and_retries_the_edited_goal',async()=>{
  const issue='隔离验收对象意见：数值计算仍需核对';await control({node_id:fixture.nodes.self_attention,scenario:{reject:true,review_issues:[{section:'derivation',category:'arithmetic',blocking:true,description:issue}]}});await go('self_attention');const failed=await ready('self_attention','partial');await quiet();assert.equal(posts('self_attention').length,1);
  assert.ok(!(await mainText()).includes('未审核候选内容'));assert.ok(!failed.sections.derivation.includes('未审核候选内容'));await article().getByRole('region',{name:'知识基础讲解'}).waitFor();assert.ok(failed.last_generation?.retryable);
  const result=article().getByRole('status',{name:'详细讲解准备结果'});await result.locator('summary').click();await result.getByText('公式与推导：'+issue,{exact:true}).waitFor();await result.locator('summary').click();assert.equal(failed.last_generation.issues[0].description,issue);
  const oldGoal=await article().getByLabel('深入学习目标').inputValue();await theme('dark');await shot('1366-dark-failed-review-with-basics');await page.reload();await article().getByRole('heading',{name:fixture.labels.self_attention,exact:true}).waitFor();await quiet();assert.equal(posts('self_attention').length,1);assert.equal(await article().getByLabel('深入学习目标').inputValue(),oldGoal);
  const goal='解释自注意力的信息来源，并区分掩码允许的位置。';await openRequestOptions();await article().getByLabel('深入学习目标').fill(goal);await control({node_id:fixture.nodes.self_attention,scenario:{}});assert.equal(await primary().innerText(),'重试深入讲解');await manualGenerate();const recovered=await ready('self_attention','ready',goal);await quiet();assert.equal(posts('self_attention').length,2);assert.equal(posts('self_attention')[1].body.goal,goal);
  return {first_status:failed.status,failed_diagnostic:failed.last_generation,preserved_goal:oldGoal,retry_goal:recovered.goal,posts:2};
 });
 await check('late_learning_response_cannot_replace_a_new_node',async()=>{
  await control({node_id:fixture.nodes.dot,scenario:{hold:true}});await go('dot');await waitUntil(()=>posts('dot').length===1,'delayed dot automatic POST');await waitUntil(async()=>(await stats()).calls.some(call=>call.node_id===fixture.nodes.dot&&!call.finished),'held model generation');
  await go('multihead');await ready('multihead');await control({release:[fixture.nodes.dot]});await ready('dot');await quiet();assert.equal(new URL(page.url()).searchParams.get('node'),fixture.nodes.multihead);await article().getByRole('heading',{name:fixture.labels.multihead,exact:true}).waitFor();assert.ok(!(await mainText()).includes('已核对教学详解：'+fixture.labels.dot+'。'));
  const detail=await api(root+fixture.nodes.multihead);assert.equal(detail.study_guide.topic,'multi_head_attention');const recall=article().locator('#kw-learning-primer details');if(await recall.count())await recall.locator('summary').first().click();await article().getByRole('heading',{name:'多头注意力：并行比较，再组合信息',exact:true}).waitFor();await shot('1366-dark-multi-head-guide');
  return {delayed_node:fixture.nodes.dot,current_node:fixture.nodes.multihead,current_topic:detail.study_guide.topic,stale_response_displayed:false};
 });
 await check('leaving_learning_while_generation_runs_keeps_the_destination',async()=>{
  await control({node_id:fixture.nodes.unrelated,scenario:{hold:true}});await go('unrelated');await waitUntil(()=>posts('unrelated').length===1,'delayed unrelated automatic POST');await article().getByRole('button',{name:'返回原位置',exact:true}).click();await page.locator('.kw-graph-view').waitFor();await control({release:[fixture.nodes.unrelated]});await ready('unrelated');await quiet();assert.equal(new URL(page.url()).searchParams.get('view'),'graph');assert.equal(await article().count(),0);
  return {view:'graph',late_response_displayed:false};
 });
 await check('unconfigured_model_keeps_a_useful_paper_reading_guide_without_post',async()=>{
  await control({configured:false,enabled:false});await go('root');await quiet();assert.equal(posts('root').length,0);const detail=await api(root+fixture.nodes.root);assert.equal(detail.study_guide.topic,'paper_reading');assert.equal(detail.study_guide.origin,'authored_teaching');await article().getByRole('heading',{name:'从研究问题开始读这篇论文',exact:true}).waitFor();const text=await article().getByRole('region',{name:'知识基础讲解'}).innerText();assert.ok(text.length>500);await theme('light');await shot('1366-light-paper-reading-guide');
  return {model_configured:false,automatic_posts:0,topic:detail.study_guide.topic,guide_characters:text.length,paper_title:fixture.labels.root};
 });
 await check('no_unexpected_errors_and_all_model_calls_are_fixed_transport',async()=>{
  for(const key of ['page_errors','console_errors','http_errors','unexpected_request_failures','blocked_external'])assert.deepEqual(report[key],[],key);report.fixed_model_calls=(await stats()).calls;assert.equal((await stats()).real_provider_calls,0);return {real_provider_calls:0,fixed_model_calls:report.fixed_model_calls.length,expected_aborts:report.expected_aborts.length};
 });report.passed=true;
}catch(error){report.passed=false;report.error=String(error.stack||error);console.error(error);if(page)await shot('failure').catch(()=>{});process.exitCode=1;}
finally{if(page)await control({release:Object.values(fixture.nodes)}).catch(()=>{});report.finished_at=new Date().toISOString();fs.writeFileSync(path.join(output,'report.json'),JSON.stringify(report,null,2));if(browser)await browser.close();}})();
