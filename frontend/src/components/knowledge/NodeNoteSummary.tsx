import {useEffect,useState} from 'react';
import {Button} from 'antd';
import {listNodeNotes,noteContext,type KnowledgeNote} from '../../api/knowledgeOutcomes';
import {useCurrentAccount} from '../SessionContext';
import KnowledgeText from './KnowledgeText';
import './node-materials.css';

export default function NodeNoteSummary({projectId,nodeId,onEdit}:{projectId:string;nodeId:string;onEdit:()=>void}){
 const account=useCurrentAccount();
 const [saved,setSaved]=useState<{body:string;origin:string}>(),[loading,setLoading]=useState(true),[error,setError]=useState(false),[expanded,setExpanded]=useState(false);
 useEffect(()=>{
  const controller=new AbortController();setSaved(undefined);setLoading(true);setError(false);setExpanded(false);
  let revision=0;
  const update=(event:Event)=>{const detail=(event as CustomEvent).detail;if(detail?.projectId===projectId&&detail.nodeId===nodeId){revision++;setSaved({body:String(detail.body||''),origin:detail.contentOrigin==='saved_ai_answer'?'saved_ai_answer':'user'});setLoading(false);setError(false)}};
  window.addEventListener('paperstride:note-saved',update);
  listNodeNotes(projectId,nodeId,controller.signal).then(value=>{
   if(controller.signal.aborted||revision)return;
   const item:KnowledgeNote|undefined=value.items.find(note=>note.kind==='note'&&!note.id.startsWith('editor:'));
   if(item)setSaved({body:item.body,origin:noteContext(item).content_origin||'user'});
  }).catch(()=>{if(!controller.signal.aborted&&!revision)setError(true)}).finally(()=>{if(!controller.signal.aborted)setLoading(false)});
  return()=>{controller.abort();window.removeEventListener('paperstride:note-saved',update)};
 },[projectId,nodeId,account?.id]);
 if(loading)return null;
 if(!saved?.body.trim())return <div className="kw-node-note-entry"><Button size="small" onClick={onEdit}>{error?'查看节点笔记':'记录文字'}</Button></div>;
 const long=saved.body.length>220;
 return <section className="kw-node-note-summary" aria-label="已保存节点笔记"><header><h3>{saved.origin==='saved_ai_answer'?'保存的回答摘录':'我的笔记'}</h3><Button size="small" type="text" onClick={onEdit}>编辑笔记</Button></header>
  <div className={'kw-node-note-summary-body'+(long&&!expanded?' is-collapsed':'')}><KnowledgeText text={saved.body}/></div>
  {long&&<Button size="small" type="link" onClick={()=>setExpanded(value=>!value)}>{expanded?'收起笔记':'展开全文'}</Button>}
 </section>;
}
