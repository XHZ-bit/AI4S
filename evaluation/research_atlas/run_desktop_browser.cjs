// Desktop rendering checks use synthetic API responses and the actual application UI.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const {chromium} = require('../../frontend/node_modules/playwright');

const base = process.argv[2] || 'http://127.0.0.1:15291';
const directory = path.resolve(process.argv[3] || '.ui_validation/desktop-20261116');
fs.mkdirSync(directory, {recursive: true});
const pid = 'desktop-synthetic';
const project = {id:pid,title:'理解注意力，从问题到可核查的判断',research_question:'注意力为什么需要缩放点积分数？',version:1,status:'active',stage:'exploring',domain:'custom',domain_label:'机器学习',created_at:'2026-11-16',updated_at:'2026-11-16',goals:[],constraints:{},preferences:{}};
const sources = [
 {id:'attention',title:'Attention Is All You Need · 教学摘录'},
 {id:'bahdanau',title:'Jointly Learning to Align and Translate · 教学摘录'},
 {id:'memory',title:'Test-Enhanced Learning · 教学摘录'},
].map(value=>({...value,project_id:pid,asset_id:value.id,version:'synthetic-v1',filename:value.id+'.md',kind:'paper',media_type:'text/markdown',removed:false,created_at:'2026-11-16'}));
const makeNode=(id,kind,label,source='attention',summary='用于桌面界面核查的自编教学说明。')=>({id,kind,label,summary,project_id:pid,source_id:source,parent_id:kind==='paper'?null:source,origin:'source',research_status:'unspecified',version:1,hidden:false,source_missing:false,evidence_ids:kind==='paper'?[]:['e-'+id],metadata:{semantic:true}});
const nodes = [
 ...sources.map(source=>makeNode(source.id,'paper',source.title,source.id)),
 makeNode('problem','problem','相关性得分为什么需要缩放？'),
 makeNode('scaling','formula','缩放点积分数',undefined,'先把 Q 与 K 做点积，再除以键向量维度的平方根。该数值随后进入 softmax。'),
 makeNode('dot','concept','向量点积'),makeNode('method','method','缩放点积注意力'),
 makeNode('softmax','concept','Softmax 与注意力权重'),makeNode('experiment','experiment','固定输入的缩放教学算例'),
 makeNode('finding','finding','缩放分数 4.0，随后再做 softmax'),
 makeNode('additive','method','加性注意力的打分方式','bahdanau'),
 makeNode('retrieval','finding','延迟回忆的实验发现','memory'),
];
while(nodes.length<500)nodes.push(makeNode('extra-'+nodes.length,'concept','扩展知识条目 '+nodes.length,'attention','保留在内容列表中的教学资料。'));
nodes.find(node=>node.id==='scaling').metadata.latex='s = \\frac{QK^T}{\\sqrt{d_k}}';
const makeEdge=(id,source,target,label,kind='USES')=>({id,source,target,label,kind,project_id:pid,source_id:'attention',explanation:'自编教学关系，用于检查定位、可读性和浏览器往返。',origin:'inference',version:1,hidden:false,source_missing:false,evidence_ids:['e-scaling'],metadata:{}});
const edges=[makeEdge('uses','method','scaling','使用缩放分数'),makeEdge('prerequisite','dot','scaling','是前置知识','PREREQUISITE_OF'),makeEdge('next','scaling','softmax','随后归一化'),makeEdge('answers','problem','scaling','通过缩放处理'),makeEdge('checks','experiment','scaling','用教学输入检查'),makeEdge('reports','experiment','finding','记录教学数值')];
const evidence=id=>({id:'e-'+id,source_id:'attention',source_title:sources[0].title,block_id:'scale-block',quote:'The scaled dot product is divided by the square root of d_k before softmax.',locator:{heading:'缩放点积分数的教学摘录'},source_version:'synthetic-v1',origin:'source'});
const sourceDetail = source => ({...source,blocks:[{id:'scale-block',ordinal:0,kind:'formula',heading:'缩放点积分数的教学摘录',text:'教学输入 Q·K = 8、d_k = 4，缩放后得到 4.0。该分数随后进入 softmax。',page:null,metadata:{latex:'8 / \\sqrt{4} = 4.0'}}],knowledge_nodes:[{id:'scaling',label:'缩放点积分数',kind:'formula',block_ids:['scale-block']}]});
const report = {fixture:'synthetic API responses with actual desktop app rendering',dataset_nodes:nodes.length,checks:{},screenshots:[],errors:[],requests:[],performance:{}};

async function main(){
 const browser=await chromium.launch({headless:true,channel:process.env.ATLAS_BROWSER_CHANNEL||'chrome'});
 try{
  for(const size of [{width:1366,height:768},{width:1440,height:900},{width:1920,height:1080}]){
   const context=await browser.newContext({viewport:size,reducedMotion:'reduce'});
   await context.addInitScript(()=>localStorage.setItem('atlas:sidebar-collapsed','true'));
   await context.route('**/*',async route=>{
    const url=new URL(route.request().url());
    if(!['127.0.0.1','localhost'].includes(url.hostname))return route.abort();
    if(!url.pathname.startsWith('/api/'))return route.continue();
    report.requests.push(url.pathname);
    let body={items:[]};
    if(url.pathname==='/api/auth/session')body={mode:'local',user:null,require_login:false};
    else if(url.pathname==='/api/preferences')body={profile:{display_name:'',bio:'',institution:'',interests:'',level:'beginner',weekly_hours:5},features:{foundations:true,glossary:true,quizzes:true,coding:true,visuals:true,paper_guidance:true,roadmap:true,graph:true},provider:{enabled:false,base_url:'',model:''},version:1};
    else if(url.pathname==='/api/projects')body={items:[project],total:1};
    else if(url.pathname==='/api/projects/'+pid)body=project;
    else if(url.pathname==='/api/workbench/projects/'+pid)body={project,papers:[],records:[],sessions:[],features:{}};
    else if(url.pathname.endsWith('/sources'))body={items:sources,preferences:{mode:'explore',view:'graph'},model:{enabled:false,configured:false}};
    else if(url.pathname.includes('/sources/'))body=sourceDetail(sources.find(source=>url.pathname.endsWith('/'+source.id))||sources[0]);
    else if(url.pathname.endsWith('/knowledge/graph')){
     const visible=nodes.slice(0,Number(url.searchParams.get('limit')||240)),ids=new Set(visible.map(node=>node.id));
     body={nodes:visible,edges:edges.filter(edge=>ids.has(edge.source)&&ids.has(edge.target)),total_nodes:500,total_edges:edges.length,truncated:visible.length<500};
    }else if(url.pathname.startsWith('/api/knowledge/edges/'))body={edge:edges.find(edge=>url.pathname.endsWith('/'+edge.id)),evidence:[evidence('scaling')],scope:{id:pid,kind:'project',project_id:pid,title:project.title}};
    else if(url.pathname.includes('/knowledge/nodes/')){
     const id=url.pathname.split('/knowledge/nodes/')[1].split('/')[0],node=nodes.find(node=>node.id===id)||nodes[4];
     if(url.pathname.endsWith('/learning'))body={id:'lesson-'+id,node_id:id,node_version:1,status:'basic',stale:false,cached:true,sections:{overview:node.summary,definition:node.summary,derivation:'',prerequisites:'',implementation:'',limitations:''},evidence:[evidence(id)],resources:[],demos:[],usage:{},errors:[]};
     else if(url.pathname.endsWith('/implementations'))body={items:[],code_sources:[],paper_evidence:[evidence(id)]};
     else if(url.pathname.endsWith('/progress'))body={node_id:id,status:'not_started',version:1};
     else if(url.pathname.endsWith('/summary'))body={node_id:id,summary:'',recommended_actions:[],suggested_node:null};
     else if(/\/(resources|outcomes|history)$/.test(url.pathname))body={items:[]};
     else body={node,neighbors:[],prerequisites:id==='scaling'?[nodes.find(item=>item.id==='dot')]:[],edges:edges.filter(edge=>edge.source===id||edge.target===id),evidence:[evidence(id)],resources:[],demos:[]};
    }
    return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(body)});
   });
   const page=await context.newPage();page.setDefaultTimeout(15000);
   page.on('pageerror',error=>report.errors.push(error.message));
   await page.goto(base+'/research/'+pid);
   await page.getByLabel('研究知识图谱画布',{exact:true}).waitFor();
   await page.locator('[data-node-id="scaling"]').waitFor();
   await page.evaluate(()=>document.fonts.ready);
   const capture=async(name)=>{await page.screenshot({path:path.join(directory,name+'.png')});report.screenshots.push(name+'.png')};
   const noOverflow=await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1);
   assert(noOverflow,'Desktop outer overflow at '+size.width);
   await capture(size.width+'-light');
   await page.getByRole('button',{name:'切换到深色主题',exact:true}).click();
   await capture(size.width+'-dark');
   await page.getByRole('button',{name:'切换到浅色主题',exact:true}).click();
   const before=await page.locator('[data-node-id]').evaluateAll(elements=>elements.map(element=>[element.getAttribute('data-node-id'),element.getAttribute('transform')]));
   await page.locator('[data-node-id="scaling"]').click();
   await page.getByRole('heading',{name:'缩放点积分数',exact:true}).waitFor();
   const after=await page.locator('[data-node-id]').evaluateAll(elements=>elements.map(element=>[element.getAttribute('data-node-id'),element.getAttribute('transform')]));
   assert.deepEqual(after,before,'Selecting a visible node rearranged its graph');
   const overlap=await page.evaluate(()=>{
    const graph=document.querySelector('.kw-graph-canvas').getBoundingClientRect(),panel=document.querySelector('.kw-node-inspector').getBoundingClientRect();
    return Math.max(0,Math.min(graph.right,panel.right)-Math.max(graph.left,panel.left));
   });
   assert.equal(overlap,0,'Node inspector covers canvas');
   const geometry=await page.evaluate(edgeRecords=>{
    const rectangles=selector=>[...document.querySelectorAll(selector)].map(element=>element.getBoundingClientRect());
    const nodes=rectangles('.kw-graph-node rect'),labels=rectangles('.kw-edge-label rect');
    const intersects=(first,second)=>first.left<second.right&&first.right>second.left&&first.top<second.bottom&&first.bottom>second.top;
    const labelCollisions=labels.reduce((sum,label,index)=>sum+[...nodes,...labels.slice(index+1)].filter(other=>intersects(label,other)).length,0);
    let crossings=0;
    for(const route of document.querySelectorAll('[data-edge-id]')){
     const edgeId=route.getAttribute('data-edge-id'),line=route.querySelector('.kw-edge-line');
     const coordinates=(line.getAttribute('d').match(/-?\d+(?:\.\d+)?/g)||[]).map(Number);
     const points=[];for(let index=0;index<coordinates.length;index+=2)points.push(new DOMPoint(coordinates[index],coordinates[index+1]).matrixTransform(line.getScreenCTM()));
     const data=edgeRecords.find(edge=>edge.id===edgeId);
     const unrelated=[...document.querySelectorAll('[data-node-id]')].filter(element=>![data?.source,data?.target].includes(element.getAttribute('data-node-id'))).map(element=>element.querySelector('rect').getBoundingClientRect());
     for(let index=1;index<points.length;index++){
      const first=points[index-1],second=points[index];
      for(const box of unrelated){
       if(Math.abs(first.x-second.x)<.01?first.x>box.left&&first.x<box.right&&Math.max(first.y,second.y)>box.top&&Math.min(first.y,second.y)<box.bottom:first.y>box.top&&first.y<box.bottom&&Math.max(first.x,second.x)>box.left&&Math.min(first.x,second.x)<box.right)crossings++;
      }
     }
    }
    return {labelCollisions,unrelatedNodeCrossings:crossings};
   },edges);
   assert.equal(geometry.labelCollisions,0,'Relationship labels overlap cards or each other');
   assert.equal(geometry.unrelatedNodeCrossings,0,'Relationship crosses an unrelated card');
   await capture(size.width+'-node');
   await page.getByRole('button',{name:'查看原文依据',exact:true}).click();
   await page.locator('.kw-source-highlight').waitFor();
   assert.equal(new URL(page.url()).searchParams.get('block'),'scale-block');
   await page.getByRole('button',{name:'返回原位置',exact:true}).click();
   await page.getByRole('heading',{name:'缩放点积分数',exact:true}).waitFor();
   assert.equal(new URL(page.url()).searchParams.get('node'),'scaling');
   await page.getByRole('button',{name:'关闭节点详情',exact:true}).click();
   const relation=page.locator('[data-edge-id="uses"]');
   await relation.scrollIntoViewIfNeeded();
   const hit=await relation.locator('.kw-edge-hit').evaluate(element=>{
    const matrix=element.getScreenCTM();
    for(const fraction of [.5,.25,.75,.1,.9]){
     const point=element.getPointAtLength(element.getTotalLength()*fraction).matrixTransform(matrix);
     const target=document.elementFromPoint(point.x,point.y)?.closest('[data-edge-id]');
     if(target?.getAttribute('data-edge-id')==='uses')return {x:point.x,y:point.y};
    }
    return null;
   });
   assert(hit,'No visible pointer target on relation path');
   await page.mouse.click(hit.x,hit.y);
   await page.getByRole('heading',{name:'关系与依据',exact:true}).waitFor();
   assert(await page.getByText('修订与核查记录',{exact:true}).isVisible());
   await capture(size.width+'-relation');
   const relationDock=page.getByLabel('关系详情',{exact:true});
   await relationDock.getByRole('button',{name:/教学摘录/}).first().click();
   await page.locator('.kw-source-highlight').waitFor();
   await page.getByRole('button',{name:'返回原位置',exact:true}).click();
   await page.getByRole('heading',{name:'关系与依据',exact:true}).waitFor();
   await page.getByRole('button',{name:'关闭关系详情',exact:true}).click();
   assert(await page.locator('[data-edge-id="uses"]').evaluate(element=>document.activeElement===element),'Relation keyboard focus was lost');
   report.checks[size.width]={outer_overflow:false,stable_node_positions:true,inspector_overlap_px:overlap,node_original_return:true,relation_original_return:true,relation_focus_restored:true,...geometry};
   if(size.width===1440){
    const samples=[];
    for(let index=0;index<20;index++){
     const id=index%2?'method':'scaling';
     const elapsed=await page.locator('[data-node-id="'+id+'"]').evaluate(async element=>{
      const start=performance.now();element.dispatchEvent(new MouseEvent('click',{bubbles:true}));
      await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));return performance.now()-start;
     });
     await page.getByRole('button',{name:'关闭节点详情',exact:true}).click();samples.push(elapsed);
    }
    const sorted=[...samples].sort((a,b)=>a-b);
    report.performance={browser:'local Chrome headless',measurement:'cached visible-node click through two animation frames',dataset_nodes:500,loaded_nodes:240,samples_ms:samples,p95_ms:sorted[Math.ceil(sorted.length*.95)-1],target_ms:200};
    await page.setViewportSize({width:Math.round(size.width/1.25),height:Math.round(size.height/1.25)});
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'125 percent layout-equivalent desktop overflow');
    await capture('1440-125pct-layout-equivalent');
    report.checks[size.width].zoom_layout_equivalent={scale:1.25,css_viewport:{width:Math.round(size.width/1.25),height:Math.round(size.height/1.25)},outer_overflow:false};
   }
   await context.close();
  }
  assert.equal(report.errors.length,0,report.errors.join('\n'));
 }catch(error){report.errors.push(error.message);throw error}
 finally{fs.writeFileSync(path.join(directory,'browser-report.json'),JSON.stringify(report,null,2));await browser.close()}
}
main().catch(error=>{console.error(error);process.exitCode=1});
