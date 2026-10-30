import {useState} from 'react';
import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import {beforeEach,expect,test,vi} from 'vitest';
import KnowledgeGraphView,{type GraphScene} from '../components/knowledge/KnowledgeGraph';
import type {KnowledgeGraph,KnowledgeNode,KnowledgeSource} from '../api/knowledge';

const api=vi.hoisted(()=>({graph:vi.fn(),node:vi.fn(),patch:vi.fn(),merge:vi.fn(),split:vi.fn()}));
vi.mock('../api/knowledge',()=>({getKnowledgeGraph:api.graph,getKnowledgeNode:api.node,patchKnowledgeNode:api.patch,patchKnowledgeEdge:api.patch,mergeKnowledgeNodes:api.merge,splitKnowledgeNode:api.split,
 nodeKindLabels:{paper:'论文',report:'报告',method:'方法',module:'模块',formula:'公式',concept:'概念',problem:'问题'},originLabels:{source:'原文明示'},researchStatusLabels:{unknown:'未知'}}));
vi.mock('../components/knowledge/KnowledgeSources',()=>({EvidenceList:()=>null}));
vi.mock('@ant-design/icons',()=>({CloseOutlined:()=>null,FilterOutlined:()=>null,FullscreenOutlined:()=>null,MinusOutlined:()=>null,PlusOutlined:()=>null,ArrowLeftOutlined:()=>null,ArrowRightOutlined:()=>null}));
vi.mock('antd',()=>{
 const Input=Object.assign(({allowClear:_,...p}:any)=><input {...p}/>,{
  Search:({onSearch,allowClear:_,...p}:any)=><input {...p} onKeyDown={e=>{if(e.key==='Enter')onSearch?.(e.currentTarget.value)}}/>,
  TextArea:({autoSize:_,...p}:any)=><textarea {...p}/>,
 });
 const Space=Object.assign(({children}:any)=><div>{children}</div>,{Compact:({children}:any)=><div>{children}</div>});
 return {Input,Space,Button:({children,icon,loading:_,type:__,danger:___,...p}:any)=><button {...p}>{icon}{children}</button>,
  Select:({options,onChange,showSearch:_,optionFilterProp:__,...p}:any)=><select {...p} onChange={e=>onChange?.(e.currentTarget.value)}>{options.map((o:any)=><option value={o.value} key={o.value}>{o.label}</option>)}</select>,
  Switch:({checked,onChange,size:_,...p}:any)=><input {...p} type="checkbox" checked={checked} onChange={e=>onChange?.(e.currentTarget.checked)}/>,
  Tag:({children}:any)=><span>{children}</span>,Spin:()=>null,Alert:({message,description,action}:any)=><div role="alert">{message}{description}{action}</div>};
});

const node=(id:string,kind:string,label:string,parent_id:string|null):KnowledgeNode=>({id,kind,label,parent_id,project_id:'p',source_id:'s1',summary:'Grounded context for '+label,origin:'source',research_status:'unknown',version:1,hidden:false,source_missing:false,evidence_ids:[],metadata:{semantic:true}});
const nodes=[node('paper','paper','Paper A',null),node('method','method','Coordinated policy','paper'),node('module','module','State gate','method'),node('formula','formula','Bounded residual','module')];
const source:KnowledgeSource={id:'s1',project_id:'p',asset_id:'asset',version:'v1',title:'Paper A',filename:'paper.pdf',kind:'paper',media_type:'application/pdf',removed:false,created_at:'2026-10-29'};
const graph:KnowledgeGraph={nodes,edges:[['paper','method'],['method','module'],['module','formula']].map(([from,to],i)=>({id:'e'+i,project_id:'p',source_id:'s1',source:from,target:to,kind:'HAS_PART',label:'组成',explanation:'Actual source relation',origin:'source',version:1,hidden:false,source_missing:false,evidence_ids:[],metadata:{}})),total_nodes:4,total_edges:3,truncated:false};

function Harness({initialScene,initialNode,initialSource}:{initialScene?:GraphScene;initialNode?:string;initialSource?:string}){
 const [scope,setScope]=useState<string|undefined>(initialSource),[selected,setSelected]=useState(initialNode);
 return <KnowledgeGraphView projectId="p" sourceId={scope} nodeId={selected} sources={[source]} onScope={id=>{setScope(id);setSelected(undefined)}} onNode={n=>{setSelected(n.id);if(n.kind==='paper')setScope(n.source_id)}}
  onClear={()=>setSelected(undefined)} onLearn={vi.fn()} onEvidence={vi.fn()} onSource={vi.fn()} revision={0} onUpdated={vi.fn()} initialScene={initialScene}/>;
}
beforeEach(()=>{vi.clearAllMocks();api.graph.mockImplementation(async(_p,query)=>query.q?{...graph,nodes:nodes.filter(n=>n.label.toLowerCase().includes(query.q.toLowerCase())),edges:[],total_nodes:1,total_edges:0}:graph);api.node.mockImplementation(async(_p,id)=>({node:nodes.find(n=>n.id===id)||nodes[0],neighbors:[],edges:[],evidence:[],prerequisites:[],resources:[],demos:[]}));});

test('one paper selection exposes its method and module without category drill-down controls',async()=>{
 const {container}=render(<Harness/>);
 fireEvent.click(await screen.findByLabelText('论文：Paper A'));
 await waitFor(()=>expect(api.graph).toHaveBeenLastCalledWith('p',expect.objectContaining({source_id:'s1',node_id:undefined}),expect.any(AbortSignal)));
 expect(await screen.findByLabelText('方法：Coordinated policy')).toBeVisible();
 expect(screen.getByLabelText('模块：State gate')).toBeVisible();
 expect(container.querySelector('.kw-node-expand')).toBeNull();
 expect(screen.queryAllByLabelText(/^展开主题：/)).toHaveLength(0);
});

test('selecting ordinary knowledge opens its detail without replacing the graph with a single-hop request',async()=>{
 render(<Harness initialSource="s1"/>);
 fireEvent.click(await screen.findByLabelText('模块：State gate'));
 expect(await screen.findByRole('heading',{name:'State gate'})).toBeVisible();
 expect(screen.getByLabelText('方法：Coordinated policy')).toBeVisible();
 expect(api.graph.mock.calls.every(([,query])=>!query.node_id)).toBe(true);
});

test('an explicit search is not restricted by a previously focused node and its result opens directly',async()=>{
 const scene:GraphScene={scope:'p/all',search:'',query:'',kind:'',focus:'method',zoom:1,includeHidden:false,showStructure:false,scrollLeft:0,scrollTop:0};
 render(<Harness initialScene={scene} initialNode="method"/>);
 const search=await screen.findByLabelText('搜索图谱知识');
 fireEvent.change(search,{target:{value:'Bounded residual'}});fireEvent.keyDown(search,{key:'Enter'});
 await waitFor(()=>expect(api.graph).toHaveBeenLastCalledWith('p',expect.objectContaining({q:'Bounded residual',node_id:undefined}),expect.any(AbortSignal)));
 fireEvent.click(await screen.findByLabelText('公式：Bounded residual'));
 expect(await screen.findByRole('heading',{name:'Bounded residual'})).toBeVisible();
});

test('parent refresh during first load does not treat an unmeasured scene as a restored viewport',async()=>{
 let resolveGraph!:(value:KnowledgeGraph)=>void;
 api.graph.mockReturnValue(new Promise<KnowledgeGraph>(resolve=>{resolveGraph=resolve}));
 const width=vi.spyOn(HTMLElement.prototype,'clientWidth','get').mockReturnValue(500);
 const height=vi.spyOn(HTMLElement.prototype,'clientHeight','get').mockReturnValue(320);
 let saved:GraphScene|undefined;
 const props={projectId:'p',onNode:vi.fn(),onLearn:vi.fn(),onEvidence:vi.fn(),onSource:vi.fn(),revision:0,onUpdated:vi.fn(),onSceneChange:(scene:GraphScene)=>{saved=scene}};
 try{
  const view=render(<KnowledgeGraphView {...props}/>);
  await waitFor(()=>expect(saved?.zoom).toBe(1));
  view.rerender(<KnowledgeGraphView {...props} initialScene={saved}/>);
  resolveGraph(graph);
  await screen.findByLabelText('方法：Coordinated policy');
  await waitFor(()=>expect(saved!.zoom).toBeLessThan(1));
  expect(screen.getByRole('button',{name:'重置图谱视角'})).not.toHaveTextContent('100%');
 }finally{width.mockRestore();height.mockRestore()}
});
