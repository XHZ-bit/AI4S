import {useEffect,useRef,useState} from 'react';
import {Button,Checkbox,Input,Space,Spin} from 'antd';
import type {KnowledgeNode,KnowledgeEvidence} from '../../api/knowledge';
import {getNodeOutcomes,listNodeNotes,noteContext,previewNodeOutcomes,saveNodeNote,type KnowledgeNote,type OutcomeCatalog,type OutcomeSelection,type OutcomePreview} from '../../api/knowledgeOutcomes';
import {useCurrentAccount} from '../SessionContext';
import {download} from '../workbench/Notebook';
import KnowledgeText from './KnowledgeText';
import EvidenceQuote from './EvidenceQuote';
import './node-notebook.css';

type InitialDraft={text:string;origin:'saved_ai_answer'|'user';nonce?:string;evidence?:KnowledgeEvidence[]};
const emptySelection=():OutcomeSelection=>({note_ids:[],evidence_ids:[],learning_sections:[],practice_ids:[],comparison_cells:[],mappings:[]});
const sectionLabels:Record<string,string>={overview:'直观理解',definition:'定义',derivation:'公式与推导',prerequisites:'前置基础',implementation:'实现',limitations:'边界与限制'};
export default function NodeNotebook({projectId,node,initialDraft,onEvidence}:{projectId:string;node:KnowledgeNode;initialDraft?:InitialDraft;onEvidence?:(evidence:KnowledgeEvidence)=>void}){
 const account=useCurrentAccount();
 const scope=(account?.id||'local')+':'+projectId+':'+node.id;
 const draftKey='paperstride:node-note:'+scope;
 const [active,setActive]=useState<KnowledgeNote>(),[body,setBody]=useState(''),[questions,setQuestions]=useState(''),[origin,setOrigin]=useState<'user'|'saved_ai_answer'>('user');
 const [loading,setLoading]=useState(true),[saving,setSaving]=useState(false),[dirty,setDirty]=useState(false),[notice,setNotice]=useState(''),[error,setError]=useState(''),[conflict,setConflict]=useState<KnowledgeNote>(),[retry,setRetry]=useState(0);
 const [exportOpen,setExportOpen]=useState(false),[catalog,setCatalog]=useState<OutcomeCatalog>(),[exportBusy,setExportBusy]=useState(false),[exportError,setExportError]=useState(''),[selection,setSelection]=useState<OutcomeSelection>(emptySelection),[preview,setPreview]=useState<OutcomePreview>();
 const [references,setReferences]=useState<KnowledgeEvidence[]>([]);
 const generation=useRef(0),appliedDraft=useRef('');
 useEffect(()=>{
  const c=new AbortController();const gen=++generation.current;setLoading(true);setSaving(false);setBody('');setQuestions('');setDirty(false);setError('');setNotice('');setConflict(undefined);setActive(undefined);setOrigin('user');setExportOpen(false);setCatalog(undefined);setPreview(undefined);setSelection(emptySelection());appliedDraft.current='';setReferences([]);
  listNodeNotes(projectId,node.id,c.signal).then(result=>{
   if(c.signal.aborted||gen!==generation.current)return;
   const saved=(result.items||[]).find(item=>item.kind==='note'&&!item.id.startsWith('editor:'));
   const context=noteContext(saved);setActive(saved||{id:crypto.randomUUID(),version:0,title:node.label+' · 我的理解',body:'',kind:'note',project_id:projectId,source_json:'{}'});
   setBody(saved?.body||'');setQuestions(context.unresolved_questions||'');setOrigin(context.content_origin||'user');setReferences(context.evidence_references||[]);
   try{const local=JSON.parse(localStorage.getItem(draftKey)||'null');if(local?.scope===scope&&typeof local.body==='string'&&typeof local.questions==='string'){
    setBody(local.body);setQuestions(local.questions);setOrigin(local.origin==='saved_ai_answer'?'saved_ai_answer':'user');setActive(local.active||saved);setReferences(Array.isArray(local.references)?local.references:context.evidence_references||[]);setDirty(true);setNotice('已恢复未保存的草稿');
   }}catch{/* Editing still works without browser storage. */}
  }).catch(e=>{if(!c.signal.aborted)setError('笔记暂时无法读取：'+String(e))}).finally(()=>{if(!c.signal.aborted)setLoading(false)});
  return()=>{generation.current++;c.abort()};
 },[scope,draftKey,projectId,node.id,retry]);
 useEffect(()=>{if(loading||!dirty||!active)return;try{localStorage.setItem(draftKey,JSON.stringify({scope,body,questions,origin,active,references}))}catch{/* Explicit save remains available. */}},[body,questions,origin,active,references,dirty,loading,draftKey,scope]);
 useEffect(()=>{
  if(loading||!active||!initialDraft?.text.trim())return;
  const key=initialDraft.nonce||initialDraft.text;if(appliedDraft.current===key)return;appliedDraft.current=key;
  setBody(old=>[old,initialDraft.origin==='saved_ai_answer'?'从辅助回答保存（待核对）：\n'+initialDraft.text:initialDraft.text].filter(Boolean).join('\n\n'));setOrigin(initialDraft.origin);setReferences(old=>[...new Map([...old,...(initialDraft.evidence||[])].map(item=>[item.id+':'+item.source_version,item])).values()].slice(0,40));setDirty(true);setNotice('已加入草稿，请编辑后保存');setPreview(undefined);
 },[initialDraft,loading,active]);
 async function save(){
  if(saving||!active)return;const gen=generation.current;setSaving(true);setError('');setNotice('');
  const context=noteContext(active);
  try{
   const next=await saveNodeNote({id:active.id,version:active.version,title:active.title||node.label+' · 我的理解',body,project_id:projectId,knowledge_node_id:node.id,unresolved_questions:questions,content_origin:origin,evidence_references:references,
    ...(context.source_id?{source_id:context.source_id,block_id:context.block_id,source_version:context.source_version,node_version:context.node_version}:{})});
   if(gen!==generation.current)return;setActive(next);setDirty(false);setConflict(undefined);setNotice('已保存');setPreview(undefined);setCatalog(undefined);try{localStorage.removeItem(draftKey)}catch{}
   if(exportOpen)void loadExport();
   window.dispatchEvent(new CustomEvent('paperstride:records-change',{detail:{projectId}}));
   const savedContext=noteContext(next);
   window.dispatchEvent(new CustomEvent('paperstride:note-saved',{detail:{projectId,nodeId:node.id,unresolvedQuestions:questions,body,contentOrigin:origin,title:next.title,sourceId:savedContext.source_id,sourceVersion:savedContext.source_version,nodeVersion:savedContext.node_version}}));
  }catch(e){if(gen!==generation.current)return;
   if((e as {status?:number}).status===409){try{const current=await listNodeNotes(projectId,node.id);if(gen!==generation.current)return;setConflict((current.items||[]).find(item=>item.id===active.id));setError('笔记或来源已有更新。你的草稿已保留，请比较后保存。')}catch{setError('笔记已有更新，草稿已保留。请重新读取后核对。')}}else setError('保存未完成：'+String(e));
  }finally{if(gen===generation.current)setSaving(false)}
 }
 async function loadExport(){
  const gen=generation.current;setExportBusy(true);setExportError('');setPreview(undefined);
  try{const data=await getNodeOutcomes(projectId,node.id);if(gen!==generation.current)return;setCatalog(data);setSelection(emptySelection())}catch(e){if(gen===generation.current)setExportError('导出内容未能读取：'+String(e))}finally{if(gen===generation.current)setExportBusy(false)}
 }
 async function buildPreview(){const gen=generation.current;setExportBusy(true);setExportError('');try{const value=await previewNodeOutcomes(projectId,node.id,selection);if(gen===generation.current)setPreview(value)}catch(e){if(gen===generation.current)setExportError(String(e))}finally{if(gen===generation.current)setExportBusy(false)}}
 function toggleId(field:'note_ids'|'evidence_ids'|'practice_ids',id:string,checked:boolean){setSelection(old=>({...old,[field]:checked?[...old[field],id]:old[field].filter(x=>x!==id)}));setPreview(undefined)}
 const count=selection.note_ids.length+selection.evidence_ids.length+selection.learning_sections.length+selection.practice_ids.length+selection.comparison_cells.length+selection.mappings.length;
 return <section className="kw-node-notebook" aria-label="我的学习笔记">
  <header><h3>我的理解</h3><Button size="small" type="text" onClick={()=>{setExportOpen(v=>!v);if(!exportOpen)void loadExport()}} aria-expanded={exportOpen}>导出学习成果</Button></header>
  {loading?<Spin size="small"/>:<><Input.TextArea aria-label="我的理解" value={body} disabled={saving||!active} maxLength={50000} autoSize={{minRows:3,maxRows:10}} placeholder="用自己的话记录这个知识点。" onChange={e=>{setBody(e.target.value);setDirty(true);setPreview(undefined);setNotice('')}}/>
   {!!body.trim()&&<details><summary>预览笔记排版</summary><KnowledgeText text={body}/></details>}
   {!!references.length&&<section className="kw-note-references" aria-label="笔记原文依据"><h4>这份笔记的原文依据</h4><ul>{references.map(reference=><li key={reference.id+reference.source_version}><Button size="small" type="link" disabled={!onEvidence} onClick={()=>onEvidence?.(reference)}>{reference.source_title} · {reference.locator.page?'第 '+reference.locator.page+' 页':reference.locator.path||reference.locator.heading||'原文片段'}</Button>{(reference.source_missing||reference.source_changed||reference.unresolved)&&<span role="note">来源已变化，请复核；下方保留保存时的摘录。</span>}<details><summary>查看保存时的摘录与版本</summary><blockquote><EvidenceQuote evidence={reference}/></blockquote><small>{reference.source_version}</small></details><Button size="small" type="text" disabled={saving} onClick={()=>{setReferences(old=>old.filter(item=>!(item.id===reference.id&&item.source_version===reference.source_version)));setDirty(true);setPreview(undefined)}}>移除这条依据</Button></li>)}</ul></section>}
   <details><summary>未解决的问题{questions.trim()?' · 已记录':''}</summary><Input.TextArea aria-label="未解决的问题" value={questions} disabled={saving||!active} maxLength={12000} autoSize={{minRows:2,maxRows:6}} placeholder="还有哪一步没弄懂？" onChange={e=>{setQuestions(e.target.value);setDirty(true);setPreview(undefined);setNotice('')}}/></details>
   <div className="kw-node-note-actions"><Button size="small" loading={saving} disabled={!active||!dirty} onClick={()=>void save()}>保存笔记</Button><span role="status">{notice}</span></div>
  </>}
  {error&&<div role="alert" className="kw-node-note-error">{error}{!active&&<Button size="small" type="link" onClick={()=>setRetry(v=>v+1)}>重新读取</Button>}</div>}
  {conflict&&<div className="kw-node-note-conflict"><details><summary>查看已保存版本</summary><pre>{conflict.body}</pre></details><Space wrap><Button size="small" onClick={()=>{setActive(conflict);setBody(conflict.body);const context=noteContext(conflict);setQuestions(context.unresolved_questions||'');setOrigin(context.content_origin||'user');setReferences(context.evidence_references||[]);setDirty(false);setConflict(undefined);setError('');try{localStorage.removeItem(draftKey)}catch{}}}>采用已保存版本</Button><Button size="small" onClick={()=>{setActive(old=>old?{...old,version:conflict.version}:old);setConflict(undefined);setError('');setNotice('草稿已保留，请检查后再次保存')}}>保留我的草稿</Button></Space></div>}
  {exportOpen&&<div className="kw-node-note-export" aria-label="选择学习成果导出内容">
   {dirty&&<p>导出使用已保存内容；当前草稿可先保存。</p>}{exportBusy&&!catalog&&<Spin size="small"/>}{exportError&&<p role="alert">{exportError}</p>}
   {catalog&&<><p>选择要带走的内容：</p><div className="kw-outcome-choices">
    {catalog.notes?.map(item=><Checkbox key={item.id} checked={selection.note_ids.includes(item.id)} onChange={e=>toggleId('note_ids',item.id,e.target.checked)}>{item.title}</Checkbox>)}
    {catalog.evidence?.map(item=><Checkbox key={item.id} checked={selection.evidence_ids.includes(item.id)} onChange={e=>toggleId('evidence_ids',item.id,e.target.checked)}>原文依据 · {item.locator.page?'第 '+item.locator.page+' 页':item.locator.heading||item.source_title}</Checkbox>)}
    {catalog.lessons?.map(item=><details key={item.id}><summary>讲解 · {item.goal||'已保存讲解'}{item.stale?'（历史版本）':''}</summary>{Object.keys(item.sections).map(section=><Checkbox key={section} checked={selection.learning_sections.some(s=>s.artifact_id===item.id&&s.section===section)} onChange={e=>{setSelection(old=>({...old,learning_sections:e.target.checked?[...old.learning_sections,{artifact_id:item.id,revision:item.revision,section}]:old.learning_sections.filter(s=>!(s.artifact_id===item.id&&s.section===section))}));setPreview(undefined)}}>{sectionLabels[section]||section}</Checkbox>)}</details>)}
    {catalog.practices?.map(item=><Checkbox key={item.id} checked={selection.practice_ids.includes(item.id)} onChange={e=>toggleId('practice_ids',item.id,e.target.checked)}>练习 · {item.title}（{item.runs.length} 次记录）</Checkbox>)}
    {catalog.mappings?.map(item=><Checkbox key={item.id} checked={selection.mappings.some(m=>m.id===item.id)} onChange={e=>{setSelection(old=>({...old,mappings:e.target.checked?[...old.mappings,{id:item.id,revision:item.revision}]:old.mappings.filter(m=>m.id!==item.id)}));setPreview(undefined)}}>论文与代码映射 · {item.paper_span.slice(0,60)} · {item.status}{item.stale?'（历史版本）':''}</Checkbox>)}
    {catalog.comparisons?.map(item=><details key={item.id}><summary>已保存比较{item.stale?'（历史版本）':''}</summary>{item.cells.map(cell=><Checkbox key={cell.dimension+cell.source_id} checked={selection.comparison_cells.some(c=>c.comparison_id===item.id&&c.dimension===cell.dimension&&c.source_id===cell.source_id)} onChange={e=>{setSelection(old=>({...old,comparison_cells:e.target.checked?[...old.comparison_cells,{comparison_id:item.id,revision:item.revision,dimension:cell.dimension,source_id:cell.source_id}]:old.comparison_cells.filter(c=>!(c.comparison_id===item.id&&c.dimension===cell.dimension&&c.source_id===cell.source_id))}));setPreview(undefined)}}>{cell.dimension} · {cell.text.slice(0,60)}</Checkbox>)}</details>)}
   </div><Button size="small" loading={exportBusy} disabled={!count} onClick={()=>void buildPreview()}>预览所选内容</Button>{!catalog.notes?.length&&!catalog.evidence?.length&&!catalog.lessons?.length&&!catalog.practices?.length&&!catalog.comparisons?.length&&!catalog.mappings?.length&&<p>当前没有可导出的已保存成果。</p>}</>}
   {preview&&<><div className="kw-outcome-preview kw-math-preview" aria-label="学习成果导出预览"><KnowledgeText text={preview.markdown}/></div><details><summary>查看 Markdown 原文</summary><pre className="kw-outcome-preview">{preview.markdown}</pre></details><Button size="small" onClick={()=>download(preview.filename,preview.markdown,'text/markdown;charset=utf-8')}>下载 Markdown</Button></>}
  </div>}
 </section>;
}
