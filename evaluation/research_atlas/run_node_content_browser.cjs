/* Node learning content acceptance against the actual local React application.
 * Usage: prepare_node_content_fixture.py, then node this-file [base URL]
 * The fixture exports the real backend guide module. All API calls are mocked
 * in a separate browser context, and no account, user database or external site
 * is accessed. This checks presentation and navigation, not extraction quality.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require('../../frontend/node_modules/playwright');
const base = process.argv[2] || 'http://127.0.0.1:5173';
const directory = path.resolve('.ui_validation/node-content-20261117');
const fixture = JSON.parse(fs.readFileSync(path.join(directory, 'fixture.json'), 'utf8').replace(/^\uFEFF/, ''));
const {project, source, nodes, graph, details} = fixture;
const pid = project.id;
const self = nodes['self-attention'];
const guide = details[self.id].study_guide;
const report = {started_at:new Date().toISOString(), fixture:directory,
  source_kind:fixture.source_kind, api_stub:true, guide_origin:fixture.guide_origin,
  real_provider_calls:0, checks:[], screenshots:[], page_errors:[], console_errors:[],
  http_errors:[], blocked_external:[], api_mutations:[], model_requests:[]};
let browser, context, page, lessonMode = 'basic';
async function check(name, action) {
  try {const detail = await action(); report.checks.push({name, passed:true, detail}); console.log('PASS', name);}
  catch(error) {report.checks.push({name, passed:false, error:String(error.stack || error)}); throw error;}
}
async function learn(id = self.id) {
  await page.goto(`${base}/research/${pid}?view=learning&node=${id}`);
  await page.locator('.kw-learning-view').waitFor();
}
async function inspect(id = self.id) {
  await page.goto(`${base}/research/${pid}?view=graph&source=${source.id}&node=${id}`);
  await page.getByRole('complementary', {name:'知识节点详情'}).waitFor();
  await page.getByRole('complementary', {name:'知识节点详情'}).getByRole('heading', {name:nodes[id].label, exact:true}).waitFor();
  return page.getByRole('complementary', {name:'知识节点详情'});
}
async function theme(value) {
  await page.evaluate(value => {
    localStorage.setItem('research-atlas-theme', value);
    window.dispatchEvent(new StorageEvent('storage', {key:'research-atlas-theme', newValue:value}));
  }, value);
  await page.locator(`html[data-theme="${value}"]`).waitFor();
}
async function scrollTo(locator) {
  await locator.evaluate(element => {
    element.scrollIntoView({block:'start'});
    let parent = element.parentElement;
    while (parent && parent !== document.documentElement) {
      if (/auto|scroll/.test(getComputedStyle(parent).overflowY) && parent.scrollHeight > parent.clientHeight) {
        parent.scrollBy(0, -88); return;
      }
      parent = parent.parentElement;
    }
    window.scrollBy(0, -88);
  });
}
async function shot(name, locator) {
  if (locator) await locator.evaluate(element => {
    if (element.matches('.kw-node-panel-header')) {
      const body = element.closest('.kw-node-panel')?.querySelector('.kw-node-panel-body');
      if (body) body.scrollTop = 0;
    }
  });
  if (locator) await scrollTo(locator);
  const file = path.join(directory, name + '.png');
  await page.screenshot({path:file, fullPage:false}); report.screenshots.push(file);
}
async function overflowMetrics() {
  return page.evaluate(() => {
    const panel = document.querySelector('.kw-node-panel');
    const guide = document.querySelector('.kw-node-study-guide');
    return {viewport:innerWidth, document:document.documentElement.scrollWidth,
      panel:panel ? Math.round(panel.getBoundingClientRect().width) : null,
      panelScroll:panel ? panel.scrollWidth : null,
      guide:guide ? Math.round(guide.getBoundingClientRect().width) : null,
      guideScroll:guide ? guide.scrollWidth : null};
  });
}
(async() => {
  try {
    browser = await chromium.launch({headless:true, channel:process.env.ATLAS_BROWSER_CHANNEL || 'chrome'});
    context = await browser.newContext({viewport:{width:1366,height:768}, reducedMotion:'reduce'});
    await context.route('**/*', async route => {
      const request = route.request(), url = new URL(request.url());
      if (!['localhost','127.0.0.1'].includes(url.hostname)) {report.blocked_external.push(url.href); return route.abort();}
      if (!url.pathname.startsWith('/api/')) return route.continue();
      const method = request.method();
      if (method !== 'GET') report.api_mutations.push({method, path:url.pathname});
      if (method === 'POST' && /\/(generate|supplement|question|summary|analyze|learning)$/.test(url.pathname)) report.model_requests.push(url.pathname);
      let body = {items:[]};
      const match = url.pathname.match(new RegExp(`^/api/projects/${pid}/knowledge/nodes/([^/]+)(?:/(.*))?$`));
      if (url.pathname === '/api/auth/session') body = {mode:'local', user:null, require_login:false};
      else if (url.pathname === '/api/preferences') body = {profile:{display_name:'',bio:'',institution:'',interests:'',level:'beginner',weekly_hours:5},features:{foundations:true,glossary:true,quizzes:true,coding:true,visuals:true,paper_guidance:true,roadmap:true,graph:true},provider:{enabled:false,base_url:'',model:''},version:1};
      else if (url.pathname === '/api/projects') body = {items:[project],total:1};
      else if (url.pathname === `/api/projects/${pid}`) body = project;
      else if (url.pathname === `/api/workbench/projects/${pid}`) body = {project,papers:[],records:[],sessions:[],features:{}};
      else if (url.pathname === `/api/projects/${pid}/sources`) body = {items:[source],preferences:{mode:'explore',view:'graph'},model:{enabled:false,configured:false}};
      else if (url.pathname === `/api/projects/${pid}/sources/${source.id}`) body = source;
      else if (url.pathname === `/api/projects/${pid}/knowledge/graph`) body = graph;
      else if (url.pathname === `/api/projects/${pid}/knowledge/learning-route`) body = {route:null};
      else if (url.pathname === `/api/projects/${pid}/knowledge/checks/recommendation`) body = {recommendation:null};
      else if (url.pathname === `/api/projects/${pid}/knowledge/progress`) body = {items:[]};
      else if (url.pathname === `/api/projects/${pid}/knowledge/paths`) body = {nodes:[],edges:[],paths:[],cycle_detected:false,truncated:false,message:'本测试不预设学习路径'};
      else if (url.pathname.startsWith('/api/knowledge/edges/')) {
        const edge = graph.edges.find(item => item.id === url.pathname.split('/').pop());
        body = {edge, evidence:[details[self.id].evidence[1]], scope:{id:pid,title:project.title}};
      } else if (match && nodes[decodeURIComponent(match[1])]) {
        const id = decodeURIComponent(match[1]), node = nodes[id], detail = details[id], suffix = match[2] || '';
        if (!suffix) body = detail;
        else if (suffix === 'learning') {
          body = {id:'lesson-' + id,node_id:id,node_version:1,revision:1,status:lessonMode === 'ready' ? 'ready' : 'basic',stale:false,cached:true,origin:lessonMode === 'ready' ? 'user' : 'source',
            user_edited_sections:lessonMode === 'ready' ? ['overview'] : [],
            sections:{overview:lessonMode === 'ready' ? '我保存的解释：先确认信息来源，再看聚合过程。' : node.summary,
              definition:node.summary,derivation:'',prerequisites:'',implementation:'',limitations:''},
            evidence:detail.evidence, resources:[], demos:[], usage:{},errors:[]};
        } else if (suffix === 'progress') body = {node_id:id,status:'not_started',version:0};
        else if (suffix === 'checks') body = {questions:[],history:[],available:false,context_fingerprint:'authored'};
        else if (suffix === 'implementations') body = {items:[],code_sources:[],paper_evidence:[detail.evidence[0]]};
        else if (suffix === 'concept-correspondences') body = {candidates:[],items:[],left:{node,evidence:[detail.evidence[0]],conditions:{}}};
      }
      return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(body)});
    });
    page = await context.newPage(); page.setDefaultTimeout(20000); page.setDefaultNavigationTimeout(60000);
    page.on('pageerror', error => report.page_errors.push(String(error)));
    page.on('console', message => {if (message.type() === 'error') report.console_errors.push(message.text());});
    page.on('response', response => {if (!response.ok() && response.url().includes('/api/')) report.http_errors.push({status:response.status(),url:response.url()});});

    await check('one_line_english_node_has_substantial_chinese_teaching_and_worked_example', async() => {
      await learn(); const teaching = page.getByRole('region', {name:'知识基础讲解'});
      await teaching.waitFor(); assert(await teaching.getByText('通用教学', {exact:true}).isVisible());
      assert((await teaching.innerText()).includes('自注意力让同一序列'));
      assert.equal(await teaching.locator('.kw-study-flow > li').count(),4);
      assert.equal(await teaching.locator('.kw-study-confusions dl > div').count(),3);
      const example = teaching.locator('.kw-study-example');
      assert((await example.innerText()).includes('0.75'));
      assert((await example.innerText()).includes('0.25'));
      assert((await example.innerText()).includes('=3'));
      assert((await example.locator('.katex').count()) > 0);
      assert(await page.getByRole('heading', {name:'资料中的描述',exact:true}).isVisible());
      await shot('1366-light-self-attention-lesson', teaching);
      await shot('1366-light-worked-example', example);
      return {guide_topic:guide.topic,actual_module_version:guide.version,flow_steps:4,confusions:3,weighted_value:3,original_summary_preserved:self.summary};
    });
    await check('side_panel_combines_teaching_direct_evidence_and_actual_directional_relations', async() => {
      const panel = await inspect(); const teaching = panel.getByRole('region',{name:'节点基础讲解'});
      assert(await teaching.isVisible()); await teaching.locator('summary').filter({hasText:'看一个例子'}).click();
      assert((await teaching.locator('.kw-study-example').innerText()).includes('=3'));
      const direct = panel.getByRole('region',{name:'当前知识的原文片段'});
      assert((await direct.innerText()).includes(self.summary));
      assert(!(await direct.innerText()).includes('关联来源的条件'));
      assert(!(await direct.innerText()).includes('自编关系摘录'));
      const role = panel.getByRole('region',{name:'在知识图谱中的作用'});
      assert((await role.innerText()).includes('Self-attention'));
      assert((await role.innerText()).includes('使用'));
      assert((await role.innerText()).includes('缩放点积注意力'));
      assert((await role.innerText()).includes('在本教学图中'));
      await shot('1366-light-node-side-panel', panel.locator('header').first());
      await shot('1366-light-node-evidence-relations', role);
      await panel.getByRole('button',{name:'查看关系：Self-attention 使用 缩放点积注意力'}).click();
      const relation = panel.getByRole('region',{name:'关系详情'});await relation.waitFor();
      assert((await relation.locator('.kw-edge-statement').innerText()).includes('Self-attention'));
      await relation.getByRole('button',{name:'关闭关系详情'}).click();
      return {direct_evidence_count:1,relation_count:2,relation_direction:'Self-attention → 使用 → 缩放点积注意力'};
    });
    await check('direct_evidence_locates_the_exact_original_block_and_returns', async() => {
      const panel = page.getByRole('complementary',{name:'知识节点详情'});
      await panel.getByRole('button',{name:'查看原文依据',exact:true}).click();
      await page.waitForURL(url => url.searchParams.get('view') === 'reading');
      assert.equal(new URL(page.url()).searchParams.get('block'),'b-self-attention');
      assert.equal(new URL(page.url()).searchParams.get('source'),source.id);
      await page.getByRole('heading',{name:'Self-attention',exact:true}).first().waitFor();
      await page.getByRole('button',{name:'返回原位置',exact:true}).click();
      await page.getByRole('region',{name:'节点基础讲解'}).waitFor();
      assert.equal(new URL(page.url()).searchParams.get('node'),self.id);
      return {source:source.id,block:'b-self-attention',returned_node:self.id};
    });
    await check('saved_user_lesson_stays_primary_and_foundation_recall_is_optional', async() => {
      lessonMode = 'ready'; await learn();
      const recall = page.locator('.kw-learning-primer-recall');await recall.waitFor();
      assert.equal(await recall.getAttribute('open'),null);
      assert.equal(await page.getByRole('region',{name:'知识基础讲解'}).isVisible(),false);
      assert(await page.getByText('我保存的解释：先确认信息来源，再看聚合过程。',{exact:true}).isVisible());
      await recall.locator(':scope > summary').click();assert(await page.getByRole('region',{name:'知识基础讲解'}).isVisible());
      await shot('1366-light-saved-lesson-recall', recall);
      lessonMode = 'basic'; return {user_revision_preserved:true,recall_default:'closed',explicit_recall:true};
    });
    await check('unknown_topics_and_psychology_do_not_get_transformer_tutorials', async() => {
      await learn('unknown');assert.equal(await page.locator('.kw-node-study-guide').count(),0);
      assert(await page.getByText(nodes.unknown.summary,{exact:true}).first().isVisible());
      let panel = await inspect('unknown');
      assert.equal(await panel.locator('.kw-node-study-guide').count(),0);
      assert(await panel.getByRole('region',{name:'当前知识的原文片段'}).isVisible());
      assert(await panel.getByRole('region',{name:'在知识图谱中的作用'}).isVisible());
      await learn('psychology'); assert.equal(await page.locator('.kw-node-study-guide').count(),0);
      assert.equal(await page.getByText('区分查询、键和值',{exact:true}).count(),0);
      return {unknown_teaching:null,unknown_evidence_and_relations:true,psychology_teaching:null};
    });
    await check('no_code_research_design_also_has_a_complete_learning_entry', async() => {
      await learn('research-design');const teaching = page.getByRole('region',{name:'知识基础讲解'});await teaching.waitFor();
      assert((await teaching.innerText()).includes('测量'));
      assert((await teaching.locator('.kw-study-flow > li').count()) >= 3);
      assert((await teaching.locator('.kw-study-example').innerText()).length > 40);
      await shot('1366-light-research-design-lesson', teaching);
      return {guide_topic:details['research-design'].study_guide.topic,has_code_source:false};
    });
    await check('desktop_themes_keyboard_and_equivalent_125_percent_zoom', async() => {
      const metrics = [];
      for (const viewport of [{width:1366,height:768},{width:1920,height:1080},{width:1152,height:720}]) {
        await page.setViewportSize(viewport);
        for (const color of ['light','dark']) {
          await theme(color);await learn();
          const teaching = page.getByRole('region',{name:'知识基础讲解'});await teaching.waitFor();
          let measurement = await overflowMetrics();assert(measurement.document <= measurement.viewport + 1,JSON.stringify(measurement));
          assert(measurement.guideScroll <= measurement.guide + 1,JSON.stringify(measurement));
          metrics.push({...viewport,color,view:'learning',...measurement});await shot(`${viewport.width}-${color}-lesson`,teaching);
          const panel = await inspect();
          const active = panel.getByRole('tab',{name:'知识与学习'});await active.focus();await page.keyboard.press('ArrowRight');
          assert.equal(await panel.getByRole('tab',{name:'原文与资料'}).getAttribute('aria-selected'),'true');
          await page.keyboard.press('ArrowLeft');
          assert.equal(await active.getAttribute('aria-selected'),'true');
          measurement = await overflowMetrics();assert(measurement.document <= measurement.viewport + 1,JSON.stringify(measurement));
          assert(measurement.panelScroll <= measurement.panel + 1,JSON.stringify(measurement));
          metrics.push({...viewport,color,view:'inspector',...measurement});await shot(`${viewport.width}-${color}-side-panel`,panel.locator('header').first());
        }
      }
      return {metrics,zoom_note:'1152×720 CSS viewport is the equivalent of 1440×900 at 125%, not native browser zoom'};
    });
    await check('reads_never_generate_content_or_access_external_services', async() => {
      assert.equal(report.page_errors.length,0);assert.equal(report.console_errors.length,0);
      assert.equal(report.http_errors.length,0);assert.equal(report.blocked_external.length,0);
      assert.equal(report.api_mutations.length,0);assert.equal(report.model_requests.length,0);
      return {page_errors:0,console_errors:0,http_errors:0,external_requests:0,api_mutations:0,model_requests:0};
    });
    report.passed = true;
  } catch(error) {report.passed = false;report.error = String(error.stack || error);console.error(error);process.exitCode=1;}
  finally {report.finished_at = new Date().toISOString();fs.writeFileSync(path.join(directory,'report.json'),JSON.stringify(report,null,2));await browser?.close();}
})();
