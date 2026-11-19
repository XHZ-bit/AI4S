/* Focused regression for route -> source -> route -> exploration canvas return.
 * Run after run_route_browser.cjs against the same isolated saved-route fixture.
 */
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('../../frontend/node_modules/playwright');
const directory=path.resolve(process.argv[2]||'.ui_validation/learning-route-20261116-final');
const base=process.argv[3]||'http://127.0.0.1:15297';
const fixture=JSON.parse(fs.readFileSync(path.join(directory,'fixture.json'),'utf8').replace(/^\uFEFF/,''));
const output=path.join(directory,'browser');fs.mkdirSync(output,{recursive:true});
const report={started_at:new Date().toISOString(),fixture:directory,model_stub:true,real_provider_calls:0,checks:[],page_errors:[],console_errors:[],http_errors:[],model_requests:[],screenshots:[]};
let browser,page;
const key=`paperstride:knowledge-scene:${fixture.project_id}:canvas`;
async function snapshot(){return page.evaluate(key=>JSON.parse(localStorage.getItem(key)||'null'),key);}
async function settle(){await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));}
(async()=>{try{
 browser=await chromium.launch({headless:true,channel:'chrome'});
 const context=await browser.newContext({viewport:{width:1440,height:900},reducedMotion:'reduce'});
 await context.route('**/*',async route=>{
   const url=new URL(route.request().url());
   if(!['127.0.0.1','localhost'].includes(url.hostname))return route.abort();
   // Keep the real response; delay the route read so the loading state renders.
   if(route.request().method()==='GET'&&url.pathname.endsWith('/knowledge/learning-route'))await new Promise(resolve=>setTimeout(resolve,250));
   return route.continue();
 });
 page=await context.newPage();page.setDefaultTimeout(30000);
 page.on('pageerror',error=>report.page_errors.push(String(error)));
 page.on('console',message=>{if(message.type()==='error')report.console_errors.push(message.text());});
 page.on('response',response=>{if(!response.ok()&&response.url().includes('/api/'))report.http_errors.push({status:response.status(),url:response.url()});});
 page.on('request',request=>{if(request.method()==='POST'&&/\/(generate|supplement|question|summary|analyze)$|\/learning$/.test(new URL(request.url()).pathname))report.model_requests.push(request.url());});
 await page.goto(`${base}/research/${fixture.project_id}?view=graph&source=${fixture.source_id}&node=${fixture.nodes.unrelated}`);
 await page.locator('.kw-node-panel').waitFor();await page.locator('.kw-graph-canvas svg').waitFor();
 for(let i=0;i<8;i++)await page.getByRole('button',{name:'放大图谱',exact:true}).click();
 await settle();await page.locator('.kw-graph-canvas').evaluate(element=>{element.scrollLeft=130;element.scrollTop=75;element.dispatchEvent(new Event('scroll'));});await settle();
 const before=await snapshot();assert.equal(before.scope,`${fixture.project_id}/${fixture.source_id}`);assert.equal(new URL(page.url()).searchParams.get('node'),fixture.nodes.unrelated);assert.ok(before.zoom>1);
 const originalUrl=page.url();
 await page.getByRole('button',{name:'学习路线',exact:true}).click();await page.getByRole('region',{name:'我的学习路线',exact:true}).waitFor();
 await page.getByRole('button',{name:'在图谱中查看路线',exact:true}).click();await page.getByRole('region',{name:'已保存路线图谱',exact:true}).waitFor();
 await page.locator('.kw-graph-node').first().waitFor();
 await page.getByRole('button',{name:'放大图谱',exact:true}).click();await page.getByRole('button',{name:'放大图谱',exact:true}).click();await settle();
 const whileInRoute=await snapshot();assert.equal(whileInRoute.scope,before.scope);assert.equal(whileInRoute.zoom,before.zoom);
 await page.locator(`.kw-graph-node[data-node-id="${fixture.nodes.goal}"]`).press('Enter');await page.locator('.kw-node-panel').waitFor();
 await page.locator('.kw-node-panel').getByRole('button',{name:'查看原文依据',exact:true}).click();await page.locator('.kw-source-reader').waitFor();
 assert.equal(new URL(page.url()).searchParams.get('view'),'reading');
 await page.getByRole('button',{name:'返回原位置',exact:true}).click();await page.getByRole('region',{name:'已保存路线图谱',exact:true}).waitFor();
 await page.getByRole('button',{name:'返回自由探索图谱',exact:true}).click();await page.locator('.kw-saved-route-map').waitFor({state:'detached'});await page.locator('.kw-node-panel').waitFor();await page.locator('.kw-graph-canvas svg').waitFor();await settle();
 const params=new URL(page.url()).searchParams;assert.equal(params.get('source'),fixture.source_id);assert.equal(params.get('node'),fixture.nodes.unrelated);assert.ok(!params.has('route'));
 const after=await snapshot();report.scene_debug={before,after};assert.equal(after.scope,before.scope);assert.equal(after.focus,before.focus);assert.equal(after.zoom,before.zoom);
 const canvas=await page.locator('.kw-graph-canvas').evaluate(element=>({left:element.scrollLeft,top:element.scrollTop,maxLeft:Math.max(0,element.scrollWidth-element.clientWidth),maxTop:Math.max(0,element.scrollHeight-element.clientHeight)}));
 assert.ok(Math.abs(canvas.left-Math.min(before.scrollLeft,canvas.maxLeft))<=1,JSON.stringify({before,after,canvas}));
 assert.ok(Math.abs(canvas.top-Math.min(before.scrollTop,canvas.maxTop))<=1,JSON.stringify({before,after,canvas}));
 assert.deepEqual(report.page_errors,[]);assert.deepEqual(report.console_errors,[]);assert.deepEqual(report.http_errors,[]);assert.deepEqual(report.model_requests,[]);
 const shot=path.join(output,'1440-light-canvas-restored.png');await page.screenshot({path:shot,fullPage:false});report.screenshots.push(shot);
 report.checks.push({name:'route_reader_roundtrip_restores_original_source_node_zoom_scroll',passed:true,detail:{original_url:originalUrl,returned_url:page.url(),before,after,canvas}});report.passed=true;
 console.log('PASS route_reader_roundtrip_restores_original_source_node_zoom_scroll');
}catch(error){report.passed=false;report.error=String(error.stack||error);if(page){await page.screenshot({path:path.join(output,'canvas-failure.png'),fullPage:true}).catch(()=>{});fs.writeFileSync(path.join(output,'canvas-failure.html'),await page.content().catch(()=>''));}console.error(report.error);process.exitCode=1;
}finally{report.finished_at=new Date().toISOString();fs.writeFileSync(path.join(output,'canvas-report.json'),JSON.stringify(report,null,2));if(browser)await browser.close();console.log('Report:',path.join(output,'canvas-report.json'));}})();
