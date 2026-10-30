import {useCallback,useEffect,useRef,useState} from 'react';
import {Alert,Button,Select,Space,Spin} from 'antd';
import {ArrowLeftOutlined,ReloadOutlined,SettingOutlined} from '@ant-design/icons';
import {Link,useLocation,useNavigate,useSearchParams} from 'react-router-dom';
import {safeReturnTo} from '../../api/workContext';
import {apiGet} from '../../api/client';
import {getProject} from '../../api/projects';
import type {ResearchProject} from '../../api/project-types';
import {getKnowledgeNode,listKnowledgeSources,saveKnowledgePreferences} from '../../api/knowledge';
import type {KnowledgeEvidence,KnowledgeNode,SourcesResponse,WorkspaceMode,WorkspaceView} from '../../api/knowledge';
import KnowledgeGraphView,{type GraphScene} from './KnowledgeGraph';
import KnowledgeLearning from './KnowledgeLearning';
import KnowledgeComparison from './KnowledgeComparison';
import KnowledgePractice from './KnowledgePractice';
import KnowledgeSources,{AnalysisStatus,SourceReader,type SourceKnowledgeContext} from './KnowledgeSources';
import './knowledge-workspace.css';

export const WORKSPACE_MODES={explore:'零基础探索',research:'已有思路深入研究',reproduce:'阅读与复现'};
const modes=Object.entries(WORKSPACE_MODES).map(([value,label])=>({value,label}));
const validViews=new Set(['graph','reading','learning','compare','practice','materials']);
const viewLabels:Record<WorkspaceView,string>={graph:'研究图谱',reading:'原文阅读',learning:'深入学习',compare:'方法比较',practice:'动态练习',materials:'资料与记录'};
const SCENE_FIELDS=['view','source','node','page','block','line','endLine','targetPage','comparison'] as const;

export default function KnowledgeWorkbench({projectId}:{projectId:string}){
 const [completedSources,setCompletedSources]=useState<{id:string;title:string}[]>([]);
 const analysisStates=useRef(new Map<string,string>());
 const [project,setProject]=useState<ResearchProject>(),[data,setData]=useState<SourcesResponse>(),[workspace,setWorkspace]=useState<unknown>();
 const [error,setError]=useState(''),[refreshing,setRefreshing]=useState(false),[revision,setRevision]=useState(0),[retry,setRetry]=useState(0),[savingMode,setSavingMode]=useState(false),[modeError,setModeError]=useState(''),[selectedNode,setSelectedNode]=useState<KnowledgeNode>();
 const [params,setParams]=useSearchParams();
 const location=useLocation(),navigate=useNavigate();
 const generation=useRef(0),fingerprint=useRef(''),loadSequence=useRef(0),restoredScene=useRef(false),graphScene=useRef<GraphScene>();
 const requested=params.get('view')||params.get('tab')||'graph';
 const view:WorkspaceView=(validViews.has(requested)?requested:'graph') as WorkspaceView;
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
  const c=new AbortController();generation.current++;restoredScene.current=false;graphScene.current=undefined;
  setCompletedSources([]);analysisStates.current.clear();setProject(undefined);setData(undefined);setWorkspace(undefined);setSelectedNode(undefined);setError('');setModeError('');fingerprint.current='';
  void load(c.signal).catch(e=>{if(!c.signal.aborted)setError(e instanceof Error?e.message:String(e))});
  void apiGet<unknown>('/api/workbench/projects/'+projectId,undefined,c.signal).then(value=>{if(!c.signal.aborted)setWorkspace(value)}).catch(()=>{});
  return()=>{generation.current++;c.abort()};
 },[projectId,load,retry]);
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
   const saved=JSON.parse(localStorage.getItem('paperstride:knowledge-scene:'+projectId)||'null');
   if(!saved||typeof saved!=='object')return;
   const next=new URLSearchParams({view:'graph'});
   for(const key of ['source','node'] as const){const value=saved[key];if(typeof value==='string'&&value.length<=500)next.set(key,value)}
   if(next.size>1)setParams(next,{replace:true});
  }catch{/* Unavailable browser storage does not block the workspace. */}
 },[data,params,projectId,setParams]);
 const sceneQuery=params.toString();
 useEffect(()=>{
  if(!data||!restoredScene.current)return;
  const saved:Record<string,string>={};
  for(const key of SCENE_FIELDS){const value=params.get(key);if(value&&value.length<=500)saved[key]=value}
  if(!Object.keys(saved).length)return;
  try{localStorage.setItem('paperstride:knowledge-scene:'+projectId,JSON.stringify(saved))}catch{/* URL navigation remains available. */}
 },[sceneQuery,projectId,!!data]);
 useEffect(()=>{
  if(!active)return;const c=new AbortController();
  const id=window.setInterval(()=>{void load(c.signal).catch(e=>{if(!c.signal.aborted)setError(String(e))})},3000);
  return()=>{window.clearInterval(id);c.abort()};
 },[active,load]);
 const refresh=useCallback(()=>{setRevision(v=>v+1);setRefreshing(true);void load().catch(e=>setError(String(e))).finally(()=>setRefreshing(false))},[load]);
 const saveCanvas=useCallback((scene:GraphScene)=>{graphScene.current=scene},[]);
 if(!project||!data)return <div className="kw-workspace">{error?<Alert type="error" message="研究空间暂时无法打开" description={error} action={<Button onClick={()=>setRetry(v=>v+1)}>重试</Button>}/>:<div className="kw-loading"><Spin/><span role="status">打开研究空间…</span></div>}</div>;

 const sources=data.items||[],activeSources=sources.filter(s=>!s.removed);
 const explicitSource=params.get('source'),legacyPaper=params.get('paper');
 const currentSource=explicitSource?activeSources.find(s=>s.id===explicitSource)||sources.find(s=>s.id===explicitSource):legacyPaper?activeSources.find(s=>s.paper_uid===legacyPaper):undefined;
 const sourceId=currentSource?.id;
 const readingSource=view==='reading'?currentSource?.id||selectedNode?.source_id||activeSources[0]?.id:selectedNode?.source_id||currentSource?.id||activeSources[0]?.id;
 const setContext=(changes:Record<string,string|undefined>)=>setParams(old=>{
  const next=new URLSearchParams(old);next.delete('legacy');
  Object.entries(changes).forEach(([key,value])=>value?next.set(key,value):next.delete(key));
  if(changes.view)next.delete('tab');return next;
 });
 const graphOrigin=(id?:string)=>{
  const previous=params.get('graphFrom');
  if(view!=='graph'&&previous?.startsWith('/research/'+encodeURIComponent(projectId)))return previous;
  const query=new URLSearchParams({view:'graph'});
  if(sourceId)query.set('source',sourceId);
  if(id||nodeId)query.set('node',id||nodeId!);
  return location.pathname+'?'+query;
 };
 const openTool=(next:WorkspaceView,id?:string,extra:Record<string,string|undefined>={})=>setContext({
  view:next,node:id||nodeId,returnTo:safeReturnTo(location.pathname+location.search)||location.pathname,graphFrom:graphOrigin(id),...extra,
 });
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
 const openPractice=(id:string)=>openTool('practice',id);
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
 const bbox=params.get('bbox')?.split(',').map(Number),selectedBbox=bbox?.length===4&&bbox.every(Number.isFinite)?bbox:undefined;
 const graph=<KnowledgeGraphView projectId={projectId} sourceId={sourceId} nodeId={nodeId} sources={activeSources}
  onScope={id=>setContext({source:id,node:undefined,block:undefined,page:undefined,quote:undefined,bbox:undefined})}
  onNode={openNode} onClear={()=>setContext({node:undefined})} onLearn={openLearning} onCompare={openComparison} onPractice={openPractice} onReturn={params.has('returnTo')?back:undefined}
  onEvidence={openEvidence} onSource={openSource} revision={revision} onUpdated={refresh} initialScene={graphScene.current} onSceneChange={saveCanvas} onImport={()=>openTool('materials')}/>;
 const content=view==='graph'?graph:view==='reading'?<>
  {params.has('returnTo')&&<div className="kw-reading-actions"><Button onClick={back}>返回原位置</Button></div>}
  <div className="kw-reading-scope"><label>当前资料<Select aria-label="当前资料" value={readingSource} showSearch optionFilterProp="label" onChange={id=>setContext({source:id,block:undefined,page:undefined,quote:undefined,bbox:undefined})} options={activeSources.map(s=>({value:s.id,label:s.title}))}/></label></div>
  <SourceReader projectId={projectId} sourceId={readingSource} page={Number(params.get('page'))||1} targetPage={Number(params.get('targetPage'))||undefined} blockId={params.get('block')||undefined} quote={params.get('quote')||undefined} bbox={selectedBbox} startLine={Number(params.get('line'))||undefined} endLine={Number(params.get('endLine'))||undefined} onNode={(id,context)=>openFromSource(id,context,'graph')} onLearn={(id,context)=>openFromSource(id,context,'learning')} onPageChange={page=>setParams(old=>{const next=new URLSearchParams(old);next.set('page',String(page));return next},{replace:true})}/>
 </>:view==='learning'?<KnowledgeLearning focusResources={params.get('section')==='resources'} projectId={projectId} nodeId={nodeId} onNode={id=>setContext({node:id})} onEvidence={openEvidence} onBack={back}/>
 :view==='practice'?<KnowledgePractice projectId={projectId} nodeId={nodeId} onNode={id=>setContext({view:'graph',node:id,source:undefined})} onEvidence={openEvidence} onBack={back}/>
 :view==='compare'?<KnowledgeComparison projectId={projectId} sources={sources} contextNodeId={nodeId} comparisonId={params.get('comparison')||undefined} onComparison={id=>setContext({comparison:id})} onNode={openLearning} onGraphNode={id=>setContext({view:"graph",node:id,source:undefined})} onEvidence={openEvidence}/>
 :<KnowledgeSources projectId={projectId} sources={sources} onUpdated={refresh} onRead={openSource} onGraph={id=>setContext({view:'graph',source:id,node:undefined})} workspace={workspace}/>;
 return <div className={'kw-workspace kw-graph-first kw-view-'+view}>
  <header className="kw-workspace-header kw-space-heading"><div className="kw-space-title"><Link className="ps-back-link" to="/research">研究空间</Link><div><h1>{project.title}</h1>{project.research_question&&<p title={project.research_question}>{project.research_question}</p>}</div></div>
   <div className="kw-space-actions"><Button onClick={()=>openTool('materials')}>资料与记录 <span className="kw-source-count">{activeSources.length}</span></Button><Button type="text" aria-label="刷新空间" icon={<ReloadOutlined/>} loading={refreshing} onClick={refresh}/><details className="kw-space-options"><summary aria-label="空间选项"><SettingOutlined/><span>空间选项</span></summary><div><label>使用方式<Select aria-label="本空间使用方式" value={data.preferences?.mode||'research'} onChange={mode=>void saveMode(mode)} loading={savingMode} disabled={savingMode} options={modes}/></label><Link to={'/research/'+projectId+'?legacy=1&tab=settings'}>空间设置与历史工具</Link></div></details></div>
  </header>
  {error&&<Alert type="warning" message="部分状态暂未更新" description={error} action={<Button onClick={refresh}>重试</Button>}/>}{modeError&&<Alert type="warning" message={modeError}/>}
  {view!=='graph'&&<div className="kw-context-heading"><Button type="text" icon={<ArrowLeftOutlined aria-hidden/>} onClick={returnToGraph}>返回研究图谱</Button><div><span>{selectedNode?.label||'当前研究空间'}</span><strong>{viewLabels[view]}</strong></div>{nodeId&&view!=='materials'&&<details className="kw-context-tools"><summary>节点工具</summary><Space wrap><Button onClick={()=>openLearning(nodeId)}>深入学习</Button><Button onClick={()=>openPractice(nodeId)}>动态练习</Button><Button onClick={()=>selectedNode&&openComparison(selectedNode)} disabled={!selectedNode}>方法比较</Button><Button onClick={()=>readingSource&&openSource(readingSource)}>原文阅读</Button></Space></details>}</div>}
  {!data.model?.enabled&&<details className="kw-model-notice kw-model-details"><summary>{data.model?.configured?'自动理解服务尚未启用':'平台模型尚未配置'} · 原文与已有知识可用</summary><Link to="/settings">查看平台设置</Link></details>}
  {active&&<details className="kw-inline-tasks"><summary>正在更新 {activeSources.filter(s=>s.analysis&&['queued','running'].includes(s.analysis.status)).length} 份资料 · 查看处理进度</summary>{activeSources.filter(s=>s.analysis&&['queued','running'].includes(s.analysis.status)).map(s=><div key={s.id}><strong>{s.title}</strong><AnalysisStatus run={s.analysis}/></div>)}</details>}
  {!!completedSources.length&&<div className="kw-analysis-complete" role="status"><span>资料已进入当前知识图谱</span>{completedSources.map(s=><Button key={s.id} type="link" onClick={()=>{setContext({view:'graph',source:s.id,node:undefined});setCompletedSources(old=>old.filter(x=>x.id!==s.id))}}>查看新增知识 · {s.title}</Button>)}<Button type="text" onClick={()=>setCompletedSources([])}>收起</Button></div>}
  <section className="kw-main-view" aria-label={viewLabels[view]}>{content}</section>
 </div>;
}
