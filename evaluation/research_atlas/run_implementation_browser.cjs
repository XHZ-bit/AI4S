// Run against an isolated fixture made by prepare_implementation_fixture.py.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const {execFileSync} = require('node:child_process');
const {chromium} = require('../../frontend/node_modules/playwright');
const directory = path.resolve(process.argv[2]);
const base = process.argv[3] || 'http://127.0.0.1:15274';
const fixture = JSON.parse(fs.readFileSync(path.join(directory, 'fixture.json'), 'utf8'));
const pid = fixture.project_id;
const report = {checks: {}, errors: [], screenshots: [], candidate_evaluation: {}};
const bindExercise = (caseKey, mappingId) => {
 const root = path.resolve(__dirname, '../..');
 const python = process.env.PAPERSTRIDE_PYTHON || path.join(root, 'backend/.venv/Scripts/python.exe');
 return JSON.parse(execFileSync(python, [path.join(__dirname, 'prepare_implementation_fixture.py'), directory,
  '--bind-case', caseKey, '--mapping', mappingId], {encoding:'utf8', cwd:root}));
};

async function run() {
 const browser = await chromium.launch({headless: true, channel: process.env.ATLAS_BROWSER_CHANNEL || 'chrome'});
 const context = await browser.newContext({viewport: {width: 1440, height: 1000}, reducedMotion: 'reduce'});
 await context.route('**/*', route => ['127.0.0.1', 'localhost'].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort());
 const page = await context.newPage();
 page.setDefaultTimeout(20000);
 page.setDefaultNavigationTimeout(60000);
 page.on('pageerror', e => report.errors.push(e.message));
 const request = async (url, method = 'GET', data) => {
  const res = await page.request.fetch(base + url, {method, data});
  assert(res.ok(), `${res.status()} ${url}: ${await res.text()}`);
  return res.json();
 };
 const endpoint = nid => `/api/projects/${pid}/knowledge/nodes/${nid}/implementations`;
 const url = nid => `${base}/research/${pid}?view=learning&node=${nid}`;
 const expand = async () => {const panel = page.locator('.kw-implementation');await panel.locator('summary').click();await panel.getByText('还没有对应关系。', {exact:false}).or(panel.locator('.kw-implementation-item').first()).or(panel.getByText('选择代码资料',{exact:true})).first().waitFor();return panel;};
 const shot = async name => {await page.screenshot({path:path.join(directory,name+'.png')});report.screenshots.push(name+'.png');};
 try {
  const sample = fixture.cases.coordex;
  await page.goto(url(sample.node_id));
  let panel = await expand();
  await panel.getByRole('combobox', {name:'选择代码资料',exact:true}).click();
  await page.locator('.ant-select-item-option').filter({hasText:'coordex'}).first().click();
  await page.keyboard.press('Escape');
  const generated = page.waitForResponse(r=>r.url().endsWith('/implementations/generate')&&r.request().method()==='POST');
  await panel.getByRole('button',{name:'生成待核对关系',exact:true}).click();
  const generation = await (await generated).json();
  assert(generation.items.length>0, 'No local candidate returned for the fixed source');
  report.checks.explicit_generation = true;
  report.candidate_evaluation.coordex = generation.items.map(x=>({id:x.id,block:x.code_block_id,
   result:x.code_block_id===sample.code_block_id?'expected_function':'requires_review'}));
  const created = await request(endpoint(sample.node_id),'POST',{paper_evidence_id:sample.paper_evidence_id,
   code_source_id:sample.code_source_id,code_block_id:sample.code_block_id,paper_span:sample.paper_span.trim(),
   code_span:sample.code_span.trim().slice(0,2400),explanation:'核对原文 tanh 残差与固定版本 actor 输出及分布构造；采样边界由独立教学算例检验。',implementation_kind:'source'});
  await page.reload();panel=await expand();
  let item=panel.locator(`[data-mapping-id="${created.id}"]`);
  await item.getByRole('button',{name:'确认对应',exact:true}).click();
  await item.getByText('已确认',{exact:true}).waitFor();
  await item.getByRole('button',{name:/^编\s*辑$/}).click();
  await panel.getByLabel('对应说明',{exact:true}).fill('已核对：源码更新分布属性，采样由 act 调用；1.3 是后续裁剪之前的教学数值。');
  await panel.getByRole('button',{name:/^保\s*存$/}).click();
  item=panel.locator(`[data-mapping-id="${created.id}"]`);
  await item.getByRole('button',{name:'确认对应',exact:true}).click();
  await item.getByText('已确认',{exact:true}).waitFor();
  await shot('correspondence-desktop');
  await item.getByRole('button',{name:'查看原文',exact:true}).click();
  await page.getByLabel('原文定位区域',{exact:true}).waitFor();
  assert.equal(new URL(page.url()).searchParams.get('page'),'5');
  await shot('coordex-original-formula');
  await page.getByRole('button',{name:'返回原位置',exact:true}).click();
  panel=await expand();item=panel.locator(`[data-mapping-id="${created.id}"]`);
  await item.getByRole('button',{name:'查看代码来源',exact:true}).click();
  await page.locator('.kw-source-highlight').waitFor();
  assert.equal(new URL(page.url()).searchParams.get('source'),sample.code_source_id);
  await page.getByRole('button',{name:'返回原位置',exact:true}).click();
  panel=await expand();item=panel.locator(`[data-mapping-id="${created.id}"]`);
  report.checks.both_originals_and_return = true;
  bindExercise('coordex', created.id);
  await item.getByRole('button',{name:'用于练习',exact:true}).click();
  assert.equal(new URL(page.url()).searchParams.get('mapping'),created.id);
  await page.getByLabel('运行前预测',{exact:true}).fill('预测为 1.3，均值有界不约束未变换的正态样本。');
  const saved=page.waitForResponse(r=>r.url().endsWith('/runs')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'运行代码',exact:true}).click();
  const actual = await (await saved).json();
  assert(actual.output.includes('1.3'),actual.output);assert.equal(actual.mapping_id,created.id);
  await page.getByLabel('运行后的解释',{exact:true}).fill('mu + sigma * epsilon = 1.3。范围判断针对后续裁剪或变换之前的标量采样。');
  await page.getByRole('button',{name:'保存运行解释',exact:true}).click();
  await page.getByText('解释已保存到运行记录。',{exact:true}).waitFor();
  await page.reload();await page.locator('.kw-practice-history > summary').click();
  await page.getByText('运行前预测：预测为 1.3，均值有界不约束未变换的正态样本。',{exact:true}).first().waitFor();
  report.checks.real_python_prediction_result_explanation_reload = true;
  await shot('practice-with-correspondence');
  await page.goto(url(sample.node_id));
  await page.getByText('我的理解与笔记',{exact:true}).click();
  await page.getByRole('button',{name:'导出学习成果',exact:true}).click();
  await page.getByRole('checkbox',{name:/论文与代码映射/}).first().check();
  await page.getByRole('checkbox',{name:/练习 ·/}).first().check();
  await page.getByRole('button',{name:'预览所选内容',exact:true}).click();
  const preview=page.getByLabel('学习成果导出预览',{exact:true});await preview.waitFor();
  assert((await preview.innerText()).includes('1.3'));
  assert((await preview.innerText()).includes('update_distribution'));
  const download=page.waitForEvent('download');
  await page.getByRole('button',{name:'下载 Markdown',exact:true}).click();
  await (await download).saveAs(path.join(directory,'selected-outcome.md'));
  assert(fs.readFileSync(path.join(directory,'selected-outcome.md'),'utf8').includes('1.3'));
  report.checks.explicit_selection_preview_download = true;
  const attention=fixture.cases.attention;
  const empty=await request(endpoint(attention.node_id));assert.equal(empty.items.length,0);
  let teachingId;
  for(const [key,kind]of [['wrong','source'],['teaching','teaching']]){
   const sid=key==='wrong'?attention.wrong_source_id:attention.code_source_id;
   const bid=key==='wrong'?attention.wrong_block_id:attention.code_block_id;
   const code=empty.code_sources.find(s=>s.id===sid).blocks.find(b=>b.id===bid).text;
   const v=await request(endpoint(attention.node_id),'POST',{paper_evidence_id:attention.paper_evidence_id,paper_span:attention.paper_span.trim(),code_source_id:sid,code_block_id:bid,code_span:code.trim(),explanation:key==='wrong'?'同名但乘以 d_k，和除以 sqrt(d_k) 不符。':'自编教学实现，缩放 logit 为 4.0。',implementation_kind:kind});
   await request(endpoint(attention.node_id)+'/'+v.id,'PATCH',{expected_revision:v.revision,status:key==='wrong'?'rejected':'confirmed'});
   if(key==='teaching')teachingId=v.id;
  }
  await request(endpoint(attention.node_id)+'/generate','POST',{source_ids:[attention.wrong_source_id,attention.code_source_id],refresh:true});
  const after=await request(endpoint(attention.node_id));assert(after.items.some(x=>x.status==='rejected'));assert(after.items.some(x=>x.status==='confirmed'&&x.implementation_kind==='teaching'));
  assert(!after.items.some(x=>x.code_block_id===attention.wrong_block_id&&x.status==='proposed'),'Rejected same-function correspondence was suggested again');
  report.checks.attention_same_name_rejection_and_teaching_preserved = true;
  bindExercise('attention', teachingId);
  await page.goto(`${base}/research/${pid}?view=practice&node=${attention.node_id}&mapping=${teachingId}`);
  await page.getByLabel('运行前预测',{exact:true}).fill('8 / sqrt(4) = 4.0，这是教学 logit。');
  const scaled=page.waitForResponse(r=>r.url().endsWith('/runs')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'运行代码',exact:true}).click();
  assert((await (await scaled).json()).output.includes('4.0'));
  report.checks.attention_real_python_scaled_logit = true;
  await page.goto(url(attention.node_id));await expand();
  for(const [width,height] of [[1366,768],[1440,900],[1920,1080]]) {
   await page.setViewportSize({width,height});
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1),`Desktop horizontal overflow at ${width}`);
   await shot(`correspondence-desktop-${width}`);
  }
  await page.getByRole('button',{name:'切换到深色主题',exact:true}).click();
  await shot('correspondence-desktop-dark');
  assert.equal(report.errors.length,0,report.errors.join('\n'));
 } catch(error) {report.errors.push(error.message);report.dom=await page.locator('.kw-implementation-item').evaluateAll(items=>items.map(x=>({id:x.dataset.mappingId,buttons:[...x.querySelectorAll('button')].map(b=>({text:b.textContent,disabled:b.disabled})),text:x.textContent.slice(-300)})));await shot('failure');throw error;}
 finally {fs.writeFileSync(path.join(directory,'browser-report.json'),JSON.stringify(report,null,2));await browser.close();}
}
run().catch(e=>{console.error(e);process.exitCode=1;});
