import {useCallback,useEffect,useMemo,useRef,useState} from 'react';
import {Alert,Button,Input,Select,Space,Spin} from 'antd';
import {ArrowLeftOutlined,ReloadOutlined,SettingOutlined} from '@ant-design/icons';
import {Link,useLocation,useNavigate,useSearchParams} from 'react-router-dom';
import {safeReturnTo} from '../../api/workContext';
import {useCurrentAccount} from '../SessionContext';
import {apiGet} from '../../api/client';
import {getProject,updateProject} from '../../api/projects';
import type {ResearchProject} from '../../api/project-types';
import {getKnowledgeNode,listKnowledgeSources,saveKnowledgePreferences} from '../../api/knowledge';
import type {KnowledgeEvidence,KnowledgeGraph,KnowledgeNode,SourcesResponse,WorkspaceMode,WorkspaceView} from '../../api/knowledge';
import KnowledgeGraphView,{type GraphScene} from './KnowledgeGraph';
import {restoreNodeLayouts} from './GraphInteraction';
import KnowledgeLearning from './KnowledgeLearning';
import KnowledgeComparison from './KnowledgeComparison';
import KnowledgePractice from './KnowledgePractice';
import KnowledgeSources,{AnalysisStatus,SourceReader,type SourceKnowledgeContext} from './KnowledgeSources';
import TaskGuidance from './TaskGuidance';
import LearningRoute from './LearningRoute';
import LearningRouteContinue from './LearningRouteContinue';
import NodeCreate from './NodeCreate';
import {getLearningRoute, type SavedLearningRoute} from '../../api/knowledgeRoutes';
import {readWorkspaceResume,resumeLocation,writeWorkspaceResume,type WorkspaceResume} from './workspaceResume';
import './knowledge-workspace.css';
import './reading-layout.css';
import './workspace-command-bar.css';

export const WORKSPACE_MODES={explore:'零基础探索',research:'已有思路深入研究',reproduce:'阅读与复现'};
const modes=Object.entries(WORKSPACE_MODES).map(([value,label])=>({value,label}));
const validViews=new Set(['graph','reading','learning','compare','practice','materials','route']);
const viewLabels:Record<WorkspaceView,string>={graph:'研究图谱',reading:'原文阅读',learning:'深入学习',compare:'资料比较',practice:'动态练习',materials:'资料与记录',route:'学习路线'};
const SCENE_FIELDS=['view','source','node','page','block','line','endLine','targetPage','comparison','mapping','bbox','returnTo','graphFrom','section','route','routeFrom'] as const;

function readCanvasScene(key:string,projectId:string):GraphScene|undefined{
 try{
  const value=JSON.parse(localStorage.getItem(key)||'null');
  if(!value||typeof value!=='object'||typeof value.scope!=='string')return undefined;
  const text=(field:unknown)=>typeof field==='string'?field.slice(0,500):'';
  const number=(field:unknown,fallback:number)=>typeof field==='number'&&Number.isFinite(field)?field:fallback;
  return {
   scope:text(value.scope),search:text(value.search),query:text(value.query),kind:text(value.kind),focus:text(value.focus),
   zoom:Math.max(.3,Math.min(3,number(value.zoom,1))),
   includeHidden:value.includeHidden===true,showStructure:value.showStructure===true,
   scrollLeft:Math.max(0,number(value.scrollLeft,0)),scrollTop:Math.max(0,number(value.scrollTop,0)),
   displayMode:value.displayMode==='network'?'network':value.displayMode==='list'?'list':'graph',
   layouts:restoreNodeLayouts(value.layouts,projectId),
   edgeId:text(value.edgeId),
   anchorId:typeof value.anchorId==='string'?text(value.anchorId):undefined,
  };
 }catch{return undefined}
}

export default function KnowledgeWorkbench({projectId}:{projectId:string}){
 const [completedSources,setCompletedSources]=useState<{id:string;title:string}[]>([]);
 const analysisStates=useRef(new Map<string,string>());
 const [project,setProject]=useState<ResearchProject>(),[data,setData]=useState<SourcesResponse>(),[workspace,setWorkspace]=useState<unknown>();
 const [error,setError]=useState(''),[refreshing,setRefreshing]=useState(false),[revision,setRevision]=useState(0),[retry,setRetry]=useState(0),[savingMode,setSavingMode]=useState(false),[modeError,setModeError]=useState(''),[selectedNode,setSelectedNode]=useState<KnowledgeNode>();
 const [params,setParams]=useSearchParams();
 const account=useCurrentAccount();
 const sceneKey=account?.id?'paperstride:'+account.id+':knowledge-scene:'+projectId:'paperstride:knowledge-scene:'+projectId;
 const canvasKey=sceneKey+':canvas';
 const [resume,setResume]=useState<WorkspaceResume|undefined>(()=>readWorkspaceResume(account?.id,projectId));
 const [graphData,setGraphData]=useState<KnowledgeGraph>(),[graphInspecting,setGraphInspecting]=useState(false);
 const [canvasVisit,setCanvasVisit]=useState(0);
 const [creatingNode,setCreatingNode]=useState(false);
 useEffect(()=>{setCreatingNode(false)},[projectId,account?.id]);
 const [questionFocused,setQuestionFocused]=useState(true),[editingQuestion,setEditingQuestion]=useState(false),[questionDraft,setQuestionDraft]=useState(''),[savingQuestion,setSavingQuestion]=useState(false),[questionError,setQuestionError]=useState('');
 const [expandedQuestion,setExpandedQuestion]=useState(false);
 const receiveGraph=useCallback((value:KnowledgeGraph)=>setGraphData(value),[]);
 const [learningRoute,setLearningRoute]=useState<SavedLearningRoute|null>(null),[routeLoading,setRouteLoading]=useState(true),[routeError,setRouteError]=useState(''),[routeRetry,setRouteRetry]=useState(0);
 useEffect(()=>{setLearningRoute(null);setRouteError('')},[projectId,account?.id]);
 useEffect(()=>{
  let controller=new AbortController();
  const loadRoute=()=>{
   controller.abort();controller=new AbortController();const current=controller;
   setRouteLoading(true);setRouteError('');
   getLearningRoute(projectId,current.signal).then(value=>{if(!current.signal.aborted)setLearningRoute(value.route)}).catch(e=>{if(!current.signal.aborted)setRouteError(String(e))}).finally(()=>{if(!current.signal.aborted)setRouteLoading(false)});
  };
  const updated=(event:Event)=>{if((event as CustomEvent).detail?.projectId===projectId)loadRoute()};
  loadRoute();window.addEventListener('paperstride:learning-route',updated);
  return()=>{controller.abort();window.removeEventListener('paperstride:learning-route',updated)};
 },[projectId,account?.id,revision,routeRetry,project?.research_question]);
 const savedCanvas=useMemo(()=>readCanvasScene(canvasKey,projectId),[canvasKey,projectId]);
 const location=useLocation(),navigate=useNavigate();
 const generation=useRef(0),fingerprint=useRef(''),loadSequence=useRef(0),restoredScene=useRef(false),graphScene=useRef<GraphScene>();
 const requested=params.get('view')||params.get('tab')||'graph';
 const view:WorkspaceView=(validViews.has(requested)?requested:'graph') as WorkspaceView;
 const routeFocused=params.get('route')==='1';
 const routeReturnScene=useRef<GraphScene>(),routeActive=useRef(routeFocused);
 routeActive.current=routeFocused;
 if(routeFocused&&!routeReturnScene.current)routeReturnScene.current=graphScene.current||savedCanvas;
 const nodeId=params.get('node')||undefined;
 const load=useCallback(async(signal?:AbortSignal)=>{
  const sequence=++loadSequence.current;
  const [p,s]=await Promise.all([getProject(projectId,signal),listKnowledgeSources(projectId,signal)]);
  if(signal?.aborted||sequence!==loadSequence.current)return;
  setProject(p);setData(s);setError('');
  const finished=s.items.filter(x=>x.analysis&&['queued','running'].includes(analysisStates.current.get(x.id)||'')&&['succeeded','partial'].includes(x.analysis.status));
  if(finished.length)setCompletedSources(old=>[...new Map([...old,...finished.map(x=>({id:x.id,title:x.title}))].map(x=>[x.id,x])).values()]);
  analysisStates.current=new Map(s.items.map(x=>[x.id,x.analysis?.status||'']));
  const f=JSON.stringify(s.items.map(x=>[x.id,x.version,x.removed,x.analysis?.status,x.analysis?.updated_at]));
  if(f!==fingerprint.current){fingerprint.current=f;setRevision(v=>v+1)}
 },[projectId]);
 useEffect(()=>{
  const c=new AbortController();generation.current++;restoredScene.current=false;
  graphScene.current=(params.get('resume')==='1'||params.get('resumeCanvas')==='1'||params.get('route')==='1')?savedCanvas:undefined;
  routeReturnScene.current=undefined;
  setCompletedSources([]);analysisStates.current.clear();setProject(undefined);setData(undefined);setWorkspace(undefined);setSelectedNode(undefined);setError('');setModeError('');fingerprint.current='';
  setGraphData(undefined);setGraphInspecting(false);setEditingQuestion(false);setSavingQuestion(false);setQuestionError('');setExpandedQuestion(false);
  setResume(readWorkspaceResume(account?.id,projectId));
  try{setQuestionFocused(localStorage.getItem(sceneKey+':question-focus')!=='false')}catch{setQuestionFocused(true)}
  void load(c.signal).catch(e=>{if(!c.signal.aborted)setError(e instanceof Error?e.message:String(e))});
  void apiGet<unknown>('/api/workbench/projects/'+projectId,undefined,c.signal).then(value=>{if(!c.signal.aborted)setWorkspace(value)}).catch(()=>{});
  return()=>{generation.current++;c.abort()};
 },[projectId,load,retry,canvasKey,savedCanvas]);
 useEffect(()=>{
  const c=new AbortController();setSelectedNode(undefined);
  if(nodeId)void getKnowledgeNode(projectId,nodeId,c.signal).then(result=>{if(!c.signal.aborted)setSelectedNode(result.node)}).catch(()=>{});
  return()=>c.abort();
 },[projectId,nodeId,revision]);
 const active=!!data?.items.some(s=>s.analysis&&['queued','running'].includes(s.analysis.status));
 useEffect(()=>{
  if(!data||restoredScene.current)return;restoredScene.current=true;
  if(['view','tab','source','paper','node','page','comparison'].some(key=>params.has(key)))return;
  try{
   const saved=JSON.parse(localStorage.getItem(sceneKey)||'null');
   if(!saved||typeof saved!=='object'){
    if(params.get('resume')==='1')setParams(new URLSearchParams(),{replace:true});
    return;
   }
   const next=new URLSearchParams({view:'graph'});
   const fields=params.get('resume')==='1'?SCENE_FIELDS:['source','node'] as const;
   for(const key of fields){const value=saved[key];if(typeof value==='string'&&value.length<=2000&&(key!=='view'||validViews.has(value)))next.set(key,value)}
   if(next.size>1||params.get('resume')==='1')setParams(next,{replace:true});
  }catch{
   if(params.get('resume')==='1')setParams(new URLSearchParams(),{replace:true});
  }
 },[data,params,sceneKey,setParams]);
 const sceneQuery=params.toString();
 useEffect(()=>{
  if(!data||!restoredScene.current)return;
  const saved:Record<string,string>={};
  for(const key of SCENE_FIELDS){const value=params.get(key);if(value&&value.length<=2000)saved[key]=['returnTo','graphFrom','routeFrom'].includes(key)?resumeLocation(value):value}
  if(!Object.keys(saved).length)return;
  try{
   localStorage.setItem(sceneKey,JSON.stringify(saved));
   localStorage.setItem('paperstride:'+(account?.id||'local')+':lastWorkspace','/research/'+encodeURIComponent(projectId)+'?resume=1');
  }catch{/* URL navigation remains available. */}
 },[sceneQuery,projectId,sceneKey,account?.id,!!data]);
 useEffect(()=>{
  if(!project||!data||!restoredScene.current)return;
  if((view==='graph'&&!nodeId)||(params.get('resume')==='1'&&!params.has('view')))return;
  if(nodeId&&(!selectedNode||selectedNode.id!==nodeId))return;
  const current=readWorkspaceResume(account?.id,projectId);
  const sourceId=view==='reading'?params.get('source')||selectedNode?.source_id:selectedNode?.source_id||params.get('source');
  const source=data.items.find(item=>item.id===sourceId);
  const sameNode=current?.nodeId===nodeId;
  const snapshot:WorkspaceResume={
   projectId,title:project.title,url:location.pathname+location.search,view,question:project.research_question,
   nodeId,nodeLabel:selectedNode?.label||(sameNode?current?.nodeLabel:undefined),nodeVersion:selectedNode?.version,
   sourceId:source?.id,sourceTitle:source?.title,sourceVersion:source?.version,
   page:params.get('page')||undefined,line:params.get('line')||undefined,
   unresolvedQuestions:sameNode?current?.unresolvedQuestions:undefined,
   judgmentSourceId:sameNode?(current?.judgmentSourceId||current?.sourceId):undefined,
   judgmentSourceVersion:sameNode?(current?.judgmentSourceVersion||current?.sourceVersion):undefined,
  };
  writeWorkspaceResume(account?.id,snapshot);setResume(snapshot);
 },[project,data,selectedNode,sceneQuery,account?.id,projectId]);
 useEffect(()=>{
  const saved=(event:Event)=>{
   const detail=(event as CustomEvent).detail;
   if(detail?.projectId!==projectId)return;
   const current=readWorkspaceResume(account?.id,projectId);
   if(!current||current.nodeId!==detail.nodeId)return;
   const snapshot={...current,unresolvedQuestions:String(detail.unresolvedQuestions||''),
    judgmentSourceId:detail.sourceId||current.sourceId,judgmentSourceVersion:detail.sourceVersion||current.sourceVersion};
   writeWorkspaceResume(account?.id,snapshot);setResume(snapshot);
  };
  window.addEventListener('paperstride:note-saved',saved);
  return()=>window.removeEventListener('paperstride:note-saved',saved);
 },[account?.id,projectId]);
 useEffect(()=>{
  if(!active)return;const c=new AbortController();
  const id=window.setInterval(()=>{void load(c.signal).catch(e=>{if(!c.signal.aborted)setError(String(e))})},3000);
  return()=>{window.clearInterval(id);c.abort()};
 },[active,load]);
 const refresh=useCallback(()=>{setRevision(v=>v+1);setRefreshing(true);void load().catch(e=>setError(String(e))).finally(()=>setRefreshing(false))},[load]);
 const saveCanvas=useCallback((scene:GraphScene)=>{
  const value=routeActive.current&&routeReturnScene.current?{...routeReturnScene.current,layouts:scene.layouts}:scene;
  if(routeActive.current&&routeReturnScene.current)routeReturnScene.current=value;
  graphScene.current=value;
  try{localStorage.setItem(canvasKey,JSON.stringify(value));return true}catch{return false}
 },[canvasKey]);
 if(!project||!data)return <div className="kw-workspace">{error?<Alert type="error" message="研究空间暂时无法打开" description={error} action={<Button onClick={()=>setRetry(v=>v+1)}>重试</Button>}/>:<div className="kw-loading"><Spin/><span role="status">打开研究空间…</span></div>}</div>;
 if(params.get('resume')==='1'&&!params.has('view'))return <div className="kw-workspace"><div className="kw-loading"><Spin/><span role="status">恢复上次学习位置…</span></div></div>;

 const sources=data.items||[],activeSources=sources.filter(s=>!s.removed);
 const explicitSource=params.get('source'),legacyPaper=params.get('paper');
 const currentSource=explicitSource?activeSources.find(s=>s.id===explicitSource)||sources.find(s=>s.id===explicitSource):legacyPaper?activeSources.find(s=>s.paper_uid===legacyPaper):undefined;
 const sourceId=currentSource?.id;
 const readingSource=view==='reading'?explicitSource||currentSource?.id||selectedNode?.source_id||activeSources[0]?.id:selectedNode?.source_id||currentSource?.id||activeSources[0]?.id;
 const setContext=(changes:Record<string,string|undefined>)=>setParams(old=>{
  const next=new URLSearchParams(old);next.delete('legacy');
  Object.entries(changes).forEach(([key,value])=>value?next.set(key,value):next.delete(key));
  if(changes.view)next.delete('tab');return next;
 });
 const graphOrigin=(id?:string)=>{
  const previous=params.get('graphFrom');
  if(view!=='graph'&&previous?.startsWith('/research/'+encodeURIComponent(projectId)))return previous;
  const query=new URLSearchParams({view:'graph'});
  if(routeFocused)query.set('route','1');
  if(sourceId)query.set('source',sourceId);
  if(id||nodeId)query.set('node',id||nodeId!);
  return location.pathname+'?'+query;
 };
 const openTool=(next:WorkspaceView,id?:string,extra:Record<string,string|undefined>={})=>setContext({
  view:next,node:id||nodeId,returnTo:safeReturnTo(location.pathname+location.search)||location.pathname,graphFrom:graphOrigin(id),
  ...(next==='route'&&!routeFocused?{routeFrom:view==='graph'?location.pathname+location.search:graphOrigin()}:{}),...extra,
 });
 const exitRouteGraph=()=>{
  const previous=safeReturnTo(params.get('routeFrom'))||safeReturnTo(params.get('graphFrom'));
  graphScene.current=routeReturnScene.current;routeReturnScene.current=undefined;setCanvasVisit(value=>value+1);
  if(previous&&previous.split('?')[0]===location.pathname){
   const query=new URLSearchParams(previous.split('?')[1]);
   if(query.get('view')==='graph'&&query.get('route')!=='1'){navigate(previous);return}
  }
  setContext({view:'graph',route:undefined,routeFrom:undefined,node:undefined});
 };
 const returnToGraph=()=>navigate(graphOrigin());
 const back=()=>{
  const previous=safeReturnTo(params.get('returnTo'));
  if(previous&&(previous.startsWith('/research/'+encodeURIComponent(projectId))||/^\/graph(?:\?|$)/.test(previous)))navigate(previous);
  else returnToGraph();
 };
 const openNode=(node:KnowledgeNode)=>{
  setSelectedNode(node);
  setContext({node:node.id,...(['paper','report','results','code'].includes(node.kind)?{source:node.source_id}:{})});
 };
 const openLearning=(id:string,section?:'resources')=>openTool('learning',id,{section});
 const openPractice=(id:string,mappingId?:string)=>openTool('practice',id,{mapping:mappingId});
 const openComparison=(node:KnowledgeNode)=>openTool('compare',node.id,{source:node.source_id,comparison:undefined});
 const openEvidence=(e:KnowledgeEvidence)=>openTool('reading',nodeId,{
  source:e.source_id,block:e.block_id,page:e.locator?.page?String(e.locator.page):undefined,
  targetPage:e.locator?.page?String(e.locator.page):undefined,quote:e.quote?.slice(0,600)||undefined,
  bbox:e.locator?.bbox?.join(','),line:e.locator?.start_line?String(e.locator.start_line):undefined,endLine:e.locator?.end_line?String(e.locator.end_line):undefined,
 });
 const openSource=(id:string)=>openTool('reading',nodeId,{source:id,block:undefined,page:undefined,quote:undefined,bbox:undefined,line:undefined,endLine:undefined});
 const openFromSource=(id:string,context:SourceKnowledgeContext,nextView:'graph'|'learning')=>{
  const previous=new URLSearchParams(location.search);previous.delete('returnTo');previous.set('view','reading');
  if(readingSource)previous.set('source',readingSource);if(context.block)previous.set('block',context.block);if(context.page)previous.set('page',String(context.page));
  setContext({view:nextView,node:id,source:readingSource,returnTo:location.pathname+'?'+previous,graphFrom:graphOrigin(id)});
 };
 const saveMode=async(mode:WorkspaceMode)=>{
  const token=generation.current;setSavingMode(true);setModeError('');
  try{const prefs=await saveKnowledgePreferences(projectId,{mode});if(token===generation.current){loadSequence.current++;setData(old=>old?{...old,preferences:prefs}:old)}}
  catch(e){if(token===generation.current)setModeError(String(e))}
  finally{if(token===generation.current)setSavingMode(false)}
 };
 const saveQuestion=async()=>{
  if(savingQuestion||!questionDraft.trim())return;
  const token=generation.current;setSavingQuestion(true);setQuestionError('');
  try{
   const updated=await updateProject(projectId,{expected_version:project.version,title:null,research_question:questionDraft.trim(),status:null,constraints:null});
   if(token===generation.current){setProject(updated);setEditingQuestion(false)}
  }catch(e){if(token===generation.current)setQuestionError(String(e))}
  finally{if(token===generation.current)setSavingQuestion(false)}
 };
 const changeQuestionFocus=()=>{
  const next=!questionFocused;setQuestionFocused(next);
  try{localStorage.setItem(sceneKey+':question-focus',String(next))}catch{/* The selection still works for this visit. */}
 };
 const resumeTask=(url:string)=>{
  graphScene.current=readCanvasScene(canvasKey,projectId);
  setCanvasVisit(value=>value+1);
  navigate(url+(url.includes('?')?'&':'?')+'resumeCanvas=1');
 };
 const bbox=params.get('bbox')?.split(',').map(Number),selectedBbox=bbox?.length===4&&bbox.every(Number.isFinite)?bbox:undefined;
 // A route exit can restore the URL in a separate router render from the
 // visit counter. Mount the destination scope with its saved scene instead
 // of letting the previous all-source canvas reset that scene on scope change.
 const graph=<KnowledgeGraphView key={projectId+'/'+(sourceId||'all')+'/'+canvasVisit} projectId={projectId} sourceId={sourceId} nodeId={nodeId} sources={activeSources}
  question={project.research_question} questionFocused={questionFocused} onGraphData={receiveGraph} onInspectChange={setGraphInspecting}
  onCreateNode={()=>setCreatingNode(true)}
  learningRoute={learningRoute||undefined} routeFocused={routeFocused} onExitRoute={exitRouteGraph}
  onScope={id=>setContext({source:id,node:undefined,block:undefined,page:undefined,quote:undefined,bbox:undefined})}
  onNode={openNode} onClear={()=>setContext({node:undefined})} onLearn={openLearning} onCompare={openComparison} onPractice={openPractice} onReturn={params.has('returnTo')?back:undefined}
  onEvidence={openEvidence} onSource={openSource} revision={revision} onUpdated={refresh} initialScene={graphScene.current} initialLayouts={graphScene.current?.layouts||savedCanvas?.layouts} onSceneChange={saveCanvas} onImport={()=>openTool('materials')}/>;
 const content=view==='graph'?<>
  <section className={'kw-question'+(expandedQuestion?' kw-question-expanded':'')+(editingQuestion?' kw-question-editing':'')} aria-label="当前研究问题">
   <div className="kw-question-command">
    <div className="kw-question-heading">
     {(project.research_question||editingQuestion)&&<span className="kw-question-label">当前问题</span>}
     {!editingQuestion&&project.research_question&&<h2 id="kw-current-question" title={project.research_question}>{project.research_question}</h2>}
     {!editingQuestion&&project.research_question&&(project.research_question.length>64||project.research_question.includes('\n'))&&<Button type="text" size="small" aria-expanded={expandedQuestion} aria-controls="kw-current-question" onClick={()=>setExpandedQuestion(value=>!value)}>{expandedQuestion?'收起问题':'展开问题'}</Button>}
     {!editingQuestion&&<Button type="text" size="small" onClick={()=>{setQuestionDraft(project.research_question||'');setQuestionError('');setEditingQuestion(true)}}>{project.research_question?'修改问题':'写下问题'}</Button>}
    </div>
    <div className="kw-question-context">{routeFocused?<span title="正在查看已保存路线的知识与真实关系，步骤顺序仅用于安排学习。">已保存路线</span>:<Button size="small" title={questionFocused?'围绕当前问题浏览，切换后可自由探索整个课题。':'查看与当前问题相关的知识。'} onClick={changeQuestionFocus}>{questionFocused?'切换完整图谱':'围绕当前问题'}</Button>}</div>
   </div>
   {editingQuestion&&<div className="kw-question-editor"><Input.TextArea aria-label="当前研究问题" value={questionDraft} maxLength={1500} autoSize={{minRows:2,maxRows:4}} onChange={e=>setQuestionDraft(e.target.value)} disabled={savingQuestion}/><Button type="primary" loading={savingQuestion} disabled={!questionDraft.trim()} onClick={()=>void saveQuestion()}>保存问题</Button><Button disabled={savingQuestion} onClick={()=>setEditingQuestion(false)}>取消</Button></div>}
   {questionError&&<Alert type="error" message="问题尚未保存，输入已保留" description={questionError}/>}
  </section>
  {creatingNode&&<NodeCreate projectId={projectId} onCancel={()=>setCreatingNode(false)} onCreated={created=>{setCreatingNode(false);setSelectedNode(created);refresh();setContext({view:'graph',node:created.id,source:undefined,route:undefined,routeFrom:undefined})}}/>}
  <div className={!nodeId&&!graphInspecting&&questionFocused&&!routeFocused?'kw-task-layout':undefined}>{graph}
   {!nodeId&&!graphInspecting&&questionFocused&&!routeFocused&&<TaskGuidance projectId={projectId} question={project.research_question} graph={graphData} sources={activeSources} resume={resume} onResume={resumeTask} onLearn={openLearning} onRead={openSource} onImport={()=>openTool('materials')} learningRoute={learningRoute} onRoute={()=>openTool('route')}/>}
  </div></>:view==='reading'?<SourceReader projectId={projectId} sourceId={readingSource} onEvidence={openEvidence}
  sourcePicker={<Select aria-label="当前资料" value={readingSource} showSearch optionFilterProp="label" onChange={id=>setContext({source:id,block:undefined,page:undefined,targetPage:undefined,quote:undefined,bbox:undefined,line:undefined,endLine:undefined})} options={activeSources.map(s=>({value:s.id,label:s.title}))}/>}
  page={Number(params.get('page'))||1} targetPage={Number(params.get('targetPage'))||undefined} blockId={params.get('block')||undefined} quote={params.get('quote')||undefined} bbox={selectedBbox} startLine={Number(params.get('line'))||undefined} endLine={Number(params.get('endLine'))||undefined} onNode={(id,context)=>openFromSource(id,context,'graph')} onLearn={(id,context)=>openFromSource(id,context,'learning')} onPageChange={page=>setParams(old=>{const next=new URLSearchParams(old);next.set('page',String(page));return next},{replace:true})}/>
 :view==='route'?<LearningRoute projectId={projectId} route={learningRoute} loading={routeLoading} loadError={routeError} initialNode={selectedNode} onChanged={setLearningRoute} onReload={()=>setRouteRetry(value=>value+1)} onLearn={openLearning} onEvidence={openEvidence} onGraph={()=>setContext({view:'graph',route:'1',node:undefined,source:undefined})}/>
 :view==='learning'?<><LearningRouteContinue projectId={projectId} nodeId={nodeId} route={learningRoute} loading={routeLoading||!!routeError} onChanged={setLearningRoute} onLearn={openLearning} onRoute={()=>openTool('route')}/><KnowledgeLearning compactControls autoPrepare={!!data.model?.configured&&!!data.model?.enabled} focusResources={params.get('section')==='resources'} projectId={projectId} nodeId={nodeId} initialGoal={project.research_question} workspaceMode={data.preferences?.mode} onNode={id=>setContext({node:id})} onEvidence={openEvidence} onBack={back} onPractice={openPractice}/></>
 :view==='practice'?<KnowledgePractice projectId={projectId} nodeId={nodeId} mappingId={params.get('mapping')||undefined} onNode={id=>setContext({view:'graph',node:id,source:undefined,mapping:undefined})} onEvidence={openEvidence} onBack={back}/>
 :view==='compare'?<KnowledgeComparison projectId={projectId} sources={sources} initialQuestion={project.research_question} contextNodeId={nodeId} comparisonId={params.get('comparison')||undefined} onComparison={id=>setContext({comparison:id})} onNode={openLearning} onGraphNode={id=>setContext({view:"graph",node:id,source:undefined})} onEvidence={openEvidence}/>
 :<KnowledgeSources projectId={projectId} sources={sources} onEvidence={openEvidence} onUpdated={refresh} onRead={openSource} onGraph={id=>setContext({view:'graph',source:id,node:undefined})} workspace={workspace}/>;
 return <div className={'kw-workspace kw-graph-first kw-view-'+view}>
  <header className="kw-workspace-header kw-space-heading"><div className="kw-space-title">{view==='reading'?<Button className="kw-reading-back" aria-label={params.has('returnTo')?'返回原位置':undefined} type="text" icon={<ArrowLeftOutlined aria-hidden/>} onClick={back}>{selectedNode?'返回'+selectedNode.label:params.get('comparison')?'返回比较位置':'返回研究图谱'}</Button>:<Link className="ps-back-link" to="/research">研究空间</Link>}<div><h1 title={project.title}>{project.title}</h1>{view==='reading'?<span className="kw-reading-view-label">原文阅读</span>:view!=='graph'&&project.research_question&&<p title={project.research_question}>{project.research_question}</p>}</div></div>
   <div className="kw-space-actions">
    {(view==='compare'||view==='materials'||view==='route')&&<Button className="kw-return-graph" type="text" icon={<ArrowLeftOutlined aria-hidden/>} onClick={returnToGraph}>返回研究图谱</Button>}
    <Button onClick={()=>openTool('route')}>学习路线</Button><Button onClick={()=>openTool('materials')}>资料与记录 <span className="kw-source-count">{activeSources.length}</span></Button><Button type="text" aria-label="刷新空间" icon={<ReloadOutlined/>} loading={refreshing} onClick={refresh}/>
    <details className="kw-space-options"><summary aria-label="空间选项"><SettingOutlined/><span>空间选项</span></summary><div>
     {view==='reading'&&selectedNode&&<section className="kw-reading-node-tools"><strong>{selectedNode.label}</strong><Space wrap><Button size="small" onClick={()=>openLearning(selectedNode.id)}>深入学习</Button><Button size="small" onClick={()=>openPractice(selectedNode.id)}>动态练习</Button><Button size="small" onClick={()=>openComparison(selectedNode)}>方法比较</Button></Space></section>}
     <label>使用方式<Select aria-label="本空间使用方式" value={data.preferences?.mode||'research'} onChange={mode=>void saveMode(mode)} loading={savingMode} disabled={savingMode} options={modes}/></label>
     {!data.model?.enabled&&<p className="kw-reading-model-note">{data.model?.configured?'自动理解服务尚未启用':'平台模型尚未配置'}，原文与已有知识可用。<Link to="/settings">查看平台设置</Link></p>}
     <Link to={'/research/'+projectId+'?legacy=1&tab=settings'}>空间设置与历史工具</Link>
    </div></details>
   </div>
  </header>
  {error&&<Alert type="warning" message="部分状态暂未更新" description={error} action={<Button onClick={refresh}>重试</Button>}/>}{modeError&&<Alert type="warning" message={modeError}/>}
  {active&&<details className="kw-inline-tasks"><summary>正在更新 {activeSources.filter(s=>s.analysis&&['queued','running'].includes(s.analysis.status)).length} 份资料 · 查看处理进度</summary>{activeSources.filter(s=>s.analysis&&['queued','running'].includes(s.analysis.status)).map(s=><div key={s.id}><strong>{s.title}</strong><AnalysisStatus run={s.analysis}/></div>)}</details>}
  {!!completedSources.length&&<div className="kw-analysis-complete" role="status"><span>资料已进入当前知识图谱</span>{completedSources.map(s=><Button key={s.id} type="link" onClick={()=>{setContext({view:'graph',source:s.id,node:undefined});setCompletedSources(old=>old.filter(x=>x.id!==s.id))}}>查看新增知识 · {s.title}</Button>)}<Button type="text" onClick={()=>setCompletedSources([])}>收起</Button></div>}
  <section className="kw-main-view" aria-label={viewLabels[view]}>{content}</section>
 </div>;
}
