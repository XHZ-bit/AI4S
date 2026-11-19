/* Desktop layout acceptance against a real isolated API/Vite pair.
 * Usage: node this-file [fresh layout fixture directory] [isolated base URL].
 * No normal browser profile, normal database, API mocks or external models.
 */
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('../../frontend/node_modules/playwright');
const directory=path.resolve(process.argv[2]||'.ui_validation/workspace-layout-20261117');
const base=process.argv[3]||'http://127.0.0.1:15309';
assert.ok(directory.includes(path.sep+'.ui_validation'+path.sep),'Use an isolated validation directory');
assert.ok(['127.0.0.1','localhost'].includes(new URL(base).hostname));
assert.ok(!['5173','8000'].includes(new URL(base).port),'Never run this script on normal user services');
const fixture=JSON.parse(fs.readFileSync(path.join(directory,'fixture.json'),'utf8').replace(/^\uFEFF/,''));
const screenshotsOnly=process.argv.includes('--screenshots-only');
const output=path.join(directory,'layout-browser');fs.mkdirSync(output,{recursive:true});
const report={started_at:new Date().toISOString(),fixture:directory,base,source_kind:'authored_teaching_material',model_stub:true,real_provider_calls:0,checks:[],viewport_checks:[],screenshots:[],page_errors:[],console_errors:[],http_errors:[],expected_errors:[],model_requests:[],blocked_external:[],limits:['125% and 150% are equivalent CSS layout viewports, not physical Chrome zoom controls.','No mobile or physical touch-device coverage.']};
let browser,context,page,localPreferred;
const workspace=(project=fixture.project_id,node=fixture.nodes.goal)=>`${base}/research/${project}?view=graph&node=${encodeURIComponent(node)}`;
const panel=()=>page.getByRole('complementary',{name:'知识节点详情'});
const separator=()=>page.getByRole('separator',{name:'调整节点详情宽度',exact:true});
const widthKey=(project=fixture.project_id,account='local')=>`paperstride:${account}:graph-detail-width:${project}`;
const near=(actual,expected,message)=>assert.ok(Math.abs(actual-expected)<=2,`${message}: ${actual} versus ${expected}`);
async function check(name,action){if(screenshotsOnly&&name!=='desktop_themes_and_equivalent_zoom_viewports')return;const started=Date.now();try{const detail=await action();report.checks.push({name,passed:true,milliseconds:Date.now()-started,detail});console.log('PASS',name);}catch(error){report.checks.push({name,passed:false,error:String(error.stack||error)});throw error;}}
async function settled(){await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));}
async function nodeReady(){await panel().locator('h2').waitFor();await separator().waitFor();await settled();}
async function useNetwork(){const button=page.getByRole('button',{name:'关系网络',exact:true});await button.waitFor();if(await button.getAttribute('aria-pressed')!=='true')await button.click();await page.getByRole('region',{name:'课题关系网络',exact:true}).waitFor();}
async function open(project=fixture.project_id,node=fixture.nodes.goal){await page.goto(workspace(project,node));await useNetwork();await nodeReady();}
async function width(){return (await panel().boundingBox()).width;}
async function values(){return separator().evaluate(element=>({now:Number(element.getAttribute('aria-valuenow')),min:Number(element.getAttribute('aria-valuemin')),max:Number(element.getAttribute('aria-valuemax')),orientation:element.getAttribute('aria-orientation'),tabIndex:element.tabIndex}));}
async function stored(key){return page.evaluate(key=>JSON.parse(localStorage.getItem(key)||'null'),key);}
async function waitStored(key,target){await page.waitForFunction(({key,target})=>Math.abs(JSON.parse(localStorage.getItem(key)||'null')-target)<=2,{key,target});}
async function dragWidth(target){const before=await width(),box=await separator().boundingBox();await page.mouse.move(box.x+box.width/2,box.y+Math.min(box.height/2,160));await page.mouse.down();await page.mouse.move(box.x+box.width/2+before-target,box.y+Math.min(box.height/2,160),{steps:14});await page.mouse.up();await page.waitForFunction(target=>{const panel=document.querySelector('[aria-label="知识节点详情"]');return panel&&Math.abs(panel.getBoundingClientRect().width-target)<=2;},target);return width();}
async function theme(value){await page.evaluate(value=>{localStorage.setItem('research-atlas-theme',value);window.dispatchEvent(new StorageEvent('storage',{key:'research-atlas-theme',newValue:value}));},value);await page.locator(`html[data-theme="${value}"]`).waitFor();}
async function metrics(){await settled();return page.evaluate(()=>{const box=selector=>{const r=document.querySelector(selector).getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height,right:r.right,bottom:r.bottom};};return {viewport:{width:innerWidth,height:innerHeight},outer_width:document.documentElement.scrollWidth,layout:box('.kw-resizable-graph'),primary:box('.kw-graph-primary'),panel:box('[aria-label="知识节点详情"]'),body_scroll:document.scrollingElement.scrollTop};});}
function fitsViewport(d){for(const part of ['layout','primary','panel'])assert.ok(d[part].bottom<=d.viewport.height+2,`${part} bottom ${d[part].bottom} exceeds viewport ${d.viewport.height} at width ${d.viewport.width}`);assert.ok(d.outer_width<=d.viewport.width+1,`${d.viewport.width} outer horizontal overflow: ${d.outer_width}`);}
async function shot(name){const file=path.join(output,name+'.png');await page.screenshot({path:file,fullPage:false});report.screenshots.push(file);}
async function api(path,method='GET',data,headers){const response=await page.request.fetch(base+path,{method,data,headers});assert.ok(response.ok(),`${response.status()} ${await response.text()}`);return response.json();}
(async()=>{try{
 browser=await chromium.launch({headless:true,channel:'chrome'});
 context=await browser.newContext({viewport:{width:1366,height:768},reducedMotion:'reduce'});
 await context.route('**/*',route=>{const url=new URL(route.request().url());if(['127.0.0.1','localhost'].includes(url.hostname))return route.continue();report.blocked_external.push(url.href);return route.abort();});
 page=await context.newPage();page.setDefaultTimeout(30000);page.setDefaultNavigationTimeout(60000);
 page.on('pageerror',error=>report.page_errors.push(String(error)));page.on('console',message=>{if(message.type()==='error')report.console_errors.push(message.text());});
 page.on('response',response=>{if(!response.ok()&&response.url().includes('/api/'))report.http_errors.push({status:response.status(),url:response.url()});});
 page.on('request',request=>{if(request.method()==='POST'&&/\/(generate|supplement|question|summary|analyze)$|\/learning$/.test(new URL(request.url()).pathname))report.model_requests.push(request.url());});
 if(screenshotsOnly){await page.goto(base);await page.evaluate(key=>localStorage.setItem(key,'560'),widthKey());localPreferred=560;report.capture_mode='Fixed selected node; interaction and account checks remain in the complete report.';}
 await check('compact_top_and_wider_default_details',async()=>{
  await open();const dimensions=await metrics(),state=await values();
  assert.ok(dimensions.layout.y<=260,`Canvas starts too low: ${dimensions.layout.y}`);
  assert.ok(dimensions.layout.height>=400,`Canvas usable height too small: ${dimensions.layout.height}`);
  fitsViewport(dimensions);
  assert.ok(dimensions.panel.width>=418,'Default details should be at least 420px wide');
  assert.ok(dimensions.outer_width<=dimensions.viewport.width+1);assert.equal(state.orientation,'vertical');assert.equal(state.tabIndex,0);
  await shot('1366-light-default');return {...dimensions,separator:state};
 });
 await check('pointer_drag_persists_and_double_click_resets',async()=>{
  const initial=await width(),state=await values(),target=Math.min(initial+110,state.max-10);assert.ok(target>initial+40);
  const dragged=await dragWidth(target);await waitStored(widthKey(),dragged);await page.reload();await nodeReady();near(await width(),dragged,'Refresh preserves width');
  await separator().dblclick();await page.waitForFunction(expected=>Math.abs(document.querySelector('[aria-label="知识节点详情"]').getBoundingClientRect().width-expected)<=2,initial);
  near(await width(),initial,'Double-click restores default');return {initial,dragged,after_refresh:dragged,after_reset:await width()};
 });
 await check('keyboard_resize_limits_accelerated_step_and_reset',async()=>{
  await separator().focus();const initial=await width();await page.keyboard.press('ArrowLeft');const regular=(await width())-initial;assert.ok(regular>0,'Left should widen details');
  await page.keyboard.press('Shift+ArrowLeft');const fast=(await width())-initial-regular;assert.ok(fast>regular,'Shift should accelerate resizing');
  await page.keyboard.press('ArrowRight');assert.ok(await width()<initial+regular+fast);
  await page.keyboard.press('Home');let state=await values();near(await width(),state.min,'Home reaches minimum');const minDimensions=await metrics();fitsViewport(minDimensions);await shot('1366-light-minimum-details');
  await page.keyboard.press('End');state=await values();near(await width(),state.max,'End reaches maximum');const maxDimensions=await metrics();fitsViewport(maxDimensions);await shot('1366-light-maximum-details');
  await page.getByRole('button',{name:'恢复默认宽度',exact:true}).click();near(await width(),initial,'Reset button restores default');
  return {regular_step:regular,accelerated_step:fast,min:state.min,max:state.max,reset:await width(),min_dimensions:minDimensions,max_dimensions:maxDimensions};
 });
 await check('expanded_details_keep_node_tab_and_unsaved_note',async()=>{
  await panel().getByRole('tab').filter({hasText:/笔记|记录/}).last().click();const draft='未保存的阅读草稿：面板展开前后保持当前内容。';await panel().getByLabel('我的理解',{exact:true}).fill(draft);
  const previous=await width();await panel().getByRole('button',{name:/展开节点详情/}).click();
  const expanded=await width();assert.ok(expanded>previous+100);assert.equal(await panel().getByLabel('我的理解',{exact:true}).inputValue(),draft);assert.equal(new URL(page.url()).searchParams.get('node'),fixture.nodes.goal);
  assert.equal(await separator().isVisible(),false);await shot('1366-light-expanded-note');
  await panel().getByRole('button',{name:/还原分栏/}).click();await separator().waitFor();near(await width(),previous,'Restore uses previous split width');assert.equal(await panel().getByLabel('我的理解',{exact:true}).inputValue(),draft);
  return {node:fixture.nodes.goal,split_width:previous,expanded_width:expanded,unsaved_draft_preserved:true};
 });
 await check('project_widths_are_independent',async()=>{
  localPreferred=Math.min(560,(await values()).max-10);await dragWidth(localPreferred);await waitStored(widthKey(),localPreferred);
  await open(fixture.other_project_id,fixture.other_node.id);const projectDefault=await width();assert.ok(Math.abs(projectDefault-localPreferred)>20,'Other project inherited A width');
  const projectB=Math.min(projectDefault+55,(await values()).max-10);await dragWidth(projectB);await waitStored(widthKey(fixture.other_project_id),projectB);
  await open();near(await width(),localPreferred,'A width is restored');return {project_a:localPreferred,project_b:projectB,project_b_initial:projectDefault};
 });
 await check('reading_return_restores_selected_node_and_width',async()=>{
  await panel().getByRole('tab',{name:'原文与资料',exact:true}).click();await panel().getByRole('button',{name:'阅读原文',exact:true}).click();await page.locator('.kw-source-reader').waitFor();
  assert.equal(new URL(page.url()).searchParams.get('view'),'reading');await page.getByRole('button',{name:'返回原位置',exact:true}).click();await nodeReady();
  near(await width(),localPreferred,'Reading return preserves width');assert.equal(new URL(page.url()).searchParams.get('node'),fixture.nodes.goal);
  return {node:fixture.nodes.goal,width:await width(),source:fixture.source_id};
 });
 await check('desktop_themes_and_equivalent_zoom_viewports',async()=>{
  const results=[];
  for(const [w,h,zoom] of [[1366,768,100],[1440,900,100],[1920,1080,100],[1093,614,125],[1280,720,150]])for(const color of ['light','dark']){
   if(screenshotsOnly&&!((w===1366&&color==='light')||(w===1920&&color==='dark')||(w===1093&&color==='dark')))continue;
   await page.setViewportSize({width:w,height:h});await theme(color);await open();const d=await metrics(),state=await values();
   report.viewport_checks.push({width:w,height:h,equivalent_zoom_percent:zoom,color,...d,separator:state});fitsViewport(d);assert.ok(d.layout.y<=260,`${w} ${color} top=${d.layout.y}`);assert.ok(d.layout.height>=h*.45);assert.ok(d.panel.width>=state.min-1&&d.panel.width<=state.max+1);
   if(!screenshotsOnly){const select=page.getByLabel('定位关系网络节点');await select.focus();await page.keyboard.press('Home');await page.keyboard.press('ArrowDown');await page.keyboard.press('Tab');await settled();}
   const selected=await api(`/api/projects/${fixture.project_id}/knowledge/nodes/${fixture.nodes.goal}`);
   if(screenshotsOnly)await panel().getByRole('heading',{name:selected.node.label,exact:true}).waitFor();
   else await page.waitForFunction(()=>{const select=document.querySelector('[aria-label="定位关系网络节点"]'),heading=document.querySelector('[aria-label="知识节点详情"] h2');return select&&heading&&select.selectedOptions[0]?.textContent.split(' · ')[0]===heading.textContent;});
   await page.waitForLoadState('networkidle');
   await settled();await shot(`${w}-${color}-zoom${zoom}`);
   results.push({width:w,height:h,equivalent_zoom_percent:zoom,color,...d,separator:state});
  }
  await page.setViewportSize({width:1366,height:768});await theme('light');await open();near(await stored(widthKey()),localPreferred,'Resize does not overwrite preference');near(await width(),localPreferred,'Larger viewport restores preference');return results;
 });
 await check('real_account_sessions_do_not_inherit_other_widths',async()=>{
  const results=[];
  for(const identity of fixture.layout_accounts){
   const session=await api('/api/auth/login','POST',{username:identity.username,password:identity.password});assert.equal(session.user.id,identity.id);
   await open(identity.project_id,identity.node_id);const initial=await width(),key=widthKey(identity.project_id,identity.id);
   assert.ok(await stored(key)===null||Math.abs(await stored(key)-initial)<2);const target=Math.min(initial+80,(await values()).max-10);await dragWidth(target);await waitStored(key,target);await page.reload();await nodeReady();near(await width(),target,'Same account refresh preserves width');
   const keys=await page.evaluate(()=>Object.keys(localStorage).filter(key=>key.includes(':graph-detail-width:')));assert.ok(keys.includes(key));assert.ok(!keys.some(key=>key.startsWith('paperstride:local:')));assert.ok(!keys.some(key=>fixture.layout_accounts.some(other=>other.id!==identity.id&&key.startsWith('paperstride:'+other.id+':'))));
   results.push({account_id:identity.id,project_id:identity.project_id,initial,width:target,key,other_account_width_keys:0});
  }
  return {accounts:results,session_cleanup:'Existing SessionGate clears workspace caches on account change; no change to that policy.'};
 });
 await check('no_unexpected_runtime_requests_or_browser_errors',async()=>{
  for(const key of ['page_errors','console_errors','http_errors','model_requests','blocked_external'])assert.deepEqual(report[key],[],key);
  return {javascript_errors:0,console_errors:0,http_errors:0,external_requests:0,runtime_model_requests:0};
 });report.passed=true;
}catch(error){report.passed=false;report.error=String(error.stack||error);console.error(error);if(page)await shot('failure').catch(()=>{});process.exitCode=1;}
finally{report.finished_at=new Date().toISOString();fs.writeFileSync(path.join(output,screenshotsOnly?'report-screenshots.json':'report.json'),JSON.stringify(report,null,2));if(browser)await browser.close();}})();
