import {useCallback,useEffect,useLayoutEffect,useMemo,useRef,useState} from 'react';
import {Alert,Button,Input,Select,Space,Spin,Tag,Switch} from 'antd';
import {CloseOutlined,FilterOutlined,FullscreenOutlined,MinusOutlined,PlusOutlined} from '@ant-design/icons';
import {getKnowledgeGraph,getKnowledgeNode,mergeKnowledgeNodes,nodeKindLabels,originLabels,patchKnowledgeEdge,patchKnowledgeNode,researchStatusLabels,splitKnowledgeNode} from '../../api/knowledge';
import type {KnowledgeEdge,KnowledgeEvidence,KnowledgeGraph as Graph,KnowledgeNode,KnowledgeSource,NodeDetail} from '../../api/knowledge';
import MathText,{damagedMathText} from '../learning/MathText';
import {EvidenceList} from './KnowledgeSources';
import {layoutFocusGraph,placeEdgeLabels,routeGraphEdges,selectGraphScene,NODE_WIDTH,NODE_HEIGHT,wrapNodeLabel as labelLines} from './KnowledgeGraphLayout';
import KnowledgePathPanel from './KnowledgePathPanel';
import {getUnifiedEdge,type KnowledgePath} from '../../api/unifiedGraph';
import LearningProgress from './LearningProgress';
import NodeQuestion from './NodeQuestion';
import './knowledge-graph-flat.css';

const progressLabels:Record<string,string>={not_started:'待学习',in_progress:'学习中',understood:'自评理解',review:'需复习'};
const SOURCE_KINDS=new Set(['paper','report','results','code']);
export interface GraphScene {scope:string;search:string;query:string;kind:string;focus:string;zoom:number;includeHidden:boolean;showStructure:boolean;scrollLeft:number;scrollTop:number;displayMode?:'graph'|'list'}
export function layoutGraph(graph:Graph,_narrow=false){
 return layoutFocusGraph(graph,undefined,_narrow);
}
export function NodeBadges({node}:{node:KnowledgeNode}){return <Space size={4} wrap><Tag>{nodeKindLabels[node.kind]||node.kind}</Tag><Tag>{originLabels[node.origin]||node.origin}</Tag>{node.research_status&&node.research_status!=='unknown'&&node.research_status!=='unspecified'&&<Tag>{researchStatusLabels[node.research_status]||node.research_status}</Tag>}{node.source_missing&&<Tag color="warning">来源已移除</Tag>}{node.metadata.missing_source===true&&<Tag color="warning">待补充来源</Tag>}{typeof node.metadata.reported_at==='string'&&node.metadata.reported_at&&<Tag>报告记录：{node.metadata.reported_at}</Tag>}{node.hidden&&<Tag>已隐藏</Tag>}</Space>;}
function EdgeEditor({edge,projectId,onSaved,onClose,onEvidence}:{edge:KnowledgeEdge;projectId:string;onSaved:()=>void;onClose:()=>void;onEvidence:(e:KnowledgeEvidence)=>void}){
 const [label,setLabel]=useState(edge.label),[explanation,setExplanation]=useState(edge.explanation),[busy,setBusy]=useState(false),[error,setError]=useState(''),[evidence,setEvidence]=useState<KnowledgeEvidence[]>([]);
 useEffect(()=>{const c=new AbortController();setEvidence([]);void getUnifiedEdge(edge.id,c.signal).then(detail=>{if(!c.signal.aborted)setEvidence(detail.evidence||[])}).catch(e=>{if(!c.signal.aborted)setError('关系来源暂时无法载入：'+String(e))});return()=>c.abort()},[projectId,edge.id]);
 const save=async(hidden=edge.hidden)=>{setBusy(true);setError('');try{await patchKnowledgeEdge(projectId,edge.id,{expected_version:edge.version,label,explanation,hidden});onSaved();onClose()}catch(e){setError(String(e))}finally{setBusy(false)}};
 return <section className="kw-edge-editor"><div className="kw-section-heading"><h3>关系依据与修订</h3><Button type="text" onClick={onClose}>关闭</Button></div><Space wrap><Tag>{originLabels[edge.origin]||edge.origin}</Tag>{edge.source_missing&&<Tag color="warning">来源已移除</Tag>}{edge.hidden&&<Tag>已隐藏</Tag>}</Space><label>关系名称<Input value={label} onChange={e=>setLabel(e.target.value)} maxLength={200}/></label><label>关系说明<Input.TextArea rows={5} value={explanation} onChange={e=>setExplanation(e.target.value)}/></label><EvidenceList items={evidence} onOpen={onEvidence}/>{error&&<Alert type="error" message={error}/>}<Space><Button type="primary" loading={busy} onClick={()=>void save()}>保存关系</Button><Button disabled={busy} onClick={()=>void save(!edge.hidden)}>{edge.hidden?'恢复关系':'隐藏关系'}</Button></Space></section>;
}
export function NodeInspector({projectId,nodeId,onNode,onLearn,onEvidence,onSource,onUpdated,allNodes=[],onClose,onCompare,onPractice,onExpand}:{projectId:string;nodeId:string;onNode:(node:KnowledgeNode)=>void;onLearn:(id:string,section?:'resources')=>void;onEvidence:(e:KnowledgeEvidence)=>void;onSource:(id:string)=>void;onUpdated:()=>void;allNodes?:KnowledgeNode[];onClose?:()=>void;onCompare?:(node:KnowledgeNode)=>void;onPractice?:(id:string)=>void;onExpand?:(id:string)=>void}){
 const [detail,setDetail]=useState<NodeDetail>(),[error,setError]=useState(''),[revision,setRevision]=useState(0),[editing,setEditing]=useState(false),[label,setLabel]=useState(''),[summary,setSummary]=useState(''),[latex,setLatex]=useState(''),[status,setStatus]=useState('unspecified'),[busy,setBusy]=useState(false),[merge,setMerge]=useState<string>(),[edge,setEdge]=useState<KnowledgeEdge>();
 useEffect(()=>{const c=new AbortController();setDetail(undefined);setError('');setEditing(false);setEdge(undefined);getKnowledgeNode(projectId,nodeId,c.signal).then(d=>{if(c.signal.aborted)return;setDetail(d);setLabel(d.node.label);setSummary(d.node.summary);setLatex(typeof d.node.metadata.latex==='string'?d.node.metadata.latex:'');setStatus(d.node.research_status||'unspecified')}).catch(e=>{if(!c.signal.aborted)setError(String(e))});return()=>c.abort()},[projectId,nodeId,revision]);
 const update=()=>{setRevision(v=>v+1);onUpdated()};
 const action=async(fn:()=>Promise<unknown>)=>{setBusy(true);setError('');try{await fn();setEditing(false);update()}catch(e){setError(e instanceof Error?e.message:String(e))}finally{setBusy(false)}};
 if(!detail)return <aside className="kw-node-inspector" aria-label="知识节点详情"><Button className="kw-inspector-close" type="text" aria-label="关闭节点详情" icon={<CloseOutlined/>} onClick={onClose}/>{error?<Alert type="error" message={error} action={<Button onClick={()=>setRevision(v=>v+1)}>重试</Button>}/>:<div className="kw-loading"><Spin/><span role="status">读取节点与依据…</span></div>}</aside>;
 const {node}=detail;
 return <aside className="kw-node-inspector" aria-label="知识节点详情"><Button className="kw-inspector-close" type="text" aria-label="关闭节点详情" icon={<CloseOutlined/>} onClick={onClose}/><NodeBadges node={node}/><h2>{node.label}</h2>{error&&<Alert type="error" message={error}/>}
 {editing?<div className="kw-edit-form"><label>节点名称<Input aria-label="节点名称" value={label} onChange={e=>setLabel(e.target.value)}/></label><label>节点解释<Input.TextArea aria-label="节点解释" rows={7} value={summary} onChange={e=>setSummary(e.target.value)}/></label>{node.kind==='formula'&&<label>公式 LaTeX<Input.TextArea aria-label="公式 LaTeX" rows={4} value={latex} onChange={e=>setLatex(e.target.value)} maxLength={10000}/><small>对照原文修改公式，修订保存在本空间。</small>{latex&&<MathText text={'$$'+latex+'$$'}/>}</label>}<label>研究状态<Select aria-label="研究状态" value={status} onChange={setStatus} options={Object.entries(researchStatusLabels).map(([value,label])=>({value,label}))}/></label><Space><Button type="primary" loading={busy} onClick={()=>void action(()=>patchKnowledgeNode(projectId,node.id,{expected_version:node.version,label,summary,research_status:status,...(node.kind==='formula'?{latex}:{})}))}>保存修订</Button><Button onClick={()=>setEditing(false)}>取消</Button></Space></div>:<>{node.summary?.trim()&&<div className="kw-node-summary"><MathText text={node.summary}/></div>}{typeof node.metadata.latex==='string'&&<MathText text={'$$'+node.metadata.latex+'$$'}/>}<div className="kw-node-actions"><Button type="primary" onClick={()=>onLearn(node.id)}>深入学习</Button><Button onClick={()=>onLearn(node.id,'resources')}>学习资源</Button><Button onClick={()=>detail.evidence?.[0]?onEvidence(detail.evidence[0]):onSource(node.source_id)}>阅读原文</Button>{onCompare&&<Button onClick={()=>onCompare(node)}>方法比较</Button>}{onPractice&&<Button onClick={()=>onPractice(node.id)}>动态练习</Button>}</div><div className="kw-node-secondary"><Button size="small" type="text" onClick={()=>onExpand?.(node.id)}>查看关联</Button><Button size="small" type="text" onClick={()=>setEditing(true)}>修订内容</Button></div></>}
 <LearningProgress key={node.id} projectId={projectId} nodeId={node.id} onUpdated={onUpdated}/>
 <details className="kw-node-question"><summary>围绕当前知识提问</summary><NodeQuestion key={node.id} projectId={projectId} nodeId={node.id} onEvidence={onEvidence} onNode={id=>{const found=allNodes.find(n=>n.id===id)||detail.neighbors.find(n=>n.id===id);if(found)onNode(found)}}/></details>
 {!!detail.prerequisites?.length&&<section><h3>前置知识</h3><ul className="kw-node-links">{detail.prerequisites.map(n=><li key={n.id}><button onClick={()=>onNode(n)}>{n.label}</button></li>)}</ul></section>}
 {!!detail.evidence?.length&&<details className="kw-node-evidence"><summary>原文依据 · {detail.evidence.length} 处</summary><EvidenceList items={detail.evidence} onOpen={onEvidence}/></details>}
 {!!detail.neighbors?.length&&<details className="kw-neighbor-details"><summary>相邻知识 · {detail.neighbors.length} 个</summary><ul className="kw-node-links">{detail.neighbors.map(n=><li key={n.id}><button onClick={()=>onNode(n)}>{n.label}</button><small>{nodeKindLabels[n.kind]||n.kind}</small></li>)}</ul></details>}
 {!!detail.edges?.length&&<details className="kw-relations"><summary>查看与修订关系</summary>{detail.edges.map(e=><button key={e.id} onClick={()=>setEdge(e)}><span>{e.label}</span><small>{e.explanation||originLabels[e.origin]}</small></button>)}</details>}{edge&&<EdgeEditor key={edge.id} projectId={projectId} edge={edge} onClose={()=>setEdge(undefined)} onSaved={update} onEvidence={onEvidence}/>}
 <details className="kw-node-maintenance"><summary>节点整理</summary><p>合并仅影响当前空间，原始来源和成员保留。</p><Select aria-label="选择要合并的节点" value={merge} onChange={setMerge} placeholder="选择另一个节点" showSearch optionFilterProp="label" options={allNodes.filter(n=>n.id!==node.id&&n.kind===node.kind).map(n=>({value:n.id,label:n.label}))}/><Space wrap><Button disabled={!merge||busy} onClick={()=>void action(async()=>{const merged=await mergeKnowledgeNodes(projectId,[node.id,merge!],node.label);if(merged?.id)onNode(merged)})}>合并节点</Button><Button disabled={busy} onClick={()=>void action(()=>splitKnowledgeNode(projectId,node.id))}>拆分已合并成员</Button><Button disabled={busy} onClick={()=>void action(()=>patchKnowledgeNode(projectId,node.id,{expected_version:node.version,hidden:!node.hidden}))}>{node.hidden?'恢复显示':'隐藏节点'}</Button></Space></details>
 </aside>;
}

interface GraphProps {
 projectId:string;sourceId?:string;nodeId?:string;sources?:KnowledgeSource[];
 onNode:(node:KnowledgeNode)=>void;onLearn:(id:string,section?:'resources')=>void;onEvidence:(e:KnowledgeEvidence)=>void;onSource:(id:string)=>void;
 onScope?:(id?:string)=>void;onClear?:()=>void;onCompare?:(node:KnowledgeNode)=>void;onPractice?:(id:string)=>void;onReturn?:()=>void;onImport?:()=>void;
 revision:number;onUpdated:()=>void;initialScene?:GraphScene;onSceneChange?:(scene:GraphScene)=>void;
}
export default function KnowledgeGraphView({projectId,sourceId,nodeId,sources=[],onScope,onNode,onClear,onLearn,onCompare,onPractice,onReturn,onImport,onEvidence,onSource,revision,onUpdated,initialScene,onSceneChange}:GraphProps){
 const scope=projectId+'/'+(sourceId||'all');
 // A scene is restored only when entering this canvas. Parent refreshes can
 // already contain our first (unmeasured) save and must not cancel initial fit.
 const entryScene=useRef({scope,scene:initialScene?.scope===scope?initialScene:undefined});
 if(entryScene.current.scope!==scope)entryScene.current={scope,scene:undefined};
 const initial=entryScene.current.scene;
 const [progressByNode,setProgressByNode]=useState<Record<string,string>>({});
 useEffect(()=>{setProgressByNode({});const listener=(event:Event)=>{const d=(event as CustomEvent).detail;if(d?.projectId===projectId)setProgressByNode(old=>({...old,[d.nodeId]:d.status}))};window.addEventListener('paperstride:learning-progress',listener);return()=>window.removeEventListener('paperstride:learning-progress',listener)},[projectId]);
 const [pathGraph,setPathGraph]=useState<KnowledgePath>();
 const [graph,setGraph]=useState<Graph>(),[error,setError]=useState(''),[loading,setLoading]=useState(true);
 const [search,setSearch]=useState(initial?.search||''),[query,setQuery]=useState(initial?.query||''),[kind,setKind]=useState(initial?.kind||'');
 // Selection opens details; it never implicitly narrows the diagram.
 const [focus,setFocus]=useState(initial?initial.focus:nodeId||''),[displayMode,setDisplayMode]=useState<'graph'|'list'>(initial?.displayMode||'graph');
 const [zoom,setZoom]=useState(initial?.zoom||1),[edge,setEdge]=useState<KnowledgeEdge>(),[retry,setRetry]=useState(0);
 const [includeHidden,setIncludeHidden]=useState(initial?.includeHidden||false),[showStructure,setShowStructure]=useState(initial?.showStructure||false),[filtersOpen,setFiltersOpen]=useState(false);
 const [fetchLimit,setFetchLimit]=useState(240);
 const [hover,setHover]=useState(''),[hoverEdge,setHoverEdge]=useState(''),[listLimit,setListLimit]=useState(40);
 const [canvasWidth,setCanvasWidth]=useState(0),[canvasHeight,setCanvasHeight]=useState(600),[narrow,setNarrow]=useState(window.innerWidth<800);
 const canvas=useRef<HTMLDivElement>(null),scopeRef=useRef(scope),restored=useRef(false),drag=useRef<{x:number;y:number;left:number;top:number}>(),scene=useRef<GraphScene>();
 const initialScroll=useRef({left:initial?.scrollLeft||0,top:initial?.scrollTop||0});
 useEffect(()=>{
  if(scopeRef.current===scope)return;
  scopeRef.current=scope;restored.current=false;initialScroll.current={left:0,top:0};scene.current=undefined;
  setFetchLimit(240);setGraph(undefined);setPathGraph(undefined);setFocus('');setEdge(undefined);setSearch('');setQuery('');setKind('');setZoom(1);setHover('');setListLimit(40);
 },[scope]);
 const contextId=!sourceId&&!query&&!kind?focus||undefined:undefined;
 useEffect(()=>{
  const c=new AbortController();setLoading(true);setError('');
  getKnowledgeGraph(projectId,{source_id:sourceId,node_id:contextId,q:query,kind:kind||undefined,
   limit:fetchLimit,include_hidden:includeHidden,overview:false},c.signal)
   .then(value=>{if(c.signal.aborted)return;if(!Array.isArray(value.nodes)||!Array.isArray(value.edges))throw new Error('图谱服务未返回可用的节点与关系');setGraph(value)})
   .catch(e=>{if(!c.signal.aborted)setError(e instanceof Error?e.message:String(e))}).finally(()=>{if(!c.signal.aborted)setLoading(false)});
  return()=>c.abort();
 },[projectId,sourceId,contextId,query,kind,revision,retry,includeHidden,fetchLimit]);
 const available=useMemo(()=>{
  if(!graph)return {nodes:[],edges:[],total_nodes:0,total_edges:0,truncated:false};
  const semantic=graph.nodes.filter(n=>n.id===focus||!n.metadata?.structural||SOURCE_KINDS.has(n.kind));
  const nodes=showStructure||!semantic.some(n=>!SOURCE_KINDS.has(n.kind))?graph.nodes:semantic;
  const ids=new Set(nodes.map(n=>n.id));return {...graph,nodes,edges:graph.edges.filter(e=>ids.has(e.source)&&ids.has(e.target))};
 },[graph,showStructure,focus]);
 const browse=useMemo(()=>selectGraphScene(available,sourceId,focus,narrow?6:9),[available,sourceId,focus,narrow]);
 const displayed=pathGraph?{...browse.graph,nodes:pathGraph.nodes,edges:pathGraph.edges}:browse.graph;
 const layout=useMemo(()=>layoutFocusGraph(displayed,browse.center?.id,narrow),[displayed,browse.center?.id,narrow]);
 const routes=useMemo(()=>routeGraphEdges(displayed,layout),[displayed,layout]);
 const saveScene=useCallback(()=>{
  const value={scope,search,query,kind,focus,zoom,includeHidden,showStructure,displayMode,
   scrollLeft:canvas.current?.scrollLeft??scene.current?.scrollLeft??initialScroll.current.left,
   scrollTop:canvas.current?.scrollTop??scene.current?.scrollTop??initialScroll.current.top};
  scene.current=value;onSceneChange?.(value);
 },[scope,search,query,kind,focus,zoom,includeHidden,showStructure,displayMode,onSceneChange]);
 useEffect(()=>{saveScene()},[saveScene]);
 useLayoutEffect(()=>{
  const element=canvas.current;if(!element)return;
  const measure=()=>{setCanvasWidth(element.clientWidth);setNarrow(window.innerWidth<800);setCanvasHeight(Math.max(320,window.innerHeight-element.getBoundingClientRect().top-(window.innerWidth<800?140:90)))};
  measure();window.addEventListener('resize',measure);
  const observer=new ResizeObserver(measure);observer.observe(element);
  const workspace=element.closest('.kw-workspace');if(workspace)observer.observe(workspace);
  return()=>{window.removeEventListener('resize',measure);observer.disconnect()};
 },[graph?.nodes.length,nodeId,filtersOpen,error,loading,displayMode]);
 useLayoutEffect(()=>{
  if(!graph||!canvas.current||restored.current)return;
  canvas.current.scrollLeft=initialScroll.current.left;canvas.current.scrollTop=initialScroll.current.top;restored.current=true;
  if(!initial&&nodeId){const point=layout.points.get(nodeId);if(point){canvas.current.scrollLeft=Math.max(0,point.x*zoom-80);canvas.current.scrollTop=Math.max(0,point.y*zoom-80)}}
 },[graph,layout,zoom,nodeId,initial,displayMode]);
 const activeNode=nodeId||hover;
 const relatedEdges=useMemo(()=>new Set(displayed.edges.filter(e=>e.source===activeNode||e.target===activeNode).map(e=>e.id)),[displayed.edges,activeNode]);
 const labels=useMemo(()=>placeEdgeLabels(routes,layout,new Set(edge||hoverEdge?[edge?.id||hoverEdge]:activeNode?[...relatedEdges].slice(0,5):displayed.edges.filter(e=>!['CONTAINS','HAS_PART','MENTIONS'].includes(e.kind)).slice(0,4).map(e=>e.id))),[routes,layout,edge,hoverEdge,activeNode,relatedEdges,displayed.edges]);
 const reset=()=>{const element=canvas.current;setZoom(element?Math.max(.3,Math.min(1,(element.clientWidth-16)/layout.width,narrow?1:(element.clientHeight-16)/layout.height)):1);if(element){element.scrollLeft=0;element.scrollTop=0}};
 useLayoutEffect(()=>{if(!initial&&graph&&canvas.current&&displayMode==='graph')reset()},[layout.width,layout.height,sourceId,displayMode,narrow,!!graph,canvasWidth,canvasHeight]);
 const clearContext=()=>{setPathGraph(undefined);setFocus('');setEdge(undefined);restored.current=false;initialScroll.current={left:0,top:0}};
 const pick=(node:KnowledgeNode)=>{
  setEdge(undefined);
  if(SOURCE_KINDS.has(node.kind)&&!node.parent_id&&onScope){if(node.source_id===sourceId){onSource(node.source_id)}else{clearContext();onScope(node.source_id)}}
  else onNode(node);
 };
 const showRelated=(id:string)=>{setPathGraph(undefined);setFetchLimit(240);setFocus(id);setQuery('');setSearch('');setKind('');setDisplayMode('graph');setEdge(undefined);restored.current=false;initialScroll.current={left:0,top:0}};
 const listNodes=available.nodes.slice(0,listLimit);
 const sourceName=sources.find(s=>s.id===sourceId)?.title;
 const switchMode=(mode:'graph'|'list')=>{if(mode===displayMode)return;saveScene();restored.current=false;initialScroll.current={left:scene.current?.scrollLeft||0,top:scene.current?.scrollTop||0};setListLimit(40);if(mode==='list')setFocus('');setDisplayMode(mode)};
 const submitSearch=(value:string)=>{setFetchLimit(240);clearContext();onClear?.();setListLimit(40);setQuery(value.trim())};
 return <section className="kw-graph-view kw-flat-graph" aria-label="研究图谱主画布">
  <div className="kw-graph-tools kw-canvas-tools">
   {onReturn&&<Button type="text" onClick={onReturn}>返回原位置</Button>}
   <Input.Search aria-label="搜索图谱知识" value={search} onChange={event=>{setSearch(event.target.value);if(!event.target.value){setQuery('');setFocus('')}}} onSearch={submitSearch} allowClear placeholder="搜索方法、概念或公式"/>
   {!!sources.length&&<Select className="kw-graph-source-scope" aria-label="图谱范围" value={sourceId||'all'} showSearch optionFilterProp="label" onChange={id=>{clearContext();onScope?.(id==='all'?undefined:id)}} options={[{value:'all',label:'整个研究空间'},...sources.map(source=>({value:source.id,label:source.title}))]}/>}
   <Button type={filtersOpen?'default':'text'} icon={<FilterOutlined/>} aria-expanded={filtersOpen} aria-controls="kw-graph-filters" onClick={()=>setFiltersOpen(v=>!v)}>筛选</Button>
   <div className="kw-graph-display-switch" role="group" aria-label="图谱浏览方式">
    <button aria-pressed={displayMode==='graph'} onClick={()=>switchMode('graph')}>关系图</button>
    <button aria-pressed={displayMode==='list'} onClick={()=>switchMode('list')}>内容列表</button>
   </div>
  </div>
  {(sourceId||focus)&&<div className="kw-graph-viewbar">
   <nav className="kw-graph-breadcrumb" aria-label="图谱浏览层级">
    <button aria-current={!sourceId?'page':undefined} onClick={()=>{clearContext();if(onScope)onScope(undefined);else onClear?.()}}>研究空间</button>
    {sourceId&&<><span aria-hidden="true">/</span><span className="kw-current-source" title={sourceName}>{sourceName||'资料全景'}</span></>}
    {focus&&<Button type="text" size="small" onClick={clearContext}>退出关联视图</Button>}
   </nav>
  </div>}
  {filtersOpen&&<div className="kw-graph-filters" id="kw-graph-filters"><label>知识类型<Select aria-label="图谱节点类型" value={kind} onChange={value=>{setFocus('');setKind(value)}} options={[{value:'',label:'全部'},...Object.entries(nodeKindLabels).map(([value,label])=>({value,label}))]}/></label><label><Switch size="small" aria-label="显示已隐藏知识" checked={includeHidden} onChange={setIncludeHidden}/>已隐藏内容</label><label><Switch size="small" aria-label="显示文档结构" checked={showStructure} onChange={setShowStructure}/>章节结构</label></div>}
  {!!graph?.nodes.length&&<KnowledgePathPanel key={scope} projectId={projectId} nodes={graph.nodes} currentNode={nodeId} onNode={onNode} onResult={value=>{setPathGraph(value);setDisplayMode('graph')}}/>}
  {error&&<Alert type="error" message="图谱暂时无法加载" description={error} action={<Button aria-label="重试加载图谱" onClick={()=>setRetry(v=>v+1)}>重试</Button>}/>}
  <div className={'kw-graph-layout '+(nodeId?'kw-has-inspector':'')+(edge?' kw-has-editor':'')}>
   <div className="kw-graph-primary">
    {displayMode==='graph'?<>
     <div ref={canvas} className="kw-graph-canvas" style={{height:canvasHeight}} tabIndex={0} aria-label="研究知识图谱画布" onScroll={saveScene}
      onKeyDown={event=>{if(event.key==='Escape'){onClear?.();setEdge(undefined)}}}
      onPointerDown={event=>{if(event.button!==0||(event.target as Element).closest('.kw-graph-node,.kw-graph-edge,button'))return;drag.current={x:event.clientX,y:event.clientY,left:event.currentTarget.scrollLeft,top:event.currentTarget.scrollTop};event.currentTarget.setPointerCapture?.(event.pointerId)}}
      onPointerMove={event=>{if(!drag.current)return;event.currentTarget.scrollLeft=drag.current.left-(event.clientX-drag.current.x);event.currentTarget.scrollTop=drag.current.top-(event.clientY-drag.current.y)}}
      onPointerUp={()=>{drag.current=undefined}} onPointerCancel={()=>{drag.current=undefined}}>
      {loading&&<div className="kw-graph-loading" role="status"><Spin size="small"/><span>读取研究知识…</span></div>}
      {!!displayed.nodes.length?<svg style={{maxWidth:'none'}} width={layout.width*zoom} height={layout.height*zoom} viewBox={'0 0 '+layout.width+' '+layout.height} role="group" aria-label="问题、方法、知识与来源组成的研究图谱">
       <defs><marker id="kw-arrow" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto"><path d="M0 0 L6 3 L0 6" fill="currentColor"/></marker></defs>
       {layout.lanes.map(lane=><g key={lane.kind} className="kw-graph-lane" aria-hidden="true"><text x={lane.x} y="29">{lane.label}</text></g>)}
       {routes.map(route=>{
        const e=route.edge,related=relatedEdges.has(e.id),selected=edge?.id===e.id,label=labels.get(e.id);
        return <g key={e.id} className={'kw-graph-edge '+(selected||related?'kw-related-edge':'')+(activeNode&&!related?' kw-muted-edge':'')} tabIndex={0} role="button" aria-label={'关系：'+e.label} onMouseEnter={()=>setHoverEdge(e.id)} onMouseLeave={()=>setHoverEdge('')} onFocus={()=>setHoverEdge(e.id)} onBlur={()=>setHoverEdge('')} onClick={()=>setEdge(e)} onKeyDown={event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();setEdge(e)}}}><title>{e.label+'\n'+e.explanation}</title><path className="kw-edge-line" fill="none" d={route.d} markerEnd="url(#kw-arrow)"/><path className="kw-edge-hit" fill="none" stroke="transparent" d={route.d}/>{label&&<g className="kw-edge-label"><rect x={label.x} y={label.y} width={label.width} height={label.height} rx="4"/><text x={label.x+label.width/2} y={label.y+15} textAnchor="middle">{label.text}</text></g>}</g>;
       })}
       {displayed.nodes.map(node=>{const point=layout.points.get(node.id);if(!point)return null;return <g key={node.id} className={'kw-graph-node '+(node.id===nodeId?'kw-selected-node ':'')+'kw-kind-'+node.kind} transform={'translate('+point.x+','+point.y+')'} tabIndex={0} role="button" aria-label={(nodeKindLabels[node.kind]||node.kind)+'：'+node.label} onClick={()=>pick(node)} onMouseEnter={()=>setHover(node.id)} onMouseLeave={()=>setHover('')} onFocus={()=>setHover(node.id)} onBlur={()=>setHover('')} onKeyDown={event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();pick(node)}}}><title>{node.label+'\n'+node.summary.slice(0,350)}</title><rect width={NODE_WIDTH} height={NODE_HEIGHT} rx="8"/><text className="kw-node-kind" x="16" y="20">{nodeKindLabels[node.kind]||node.kind}{progressLabels[progressByNode[node.id]||String(node.metadata.learning_progress||'')]?' · '+progressLabels[progressByNode[node.id]||String(node.metadata.learning_progress||'')]:''}</text><text className="kw-node-label" x="16" y="43">{labelLines(node.label).map((line,index)=><tspan key={index} x="16" dy={index?20:0}>{line}</tspan>)}</text>{!!node.evidence_ids?.length&&<text className="kw-node-evidence-count" x="16" y={NODE_HEIGHT-14}>原文依据 {node.evidence_ids.length} 处</text>}{node.source_missing&&<circle cx={NODE_WIDTH-15} cy="18" r="3" className="kw-source-warning"/>}</g>})}
      </svg>:!loading&&<section className="kw-empty"><h2>{query||kind?'没有找到匹配知识':'从你的研究资料开始'}</h2><p>{query||kind?'尝试更短的关键词，或清除筛选。':'添加论文或研究报告后，相关方法与知识会出现在这里。'}</p>{!query&&!kind&&onImport&&<Button type="primary" onClick={onImport}>添加资料并构建图谱</Button>}{(query||kind)&&<Button onClick={()=>{setSearch('');setQuery('');setKind('')}}>清除筛选</Button>}</section>}
     </div>
     <div className="kw-canvas-navigation"><span className="kw-graph-level-caption">{focus?'相关知识':sourceId?'资料全景':'空间概览'} · {displayed.nodes.length} 个关键节点</span><Space.Compact><Button aria-label="缩小图谱" icon={<MinusOutlined/>} onClick={()=>setZoom(v=>Math.max(.3,v-.15))}/><Button aria-label="重置图谱视角" onClick={reset}>{Math.round(zoom*100)}%</Button><Button aria-label="放大图谱" icon={<PlusOutlined/>} onClick={()=>setZoom(v=>Math.min(1.8,v+.15))}/><Button aria-label="展开画布" icon={<FullscreenOutlined/>} onClick={()=>canvas.current?.requestFullscreen?.()}/></Space.Compact></div>
     {!!browse.omitted.length&&<button className="kw-open-content-list" onClick={()=>switchMode('list')}>查看全部内容</button>}
    </>:<section className={'kw-content-list'+(sourceId?' kw-scoped-content':'')} aria-label="知识内容列表">
     <div className="kw-content-list-status">{loading?<span role="status">读取内容…</span>:<span>已载入 {available.nodes.length} 项内容{graph?.truncated?' · 可继续载入或缩小范围':''}</span>}</div>
     <ul>{listNodes.map(node=><li key={node.id}><button className={node.id===nodeId?'kw-current-content':undefined} aria-label={(nodeKindLabels[node.kind]||node.kind)+'：'+node.label} onClick={()=>pick(node)}><span className="kw-content-list-kind">{nodeKindLabels[node.kind]||node.kind}</span><span className="kw-content-list-body"><strong>{node.label}</strong>{node.summary?.trim()&&node.kind!=='formula'&&!damagedMathText(node.summary)&&<span><MathText text={node.summary}/></span>}</span>{!sourceId&&<small>{sources.find(s=>s.id===node.source_id)?.title}</small>}</button></li>)}</ul>
     {!loading&&!listNodes.length&&<p>没有找到匹配内容。</p>}
     {graph?.truncated&&available.nodes.length<=listLimit&&(fetchLimit<2000?<Button loading={loading} onClick={()=>{setFetchLimit(v=>Math.min(2000,v+240));setListLimit(v=>v+240)}}>继续载入知识</Button>:<p>当前已达单次浏览上限，请选择资料或搜索关键词继续定位。</p>)}
     {available.nodes.length>listLimit&&<Button onClick={()=>setListLimit(value=>value+40)}>显示更多内容</Button>}
    </section>}
   </div>
   {nodeId&&<NodeInspector key={projectId+nodeId} projectId={projectId} nodeId={nodeId} onNode={onNode} onLearn={onLearn} onEvidence={onEvidence} onSource={onSource} onUpdated={onUpdated} allNodes={graph?.nodes||[]} onClose={onClear} onCompare={onCompare} onPractice={onPractice} onExpand={showRelated}/>}
   {edge&&<div className="kw-relation-dock"><EdgeEditor key={edge.id} edge={edge} projectId={projectId} onClose={()=>setEdge(undefined)} onSaved={onUpdated} onEvidence={onEvidence}/></div>}
  </div>
 </section>;
}
