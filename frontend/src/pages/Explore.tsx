import {useEffect,useState,useRef,type ReactNode} from 'react';
import {Alert,Button,Segmented,Select,Space,Skeleton} from 'antd';
import {HistoryOutlined} from '@ant-design/icons';
import {Link,useSearchParams} from 'react-router-dom';
import {apiGet,apiPost} from '../api/client';
import {usePreferences} from '../components/PreferencesContext';
import Graph from './Graph';
import './graph.css';
import SyncedDraft from '../components/workbench/SyncedDraft';
import LearningDependencies from '../components/workbench/LearningDependencies';
import './explore-layout.css';

// Native details keeps the draft mounted so restoring and syncing do not depend
// on opening the menu. Its panel floats above the canvas instead of moving it.
function ExploreDisclosure({label,children}:{label:ReactNode;children:ReactNode}){
 const menu=useRef<HTMLDetailsElement>(null);
 const fitPanel=()=>{
  const panel=menu.current?.querySelector('.explore-tool-panel');
  if(!menu.current?.open||!panel)return;
  const viewport=window.visualViewport;
  const navigation=document.querySelector('.atlas-mobile-navigation')?.getBoundingClientRect();
  let bottom=viewport?viewport.offsetTop+viewport.height:window.innerHeight;
  if(navigation&&navigation.height>0)bottom=Math.min(bottom,navigation.top);
  menu.current.style.setProperty('--explore-panel-height',`${Math.max(96,Math.floor(bottom-panel.getBoundingClientRect().top-12))}px`);
 };
 useEffect(()=>{
  const close=(event:PointerEvent)=>{if(menu.current?.open&&event.target instanceof Node&&!menu.current.contains(event.target))menu.current.open=false};
  document.addEventListener('pointerdown',close);window.addEventListener('resize',fitPanel);window.visualViewport?.addEventListener('resize',fitPanel);
  return()=>{document.removeEventListener('pointerdown',close);window.removeEventListener('resize',fitPanel);window.visualViewport?.removeEventListener('resize',fitPanel)};
 },[]);
 return <details ref={menu} className="explore-tool-disclosure" onToggle={fitPanel} onKeyDown={event=>{if(event.key==='Escape'&&menu.current?.open){menu.current.open=false;menu.current.querySelector('summary')?.focus();event.preventDefault();event.stopPropagation()}}}><summary>{label}</summary><div className="explore-tool-panel">{children}</div></details>;
}

export default function Explore({projectId:propProject}:{projectId?:string}){
 const [params,setParams]=useSearchParams();const projectId=propProject||params.get('project')||undefined;
 const {preferences}=usePreferences();const [papers,setPapers]=useState<any[]>([]),[seed,setSeed]=useState(params.get('seed')||''),[direction,setDirection]=useState('references'),[result,setResult]=useState<any>(),[offset,setOffset]=useState(0),[busy,setBusy]=useState(false),[error,setError]=useState(''),[trail,setTrail]=useState<string[]>([]);
 const [scopeGraph,setScopeGraph]=useState(true),[scopeReady,setScopeReady]=useState(!projectId);const discoveryRequest=useRef(0);const [scopeRetry,setScopeRetry]=useState(0);
 const view=params.get('mode')==='learning'?'learning':'literature';
 useEffect(()=>{const c=new AbortController();setScopeReady(!projectId);if(!preferences.features.graph)return;const url=projectId?'/api/workbench/projects/'+projectId:'/api/papers';void apiGet<any>(url,projectId?undefined:{limit:100},c.signal).then(r=>{if(c.signal.aborted)return;setPapers(r.papers||r.items||[]);setScopeGraph(r.features?.graph!==false);setScopeReady(true)}).catch(e=>{if(!c.signal.aborted)setError(String(e))});return()=>c.abort()},[projectId,preferences.features.graph,scopeRetry]);
 useEffect(()=>{discoveryRequest.current++;setBusy(false);return()=>{discoveryRequest.current++}},[seed,direction,projectId]);
 const discover=async(next=0)=>{if(!seed||busy)return;const request=++discoveryRequest.current;setBusy(true);setError('');try{const response=await apiGet('/api/graph/explore',{seed,direction,offset:next,project_id:projectId,remote:true});if(request===discoveryRequest.current){setResult(response);setOffset(next)}}catch(e){if(request===discoveryRequest.current)setError(String(e))}finally{if(request===discoveryRequest.current)setBusy(false)}};

 const choose=(uid:string)=>{if(seed)setTrail(t=>[...t.slice(-9),seed]);setSeed(uid);setResult(undefined);setOffset(0);setParams(old=>{const n=new URLSearchParams(old);n.set('seed',uid);return n})};
 const goBack=()=>{const previous=trail[trail.length-1];if(!previous)return;setSeed(previous);setParams(old=>{const n=new URLSearchParams(old);n.set('seed',previous);return n});setTrail(t=>t.slice(0,-1));setResult(undefined)};
 const importPaper=async(p:any)=>{const r=await apiPost<any>('/api/workbench/import',{value:p.identifier,project_id:projectId});const all=await apiGet<any>(projectId?'/api/workbench/projects/'+projectId:'/api/papers',projectId?undefined:{limit:100});setPapers(all.papers||all.items||[]);if(r.uid||r.paper?.uid)choose(r.uid||r.paper.uid);setError('')};
 if(!scopeReady&&preferences.features.graph)return <section><h1>探索</h1>{error?<Alert type='error' message='无法读取课题探索偏好' description={error} action={<Button onClick={()=>{setError('');setScopeRetry(v=>v+1)}}>重试</Button>}/>:<Skeleton active/>}</section>;
 if(!preferences.features.graph||!scopeGraph)return <section><h1>探索</h1><p>图谱已关闭。你仍可以阅读和比较论文。</p><Link to="/manage">打开资料库</Link></section>;
 return <section className="stride-explore">
  <header className="explore-heading">
   <h1>探索</h1>
   <Segmented aria-label="探索视图" value={view} options={[{value:'literature',label:'文献关系'},{value:'learning',label:'学习依赖'}]} onChange={v=>setParams(old=>{const n=new URLSearchParams(old);n.set('mode',String(v));return n})}/>
   {view==='literature'&&<div className="explore-secondary-tools">
    <ExploreDisclosure label={<><HistoryOutlined aria-hidden="true"/>文献记录</>}>
     <h2>文献探索历史与同步</h2>
     <SyncedDraft identity={`paperstride:exploration:${projectId||'personal'}`} title="文献探索现场" value={JSON.stringify({seed,direction,trail})} onLoad={raw=>{try{const s=JSON.parse(raw);if(!params.get('seed')){setSeed(s.seed||'');setDirection(s.direction||'references');setTrail(s.trail||[])}}catch{}}} projectId={projectId}/>
     <Button className="explore-history-back" disabled={!trail.length} onClick={goBack}>返回上篇</Button>
    </ExploreDisclosure>
    {result&&<ExploreDisclosure label={`相关论文（${result.items.length}）`}>
     <h2>找到的相关论文（{result.items.length}）</h2>
     <p role="status">{result.notice}{result.cached?' 已使用缓存。':''}</p>
     <ul className="stride-discoveries">{result.items.map((p:any)=><li key={p.id||p.title}><strong>{p.title}</strong><p>{p.year||'年份未知'} · {p.reason}</p>{p.identifier?<Button onClick={async()=>{try{await importPaper(p)}catch(e){setError(String(e))}}}>加入资料库</Button>:<span>没有可导入标识</span>}</li>)}</ul>
     <Space><Button disabled={!offset} onClick={()=>void discover(Math.max(0,offset-20))}>上一页</Button><Button disabled={result.next==null} onClick={()=>void discover(result.next)}>下一页</Button></Space>
    </ExploreDisclosure>}
   </div>}
   {projectId&&<Link to={`/research/${projectId}?tab=overview`}>返回研究空间</Link>}
  </header>
  {error&&<Alert type="error" message={error}/>}
  {view==='learning'?<LearningDependencies projectId={projectId}/>:<>
   <div className="explore-seed-tools" role="group" aria-label="文献探索工具">
    <Select className="explore-seed-select" showSearch optionFilterProp="label" aria-label="种子论文" placeholder="选择种子论文" value={seed||undefined} onChange={choose} options={papers.map(p=>({value:p.uid,label:p.title}))}/>
    <Select aria-label="引用方向" value={direction} onChange={v=>{setDirection(v);setResult(undefined);setOffset(0)}} options={[{value:'references',label:'追溯参考文献'},{value:'citations',label:'查看后续引用'}]}/>
    <Button disabled={!seed} loading={busy} onClick={()=>void discover()}>查找相关文献</Button>
    <Button className="explore-back-button" disabled={!trail.length} onClick={goBack}>返回上篇</Button>
   </div>
   {seed?<Graph key={`${projectId||'personal'}:${seed}`} seed={seed} projectId={projectId} discovered={result?.items} direction={direction} onImport={importPaper}/>:<div className="explore-empty"><h2>从一篇论文出发</h2><p>选择一篇你感兴趣的论文，查看它使用的方法、数据集和相关研究。</p><Link to={projectId?`/manage?project=${projectId}&view=add`:"/manage?view=add"}>添加一篇论文</Link></div>}
  </>}
 </section>;
}
