import {useEffect,useId,useMemo,useRef,useState} from 'react';
import {Alert,Button,Checkbox,Segmented,Select,Skeleton,Space} from 'antd';
import {Link,useLocation,useSearchParams} from 'react-router-dom';
import {contextLink} from '../../api/workContext';
import {apiGet,apiPost} from '../../api/client';
import './learning-dependencies.css';

type Knowledge={id:string;title:string};
type Dependency={source:string;target:string;origin:string};
type DependencyData={version:number;data:Dependency[];nodes:Knowledge[]};
type Check={id:string;state:string;checked:number;code_checked:boolean};
type Curriculum={checks:Check[];features:Record<string,boolean>};
type History={version:number;created_at:string;data:Dependency[]};
type Position=Knowledge&{x:number;y:number;level:number};

const NODE_WIDTH=206,NODE_HEIGHT=104,COLUMN_GAP=32,ROW_GAP=64,PADDING=24;
const edgeKey=(edge:Dependency)=>`${edge.source}:${edge.target}`;
const originLabel=(edge:Dependency)=>edge.origin==='user_input'?'个人调整':'教学建议';
const lessonURL=(id:string,projectId?:string)=>`${id.startsWith('dp-')?`/practice?unit=${encodeURIComponent(id)}`:`/learn?view=foundations&lesson=${encodeURIComponent(id)}`}${projectId?`&project=${encodeURIComponent(projectId)}`:''}`;

/** Keep titles at their reading size; the graph scrolls inside its own viewport. */
export function dependencyLayout(nodes:Knowledge[],edges:Dependency[]) {
  const ids=new Set(nodes.map(node=>node.id));
  const incoming=new Map(nodes.map(node=>[node.id,0]));
  const next=new Map(nodes.map(node=>[node.id,[] as string[]]));
  const levels=new Map(nodes.map(node=>[node.id,0]));
  for(const edge of edges)if(ids.has(edge.source)&&ids.has(edge.target)){
    incoming.set(edge.target,incoming.get(edge.target)!+1);next.get(edge.source)!.push(edge.target);
  }
  const queue=nodes.filter(node=>incoming.get(node.id)===0).map(node=>node.id);let seen=0;
  while(queue.length){
    const id=queue.shift()!;seen++;
    for(const target of next.get(id)||[]){levels.set(target,Math.max(levels.get(target)!,levels.get(id)!+1));incoming.set(target,incoming.get(target)!-1);if(incoming.get(target)===0)queue.push(target);}
  }
  const groups=new Map<number,Knowledge[]>();
  for(const node of nodes){const level=levels.get(node.id)!;groups.set(level,[...(groups.get(level)||[]),node]);}
  const columns=Math.max(1,...[...groups.values()].map(group=>group.length));
  const width=PADDING*2+Math.max(3,columns)*NODE_WIDTH+(Math.max(3,columns)-1)*COLUMN_GAP;
  const positions:Position[]=[];
  for(const [level,group] of groups){
    const groupWidth=group.length*NODE_WIDTH+(group.length-1)*COLUMN_GAP;
    for(const [index,node] of group.entries())positions.push({...node,level,x:(width-groupWidth)/2+index*(NODE_WIDTH+COLUMN_GAP),y:PADDING+level*(NODE_HEIGHT+ROW_GAP)});
  }
  return {positions,width,height:PADDING*2+(Math.max(0,...groups.keys())+1)*NODE_HEIGHT+Math.max(0,...groups.keys())*ROW_GAP,hasCycle:seen!==nodes.length};
}

function connected(ids:Set<string>,edges:Dependency[],direction:'source'|'target'){
  const visited=new Set(ids);let changed=true;
  while(changed){changed=false;for(const edge of edges){const from=direction==='source'?edge.target:edge.source,to=direction==='source'?edge.source:edge.target;if(visited.has(from)&&!visited.has(to)){visited.add(to);changed=true;}}}
  return visited;
}

export default function LearningDependencies({projectId}:{projectId?:string}){
  const location=useLocation();const [params]=useSearchParams();
  const [data,setData]=useState<DependencyData>(),[curriculum,setCurriculum]=useState<Curriculum>(),[error,setError]=useState(''),[checkError,setCheckError]=useState('');
  const [selected,setSelected]=useState(''),[source,setSource]=useState(''),[target,setTarget]=useState(''),[onlyPath,setOnlyPath]=useState(false),[editing,setEditing]=useState(false),[saving,setSaving]=useState(false);
  const [view,setView]=useState<'map'|'stages'>(()=>window.innerWidth<700?'stages':'map'),[activeLevel,setActiveLevel]=useState(0);
  const [history,setHistory]=useState<History[]>([]),[historyOpen,setHistoryOpen]=useState(false),[historyError,setHistoryError]=useState(''),[notice,setNotice]=useState(''),[refresh,setRefresh]=useState(0);
  const latestScope=useRef(projectId);latestScope.current=projectId;
  const nodeButtons=useRef<Record<string,HTMLButtonElement|null>>({});
  const marker='dependency-arrow-'+useId().replace(/:/g,'');
  const suffix=projectId?'?project_id='+encodeURIComponent(projectId):'';
  useEffect(()=>{
    const controller=new AbortController();setData(undefined);setCurriculum(undefined);setError('');setCheckError('');setSelected('');setOnlyPath(false);setActiveLevel(0);setHistory([]);setHistoryOpen(false);setHistoryError('');setNotice('');setSaving(false);
    void apiGet<DependencyData>('/api/stride/dependencies'+suffix,undefined,controller.signal).then(value=>{if(!controller.signal.aborted)setData(value)}).catch(caught=>{if(!controller.signal.aborted)setError(String(caught))});
    void apiGet<Curriculum>('/api/stride/curriculum',projectId?{project_id:projectId}:undefined,controller.signal).then(value=>{if(!controller.signal.aborted)setCurriculum(value)}).catch(()=>{if(!controller.signal.aborted)setCheckError('检查记录暂不可用，学习关系仍可查看。')});
    return()=>controller.abort();
  },[projectId,refresh]);
  const relevant=useMemo(()=>{
    if(!selected||!data)return new Set(data?.nodes.map(node=>node.id)||[]);
    return new Set([...connected(new Set([selected]),data.data,'source'),...connected(new Set([selected]),data.data,'target')]);
  },[data,selected]);
  const visibleNodes=data?.nodes.filter(node=>!onlyPath||relevant.has(node.id))||[];
  const visibleIds=new Set(visibleNodes.map(node=>node.id));
  const visibleEdges=data?.data.filter(edge=>visibleIds.has(edge.source)&&visibleIds.has(edge.target))||[];
  const layout=dependencyLayout(visibleNodes,visibleEdges);
  const positions=new Map(layout.positions.map(node=>[node.id,node]));
  const levels=[...new Set(layout.positions.map(node=>node.level))].sort((a,b)=>a-b);
  const stageNodes=layout.positions.filter(node=>node.level===activeLevel);
  const stageIds=new Set(stageNodes.map(node=>node.id));
  const stageNext=data?.nodes.filter(node=>data.data.some(edge=>stageIds.has(edge.source)&&edge.target===node.id))||[];
  useEffect(()=>{if(view==='stages'&&selected){const level=dependencyLayout(data?.nodes||[],data?.data||[]).positions.find(node=>node.id===selected)?.level;if(level!==undefined)setActiveLevel(level)}},[selected,view,data]);
  const current=data?.nodes.find(node=>node.id===selected);
  const prerequisites=data?.data.filter(edge=>edge.target===selected)||[];
  const successors=data?.data.filter(edge=>edge.source===selected)||[];
  const check=curriculum?.checks.find(item=>item.id===selected);
  const canLearn=curriculum?['foundations','quizzes','coding','visuals'].some(name=>curriculum.features[name]):true;
  const title=(id:string)=>data?.nodes.find(node=>node.id===id)?.title||id;
  const save=async(edges:Dependency[])=>{
    if(!data||saving)return;setSaving(true);setError('');setNotice('');const scope=projectId;
    try{
      const value=await apiPost<{version:number;data:Dependency[]}>('/api/stride/dependencies'+suffix,{version:data.version,edges});
      if(latestScope.current!==scope)return;
      setData({...data,...value});setNotice('学习顺序已保存');setHistoryOpen(false);setHistory([]);
    }catch(caught:any){if(latestScope.current===scope)setError(caught.status===409?'另一处已修改学习顺序。你的选择已保留，请重新加载后核对。':String(caught));}
    finally{if(latestScope.current===scope)setSaving(false);}
  };
  const add=()=>{
    if(!data||!source||!target)return;
    if(source===target){setError('一个知识点不能作为自己的先修知识。');return;}
    if(data.data.some(edge=>edge.source===source&&edge.target===target)){setError('这条学习依赖已经存在。');return;}
    if(connected(new Set([target]),data.data,'target').has(source)){setError('这条依赖会形成循环，请调整先后顺序。');return;}
    void save([...data.data,{source,target,origin:'user_input'}]);
  };
  const remove=(edge:Dependency)=>{if(data)void save(data.data.filter(item=>edgeKey(item)!==edgeKey(edge)))};
  const keyNavigate=(event:React.KeyboardEvent<HTMLButtonElement>,node:Position)=>{
    if(!['ArrowUp','ArrowDown','ArrowLeft','ArrowRight'].includes(event.key))return;
    const sibling=layout.positions.filter(item=>item.level===node.level).sort((a,b)=>a.x-b.x),index=sibling.findIndex(item=>item.id===node.id);
    const id=event.key==='ArrowUp'?data?.data.find(edge=>edge.target===node.id)?.source:event.key==='ArrowDown'?data?.data.find(edge=>edge.source===node.id)?.target:sibling[index+(event.key==='ArrowLeft'?-1:1)]?.id;
    if(id&&positions.has(id)){event.preventDefault();setSelected(id);nodeButtons.current[id]?.focus();nodeButtons.current[id]?.scrollIntoView?.({block:'nearest',inline:'nearest'});}
  };
  const loadHistory=async()=>{
    const next=!historyOpen;setHistoryOpen(next);if(!next)return;setHistoryError('');const scope=projectId;
    try{const value=await apiGet<{items:History[]}>('/api/stride/dependencies/history'+suffix);if(latestScope.current===scope)setHistory(value.items);}
    catch(caught){if(latestScope.current===scope)setHistoryError(String(caught));}
  };
  return <section className="learning-dependencies" aria-labelledby="dependency-title">
    <header className="dependency-heading"><div><h2 id="dependency-title">学习依赖</h2><p>沿箭头从先修知识走向方法与实践。点击知识点，查看前后联系。</p></div>{data&&<span className="dependency-version">{data.nodes.length} 个知识点 · v{data.version}</span>}</header>
    {error&&<Alert type="error" message={error} action={<Button onClick={()=>setRefresh(value=>value+1)}>重新加载学习顺序</Button>}/>}
    {checkError&&<p className="dependency-status-note">{checkError}</p>}
    {!data&&!error&&<Skeleton active paragraph={{rows:5}}/>}
    {data&&<>
      <div className="dependency-toolbar"><div className="dependency-legend" aria-label="连线类型"><span><i/>教学建议</span><span><i className="is-personal"/>个人调整</span></div><Segmented aria-label="依赖图呈现方式" value={view} options={[{value:'map',label:'完整关系图'},{value:'stages',label:'分层浏览'}]} onChange={value=>setView(value as 'map'|'stages')}/><Checkbox checked={onlyPath} disabled={!selected} onChange={event=>setOnlyPath(event.target.checked)}>只看当前知识点的学习路径</Checkbox><Button onClick={()=>{setEditing(value=>!value);setError('')}} aria-expanded={editing}>{editing?'收起调整':'调整学习顺序'}</Button></div>
      {editing&&<div className="dependency-editor"><h3>添加先后关系</h3><p>选择需要先了解的知识，再选择目标内容。已有关系可在知识点详情中移除。</p><Space wrap><Select aria-label="先修知识" placeholder="选择先修知识" value={source||undefined} onChange={setSource} options={data.nodes.map(node=>({value:node.id,label:node.title}))}/><span className="dependency-editor-arrow">先于</span><Select aria-label="目标知识" placeholder="选择目标知识" value={target||undefined} onChange={setTarget} options={data.nodes.map(node=>({value:node.id,label:node.title}))}/><Button loading={saving} disabled={!source||!target} onClick={add}>保存新依赖</Button></Space></div>}
      {layout.hasCycle&&<Alert type="warning" message="已保存关系存在循环，暂不能确定先后顺序。请移除冲突依赖。"/>}
      <div className="dependency-workspace">
        <div className="dependency-map-wrap">{view==='stages'?<div className="dependency-stages"><nav aria-label="选择学习层级">{levels.map(level=><button type="button" key={level} aria-current={activeLevel===level?'step':undefined} onClick={()=>setActiveLevel(level)}>第 {level+1} 层</button>)}</nav><div className="dependency-stage-body"><h3>{activeLevel===0?'从这些基础开始':`这一层可以了解的知识`}</h3><p>选择知识点查看前后联系，或沿下方入口继续。</p><div className="dependency-stage-nodes">{stageNodes.map(node=><button type="button" key={node.id} className={selected===node.id?'is-selected':''} aria-label={`选择知识点：${node.title}`} aria-pressed={selected===node.id} onClick={()=>setSelected(node.id)}><strong>{node.title}</strong><span>{curriculum?.checks.find(item=>item.id===node.id)?.state||'基础课程'}</span></button>)}</div>{stageNext.length>0&&<><div className="dependency-stage-arrow" aria-hidden="true"><svg viewBox="0 0 24 32"><path d="M12 2v26m-7-7 7 7 7-7" fill="none" stroke="currentColor" strokeWidth="1.5"/></svg></div><h4>基于这些知识，可以继续</h4><div className="dependency-stage-next" role="group" aria-label="后续学习入口">{stageNext.map(node=><button type="button" key={node.id} onClick={()=>{setSelected(node.id);setActiveLevel(positions.get(node.id)?.level||0)}}>{node.title}</button>)}</div></>}</div></div>:<><p className="dependency-map-hint">箭头向下阅读；可在图内滚动。键盘可用 Tab 选择，方向键沿关系移动。</p><div className="dependency-map-scroll" tabIndex={0} role="group" aria-label="学习依赖图，可滚动查看完整关系"><div className="dependency-map" style={{width:layout.width,height:layout.height}}>
          <svg width={layout.width} height={layout.height} aria-hidden="true"><defs><marker id={marker} viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="context-stroke"/></marker></defs>{visibleEdges.map(edge=>{const start=positions.get(edge.source),end=positions.get(edge.target);if(!start||!end)return null;const x1=start.x+NODE_WIDTH/2,y1=start.y+NODE_HEIGHT+4,x2=end.x+NODE_WIDTH/2,y2=end.y-7,mid=(y1+y2)/2;return <path key={edgeKey(edge)} d={`M ${x1} ${y1} C ${x1} ${mid}, ${x2} ${mid}, ${x2} ${y2}`} markerEnd={`url(#${marker})`} className={`dependency-edge ${edge.origin==='user_input'?'is-personal':''} ${selected&&relevant.has(edge.source)&&relevant.has(edge.target)?'is-connected':''} ${selected&&(!relevant.has(edge.source)||!relevant.has(edge.target))?'is-dimmed':''}`}><title>{title(edge.source)} → {title(edge.target)} · {originLabel(edge)}</title></path>})}</svg>
          {layout.positions.map(node=>{const record=curriculum?.checks.find(item=>item.id===node.id);return <button key={node.id} ref={element=>{nodeButtons.current[node.id]=element}} type="button" className={`dependency-node ${selected===node.id?'is-selected':''} ${selected&&!relevant.has(node.id)?'is-dimmed':''}`} style={{left:node.x,top:node.y,width:NODE_WIDTH,height:NODE_HEIGHT}} aria-label={`选择知识点：${node.title}`} aria-pressed={selected===node.id} onClick={()=>setSelected(node.id)} onKeyDown={event=>keyNavigate(event,node)}><strong>{node.title}</strong><span className={record?.state==='本轮通过'?'is-checked':''}>{record?.state||'基础课程'}</span></button>})}
        </div></div></>}</div>
        <aside className="dependency-detail" aria-label="知识点详情">{current?<><div className="dependency-detail-heading"><span>{current.id.startsWith('dp-')?'方法与实践':'先修基础'}</span><Button type="text" size="small" onClick={()=>{setSelected('');setOnlyPath(false)}}>取消选择</Button></div><h3>{current.title}</h3><p className="dependency-check-state">{check?`学习检查：${check.state}`:'此图尚未提供该基础知识的检查记录。'}</p>{check&&<p>已检查 {check.checked} 道不同题目{check.code_checked?'，含浏览器代码练习':'，尚无代码练习记录'}。</p>}{canLearn?<Link className="dependency-open-lesson" to={contextLink(lessonURL(current.id,projectId),params,{project:projectId,step:null,activity:null,returnTo:location.pathname+location.search})}>打开这节学习内容</Link>:<p>学习支持已关闭，可在个人或课题设置中开启。</p>}<h4>先了解这些</h4>{prerequisites.length?<ul>{prerequisites.map(edge=><li key={edgeKey(edge)}><button type="button" onClick={()=>setSelected(edge.source)}>{title(edge.source)}</button><span>{originLabel(edge)}</span><Button size="small" type="text" disabled={saving} onClick={()=>remove(edge)} aria-label={`移除依赖：${title(edge.source)}先于${current.title}`}>移除</Button></li>)}</ul>:<p>当前没有设置先修依赖，可以从这里开始。</p>}<h4>然后可以继续</h4>{successors.length?<ul>{successors.map(edge=><li key={edgeKey(edge)}><button type="button" onClick={()=>setSelected(edge.target)}>{title(edge.target)}</button><span>{originLabel(edge)}</span><Button size="small" type="text" disabled={saving} onClick={()=>remove(edge)} aria-label={`移除依赖：${current.title}先于${title(edge.target)}`}>移除</Button></li>)}</ul>:<p>当前没有后续依赖，可进入实践或调整学习顺序。</p>}<Button onClick={()=>{setTarget(current.id);setEditing(true)}}>为它添加先修知识</Button></>:<><h3>从图中选择一个知识点</h3><p>这里会显示它的先修知识、后续内容和已有检查记录。</p><p>实线表示教学建议，虚线表示你的调整。学习依赖可修改，与文献引用关系分开记录。</p></>}</aside>
      </div>
      {notice&&<p role="status" className="dependency-save-notice">{notice}</p>}
      <details className="dependency-list"><summary>以列表核对全部关系（{data.data.length}）</summary>{data.data.length?<ul>{data.data.map(edge=><li key={edgeKey(edge)}><button type="button" onClick={()=>setSelected(edge.source)}>{title(edge.source)}</button><span aria-label="先于">→</span><button type="button" onClick={()=>setSelected(edge.target)}>{title(edge.target)}</button><small>{originLabel(edge)}</small><Button size="small" type="text" disabled={saving} onClick={()=>remove(edge)}>移除此依赖</Button></li>)}</ul>:<p>尚无依赖关系。知识点仍可单独打开学习。</p>}</details>
      <div className="dependency-history"><Button type="text" onClick={()=>void loadHistory()} aria-expanded={historyOpen}>查看修改历史</Button>{historyOpen&&<>{historyError?<Alert type="error" message={historyError}/>:history.length?<ul>{history.map(item=><li key={item.version}>版本 {item.version} · {item.created_at} · {item.data.length} 条依赖</li>)}</ul>:<p>尚无修改记录。</p>}</>}</div>
    </>}
  </section>;
}
