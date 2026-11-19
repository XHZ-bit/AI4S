/* Run against prepare_route_fixture.py + an isolated offline API/Vite instance.
 * Usage: node evaluation/research_atlas/run_route_browser.cjs [fixture dir] [base URL]
 * Normal product interactions persist the route. Source/node PATCH calls below
 * deliberately simulate external changes to the isolated teaching fixture.
 */
const fs=require('node:fs'), path=require('node:path'), assert=require('node:assert/strict');
const {chromium}=require('../../frontend/node_modules/playwright');
const directory=path.resolve(process.argv[2]||'.ui_validation/learning-route-20261116');
const base=process.argv[3]||'http://127.0.0.1:15297';
const fixture=JSON.parse(fs.readFileSync(path.join(directory,'fixture.json'),'utf8').replace(/^\uFEFF/,''));
const output=path.join(directory,'browser'); fs.mkdirSync(output,{recursive:true});
const report={started_at:new Date().toISOString(),fixture:directory,source_kind:fixture.source_kind,
 model_stub:fixture.model_stub,real_provider_calls:fixture.real_provider_calls,checks:[],screenshots:[],
 page_errors:[],http_errors:[],model_requests:[],blocked_external:[]};
let browser,page;
const workspace=(query='view=route')=>`${base}/research/${fixture.project_id}?${query}`;
async function check(name,action){const started=Date.now();try{const detail=await action();report.checks.push({name,passed:true,milliseconds:Date.now()-started,detail});console.log('PASS',name);}catch(error){report.checks.push({name,passed:false,error:String(error.stack||error)});throw error;}}
async function api(suffix,method='GET',data){const response=await page.request.fetch(`${base}/api/projects/${fixture.project_id}/${suffix}`,{method,data});assert.ok(response.ok(),`${response.status()} ${await response.text()}`);return response.json();}
async function saved(){return (await api('knowledge/learning-route')).route;}
async function routePage(){await page.goto(workspace());await page.getByRole('region',{name:'我的学习路线',exact:true}).waitFor();}
async function openDetails(locator){if(await locator.getAttribute('open')===null)await locator.locator(':scope > summary').click();}
async function contains(locator,text){await locator.filter({hasText:text}).first().waitFor({state:'visible'});}
function step(label){return page.locator('.kw-route-steps > li').filter({has:page.getByRole('heading',{name:label,exact:true})});}
async function shot(name,locator){if(locator)await locator.evaluate(element=>{element.scrollIntoView({block:'start'});let parent=element.parentElement;while(parent&&parent!==document.documentElement){if(/auto|scroll/.test(getComputedStyle(parent).overflowY)&&parent.scrollHeight>parent.clientHeight){parent.scrollBy(0,-85);return;}parent=parent.parentElement;}window.scrollBy(0,-85);});const file=path.join(output,name+'.png');await page.screenshot({path:file,fullPage:false});report.screenshots.push(file);}
async function theme(value){await page.evaluate(value=>{localStorage.setItem('research-atlas-theme',value);window.dispatchEvent(new StorageEvent('storage',{key:'research-atlas-theme',newValue:value}));},value);await page.locator(`html[data-theme="${value}"]`).waitFor();}
async function waitNotice(text){await contains(page.locator('.kw-learning-route [role="status"]'),text);}
(async()=>{try{
 browser=await chromium.launch({headless:true,channel:'chrome'});
 const context=await browser.newContext({viewport:{width:1366,height:768},reducedMotion:'reduce'});
 await context.route('**/*',route=>{const url=new URL(route.request().url());if(['127.0.0.1','localhost'].includes(url.hostname))return route.continue();report.blocked_external.push(url.href);return route.abort();});
 page=await context.newPage();page.setDefaultTimeout(30000);page.setDefaultNavigationTimeout(60000);
 page.on('pageerror',error=>report.page_errors.push(String(error)));
 page.on('response',response=>{if(!response.ok()&&response.url().includes('/api/'))report.http_errors.push({status:response.status(),url:response.url()});});
 page.on('request',request=>{if(request.method()==='POST'&&/\/(generate|supplement|question|summary|analyze)$|\/learning$/.test(new URL(request.url()).pathname))report.model_requests.push(request.url());});
 await check('preview_is_read_only_and_uses_real_prerequisite_branches',async()=>{
   await page.goto(workspace(`view=route&node=${fixture.nodes.goal}`));await page.getByRole('region',{name:'我的学习路线',exact:true}).waitFor();
   assert.equal(await saved(),null,'Use a freshly prepared fixture for this first-pass acceptance');
   await page.getByRole('button',{name:'预览学习路线',exact:true}).click();
   const preview=page.getByRole('region',{name:'学习路线预览',exact:true});await preview.waitFor();
   assert.equal(await preview.locator('ol > li').count(),3);
   for(const label of ['向量点积','Softmax归一化','缩放点积注意力'])await contains(preview,label);
   assert.equal(await saved(),null,'Preview must not create a saved route');
   const expected=await api('knowledge/learning-route/preview','POST',{target_node_id:fixture.nodes.goal});
   assert.deepEqual(new Set(expected.steps.map(item=>item.node_id)),new Set([fixture.nodes.dot,fixture.nodes.softmax,fixture.nodes.goal]));
   assert.ok(expected.steps.every(item=>!fixture.teaching_node_ids.includes(item.node_id)),'SUPPLEMENTS are not forced prerequisites');
   assert.equal(expected.edges.length,2);assert.ok(expected.edges.every(item=>item.kind==='PREREQUISITE_OF'));
   await shot('1366-light-route-preview',preview);
   await page.getByRole('button',{name:'保存并使用路线',exact:true}).click();await waitNotice('学习路线已保存');
   const value=await saved();assert.equal(value.revision,1);assert.equal(value.target_node_id,fixture.nodes.goal);
   return {steps:value.steps.map(item=>({node_id:item.node_id,label:item.label})),edges:expected.edges.map(item=>({source:item.source,target:item.target,kind:item.kind})),excluded_teaching_count:fixture.teaching_node_ids.length};
 });
 await check('manual_skip_reorder_complete_preserve_self_assessment',async()=>{
   let value=await saved();const first=value.steps[0];
   const before=await api(`knowledge/nodes/${first.node_id}/progress`);assert.equal(before.status,'not_started');
   await step(first.label).getByRole('button',{name:'本次跳过',exact:true}).click();await waitNotice('步骤已保存');
   value=await saved();assert.equal(value.steps.find(item=>item.node_id===first.node_id).state,'skipped');
   const next=value.steps.find(item=>item.node_id===value.next_node_id);assert.ok(next);
   await step(next.label).getByRole('button',{name:'完成这一步',exact:true}).click();await waitNotice('步骤已保存');
   value=await saved();assert.equal(value.steps.find(item=>item.node_id===next.node_id).state,'done');
   assert.equal((await api(`knowledge/nodes/${next.node_id}/progress`)).status,'not_started','Task completion must not certify mastery');
   await step(first.label).getByRole('button',{name:'重新进行',exact:true}).click();await waitNotice('步骤已保存');
   await page.getByRole('button',{name:`下移：${first.label}`,exact:true}).click();await waitNotice('顺序已保存');
   value=await saved();assert.equal(value.steps[1].node_id,first.node_id);assert.equal(value.steps[1].state,'todo');
   await page.reload();await page.getByRole('region',{name:'已保存的学习路线',exact:true}).waitFor();
   const reopened=await saved();assert.deepEqual(reopened.steps.map(item=>[item.node_id,item.state]),value.steps.map(item=>[item.node_id,item.state]));
   await openDetails(page.locator('.kw-route-history'));await contains(page.locator('.kw-route-history'),'修订 1');
   return {revision:reopened.revision,steps:reopened.steps.map(item=>({label:item.label,state:item.state})),self_assessment:'not_started'};
 });
 await check('route_graph_has_only_actual_edges_and_keyboard_navigation',async()=>{
   const value=await saved();await page.getByRole('button',{name:'在图谱中查看路线',exact:true}).click();
   const map=page.getByRole('region',{name:'已保存路线图谱',exact:true});await map.waitFor();
   assert.equal(await page.locator('.kw-graph-node').count(),3);assert.equal(await page.locator('.kw-graph-edge').count(),2);
   const nodes=await page.locator('.kw-graph-node').evaluateAll(elements=>elements.map(element=>element.getAttribute('data-node-id')));
   assert.ok(!nodes.includes(fixture.nodes.unrelated));assert.ok(nodes.every(id=>!fixture.teaching_node_ids.includes(id)));
   const first=page.getByRole('list',{name:'路线步骤顺序'}).getByRole('button').first();await first.focus();await page.keyboard.press('Enter');
   await page.locator('.kw-node-panel').waitFor();
   assert.equal(await page.locator('.kw-graph-node').count(),3,'Selection must not replace the saved route graph');
   await page.getByRole('button',{name:'返回自由探索图谱',exact:true}).click();
   await page.getByRole('region',{name:'已保存路线图谱',exact:true}).waitFor({state:'detached'});
   assert.ok(!new URL(page.url()).searchParams.has('route'));
   return {nodes:3,actual_edges:2,no_sequential_fake_edges:true,next_node_id:value.next_node_id,keyboard_enter_opens_node:true};
 });
 await check('workspace_guidance_continues_saved_route',async()=>{
   const value=await saved();await page.goto(workspace('view=graph'));
   const guidance=page.getByRole('complementary',{name:'当前问题的下一步'});await guidance.waitFor();
   const target=value.steps.find(item=>item.node_id===value.next_node_id);assert.ok(target);
   await contains(guidance,target.label);await contains(guidance,'路线');
   await shot('1366-light-continue-route',guidance);
   await guidance.getByRole('button',{name:/继续/}).first().click();await page.locator('.kw-learning-view').waitFor();
   assert.equal(new URL(page.url()).searchParams.get('node'),target.node_id);
   return {next_node_id:target.node_id,label:target.label};
 });
 await check('route_evidence_returns_to_same_route',async()=>{
   await routePage();const value=await saved();const target=step(value.steps[0].label);await openDetails(target.locator('.kw-route-step-context'));
   await target.locator('.kw-route-evidence button').first().click();await page.locator('.kw-source-reader').waitFor();
   const params=new URL(page.url()).searchParams;assert.equal(params.get('source'),fixture.source_id);assert.ok(params.get('block'));
   await page.getByRole('button',{name:'返回原位置',exact:true}).click();await page.getByRole('region',{name:'我的学习路线',exact:true}).waitFor();
   assert.equal(new URL(page.url()).searchParams.get('view'),'route');
   assert.equal((await saved()).revision,value.revision);
   return {source_id:fixture.source_id,block_id:params.get('block'),return_view:'route'};
 });
 await check('changed_node_shows_saved_and_current_evidence_then_explicit_recheck',async()=>{
   const value=await saved();const original=value.steps.find(item=>item.node_id===fixture.nodes.goal);
   const detail=await api(`knowledge/nodes/${fixture.nodes.goal}`);const node=detail.node||detail;
   await api(`knowledge/nodes/${fixture.nodes.goal}`,'PATCH',{expected_version:node.version,summary:node.summary+' 用户补充：本教学输入只检查softmax之前的缩放分数和之后的权重。'});
   await routePage();let changed=await saved();assert.ok(changed.steps.find(item=>item.node_id===fixture.nodes.goal).stale);
   assert.equal(changed.steps.find(item=>item.node_id===fixture.nodes.goal).snapshot.node.summary,original.snapshot.node.summary);
   const target=step(original.label);await openDetails(target.locator('.kw-route-step-context'));
   await contains(target,'保存时的内容');await contains(target,'当前内容');
   await contains(target,'用户补充');await shot('1366-light-route-review',target);
   await target.getByRole('button',{name:'确认采用当前依据',exact:true}).click();await waitNotice('当前依据已确认');
   changed=await saved();assert.equal(changed.steps.find(item=>item.node_id===fixture.nodes.goal).stale,false);
   assert.ok(changed.steps.find(item=>item.node_id===fixture.nodes.goal).snapshot.node.summary.includes('用户补充'));
   return {old_summary:original.snapshot.node.summary,current_summary:changed.steps.find(item=>item.node_id===fixture.nodes.goal).snapshot.node.summary,revision:changed.revision};
 });
 await check('removed_source_disables_route_and_restoration_keeps_decisions',async()=>{
   const before=await saved();await api(`sources/${fixture.source_id}`,'PATCH',{removed:true});await routePage();
   const removed=await saved();assert.ok(removed.steps.every(item=>item.stale));assert.equal(removed.next_node_id,null);assert.equal(removed.graph.nodes.length,0);
   assert.equal(await page.locator('.kw-route-steps').getByRole('button',{name:'打开这一步',exact:true}).filter({visible:true}).count(),3);
   for(const button of await page.locator('.kw-route-steps').getByRole('button',{name:'打开这一步',exact:true}).all())assert.ok(await button.isDisabled());
   await api(`sources/${fixture.source_id}`,'PATCH',{removed:false});await routePage();
   const restored=await saved();assert.deepEqual(restored.steps.map(item=>[item.node_id,item.state]),before.steps.map(item=>[item.node_id,item.state]));
   assert.ok(restored.graph.nodes.length);assert.ok(restored.next_node_id);
   return {removed_step_count:removed.steps.length,removed_next:null,restored_next:restored.next_node_id};
 });
 await check('three_desktop_sizes_light_dark_and_focus',async()=>{
   const measurements=[];
   for(const [width,height] of [[1366,768],[1440,900],[1920,1080]]){
     await page.setViewportSize({width,height});await routePage();
     for(const color of ['light','dark']){
       await theme(color);await shot(`${width}-${color}-learning-route`,page.locator('.kw-route-current'));
       let geometry=await page.evaluate(()=>({viewport:innerWidth,document:document.documentElement.scrollWidth}));assert.ok(geometry.document<=geometry.viewport+1,JSON.stringify(geometry));
       measurements.push({width,height,color,surface:'route',...geometry});
       await page.getByRole('button',{name:'在图谱中查看路线',exact:true}).click();await page.getByRole('region',{name:'已保存路线图谱',exact:true}).waitFor();
       await shot(`${width}-${color}-route-graph`,page.locator('.kw-saved-route-map'));
       geometry=await page.evaluate(()=>({viewport:innerWidth,document:document.documentElement.scrollWidth}));assert.ok(geometry.document<=geometry.viewport+1,JSON.stringify(geometry));
       measurements.push({width,height,color,surface:'graph',...geometry});
       await routePage();
     }
   }
   return measurements;
 });
 await check('no_live_model_or_javascript_http_errors',async()=>{assert.deepEqual(report.model_requests,[]);assert.deepEqual(report.page_errors,[]);assert.deepEqual(report.http_errors,[]);return {runtime_model_requests:0,javascript_errors:0,http_errors:0};});
 report.passed=true;
}catch(error){report.passed=false;report.error=String(error.stack||error);if(page){await page.screenshot({path:path.join(output,'failure.png'),fullPage:true}).catch(()=>{});fs.writeFileSync(path.join(output,'failure.html'),await page.content().catch(()=>''));}console.error(report.error);process.exitCode=1;
}finally{report.finished_at=new Date().toISOString();fs.writeFileSync(path.join(output,'report.json'),JSON.stringify(report,null,2));if(browser)await browser.close();console.log('Report:',path.join(output,'report.json'));}})();
