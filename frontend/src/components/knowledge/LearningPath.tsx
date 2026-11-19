import {useEffect,useState} from 'react';
import {getKnowledgePath,getLearningProgress,type KnowledgePath,type NodeProgress} from '../../api/knowledgeExperience';
import {learningStatusLabels} from './LearningProgress';

export default function LearningPath({projectId,nodeId,onNode}:{projectId:string;nodeId:string;onNode:(id:string)=>void}){
 const [path,setPath]=useState<KnowledgePath>();
 const [progress,setProgress]=useState<NodeProgress[]>();
 const [error,setError]=useState('');
 const [progressError,setProgressError]=useState(false);
 const [open,setOpen]=useState(true);
 const [retry,setRetry]=useState(0);

 useEffect(()=>{
  setPath(undefined);setProgress(undefined);setError('');setProgressError(false);
  if(!open)return;
  const controller=new AbortController();
  getKnowledgePath(projectId,{source:nodeId,kind:'prerequisites',max_depth:4},controller.signal)
   .then(value=>{if(!controller.signal.aborted)setPath(value)})
   .catch(e=>{if(!controller.signal.aborted)setError(String(e))});
  getLearningProgress(projectId,controller.signal)
   .then(result=>{if(!controller.signal.aborted)setProgress(result.items)})
   .catch(()=>{if(!controller.signal.aborted)setProgressError(true)});
  return()=>controller.abort();
 },[projectId,nodeId,open,retry]);

 useEffect(()=>{
  if(!open)return;
  const refresh=(event:Event)=>{
   const detail=(event as CustomEvent<{projectId:string}>).detail;
   if(detail?.projectId===projectId)setRetry(value=>value+1);
  };
  window.addEventListener('paperstride:learning-progress',refresh);
  return()=>window.removeEventListener('paperstride:learning-progress',refresh);
 },[open,projectId]);

 const progressByNode=new Map(progress?.map(item=>[item.node_id,item])||[]);
 const orderedNodes=path?.paths.flatMap(item=>item.node_ids)||[];
 const nextId=progress&&!path?.cycle_detected?orderedNodes.find(id=>{
  if(id===nodeId)return false;
  const item=progressByNode.get(id);
  return !item||item.stale||item.status!=='understood';
 }):undefined;
 const nextNode=path?.nodes.find(node=>node.id===nextId);
 return <details className="kw-learning-path" open={open} onToggle={e=>setOpen(e.currentTarget.open)}>
  <summary>沿图谱查看前置学习路径</summary>
  {open&&(!path&&!error?<p role="status">读取前置关系…</p>:error?<p>路径暂未读取：{error} <button onClick={()=>setRetry(v=>v+1)}>重试</button></p>:path&&<>
   <p>{path.message||'以下路径来自当前空间已保存的前置知识关系，可按需要选择。'}</p>
   {path.cycle_detected&&<p role="note">部分前置关系形成循环，已停止重复展开；请结合原文核对。</p>}
   {path.truncated&&<p>当前显示有界路径，可进入节点继续展开。</p>}
   {progressError&&<p>学习记录暂时无法读取，仍可浏览路径。<button onClick={()=>setRetry(v=>v+1)}>重试</button></p>}
   {nextNode&&<div className="kw-path-next"><span>建议下一步</span><button onClick={()=>onNode(nextNode.id)} disabled={nextNode.id===nodeId}>{nextNode.label}</button><small>根据当前路径顺序和你的自评选择，你也可以自行选择其他节点。</small></div>}
   <div className="kw-path-map" role="region" aria-label="前置学习地图" tabIndex={0}>{path.paths.map((item,i)=><ol key={i} className="kw-learning-path-steps" aria-label={path.paths.length>1?'学习分支 '+(i+1):'学习路径'}>{item.node_ids.map((id,j)=>{
    const node=path.nodes.find(n=>n.id===id),state=progressByNode.get(id);
    return <li key={id+':'+j} className={'kw-path-step'+(id===nodeId?' is-current':'')+(id===nextId?' is-recommended':'')}>
     <div className="kw-path-node">
      <span className="kw-path-node-marker" aria-hidden="true">{state?.status==='understood'&&!state.stale?'✓':j+1}</span>
      <div className="kw-path-node-content"><button disabled={id===nodeId} onClick={()=>onNode(id)}>{node?.label||'关联知识'}</button>
       <div className="kw-path-node-meta">{id===nodeId&&<span>当前节点</span>}{id===nextId&&id!==nodeId&&<span>建议学习</span>}{progress&&<span className="kw-path-status">{state?.stale?'需要重新确认':learningStatusLabels[state?.status||'not_started']}</span>}</div>
      </div>
     </div>
     {j<item.edge_ids.length&&<div className="kw-path-connection"><span aria-hidden="true" className="kw-path-arrow">→</span><small>{path.edges.find(edge=>edge.id===item.edge_ids[j])?.explanation||'关系详情暂不可用'}</small></div>}
    </li>;
   })}</ol>)}</div>
  </>)}
 </details>;
}
