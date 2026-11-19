import {useEffect,useRef,useState,type ReactNode} from 'react';
import {getNodeProgress,getNodeSummary,explainNodeSummary,getProjectLearningSummary,explainProjectLearningSummary,saveNodeProgress,type LearningStatus,type NodeProgress,type NodeSummary,type ProjectLearningSummary,type SavedLearningExperience} from '../../api/knowledgeExperience';
import './knowledge-experience.css';
import './learning-progress-compact.css';
import MathText from '../learning/MathText';

export const learningStatusLabels:Record<LearningStatus,string>={not_started:'待学习',in_progress:'学习中',understood:'自评理解',review:'需复习'};
function SavedExperiences({items}:{items?:SavedLearningExperience[]}){
 if(!items?.length)return null;
 return <details><summary>AI 学习记录（{items.length}）</summary><p>由你保存，供回顾与核对。</p>{items.map(entry=><article key={entry.id}><small><time dateTime={entry.created_at}>{entry.created_at}</time></small><p style={{whiteSpace:'pre-wrap'}}><MathText text={entry.content} showSourceOnError/></p></article>)}</details>;
}
export interface LearningProgressProps {
 projectId:string;
 nodeId:string;
 onUpdated?:()=>void;
 onNode?:(id:string)=>void;
 variant?:'inline'|'dock';
 summaryVisible?:boolean;
 onOpenSummary?:()=>void;
 children?:ReactNode;
}
export default function LearningProgress({projectId,nodeId,onUpdated,onNode,variant='inline',summaryVisible,onOpenSummary,children}:LearningProgressProps){
 const [progress,setProgress]=useState<NodeProgress>(),[busy,setBusy]=useState(false),[error,setError]=useState(''),[reload,setReload]=useState(0);
 const [saved,setSaved]=useState(false);
 const [summary,setSummary]=useState<NodeSummary>(),[summaryBusy,setSummaryBusy]=useState(false),[summaryError,setSummaryError]=useState('');
 const [projectSummary,setProjectSummary]=useState<ProjectLearningSummary>(),[projectBusy,setProjectBusy]=useState(false);
 const generation=useRef(0);
 const summaryRequest=useRef<number>();
 const dock=variant==='dock',recordsVisible=summaryVisible!==false;
 useEffect(()=>{const c=new AbortController();generation.current++;setProgress(undefined);setSummary(undefined);setProjectSummary(undefined);setProjectBusy(false);setSummaryBusy(false);setSummaryError('');setError('');setBusy(false);setSaved(false);getNodeProgress(projectId,nodeId,c.signal).then(value=>{if(!c.signal.aborted)setProgress(value)}).catch(e=>{if(!c.signal.aborted)setError(String(e))});return()=>{generation.current++;c.abort()}},[projectId,nodeId,reload]);
 useEffect(()=>{if(dock&&summaryVisible===true)void loadSummary()},[projectId,nodeId,reload,dock,summaryVisible]);
 async function update(status:LearningStatus){if(busy||!progress)return;const token=generation.current;setBusy(true);setError('');setSaved(false);try{const next=await saveNodeProgress(projectId,nodeId,status,progress.version);if(token!==generation.current)return;setProgress(next);setSaved(true);window.dispatchEvent(new CustomEvent('paperstride:learning-progress',{detail:{projectId,nodeId,status:next.status}}));onUpdated?.();if(dock&&recordsVisible)void loadSummary()}catch(e){if(token===generation.current)setError(String(e))}finally{if(token===generation.current)setBusy(false)}}
 async function loadSummary(explain=false){const token=generation.current;if(summaryRequest.current===token)return;summaryRequest.current=token;setSummaryBusy(true);setSummaryError('');try{const value=await (explain?explainNodeSummary(projectId,nodeId):getNodeSummary(projectId,nodeId));if(token===generation.current)setSummary(value)}catch(e){if(token===generation.current)setSummaryError(String(e))}finally{if(summaryRequest.current===token)summaryRequest.current=undefined;if(token===generation.current)setSummaryBusy(false)}}
 async function loadProjectSummary(explain=false){const token=generation.current;setProjectBusy(true);setSummaryError('');try{const value=await (explain?explainProjectLearningSummary(projectId):getProjectLearningSummary(projectId));if(token===generation.current)setProjectSummary(value)}catch(e){if(token===generation.current)setSummaryError(String(e))}finally{if(token===generation.current)setProjectBusy(false)}}
 const statusControl=<label>我的学习状态<select aria-label="我的学习状态" disabled={busy||!progress} value={progress?.status||'not_started'} onChange={e=>void update(e.target.value as LearningStatus)}>{Object.entries(learningStatusLabels).map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label>;
 const openSummary=<button className={dock?'kw-learning-open-summary':undefined} type="button" disabled={summaryBusy} aria-controls={dock?'kw-learning-tool-records-panel':undefined} aria-expanded={dock?recordsVisible:undefined} onClick={()=>{onOpenSummary?.();void loadSummary()}}>{summaryBusy?'读取中…':'查看学习小结'}</button>;
 const stageButton=onNode&&<button type="button" disabled={projectBusy} onClick={()=>void loadProjectSummary()}>{projectBusy?'读取中…':'查看阶段记录'}</button>;
 const errorMessage=error&&<span className="kw-experience-error" role="alert">学习状态读取或保存失败。<button type="button" onClick={()=>setReload(v=>v+1)}>重新读取</button></span>;
 const records=<>
  {dock&&<>
   <details className="kw-learning-record-scope"><summary>学习记录说明</summary><p>自评记录与论文审核状态分别保存。</p>{summary&&<p>{summary.scope}，共 {summary.run_count} 次。</p>}{projectSummary&&<p>{projectSummary.scope}</p>}</details>
   {stageButton}
  </>}
  {summaryError&&<span role="alert">记录读取失败，请重试。</span>}
  {summary&&<div role="status">
   <p>{summary.recommendation}</p>
   {summary.suggested_node&&onNode&&<p>根据已有前置关系，可选复习 <button type="button" onClick={()=>onNode(summary.suggested_node!.id)}>{summary.suggested_node.label}</button>。</p>}
   {!dock&&<small>{summary.scope}，共 {summary.run_count} 次。</small>}
   <SavedExperiences items={summary.saved_experiences}/>
   {summary.recent_runs.length>0&&<ul>{summary.recent_runs.map(run=><li key={run.id}>{run.created_at} · {run.status==='success'?'运行完成':run.status==='error'?'运行出错':run.status==='timeout'?'运行超时':'已停止'}</li>)}</ul>}
   <button type="button" disabled={summaryBusy} onClick={()=>void loadSummary(true)}>生成 AI 学习建议</button>
   {dock?<details className="kw-learning-record-scope"><summary>AI 建议使用说明</summary><p>将当前节点、近期运行状态和最多 5 条经验的片段发送给所选模型。</p></details>:<small>将当前节点、近期运行状态和最多 5 条经验的片段发送给所选模型。</small>}
   {summary.explanation&&<p><MathText text={summary.explanation} showSourceOnError/>{summary.cached?'（已保存）':''}</p>}{summary.error&&<p>{summary.error}</p>}
  </div>}
  {projectSummary&&<section aria-label="阶段学习记录">
   {!dock&&<p>{projectSummary.scope}</p>}
   {!projectSummary.items.length&&<p>当前空间还没有学习记录。</p>}
   <ul>{projectSummary.items.map(item=><li key={item.node_id}>
    <button type="button" onClick={()=>onNode?.(item.node_id)}>{item.node_label}</button> · {learningStatusLabels[item.status]} · 运行 {item.run_count} 次
    <p><MathText text={item.recommendation}/></p>
    {item.experience_entries?.map((entry,index)=><p key={entry.kind+index}><MathText text={entry.reason}/></p>)}
    <SavedExperiences items={item.saved_experiences}/>
    {item.suggested_node&&<button type="button" onClick={()=>onNode?.(item.suggested_node!.id)}>复习 {item.suggested_node.label}</button>}
   </li>)}</ul>
   {projectSummary.truncated&&<p>当前仅显示前 50 个有记录的节点。</p>}
   <button type="button" disabled={projectBusy||!projectSummary.items.length} onClick={()=>void loadProjectSummary(true)}>生成 AI 阶段建议</button>
   {dock?<details className="kw-learning-record-scope"><summary>AI 阶段建议使用说明</summary><p>将前 20 个节点的学习状态、运行统计和每个节点最多 2 条经验片段发送给所选模型。</p></details>:<small>将前 20 个节点的学习状态、运行统计和每个节点最多 2 条经验片段发送给所选模型。</small>}
   {projectSummary.explanation&&<p><MathText text={projectSummary.explanation} showSourceOnError/>{projectSummary.cached?'（已保存）':''}</p>}
   {projectSummary.error&&<p>{projectSummary.error}</p>}
  </section>}
 </>;
 return <div className={'kw-learning-progress'+(dock?' kw-learning-progress--dock':'')}>
  {dock?<>
   <div className="kw-learning-progress-status">{statusControl}{openSummary}</div>
   <div className="kw-learning-progress-feedback" role="status">{busy?'正在保存…':saved?'学习状态已保存：'+learningStatusLabels[progress?.status||'not_started']:''}</div>
   {errorMessage}
  </>:<>{statusControl}<small>自评记录与论文审核状态分别保存。</small>{busy&&<span role="status">正在保存…</span>}{errorMessage}{openSummary}{stageButton}</>}
  {children}
  {dock?<div id="kw-learning-tool-records-panel" className="kw-learning-progress-records" role="tabpanel" aria-labelledby="kw-learning-tool-records-tab" hidden={!recordsVisible}>{records}</div>:records}
 </div>;
}
