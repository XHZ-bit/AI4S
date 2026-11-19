import {useEffect,useRef,useState} from 'react';
import {Button,Checkbox,Input,Space} from 'antd';
import type {KnowledgeComparison,KnowledgeEvidence,KnowledgeSource} from '../../api/knowledge';
import {listComparisonOutcomes,previewComparisonOutcome,saveComparisonOutcome,type ComparisonOutcome as Outcome,type ComparisonSelection} from '../../api/knowledgeComparison';
import {useCurrentAccount} from '../SessionContext';
import {download} from '../workbench/Notebook';
import {EvidenceList} from './KnowledgeSources';
import KnowledgeText from './KnowledgeText';

export default function ComparisonOutcome({projectId,comparison,sources,onEvidence,initialQuestion=''}:{projectId:string;comparison:KnowledgeComparison;sources:KnowledgeSource[];initialQuestion?:string;onEvidence:(e:KnowledgeEvidence)=>void}){
 const account=useCurrentAccount();
 const scope=(account?.id||'local')+':'+projectId+':'+comparison.id;
 const draftKey='paperstride:comparison-outcome:'+scope;
 const [open,setOpen]=useState(false),[question,setQuestion]=useState(''),[interpretation,setInterpretation]=useState(''),[unresolved,setUnresolved]=useState('');
 const [selection,setSelection]=useState<ComparisonSelection[]>([]),[preview,setPreview]=useState<Outcome>(),[saved,setSaved]=useState<Outcome[]>([]);
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState(''),[retry,setRetry]=useState(0);
 const generation=useRef(0);
 const [draftScope,setDraftScope]=useState('');
 useEffect(()=>{
  generation.current++;setQuestion(initialQuestion);setInterpretation('');setUnresolved('');setSelection([]);setPreview(undefined);setSaved([]);setBusy(false);setError('');setNotice('');
  try{
   const draft=JSON.parse(localStorage.getItem(draftKey)||'null');
   if(draft?.scope===scope){setQuestion(typeof draft.question==='string'?draft.question:'');setInterpretation(typeof draft.interpretation==='string'?draft.interpretation:'');setUnresolved(typeof draft.unresolved==='string'?draft.unresolved:'');}
  }catch{/* Saving to the server remains available. */}
  setDraftScope(scope);
  return()=>{generation.current++};
 },[scope,draftKey,initialQuestion]);
 useEffect(()=>{if(draftScope!==scope)return;try{localStorage.setItem(draftKey,JSON.stringify({scope,question,interpretation,unresolved}))}catch{/* The user's text stays in the editor. */}},[draftScope,scope,draftKey,question,interpretation,unresolved]);
 useEffect(()=>{setPreview(undefined);setSelection(old=>old.filter(s=>comparison.rows.some(r=>r.dimension===s.dimension&&r.values.some(v=>v.source_id===s.source_id))))},[comparison.id,comparison.revision]);
 useEffect(()=>{
  if(!open)return;const c=new AbortController();
  listComparisonOutcomes(projectId,comparison.id,c.signal).then(r=>{if(!c.signal.aborted)setSaved(r.items)}).catch(e=>{if(!c.signal.aborted)setError(String(e))});
  return()=>c.abort();
 },[open,projectId,comparison.id,retry]);
 const changed=()=>{setPreview(undefined);setNotice('')};
 const build=async(save:boolean)=>{
  if(busy||!selection.length)return;const token=generation.current;setBusy(true);setError('');setNotice('');
  const body={expected_revision:comparison.revision||1,selections:selection,question,interpretation,unresolved};
  try{
   const value=await (save?saveComparisonOutcome:previewComparisonOutcome)(projectId,comparison.id,body);
   if(token!==generation.current)return;setPreview(value);
   if(save){setSaved(old=>[value,...old]);setNotice('比较成果已保存，包含原文位置与版本快照');}
  }catch(e){if(token===generation.current)setError(String(e))}finally{if(token===generation.current)setBusy(false)}
 };
 return <details className="kw-comparison-outcome" open={open} onToggle={e=>setOpen(e.currentTarget.open)}><summary>保存我的比较成果</summary>
  {open&&<><p>选择本次要保留的比较项，写下自己的理解。保存后可以重开和导出。</p>
   <div className="kw-comparison-outcome-fields"><label>我的研究问题<Input.TextArea aria-label="比较成果研究问题" value={question} maxLength={1500} autoSize={{minRows:2,maxRows:4}} onChange={e=>{setQuestion(e.target.value);changed()}}/></label>
   <label>我的理解<Input.TextArea aria-label="比较成果我的理解" value={interpretation} maxLength={12000} autoSize={{minRows:3,maxRows:8}} onChange={e=>{setInterpretation(e.target.value);changed()}}/></label>
   <label>未解决的问题<Input.TextArea aria-label="比较成果未解决的问题" value={unresolved} maxLength={12000} autoSize={{minRows:2,maxRows:5}} onChange={e=>{setUnresolved(e.target.value);changed()}}/></label></div>
   <fieldset className="kw-comparison-outcome-choices"><legend>选择比较内容 · 已选 {selection.length} 项</legend>{comparison.rows.map(row=><div key={row.dimension}><strong>{row.dimension}</strong>{row.values.map(cell=><Checkbox key={cell.source_id} checked={selection.some(s=>s.dimension===row.dimension&&s.source_id===cell.source_id)} onChange={e=>{setSelection(old=>e.target.checked?[...old,{dimension:row.dimension,source_id:cell.source_id}]:old.filter(s=>!(s.dimension===row.dimension&&s.source_id===cell.source_id)));changed()}}><span className="kw-comparison-choice-source">{sources.find(s=>s.id===cell.source_id)?.title||'历史资料'} · {row.dimension}</span><span>{cell.text.slice(0,100)||'尚未补充'}</span></Checkbox>)}</div>)}</fieldset>
   <Space wrap><Button aria-label="预览比较成果" disabled={!selection.length||busy} onClick={()=>void build(false)}>预览比较成果</Button><Button type="primary" aria-label="保存比较成果" aria-busy={busy} disabled={!selection.length||busy} loading={busy} onClick={()=>void build(true)}>保存比较成果</Button><span role="status">{notice}</span></Space>
   {error&&<div role="alert">{error}<Button type="link" onClick={()=>setRetry(v=>v+1)}>重新读取已保存成果</Button></div>}
   {preview&&<div className="kw-comparison-outcome-preview"><div className="kw-math-preview" aria-label="比较成果导出预览"><KnowledgeText text={preview.markdown}/></div><details><summary>查看 Markdown 原文</summary><pre>{preview.markdown}</pre></details><Button onClick={()=>download('paperstride-comparison.md',preview.markdown,'text/markdown;charset=utf-8')}>下载比较 Markdown</Button><EvidenceList items={[...new Map(preview.cells.flatMap(c=>c.evidence).map(e=>[e.id,e])).values()]} onOpen={onEvidence}/></div>}
   {!!saved.length&&<section><h3>已保存的比较成果</h3><ul>{saved.map(item=><li key={item.id}><Button type="link" onClick={()=>{setPreview(item);setNotice('正在查看已保存快照')}}>{item.title} · {new Date(item.created_at).toLocaleString()}</Button>{(item.comparison_changed||!!item.source_changes?.length)&&<span>比较或来源已变化，保留保存时的判断</span>}</li>)}</ul></section>}
  </>}
 </details>;
}
