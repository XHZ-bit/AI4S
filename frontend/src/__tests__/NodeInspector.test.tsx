import {fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {beforeEach,expect,test,vi} from 'vitest';
import {NodeInspector,EdgeEditor} from '../components/knowledge/NodeInspector';
import type {KnowledgeEdge,KnowledgeEvidence,KnowledgeNode,KnowledgeSource,NodeDetail,NodeStudyGuide} from '../api/knowledge';

const api=vi.hoisted(()=>({node:vi.fn(),patch:vi.fn(),resources:vi.fn(),ask:vi.fn(),edge:vi.fn()}));
vi.mock('../api/unifiedGraph',()=>({getUnifiedEdge:api.edge}));
vi.mock('../api/knowledge',()=>({getKnowledgeNode:api.node,patchKnowledgeNode:api.patch,mergeKnowledgeNodes:vi.fn(),splitKnowledgeNode:vi.fn(),patchKnowledgeEdge:vi.fn(),nodeKindLabels:{concept:'概念',formula:'公式'},originLabels:{source:'原文明示'},researchStatusLabels:{unspecified:'未说明'}}));
vi.mock('../api/knowledgeExperience',()=>({getNodeResources:api.resources,addNodeResource:vi.fn(),askKnowledgeNode:api.ask}));
vi.mock('../components/knowledge/KnowledgeSources',()=>({EvidenceList:({items,onOpen}:{items:KnowledgeEvidence[];onOpen:(e:KnowledgeEvidence)=>void})=><>{items.map(e=><button key={e.id} onClick={()=>onOpen(e)}>{e.source_title} 第 {e.locator.page} 页</button>)}</>}));
vi.mock('../components/knowledge/LearningProgress',()=>({default:({onNode}:{onNode:(id:string)=>void})=><button onClick={()=>onNode('foundation')}>复习链式法则</button>}));
vi.mock('../components/knowledge/NodeMaterials',()=>({default:()=>null}));
vi.mock('../components/knowledge/NodeNoteSummary',()=>({default:()=>null}));
vi.mock('@ant-design/icons',()=>({CloseOutlined:()=>null}));
vi.mock('antd',()=>{
 const Input=Object.assign((props:any)=><input {...props}/>,{TextArea:({autoSize:_,...props}:any)=><textarea {...props}/>});
 return {Input,Button:({children,type:_,size:__,icon,loading:___,...props}:any)=><button {...props}>{icon}{children}</button>,Alert:({message,description,action}:any)=><div role="alert">{message}{description}{action}</div>,Spin:()=>null,Space:({children}:any)=><div>{children}</div>,Tag:({children}:any)=><span>{children}</span>,Select:({options,onChange,showSearch:_,optionFilterProp:__,...props}:any)=><select {...props} onChange={event=>onChange?.(event.target.value)}>{options.map((o:any)=><option key={o.value} value={o.value}>{o.label}</option>)}</select>};
});

const node:KnowledgeNode={id:'n',project_id:'p',source_id:'s',kind:'concept',label:'反向传播',summary:'利用链式法则逐层计算梯度。',parent_id:null,origin:'source',research_status:'unspecified',version:1,hidden:false,source_missing:false,evidence_ids:['e'],metadata:{}};
const foundation={...node,id:'foundation',label:'链式法则'};
const evidence:KnowledgeEvidence={id:'e',source_id:'s',source_title:'原始论文',block_id:'b',quote:'Saved source quote',locator:{page:7},source_version:'v1',origin:'source'};
const detail:NodeDetail={node,neighbors:[foundation],prerequisites:[foundation],edges:[],evidence:[evidence],resources:[{title:'官方教程',url:'https://example.org/tutorial',type:'tutorial'}],demos:[]};
const callbacks={onNode:vi.fn(),onLearn:vi.fn(),onEvidence:vi.fn(),onSource:vi.fn(),onUpdated:vi.fn(),onPractice:vi.fn()};
function show(){return render(<NodeInspector projectId="p" nodeId="n" allNodes={[node,foundation]} {...callbacks}/>)}
beforeEach(()=>{vi.clearAllMocks();api.node.mockResolvedValue(detail);api.resources.mockResolvedValue({items:[]});api.patch.mockResolvedValue({...node,version:2});});

test('node details connect prerequisite learning and practice without triggering model requests',async()=>{
 show();await screen.findByRole('heading',{name:'反向传播'});
 const foundations=screen.getByRole('heading',{name:'先补充基础'}).closest('section')!;
 fireEvent.click(within(foundations).getByRole('button',{name:'链式法则'}));
 expect(callbacks.onNode).toHaveBeenCalledWith(foundation);
 fireEvent.click(screen.getByRole('button',{name:'深入学习'}));
 expect(callbacks.onLearn).toHaveBeenCalledWith('n');
 fireEvent.click(screen.getByRole('button',{name:'动态练习'}));
 expect(callbacks.onPractice).toHaveBeenCalledWith('n');
 expect(api.ask).not.toHaveBeenCalled();expect(api.resources).not.toHaveBeenCalled();
});

test('keyboard tabs expose exact source evidence and saved resource links',async()=>{
 show();await screen.findByRole('heading',{name:'反向传播'});
 fireEvent.keyDown(screen.getByRole('tab',{name:'知识与学习'}),{key:'ArrowRight'});
 expect(screen.getByRole('tab',{name:'原文与资料'})).toHaveFocus();
 fireEvent.click(screen.getByRole('button',{name:'原始论文 第 7 页'}));
 expect(callbacks.onEvidence).toHaveBeenCalledWith(evidence);
 fireEvent.click(screen.getByText('学习资料 · 1'));
 expect(await screen.findByRole('link',{name:'官方教程'})).toHaveAttribute('href','https://example.org/tutorial');
 await waitFor(()=>expect(api.resources).toHaveBeenCalledTimes(1));
});

test('switching tabs preserves a learner question and record recommendations navigate to a real node',async()=>{
 show();await screen.findByRole('heading',{name:'反向传播'});
 fireEvent.click(screen.getByRole('tab',{name:'笔记与提问'}));
 fireEvent.change(screen.getByLabelText('节点问题'),{target:{value:'为什么局部梯度可以相乘？'}});
 fireEvent.click(screen.getByRole('tab',{name:'知识与学习'}));
 fireEvent.click(screen.getByRole('tab',{name:'笔记与提问'}));
 expect(screen.getByLabelText('节点问题')).toHaveValue('为什么局部梯度可以相乘？');
 fireEvent.click(screen.getByRole('button',{name:'复习链式法则'}));
 expect(callbacks.onNode).toHaveBeenCalledWith(foundation);
 expect(api.ask).not.toHaveBeenCalled();
});

test('missing descriptions and sources give a usable learning path without a broken original link',async()=>{
 api.node.mockResolvedValue({...detail,node:{...node,summary:'',source_id:'',source_missing:true},prerequisites:[],evidence:[]});
 show();await screen.findByRole('heading',{name:'反向传播'});
 expect(screen.getByText(/当前节点还没有独立说明/)).toBeVisible();
 fireEvent.click(screen.getByRole('tab',{name:'原文与资料'}));
 expect(screen.getByRole('button',{name:'阅读原文'})).toBeDisabled();
 expect(screen.getByRole('button',{name:'深入学习'})).toBeEnabled();
});

test('relation details lead with endpoints and stale evidence and keep editing secondary',async()=>{
 const edge:KnowledgeEdge={id:'relationship',project_id:'p',source_id:'s',source:'foundation',target:'n',kind:'PREREQUISITE_OF',label:'是前置知识',explanation:'根据论文中的定义理解链式法则的用途。',origin:'source',version:1,hidden:false,source_missing:false,evidence_ids:['e'],metadata:{},quality_status:'human_verified'};
 api.edge.mockResolvedValue({edge,evidence:[{...evidence,source_changed:true}]});
 const onEvidence=vi.fn();
 render(<EdgeEditor projectId="p" edge={edge} nodes={[node,foundation]} onEvidence={onEvidence} onClose={vi.fn()} onSaved={vi.fn()}/>);
 expect(screen.getByText('链式法则')).toBeVisible();expect(screen.getByText('反向传播')).toBeVisible();
 await screen.findByText('依据变化，待复核');
 expect(screen.getByText('修订与核查记录').closest('details')).not.toHaveAttribute('open');
 fireEvent.click(screen.getByRole('button',{name:'原始论文 第 7 页'}));
 expect(onEvidence).toHaveBeenCalledWith(expect.objectContaining({id:'e',source_changed:true}));
 fireEvent.click(screen.getByText('修订与核查记录'));
 expect(screen.getByRole('textbox',{name:'关系名称'})).toBeVisible();
});

test('same-name concepts remain separate candidates with both source identities',async()=>{
 const candidate={...node,id:'same-name',source_id:'other'};
 const onCompare=vi.fn();
 const sources:KnowledgeSource[]=['s','other'].map((id,index)=>({id,title:index?'另一篇论文':'当前论文',project_id:'p',asset_id:id,version:'v1',filename:id+'.pdf',kind:'paper',media_type:'application/pdf',removed:false,created_at:'2026-11-16'}));
 render(<NodeInspector projectId="p" nodeId="n" allNodes={[node,foundation,candidate]} sources={sources} {...callbacks} onCompare={onCompare}/>);
 await screen.findByRole('heading',{name:'跨资料同名候选'});
 expect(screen.getByText('当前出处 · 当前论文')).toBeVisible();
 expect(screen.getByText('候选出处 · 另一篇论文')).toBeVisible();
 expect(screen.getByText('待核对')).toBeVisible();
 fireEvent.click(screen.getByRole('button',{name:'查看候选节点'}));
 expect(callbacks.onNode).toHaveBeenCalledWith(candidate);
 fireEvent.click(screen.getByRole('button',{name:'比较相关资料'}));
 expect(onCompare).toHaveBeenCalledWith(node);
 expect(api.patch).not.toHaveBeenCalled();
});

test('the first view combines an authored guide with the actual source description and a readable direct excerpt',async()=>{
 const guide:NodeStudyGuide={topic:'backprop',title:'反向传播',version:'1',origin:'authored_teaching',overview:'把最终误差沿计算步骤向前分配，得到每个参数的影响。',why_it_matters:'用这些梯度更新参数，减少给定损失。',flow:[],example:{title:'一个教学算例',body:'给定局部导数2和3，链式法则得到6。'},key_points:['沿真实计算图逐步求导。','局部导数与前后依赖相乘。'],common_confusions:[],questions:[],demo_ids:[]};
 api.node.mockResolvedValue({...detail,study_guide:guide});
 show();const panel=await screen.findByRole('tabpanel',{name:'知识与学习'});
 expect(within(panel).getByRole('region',{name:'节点基础讲解'})).toBeVisible();
 expect(within(panel).getByText(guide.overview)).toBeVisible();
 expect(within(panel).getByRole('heading',{name:'资料中的描述'})).toBeVisible();
 expect(within(panel.querySelector('.kw-node-overview')!).getByText(node.summary)).toBeVisible();
 const quote=within(panel).getByRole('region',{name:'当前知识的原文片段'});
 expect(within(quote).getByText(evidence.quote)).toBeVisible();
 expect(within(quote).getByText('原始论文 · 第 7 页')).toBeVisible();
 expect(within(panel).getByText('看一个例子').closest('details')).not.toHaveAttribute('open');
 expect(api.ask).not.toHaveBeenCalled();
});

test('a node without a teaching guide shows directed graph context and chooses its own evidence before associated sources',async()=>{
 const method={...node,id:'method',label:'梯度下降'};
 const other:KnowledgeEvidence={...evidence,id:'other',source_id:'other-source',source_title:'关联论文',quote:'This belongs to a different concept.'};
 const into:KnowledgeEdge={id:'in',project_id:'p',source_id:'s',source:foundation.id,target:node.id,kind:'PREREQUISITE_OF',label:'是前置知识',explanation:'逐层求导需要先知道复合函数怎样求导。',origin:'source',version:1,hidden:false,source_missing:false,evidence_ids:['e'],metadata:{}};
 const out:KnowledgeEdge={...into,id:'out',source:node.id,target:method.id,kind:'USES',label:'提供梯度',explanation:'求出的参数梯度交给更新步骤。'};
 api.node.mockResolvedValue({...detail,neighbors:[foundation,method],evidence:[other,evidence],edges:[out,into]});
 render(<NodeInspector projectId="p" nodeId="n" allNodes={[node,foundation,method]} {...callbacks}/>);
 const panel=await screen.findByRole('tabpanel',{name:'知识与学习'});
 const roles=within(panel).getByRole('region',{name:'在知识图谱中的作用'});
 const statements=roles.querySelectorAll('.kw-node-role-statement');
 expect(statements[0]).toHaveTextContent(/链式法则.*是前置知识.*反向传播/);
 expect(statements[1]).toHaveTextContent(/反向传播.*提供梯度.*梯度下降/);
 expect(within(roles).getByText(into.explanation)).toBeVisible();
 expect(within(roles).getByText(out.explanation)).toBeVisible();
 fireEvent.click(within(roles).getByRole('button',{name:'梯度下降'}));
 expect(callbacks.onNode).toHaveBeenCalledWith(method);
 fireEvent.click(within(panel).getByRole('button',{name:'查看原文依据'}));
 expect(callbacks.onEvidence).toHaveBeenCalledWith(evidence);
 expect(within(panel).queryByText(other.quote)).toBeNull();
 fireEvent.click(screen.getByRole('tab',{name:'原文与资料'}));
 const sources=screen.getByRole('tabpanel',{name:'原文与资料'});
 expect(within(sources).getByRole('button',{name:'原始论文 第 7 页'})).toBeVisible();
 expect(within(sources).getByRole('button',{name:'关联论文 第 7 页',hidden:true})).not.toBeVisible();
 expect(api.edge).not.toHaveBeenCalled();expect(api.ask).not.toHaveBeenCalled();
});

test('associated or stale evidence is not presented as the current direct quote',async()=>{
 const associated={...evidence,id:'associated',source_id:'other',source_title:'其他来源',quote:'Only an associated quote.'};
 api.node.mockResolvedValue({...detail,evidence:[associated,{...evidence,source_changed:true}]});
 show();const panel=await screen.findByRole('tabpanel',{name:'知识与学习'});
 expect(within(panel).queryByRole('region',{name:'当前知识的原文片段'})).toBeNull();
 fireEvent.click(within(panel).getByRole('button',{name:'查看原文依据'}));
 expect(callbacks.onEvidence).not.toHaveBeenCalled();
 expect(callbacks.onSource).toHaveBeenCalledWith('s');
});

test('optional foundations expose two useful summaries and stale relations stay out of the role overview',async()=>{
 const supplements=[{...foundation,id:'basic1',label:'复合函数',summary:'前一个函数的输出作为后一个函数的输入。'},{...foundation,id:'basic2',label:'偏导数',summary:'固定其余变量，观察一个变量的局部变化。'},{...foundation,id:'basic3',label:'梯度向量',summary:'把各个偏导数排成一个向量。'}];
 const withdrawn:KnowledgeEdge={id:'withdrawn',project_id:'p',source_id:'s',source:foundation.id,target:node.id,kind:'PREREQUISITE_OF',label:'旧的前置关系',explanation:'已经撤回的说明',origin:'source',version:1,hidden:false,source_missing:false,evidence_ids:['e'],metadata:{},quality_status:'withdrawn'};
 api.node.mockResolvedValue({...detail,prerequisites:[],suggested_foundations:supplements,edges:[withdrawn]});
 show();const panel=await screen.findByRole('tabpanel',{name:'知识与学习'});
 const basics=within(panel).getByRole('region',{name:'可选基础补充'});
 expect(within(basics).getByText(supplements[0].summary)).toBeVisible();
 expect(within(basics).getByText(supplements[1].summary)).toBeVisible();
 expect(within(basics).getByRole('button',{name:'梯度向量',hidden:true})).not.toBeVisible();
 expect(within(panel).queryByText('暂无已核对的前置关系。')).toBeNull();
 expect(within(panel).queryByRole('region',{name:'在知识图谱中的作用'})).toBeNull();
 fireEvent.click(within(basics).getByRole('button',{name:'偏导数'}));
 expect(callbacks.onNode).toHaveBeenCalledWith(supplements[1]);
});

test('a long source preview stays bounded while original navigation retains the complete evidence',async()=>{
 const longEvidence={...evidence,quote:'完整原文片段。'.repeat(100)+'末尾仍保留在原始依据中。'};
 api.node.mockResolvedValue({...detail,evidence:[longEvidence]});
 show();const panel=await screen.findByRole('tabpanel',{name:'知识与学习'});
 const preview=within(panel).getByRole('region',{name:'当前知识的原文片段'}).querySelector('blockquote')!;
 expect(Array.from(preview.textContent||'').length).toBeLessThanOrEqual(450);
 expect(preview).toHaveTextContent('完整原文片段。');
 expect(preview).not.toHaveTextContent('末尾仍保留在原始依据中。');
 fireEvent.click(within(panel).getByRole('button',{name:'查看原文依据'}));
 expect(callbacks.onEvidence).toHaveBeenCalledWith(longEvidence);
 expect(longEvidence.quote).toContain('末尾仍保留在原始依据中。');
});
