import {useEffect,useRef,useState} from 'react';
import {Button,Input,Spin} from 'antd';
import {UploadOutlined} from '@ant-design/icons';
import type {KnowledgeSource} from '../../api/knowledge';
import {bindNodeMaterial,getNodeMaterials,updateNodeMaterial,uploadNodeMaterial,type NodeMaterial} from '../../api/knowledgeMaterials';
import {useCurrentAccount} from '../SessionContext';
import './node-materials.css';

export default function NodeMaterials({projectId,nodeId,sources=[],enabled=true,onRead,onUpdated}:{
 projectId:string;nodeId:string;sources?:KnowledgeSource[];enabled?:boolean;onRead:(sourceId:string)=>void;onUpdated:()=>void;
}){
 const account=useCurrentAccount();const scope=(account?.id||'local')+':'+projectId+':'+nodeId;
 const [items,setItems]=useState<NodeMaterial[]>([]),[loading,setLoading]=useState(false),[busy,setBusy]=useState(''),[error,setError]=useState(''),[notice,setNotice]=useState(''),[retry,setRetry]=useState(0);
 const [adding,setAdding]=useState(false),[source,setSource]=useState<string>(),[note,setNote]=useState('');
 const [editing,setEditing]=useState<string>(),[draft,setDraft]=useState('');
 const [pendingFile,setPendingFile]=useState<File>();
 const generation=useRef(0),inFlight=useRef(false),input=useRef<HTMLInputElement>(null),readController=useRef<AbortController>();
 useEffect(()=>{generation.current++;inFlight.current=false;readController.current?.abort();setItems([]);setBusy('');setError('');setNotice('');setSource(undefined);setNote('');setAdding(false);setEditing(undefined);setDraft('');setPendingFile(undefined);if(input.current)input.current.value='';return()=>{generation.current++;readController.current?.abort()}},[scope]);
 useEffect(()=>{
  if(!enabled)return;const controller=new AbortController();readController.current?.abort();readController.current=controller;setLoading(true);setError('');
  getNodeMaterials(projectId,nodeId,controller.signal).then(value=>{if(!controller.signal.aborted)setItems(value.items)}).catch(cause=>{if(!controller.signal.aborted)setError('节点资料暂未读取：'+String(cause))}).finally(()=>{if(!controller.signal.aborted)setLoading(false)});
  return()=>controller.abort();
 },[scope,projectId,nodeId,enabled,retry]);
 async function change(key:string,operation:()=>Promise<{item:NodeMaterial}>,message:string){
  if(inFlight.current)return;inFlight.current=true;const gen=generation.current;readController.current?.abort();setLoading(false);setBusy(key);setError('');setNotice('');
  try{const value=await operation();if(gen!==generation.current)return;setItems(old=>value.item.removed?old.filter(item=>item.id!==value.item.id):[value.item,...old.filter(item=>item.id!==value.item.id)]);setAdding(false);setSource(undefined);setNote('');setEditing(undefined);setDraft('');setPendingFile(undefined);if(input.current)input.current.value='';setNotice(message);onUpdated()}
  catch(cause){if(gen===generation.current){
   const saved=(cause as {savedSource?:{id:string}}).savedSource;
   if(saved){setSource(saved.id);setPendingFile(undefined);setError('资料已保存在课题中，关联未完成。请从已有资料重试关联。');onUpdated()}
   else setError((cause as {status?:number}).status===409?'资料关联已在其他位置更新。输入已保留，请重新读取后核对。':'操作未完成，输入已保留：'+String(cause));
  }}
  finally{if(gen===generation.current){setBusy('');inFlight.current=false}}
 }
 const usable=sources.filter(item=>!item.removed&&!items.some(material=>material.source_id===item.id));
 return <section className="kw-node-materials" aria-label="节点资料">
  <header><h3>节点资料{items.length?' · '+items.length:''}</h3><Button size="small" disabled={!!busy} onClick={()=>setAdding(value=>!value)}>{adding?'收起添加':'添加资料'}</Button></header>
  {adding&&<div className="kw-node-material-form">
   <label>资料说明<Input.TextArea aria-label="节点资料说明" value={note} maxLength={4000} autoSize={{minRows:2,maxRows:5}} disabled={!!busy} placeholder="记录这份资料与当前节点的关系。" onChange={event=>setNote(event.target.value)}/></label>
   <div><input ref={input} className="kw-material-file" aria-label="上传节点资料" type="file" disabled={!!busy} onChange={event=>setPendingFile(event.target.files?.[0])}/><Button icon={<UploadOutlined/>} disabled={!!busy} onClick={()=>input.current?.click()}>选择本地文件</Button>{pendingFile&&<p className="kw-material-filename">{pendingFile.name}</p>}<Button type="primary" disabled={!!busy||!pendingFile} loading={busy==='upload'} onClick={()=>pendingFile&&void change('upload',()=>uploadNodeMaterial(projectId,nodeId,pendingFile,note),'资料已导入并保存到当前节点')}>导入并关联</Button></div>
   {!!usable.length&&<div className="kw-material-existing"><label>当前课题已有资料<select aria-label="关联已有课题资料" value={source||''} disabled={!!busy} onChange={event=>setSource(event.target.value||undefined)}><option value="">选择已导入的资料</option>{usable.map(item=><option key={item.id} value={item.id}>{item.title}</option>)}</select></label><Button disabled={!!busy||!source} loading={busy==='bind'} onClick={()=>source&&void change('bind',()=>bindNodeMaterial(projectId,nodeId,source,note),'资料已关联到当前节点')}>关联所选资料</Button></div>}
  </div>}
  {loading&&<div role="status"><Spin size="small"/> 读取节点资料…</div>}{notice&&<p role="status">{notice}</p>}
  {error&&<div role="alert"><p>{error}</p><Button type="link" size="small" disabled={!!busy} onClick={()=>setRetry(value=>value+1)}>重新读取资料</Button></div>}
  {!items.length&&!loading&&!error&&<p className="kw-material-empty">把需要反复查阅的论文、代码或研究记录放到这个节点。</p>}
  {!!items.length&&<ul className="kw-node-material-list">{items.map(item=><li key={item.id}>
   <strong>{item.current_source?.title||item.source_snapshot.title}</strong>
   {item.source_missing?<p className="kw-material-state">资料已移除，保存时的说明仍保留。</p>:item.source_changed&&<p className="kw-material-state">资料已有更新，请重新核对关联说明。</p>}
   {editing===item.id?<><Input.TextArea aria-label="编辑资料说明" value={draft} maxLength={4000} disabled={!!busy} autoSize={{minRows:2,maxRows:6}} onChange={event=>setDraft(event.target.value)}/><div className="kw-material-actions"><Button size="small" loading={busy===item.id} disabled={!!busy} onClick={()=>void change(item.id,()=>updateNodeMaterial(projectId,nodeId,item.id,{expected_revision:item.revision,note:draft}),'资料说明已保存')}>保存说明</Button><Button type="text" size="small" disabled={!!busy} onClick={()=>setEditing(undefined)}>取消</Button></div></>:<>{item.note&&<p className="kw-material-note">{item.note}</p>}<div className="kw-material-actions"><Button size="small" disabled={item.source_missing||!!busy} onClick={()=>onRead(item.source_id)}>查看资料</Button><Button size="small" type="text" disabled={!!busy} onClick={()=>{setEditing(item.id);setDraft(item.note)}}>编辑说明</Button><Button size="small" type="text" disabled={!!busy} onClick={()=>void change(item.id,()=>updateNodeMaterial(projectId,nodeId,item.id,{expected_revision:item.revision,removed:true}),'已移除关联，课题中的原资料仍保留')}>移除关联</Button></div></>}
   <details><summary>关联记录</summary><p>{item.source_snapshot.filename} · 保存版本 {item.source_snapshot.version}</p><small>{item.updated_at} · {item.reviewed_by} · 修订 {item.revision}</small></details>
  </li>)}</ul>}
 </section>;
}
