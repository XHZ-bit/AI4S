import {useEffect,useRef,useState} from 'react';
import {Button,Input,Select} from 'antd';
import type {KnowledgeNode} from '../../api/knowledge';
import {createManualNode,type ManualNodeKind} from '../../api/knowledgeMaterials';
import {useCurrentAccount} from '../SessionContext';
import './node-materials.css';

export default function NodeCreate({projectId,onCreated,onCancel}:{projectId:string;onCreated:(node:KnowledgeNode)=>void;onCancel:()=>void}){
 const account=useCurrentAccount();
 const [label,setLabel]=useState(''),[summary,setSummary]=useState(''),[kind,setKind]=useState<ManualNodeKind>('concept'),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const generation=useRef(0),inFlight=useRef(false);
 useEffect(()=>{generation.current++;inFlight.current=false;setLabel('');setSummary('');setKind('concept');setBusy(false);setError('');return()=>{generation.current++}},[projectId,account?.id]);
 async function save(){
  if(inFlight.current||!label.trim())return;inFlight.current=true;const gen=generation.current;setBusy(true);setError('');
  try{const value=await createManualNode(projectId,{label:label.trim(),summary:summary.trim(),kind});if(gen===generation.current)onCreated(value.node)}
  catch(cause){if(gen===generation.current)setError('节点未保存，输入已保留：'+String(cause))}
  finally{if(gen===generation.current){setBusy(false);inFlight.current=false}}
 }
 return <section className="kw-node-create" aria-label="新增课题节点"><header><h3>新增课题节点</h3></header>
  <div className="kw-node-create-fields"><label>节点名称<Input aria-label="新节点名称" value={label} disabled={busy} maxLength={250} placeholder="例如：实验设计、待验证的想法" onChange={event=>setLabel(event.target.value)}/></label>
   <label>节点类型<Select aria-label="新节点类型" value={kind} disabled={busy} onChange={setKind} options={[{value:'concept',label:'概念'},{value:'method',label:'方法'},{value:'formula',label:'公式'},{value:'experiment',label:'实验'},{value:'finding',label:'发现'}]}/></label>
   <label>节点说明<Input.TextArea aria-label="新节点说明" value={summary} disabled={busy} maxLength={30000} autoSize={{minRows:3,maxRows:10}} placeholder="写下含义、研究思路或准备整理的内容。" onChange={event=>setSummary(event.target.value)}/></label></div>
  {error&&<p role="alert">{error}</p>}<div className="kw-node-create-actions"><Button type="primary" disabled={!label.trim()||busy} loading={busy} onClick={()=>void save()}>保存节点</Button><Button disabled={busy} onClick={onCancel}>取消新增</Button></div>
 </section>;
}
