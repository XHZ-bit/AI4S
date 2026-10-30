// Run against a local Vite dev server; all exercises are synthetic and no API/model generation is used.
import {chromium} from 'playwright';
import fs from 'node:fs';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
const output=fileURLToPath(new URL('../../.tmp/practice-sandbox-report.json',import.meta.url));
fs.mkdirSync(new URL('../../.tmp/',import.meta.url),{recursive:true});
const BASE=process.env.PRACTICE_TEST_ORIGIN||'http://127.0.0.1:5173';
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.PRACTICE_BROWSER_EXECUTABLE||'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 const page=await browser.newPage();const requests=[],errors=[],consoleErrors=[];
 await page.route('**/*',route=>{const url=route.request().url();if(url.startsWith(BASE+'/api/__practice_probe')||url.startsWith('https://example.com/')){requests.push(url);return route.abort()}return route.continue()});
 page.on('pageerror',e=>errors.push(String(e)));page.on('console',m=>{if(m.type()==='error')consoleErrors.push(m.text())});
 try{
  // A real local HTTP resource supplies Chrome's loopback address space. The
  // top-level JavaScript response is displayed as text; no application runs.
  await page.goto(BASE+'/knowledge-practice-worker.js');
  await page.evaluate(()=>{document.cookie='practice_probe=opaque-parent-only';localStorage.setItem('practice_probe','private-parent-fixture')});
  async function run(code,inputs={},tests='',mode='normal'){
   return page.evaluate(async ({code,inputs,tests,mode})=>{
    const {runBrowserPython}=await import('/src/components/knowledge/practiceRuntime.ts');
    const states=[];let runner;
    return new Promise(resolve=>{
     runner=runBrowserPython(code,inputs,tests,{onState:state=>{states.push(state);if(state==='running'&&mode==='cancel')setTimeout(()=>runner.cancel(),150)},onOutput:()=>{},onComplete:result=>resolve({...result,states})},mode==='timeout'?{execution:200}:mode==='loading-timeout'?{loading:50}:{});
    });
   },{code,inputs,tests,mode});
  }
  await page.route(BASE+'/knowledge-practice-worker.js',route=>route.abort());
  const startup=await run('print(1)');assert.equal(startup.status,'error');await page.unroute(BASE+'/knowledge-practice-worker.js');
  const normal=await run("import math, json, statistics, sqlite3, decimal, collections, itertools, datetime, unittest\nprint(sum(inputs['values']))\nprint(round(math.sqrt(9)))",{values:[1,2,3]},'assert sum(inputs["values"]) == 6');
  assert.equal(normal.status,'success');assert.equal(normal.passed,true);assert.match(normal.output,/6\n3/);
  const error=await run('print("before error")\n1 / 0');assert.equal(error.status,'error');assert.match(error.output,/ZeroDivisionError/);
  const network=await run(`import js\nprint('document=', hasattr(js, 'document'))\nprint('parent=', hasattr(js, 'parent'))\nfor url in ['${BASE}/api/__practice_probe', 'https://example.com/practice-probe']:\n    try:\n        await js.fetch(url)\n        print('NETWORK_ALLOWED')\n    except Exception:\n        print('NETWORK_BLOCKED')`);
  assert.equal(network.status,'success');assert.match(network.output,/document= False/);assert.match(network.output,/parent= False/);assert.equal((network.output.match(/NETWORK_BLOCKED/g)||[]).length,2);assert.equal(requests.length,0);
  const timeout=await run("from pyodide.ffi import to_js\nfrom js import Object, self\nself.postMessage(to_js({'type':'ready'}, dict_converter=Object.fromEntries))\nwhile True:\n    pass",{},'','timeout');assert.equal(timeout.status,'timeout');assert.equal(timeout.states.filter(s=>s==='running').length,1);
  const cancelled=await run('while True:\n    pass',{},'','cancel');assert.equal(cancelled.status,'cancelled');
  const loadingTimeout=await run('print(1)',{},'','loading-timeout');assert.equal(loadingTimeout.status,'timeout');
  await page.waitForTimeout(250);assert.equal(await page.locator('iframe').count(),0);
  assert.equal(await page.evaluate(()=>localStorage.getItem('practice_probe')),'private-parent-fixture');
  const report={origin:BASE,fixture_only:true,model_calls:0,startup,normal,error,network,timeout,cancelled,loadingTimeout,blocked_requests_reached_network:requests,remaining_iframes:0,page_errors:errors,expected_csp_console_errors:consoleErrors};
  fs.writeFileSync(output,JSON.stringify(report,null,2));
  console.log(JSON.stringify({pass:true,normal:normal.elapsed_ms,error:error.elapsed_ms,network:network.output,timeout:timeout.elapsed_ms,cancelled:cancelled.elapsed_ms,remaining_iframes:0}));
 }finally{await browser.close()}
})().catch(error=>{console.error(error);process.exitCode=1});


