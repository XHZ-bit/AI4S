/* Complete a saved route step from the learning page, without certifying mastery. */
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('../../frontend/node_modules/playwright');
const directory=path.resolve(process.argv[2]||'.ui_validation/learning-route-20261116-final');
const base=process.argv[3]||'http://127.0.0.1:15297';
const fixture=JSON.parse(fs.readFileSync(path.join(directory,'fixture.json'),'utf8').replace(/^\uFEFF/,''));
const output=path.join(directory,'browser');fs.mkdirSync(output,{recursive:true});
const report={started_at:new Date().toISOString(),fixture:directory,model_stub:true,real_provider_calls:0,checks:[],page_errors:[],http_errors:[],model_requests:[],screenshots:[]};
let browser,page;
async function api(suffix){const response=await page.request.get(`${base}/api/projects/${fixture.project_id}/${suffix}`);assert.ok(response.ok());return response.json();}
(async()=>{try{
 browser=await chromium.launch({headless:true,channel:'chrome'});
 const context=await browser.newContext({viewport:{width:1440,height:900},reducedMotion:'reduce'});
 await context.route('**/*',route=>['127.0.0.1','localhost'].includes(new URL(route.request().url()).hostname)?route.continue():route.abort());
 page=await context.newPage();page.setDefaultTimeout(30000);
 page.on('pageerror',error=>report.page_errors.push(String(error)));
 page.on('response',response=>{if(!response.ok()&&response.url().includes('/api/'))report.http_errors.push({status:response.status(),url:response.url()});});
 page.on('request',request=>{if(request.method()==='POST'&&/\/(generate|supplement|question|summary|analyze)$|\/learning$/.test(new URL(request.url()).pathname))report.model_requests.push(request.url());});
 await page.goto(`${base}/research/${fixture.project_id}?view=route`);
 let route=(await api('knowledge/learning-route')).route;assert.ok(route.next_node_id);
 const currentId=route.next_node_id;const current=route.steps.find(step=>step.node_id===currentId);
 const progress=await api(`knowledge/nodes/${currentId}/progress`);assert.equal(progress.status,'not_started');
 await page.goto(`${base}/research/${fixture.project_id}?view=learning&node=${currentId}`);await page.locator('.kw-learning-view').waitFor();
 const strip=page.getByRole('complementary',{name:'当前学习路线',exact:true});await strip.waitFor();
 await strip.getByRole('button',{name:'完成这一步并继续',exact:true}).click();
 await page.waitForURL(url=>url.searchParams.get('node')!==currentId);
 route=(await api('knowledge/learning-route')).route;
 assert.equal(route.steps.find(step=>step.node_id===currentId).state,'done');assert.ok(route.next_node_id);
 assert.equal(new URL(page.url()).searchParams.get('node'),route.next_node_id);
 assert.equal((await api(`knowledge/nodes/${currentId}/progress`)).status,'not_started');
 await page.locator('.kw-learning-view').waitFor();await page.getByRole('complementary',{name:'当前学习路线',exact:true}).waitFor();
 const file=path.join(output,'1440-light-complete-and-continue.png');await page.screenshot({path:file,fullPage:false});report.screenshots.push(file);
 assert.deepEqual(report.page_errors,[]);assert.deepEqual(report.http_errors,[]);assert.deepEqual(report.model_requests,[]);
 report.checks.push({name:'complete_from_learning_page_opens_server_next_without_mastery_change',passed:true,detail:{completed_node_id:currentId,completed_label:current.label,next_node_id:route.next_node_id,progress:'not_started',revision:route.revision}});report.passed=true;
 console.log('PASS complete_from_learning_page_opens_server_next_without_mastery_change');
}catch(error){report.passed=false;report.error=String(error.stack||error);if(page){await page.screenshot({path:path.join(output,'continue-failure.png'),fullPage:true}).catch(()=>{});}console.error(report.error);process.exitCode=1;
}finally{report.finished_at=new Date().toISOString();fs.writeFileSync(path.join(output,'continue-report.json'),JSON.stringify(report,null,2));if(browser)await browser.close();console.log('Report:',path.join(output,'continue-report.json'));}})();
