import {useCallback,useEffect,useLayoutEffect,useMemo,useRef,useState} from 'react';
import {Alert,Button,Input,Select,Space,Spin,Switch} from 'antd';
import {FilterOutlined,FullscreenOutlined,MinusOutlined,PlusOutlined} from '@ant-design/icons';
import {getKnowledgeGraph,nodeKindLabels} from '../../api/knowledge';
import type {KnowledgeEdge,KnowledgeEvidence,KnowledgeGraph as Graph,KnowledgeNode,KnowledgeSource} from '../../api/knowledge';
import MathText,{damagedMathText} from '../learning/MathText';
import {NodeInspector,EdgeEditor} from './NodeInspector';
export {NodeInspector,NodeBadges} from './NodeInspector';
import {layoutFocusGraph,placeEdgeLabels,routeGraphEdges,selectGraphScene,selectQuestionGraphScene,NODE_WIDTH,NODE_HEIGHT,wrapNodeLabel as labelLines} from './KnowledgeGraphLayout';
import KnowledgePathPanel from './KnowledgePathPanel';
import {type KnowledgePath} from '../../api/unifiedGraph';
import type {SavedLearningRoute} from '../../api/knowledgeRoutes';
import {routeStepLabel,selectSavedRouteGraph} from './SavedRouteGraph';
import './saved-route-graph.css';
import './knowledge-graph-flat.css';
import {applyNodePositions,dragPosition,resolveNodeDrop,restoreNodeLayouts,type NodePosition,type NodePositions,type ScopedNodePositions} from './GraphInteraction';
import './graph-interactions.css';
import ProjectForceGraph from './ProjectForceGraph';
import {useCurrentAccount} from '../SessionContext';
import GraphSplitLayout from './GraphSplitLayout';

const progressLabels:Record<string,string>={not_started:'待学习',in_progress:'学习中',understood:'自评理解',review:'需复习'};
const SOURCE_KINDS=new Set(['paper','report','results','code']);
const EMPTY_POSITIONS:NodePositions={};
export type GraphDisplayMode='graph'|'network'|'list';
export interface GraphScene {scope:string;search:string;query:string;kind:string;focus:string;zoom:number;includeHidden:boolean;showStructure:boolean;scrollLeft:number;scrollTop:number;displayMode?:GraphDisplayMode;layouts?:ScopedNodePositions;edgeId?:string;anchorId?:string}
function preferredPresentation(account:string|undefined,project:string):GraphDisplayMode{
 try{return localStorage.getItem(`paperstride:${account||'local'}:graph-presentation:${project}`)==='network'?'network':'graph'}catch{return 'graph'}
}
export function layoutGraph(graph:Graph,_narrow=false){
 return layoutFocusGraph(graph,undefined,_narrow);
}

interface GraphProps {
 projectId:string;sourceId?:string;nodeId?:string;sources?:KnowledgeSource[];
 onNode:(node:KnowledgeNode)=>void;onLearn:(id:string,section?:'resources')=>void;onEvidence:(e:KnowledgeEvidence)=>void;onSource:(id:string)=>void;
 onScope?:(id?:string)=>void;onClear?:()=>void;onCompare?:(node:KnowledgeNode)=>void;onPractice?:(id:string,mappingId?:string)=>void;onReturn?:()=>void;onImport?:()=>void;onCreateNode?:()=>void;
 revision:number;onUpdated:()=>void;initialScene?:GraphScene;initialLayouts?:ScopedNodePositions;onSceneChange?:(scene:GraphScene)=>boolean|void;
 question?:string;questionFocused?:boolean;onGraphData?:(graph:Graph)=>void;onInspectChange?:(inspecting:boolean)=>void;
 learningRoute?:SavedLearningRoute;routeFocused?:boolean;onExitRoute?:()=>void;
}
export default function KnowledgeGraphView({projectId,sourceId,nodeId,sources=[],onScope,onNode,onClear,onLearn,onCompare,onPractice,onReturn,onImport,onCreateNode,onEvidence,onSource,revision,onUpdated,initialScene,initialLayouts,onSceneChange,question='',questionFocused=false,onGraphData,onInspectChange,learningRoute,routeFocused=false,onExitRoute}:GraphProps){
 const account=useCurrentAccount();
 const scope=projectId+'/'+(sourceId||'all');
 const layoutScope=routeFocused&&learningRoute?projectId+'/route:'+learningRoute.id:scope;
 // A scene is restored only when entering this canvas. Parent refreshes can
 // already contain our first (unmeasured) save and must not cancel initial fit.
 const entryScene=useRef({scope,scene:initialScene?.scope===scope?initialScene:undefined});
 if(entryScene.current.scope!==scope)entryScene.current={scope,scene:undefined};
 const initial=entryScene.current.scene;
 const [manualLayouts,setManualLayouts]=useState<ScopedNodePositions>(()=>restoreNodeLayouts(initialLayouts||initialScene?.layouts,projectId));
 const [arranging,setArranging]=useState(false),[layoutNotice,setLayoutNotice]=useState(''),[undoLayouts,setUndoLayouts]=useState<NodePositions[]>([]);
 const [layoutSaveError,setLayoutSaveError]=useState(false);
 const [dragPreview,setDragPreview]=useState<{id:string;point:NodePosition}>();
 const nodeDrag=useRef<{id:string;pointerId:number;clientX:number;clientY:number;scrollLeft:number;scrollTop:number;start:NodePosition;point:NodePosition;moved:boolean}>();
 const suppressClick=useRef<{id:string;until:number}>();
 const previewFrame=useRef<number>();
 const positions=manualLayouts[layoutScope]||EMPTY_POSITIONS;
 useEffect(()=>{setArranging(false);setUndoLayouts([]);setDragPreview(undefined);nodeDrag.current=undefined},[layoutScope]);
 useEffect(()=>()=>{if(previewFrame.current!==undefined)cancelAnimationFrame(previewFrame.current)},[]);
 const [progressByNode,setProgressByNode]=useState<Record<string,string>>({});
 useEffect(()=>{setProgressByNode({});const listener=(event:Event)=>{const d=(event as CustomEvent).detail;if(d?.projectId===projectId)setProgressByNode(old=>({...old,[d.nodeId]:d.status}))};window.addEventListener('paperstride:learning-progress',listener);return()=>window.removeEventListener('paperstride:learning-progress',listener)},[projectId]);
 const [pathGraph,setPathGraph]=useState<KnowledgePath>();
 const [graph,setGraph]=useState<Graph>(),[error,setError]=useState(''),[loading,setLoading]=useState(true);
 const [search,setSearch]=useState(initial?.search||''),[query,setQuery]=useState(initial?.query||''),[kind,setKind]=useState(initial?.kind||'');
 // Selection opens details; it never implicitly narrows the diagram.
 const [focus,setFocus]=useState(initial?initial.focus:nodeId||''),[displayMode,setDisplayMode]=useState<GraphDisplayMode>(initial?.displayMode||preferredPresentation(account?.id,projectId));
 const presentationScope=useRef((account?.id||'local')+':'+projectId);
 useEffect(()=>{const current=(account?.id||'local')+':'+projectId;if(current===presentationScope.current)return;presentationScope.current=current;setDisplayMode(preferredPresentation(account?.id,projectId))},[account?.id,projectId]);
 const [sceneAnchor,setSceneAnchor]=useState(initial?.anchorId===undefined?nodeId:initial.anchorId||undefined);
 const [zoom,setZoom]=useState(initial?.zoom||1),[edge,setEdge]=useState<KnowledgeEdge>(),[retry,setRetry]=useState(0);
 useEffect(()=>{onInspectChange?.(!!nodeId||!!edge)},[nodeId,edge,onInspectChange]);
 const zoomRef=useRef(zoom);zoomRef.current=zoom;
 const viewportReady=useRef({scope,initialized:!!initial}),graphScope=useRef('');
 if(viewportReady.current.scope!==scope)viewportReady.current={scope,initialized:false};
 const pendingZoom=useRef<{left:number;top:number}>();
 const [includeHidden,setIncludeHidden]=useState(initial?.includeHidden||false),[showStructure,setShowStructure]=useState(initial?.showStructure||false),[filtersOpen,setFiltersOpen]=useState(false);
 const [fetchLimit,setFetchLimit]=useState(240);
 const [hover,setHover]=useState(''),[hoverEdge,setHoverEdge]=useState(''),[listLimit,setListLimit]=useState(40);
 const [canvasWidth,setCanvasWidth]=useState(0),[canvasHeight,setCanvasHeight]=useState(600),[narrow,setNarrow]=useState(window.innerWidth<800);
 const canvas=useRef<HTMLDivElement>(null),scopeRef=useRef(scope),restored=useRef(false),drag=useRef<{x:number;y:number;left:number;top:number}>(),scene=useRef<GraphScene>();
 const initialScroll=useRef({left:initial?.scrollLeft||0,top:initial?.scrollTop||0});
 const restoreEdge=useRef(initial?.edgeId);
 const opener=useRef<Element>();
 const pathViewport=useRef<{zoom:number;left:number;top:number;mode:GraphDisplayMode}>();
 const routeViewport=useRef<{scope:string;zoom:number;left:number;top:number;mode:GraphDisplayMode;path?:KnowledgePath;edge?:KnowledgeEdge;scene?:GraphScene}>();
 const [routeRestore,setRouteRestore]=useState(0);
 const restoredFocus=useRef(false);
 useEffect(()=>{
  if(scopeRef.current===scope)return;
  scopeRef.current=scope;restored.current=false;initialScroll.current={left:0,top:0};scene.current=undefined;pendingZoom.current=undefined;
  setFetchLimit(240);setGraph(undefined);setPathGraph(undefined);setFocus('');setSceneAnchor(nodeId);setEdge(undefined);setSearch('');setQuery('');setKind('');setZoom(1);setHover('');setListLimit(40);
  restoreEdge.current=undefined;pathViewport.current=undefined;opener.current=undefined;restoredFocus.current=false;
  routeViewport.current=undefined;
  setArranging(false);setLayoutNotice('');setUndoLayouts([]);setDragPreview(undefined);nodeDrag.current=undefined;
 },[scope]);
 const contextId=!sourceId&&!query&&!kind?focus||undefined:undefined;
 useLayoutEffect(()=>{
  if(routeFocused){
   if(routeViewport.current?.scope===scope)return;
   const previousScene=scene.current||initial;
   routeViewport.current={scope,zoom:previousScene?.zoom??zoomRef.current,left:previousScene?.scrollLeft??canvas.current?.scrollLeft??0,top:previousScene?.scrollTop??canvas.current?.scrollTop??0,mode:previousScene?.displayMode||displayMode,path:pathGraph,edge,scene:previousScene};
   setPathGraph(undefined);setEdge(undefined);setHover('');setHoverEdge('');setArranging(false);setUndoLayouts([]);setDisplayMode('graph');
   viewportReady.current.initialized=false;restored.current=true;
   if(canvas.current){canvas.current.scrollLeft=0;canvas.current.scrollTop=0}
  }else if(routeViewport.current){
   const previous=routeViewport.current;routeViewport.current=undefined;
   if(previous.scope!==scope)return;
   setZoom(previous.zoom);zoomRef.current=previous.zoom;
   pendingZoom.current={left:previous.left,top:previous.top};setDisplayMode(previous.mode);setPathGraph(previous.path);setEdge(previous.edge);
   setRouteRestore(value=>value+1);
   setArranging(false);setUndoLayouts([]);viewportReady.current.initialized=true;
  }
 },[routeFocused,scope]);
 useEffect(()=>{
  if(routeFocused)return;
  const c=new AbortController();setLoading(true);setError('');
  getKnowledgeGraph(projectId,{source_id:sourceId,node_id:contextId,q:query,kind:kind||undefined,
   limit:fetchLimit,include_hidden:includeHidden,overview:false},c.signal)
   .then(value=>{if(c.signal.aborted)return;if(!Array.isArray(value.nodes)||!Array.isArray(value.edges))throw new Error('图谱服务未返回可用的节点与关系');graphScope.current=scope;setGraph(value)})
   .catch(e=>{if(!c.signal.aborted)setError(e instanceof Error?e.message:String(e))}).finally(()=>{if(!c.signal.aborted)setLoading(false)});
  return()=>c.abort();
 },[projectId,sourceId,contextId,query,kind,revision,retry,includeHidden,fetchLimit,routeFocused]);
 useEffect(()=>{if(graph)onGraphData?.(graph)},[graph,onGraphData]);
 useEffect(()=>{
  if(!graph||!restoreEdge.current)return;
  const saved=graph.edges.find(item=>item.id===restoreEdge.current);
  if(saved){setEdge(saved);restoreEdge.current=undefined}
 },[graph]);
 const available=useMemo(()=>{
  if(!graph)return {nodes:[],edges:[],total_nodes:0,total_edges:0,truncated:false};
  // User-corrected formulas are study content, even when their original PDF
  // region was structural. Preserve their real source path like a selection.
  const correctedFormulas=graph.nodes.filter(n=>n.kind==='formula'&&(n.origin==='user'||n.metadata?.recognition==='user_corrected')).map(n=>n.id);
  const required=new Set([focus,sceneAnchor,...correctedFormulas].filter((id):id is string=>!!id));
  for(const e of graph.edges)if(e.source===sceneAnchor||e.target===sceneAnchor||e.source===focus||e.target===focus){required.add(e.source);required.add(e.target)}
  const byId=new Map(graph.nodes.map(n=>[n.id,n]));
  for(const id of [...required]){let current=byId.get(id);const visited=new Set<string>();while(current?.parent_id&&!visited.has(current.id)){visited.add(current.id);required.add(current.parent_id);current=byId.get(current.parent_id)}}
  const semantic=graph.nodes.filter(n=>required.has(n.id)||!n.metadata?.structural||SOURCE_KINDS.has(n.kind));
  const nodes=showStructure||!semantic.some(n=>!SOURCE_KINDS.has(n.kind))?graph.nodes:semantic;
  const ids=new Set(nodes.map(n=>n.id));return {...graph,nodes,edges:graph.edges.filter(e=>ids.has(e.source)&&ids.has(e.target))};
 },[graph,showStructure,focus,sceneAnchor]);
 const browse=useMemo(()=>questionFocused&&question.trim()&&!query&&!kind&&!focus
  ?selectQuestionGraphScene(available,question,narrow?6:9,sceneAnchor)
  :selectGraphScene(available,sourceId,focus,narrow?6:9,sceneAnchor),[available,sourceId,focus,narrow,sceneAnchor,questionFocused,question,query,kind]);
 useEffect(()=>{
  if(routeFocused)return;
  if(nodeId&&graph?.nodes.some(node=>node.id===nodeId)&&!browse.graph.nodes.some(node=>node.id===nodeId))setSceneAnchor(nodeId);
 },[nodeId,graph,browse,routeFocused]);
 const routeGraph=useMemo(()=>learningRoute?selectSavedRouteGraph(learningRoute):{nodes:[],edges:[],total_nodes:0,total_edges:0,truncated:false},[learningRoute]);
 useEffect(()=>{if(routeFocused&&edge&&!routeGraph.edges.some(item=>item.id===edge.id))setEdge(undefined)},[routeFocused,routeGraph,edge]);
 const routeSteps=useMemo(()=>new Map(learningRoute?.steps.map((step,index)=>[step.node_id,{step,index}])||[]),[learningRoute]);
 const displayed=useMemo(()=>routeFocused?routeGraph:pathGraph?{...browse.graph,nodes:pathGraph.nodes,edges:pathGraph.edges}:browse.graph,[browse.graph,pathGraph,routeFocused,routeGraph]);
 const networkGraph=useMemo(()=>routeFocused?routeGraph:pathGraph?{...available,nodes:pathGraph.nodes,edges:pathGraph.edges}:questionFocused&&question.trim()&&!query&&!kind&&!focus?browse.graph:available,[routeFocused,routeGraph,pathGraph,available,questionFocused,question,query,kind,focus,browse.graph]);
 const automaticLayout=useMemo(()=>layoutFocusGraph(displayed,routeFocused?undefined:browse.center?.id,narrow),[displayed,browse.center?.id,narrow,routeFocused]);
 const layout=useMemo(()=>applyNodePositions(automaticLayout,dragPreview?{...positions,[dragPreview.id]:dragPreview.point}:positions),[automaticLayout,positions,dragPreview]);
 const routes=useMemo(()=>routeGraphEdges(displayed,layout),[displayed,layout]);
 const saveScene=useCallback(()=>{
  const value={scope,search,query,kind,focus,zoom,includeHidden,showStructure,displayMode,edgeId:edge?.id||restoreEdge.current,anchorId:sceneAnchor||'',layouts:restoreNodeLayouts(manualLayouts,projectId),
   scrollLeft:canvas.current?.scrollLeft??scene.current?.scrollLeft??initialScroll.current.left,
   scrollTop:canvas.current?.scrollTop??scene.current?.scrollTop??initialScroll.current.top};
  scene.current=value;
  // Route zoom, list mode and selection are temporary. Browser persistence
  // keeps the exploration view and independently scoped route arrangements.
  const savedValue=routeFocused?{...(routeViewport.current?.scene||value),layouts:value.layouts}:value;
  if(routeFocused&&routeViewport.current?.scene)scene.current=routeViewport.current.scene;
  try{const saved=onSceneChange?.(savedValue)!==false;setLayoutSaveError(!saved);return saved}
  catch{setLayoutSaveError(true);return false}
 },[scope,search,query,kind,focus,zoom,includeHidden,showStructure,displayMode,edge?.id,sceneAnchor,manualLayouts,projectId,onSceneChange,routeFocused]);
 useEffect(()=>{saveScene()},[saveScene]);
 useLayoutEffect(()=>{
  const element=canvas.current;if(!element)return;
  const measure=()=>{setCanvasWidth(element.clientWidth);setNarrow(window.innerWidth<800)};
  measure();window.addEventListener('resize',measure);
  const observer=new ResizeObserver(measure);observer.observe(element);
  const workspace=element.closest('.kw-workspace');if(workspace)observer.observe(workspace);
  return()=>{window.removeEventListener('resize',measure);observer.disconnect()};
 },[graph?.nodes.length,nodeId,filtersOpen,error,loading,displayMode,routeFocused,routeGraph.nodes.length]);
 useLayoutEffect(()=>{
  if(routeFocused||!graph||!canvas.current||restored.current)return;
  canvas.current.scrollLeft=initialScroll.current.left;canvas.current.scrollTop=initialScroll.current.top;restored.current=true;
  if(!initial&&nodeId){const point=layout.points.get(nodeId);if(point){canvas.current.scrollLeft=Math.max(0,point.x*zoom-80);canvas.current.scrollTop=Math.max(0,point.y*zoom-80)}}
  if(scene.current)scene.current={...scene.current,scrollLeft:canvas.current.scrollLeft,scrollTop:canvas.current.scrollTop};
 },[graph,layout,zoom,nodeId,initial,displayMode,routeFocused]);
 useLayoutEffect(()=>{
  if(!initial||restoredFocus.current||!graph||!canvas.current)return;
  const attribute=initial.edgeId?'data-edge-id':'data-node-id',id=initial.edgeId||nodeId;
  const target=[...canvas.current.querySelectorAll<SVGElement>('['+attribute+']')].find(element=>element.getAttribute(attribute)===id);
  if(target){restoredFocus.current=true;opener.current=target;target.focus({preventScroll:true})}
 },[graph,initial,nodeId,displayed]);
 const activeNode=nodeId||hover;
 const relatedEdges=useMemo(()=>new Set(displayed.edges.filter(e=>e.source===activeNode||e.target===activeNode).map(e=>e.id)),[displayed.edges,activeNode]);
 const relatedNodes=useMemo(()=>new Set([activeNode,...displayed.edges.filter(e=>e.source===activeNode||e.target===activeNode).flatMap(e=>[e.source,e.target])]),[displayed.edges,activeNode]);
 const labels=useMemo(()=>placeEdgeLabels(routes,layout,new Set(edge||hoverEdge?[edge?.id||hoverEdge]:activeNode?[...relatedEdges].slice(0,5):displayed.edges.filter(e=>!['CONTAINS','HAS_PART','MENTIONS'].includes(e.kind)).slice(0,4).map(e=>e.id))),[routes,layout,edge,hoverEdge,activeNode,relatedEdges,displayed.edges]);
 const reset=()=>{const element=canvas.current,value=element?Math.max(.65,Math.min(1,(element.clientWidth-16)/layout.width,narrow?1:(element.clientHeight-16)/layout.height)):1;viewportReady.current.initialized=true;pendingZoom.current=undefined;zoomRef.current=value;setZoom(value);if(element){element.scrollLeft=0;element.scrollTop=0}};
 // Fit once when entering a scope. Selecting nodes, opening details, resizing
 // the workspace and refreshing content must leave the user's viewport alone.
 useLayoutEffect(()=>{
  if(viewportReady.current.initialized||(!routeFocused&&graphScope.current!==scope)||!displayed.nodes.length||!canvas.current||displayMode!=='graph'||canvasWidth<=0)return;
  viewportReady.current.initialized=true;reset();
 },[scope,displayed,displayMode,canvasWidth,canvasHeight,automaticLayout.width,automaticLayout.height,routeFocused]);
 const zoomAt=useCallback((next:number,anchor?:{x:number;y:number})=>{
  const element=canvas.current,current=zoomRef.current;
  const value=Math.max(.3,Math.min(1.8,next));
  if(!element||value===current)return;
  viewportReady.current.initialized=true;
  const point=anchor||{x:element.clientWidth/2,y:element.clientHeight/2};
  pendingZoom.current={left:((pendingZoom.current?.left??element.scrollLeft)+point.x)*value/current-point.x,top:((pendingZoom.current?.top??element.scrollTop)+point.y)*value/current-point.y};
  zoomRef.current=value;setZoom(value);
 },[]);
 useLayoutEffect(()=>{
  if(!pendingZoom.current||!canvas.current)return;
  canvas.current.scrollLeft=Math.max(0,pendingZoom.current.left);canvas.current.scrollTop=Math.max(0,pendingZoom.current.top);pendingZoom.current=undefined;
 },[zoom,pathGraph,displayMode,routeRestore]);
 useEffect(()=>{
  const element=canvas.current;if(!element)return;
  const wheel=(event:WheelEvent)=>{
   if(!element.querySelector('svg')||nodeDrag.current||!event.deltaY||event.shiftKey||Math.abs(event.deltaX)>Math.abs(event.deltaY))return;
   event.preventDefault();
   const bounds=element.getBoundingClientRect(),delta=event.deltaY*(event.deltaMode===1?16:event.deltaMode===2?element.clientHeight:1);
   zoomAt(zoomRef.current*Math.exp(-delta*.0015),{x:Math.max(0,Math.min(element.clientWidth,event.clientX-bounds.left-element.clientLeft)),y:Math.max(0,Math.min(element.clientHeight,event.clientY-bounds.top-element.clientTop))});
  };
  // React's delegated wheel listeners are passive; this must be a native
  // non-passive listener to zoom the canvas without scrolling the whole page.
  element.addEventListener('wheel',wheel,{passive:false});
  return()=>element.removeEventListener('wheel',wheel);
 },[displayMode,zoomAt]);
 const commitPositions=(next:NodePositions,message:string)=>{
  setUndoLayouts(history=>[...history.slice(-19),positions]);
  setManualLayouts(current=>({...current,[layoutScope]:next}));setLayoutNotice(message);
 };
 const finishNodeDrag=(cancel=false)=>{
  const moving=nodeDrag.current;if(!moving)return;
  if(previewFrame.current!==undefined){cancelAnimationFrame(previewFrame.current);previewFrame.current=undefined}
  if(moving.moved){
   suppressClick.current={id:moving.id,until:Date.now()+300};
   if(!cancel){const point=resolveNodeDrop(applyNodePositions(automaticLayout,positions),moving.id,moving.point);commitPositions({...positions,[moving.id]:point},'布局已保存在此浏览器');}
   else setLayoutNotice('已取消本次移动');
  }
  nodeDrag.current=undefined;setDragPreview(undefined);
 };
 const moveNodeWithKey=(id:string,key:string,large:boolean)=>{
  const current=layout.points.get(id);if(!current)return;
  const step=large?40:12,delta=({ArrowLeft:[-step,0],ArrowRight:[step,0],ArrowUp:[0,-step],ArrowDown:[0,step]} as Record<string,number[]>)[key];
  if(!delta)return;
  const point=resolveNodeDrop(layout,id,dragPosition(current,delta[0],delta[1],1));
  commitPositions({...positions,[id]:point},'节点位置已保存在此浏览器');
 };
 const clearContext=()=>{setPathGraph(undefined);setFocus('');setEdge(undefined);restored.current=false;initialScroll.current={left:0,top:0}};
 const restoreOpener=()=>{
  const target=opener.current;
  if(target?.isConnected&&(target instanceof HTMLElement||target instanceof SVGElement))target.focus({preventScroll:true});
 };
 const closeEdge=()=>{restoreEdge.current=undefined;setEdge(undefined);restoreOpener()};
 const closeNode=()=>{onClear?.();restoreOpener()};
 const openEdge=(value:KnowledgeEdge,element:Element)=>{opener.current=element;restoreEdge.current=undefined;setEdge(value)};
 const showPath=(value:KnowledgePath|undefined)=>{
  if(value&&!pathGraph){pathViewport.current={zoom,left:canvas.current?.scrollLeft||0,top:canvas.current?.scrollTop||0,mode:displayMode};viewportReady.current.initialized=false}
  if(!value&&pathViewport.current){
   const previous=pathViewport.current;setZoom(previous.zoom);pendingZoom.current={left:previous.left,top:previous.top};setDisplayMode(previous.mode);pathViewport.current=undefined;
  }else if(value)setDisplayMode('graph');
  setPathGraph(value);
 };
 const pick=(node:KnowledgeNode)=>{
  setEdge(undefined);
  if(SOURCE_KINDS.has(node.kind)&&!node.parent_id&&onScope){if(node.source_id===sourceId){onSource(node.source_id)}else{clearContext();onScope(node.source_id)}}
  else onNode(node);
 };
 const showRelated=(id:string)=>{setPathGraph(undefined);setFetchLimit(240);setFocus(id);setQuery('');setSearch('');setKind('');setDisplayMode('graph');setEdge(undefined);restored.current=false;initialScroll.current={left:0,top:0}};
 // The content list includes every object in the current API/source/filter
 // scope; hiding document scaffolding is only a canvas presentation choice.
 const listGraph=routeFocused?routeGraph:graph||available;
 const listNodes=listGraph.nodes.slice(0,listLimit);
 const sourceName=sources.find(s=>s.id===sourceId)?.title;
 const switchMode=(mode:GraphDisplayMode)=>{if(mode===displayMode)return;saveScene();restored.current=routeFocused;initialScroll.current={left:scene.current?.scrollLeft||0,top:scene.current?.scrollTop||0};setListLimit(40);if(mode==='list'&&!routeFocused)setFocus('');setDisplayMode(mode);if(!routeFocused&&mode!=='list')try{localStorage.setItem(`paperstride:${account?.id||'local'}:graph-presentation:${projectId}`,mode)}catch{/* The current choice remains usable. */}};
 const submitSearch=(value:string)=>{setFetchLimit(240);clearContext();onClear?.();setListLimit(40);setQuery(value.trim())};
 return <section className={'kw-graph-view kw-flat-graph'+(arranging?' kw-arranging-nodes':'')} aria-label="研究图谱主画布">
  <div className="kw-graph-tools kw-canvas-tools">
   {onReturn&&<Button type="text" onClick={onReturn}>返回原位置</Button>}
   {!routeFocused&&<>
   <Input.Search aria-label="搜索图谱知识" value={search} onChange={event=>{setSearch(event.target.value);if(!event.target.value){setQuery('');setFocus('')}}} onSearch={submitSearch} allowClear placeholder="搜索方法、概念或公式"/>
   {!!sources.length&&<Select className="kw-graph-source-scope" aria-label="图谱范围" value={sourceId||'all'} showSearch optionFilterProp="label" onChange={id=>{clearContext();onScope?.(id==='all'?undefined:id)}} options={[{value:'all',label:'整个研究空间'},...sources.map(source=>({value:source.id,label:source.title}))]}/>}
   <Button type={filtersOpen?'default':'text'} icon={<FilterOutlined/>} aria-expanded={filtersOpen} aria-controls="kw-graph-filters" onClick={()=>setFiltersOpen(v=>!v)}>筛选</Button>
   {onCreateNode&&<Button onClick={onCreateNode}>新增节点</Button>}
   {onImport&&<Button type="text" onClick={onImport}>导入资料</Button>}
   </>}
   <div className="kw-graph-display-switch" role="group" aria-label="图谱浏览方式">
    <button aria-pressed={displayMode==='graph'} onClick={()=>switchMode('graph')}>结构图</button>
    <button aria-pressed={displayMode==='network'} onClick={()=>switchMode('network')}>关系网络</button>
    <button aria-pressed={displayMode==='list'} onClick={()=>switchMode('list')}>内容列表</button>
   </div>
  </div>
  {routeFocused&&<section className="kw-saved-route-map" aria-label="已保存路线图谱">
   <header><h3>按我的路线浏览</h3>{onExitRoute&&<Button onClick={onExitRoute}>返回自由探索图谱</Button>}</header>
   <p>下列序号表示个人学习顺序；画布只显示当前有效知识及已有关系。基础补充可自由选择。</p>
   {!learningRoute?<p role="status">正在读取已保存的路线…</p>:<ol className="kw-saved-route-steps" aria-label="路线步骤顺序">{learningRoute.steps.map((step,index)=>{
    const node=routeGraph.nodes.find(item=>item.id===step.node_id),status=routeStepLabel(step,learningRoute.next_node_id);
    return <li key={step.node_id}><button type="button" disabled={!node} data-route-state={step.node_id===learningRoute.next_node_id?'next':step.state} aria-current={nodeId===step.node_id?'step':undefined} onClick={event=>{if(node){opener.current=event.currentTarget;pick(node)}}}><span className="kw-saved-route-index">{index+1}</span><strong>{step.label}</strong><small>{status}</small></button></li>;
   })}</ol>}
  </section>}
  {!routeFocused&&<div className="kw-graph-secondary-tools">
  {(sourceId||focus)&&<div className="kw-graph-viewbar">
   <nav className="kw-graph-breadcrumb" aria-label="图谱浏览层级">
    <button aria-current={!sourceId?'page':undefined} onClick={()=>{clearContext();if(onScope)onScope(undefined);else onClear?.()}}>研究空间</button>
    {sourceId&&<><span aria-hidden="true">/</span><span className="kw-current-source" title={sourceName}>{sourceName||'资料全景'}</span></>}
    {focus&&<Button type="text" size="small" onClick={clearContext}>退出关联视图</Button>}
   </nav>
  </div>}
  {!!graph?.nodes.length&&<KnowledgePathPanel key={scope} projectId={projectId} nodes={graph.nodes} currentNode={nodeId} onNode={onNode} onResult={showPath}/>}
  {displayMode==='graph'&&!!browse.omitted.length&&<button className="kw-open-content-list" onClick={()=>switchMode('list')}>查看全部内容</button>}
  </div>}
  {!routeFocused&&filtersOpen&&<div className="kw-graph-filters" id="kw-graph-filters"><label>知识类型<Select aria-label="图谱节点类型" value={kind} onChange={value=>{setFocus('');setKind(value)}} options={[{value:'',label:'全部'},...Object.entries(nodeKindLabels).map(([value,label])=>({value,label}))]}/></label><label><Switch size="small" aria-label="显示已隐藏知识" checked={includeHidden} onChange={setIncludeHidden}/>已隐藏内容</label><label><Switch size="small" aria-label="显示文档结构" checked={showStructure} onChange={setShowStructure}/>章节结构</label></div>}
  {!routeFocused&&error&&<Alert type="error" message="图谱暂时无法加载" description={error} action={<Button aria-label="重试加载图谱" onClick={()=>setRetry(v=>v+1)}>重试</Button>}/>}
  <GraphSplitLayout projectId={projectId} onCanvasHeight={setCanvasHeight} detail={nodeId&&!edge?controls=><NodeInspector key={projectId+nodeId} projectId={projectId} nodeId={nodeId} onNode={onNode} onLearn={onLearn} onEvidence={onEvidence} onSource={onSource} onUpdated={onUpdated} allNodes={routeFocused?routeGraph.nodes:graph?.nodes||[]} sources={sources} onClose={closeNode} onCompare={onCompare} onPractice={onPractice} onExpand={id=>{if(routeFocused)onExitRoute?.();showRelated(id)}} layoutControls={controls}/>:edge?()=> <div className="kw-relation-dock"><EdgeEditor key={edge.id} edge={edge} projectId={projectId} nodes={routeFocused?routeGraph.nodes:graph?.nodes} onClose={closeEdge} onSaved={onUpdated} onEvidence={onEvidence}/></div>:undefined}>
   <div className="kw-graph-primary">
    {displayMode==='network'?<ProjectForceGraph key={(account?.id||'local')+':'+layoutScope} projectId={projectId} scope={layoutScope} graph={networkGraph} height={canvasHeight} selectedNodeId={nodeId} onNode={onNode} onEdge={value=>{restoreEdge.current=undefined;setEdge(value)}} onClear={()=>{setEdge(undefined);onClear?.()}}/>:displayMode==='graph'?<>
     <div ref={canvas} className="kw-graph-canvas" style={{height:canvasHeight}} tabIndex={0} aria-label="研究知识图谱画布" onScroll={saveScene}
      onKeyDown={event=>{if(event.key==='Escape'){if(nodeDrag.current)finishNodeDrag(true);else if(arranging)setArranging(false);else if(edge)closeEdge();else closeNode()}}}
      onPointerDown={event=>{if(event.button!==0||(event.target as Element).closest('.kw-graph-node,.kw-graph-edge,button'))return;drag.current={x:event.clientX,y:event.clientY,left:event.currentTarget.scrollLeft,top:event.currentTarget.scrollTop};event.currentTarget.setPointerCapture?.(event.pointerId)}}
      onPointerMove={event=>{
       const moving=nodeDrag.current;
       if(moving){const dx=event.clientX-moving.clientX+event.currentTarget.scrollLeft-moving.scrollLeft,dy=event.clientY-moving.clientY+event.currentTarget.scrollTop-moving.scrollTop;
        if(!moving.moved&&Math.hypot(dx,dy)<4)return;
        moving.moved=true;moving.point=dragPosition(moving.start,dx,dy,zoom);
        if(previewFrame.current===undefined)previewFrame.current=requestAnimationFrame(()=>{previewFrame.current=undefined;const next=nodeDrag.current;if(next)setDragPreview({id:next.id,point:next.point})});
        return;
       }
       if(!drag.current)return;event.currentTarget.scrollLeft=drag.current.left-(event.clientX-drag.current.x);event.currentTarget.scrollTop=drag.current.top-(event.clientY-drag.current.y);
      }}
      onPointerUp={()=>{finishNodeDrag();drag.current=undefined}} onPointerCancel={()=>{finishNodeDrag(true);drag.current=undefined}}>
      {!routeFocused&&loading&&<div className="kw-graph-loading" role="status"><Spin size="small"/><span>读取研究知识…</span></div>}
      {!!displayed.nodes.length?<svg style={{maxWidth:'none'}} width={layout.width*zoom} height={layout.height*zoom} viewBox={'0 0 '+layout.width+' '+layout.height} role="group" aria-label="问题、方法、知识与来源组成的研究图谱">
       <defs><marker id="kw-arrow" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto"><path d="M0 0 L6 3 L0 6" fill="currentColor"/></marker></defs>
       {!Object.keys(positions).length&&!dragPreview&&layout.lanes.map(lane=><g key={lane.kind} className="kw-graph-lane" aria-hidden="true"><text x={lane.x} y="29">{lane.label}</text></g>)}
       {routes.map(route=>{
        const e=route.edge,related=relatedEdges.has(e.id),selected=edge?.id===e.id,label=labels.get(e.id);
        return <g key={e.id} className={'kw-graph-edge '+(selected||related?'kw-related-edge':'')+(activeNode&&!related?' kw-muted-edge':'')} tabIndex={0} role="button" aria-label={'关系：'+e.label} onMouseEnter={()=>setHoverEdge(e.id)} onMouseLeave={()=>setHoverEdge('')} onFocus={()=>setHoverEdge(e.id)} onBlur={()=>setHoverEdge('')} data-edge-id={e.id} onClick={event=>openEdge(e,event.currentTarget)} onKeyDown={event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();openEdge(e,event.currentTarget)}}}><title>{e.label+'\n'+e.explanation}</title><path className="kw-edge-line" fill="none" d={route.d} markerEnd="url(#kw-arrow)"/><path className="kw-edge-hit" fill="none" stroke="transparent" d={route.d}/>{label&&<g className="kw-edge-label"><rect x={label.x} y={label.y} width={label.width} height={label.height} rx="4"/><text x={label.x+label.width/2} y={label.y+15} textAnchor="middle">{label.text}</text></g>}</g>;
       })}
       {displayed.nodes.map(node=>{const point=layout.points.get(node.id);if(!point)return null;const routeStep=routeFocused?routeSteps.get(node.id):undefined;const routeStatus=routeStep?routeStepLabel(routeStep.step,learningRoute?.next_node_id):'';return <g key={node.id} className={'kw-graph-node '+(node.id===nodeId?'kw-selected-node ':'')+(activeNode&&!relatedNodes.has(node.id)?'kw-muted-node ':'')+(dragPreview?.id===node.id?'kw-dragging-node ':'')+(routeStep?'kw-route-'+(node.id===learningRoute?.next_node_id?'next':routeStep.step.state)+' ':'')+'kw-kind-'+node.kind} transform={'translate('+point.x+','+point.y+')'} tabIndex={0} role="button" aria-label={(routeStep?'第'+(routeStep.index+1)+'步 · '+routeStatus+' · ':'')+(nodeKindLabels[node.kind]||node.kind)+'：'+node.label} aria-describedby={arranging?'kw-node-arrangement-help':undefined} onPointerDown={event=>{if(!arranging||event.button!==0)return;event.stopPropagation();event.preventDefault();event.currentTarget.focus();const host=canvas.current;if(!host)return;nodeDrag.current={id:node.id,pointerId:event.pointerId,clientX:event.clientX,clientY:event.clientY,scrollLeft:host.scrollLeft,scrollTop:host.scrollTop,start:point,point,moved:false};host.setPointerCapture?.(event.pointerId)}} data-node-id={node.id} onClick={event=>{if(suppressClick.current?.id===node.id&&suppressClick.current.until>Date.now())return;opener.current=event.currentTarget;pick(node)}} onMouseEnter={()=>setHover(node.id)} onMouseLeave={()=>setHover('')} onFocus={()=>setHover(node.id)} onBlur={()=>setHover('')} onKeyDown={event=>{if(arranging&&['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key)){event.preventDefault();event.stopPropagation();moveNodeWithKey(node.id,event.key,event.shiftKey)}else if(event.key==='Enter'||event.key===' '){event.preventDefault();opener.current=event.currentTarget;pick(node)}}}><title>{node.label+'\n'+node.summary.slice(0,350)}</title><rect width={NODE_WIDTH} height={NODE_HEIGHT} rx="8"/><text className="kw-node-kind" x="16" y="20">{routeStep?'第'+(routeStep.index+1)+'步 · '+routeStatus:(nodeKindLabels[node.kind]||node.kind)+(progressLabels[progressByNode[node.id]||String(node.metadata.learning_progress||'')]?' · '+progressLabels[progressByNode[node.id]||String(node.metadata.learning_progress||'')]:'' )}</text><text className="kw-node-label" x="16" y="43">{labelLines(node.label).map((line,index)=><tspan key={index} x="16" dy={index?20:0}>{line}</tspan>)}</text>{!!node.evidence_ids?.length&&<text className="kw-node-evidence-count" x="16" y={NODE_HEIGHT-14}>原文依据 {node.evidence_ids.length} 处</text>}{node.source_missing&&<circle cx={NODE_WIDTH-15} cy="18" r="3" className="kw-source-warning"/>}</g>})}
      </svg>:(routeFocused||!loading)&&<section className="kw-empty"><h2>{routeFocused?'路线中的知识需要复核':query||kind?'没有找到匹配知识':'从你的研究资料开始'}</h2><p>{routeFocused?'当前没有可展示的有效步骤，请回到路线查看来源变化并调整。':query||kind?'尝试更短的关键词，或清除筛选。':'添加论文或研究报告后，相关方法与知识会出现在这里。'}</p>{!routeFocused&&!query&&!kind&&onImport&&<Button type="primary" onClick={onImport}>添加资料并构建图谱</Button>}{!routeFocused&&(query||kind)&&<Button onClick={()=>{setSearch('');setQuery('');setKind('')}}>清除筛选</Button>}</section>}
     </div>
     <div className="kw-canvas-navigation"><span className="kw-graph-level-caption">{routeFocused?'我的路线':focus?'相关知识':sourceId?'资料全景':'空间概览'} · {displayed.nodes.length} 个关键节点</span><div className="kw-layout-controls"><Button size="small" type={arranging?'primary':'text'} aria-pressed={arranging} onClick={()=>{finishNodeDrag(true);setArranging(value=>!value);setLayoutNotice('')}}>{arranging?'完成整理':'整理节点'}</Button>{arranging&&<><Button size="small" disabled={!undoLayouts.length} onClick={()=>{const previous=undoLayouts[undoLayouts.length-1];if(!previous)return;setManualLayouts(current=>({...current,[layoutScope]:previous}));setUndoLayouts(history=>history.slice(0,-1));setLayoutNotice('已撤销上一次布局调整')}}>撤销</Button><Button size="small" disabled={!Object.keys(positions).length} onClick={()=>commitPositions({},'已恢复自动布局，可撤销')}>恢复自动布局</Button></>}</div><Space.Compact><Button aria-label="缩小图谱" icon={<MinusOutlined/>} onClick={()=>zoomAt(zoomRef.current-.15)}/><Button aria-label="重置图谱视角" onClick={reset}>{Math.round(zoom*100)}%</Button><Button aria-label="放大图谱" icon={<PlusOutlined/>} onClick={()=>zoomAt(zoomRef.current+.15)}/><Button aria-label="展开画布" icon={<FullscreenOutlined/>} onClick={()=>canvas.current?.requestFullscreen?.()}/></Space.Compact></div>
     {arranging&&<div id="kw-node-arrangement-help" className="kw-layout-help"><span>拖动节点整理布局；也可聚焦节点后用方向键移动，Shift 加速。</span>{!layoutSaveError&&<span role="status">{layoutNotice||'布局保存在当前账号的此浏览器中'}</span>}</div>}
     {layoutSaveError&&<div className="kw-layout-save-error" role="alert"><span>布局暂未保存，存储空间可能不可用。</span><Button size="small" onClick={()=>{if(saveScene())setLayoutNotice('布局已保存在此浏览器')}}>重试保存布局</Button></div>}
    </>:<section className={'kw-content-list'+(sourceId?' kw-scoped-content':'')} aria-label="知识内容列表">
     <div className="kw-content-list-status">{!routeFocused&&loading?<span role="status">读取内容…</span>:<span>已载入 {listGraph.nodes.length} 项内容{!routeFocused&&graph?.truncated?' · 可继续载入或缩小范围':''}</span>}</div>
     <ul>{listNodes.map(node=><li key={node.id}><button className={node.id===nodeId?'kw-current-content':undefined} aria-label={(nodeKindLabels[node.kind]||node.kind)+'：'+node.label} onClick={event=>{opener.current=event.currentTarget;pick(node)}}><span className="kw-content-list-kind">{nodeKindLabels[node.kind]||node.kind}</span><span className="kw-content-list-body"><strong>{node.label}</strong>{routeFocused&&routeSteps.get(node.id)&&<span className="kw-content-route-state">第{routeSteps.get(node.id)!.index+1}步 · {routeStepLabel(routeSteps.get(node.id)!.step,learningRoute?.next_node_id)}</span>}{node.summary?.trim()&&node.kind!=='formula'&&!damagedMathText(node.summary)&&<span><MathText text={node.summary}/></span>}</span>{!sourceId&&<small>{sources.find(s=>s.id===node.source_id)?.title}</small>}</button></li>)}</ul>
     {(routeFocused||!loading)&&!listNodes.length&&<p>没有找到匹配内容。</p>}
     {!routeFocused&&graph?.truncated&&listGraph.nodes.length<=listLimit&&(fetchLimit<2000?<Button loading={loading} onClick={()=>{setFetchLimit(v=>Math.min(2000,v+240));setListLimit(v=>v+240)}}>继续载入知识</Button>:<p>当前已达单次浏览上限，请选择资料或搜索关键词继续定位。</p>)}
     {listGraph.nodes.length>listLimit&&<Button onClick={()=>setListLimit(value=>value+40)}>显示更多内容</Button>}
    </section>}
   </div>
  </GraphSplitLayout>
 </section>;
}
