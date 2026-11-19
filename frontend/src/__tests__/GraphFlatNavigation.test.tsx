import {useState} from 'react';
import {act,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {beforeEach,expect,test,vi} from 'vitest';
import KnowledgeGraphView,{type GraphScene} from '../components/knowledge/KnowledgeGraph';
import type {KnowledgeGraph,KnowledgeNode,KnowledgeSource} from '../api/knowledge';

const api=vi.hoisted(()=>({graph:vi.fn(),node:vi.fn(),patch:vi.fn(),merge:vi.fn(),split:vi.fn(),edge:vi.fn()}));
vi.mock('../api/unifiedGraph',()=>({getUnifiedEdge:api.edge,getKnowledgePath:vi.fn()}));
vi.mock('../api/knowledge',()=>({getKnowledgeGraph:api.graph,getKnowledgeNode:api.node,patchKnowledgeNode:api.patch,patchKnowledgeEdge:api.patch,mergeKnowledgeNodes:api.merge,splitKnowledgeNode:api.split,
 nodeKindLabels:{paper:'论文',report:'报告',method:'方法',module:'模块',formula:'公式',concept:'概念',problem:'问题'},originLabels:{source:'原文明示'},researchStatusLabels:{unknown:'未知'}}));
vi.mock('../components/knowledge/KnowledgeSources',()=>({EvidenceList:()=>null}));
vi.mock('@ant-design/icons',()=>({ExpandAltOutlined:()=>null,ShrinkOutlined:()=>null,ColumnWidthOutlined:()=>null,CloseOutlined:()=>null,FilterOutlined:()=>null,FullscreenOutlined:()=>null,MinusOutlined:()=>null,PlusOutlined:()=>null,ArrowLeftOutlined:()=>null,ArrowRightOutlined:()=>null}));
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

test('ordinary selection preserves every displayed node position and closing restores keyboard focus',async()=>{
 const {container}=render(<Harness initialSource="s1"/>);
 const selected=await screen.findByLabelText('模块：State gate');
 const positions=()=>[...container.querySelectorAll('[data-node-id]')].map(element=>[element.getAttribute('data-node-id'),element.getAttribute('transform')]);
 const before=positions();
 act(()=>selected.focus());fireEvent.keyDown(selected,{key:'Enter'});
 await screen.findByRole('heading',{name:'State gate'});
 expect(positions()).toEqual(before);
 fireEvent.click(screen.getByRole('button',{name:'关闭节点详情'}));
 expect(selected).toHaveFocus();expect(positions()).toEqual(before);
});

test('restored relation retains the original graph anchor and returns keyboard focus after closing',async()=>{
 api.edge.mockResolvedValue({edge:graph.edges[1],evidence:[]});
 const onInspectChange=vi.fn();let saved:GraphScene|undefined;
 const initialScene:GraphScene={scope:'p/s1',search:'',query:'',kind:'',focus:'',zoom:1,includeHidden:false,showStructure:false,scrollLeft:100,scrollTop:40,anchorId:'',edgeId:'e1'};
 const {container}=render(<KnowledgeGraphView projectId="p" sourceId="s1" onNode={vi.fn()} onLearn={vi.fn()} onEvidence={vi.fn()} onSource={vi.fn()} revision={0} onUpdated={vi.fn()} initialScene={initialScene} onInspectChange={onInspectChange} onSceneChange={scene=>{saved=scene}}/>);
 await screen.findByRole('heading',{name:'关系与依据'});
 expect(onInspectChange).toHaveBeenLastCalledWith(true);
 expect(saved?.anchorId).toBe('');expect(saved?.edgeId).toBe('e1');
 fireEvent.click(screen.getByRole('button',{name:'关闭关系详情'}));
 expect(container.querySelector('[data-edge-id="e1"]')).toHaveFocus();
 expect(saved?.edgeId).toBeUndefined();
});

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

test('mouse wheel zoom keeps the pointer anchor and survives selection, double clicks and a resized canvas',async()=>{
 let width=500;
 const widthSpy=vi.spyOn(HTMLElement.prototype,'clientWidth','get').mockImplementation(()=>width);
 const heightSpy=vi.spyOn(HTMLElement.prototype,'clientHeight','get').mockReturnValue(320);
 try{
  const initialScene:GraphScene={scope:'p/s1',search:'',query:'',kind:'',focus:'',zoom:1,includeHidden:false,showStructure:false,scrollLeft:0,scrollTop:0};
  render(<Harness initialSource="s1" initialScene={initialScene}/>);
  await screen.findByLabelText('方法：Coordinated policy');
  const canvas=screen.getByLabelText('研究知识图谱画布'),percentage=screen.getByRole('button',{name:'重置图谱视角'});
  const bounds=canvas.getBoundingClientRect();
  canvas.scrollLeft=200;canvas.scrollTop=120;
  const wheel=new WheelEvent('wheel',{bubbles:true,cancelable:true,deltaY:-120,clientX:bounds.left+150,clientY:bounds.top+100});
  fireEvent(canvas,wheel);
  expect(wheel.defaultPrevented).toBe(true);
  const scale=Math.exp(120*.0015);
  expect(percentage).toHaveTextContent(Math.round(scale*100)+'%');
  expect(canvas.scrollLeft).toBeCloseTo(350*scale-150);
  expect(canvas.scrollTop).toBeCloseTo(220*scale-100);
  const left=canvas.scrollLeft,top=canvas.scrollTop;
  fireEvent.click(screen.getByLabelText('模块：State gate'));
  await screen.findByRole('heading',{name:'State gate'});
  fireEvent.doubleClick(canvas);
  width=380;fireEvent(window,new Event('resize'));
  expect(percentage).toHaveTextContent(Math.round(scale*100)+'%');
  expect(canvas.scrollLeft).toBe(left);expect(canvas.scrollTop).toBe(top);
  fireEvent.click(percentage);
  expect(percentage).not.toHaveTextContent(Math.round(scale*100)+'%');
  expect(canvas.scrollLeft).toBe(0);expect(canvas.scrollTop).toBe(0);
 }finally{widthSpy.mockRestore();heightSpy.mockRestore()}
});

test('an initially fitted canvas keeps manual zoom across layout refreshes and initializes a new source scope',async()=>{
 const width=vi.spyOn(HTMLElement.prototype,'clientWidth','get').mockReturnValue(500);
 const height=vi.spyOn(HTMLElement.prototype,'clientHeight','get').mockReturnValue(320);
 const props={projectId:'p',onNode:vi.fn(),onLearn:vi.fn(),onEvidence:vi.fn(),onSource:vi.fn(),onUpdated:vi.fn()};
 try{
  const view=render(<KnowledgeGraphView {...props} sourceId="s1" revision={0}/>);
  await screen.findByLabelText('方法：Coordinated policy');
  const percentage=screen.getByRole('button',{name:'重置图谱视角'}),firstFit=percentage.textContent;
  fireEvent.click(screen.getByRole('button',{name:'放大图谱'}));
  const manual=percentage.textContent;
  expect(manual).not.toBe(firstFit);
  view.rerender(<KnowledgeGraphView {...props} sourceId="s1" nodeId="module" revision={1}/>);
  await screen.findByRole('heading',{name:'State gate'});
  await waitFor(()=>expect(api.graph).toHaveBeenLastCalledWith('p',expect.objectContaining({source_id:'s1'}),expect.any(AbortSignal)));
  expect(percentage.textContent).toBe(manual);
  view.rerender(<KnowledgeGraphView {...props} sourceId="s2" revision={0}/>);
  await waitFor(()=>expect(api.graph).toHaveBeenLastCalledWith('p',expect.objectContaining({source_id:'s2'}),expect.any(AbortSignal)));
  await waitFor(()=>expect(percentage.textContent).toBe(firstFit));
 }finally{width.mockRestore();height.mockRestore()}
});

test('arranging nodes saves personal positions and can undo a reset',async()=>{
 let saved:GraphScene|undefined;
 render(<KnowledgeGraphView projectId="p" sourceId="s1" onNode={vi.fn()} onLearn={vi.fn()} onEvidence={vi.fn()} onSource={vi.fn()} revision={0} onUpdated={vi.fn()} onSceneChange={scene=>{saved=scene}}/>);
 const method=await screen.findByLabelText('方法：Coordinated policy');
 const original=method.getAttribute('transform');
 fireEvent.keyDown(method,{key:'ArrowDown'});
 expect(method.getAttribute('transform')).toBe(original);
 fireEvent.click(screen.getByRole('button',{name:'整理节点'}));
 fireEvent.keyDown(method,{key:'ArrowDown',shiftKey:true});
 await waitFor(()=>expect(saved?.layouts?.['p/s1']?.method).toBeDefined());
 const moved=method.getAttribute('transform');
 expect(moved).not.toBe(original);
 expect(screen.getByText('节点位置已保存在此浏览器')).toBeVisible();
 fireEvent.click(screen.getByRole('button',{name:'恢复自动布局'}));
 expect(method.getAttribute('transform')).toBe(original);
 fireEvent.click(screen.getByRole('button',{name:'撤销'}));
 expect(method.getAttribute('transform')).toBe(moved);
});

test('restored node positions survive view changes and remain separate for each material scope',async()=>{
 const scene:GraphScene={scope:'p/s1',search:'',query:'',kind:'',focus:'',zoom:1,includeHidden:false,showStructure:false,scrollLeft:0,scrollTop:0,layouts:{'p/s1':{method:{x:800,y:600}},'p/all':{method:{x:900,y:700}}}};
 const props={projectId:'p',onNode:vi.fn(),onLearn:vi.fn(),onEvidence:vi.fn(),onSource:vi.fn(),revision:0,onUpdated:vi.fn(),initialScene:scene};
 const view=render(<KnowledgeGraphView {...props} sourceId="s1"/>);
 expect(await screen.findByLabelText('方法：Coordinated policy')).toHaveAttribute('transform','translate(800,600)');
 view.rerender(<KnowledgeGraphView {...props}/>);
 await waitFor(()=>expect(screen.getByLabelText('方法：Coordinated policy')).toHaveAttribute('transform','translate(900,700)'));
 view.rerender(<KnowledgeGraphView {...props} sourceId="s1"/>);
 await waitFor(()=>expect(screen.getByLabelText('方法：Coordinated policy')).toHaveAttribute('transform','translate(800,600)'));
});

test('dragging at a scaled zoom saves the drop without opening node details and cancellation keeps the saved layout',async()=>{
 let saved:GraphScene|undefined;
 const onNode=vi.fn(),scene:GraphScene={scope:'p/s1',search:'',query:'',kind:'',focus:'',zoom:.5,includeHidden:false,showStructure:false,scrollLeft:0,scrollTop:0,layouts:{'p/s1':{method:{x:800,y:600}}}};
 render(<KnowledgeGraphView projectId="p" sourceId="s1" onNode={onNode} onLearn={vi.fn()} onEvidence={vi.fn()} onSource={vi.fn()} revision={0} onUpdated={vi.fn()} initialScene={scene} onSceneChange={value=>{saved=value}}/>);
 const method=await screen.findByLabelText('方法：Coordinated policy'),canvas=screen.getByLabelText('研究知识图谱画布');
 const pointer=(element:Element,type:string,x:number,y:number)=>{const event=new MouseEvent(type,{bubbles:true,button:0,clientX:x,clientY:y});Object.defineProperty(event,'pointerId',{value:1});fireEvent(element,event)};
 fireEvent.click(screen.getByRole('button',{name:'整理节点'}));
 pointer(method,'pointerdown',100,100);pointer(canvas,'pointermove',180,140);pointer(canvas,'pointerup',180,140);
 await waitFor(()=>expect(saved?.layouts?.['p/s1']?.method).toEqual({x:960,y:680}));
 fireEvent.click(method);
 expect(onNode).not.toHaveBeenCalled();
 pointer(method,'pointerdown',100,100);pointer(canvas,'pointermove',300,300);pointer(canvas,'pointercancel',300,300);
 expect(saved?.layouts?.['p/s1']?.method).toEqual({x:960,y:680});
 expect(method).toHaveAttribute('transform','translate(960,680)');
});

test('a normal page entry restores personal layout independently of viewport restoration',async()=>{
 let saved:GraphScene|undefined;
 render(<KnowledgeGraphView projectId="p" sourceId="s1" onNode={vi.fn()} onLearn={vi.fn()} onEvidence={vi.fn()} onSource={vi.fn()} revision={0} onUpdated={vi.fn()} initialLayouts={{'p/s1':{method:{x:880,y:610}}}} onSceneChange={value=>{saved=value}}/>);
 expect(await screen.findByLabelText('方法：Coordinated policy')).toHaveAttribute('transform','translate(880,610)');
 expect(saved?.layouts?.['p/s1']?.method).toEqual({x:880,y:610});
});

test('a storage failure preserves in-memory positions and offers a retry without claiming success',async()=>{
 let storageReady=false;
 const save=vi.fn(()=>storageReady);
 render(<KnowledgeGraphView projectId="p" sourceId="s1" onNode={vi.fn()} onLearn={vi.fn()} onEvidence={vi.fn()} onSource={vi.fn()} revision={0} onUpdated={vi.fn()} onSceneChange={save}/>);
 const method=await screen.findByLabelText('方法：Coordinated policy');
 fireEvent.click(screen.getByRole('button',{name:'整理节点'}));
 fireEvent.keyDown(method,{key:'ArrowDown',shiftKey:true});
 const moved=method.getAttribute('transform');
 expect(screen.getByText('布局暂未保存，存储空间可能不可用。')).toBeVisible();
 expect(screen.queryByText('节点位置已保存在此浏览器')).not.toBeInTheDocument();
 storageReady=true;
 fireEvent.click(screen.getByRole('button',{name:'重试保存布局'}));
 expect(screen.queryByText('布局暂未保存，存储空间可能不可用。')).not.toBeInTheDocument();
 expect(screen.getByText('布局已保存在此浏览器')).toBeVisible();
 expect(method.getAttribute('transform')).toBe(moved);
});

test('returning from original text preserves the selected knowledge structural neighbor and its real relation',async()=>{
 api.graph.mockResolvedValue({...graph,nodes:nodes.map(n=>n.id==='module'?{...n,metadata:{structural:true}}:n)});
 const scene:GraphScene={scope:'p/s1',search:'',query:'',kind:'',focus:'',zoom:1,includeHidden:false,showStructure:false,scrollLeft:0,scrollTop:0};
 render(<Harness initialSource="s1" initialNode="formula" initialScene={scene}/>);
 expect(await screen.findByLabelText('公式：Bounded residual')).toBeVisible();
 expect(screen.getByLabelText('模块：State gate')).toBeVisible();
 expect(screen.getAllByLabelText('关系：组成')).toHaveLength(3);
});

test('a user-corrected structural formula is discoverable without search and keeps its original source path',async()=>{
 const chapter={...node('equation-section','module','缩放公式所在小节','paper'),metadata:{structural:true}};
 const corrected={...node('corrected-formula','formula','缩放分数','equation-section'),origin:'user' as const,metadata:{structural:true,user_fields:['label','summary'],recognition:'user_corrected'}};
 const noise={...node('unrelated-section','module','未修订的普通章节','paper'),metadata:{structural:true}};
 const untouched={...node('untouched-formula','formula','未修订的另一公式','unrelated-section'),metadata:{structural:true}};
 const current={...graph,nodes:[nodes[0],nodes[1],chapter,corrected,noise,untouched],edges:[{...graph.edges[0],source:'paper',target:chapter.id},{...graph.edges[1],source:chapter.id,target:corrected.id}],total_nodes:6,total_edges:2};
 api.graph.mockResolvedValue(current);
 const select=vi.fn();
 render(<KnowledgeGraphView projectId="p" sourceId="s1" onNode={select} onLearn={vi.fn()} onEvidence={vi.fn()} onSource={vi.fn()} revision={0} onUpdated={vi.fn()} question="理解缩放分数" questionFocused/>);
 const entry=await screen.findByLabelText('公式：缩放分数');
 expect(entry).toBeVisible();expect(screen.getByLabelText('模块：缩放公式所在小节')).toBeVisible();
 expect(screen.queryByLabelText('模块：未修订的普通章节')).toBeNull();
 expect(screen.queryByLabelText('公式：未修订的另一公式')).toBeNull();
 expect(api.graph.mock.calls.every(([project,query])=>project==='p'&&query.source_id==='s1'&&!query.q)).toBe(true);
 fireEvent.click(entry);expect(select).toHaveBeenCalledWith(corrected);
});

test('the content list exposes structural formulas while following the current project and source API scope',async()=>{
 const structural={...node('parsed-formula','formula','原文结构公式','paper'),metadata:{structural:true}};
 const current={...graph,nodes:[nodes[0],nodes[1],structural],edges:[],total_nodes:3,total_edges:0};
 const other={...node('other-formula','formula','另一个课题的公式',null),project_id:'other',source_id:'other-source',metadata:{structural:true}};
 api.graph.mockImplementation(async(project,query)=>project==='p'&&query.source_id==='s1'?current:project==='other'&&query.source_id==='other-source'?{nodes:[other],edges:[],total_nodes:1,total_edges:0,truncated:false}:{nodes:[],edges:[],total_nodes:0,total_edges:0,truncated:false});
 const props={onNode:vi.fn(),onLearn:vi.fn(),onEvidence:vi.fn(),onSource:vi.fn(),revision:0,onUpdated:vi.fn()};
 const view=render(<KnowledgeGraphView {...props} projectId="p" sourceId="s1" sources={[source]}/>);
 await screen.findByLabelText('方法：Coordinated policy');
 expect(screen.queryByLabelText('公式：原文结构公式')).toBeNull();
 fireEvent.click(screen.getByRole('button',{name:'内容列表'}));
 expect(await screen.findByLabelText('公式：原文结构公式')).toBeVisible();
 expect(screen.queryByLabelText('公式：另一个课题的公式')).toBeNull();
 view.rerender(<KnowledgeGraphView {...props} projectId="other" sourceId="other-source"/>);
 await screen.findByLabelText('公式：另一个课题的公式');
 fireEvent.click(screen.getByRole('button',{name:'内容列表'}));
 expect(screen.getByLabelText('公式：另一个课题的公式')).toBeVisible();
 expect(screen.queryByLabelText('公式：原文结构公式')).toBeNull();
 expect(api.graph.mock.calls.some(([project,query])=>project==='other'&&query.source_id==='other-source')).toBe(true);
});
