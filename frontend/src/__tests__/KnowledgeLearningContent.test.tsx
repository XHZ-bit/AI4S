import {act,fireEvent,render,screen,within,waitFor} from '@testing-library/react';
import {StrictMode} from 'react';
import {beforeEach,expect,test,vi} from 'vitest';
import KnowledgeLearning,{LearningResources} from '../components/knowledge/KnowledgeLearning';
import KnowledgeDemos from '../components/knowledge/KnowledgeDemos';
import type {LearningArtifact,NodeDetail,NodeStudyGuide} from '../api/knowledge';

const api=vi.hoisted(()=>({node:vi.fn(),learning:vi.fn(),generate:vi.fn(),patch:vi.fn()}));
vi.mock('../api/knowledge',()=>({getKnowledgeNode:api.node,getNodeLearning:api.learning,generateNodeLearning:api.generate,patchNodeLearning:api.patch}));
vi.mock('../components/knowledge/KnowledgeGraph',()=>({NodeBadges:()=>null}));
vi.mock('../components/knowledge/LearningProgress',()=>({default:({children}:{children:React.ReactNode})=><>{children}</>}));
vi.mock('../components/knowledge/KnowledgeText',async()=>({...await vi.importActual<typeof import('../components/knowledge/KnowledgeText')>('../components/knowledge/KnowledgeText'),default:({text}:{text:string})=><p>{text}</p>,mathAwareText:(text:string)=>text}));
vi.mock('../components/knowledge/KnowledgeSources',()=>({EvidenceList:()=>null}));
vi.mock('antd',()=>({
 Alert:({message}:{message:string})=><div role="alert">{message}</div>,
 Button:({children,type:_,loading:__,size:___,...props}:React.ButtonHTMLAttributes<HTMLButtonElement>&{loading?:boolean;size?:string})=><button {...props}>{children}</button>,
 Input:{TextArea:({autoSize:_,...props}:React.TextareaHTMLAttributes<HTMLTextAreaElement>&{autoSize?:unknown})=><textarea {...props}/>},
 Space:({children}:{children:React.ReactNode})=><div>{children}</div>,Spin:()=>null,Tag:({children}:{children:React.ReactNode})=><span>{children}</span>,Select:()=>null,
}));

const detail:NodeDetail={node:{id:'n',project_id:'p',source_id:'s',kind:'module',label:'状态门控',summary:'根据当前观测调节消息强度。',parent_id:null,origin:'source',research_status:'unknown',version:1,hidden:false,source_missing:false,evidence_ids:[],metadata:{}},edges:[],neighbors:[],evidence:[],prerequisites:[],resources:[],demos:['unknown-demo']};
const basic:LearningArtifact={id:'a',node_id:'n',node_version:1,status:'basic',stale:false,cached:false,revision:1,sections:{overview:detail.node.summary,definition:'',derivation:'',prerequisites:'',implementation:'',limitations:'基础内容来自当前资料。深入讲解属于教学补充，需结合原文的条件和范围理解。'},evidence:[],resources:[],demos:[],usage:{},errors:[]};
const guide:NodeStudyGuide={topic:'self_attention',title:'自注意力',version:'node-guide-v1',origin:'authored_teaching',overview:'同一序列中的位置根据当前查询选择要参考的信息。',why_it_matters:'让每个词结合上下文形成表示。',flow:[{label:'输入',text:'同一序列的表示分别形成查询、键和值。'},{label:'处理',text:'对候选位置打分并计算权重。'},{label:'输出',text:'按权重组合值向量。'}],example:{title:'两个候选位置的教学例子',body:'权重0.75和0.25，值为2和6，加权结果为3。'},key_points:['查询、键和值来自同一序列。'],common_confusions:[{claim:'是否等于交叉注意力？',explanation:'交叉注意力的查询与键值来自不同序列。'}],questions:['如果某个位置被掩码，还能给它分配权重吗？'],demo_ids:[]};
beforeEach(()=>{sessionStorage.clear();vi.clearAllMocks();api.node.mockResolvedValue(detail);api.learning.mockResolvedValue(basic);api.patch.mockImplementation(async(_p,_n,body)=>({...basic,revision:2,user_edited_sections:Object.keys(body.sections||{}),sections:{...basic.sections,...body.sections}}));});
function show(autoPrepare=false){return render(<KnowledgeLearning autoPrepare={autoPrepare} projectId="p" nodeId="n" onNode={vi.fn()} onEvidence={vi.fn()} onBack={vi.fn()}/>)}

test('learning entry prepares once in StrictMode while the detailed foundation remains readable',async()=>{
 api.node.mockResolvedValue({...detail,study_guide:guide});
 let finish!:(value:LearningArtifact)=>void;api.generate.mockReturnValue(new Promise<LearningArtifact>(resolve=>{finish=resolve}));
 render(<StrictMode><KnowledgeLearning autoPrepare initialGoal="解释注意力计算" workspaceMode="explore" projectId="p" nodeId="n" onNode={vi.fn()} onEvidence={vi.fn()} onBack={vi.fn()}/></StrictMode>);
 expect(await screen.findByText(guide.example.body)).toBeVisible();
 await waitFor(()=>expect(api.generate).toHaveBeenCalledTimes(1));
 expect(api.generate).toHaveBeenCalledWith('p','n',false,expect.any(AbortSignal),{goal:'解释注意力计算',depth:'standard'});
 expect(screen.getByRole('button',{name:'停止等待'})).toBeVisible();
 await act(async()=>finish({...basic,status:'ready',sections:{...basic.sections,derivation:'首次进入自动准备的完整推导'}}));
 expect(await screen.findByText('首次进入自动准备的完整推导')).toBeVisible();expect(api.generate).toHaveBeenCalledTimes(1);
});

test('saved detailed or manually curated content never triggers entry generation',async()=>{
 api.learning.mockResolvedValue({...basic,status:'ready'});const saved=show(true);await screen.findByText(detail.node.summary);expect(api.generate).not.toHaveBeenCalled();saved.unmount();
 api.learning.mockResolvedValue({...basic,user_edited_sections:['overview'],hidden_sections:['definition']});show(true);await screen.findByText(detail.node.summary);expect(api.generate).not.toHaveBeenCalled();
});

test('a partial failed review remains readable and retries only when requested with the saved goal',async()=>{
 api.node.mockResolvedValue({...detail,study_guide:guide});
 api.learning.mockResolvedValue({...basic,status:'partial',goal:'给我公式推导',depth:'standard',errors:['讲解与原文的一致性检查未通过'],last_generation:{stage:'review',code:'review_rejected',message:'修正后的内容仍需核对，基础讲解已保留。',retryable:true,retained:'basic',review_count:3,issues:[{section:'derivation',category:'math',blocking:true,description:'缩放项需要核对'}]}});
 api.generate.mockResolvedValue({...basic,status:'ready',goal:'给我公式推导',depth:'standard',sections:{...basic.sections,derivation:'重新核对后通过的推导'}});
 show(true);expect(await screen.findByText(guide.example.body)).toBeVisible();expect(api.generate).not.toHaveBeenCalled();
 expect(screen.getByLabelText('深入学习目标')).toHaveValue('给我公式推导');
 fireEvent.click(screen.getByText('查看原因',{selector:'summary'}));expect(screen.getByText('公式与推导：缩放项需要核对')).toBeVisible();
 fireEvent.click(within(screen.getByRole('status',{name:'详细讲解准备结果'})).getByRole('button',{name:'重试个性化讲解'}));
 expect(await screen.findByText('重新核对后通过的推导')).toBeVisible();expect(api.generate).toHaveBeenCalledTimes(1);
 expect(api.generate).toHaveBeenCalledWith('p','n',true,expect.any(AbortSignal),{goal:'给我公式推导',depth:'standard'});
});

test('an entry request error does not create a retry loop',async()=>{
 api.generate.mockRejectedValue(new Error('暂时无法连接讲解服务'));show(true);
 expect(await screen.findByRole('alert')).toHaveTextContent('讲解未更新');
 expect(screen.getByText(detail.node.summary)).toBeVisible();expect(api.generate).toHaveBeenCalledTimes(1);
});

test('switching nodes discards a late generation response from the previous node',async()=>{
 let finish!:(value:LearningArtifact)=>void;api.generate.mockReturnValue(new Promise<LearningArtifact>(resolve=>{finish=resolve}));
 const ui=show(true);await waitFor(()=>expect(api.generate).toHaveBeenCalledTimes(1));const signal=api.generate.mock.calls[0][3] as AbortSignal;
 api.node.mockResolvedValue({...detail,node:{...detail.node,id:'other',label:'另一个知识'}});api.learning.mockResolvedValue({...basic,node_id:'other',status:'ready',sections:{...basic.sections,overview:'另一个节点的已保存内容'}});
 ui.rerender(<KnowledgeLearning autoPrepare projectId="p" nodeId="other" onNode={vi.fn()} onEvidence={vi.fn()} onBack={vi.fn()}/>);
 await screen.findByText('另一个节点的已保存内容');expect(signal.aborted).toBe(true);
 await act(async()=>finish({...basic,status:'ready',sections:{...basic.sections,derivation:'旧节点的迟到内容'}}));
 expect(screen.queryByText('旧节点的迟到内容')).toBeNull();expect(api.generate).toHaveBeenCalledTimes(1);
});

test('stopping the wait keeps the primer and reading saved content does not start another generation',async()=>{
 api.node.mockResolvedValue({...detail,study_guide:guide});api.generate.mockReturnValue(new Promise(()=>{}));show(true);
 await waitFor(()=>expect(api.generate).toHaveBeenCalledTimes(1));const signal=api.generate.mock.calls[0][3] as AbortSignal;
 fireEvent.click(await screen.findByRole('button',{name:'停止等待'}));expect(signal.aborted).toBe(true);
 expect(screen.getByText(guide.example.body)).toBeVisible();expect(screen.getByLabelText('深入学习目标')).toBeEnabled();
 fireEvent.click(screen.getByRole('button',{name:'重新读取已保存版本'}));await screen.findByText(guide.example.body);expect(api.generate).toHaveBeenCalledTimes(1);
});

test('a paper reading outline replaces title-only placeholders and remains distinct from generated content',async()=>{
 const reading={...guide,kind:'reading_outline' as const,title:'论文阅读起点',overview:'先明确研究问题，再沿方法与证据阅读。'};
 api.node.mockResolvedValue({...detail,study_guide:reading,node:{...detail.node,kind:'paper',label:'Attention Is All You Need',summary:'已保存的论文'}});
 api.learning.mockResolvedValue({...basic,sections:{...basic.sections,overview:'已保存的论文',definition:'Attention Is All You Need'}});
 show();expect(await screen.findByText(reading.overview)).toBeVisible();expect(screen.queryByText('已保存的论文')).toBeNull();expect(screen.queryByRole('heading',{name:'原文与定义'})).toBeNull();expect(screen.getByText('阅读指引')).toBeVisible();expect(screen.getByRole('option',{name:'论文导读'})).toBeInTheDocument();
});

test('the compact entry keeps the lesson visible and opens goal settings only when requested',async()=>{
 api.node.mockResolvedValue({...detail,study_guide:guide});
 render(<KnowledgeLearning compactControls projectId="p" nodeId="n" initialGoal="解释计算过程" onNode={vi.fn()} onEvidence={vi.fn()} onBack={vi.fn()}/>);
 expect(await screen.findByText(guide.example.body)).toBeVisible();
 expect(screen.getByLabelText('深入学习目标')).not.toBeVisible();
 expect(screen.getByRole('button',{name:'生成个性化讲解'})).toBeVisible();
 fireEvent.click(screen.getByText('调整学习目标与深度'));
 expect(screen.getByLabelText('深入学习目标')).toBeVisible();expect(screen.getByLabelText('深入学习目标')).toHaveValue('解释计算过程');expect(api.generate).not.toHaveBeenCalled();
});

test('sparse learning only shows actual content and matching table of contents',async()=>{
 show();await screen.findByText(detail.node.summary);
 const toc=within(screen.getByRole('navigation',{name:'学习内容目录'}));
 expect(toc.getAllByRole('option').map(a=>a.textContent)).toEqual(['章节','直观理解']);
 expect(screen.getAllByRole('heading',{level:3}).map(h=>h.textContent)).toEqual(['直观理解']);
 expect(screen.queryByText(/当前尚无已保存内容/)).toBeNull();
 expect(screen.queryByText(/基础内容来自当前资料/)).toBeNull();
 expect(screen.queryByLabelText('前置知识依赖图')).toBeNull();
 expect(screen.queryByText(/暂未匹配可复用演示|尚未保存匹配资源/)).toBeNull();
 expect(api.generate).not.toHaveBeenCalled();
});

test('a short source definition receives a substantive authored guide without generating or rewriting it',async()=>{
 api.node.mockResolvedValue({...detail,study_guide:guide,node:{...detail.node,label:'Self-attention',summary:'Self-attention relates positions in one sequence.'}});
 api.learning.mockResolvedValue({...basic,sections:{...basic.sections,overview:'Self-attention relates positions in one sequence.'}});
 show();
 const teaching=await screen.findByRole('region',{name:'知识基础讲解'});
 expect(within(teaching).getByText(guide.overview)).toBeVisible();
 expect(within(teaching).getByText(guide.example.body)).toBeVisible();
 expect(within(teaching).getByText(guide.common_confusions[0].explanation)).toBeVisible();
 expect(screen.getByRole('heading',{name:'资料中的描述'})).toBeVisible();
 expect(screen.getByText('Self-attention relates positions in one sequence.')).toBeVisible();
 const toc=within(screen.getByRole('navigation',{name:'学习内容目录'}));
 expect(toc.getByRole('option',{name:'基础讲解'})).toHaveValue('kw-learning-primer');
 expect(api.generate).not.toHaveBeenCalled();expect(api.patch).not.toHaveBeenCalled();
});

test('saved generated explanations retain the main reading area with optional foundation recall',async()=>{
 api.node.mockResolvedValue({...detail,study_guide:guide});
 api.learning.mockResolvedValue({...basic,status:'ready',sections:{...basic.sections,overview:'已保存的个性化讲解，围绕用户的问题。'}});
 show();
 expect(await screen.findByText('已保存的个性化讲解，围绕用户的问题。')).toBeVisible();
 const recall=screen.getByText('回顾基础讲解',{selector:'summary'}).closest('details')!;
 expect(recall).not.toHaveAttribute('open');
 expect(within(recall).getByText(guide.example.body)).not.toBeVisible();
 fireEvent.click(within(recall).getByText('回顾基础讲解',{selector:'summary'}));
 expect(within(recall).getByText(guide.example.body)).toBeVisible();
 expect(api.generate).not.toHaveBeenCalled();
});

test('manual lesson edits remain primary even when the ungenerated node has a teaching guide',async()=>{
 api.node.mockResolvedValue({...detail,study_guide:guide});
 api.learning.mockResolvedValue({...basic,user_edited_sections:['overview'],sections:{...basic.sections,overview:'我手工修订的当前方法解释。'}});
 show();
 expect(await screen.findByText('我手工修订的当前方法解释。')).toBeVisible();
 expect(screen.getByText('回顾基础讲解',{selector:'summary'}).closest('details')).not.toHaveAttribute('open');
 expect(api.patch).not.toHaveBeenCalled();
});

test('an existing full foundation lesson uses optional guide recall instead of duplicating the teaching body',async()=>{
 api.node.mockResolvedValue({...detail,study_guide:guide,node:{...detail.node,origin:'inference',metadata:{educational:true,knowledge_role:'teaching_supplement'}}});
 api.learning.mockResolvedValue({...basic,sections:{...basic.sections,overview:'这份基础教材已经包含完整的直观解释。',derivation:'完整基础教材的具体推导。'}});
 show();
 expect(await screen.findByText('这份基础教材已经包含完整的直观解释。')).toBeVisible();
 expect(screen.getByText('完整基础教材的具体推导。')).toBeVisible();
 expect(screen.getByText('回顾基础讲解',{selector:'summary'}).closest('details')).not.toHaveAttribute('open');
});

test('learning distinguishes direct source evidence from neighboring comparison sources',async()=>{
 const evidence=(id:string,source_id:string)=>({id,source_id,source_title:id,block_id:'b',quote:'Evidence text',locator:{page:1},source_version:'v',origin:'source'});
 api.learning.mockResolvedValue({...basic,evidence:[evidence('paper claim','s'),evidence('other paper','other')]});
 api.node.mockResolvedValue({...detail,node:{...detail.node,evidence_ids:['paper claim']}});
 show();await screen.findByText(detail.node.summary);
 fireEvent.click(screen.getByRole('tab',{name:'原文依据'}));
 expect(screen.getByRole('heading',{name:'当前知识的直接依据'})).toBeVisible();
 fireEvent.click(screen.getByRole('button',{name:/比较与关联来源/}));
 expect(screen.getByText('这些内容用于比较或解释关系，不代表当前方法的原作者陈述。')).toBeInTheDocument();
});

test('a learning goal and chosen depth are sent only on explicit generation',async()=>{
 api.generate.mockResolvedValue({...basic,status:'ready',goal:'解释局部梯度并给出反例',depth:'standard',sections:{...basic.sections,derivation:'逐步计算并说明饱和边界。'}});
 show();await screen.findByText(detail.node.summary);
 fireEvent.change(screen.getByLabelText('深入学习目标'),{target:{value:'解释局部梯度并给出反例'}});
 fireEvent.change(screen.getByLabelText('讲解深度'),{target:{value:'standard'}});
 expect(api.generate).not.toHaveBeenCalled();
 fireEvent.click(screen.getByRole('button',{name:'生成个性化讲解'}));
 expect(await screen.findByText('逐步计算并说明饱和边界。')).toBeVisible();
 expect(api.generate).toHaveBeenCalledWith('p','n',false,expect.any(AbortSignal),{goal:'解释局部梯度并给出反例',depth:'standard'});
});

test('saved goal and depth variants can be read without another model call',async()=>{
 const saved={...basic,status:'ready',goal:'目标 B',depth:'deep',variants:[{id:'v1',goal:'目标 A',depth:'standard',status:'ready'},{id:'v2',goal:'目标 B',depth:'deep',status:'ready'}]};
 api.learning.mockResolvedValueOnce(saved).mockResolvedValueOnce({...saved,goal:'目标 A',depth:'standard',sections:{...basic.sections,overview:'目标 A 的已保存讲解'}});
 show();await screen.findByText(detail.node.summary);fireEvent.click(screen.getByText(/已保存讲解 · 2/,{selector:'summary'}));
 fireEvent.click(screen.getByRole('button',{name:'重点理解 · 目标 A'}));
 expect(await screen.findByText('目标 A 的已保存讲解')).toBeVisible();
 expect(api.learning).toHaveBeenLastCalledWith('p','n',expect.any(AbortSignal),{goal:'目标 A',depth:'standard'});expect(api.generate).not.toHaveBeenCalled();
});

test('a failed deeper generation keeps the currently readable explanation',async()=>{
 api.generate.mockRejectedValue(new Error('provider unavailable'));
 show();await screen.findByText(detail.node.summary);fireEvent.click(screen.getByRole('button',{name:'生成个性化讲解'}));
 expect(await screen.findByRole('alert')).toHaveTextContent('讲解未更新');
 expect(screen.getByText(detail.node.summary)).toBeVisible();
});

test('an empty section can be supplemented from the compact content manager',async()=>{
 show();await screen.findByText(detail.node.summary);
 fireEvent.click(screen.getByText('管理学习内容',{selector:'summary'}));
 fireEvent.click(screen.getByRole('button',{name:'修订讲解：实现与代码'}));
 fireEvent.change(screen.getByLabelText('实现与代码内容'),{target:{value:'用当前观测构造 sigmoid 门控。'}});
 fireEvent.click(screen.getByRole('button',{name:'保存讲解修订'}));
 expect(await screen.findByText('用当前观测构造 sigmoid 门控。',{selector:'p'})).toBeVisible();
 expect(screen.getByRole('option',{name:'实现与代码'})).toHaveValue('kw-learning-implementation');
 expect(api.patch).toHaveBeenCalledWith('p','n',expect.objectContaining({expected_revision:1,sections:{implementation:'用当前观测构造 sigmoid 门控。'}}),expect.any(AbortSignal));
});

test('a real prerequisite section and uncertain scientific conclusion are retained',async()=>{
 api.node.mockResolvedValue({...detail,prerequisites:[{...detail.node,id:'prereq',label:'sigmoid',summary:'把实数映射到零和一之间。'}]});
 api.learning.mockResolvedValue({...basic,sections:{...basic.sections,limitations:'当前任务的消融实验尚未验证在新物体上的泛化。'}});
 show();expect(await screen.findByText('当前任务的消融实验尚未验证在新物体上的泛化。')).toBeVisible();
 expect(screen.getByLabelText('前置知识依赖图')).toBeVisible();
 expect(screen.getByRole('option',{name:'需要的前置知识'})).toHaveValue('kw-learning-prerequisites');
});

test('exact system boilerplate is not suppressed when explicitly saved by the user',async()=>{
 api.learning.mockResolvedValue({...basic,user_edited_sections:['limitations']});
 show();expect(await screen.findByText(basic.sections.limitations)).toBeVisible();
});

test('empty resources and unmatched demos produce no headings or placeholder blocks',()=>{
 const {container}=render(<><LearningResources items={[{}]}/><KnowledgeDemos ids={['does-not-exist']}/></>);
 expect(container).toBeEmptyDOMElement();
});

test('a precise original formula image is real definition content even without extracted text',async()=>{
 const formula={evidence_id:'e',block_id:'equation',source_id:'s',label:'式 2',recognition:'partial',page:4,image_url:'/api/projects/p/sources/s/blocks/equation/image'};
 const evidence={id:'e',source_id:'s',source_title:'论文原文',block_id:'equation',quote:'',locator:{page:4},source_version:'sha256:abc',origin:'source'};
 api.node.mockResolvedValue({...detail,node:{...detail.node,kind:'formula',summary:'x = � + �',metadata:{latex:'should not duplicate'}},evidence:[evidence],formula_sources:[formula]});
 api.learning.mockResolvedValue({...basic,sections:{...basic.sections,overview:''}});
 show();expect(await screen.findByRole('img',{name:'第 4 页公式原图'})).toHaveAttribute('src',formula.image_url);
 expect(screen.getByRole('heading',{name:'原文与定义'})).toBeVisible();
 expect(screen.getByRole('option',{name:'原文与定义'})).toHaveValue('kw-learning-definition');
 expect(screen.queryByRole('heading',{name:'公式与推导'})).toBeNull();
 expect(screen.queryByRole('heading',{name:'直观理解'})).toBeNull();
 expect(screen.queryByRole('option',{name:'直观理解'})).toBeNull();
 expect(screen.queryByText(/公式文本识别不完整/)).toBeNull();
 expect(screen.getByRole('button',{name:'查看公式原文'})).toBeVisible();
});

test('recoverable prose survives broken automatic formulas while user teaching text remains untouched',async()=>{
 api.learning.mockResolvedValue({...basic,user_edited_sections:['implementation'],sections:{...basic.sections,overview:'这段正文解释观测如何决定门控。\n\n$$x=� + �$$',implementation:'我的原始核对笔记：x=� + �'}});
 show();expect(await screen.findByText('这段正文解释观测如何决定门控。')).toBeVisible();
 expect(screen.queryByText('$$x=� + �$$')).toBeNull();
 expect(screen.getByText('我的原始核对笔记：x=� + �')).toBeVisible();
});
