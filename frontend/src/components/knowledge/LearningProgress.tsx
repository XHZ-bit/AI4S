import {useEffect,useRef,useState} from 'react';
import {getNodeProgress,saveNodeProgress,type LearningStatus,type NodeProgress} from '../../api/knowledgeExperience';
import './knowledge-experience.css';

export const learningStatusLabels:Record<LearningStatus,string>={not_started:'待学习',in_progress:'学习中',understood:'自评理解',review:'需复习'};
export default function LearningProgress({projectId,nodeId,onUpdated}:{projectId:string;nodeId:string;onUpdated?:()=>void}){
 const [progress,setProgress]=useState<NodeProgress>(),[busy,setBusy]=useState(false),[error,setError]=useState(''),[reload,setReload]=useState(0);
 const generation=useRef(0);
 useEffect(()=>{const c=new AbortController();generation.current++;setProgress(undefined);setError('');setBusy(false);getNodeProgress(projectId,nodeId,c.signal).then(value=>{if(!c.signal.aborted)setProgress(value)}).catch(e=>{if(!c.signal.aborted)setError(String(e))});return()=>{generation.current++;c.abort()}},[projectId,nodeId,reload]);
 async function update(status:LearningStatus){if(busy||!progress)return;const token=generation.current;setBusy(true);setError('');try{const next=await saveNodeProgress(projectId,nodeId,status,progress.version);if(token!==generation.current)return;setProgress(next);window.dispatchEvent(new CustomEvent('paperstride:learning-progress',{detail:{projectId,nodeId,status:next.status}}));onUpdated?.()}catch(e){if(token===generation.current)setError(String(e))}finally{if(token===generation.current)setBusy(false)}}
 return <div className="kw-learning-progress"><label>我的学习状态<select aria-label="我的学习状态" disabled={busy||!progress} value={progress?.status||'not_started'} onChange={e=>void update(e.target.value as LearningStatus)}>{Object.entries(learningStatusLabels).map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label><small>自评记录与论文审核状态分别保存。</small>{busy&&<span role="status">正在保存…</span>}{error&&<span className="kw-experience-error">学习状态读取或保存失败。<button onClick={()=>setReload(v=>v+1)}>重新读取</button></span>}</div>;
}
