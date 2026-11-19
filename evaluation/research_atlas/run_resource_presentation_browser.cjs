/* Resource presentation acceptance against the real local frontend.
 * Usage: node evaluation/research_atlas/run_resource_presentation_browser.cjs [base URL]
 * All API responses and player/image content are authored fixtures intercepted
 * in a fresh browser context. No user account, database, model or external site
 * is accessed. This checks UI behavior, not resource quality or availability.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require('../../frontend/node_modules/playwright');
const base = process.argv[2] || 'http://127.0.0.1:5173';
const directory = path.resolve('.ui_validation/resource-presentation-20261117');
fs.mkdirSync(directory, {recursive:true});
const pid = 'resource-presentation-fixture', nid = 'self-attention';
const node = {id:nid,project_id:pid,source_id:'teaching-source',kind:'concept',label:'Self-attention',summary:'自编教学摘录：同一序列中的位置可以参考其他位置的表示。',parent_id:null,origin:'source',research_status:'reading',version:1,hidden:false,source_missing:false,evidence_ids:['e'],metadata:{semantic:true}};
const project = {id:pid,version:1,title:'学习资料展示验收（自编资料）',domain:'custom',research_question:'Self-attention如何关联序列中的信息？',status:'active',constraints:{version:1,objective:'检查学习资料的展示与操作'},created_at:'2026-11-17',updated_at:'2026-11-17'};
const source = {id:'teaching-source',project_id:pid,asset_id:'a',version:'authored-v1',title:'自编注意力教学材料',filename:'attention.md',kind:'paper',media_type:'text/markdown',removed:false,created_at:'2026-11-17'};
const evidence = {id:'e',source_id:source.id,source_title:source.title,source_version:source.version,block_id:'b',quote:node.summary,origin:'source',locator:{heading:'概念定义',ordinal:0}};
const search = [
 {id:'search-b',type:'search',origin:'search',title:'在哔哩哔哩搜索相关讲解',url:'https://search.bilibili.com/all?keyword=Self-attention',reason:'站外搜索入口；不是已经核验的具体资源',access_status:'not_checked'},
 {id:'search-y',type:'search',origin:'search',title:'在 YouTube 搜索相关讲解',url:'https://www.youtube.com/results?search_query=Self-attention',reason:'站外搜索入口；不是已经核验的具体资源',access_status:'not_checked'},
 {id:'search-s',type:'search',origin:'search',title:'搜索相关论文',url:'https://scholar.google.com/scholar?q=Self-attention',reason:'站外搜索入口；不是已经核验的具体资源',access_status:'not_checked'},
];
const actual = [
 {id:'tutorial',title:'自编示例：序列信息如何汇聚',type:'tutorial',url:'https://example.org/attention',origin:'user',reason:'用三个位置的例子解释信息汇聚过程。',access_status:'not_checked',fetched:false},
 {id:'video',title:'教学视频入口示例',type:'video',url:'https://www.youtube.com/watch?v=aircAruvnKk',origin:'catalog',reason:'用动态图理解向量之间的信息传递。',access_status:'source_verified',checked_at:'2026-11-17',fetched:false},
 {id:'code',title:'教学代码入口示例',type:'code',url:'https://example.org/attention.py',origin:'user',reason:'逐步查看缩放和归一化。',access_status:'unavailable',fetched:false},
 {id:'bad',title:'待更新的代码地址',type:'code',url:'javascript:alert(1)',origin:'saved',fetched:false},
];
const report = {started_at:new Date().toISOString(),fixture:'authored mocked API responses with actual local React app',model_stub:true,real_provider_calls:0,checks:[],screenshots:[],page_errors:[],console_errors:[],expected_console_errors:[],http_errors:[],expected_http_errors:[],blocked_external:[],stubbed_embeds:[],api_mutations:[],model_requests:[]};
let browser, context, page, resources = [...search], failResourceRead = false;
const endpoint = `/api/projects/${pid}/knowledge/nodes/${nid}/resources`;
const rootURL = `${base}/research/${pid}?view=learning&node=${nid}&section=resources`;
async function check(name, action) {
 try {const detail = await action(); report.checks.push({name,passed:true,detail}); console.log('PASS',name);}
 catch(error) {report.checks.push({name,passed:false,error:String(error.stack || error)});throw error;}
}
async function resourcePanel() {await page.locator('#kw-learning-resources[open]').waitFor();return page.locator('#kw-learning-resources');}
async function reload(items) {resources = items; await page.goto(rootURL);await resourcePanel();await page.locator('#kw-learning-resources [role="status"]').filter({hasText:'读取学习资料'}).waitFor({state:'hidden'});}
async function shot(name) {
 await page.locator('#kw-learning-resources').evaluate(element=>{
  element.scrollIntoView({block:'start'});
  let parent = element.parentElement;
  while(parent && parent !== document.documentElement){
   if(/auto|scroll/.test(getComputedStyle(parent).overflowY) && parent.scrollHeight>parent.clientHeight){parent.scrollBy(0,-88);return;}
   parent = parent.parentElement;
  }
  window.scrollBy(0,-88);
 });
 const file = path.join(directory,name+'.png');await page.screenshot({path:file});report.screenshots.push(file);
}
async function theme(value){await page.evaluate(value=>{localStorage.setItem('research-atlas-theme',value);window.dispatchEvent(new StorageEvent('storage',{key:'research-atlas-theme',newValue:value}));},value);await page.locator(`html[data-theme="${value}"]`).waitFor();}
async function noOverflow(){return page.evaluate(()=>({viewport:innerWidth,document:document.documentElement.scrollWidth,resource:document.querySelector('#kw-learning-resources').scrollWidth,resourceWidth:Math.round(document.querySelector('#kw-learning-resources').getBoundingClientRect().width)}));}
(async()=>{
 try {
  browser = await chromium.launch({headless:true,channel:process.env.ATLAS_BROWSER_CHANNEL || 'chrome'});
  context = await browser.newContext({viewport:{width:1366,height:768},reducedMotion:'reduce'});
  await context.route('**/*',async route=>{
   const request=route.request(),url=new URL(request.url());
   if(url.hostname==='www.youtube-nocookie.com'){
    report.stubbed_embeds.push(url.href);
    return route.fulfill({status:200,contentType:'text/html',body:'<!doctype html><title>Authored player fixture</title><p>播放器占位仅用于验证按需加载。</p>'});
   }
   if(!['localhost','127.0.0.1'].includes(url.hostname)){report.blocked_external.push(url.href);return route.abort();}
   if(!url.pathname.startsWith('/api/'))return route.continue();
   const method=request.method();
   if(method!=='GET')report.api_mutations.push({method,path:url.pathname,body:request.postDataJSON()});
   if(method==='POST'&&/\/(generate|supplement|question|summary|analyze|learning)$/.test(url.pathname))report.model_requests.push(url.pathname);
   let body={items:[]},status=200;
   if(url.pathname==='/api/auth/session')body={mode:'local',user:null,require_login:false};
   else if(url.pathname==='/api/preferences')body={profile:{display_name:'',bio:'',institution:'',interests:'',level:'beginner',weekly_hours:5},features:{foundations:true,glossary:true,quizzes:true,coding:true,visuals:true,paper_guidance:true,roadmap:true,graph:true},provider:{enabled:false,base_url:'',model:''},version:1};
   else if(url.pathname==='/api/projects')body={items:[project],total:1};
   else if(url.pathname===`/api/projects/${pid}`)body=project;
   else if(url.pathname===`/api/workbench/projects/${pid}`)body={project,papers:[],records:[],sessions:[],features:{}};
   else if(url.pathname===`/api/projects/${pid}/sources`)body={items:[source],preferences:{mode:'explore',view:'graph'},model:{enabled:false,configured:false}};
   else if(url.pathname===`/api/projects/${pid}/knowledge/learning-route`)body={route:null};
   else if(url.pathname===`/api/projects/${pid}/knowledge/nodes/${nid}`)body={node,neighbors:[],prerequisites:[],edges:[],evidence:[evidence],resources:[],demos:[]};
   else if(url.pathname===`/api/projects/${pid}/knowledge/nodes/${nid}/learning`)body={id:'lesson',node_id:nid,node_version:1,status:'basic',stale:false,cached:true,sections:{overview:node.summary,definition:node.summary,derivation:'',prerequisites:'',implementation:'',limitations:''},evidence:[evidence],resources:[],demos:[],usage:{},errors:[]};
   else if(url.pathname===endpoint){
    if(method==='POST'){
     const value=request.postDataJSON(); const saved={...value,id:'added',origin:'user',fetched:false,access_status:'not_checked'};
     resources=[...resources.filter(item=>item.url!==saved.url),saved];body=saved;
    }else if(failResourceRead){status=503;body={detail:'Authored temporary resource service failure'};report.expected_http_errors.push({status,path:url.pathname});}
    else body={items:resources};
   }else if(url.pathname.endsWith('/progress'))body=url.pathname.includes('/nodes/')?{node_id:nid,status:'not_started',version:1}:{items:[]};
   else if(url.pathname.endsWith('/paths'))body={nodes:[],edges:[],paths:[],message:'没有已保存的前置路径',cycle_detected:false,truncated:false};
   else if(url.pathname.endsWith('/implementations'))body={items:[],code_sources:[],paper_evidence:[evidence]};
   else if(url.pathname.endsWith('/concept-correspondences'))body={candidates:[],items:[],left:{node,evidence:[evidence],conditions:{}}};
   return route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});
  });
  page=await context.newPage();page.setDefaultTimeout(20000);page.setDefaultNavigationTimeout(60000);
  page.on('pageerror',error=>report.page_errors.push(String(error)));
  page.on('console',message=>{
   if(message.type()!=='error')return;
   if(/503/.test(message.text()))report.expected_console_errors.push(message.text());
   else report.console_errors.push(message.text());
  });
  page.on('response',response=>{if(!response.ok()&&response.url().includes('/api/')&&!(response.status()===503&&response.url().endsWith('/resources')))report.http_errors.push({status:response.status(),url:response.url()});});
  await check('search_entries_are_compact_shortcuts_and_not_resource_count',async()=>{
   await reload([{...search[0],type:'tutorial',origin:'inference'},...search.slice(1)]);const panel=await resourcePanel();
   assert.equal(await panel.locator(':scope > summary').innerText(),'学习资料');
   assert.equal(await panel.locator('.kw-resource-list').count(),0);
   const nav=panel.getByRole('navigation',{name:'站外搜索'});assert.equal(await nav.locator('a').count(),3);
   assert(await panel.getByText('还没有保存学习资料，可添加课程、代码或视频链接。').isVisible());
   assert.equal(await panel.locator('text=并非已经找到的特定资源').count(),0);
   assert.equal(await panel.locator('text=尚未检测访问').count(),0);
   assert.equal(await panel.locator('text=不是已经核验的具体资源').count(),0);
   for(const link of await nav.locator('a').all()){assert.equal(await link.getAttribute('target'),'_blank');assert((await link.getAttribute('rel')).includes('noopener'));}
   await shot('1366-light-search-only');return {resources:0,search_shortcuts:3,legacy_search_type:'tutorial classified as shortcut by known search URL'};
  });
  await check('actual_resources_count_filter_and_details_preserve_provenance',async()=>{
   await reload([...actual,...search]);const panel=await resourcePanel();
   assert.equal(await panel.locator(':scope > summary').innerText(),'学习资料 · 4');
   assert.equal(await panel.getByRole('list',{name:'已保存学习资料'}).locator(':scope > li').count(),4);
   const first=panel.locator('.kw-resource-list > li').first();
   assert.equal(await first.getByText('未检测',{exact:true}).isVisible(),false);
   await first.getByText('资源详情',{exact:true}).click();
   assert(await first.getByText('未检测',{exact:true}).isVisible());assert(await first.getByText('你添加的链接',{exact:true}).isVisible());
   await first.getByText('资源详情',{exact:true}).click();
   await panel.getByLabel('筛选学习资料类型').selectOption('code');
   assert.equal(await panel.locator('.kw-resource-list > li').count(),2);
   assert.equal(await panel.getByRole('navigation',{name:'站外搜索'}).locator('a').count(),3);
   await panel.getByLabel('筛选学习资料类型').selectOption('all');
   assert.equal(await panel.locator('a[href^="javascript:"]').count(),0);
   assert(await panel.getByText('链接地址需要更新。').isVisible());
   await shot('1366-light-mixed-resources');return {resources:4,code_filter:2,search_still_visible:3,hidden_metadata_available:true};
  });
  await check('unavailable_resource_offers_replacement_and_scoped_addition',async()=>{
   const panel=await resourcePanel();const code=panel.locator('.kw-resource-list > li').filter({hasText:'教学代码入口示例'});
   assert(await code.getByText('这个链接最近一次访问未成功。').isVisible());
   await code.getByRole('button',{name:'添加替代链接'}).click();
   assert.equal(await panel.getByLabel('资源标题',{exact:true}).inputValue(),'教学代码入口示例');
   assert.equal(await panel.getByLabel('资源地址',{exact:true}).inputValue(),'');
   await panel.getByLabel('资源地址',{exact:true}).fill('https://example.org/replacement.py');
   await panel.getByRole('button',{name:'保存到当前空间'}).click();
   await panel.getByText('链接已保存',{exact:true}).waitFor();
   assert.equal(report.api_mutations.length,1);assert.equal(report.api_mutations[0].path,endpoint);
   assert.equal(report.api_mutations[0].body.type,'code');
   assert.equal(await panel.locator(':scope > summary').innerText(),'学习资料 · 5');
   return {saved_url:report.api_mutations[0].body.url,origin:'user'};
  });
  await check('video_preview_is_only_loaded_after_explicit_action',async()=>{
   const panel=await resourcePanel();assert.equal(await panel.locator('iframe').count(),0);assert.equal(report.stubbed_embeds.length,0);
   const video=panel.locator('.kw-resource-list > li').filter({hasText:'教学视频入口示例'});
   await video.getByRole('button',{name:'点击播放视频'}).click();
   const frame=panel.locator('iframe');await frame.waitFor();assert((await frame.getAttribute('src')).startsWith('https://www.youtube-nocookie.com/embed/'));
   assert((await frame.getAttribute('sandbox')).includes('allow-scripts'));
   assert.equal(await panel.getByRole('link',{name:'打开原站视频'}).getAttribute('href'),'https://www.youtube.com/watch?v=aircAruvnKk');
   await panel.getByRole('button',{name:'关闭预览'}).click();assert.equal(await panel.locator('iframe').count(),0);
   return {iframe_before_click:0,iframe_after_click:1,player_network:'authored HTML substitute, external network not accessed'};
  });
  await check('refresh_failure_keeps_existing_content_and_has_retry',async()=>{
   const panel=await resourcePanel();failResourceRead=true;
   await panel.getByRole('button',{name:'刷新资源'}).click();
   await panel.getByRole('alert').waitFor();assert(await panel.getByText('学习资料暂时无法更新，已显示的内容仍可使用。',{exact:false}).isVisible());
   assert.equal(await panel.locator('.kw-resource-list > li').count(),5);
   assert.equal(await panel.getByRole('navigation',{name:'站外搜索'}).locator('a').count(),3);
   const raw=panel.getByText('Error: Authored temporary resource service failure',{exact:true});assert.equal(await raw.isVisible(),false);
   failResourceRead=false;await panel.getByRole('button',{name:'重试',exact:true}).click();await panel.getByRole('alert').waitFor({state:'hidden'});
   return {expected_503:1,resources_retained:5,retry_success:true};
  });
  await check('desktop_themes_and_equivalent_125_percent_zoom',async()=>{
   const observations=[];
   for(const viewport of [{width:1366,height:768},{width:1920,height:1080},{width:1152,height:720}]){
    await page.setViewportSize(viewport);
    for(const color of ['light','dark']){
     await theme(color);const metrics=await noOverflow();assert(metrics.document<=metrics.viewport+1,JSON.stringify(metrics));
     assert(metrics.resource<=metrics.resourceWidth+1,JSON.stringify(metrics));observations.push({...viewport,color,...metrics});await shot(`${viewport.width}-${color}-mixed-resources`);
    }
   }
   return {observations,zoom_note:'1152×720 CSS viewport is the 1440×900 at 125% equivalent, not native browser zoom'};
  });
  await check('no_unexpected_errors_or_model_external_requests',async()=>{
   assert.equal(report.page_errors.length,0);assert.equal(report.console_errors.length,0);assert.equal(report.http_errors.length,0);assert.equal(report.model_requests.length,0);assert.equal(report.blocked_external.length,0);
   return {javascript_errors:0,console_errors:0,unexpected_http_errors:0,model_requests:0,external_network_requests:0};
  });
  report.passed=true;
 }catch(error){report.passed=false;report.error=String(error.stack || error);console.error(error);process.exitCode=1;}
 finally{report.finished_at=new Date().toISOString();fs.writeFileSync(path.join(directory,'report.json'),JSON.stringify(report,null,2));await browser?.close();}
})();
