/* Real API acceptance. Prepare_project_network_fixture.py and start isolated
 * offline API/Vite first. Usage: node this-file [fixture directory] [base URL].
 * All mutations below are confined to the explicitly prepared fixture project.
 */
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('../../frontend/node_modules/playwright');
const directory=path.resolve(process.argv[2]||'.ui_validation/project-network-20261117');
const base=process.argv[3]||'http://127.0.0.1:15299';
const fixture=JSON.parse(fs.readFileSync(path.join(directory,'fixture.json'),'utf8').replace(/^\uFEFF/,''));
const output=path.join(directory,'browser');fs.mkdirSync(output,{recursive:true});
const materialsOnly=process.argv.includes('--materials-only');
const report={started_at:new Date().toISOString(),fixture:directory,source_kind:'authored_teaching_material',model_stub:true,real_provider_calls:0,checks:[],screenshots:[],page_errors:[],console_errors:[],http_errors:[],expected_errors:[],model_requests:[],blocked_external:[],graph_requests:[]};
let browser,page,uploaded,created;
const workspace=(project=fixture.project_id,node)=>`${base}/research/${project}?view=graph${node?'&node='+encodeURIComponent(node):''}`;
const panel=()=>page.getByRole('complementary',{name:'知识节点详情'});
const materials=()=>panel().getByRole('region',{name:'节点资料'});
async function check(name,action){if(materialsOnly&&['projects_have_independent_networks_and_remember_presentation','node_edit_persists_and_selection_uses_existing_editor','node_text_is_saved_and_reopened_without_changing_other_project','manual_node_creation_is_project_scoped_and_editable'].includes(name))return;const started=Date.now();try{const detail=await action();report.checks.push({name,passed:true,milliseconds:Date.now()-started,detail});console.log('PASS',name);}catch(error){report.checks.push({name,passed:false,error:String(error.stack||error)});throw error;}}
async function api(suffix,method='GET',data,project=fixture.project_id){const response=await page.request.fetch(`${base}/api/projects/${project}/${suffix}`,{method,data});assert.ok(response.ok(),`${response.status()} ${await response.text()}`);return response.json();}
async function chooseNode(id){const select=page.getByLabel('定位关系网络节点');await select.waitFor();await select.selectOption(id);await panel().locator('h2').waitFor();}
async function useNetwork(){const button=page.getByRole('button',{name:'关系网络',exact:true});await button.waitFor();if(await button.getAttribute('aria-pressed')!=='true')await button.click();await page.getByRole('region',{name:'课题关系网络',exact:true}).waitFor();}
async function sourcesTab(){await panel().getByRole('tab',{name:'原文与资料',exact:true}).click();await materials().waitFor();}
async function noteTab(){await panel().getByRole('tab').filter({hasText:/笔记|记录/}).last().click();await panel().getByRole('region',{name:'我的学习笔记'}).waitFor();}
async function shot(name,locator){if(await panel().count())await panel().locator('h2').waitFor();if(locator)await locator.evaluate(element=>{element.scrollIntoView({block:'start'});let parent=element.parentElement;while(parent&&parent!==document.documentElement){if(/auto|scroll/.test(getComputedStyle(parent).overflowY)&&parent.scrollHeight>parent.clientHeight){parent.scrollBy(0,-82);return;}parent=parent.parentElement;}window.scrollBy(0,-82);});const file=path.join(output,name+'.png');await page.screenshot({path:file,fullPage:false});report.screenshots.push(file);}
async function theme(value){await page.evaluate(value=>{localStorage.setItem('research-atlas-theme',value);window.dispatchEvent(new StorageEvent('storage',{key:'research-atlas-theme',newValue:value}));},value);await page.locator(`html[data-theme="${value}"]`).waitFor();}
async function materialItems(){return (await api(`knowledge/nodes/${fixture.nodes.goal}/materials`)).items;}
function materialRow(title){return materials().locator('.kw-node-material-list>li').filter({has:page.locator('strong').filter({hasText:title})});}
(async()=>{try{
 browser=await chromium.launch({headless:true,channel:'chrome'});
 const context=await browser.newContext({viewport:{width:1366,height:768},reducedMotion:'reduce',acceptDownloads:true});
 await context.route('**/*',route=>{const url=new URL(route.request().url());if(['127.0.0.1','localhost'].includes(url.hostname))return route.continue();report.blocked_external.push(url.href);return route.abort();});
 page=await context.newPage();page.setDefaultTimeout(30000);page.setDefaultNavigationTimeout(60000);
 page.on('pageerror',error=>report.page_errors.push(String(error)));
 page.on('console',message=>{if(message.type()==='error')report.console_errors.push(message.text());});
 page.on('response',response=>{if(!response.ok()&&response.url().includes('/api/'))report.http_errors.push({status:response.status(),url:response.url()});});
 page.on('request',request=>{const url=new URL(request.url());if(/\/api\/projects\/[^/]+\/knowledge\/graph$/.test(url.pathname))report.graph_requests.push(url.pathname+url.search);if(request.method()==='POST'&&/\/(generate|supplement|question|summary|analyze)$|\/learning$/.test(url.pathname))report.model_requests.push(url.href);});
 if(materialsOnly){await page.goto(workspace(fixture.project_id,fixture.nodes.goal));await useNetwork();await panel().locator('h2').waitFor();}
 await check('projects_have_independent_networks_and_remember_presentation',async()=>{
  await page.goto(workspace());await useNetwork();
  const full=page.getByRole('button',{name:'切换完整图谱',exact:true});if(await full.count())await full.click();
  const select=page.getByLabel('定位关系网络节点');await select.locator(`option[value="${fixture.nodes.goal}"]`).waitFor({state:'attached'});
  let ids=await select.locator('option').evaluateAll(options=>options.map(item=>item.value).filter(Boolean));
  assert.ok(ids.includes(fixture.nodes.goal));assert.ok(!ids.includes(fixture.other_node.id));
  await page.goto(workspace(fixture.other_project_id));await useNetwork();
  const otherSelect=page.getByLabel('定位关系网络节点');await otherSelect.locator(`option[value="${fixture.other_node.id}"]`).waitFor({state:'attached'});
  const otherIds=await otherSelect.locator('option').evaluateAll(options=>options.map(item=>item.value).filter(Boolean));
  assert.ok(!otherIds.includes(fixture.nodes.goal));
  await page.goto(workspace());await page.getByRole('region',{name:'课题关系网络',exact:true}).waitFor();
  await chooseNode(fixture.nodes.goal);await shot('1366-light-project-network',page.getByRole('region',{name:'课题关系网络',exact:true}));
  return {project_a_ids:ids,project_b_ids:otherIds,shared_node_count:ids.filter(id=>otherIds.includes(id)).length,preference_restored:true};
 });
 await check('node_edit_persists_and_selection_uses_existing_editor',async()=>{
  const before=(await api(`knowledge/nodes/${fixture.nodes.goal}`)).node;
  await panel().getByRole('button',{name:/^(编辑节点|修订内容)$/}).click();
  const summary=before.summary+'\n浏览器验收修订：区分当前资料与个人理解。';
  await panel().getByLabel('节点解释').fill(summary);await panel().getByRole('button',{name:'保存修订',exact:true}).click();
  await panel().getByRole('button',{name:/^(编辑节点|修订内容)$/}).waitFor();
  const saved=(await api(`knowledge/nodes/${fixture.nodes.goal}`)).node;assert.equal(saved.summary,summary);assert.ok(saved.version>before.version);
  await page.reload();await page.getByRole('region',{name:'课题关系网络',exact:true}).waitFor();await panel().waitFor();
  assert.equal((await api(`knowledge/nodes/${fixture.nodes.goal}`)).node.summary,summary);
  return {node_id:saved.id,version:saved.version,summary:saved.summary};
 });
 await check('node_text_is_saved_and_reopened_without_changing_other_project',async()=>{
  await noteTab();const text='这条笔记只属于课题A的当前节点。我的判断：缩放分数与权重处于不同步骤。';
  await panel().getByLabel('我的理解',{exact:true}).fill(text);await panel().getByRole('button',{name:'保存笔记',exact:true}).click();
  await panel().locator('.kw-node-note-actions [role="status"]').filter({hasText:'已保存'}).waitFor();
  await page.reload();await panel().waitFor();await panel().getByRole('region',{name:'已保存节点笔记'}).filter({hasText:text}).waitFor();await noteTab();assert.equal(await panel().getByLabel('我的理解',{exact:true}).inputValue(),text);
  await page.goto(workspace(fixture.other_project_id,fixture.other_node.id));await useNetwork();await panel().waitFor();await noteTab();
  assert.equal(await panel().getByLabel('我的理解',{exact:true}).inputValue(),'');
  await page.goto(workspace(fixture.project_id,fixture.nodes.goal));await useNetwork();await panel().waitFor();
  return {text,persisted:true,other_project_note_empty:true};
 });
 await check('manual_node_creation_is_project_scoped_and_editable',async()=>{
  await page.getByRole('button',{name:'新增节点',exact:true}).click();
  await page.getByLabel('新节点名称').fill(fixture.manual_node_label);
  await page.getByLabel('新节点说明').fill(fixture.manual_node_summary);
  await page.getByRole('button',{name:'保存节点',exact:true}).click();
  await panel().getByRole('heading',{name:fixture.manual_node_label,exact:true}).waitFor();
  created=new URL(page.url()).searchParams.get('node');assert.ok(created);
  const node=(await api(`knowledge/nodes/${created}`)).node;assert.equal(node.origin,'user');assert.equal(node.summary,fixture.manual_node_summary);
  const other=await api('knowledge/graph?limit=2000','GET',undefined,fixture.other_project_id);assert.ok(!other.nodes.some(item=>item.id===created));
  await page.reload();await panel().getByRole('heading',{name:fixture.manual_node_label,exact:true}).waitFor();
  await page.goto(workspace(fixture.project_id,fixture.nodes.goal));await useNetwork();await panel().waitFor();
  return {node_id:created,origin:node.origin,project_id:node.project_id};
 });
 await check('existing_project_material_is_bound_and_explained_on_the_node',async()=>{
  await sourcesTab();await materials().getByRole('button',{name:'添加资料',exact:true}).click();
  await materials().getByLabel('节点资料说明').fill('这份课题资料提供当前知识的教学背景。');
  await materials().getByRole('combobox',{name:'关联已有课题资料'}).selectOption(fixture.source_id);
  await materials().getByRole('button',{name:'关联所选资料',exact:true}).click();
  await materials().getByRole('status').filter({hasText:'资料已关联到当前节点'}).waitFor();
  const item=(await materialItems()).find(item=>item.source_id===fixture.source_id);assert.ok(item);assert.equal(item.note,'这份课题资料提供当前知识的教学背景。');
  await page.reload();await panel().waitFor();await sourcesTab();await materialRow(item.source_snapshot.title).waitFor();
  return {id:item.id,source_id:item.source_id,revision:item.revision,note:item.note};
 });
 await check('uploaded_material_is_readable_bound_and_does_not_generate_nodes',async()=>{
  const before=await api('knowledge/graph?limit=2000');
  await materials().getByRole('button',{name:'添加资料',exact:true}).click();await materials().getByLabel('节点资料说明').fill('我补充的本地研究记录，后续从这个节点查看。');
  await materials().getByLabel('上传节点资料').setInputFiles(path.join(directory,fixture.attachment_filename));
  await materials().getByRole('button',{name:'导入并关联',exact:true}).click();
  await materials().getByRole('status').filter({hasText:'资料已导入并保存到当前节点'}).waitFor();
  uploaded=(await materialItems()).find(item=>item.source_snapshot.filename===fixture.attachment_filename);assert.ok(uploaded);
  const after=await api('knowledge/graph?limit=2000');assert.deepEqual(new Set(after.nodes.map(item=>item.id)),new Set(before.nodes.map(item=>item.id)));
  const source=await api(`sources/${uploaded.source_id}`);assert.ok(source.blocks.some(block=>block.text.includes('这份附件说明')));
  const row=materialRow(uploaded.source_snapshot.title);await row.getByRole('button',{name:'查看资料',exact:true}).click();
  await page.locator('.kw-source-reader').waitFor();assert.equal(new URL(page.url()).searchParams.get('source'),uploaded.source_id);
  await page.getByRole('heading',{name:fixture.attachment_title,exact:true}).first().waitFor();
  await page.getByRole('button',{name:'返回原位置',exact:true}).click();await panel().waitFor();await sourcesTab();
  await materialRow(uploaded.source_snapshot.title).waitFor();await shot('1366-light-node-materials',materials());
  return {source_id:uploaded.source_id,filename:uploaded.source_snapshot.filename,revision:uploaded.revision,automatic_semantic_nodes_added:0};
 });
 await check('material_changes_and_cross_project_rejection_preserve_personal_records',async()=>{
  const response=await page.request.post(`${base}/api/projects/${fixture.project_id}/knowledge/nodes/${fixture.nodes.goal}/materials`,{data:{source_id:fixture.other_node.source_id,note:'应被拒绝'}});
  assert.ok([403,404,409,422].includes(response.status()));report.expected_errors.push({kind:'cross_project_binding',status:response.status()});
  await api(`sources/${uploaded.source_id}`,'PATCH',{removed:true});
  await page.reload();await panel().waitFor();await sourcesTab();
  const row=materialRow(uploaded.source_snapshot.title);await row.getByText('资料已移除，保存时的说明仍保留。').waitFor();assert.ok(await row.getByRole('button',{name:'查看资料',exact:true}).isDisabled());
  const item=(await materialItems()).find(item=>item.id===uploaded.id);assert.ok(item.source_missing);assert.equal(item.note,uploaded.note);
  await api(`sources/${uploaded.source_id}`,'PATCH',{removed:false});
  await page.reload();await panel().waitFor();await sourcesTab();
  return {cross_project_status:response.status(),retained_material_id:item.id,retained_note:item.note};
 });
 await check('desktop_themes_keyboard_and_canvas_stay_usable',async()=>{
  const checks=[];
  for(const [width,height] of [[1366,768],[1920,1080],[1152,720]])for(const color of ['light','dark']){
   await page.setViewportSize({width,height});await theme(color);await page.goto(workspace(fixture.project_id,fixture.nodes.goal));await useNetwork();await panel().waitFor();
   const select=page.getByLabel('定位关系网络节点');await select.focus();await page.keyboard.press('Home');await page.keyboard.press('ArrowDown');
   await panel().waitFor();const overflow=await page.evaluate(()=>({viewport:innerWidth,document:document.documentElement.scrollWidth}));assert.ok(overflow.document<=overflow.viewport+1);
   await shot(`${width}-${color}-project-network`,page.getByRole('region',{name:'课题关系网络',exact:true}));
   checks.push({width,color,...overflow});
  }
  return checks;
 });
 await check('no_unexpected_errors_or_runtime_model_requests',async()=>{
  assert.deepEqual(report.page_errors,[]);assert.deepEqual(report.console_errors,[]);assert.deepEqual(report.http_errors,[]);assert.deepEqual(report.model_requests,[]);assert.deepEqual(report.blocked_external,[]);
  return {javascript_errors:0,console_errors:0,http_errors:0,model_requests:0,expected_rejections:report.expected_errors};
 });
 report.passed=true;
}catch(error){report.passed=false;report.error=String(error.stack||error);console.error(error);if(page)await shot('failure');process.exitCode=1;}
finally{report.finished_at=new Date().toISOString();fs.writeFileSync(path.join(output,materialsOnly?'report-materials.json':'report.json'),JSON.stringify(report,null,2));if(browser)await browser.close();}})();
