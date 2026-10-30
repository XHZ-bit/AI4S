import {fireEvent,render,screen,within} from '@testing-library/react';
import {beforeEach,expect,test,vi} from 'vitest';
import KnowledgeLearning,{LearningResources} from '../components/knowledge/KnowledgeLearning';
import KnowledgeDemos from '../components/knowledge/KnowledgeDemos';
import type {LearningArtifact,NodeDetail} from '../api/knowledge';

const api=vi.hoisted(()=>({node:vi.fn(),learning:vi.fn(),generate:vi.fn(),patch:vi.fn()}));
vi.mock('../api/knowledge',()=>({getKnowledgeNode:api.node,getNodeLearning:api.learning,generateNodeLearning:api.generate,patchNodeLearning:api.patch}));
vi.mock('../components/knowledge/KnowledgeGraph',()=>({NodeBadges:()=>null}));
vi.mock('../components/knowledge/KnowledgeText',()=>({default:({text}:{text:string})=><p>{text}</p>,mathAwareText:(text:string)=>text}));
vi.mock('../components/knowledge/KnowledgeSources',()=>({EvidenceList:()=>null}));
vi.mock('antd',()=>({
 Alert:({message}:{message:string})=><div role="alert">{message}</div>,
 Button:({children,type:_,loading:__,size:___,...props}:React.ButtonHTMLAttributes<HTMLButtonElement>&{loading?:boolean;size?:string})=><button {...props}>{children}</button>,
 Input:{TextArea:({autoSize:_,...props}:React.TextareaHTMLAttributes<HTMLTextAreaElement>&{autoSize?:unknown})=><textarea {...props}/>},
 Space:({children}:{children:React.ReactNode})=><div>{children}</div>,Spin:()=>null,Tag:({children}:{children:React.ReactNode})=><span>{children}</span>,Select:()=>null,
}));

const detail:NodeDetail={node:{id:'n',project_id:'p',source_id:'s',kind:'module',label:'状态门控',summary:'根据当前观测调节消息强度。',parent_id:null,origin:'source',research_status:'unknown',version:1,hidden:false,source_missing:false,evidence_ids:[],metadata:{}},edges:[],neighbors:[],evidence:[],prerequisites:[],resources:[],demos:['unknown-demo']};
const basic:LearningArtifact={id:'a',node_id:'n',node_version:1,status:'basic',stale:false,cached:false,revision:1,sections:{overview:detail.node.summary,definition:'',derivation:'',prerequisites:'',implementation:'',limitations:'基础内容来自当前资料。深入讲解属于教学补充，需结合原文的条件和范围理解。'},evidence:[],resources:[],demos:[],usage:{},errors:[]};
beforeEach(()=>{vi.clearAllMocks();api.node.mockResolvedValue(detail);api.learning.mockResolvedValue(basic);api.patch.mockImplementation(async(_p,_n,body)=>({...basic,revision:2,user_edited_sections:Object.keys(body.sections||{}),sections:{...basic.sections,...body.sections}}));});
function show(){return render(<KnowledgeLearning projectId="p" nodeId="n" onNode={vi.fn()} onEvidence={vi.fn()} onBack={vi.fn()}/>)}

test('sparse learning only shows actual content and matching table of contents',async()=>{
 show();await screen.findByText(detail.node.summary);
 const toc=within(screen.getByRole('navigation',{name:'学习内容目录'}));
 expect(toc.getAllByRole('link').map(a=>a.textContent)).toEqual(['直观理解']);
 expect(screen.getAllByRole('heading',{level:3}).map(h=>h.textContent)).toEqual(['直观理解']);
 expect(screen.queryByText(/当前尚无已保存内容/)).toBeNull();
 expect(screen.queryByText(/基础内容来自当前资料/)).toBeNull();
 expect(screen.queryByLabelText('前置知识依赖图')).toBeNull();
 expect(screen.queryByText(/暂未匹配可复用演示|尚未保存匹配资源/)).toBeNull();
 expect(api.generate).not.toHaveBeenCalled();
});

test('learning distinguishes direct source evidence from neighboring comparison sources',async()=>{
 const evidence=(id:string,source_id:string)=>({id,source_id,source_title:id,block_id:'b',quote:'Evidence text',locator:{page:1},source_version:'v',origin:'source'});
 api.learning.mockResolvedValue({...basic,evidence:[evidence('paper claim','s'),evidence('other paper','other')]});
 show();await screen.findByText(detail.node.summary);
 expect(screen.getByRole('heading',{name:'当前知识的直接依据'})).toBeVisible();
 expect(screen.getByText('比较与关联来源 · 1 处',{selector:'summary'})).toBeVisible();
 expect(screen.getByText('这些内容用于比较或解释关系，不代表当前方法的原作者陈述。')).toBeInTheDocument();
});

test('a learning goal and chosen depth are sent only on explicit generation',async()=>{
 api.generate.mockResolvedValue({...basic,status:'ready',goal:'解释局部梯度并给出反例',depth:'standard',sections:{...basic.sections,derivation:'逐步计算并说明饱和边界。'}});
 show();await screen.findByText(detail.node.summary);
 fireEvent.change(screen.getByLabelText('深入学习目标'),{target:{value:'解释局部梯度并给出反例'}});
 fireEvent.change(screen.getByLabelText('讲解深度'),{target:{value:'standard'}});
 expect(api.generate).not.toHaveBeenCalled();
 fireEvent.click(screen.getByRole('button',{name:'准备深入讲解'}));
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
 show();await screen.findByText(detail.node.summary);fireEvent.click(screen.getByRole('button',{name:'准备深入讲解'}));
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
 expect(screen.getByRole('link',{name:'实现与代码'})).toBeVisible();
 expect(api.patch).toHaveBeenCalledWith('p','n',expect.objectContaining({expected_revision:1,sections:{implementation:'用当前观测构造 sigmoid 门控。'}}),expect.any(AbortSignal));
});

test('a real prerequisite section and uncertain scientific conclusion are retained',async()=>{
 api.node.mockResolvedValue({...detail,prerequisites:[{...detail.node,id:'prereq',label:'sigmoid',summary:'把实数映射到零和一之间。'}]});
 api.learning.mockResolvedValue({...basic,sections:{...basic.sections,limitations:'当前任务的消融实验尚未验证在新物体上的泛化。'}});
 show();expect(await screen.findByText('当前任务的消融实验尚未验证在新物体上的泛化。')).toBeVisible();
 expect(screen.getByLabelText('前置知识依赖图')).toBeVisible();
 expect(screen.getByRole('link',{name:'需要的前置知识'})).toBeVisible();
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
 expect(screen.getByRole('link',{name:'原文与定义'})).toBeVisible();
 expect(screen.queryByRole('heading',{name:'公式与推导'})).toBeNull();
 expect(screen.queryByRole('heading',{name:'直观理解'})).toBeNull();
 expect(screen.queryByRole('link',{name:'直观理解'})).toBeNull();
 expect(screen.queryByText(/公式文本识别不完整/)).toBeNull();
 expect(screen.getByRole('button',{name:'查看公式原文'})).toBeVisible();
});

test('recoverable prose survives broken automatic formulas while user teaching text remains untouched',async()=>{
 api.learning.mockResolvedValue({...basic,user_edited_sections:['implementation'],sections:{...basic.sections,overview:'这段正文解释观测如何决定门控。\n\n$$x=� + �$$',implementation:'我的原始核对笔记：x=� + �'}});
 show();expect(await screen.findByText('这段正文解释观测如何决定门控。')).toBeVisible();
 expect(screen.queryByText('$$x=� + �$$')).toBeNull();
 expect(screen.getByText('我的原始核对笔记：x=� + �')).toBeVisible();
});
