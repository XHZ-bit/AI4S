import {useEffect,useId,useRef,useState} from 'react';
import {Alert,Button,Select,Space} from 'antd';
import {getKnowledgePath,type KnowledgePath} from '../../api/unifiedGraph';
import type {KnowledgeNode} from '../../api/knowledge';
import {originLabels} from '../../api/knowledge';
import MathText from '../learning/MathText';

export default function KnowledgePathPanel({projectId,nodes,currentNode,onNode,onResult}:{projectId:string;nodes:KnowledgeNode[];currentNode?:string;onNode:(node:KnowledgeNode)=>void;onResult:(value:KnowledgePath|undefined)=>void}){
 const [source,setSource]=useState(currentNode),[target,setTarget]=useState<string>(),[kind,setKind]=useState('connection');
 const [result,setResult]=useState<KnowledgePath>(),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const request=useRef<AbortController>();
 const [expanded,setExpanded]=useState(false);
 const detailsId=useId();
 useEffect(()=>{setSource(currentNode)},[currentNode]);
 useEffect(()=>()=>request.current?.abort(),[projectId]);
 const find=async(start=source,pathKind=kind)=>{if(!start)return;setExpanded(true);request.current?.abort();const c=new AbortController();request.current=c;setBusy(true);setError('');try{const value=await getKnowledgePath(projectId,start,pathKind==='connection'?target:undefined,pathKind,c.signal);if(!c.signal.aborted){setResult(value);onResult(value.nodes.length?value:undefined)}}catch(e){if(!c.signal.aborted)setError(String(e))}finally{if(!c.signal.aborted)setBusy(false)}};
 const clearResult=()=>{request.current?.abort();setBusy(false);setResult(undefined);setError('');onResult(undefined)};
 const options=nodes.map(n=>({value:n.id,label:n.label}));
 return <section className={'kw-path-panel'+(expanded?' kw-path-expanded':'')} aria-label="知识路径">
 <div className="kw-path-toolbar">
  <Button size="small" loading={busy} disabled={!currentNode} title={currentNode?'查看当前知识的前置知识':'先选择一个知识节点'} onClick={()=>{if(currentNode){setSource(currentNode);setKind('prerequisites');void find(currentNode,'prerequisites')}}}>先学什么</Button>
  <Button type="text" size="small" aria-expanded={expanded} aria-controls={detailsId} title="沿已保存的关系查看知识连接、原文依据与学习路径。" onClick={()=>setExpanded(value=>!value)}>解释知识关系与学习路径</Button>
  {result&&<Button size="small" type="text" onClick={clearResult}>退出路径视图</Button>}
 </div>
 {expanded&&<div id={detailsId} className="kw-path-detail"><p>沿已保存的关系查看连接与依据；没有路径时保留未知，不补造连线。</p><Space wrap>
 <Select aria-label="路径用途" value={kind} onChange={v=>{clearResult();setKind(v)}} options={[{value:'connection',label:'两个知识为什么有关联'},{value:'prerequisites',label:'理解这个知识需要哪些前置'}]}/>
 <Select aria-label="路径起点" showSearch optionFilterProp="label" placeholder="选择知识节点" value={source} onChange={v=>{clearResult();setSource(v)}} options={options}/>
 {kind==='connection'&&<Select aria-label="路径终点" showSearch optionFilterProp="label" placeholder="选择另一节点" value={target} onChange={v=>{clearResult();setTarget(v)}} options={options.filter(n=>n.value!==source)}/>}
 <Button loading={busy} disabled={!source||kind==='connection'&&!target} onClick={()=>void find()}>查看路径</Button>
 </Space>
 {error&&<Alert type="warning" message="路径暂不可用" description={error}/>}
 {result&&<div aria-live="polite"><p>{result.message||(!result.paths.length?'当前保存关系中没有找到连接。':'下列连接来自当前空间已保存的关系。')}{result.truncated?' 已达到本次浏览上限。':''}{result.cycle_detected?' 存在循环依赖，请结合来源判断学习顺序。':''}</p>
 {result.paths.map((path,index)=><ol className="kw-path-sequence" key={index} aria-label={'知识路径 '+(index+1)}>{path.node_ids.map((id,i)=>{const n=result.nodes.find(x=>x.id===id);const edge=result.edges.find(x=>x.id===path.edge_ids[i]);return <li key={id+':'+i}>{n&&<Button type="link" onClick={()=>onNode(n)}>{n.label}</Button>}{edge&&<span>{result.nodes.find(n=>n.id===edge.source)?.label} → {edge.label} → {result.nodes.find(n=>n.id===edge.target)?.label} · {originLabels[edge.origin]||edge.origin}{edge.explanation&&<small><MathText text={edge.explanation}/></small>}</span>}</li>})}</ol>)}</div>}
 </div>}</section>;
}
