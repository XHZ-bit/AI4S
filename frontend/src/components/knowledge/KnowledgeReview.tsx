import {useEffect,useState} from 'react';
import {Button,Input} from 'antd';
import type {KnowledgeNode,KnowledgeEdge,KnowledgeEvidence} from '../../api/knowledge';
import {getKnowledgeHistory,reviewKnowledge,type KnowledgeHistoryEntry,type ReviewAction} from '../../api/knowledgeReview';
import './knowledge-review.css';
import MathText,{displayMath} from '../learning/MathText';

const statusLabels:Record<string,string>={human_verified:'用户已核对',disputed:'有疑问',withdrawn:'已撤回',candidate:'待核对',auto_checked:'系统检查过，待人工核对',legacy_unverified:'历史内容，待核对'};
export default function KnowledgeReview({projectId,record,evidence,onSaved}:{projectId:string;record:KnowledgeNode|KnowledgeEdge;evidence:KnowledgeEvidence[];onSaved:()=>void}){
 const [open,setOpen]=useState(false),[reason,setReason]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
 const [history,setHistory]=useState<KnowledgeHistoryEntry[]>(),[historyOpen,setHistoryOpen]=useState(false),[retry,setRetry]=useState(0);
 const complete=record.evidence_ids.length>0&&record.evidence_ids.every(id=>evidence.some(e=>e.id===id&&!e.source_missing&&!e.source_changed&&!e.unresolved));
 const decision=record.metadata?.quality_decision as {actor?:string;at?:string;content_version?:number}|undefined;
 useEffect(()=>{setReason('');setError('');setNotice('');setHistory(undefined)},[record.id,record.version]);
 useEffect(()=>{if(!historyOpen)return;const c=new AbortController();setError('');getKnowledgeHistory(projectId,record.id,c.signal).then(v=>{if(!c.signal.aborted)setHistory(v.items)}).catch(e=>{if(!c.signal.aborted)setError('历史暂时无法读取：'+String(e))});return()=>c.abort()},[projectId,record.id,record.version,historyOpen,retry]);
 async function save(action:ReviewAction){if(busy||!reason.trim())return;setBusy(true);setError('');try{await reviewKnowledge(projectId,record,action,reason.trim());setNotice('已保存本次核对记录');onSaved()}catch(e){setError(e instanceof Error?e.message:String(e))}finally{setBusy(false)}}
 return <details className="kw-review-details" open={open} onToggle={event=>setOpen(event.currentTarget.open)}><summary>依据核对与修订历史</summary>{open&&<div>
  <p>{record.quality_review_stale?'内容或依据已变化，上次核对仅适用于历史版本':statusLabels[record.quality_status||'candidate']||'待核对'} · 内容版本 {record.version}</p>
  {decision&&<small>{decision.actor||'历史核对者'}{decision.at?' · '+decision.at:''}{decision.content_version?' · 针对版本 '+decision.content_version:''}</small>}
  <label>核对说明<Input.TextArea aria-label="核对说明" value={reason} onChange={event=>setReason(event.target.value)} rows={2} maxLength={4000} placeholder="记录你核对的依据或发现的问题"/></label>
  <div className="kw-review-actions"><Button size="small" disabled={busy||!reason.trim()||!complete} loading={busy} onClick={()=>void save('verify')}>我已核对原文</Button><Button size="small" disabled={busy||!reason.trim()} onClick={()=>void save('dispute')}>标记疑问</Button>{record.quality_status==='disputed'&&<Button size="small" disabled={busy||!reason.trim()} onClick={()=>void save('restore')}>恢复待核对</Button>}</div>
  {!complete&&<small>有效原文依据不完整，可先标记问题或修订内容。</small>}
  {error&&<p role="alert">{error}{historyOpen&&!history&&<Button type="link" size="small" onClick={()=>setRetry(v=>v+1)}>重试读取历史</Button>}</p>}{notice&&<p role="status">{notice}</p>}
  <details onToggle={event=>setHistoryOpen(event.currentTarget.open)}><summary>查看历史版本</summary>{historyOpen&&(history?<>{!history.length&&<p>还没有修订历史。</p>}{history.map((entry,index)=>{const value=(entry.snapshot.before||entry.snapshot) as Record<string,unknown>;const latex=(value.metadata as Record<string,unknown>|undefined)?.latex;return <article key={index}><small>{entry.created_at} · {entry.kind}</small><strong>{String(value.label||'历史记录')}{value.version?' · 版本 '+String(value.version):''}</strong><p><MathText text={String(value.summary||value.explanation||(typeof latex==='string'?displayMath(latex):'核对操作已记录'))} showSourceOnError/></p></article>})}</>:<p role="status">读取历史…</p>)}</details>
 </div>}</details>;
}
