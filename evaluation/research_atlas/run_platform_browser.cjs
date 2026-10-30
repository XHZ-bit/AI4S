// Isolated local processes; real Chromium import, action versions and restart flow.
const fs = require('node:fs');
const path = require('node:path');
const {spawn, spawnSync} = require('node:child_process');
const assert = require('node:assert/strict');
const {chromium} = require(process.env.ATLAS_PLAYWRIGHT_PATH || 'playwright');
const root = path.resolve(__dirname,'../..');
const directory = path.resolve(process.argv[2]);
const fixture = JSON.parse(fs.readFileSync(path.join(directory,'browser-fixture.json'),'utf8'));
assert(fixture.interaction_fixture && fixture.user_upload);
assert.notEqual(directory,path.join(root,'backend','data'));
const api = 'http://127.0.0.1:18020', base = 'http://127.0.0.1:15190';
const python = process.env.ATLAS_PYTHON || 'python';
const identity = `platform-${Date.now()}`;
const children=[];
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const report={fixture:'synthetic',checks:{},errors:[],screenshots:[]};
function launch(binary,args,options) { const child=spawn(binary,args,{stdio:'inherit',...options}); children.push(child);return child; }
function backend() { return launch(python,['-m','uvicorn','app.main:app','--host','127.0.0.1','--port','18020'],{cwd:path.join(root,'backend'),env:{...process.env,ATLAS_ENV_FILE:'',DATA_DIR:directory,DASHSCOPE_API_KEY:'',RESEARCH_MODEL_ENABLED:'false',RUNTIME_MODE:'local',RUNTIME_ID:identity,NEO4J_URI:'bolt://127.0.0.1:1',GROBID_BASE_URL:'http://127.0.0.1:1'}}); }
async function ready() { for(let i=0;i<40;i++) { try { const health=await fetch(`${base}/api/cases`,{signal:AbortSignal.timeout(1200)});if(health.ok){const response=await fetch(`${base}/api/system/status`,{signal:AbortSignal.timeout(10000)});const data=await response.json();if(response.ok&&data.runtime_id===identity)return data;} } catch {} await pause(300); } throw Error('Isolated platform failed to become ready'); }
async function stop(child) { if(child.exitCode!==null||child.signalCode!==null)return; const done=new Promise(resolve=>child.once('exit',resolve));child.kill();await done; }
async function waitForTask(request, taskId, timeoutMs=60000) {
  const deadline=Date.now()+timeoutMs, terminal=new Set(['done','failed','cancelled','interrupted']);
  let task, lastError;
  while(Date.now()<deadline) {
    let response;
    try { response=await request.get(`${api}/api/learning/tasks/${taskId}`,{timeout:Math.min(5000,Math.max(1,deadline-Date.now()))}); }
    catch(error) { lastError=error.message; await pause(Math.min(250,Math.max(0,deadline-Date.now()))); continue; }
    assert(response.ok(),`Task ${taskId} polling returned HTTP ${response.status()}`);
    task=await response.json();
    if(terminal.has(task.status))return task;
    await pause(Math.min(250,Math.max(0,deadline-Date.now())));
  }
  throw Error(`Task ${taskId} did not finish within ${timeoutMs}ms; last status: ${task?.status || 'unavailable'}${lastError?`; last request error: ${lastError}`:''}`);
}
(async()=>{
  let browser;
  try {
    let server=backend();
    launch(process.execPath,['node_modules/vite/bin/vite.js','--host','127.0.0.1','--port','15190','--strictPort'],{cwd:path.join(root,'frontend'),env:{...process.env,ATLAS_API_TARGET:api}});
    const state=await ready();
    assert.equal(state.services.model.status,'unconfigured');assert.equal(state.capabilities.graph,false);assert(state.capabilities.automatic_actions);
    report.checks.no_model_no_graph_local_available=true;
    browser=await chromium.launch({headless:true,...(process.env.ATLAS_CHROME_PATH?{executablePath:process.env.ATLAS_CHROME_PATH}:{})});
    const context=await browser.newContext({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
    await context.route('**/*',route=>['localhost','127.0.0.1'].includes(new URL(route.request().url()).hostname)?route.continue():route.abort());
    const page=await context.newPage();page.setDefaultTimeout(15000);page.on('pageerror',error=>report.errors.push(error.message));
    page.on('response',response=>{if(response.status()>=500&&!response.url().endsWith('/api/workflow/v1/overview'))report.errors.push(`HTTP ${response.status()} ${response.url()}`);});
    const shot=async name=>{const file=`${name}.png`;await page.screenshot({path:path.join(directory,file),fullPage:true});report.screenshots.push(file);};
    await page.goto(base);await page.getByText('本地数据库：可用').waitFor();
    await page.getByRole('link',{name:'导入研究资料',exact:true}).click();
    const uploaded=page.waitForResponse(response=>response.url().endsWith('/api/papers/upload-async')&&response.request().method()==='POST');
    await page.locator('input[type=file]').setInputFiles(fixture.user_upload);
    const imported=await(await uploaded).json();assert(imported.uid&&imported.task_id);
    const completed=await waitForTask(page.request,imported.task_id);
    assert.equal(completed.status,'done');assert.equal(completed.type,'parse');
    await page.goto(`${base}/papers/${imported.uid}?tab=reading`);
    await page.getByText('有文字层 1/2 页').waitFor();await page.getByRole('checkbox',{name:'Page 1',exact:true}).check();
    await page.getByText('记录已保存',{exact:true}).waitFor();
    const workspace=await(await page.request.get(`${api}/api/learning/papers/${imported.uid}`)).json();
    assert(Object.values(workspace.state.reading).some(Boolean));
    assert.equal((await(await page.request.get(`${api}/api/workflow/v1/mastery`)).json()).items.length,0);
    report.checks.upload_partial_coverage_reading_separate_from_mastery=true;await shot('platform-paper');
    await page.getByRole('link',{name:'生成自动行动清单',exact:true}).click();
    await page.getByLabel('行动清单名称').fill('Independent paper plan');
    await page.getByRole('button',{name:'预览自动行动清单',exact:true}).click();
    await page.getByRole('button',{name:'保存自动行动清单',exact:true}).click();
    await page.locator('.ant-card-head-title').filter({hasText:'Independent paper plan · v1'}).waitFor();
    const ident=new URL(page.url()).searchParams.get('id');assert(ident);
    await page.reload();await page.locator('.ant-card-head-title').filter({hasText:'Independent paper plan · v1'}).waitFor();
    report.checks.immutable_action_save_and_refresh=true;await shot('platform-actions');
    await stop(server);server=backend();await ready();
    await page.reload();await page.locator('.ant-card-head-title').filter({hasText:'Independent paper plan · v1'}).waitFor();
    const restored=await(await page.request.get(`${api}/api/actions/v1/${ident}`)).json();
    assert(restored.items.some(item=>item.status==='completed'));report.checks.restart_restores_activity_and_plan=true;
    const change=spawnSync(python,['-c',"import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); c.execute('UPDATE passages SET text=text||? WHERE document_id IN (SELECT id FROM documents WHERE paper_uid=?)',(' Changed source for acceptance.',sys.argv[2])); c.commit(); c.close()",path.join(directory,'atlas.db'),imported.uid],{encoding:'utf8'});
    assert.equal(change.status,0,change.stderr);
    await page.reload();await page.getByText('来源变化，待复核',{exact:true}).waitFor();
    await page.getByRole('button',{name:'预览清单调整',exact:true}).click();
    await page.getByRole('button',{name:'确认保存清单新版本',exact:true}).click();
    await page.locator('.ant-card-head-title').filter({hasText:'Independent paper plan · v2'}).waitFor();
    const old=await(await page.request.get(`${api}/api/actions/v1/${ident}?version=1`)).json();assert.equal(old.version,1);assert.equal(old.needs_review,true);
    report.checks.changed_source_review_preview_new_version_old_preserved=true;
    const block='**/api/workflow/v1/overview';
    await context.route(block,route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'Injected overview failure'})}));
    await page.goto(`${base}/workflow`);await page.getByText(/概览加载失败/).waitFor();
    await page.getByText('全部活动',{exact:true}).waitFor();await page.getByRole('link',{name:/阅读：Independent research input/}).first().waitFor();
    report.checks.partial_failure_other_sections_survive=true;await context.unroute(block);
    await page.goto(`${base}/workflow`);await page.getByRole('button',{name:'记录步骤产出',exact:true}).click();
    await page.getByRole('checkbox',{name:'按快照验收条件完成',exact:true}).check();
    await page.getByLabel('步骤产出或观察').fill('Isolated platform acceptance: saved observation, not a research conclusion.');
    await page.locator('.ant-modal-footer .ant-btn-primary').click();await page.getByRole('dialog').waitFor({state:'hidden'});
    await page.reload();await page.getByText('Isolated platform acceptance: saved observation, not a research conclusion.',{exact:true}).first().waitFor();
    report.checks.snapshot_step_output_restored=true;
    await page.goto(`${base}/tasks`);await page.getByRole('link',{name:imported.uid,exact:true}).first().waitFor();
    report.checks.unified_task_progress_available=true;
    await page.goto(base);await page.getByText('本地数据库：可用').waitFor();
    await context.setOffline(true);await page.getByRole('button',{name:'检查状态',exact:true}).click();await page.getByText('运行状态读取失败',{exact:true}).waitFor();
    await context.setOffline(false);await page.getByRole('button',{name:'检查状态',exact:true}).click();await page.getByText('运行状态读取失败',{exact:true}).waitFor({state:'hidden'});
    report.checks.network_failure_and_recovery_visible=true;
    await page.goto(`${base}/actions?id=${ident}`);await page.locator('.ant-card-head-title').filter({hasText:'Independent paper plan · v2'}).waitFor();
    await page.setViewportSize({width:390,height:900});
    const widths=await page.evaluate(()=>({viewport:innerWidth,content:document.documentElement.scrollWidth}));assert(widths.content<=widths.viewport+1,JSON.stringify(widths));
    report.checks.mobile_action_list_no_overflow=true;await shot('platform-actions-mobile');
    assert.deepEqual(report.errors,[]);report.passed=true;
  } finally {
    if(browser)await browser.close();
    await Promise.all(children.map(stop));
    fs.writeFileSync(path.join(directory,'platform-browser.json'),JSON.stringify(report,null,2));
  }
  console.log(JSON.stringify(report,null,2));
})().catch(error=>{console.error(error);process.exitCode=1;});
