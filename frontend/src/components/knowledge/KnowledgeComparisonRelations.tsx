import {useEffect,useMemo,useState} from 'react';
import {Alert,Button,Spin} from 'antd';
import {getUnifiedEdge} from '../../api/unifiedGraph';
import {getKnowledgeNode,nodeKindLabels,originLabels} from '../../api/knowledge';
import type {KnowledgeEvidence,KnowledgeNode,NodeDetail} from '../../api/knowledge';
import {EvidenceList} from './KnowledgeSources';
import {layoutFocusGraph,routeGraphEdges,wrapNodeLabel,NODE_WIDTH,NODE_HEIGHT} from './KnowledgeGraphLayout';

/** A view over saved relationships; comparison prose never becomes a graph edge. */
export default function KnowledgeComparisonRelations({projectId,nodeIds,dimension,onNode,onEvidence}:{projectId:string;nodeIds:string[];dimension?:string;onNode:(id:string)=>void;onEvidence:(value:KnowledgeEvidence)=>void}){
 const [details,setDetails]=useState<NodeDetail[]>([]),[busy,setBusy]=useState(false),[error,setError]=useState(''),[selected,setSelected]=useState(''),[retry,setRetry]=useState(0);
 const [edgeEvidence,setEdgeEvidence]=useState<KnowledgeEvidence[]>([]),[evidenceError,setEvidenceError]=useState('');
 useEffect(()=>{const c=new AbortController();setEdgeEvidence([]);setEvidenceError('');if(selected)void getUnifiedEdge(selected,c.signal).then(r=>{if(!c.signal.aborted)setEdgeEvidence(r.evidence||[])}).catch(e=>{if(!c.signal.aborted)setEvidenceError(String(e))});return()=>c.abort()},[projectId,selected]);
 const key=[...new Set(nodeIds)].slice(0,4).join('|');
 useEffect(()=>{
  const c=new AbortController();setDetails([]);setSelected('');setError('');
  if(!key){setBusy(false);return()=>c.abort()}
  setBusy(true);
  void Promise.allSettled(key.split('|').map(id=>getKnowledgeNode(projectId,id,c.signal))).then(results=>{
   if(c.signal.aborted)return;
   setDetails(results.flatMap(r=>r.status==='fulfilled'?[r.value]:[]));
   if(results.some(r=>r.status==='rejected'))setError('部分知识关系暂时无法读取，可重试后继续核对。');
   setBusy(false);
  });return()=>c.abort();
 },[projectId,key,retry]);
 const graph=useMemo(()=>{
  const primary=details.map(d=>d.node),all=[...new Map(details.flatMap(d=>[d.node,...d.prerequisites,...d.neighbors]).map(n=>[n.id,n])).values()];
  const counts=new Map<string,number>();details.forEach(d=>new Set(d.prerequisites.map(n=>n.id)).forEach(id=>counts.set(id,(counts.get(id)||0)+1)));
  const common=all.filter(n=>(counts.get(n.id)||0)>1);
  const nodes=[...new Map([...primary,...common,...all].map(n=>[n.id,n])).values()].slice(0,10),ids=new Set(nodes.map(n=>n.id));
  const edges=[...new Map(details.flatMap(d=>d.edges).filter(e=>!e.hidden&&ids.has(e.source)&&ids.has(e.target)).map(e=>[e.id,e])).values()].slice(0,20);
  return {nodes,edges,common,total_nodes:all.length,total_edges:edges.length,truncated:all.length>10};
 },[details]);
 const layout=useMemo(()=>layoutFocusGraph(graph),[graph]),routes=useMemo(()=>routeGraphEdges(graph,layout),[graph,layout]);
 const edge=graph.edges.find(e=>e.id===selected);
 const evidence=[...new Map([...edgeEvidence,...details.flatMap(d=>d.evidence)].filter(e=>edge?.evidence_ids.includes(e.id)).map(e=>[e.id,e])).values()];
 const name=(id:string)=>graph.nodes.find(n=>n.id===id)?.label||'历史知识';
 const primaryIds=new Set(key.split('|'));
 return <section className="kw-comparison-relations" aria-label="比较关系视图">
  <div className="kw-section-heading"><div><h3>{dimension?dimension+' · 关系与依据':'方法的关系与共同前置'}</h3><p>点击表格中的“联动关系”，查看该比较项涉及的现有知识。图中每条箭头均为已保存关系。</p></div></div>
  {busy&&<div role="status"><Spin size="small"/> 正在读取关联知识…</div>}
  {error&&<Alert type="warning" message={error} action={<Button onClick={()=>setRetry(x=>x+1)}>重试</Button>}/>}
  {!key&&<p className="kw-muted">选择具体方法，或从表格的比较维度进入关系视图。尚未关联的比较结论不会自动变成事实。</p>}
  {!!graph.nodes.length&&<>
   <p className="kw-comparison-common">共同前置：{graph.common.length?graph.common.map(n=><Button type="link" key={n.id} onClick={()=>onNode(n.id)}>{n.label}</Button>):details.length<2?'选择至少两个方法或比较维度后，查看共同前置。':'当前已保存关系未指出共同前置知识。'}</p>
   <div className="kw-comparison-map"><svg viewBox={`0 0 ${layout.width} ${layout.height}`} role="group" aria-label="已有知识关系图">
    <defs><marker id="kw-compare-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10Z" fill="currentColor"/></marker></defs>
    {routes.map(r=><g key={r.edge.id} className={r.edge.id===selected?'is-selected':''} role="button" tabIndex={0} aria-label={name(r.edge.source)+' → '+r.edge.label+' → '+name(r.edge.target)} onClick={()=>setSelected(r.edge.id)} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();setSelected(r.edge.id)}}}><path className="kw-compare-edge-hit" d={r.d}/><path className="kw-compare-edge" d={r.d} markerEnd="url(#kw-compare-arrow)"/><title>{r.edge.label+'：'+r.edge.explanation}</title></g>)}
    {graph.nodes.map(n=>{const p=layout.points.get(n.id)!;return <g className={'kw-compare-node'+(primaryIds.has(n.id)?' is-focus':'')} key={n.id} transform={`translate(${p.x},${p.y})`} role="button" tabIndex={0} aria-label={'在图谱中打开：'+n.label} onClick={()=>onNode(n.id)} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();onNode(n.id)}}}><rect width={NODE_WIDTH} height={NODE_HEIGHT} rx="7"/><text x="14" y="23" className="kw-compare-node-kind">{nodeKindLabels[n.kind]||n.kind}</text><text x="14" y="49">{wrapNodeLabel(n.label).map((line,i)=><tspan key={i} x="14" dy={i?20:0}>{line}</tspan>)}</text></g>})}
   </svg></div>
   <div className="kw-comparison-edge-list">{graph.edges.map(e=><Button key={e.id} type={e.id===selected?'primary':'default'} onClick={()=>setSelected(e.id)}>{name(e.source)} → {e.label} → {name(e.target)}</Button>)}</div>
   {!graph.edges.length&&<p className="kw-muted">当前节点间尚无已保存关系；表格中的比较仍需各自核对来源。</p>}
   {edge&&<div className="kw-comparison-relation-evidence"><h4>{name(edge.source)} → {edge.label} → {name(edge.target)}</h4><p>{originLabels[edge.origin]||edge.origin} · {edge.explanation||'当前记录未附关系解释。'}</p>{evidenceError&&<p role="alert">关系原文暂不可用：{evidenceError}</p>}<EvidenceList items={evidence} onOpen={onEvidence}/>{!evidence.length&&<p className="kw-muted">此关系尚无可定位的原文依据。</p>}</div>}
   {graph.truncated&&<p className="kw-muted">当前呈现 10 个关联节点，可点击节点进入图谱继续展开。</p>}
  </>}
 </section>;
}
