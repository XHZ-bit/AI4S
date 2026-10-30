import {NODE_WIDTH,NODE_HEIGHT} from '../components/knowledge/KnowledgeGraphLayout';
import {fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {MemoryRouter,Route,Routes,useLocation} from 'react-router-dom';
import {beforeEach,expect,test,vi} from 'vitest';
import KnowledgeWorkbench from '../components/knowledge/KnowledgeWorkbench';
import {SourceReader} from '../components/knowledge/KnowledgeSources';
import KnowledgeDemos from '../components/knowledge/KnowledgeDemos';
import KnowledgeComparison from '../components/knowledge/KnowledgeComparison';
import KnowledgeLearning from '../components/knowledge/KnowledgeLearning';
import KnowledgeGraphView,{layoutGraph} from '../components/knowledge/KnowledgeGraph';
import {project} from './research/fixtures';
import type {KnowledgeNode,KnowledgeSource} from '../api/knowledge';

const api=vi.hoisted(()=>({sources:vi.fn(),graph:vi.fn(),node:vi.fn(),learning:vi.fn(),generate:vi.fn(),source:vi.fn(),comparisons:vi.fn(),compare:vi.fn(),preview:vi.fn(),revise:vi.fn(),prefs:vi.fn(),patchNode:vi.fn(),patchLearning:vi.fn()}));
vi.mock('../api/projects',()=>({getProject:vi.fn(async()=>project)}));
vi.mock('../api/client',()=>({apiGet:vi.fn(async()=>({project,papers:[],records:[],sessions:[]})),apiPost:vi.fn()}));
vi.mock('../api/knowledge',async()=>{const actual=await vi.importActual<typeof import('../api/knowledge')>('../api/knowledge');return {...actual,listKnowledgeSources:api.sources,getKnowledgeGraph:api.graph,getKnowledgeNode:api.node,getNodeLearning:api.learning,generateNodeLearning:api.generate,getKnowledgeSource:api.source,listKnowledgeComparisons:api.comparisons,compareKnowledgeSources:api.compare,previewKnowledgeComparison:api.preview,reviseKnowledgeComparison:api.revise,saveKnowledgePreferences:api.prefs,patchKnowledgeNode:api.patchNode,patchNodeLearning:api.patchLearning}});
vi.mock('../components/knowledge/KnowledgePractice',()=>({default:({nodeId,onBack}:{nodeId?:string;onBack:()=>void})=><section aria-label="节点动态练习"><p>练习绑定节点：{nodeId}</p><button onClick={onBack}>返回原位置</button></section>}));
vi.mock('../components/workspace/PdfReader',()=>({default:({initialPage,resource,targetPage,onPageChange}:{initialPage:number;resource:{url:string};targetPage?:number;onPageChange?:(page:number)=>void})=><><div data-testid="source-pdf">{initialPage} {resource.url}</div><output data-testid="target-page">{targetPage}</output><button onClick={()=>onPageChange?.(6)}>模拟连续滚动到第六页</button></>}));
vi.mock('../components/workbench/ProjectWorkbench',()=>({default:()=>null}));
const node:KnowledgeNode={id:'n1',project_id:'project-1',source_id:'s1',kind:'formula',label:'状态条件门控',summary:'有界消息通过门控调节。',parent_id:'root',origin:'source',research_status:'implemented',version:1,hidden:false,source_missing:false,evidence_ids:['e1'],metadata:{latex:'s=\\sigma(z)'}};
const source=(id:string):KnowledgeSource=>({id,project_id:'project-1',asset_id:id,version:'sha256:abc',title:'论文 '+id,filename:id+'.pdf',kind:'paper',media_type:'application/pdf',removed:false,created_at:'2026-10-29'});
const evidence={id:'e1',source_id:'s1',source_title:'论文 s1',block_id:'b1',quote:'State conditioned gates.',locator:{page:4,bbox:[10,20,40,50]},source_version:'sha256:abc',origin:'source'};
const basic={id:'a1',node_id:'n1',node_version:1,status:'basic',stale:false,cached:false,sections:{overview:'基础解释',definition:'原文定义',derivation:'',prerequisites:'',implementation:'',limitations:''},evidence:[evidence],resources:[],demos:['gating'],usage:{},errors:[]};
function Location(){return <output data-testid="location">{useLocation().search}</output>}
type ButtonQueries=Pick<ReturnType<typeof within>,'queryByText'|'queryByLabelText'|'getByRole'>;
function action(queries:ButtonQueries,name:string){const element=queries.queryByLabelText(name,{selector:'button'})||queries.queryByText(name,{selector:'button,button>span'})?.closest('button')||queries.getByRole('button',{name});expect(element).toBeVisible();return element;}
async function findAction(queries:ButtonQueries,name:string){return waitFor(()=>{const element=queries.queryByLabelText(name,{selector:'button'})||queries.queryByText(name,{selector:'button,button>span'})?.closest('button');if(!element)throw new Error('等待按钮：'+name);expect(element).toBeVisible();return element;});}
function show(query=''){return render(<MemoryRouter initialEntries={['/research/project-1'+query]}><Routes><Route path="/research/:projectId" element={<><KnowledgeWorkbench projectId="project-1"/><Location/></>}/></Routes></MemoryRouter>)}
beforeEach(()=>{localStorage.clear();vi.clearAllMocks();api.sources.mockResolvedValue({items:['s1','s2','s3','s4'].map(source),preferences:{mode:'research',view:null},model:{configured:true,enabled:true}});api.graph.mockResolvedValue({nodes:[node],edges:[],total_nodes:1,total_edges:0,truncated:false});api.node.mockResolvedValue({node,neighbors:[],edges:[],evidence:[evidence],prerequisites:[],resources:[],demos:['gating']});api.learning.mockResolvedValue(basic);api.generate.mockResolvedValue({...basic,status:'ready',sections:{...basic.sections,derivation:'已保存推导'}});api.source.mockResolvedValue({...source('s1'),blocks:[]});api.comparisons.mockResolvedValue({items:[]});api.preview.mockImplementation(async(_project:string,ids:string[])=>({id:'preview',source_ids:ids,title:'基础比较',status:'basic',stale:false,cached:true,usage:{},errors:[],rows:[],evidence:[]}));api.prefs.mockResolvedValue({mode:'research',view:'graph'})});

test('four-source workspace opens the whole graph and node learning never calls a model on page load',async()=>{
 show();const nodeButton=await screen.findByLabelText('公式：状态条件门控');expect(nodeButton).toHaveAttribute('role','button');expect(nodeButton).toBeVisible();expect(api.graph).toHaveBeenLastCalledWith('project-1',expect.objectContaining({source_id:undefined}),expect.any(AbortSignal));fireEvent.click(nodeButton);const inspector=within(await screen.findByLabelText('知识节点详情',{selector:'aside'}));fireEvent.click(await findAction(inspector,'深入学习'));await screen.findByText('基础解释');expect(api.generate).not.toHaveBeenCalled();const heading=within(screen.getByText('状态条件门控',{selector:'h2'}).closest('header')!);fireEvent.click(action(heading,'准备深入讲解'));await screen.findByText('已保存推导');expect(api.generate).toHaveBeenCalledTimes(1);expect(screen.getByTestId('location').textContent).toContain('view=learning');
});
// These two multi-view flows mount Ant Design repeatedly in JSDOM. Their timing
// is not a product performance benchmark; actual browser timings are validated separately.
test('comparison to learning and source evidence retain a return path and exact source page',async()=>{
 const comparison={id:'c1',source_ids:['s1','s2'],title:'协调机制比较',status:'ready',stale:false,cached:true,usage:{},errors:[],evidence:[evidence],rows:[{dimension:'信息路径',compatibility:'定性对照',values:[{source_id:'s1',text:'状态条件',node_ids:['n1'],evidence_ids:['e1'],origin:'source'},{source_id:'s2',text:'共享表示',node_ids:[],evidence_ids:[],origin:'source'}]}]};api.comparisons.mockResolvedValue({items:[comparison]});api.preview.mockResolvedValue(comparison);show('?view=compare&comparison=c1');fireEvent.click(await findAction(screen,'展开相关知识'));await screen.findByText('基础解释');fireEvent.click(action(screen,'论文 s1 第 4 页'));await waitFor(()=>expect(screen.getByTestId('source-pdf').textContent).toContain('4 /api/projects/project-1/sources/s1/file'));expect(screen.getByTestId('location').textContent).toContain('block=b1');fireEvent.click(action(screen,'返回原位置'));await screen.findByText('基础解释');
},30000);
test('report reader uses document blocks and preserves formula content without inventing PDF pages',async()=>{
 api.source.mockResolvedValue({...source('report'),kind:'report',filename:'study.docx',media_type:'application/vnd.openxmlformats-officedocument.wordprocessingml.document',blocks:[{id:'formula',ordinal:7,kind:'formula',heading:'门控公式',text:'s=sigmoid(z)',page:null,metadata:{latex:'s=\\sigma(z)'}}]});render(<SourceReader projectId="project-1" sourceId="report"/>);expect(await screen.findByRole('heading',{name:'门控公式'})).toBeTruthy();expect(screen.queryByTestId('source-pdf')).toBeNull();expect(document.querySelector('.katex')).toBeTruthy();expect(screen.queryByText('第 8 页')).toBeNull();
});
test('gating demo updates real residual calculations when message changes',()=>{
 render(<KnowledgeDemos ids={['gating']}/>);expect(screen.getByText(/外置门控残差：0.04918/)).toBeTruthy();fireEvent.change(screen.getByRole('slider',{name:'消息 m'}),{target:{value:'0'}});expect(screen.getByText('外置门控残差：0.00000')).toBeTruthy();expect(screen.getByText('∂δ₂/∂z：0.000000')).toBeTruthy();
});

test('selected report block offers its own linked knowledge without per-block footers',async()=>{
 const openNode=vi.fn(),openLearning=vi.fn();api.source.mockResolvedValue({...source('report'),kind:'report',filename:'study.docx',media_type:'application/vnd.openxmlformats-officedocument.wordprocessingml.document',blocks:[{id:'b1',ordinal:0,kind:'text',heading:'方法结构',text:'共享表示',page:null,metadata:{}},{id:'b2',ordinal:1,kind:'text',heading:'门控设计',text:'外置门控',page:null,metadata:{}}],knowledge_nodes:[{id:'n1',label:'共享表示',kind:'module',block_ids:['b1']},{id:'n2',label:'门控',kind:'concept',block_ids:['b2']}]});
 render(<SourceReader projectId="project-1" sourceId="report" onNode={openNode} onLearn={openLearning}/>);await screen.findByRole('heading',{name:'门控设计'});fireEvent.click(screen.getByRole('heading',{name:'门控设计'}));expect(screen.getAllByRole('button',{name:'查看关联知识'})).toHaveLength(1);fireEvent.click(action(screen,'查看关联知识'));expect(openNode).toHaveBeenCalledWith('n2',{block:'b2',page:undefined});fireEvent.click(action(screen,'深入学习此处'));expect(openLearning).toHaveBeenCalledWith('n2',{block:'b2',page:undefined});
});

test('source to learning returns to its selected block and PDF evidence target remains stable while scrolling',async()=>{
 api.source.mockResolvedValue({...source('s1'),blocks:[{id:'b1',ordinal:0,kind:'text',heading:'Method',text:'Gate formula',page:4,bbox:[10,20,40,50],metadata:{}}],knowledge_nodes:[{id:'n1',label:'状态条件门控',kind:'formula',block_ids:['b1']}]});
 show('?view=reading&source=s1&page=4&targetPage=4&block=b1&bbox=10,20,40,50');await findAction(screen,'深入学习此处');fireEvent.click(action(screen,'深入学习此处'));await screen.findByText('基础解释');fireEvent.click(action(screen,'返回原位置'));await screen.findByTestId('source-pdf');expect(screen.getByTestId('location').textContent).toContain('block=b1');fireEvent.click(action(screen,'模拟连续滚动到第六页'));await waitFor(()=>expect(screen.getByTestId('source-pdf').textContent).toContain('6 /api/'));expect(screen.getByTestId('target-page').textContent).toBe('4');
},30000);

test('opening a space restores the graph scope while explicit reading URLs retain their saved page',async()=>{
 localStorage.setItem('paperstride:knowledge-scene:project-1',JSON.stringify({view:'reading',source:'s2',page:'6',quote:'never persist source text',secret:'never restore'}));
 const mounted=show();await screen.findByLabelText('公式：状态条件门控');expect(api.source).not.toHaveBeenCalled();await waitFor(()=>expect(screen.getByTestId('location').textContent).toBe('?view=graph&source=s2'));expect(screen.queryByRole('tablist')).toBeNull();const stored=JSON.parse(localStorage.getItem('paperstride:knowledge-scene:project-1')!);expect(stored.secret).toBeUndefined();mounted.unmount();
 api.source.mockClear();show('?view=reading&source=s1&page=6');await screen.findByTestId('source-pdf');expect(api.source).toHaveBeenCalledWith('project-1','s1',expect.any(AbortSignal));expect(screen.getByTestId('location').textContent).toBe('?view=reading&source=s1&page=6');
});

test('repository viewer names the frozen snapshot and shows file path plus commit',async()=>{
 api.source.mockResolvedValue({...source('repo'),kind:'code',filename:'method.repo.json',media_type:'application/json',blocks:[{id:'code',ordinal:0,kind:'code',heading:'Gate.forward',text:'def forward(x):\n    return x',page:null,metadata:{path:'models/gate.py',commit:'1234567890abcdef',symbol:'Gate.forward',start_line:20,end_line:21}}]});render(<SourceReader projectId="project-1" sourceId="repo"/>);expect(await screen.findByRole('link',{name:'下载仓库快照'})).toBeTruthy();expect(screen.getByText('models/gate.py')).toBeTruthy();expect(screen.getByText('版本 12345678')).toBeTruthy();
});

test('formula correction submits versioned LaTeX for the current space without rewriting source text',async()=>{
 api.patchNode.mockResolvedValue({...node,version:2,origin:'user'});show('?view=graph&node=n1&source=s1');const inspector=within(await screen.findByLabelText('知识节点详情',{selector:'aside'}));fireEvent.click(await findAction(inspector,'修订内容'));const field=inspector.getByLabelText('公式 LaTeX');fireEvent.change(field,{target:{value:'\\delta=c\\sigma(z)\\tanh(m)'}});fireEvent.click(action(inspector,'保存修订'));await waitFor(()=>expect(api.patchNode).toHaveBeenCalledWith('project-1','n1',expect.objectContaining({expected_version:1,latex:'\\delta=c\\sigma(z)\\tanh(m)'})));expect(api.generate).not.toHaveBeenCalled();
});

test('method comparison explicitly focuses D2 within the chosen report and omits deselected sources',async()=>{
 const d2={...node,id:'d2',source_id:'s2',kind:'method',label:'D2 状态条件外置门控',metadata:{semantic:true}};
 api.graph.mockImplementation(async(_project:string,query:{source_id?:string})=>({nodes:query.source_id==='s2'?[d2]:[{...node,id:'paper-method',kind:'method'}],edges:[],total_nodes:1,total_edges:0,truncated:false}));
 const result={id:'focused',source_ids:['s1','s2'],title:'D2 与相关论文',focus_node_ids:['d2'],focus_nodes:[{id:'d2',source_id:'s2',label:d2.label}],rows:[],evidence:[],status:'ready',cached:false,stale:false,usage:{},errors:[]};api.compare.mockResolvedValue(result);
 api.preview.mockImplementation(async(_pid:string,ids:string[],focusIds:string[])=>({...result,id:'preview',source_ids:ids,title:'基础比较',status:'basic',focus_node_ids:focusIds,focus_nodes:focusIds.includes('d2')?result.focus_nodes:[]}));
 render(<KnowledgeComparison projectId="project-1" sources={[source('s1'),source('s2')]} onComparison={vi.fn()} onNode={vi.fn()} onEvidence={vi.fn()}/>);
 fireEvent.click(screen.getByText('调整资料、聚焦方法与比较关注点'));const select=await screen.findByLabelText('聚焦方法：论文 s2');await waitFor(()=>expect(select).not.toBeDisabled());fireEvent.change(select,{target:{value:'d2'}});fireEvent.click(action(screen,'深入比较所选资料'));await screen.findByText('D2 与相关论文');expect(api.compare).toHaveBeenCalledWith('project-1',['s1','s2'],false,expect.any(AbortSignal),['d2'],expect.any(Array));expect(screen.getByText('论文 s2 / '+d2.label)).toBeTruthy();
 fireEvent.click(screen.getByLabelText(/论文 s2/,{selector:'input'}));expect(screen.queryByLabelText('聚焦方法：论文 s2')).toBeNull();fireEvent.click(screen.getByLabelText(/论文 s2/,{selector:'input'}));expect((await screen.findByLabelText('聚焦方法：论文 s2')) as HTMLSelectElement).toHaveValue('');
});

test('saved comparison restores its exact focused method without generating content',async()=>{
 const saved={id:'saved',source_ids:['s1','s2'],title:'历史 D2 比较',focus_node_ids:['d2'],focus_nodes:[{id:'d2',source_id:'s2',label:'D2'}],rows:[],evidence:[],status:'ready',stale:false,cached:true,usage:{},errors:[]};api.comparisons.mockResolvedValue({items:[saved]});api.preview.mockResolvedValue(saved);
 render(<KnowledgeComparison projectId="project-1" sources={[source('s1'),source('s2')]} comparisonId="saved" onComparison={vi.fn()} onNode={vi.fn()} onEvidence={vi.fn()}/>);await screen.findByText('历史 D2 比较');fireEvent.click(screen.getByText('调整资料、聚焦方法与比较关注点'));expect(screen.getByLabelText('聚焦方法：论文 s2')).toHaveValue('d2');expect(api.compare).not.toHaveBeenCalled();
});

test('learning correction and section hide use successive saved revisions without model calls',async()=>{
 api.learning.mockResolvedValue({...basic,revision:3});api.patchLearning.mockResolvedValueOnce({...basic,revision:4,origin:'user',user_edited_sections:['overview'],hidden_sections:[],sections:{...basic.sections,overview:'我的门控理解与条件'}}).mockResolvedValueOnce({...basic,revision:5,origin:'user',user_edited_sections:['overview'],hidden_sections:['overview'],sections:{...basic.sections,overview:'我的门控理解与条件'}}).mockResolvedValueOnce({...basic,revision:6,origin:'user',user_edited_sections:['overview'],hidden_sections:[],sections:{...basic.sections,overview:'我的门控理解与条件'}});
 render(<KnowledgeLearning projectId="project-1" nodeId="n1" onNode={vi.fn()} onEvidence={vi.fn()} onBack={vi.fn()}/>);await screen.findByText('基础解释');const section=within(screen.getByText('直观理解',{selector:'h3'}).closest('section')!);fireEvent.click(action(section,'修订讲解：直观理解'));fireEvent.change(section.getByLabelText('直观理解内容'),{target:{value:'我的门控理解与条件'}});fireEvent.click(action(section,'保存讲解修订'));await section.findByText('我的门控理解与条件');expect(api.patchLearning).toHaveBeenNthCalledWith(1,'project-1','n1',{expected_revision:3,sections:{overview:'我的门控理解与条件'}},expect.any(AbortSignal));fireEvent.click(action(section,'隐藏讲解：直观理解'));await waitFor(()=>expect(screen.queryByText('直观理解',{selector:'h3'})).toBeNull());expect(screen.queryByText('我的门控理解与条件')).toBeNull();expect(api.patchLearning).toHaveBeenNthCalledWith(2,'project-1','n1',{expected_revision:4,hidden_sections:['overview']},expect.any(AbortSignal));fireEvent.click(screen.getByText('管理学习内容',{selector:'summary'}));fireEvent.click(action(screen,'恢复讲解：直观理解'));await screen.findByText('我的门控理解与条件');expect(api.patchLearning).toHaveBeenNthCalledWith(3,'project-1','n1',{expected_revision:5,hidden_sections:[]},expect.any(AbortSignal));expect(api.generate).not.toHaveBeenCalled();
});

test('learning revision conflict preserves the draft and explains how to read the latest saved version',async()=>{
 api.learning.mockResolvedValue({...basic,revision:2});api.patchLearning.mockRejectedValueOnce(new Error('讲解已更新，请重新读取最新版本'));
 render(<KnowledgeLearning projectId="project-1" nodeId="n1" onNode={vi.fn()} onEvidence={vi.fn()} onBack={vi.fn()}/>);await screen.findByText('基础解释');const section=within(screen.getByText('公式与推导',{selector:'h3'}).closest('section')!);fireEvent.click(action(section,'修订讲解：公式与推导'));fireEvent.change(section.getByLabelText('公式与推导内容'),{target:{value:'保存前的推导草稿'}});fireEvent.click(action(section,'保存讲解修订'));await screen.findByText('讲解已更新，请重新读取最新版本');expect(section.getByLabelText('公式与推导内容')).toHaveValue('保存前的推导草稿');expect(action(screen,'重新读取已保存版本')).toBeTruthy();expect(api.patchLearning).toHaveBeenCalledTimes(1);
});

test('a material click updates the real workspace URL once and opens its methods without a competing clear navigation',async()=>{
 const paper={...node,id:'paper-root',kind:'paper',parent_id:null,label:'Research paper A'};
 const method={...node,id:'method-root',kind:'method',parent_id:'paper-root',label:'Main policy'};
 const module={...node,id:'module-root',kind:'module',parent_id:'method-root',label:'State message'};
 api.graph.mockResolvedValue({nodes:[paper,method,module],edges:[],total_nodes:3,total_edges:0,truncated:false});
 show('?view=graph');fireEvent.click(await screen.findByLabelText('论文：Research paper A'));
 await waitFor(()=>expect(screen.getByTestId('location').textContent).toContain('source=s1'));
 expect(screen.getByLabelText('方法：Main policy')).toBeVisible();expect(screen.getByLabelText('模块：State message')).toBeVisible();
 fireEvent.click(screen.getByRole('button',{name:'研究空间'}));
 await waitFor(()=>expect(screen.getByTestId('location').textContent).not.toContain('source='));
});

test('a focused graph keeps nodes distinct and inside a bounded canvas',()=>{
 const nodes=[{...node,id:'paper',kind:'paper'},{...node,id:'method',kind:'method',parent_id:'paper'},{...node,id:'problem',kind:'problem',parent_id:'method'},{...node,id:'formula',kind:'formula',parent_id:'problem'}];
 const result=layoutGraph({nodes,edges:[],total_nodes:4,total_edges:0,truncated:false});
 expect(result.lanes.length).toBeLessThanOrEqual(3);expect(result.height).toBeLessThan(800);const points=[...result.points.values()];for(const [index,p] of points.entries()){expect(p.x+NODE_WIDTH).toBeLessThan(result.width);expect(p.y+NODE_HEIGHT).toBeLessThan(result.height);for(const other of points.slice(index+1))expect(p.x+NODE_WIDTH<=other.x||other.x+NODE_WIDTH<=p.x||p.y+NODE_HEIGHT<=other.y||other.y+NODE_HEIGHT<=p.y).toBe(true)}
});

test('node practice expands from the graph and returns to its selected node and canvas position',async()=>{
 show();fireEvent.click(await screen.findByLabelText('公式：状态条件门控'));const inspector=within(await screen.findByLabelText('知识节点详情',{selector:'aside'}));await findAction(inspector,'动态练习');const canvas=screen.getByLabelText('研究知识图谱画布');canvas.scrollTop=220;canvas.scrollLeft=50;fireEvent.scroll(canvas);fireEvent.click(action(inspector,'动态练习'));await screen.findByText('练习绑定节点：n1');expect(screen.getByTestId('location').textContent).toContain('view=practice');expect(screen.getByTestId('location').textContent).toContain('graphFrom=');fireEvent.click(action(screen,'返回研究图谱'));await screen.findByLabelText('公式：状态条件门控');await waitFor(()=>expect(screen.getByLabelText('研究知识图谱画布').scrollTop).toBe(220));expect(screen.getByTestId('location').textContent).toContain('node=n1');expect(api.prefs).not.toHaveBeenCalled();expect(api.generate).not.toHaveBeenCalled();
},30000);

test('graph failure is visible and recoverable rather than leaving an empty canvas',async()=>{
 api.graph.mockRejectedValueOnce(new Error('HTTP 503: graph unavailable')).mockResolvedValue({nodes:[node],edges:[],total_nodes:1,total_edges:0,truncated:false});
 render(<KnowledgeGraphView projectId="project-1" revision={0} onUpdated={vi.fn()} onNode={vi.fn()} onLearn={vi.fn()} onEvidence={vi.fn()} onSource={vi.fn()}/>);await screen.findByText('图谱暂时无法加载');expect(screen.getByText('HTTP 503: graph unavailable')).toBeTruthy();fireEvent.click(screen.getByLabelText('重试加载图谱'));expect(await screen.findByLabelText('公式：状态条件门控')).toBeTruthy();
});
