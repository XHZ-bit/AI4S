/* Focused initial-fit check for a one-node project, using a fresh browser
 * context per theme. Run after the complete project-network acceptance.
 */
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('../../frontend/node_modules/playwright');
const directory=path.resolve(process.argv[2]||'.ui_validation/project-network-20261117-final2');
const base=process.argv[3]||'http://127.0.0.1:15299';
const fixture=JSON.parse(fs.readFileSync(path.join(directory,'fixture.json'),'utf8').replace(/^\uFEFF/,''));
const output=path.join(directory,'browser');fs.mkdirSync(output,{recursive:true});
const report={started_at:new Date().toISOString(),fixture:directory,source_kind:'authored_teaching_material',real_provider_calls:0,checks:[],screenshots:[],page_errors:[],console_errors:[],http_errors:[],blocked_external:[]};
let browser;
(async()=>{try{
 browser=await chromium.launch({headless:true,channel:'chrome'});
 for(const color of ['light','dark']){
  const context=await browser.newContext({viewport:{width:1366,height:768},reducedMotion:'reduce'});
  await context.addInitScript(value=>localStorage.setItem('research-atlas-theme',value),color);
  await context.route('**/*',route=>{if(['127.0.0.1','localhost'].includes(new URL(route.request().url()).hostname))return route.continue();report.blocked_external.push(route.request().url());return route.abort();});
  const page=await context.newPage();page.setDefaultTimeout(30000);
  page.on('pageerror',error=>report.page_errors.push(String(error)));
  page.on('console',message=>{if(message.type()==='error')report.console_errors.push(message.text());});
  page.on('response',response=>{if(!response.ok()&&response.url().includes('/api/'))report.http_errors.push({status:response.status(),url:response.url()});});
  await page.goto(`${base}/research/${fixture.other_project_id}?view=graph`);
  await page.getByRole('button',{name:'关系网络',exact:true}).click();
  const network=page.getByRole('region',{name:'课题关系网络',exact:true});await network.waitFor();
  await page.waitForFunction(pid=>Object.keys(localStorage).filter(key=>key.includes('project-network:'+pid)).some(key=>{const value=JSON.parse(localStorage.getItem(key)||'{}');return value.camera&&value.camera.zoom<=2&&Object.keys(value.positions||{}).length===1;}),fixture.other_project_id);
  const scene=await page.evaluate(pid=>JSON.parse(localStorage.getItem(Object.keys(localStorage).find(key=>key.includes('project-network:'+pid)))),fixture.other_project_id);
  assert.ok(scene.camera.zoom>0&&scene.camera.zoom<=2,JSON.stringify(scene.camera));
  await page.getByLabel('定位关系网络节点').selectOption(fixture.other_node.id);
  await page.getByRole('complementary',{name:'知识节点详情'}).locator('h2').waitFor();
  const file=path.join(output,`1366-${color}-single-node.png`);await page.screenshot({path:file});report.screenshots.push(file);
  report.checks.push({name:`one_node_initial_fit_and_selection_${color}`,passed:true,camera:scene.camera,node_count:Object.keys(scene.positions).length});
  await context.close();
 }
 assert.deepEqual(report.page_errors,[]);assert.deepEqual(report.console_errors,[]);assert.deepEqual(report.http_errors,[]);assert.deepEqual(report.blocked_external,[]);
 report.passed=true;
}catch(error){report.passed=false;report.error=String(error.stack||error);console.error(error);process.exitCode=1;}
finally{report.finished_at=new Date().toISOString();fs.writeFileSync(path.join(output,'single-node-report.json'),JSON.stringify(report,null,2));if(browser)await browser.close();}})();
