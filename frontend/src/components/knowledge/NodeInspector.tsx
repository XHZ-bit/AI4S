import {useEffect,useRef,useState} from 'react';
import {Alert,Button,Input,Select,Space,Spin,Tag} from 'antd';
import {CloseOutlined,ExpandAltOutlined,ShrinkOutlined,ColumnWidthOutlined} from '@ant-design/icons';
import {getKnowledgeNode,mergeKnowledgeNodes,nodeKindLabels,originLabels,patchKnowledgeEdge,patchKnowledgeNode,researchStatusLabels,splitKnowledgeNode} from '../../api/knowledge';
import type {KnowledgeEdge,KnowledgeEvidence,KnowledgeNode,KnowledgeSource,NodeDetail} from '../../api/knowledge';
import MathText,{displayMath} from '../learning/MathText';
import EvidenceQuote from './EvidenceQuote';
import {EvidenceList} from './KnowledgeSources';
import {getUnifiedEdge} from '../../api/unifiedGraph';
import LearningProgress from './LearningProgress';
import NodeQuestion from './NodeQuestion';
import ResourceExplorer from './ResourceExplorer';
import KnowledgeReview from './KnowledgeReview';
import ImplementationCorrespondence from './ImplementationCorrespondence';
import NodeNotebook from './NodeNotebook';
import ConceptCorrespondence from './ConceptCorrespondence';
import NodeStudyGuide from './NodeStudyGuide';
import NodeMaterials from './NodeMaterials';
import NodeNoteSummary from './NodeNoteSummary';
import './node-inspector.css';
import type {GraphDetailControls} from './GraphSplitLayout';

export function NodeBadges({node}:{node:KnowledgeNode}){return <Space size={4} wrap><Tag>{nodeKindLabels[node.kind]||node.kind}</Tag><Tag>{node.metadata.knowledge_role==='teaching_supplement'||node.metadata.educational&&node.metadata.demo?'教学补充':originLabels[node.origin]||node.origin}</Tag>{node.research_status&&node.research_status!=='unknown'&&node.research_status!=='unspecified'&&<Tag>{researchStatusLabels[node.research_status]||node.research_status}</Tag>}{node.source_missing&&<Tag color="warning">来源已移除</Tag>}{node.metadata.missing_source===true&&<Tag color="warning">待补充来源</Tag>}{typeof node.metadata.reported_at==='string'&&node.metadata.reported_at&&<Tag>报告记录：{node.metadata.reported_at}</Tag>}{node.hidden&&<Tag>已隐藏</Tag>}</Space>;}
export function EdgeEditor({edge,projectId,nodes=[],onSaved,onClose,onEvidence}:{edge:KnowledgeEdge;projectId:string;nodes?:KnowledgeNode[];onSaved:()=>void;onClose:()=>void;onEvidence:(e:KnowledgeEvidence)=>void}){
 const [label,setLabel]=useState(edge.label);
 const [explanation,setExplanation]=useState(edge.explanation);
 const [busy,setBusy]=useState(false),[loading,setLoading]=useState(true),[error,setError]=useState('');
 const [evidence,setEvidence]=useState<KnowledgeEvidence[]>([]);
 const [retry,setRetry]=useState(0);
 useEffect(()=>{
  const controller=new AbortController();setEvidence([]);setLoading(true);setError('');
  void getUnifiedEdge(edge.id,controller.signal,projectId)
   .then(detail=>{if(!controller.signal.aborted)setEvidence(detail.evidence||[])})
   .catch(cause=>{if(!controller.signal.aborted)setError('关系来源暂时无法载入。'+String(cause))})
   .finally(()=>{if(!controller.signal.aborted)setLoading(false)});
  return()=>controller.abort();
 },[projectId,edge.id,retry]);
 const save=async(hidden=edge.hidden)=>{
  setBusy(true);setError('');
  try{await patchKnowledgeEdge(projectId,edge.id,{expected_version:edge.version,label,explanation,hidden});onSaved();onClose()}
  catch(cause){setError(String(cause))}
  finally{setBusy(false)}
 };
 const source=nodes.find(node=>node.id===edge.source)?.label||edge.source;
 const target=nodes.find(node=>node.id===edge.target)?.label||edge.target;
 const teaching=edge.kind==='SUPPLEMENTS'||edge.metadata?.knowledge_role==='teaching_supplement';
 const origin=teaching?'教学补充':edge.origin==='user'?'用户判断':edge.origin==='inference'?'平台建议':'原文关系';
 const missingEvidence=!loading&&edge.evidence_ids.some(id=>!evidence.some(item=>item.id===id));
 const invalid=edge.source_missing||edge.quality_review_stale||missingEvidence||evidence.some(item=>item.source_missing||item.source_changed||item.unresolved);
 const status=invalid?'依据变化，待复核':edge.hidden?'已隐藏':edge.quality_status==='human_verified'&&!loading?'用户已核对':edge.quality_status==='disputed'?'存在争议':edge.quality_status==='withdrawn'?'已撤回':'待核对';
 return <section className="kw-edge-editor" aria-label="关系详情" onKeyDown={event=>{if(event.key==='Escape'){event.stopPropagation();onClose()}}}>
  <div className="kw-section-heading"><h3>关系与依据</h3><Button type="text" aria-label="关闭关系详情" onClick={onClose}>关闭</Button></div>
  <div className="kw-edge-statement"><strong>{source}</strong><span>{edge.label}</span><strong>{target}</strong></div>
  <Space wrap><Tag>{origin}</Tag><Tag>{status}</Tag></Space>
  {edge.explanation&&<div className="kw-edge-explanation"><MathText text={edge.explanation}/></div>}
  <section className="kw-edge-evidence"><h4>原文依据</h4>
   {loading?<p role="status">读取关系依据…</p>:evidence.length?<EvidenceList items={evidence} onOpen={onEvidence}/>:<p>{teaching?'此关系是可选教学补充。':'尚无可定位的原文依据，可核对资料后修订。'}</p>}
  </section>
  {error&&<Alert type="warning" message={error} action={<Button onClick={()=>setRetry(value=>value+1)}>重试读取</Button>}/>}
  <details className="kw-edge-maintenance"><summary>修订与核查记录</summary>
   <label>关系名称<Input value={label} onChange={event=>setLabel(event.target.value)} maxLength={200}/></label>
   <label>关系说明<Input.TextArea rows={5} value={explanation} onChange={event=>setExplanation(event.target.value)}/></label>
   <Space wrap><Button type="primary" loading={busy} onClick={()=>void save()}>保存关系</Button><Button disabled={busy} onClick={()=>void save(!edge.hidden)}>{edge.hidden?'恢复关系':'隐藏关系'}</Button></Space>
   <KnowledgeReview projectId={projectId} record={edge} evidence={evidence} onSaved={onSaved}/>
  </details>
 </section>;
}

type InspectorTab='learning'|'sources'|'records';
const inspectorTabs:{id:InspectorTab;label:string}[]=[
 {id:'learning',label:'知识与学习'},
 {id:'sources',label:'原文与资料'},
 {id:'records',label:'笔记与提问'},
];
function panelExcerpt(quote:string){
 const characters=Array.from(quote.trim());
 return characters.length>440?characters.slice(0,440).join('')+'…':quote.trim();
}
export function NodeInspector({projectId,nodeId,onNode,onLearn,onEvidence,onSource,onUpdated,allNodes=[],sources=[],onClose,onCompare,onPractice,onExpand,layoutControls}:{projectId:string;nodeId:string;onNode:(node:KnowledgeNode)=>void;onLearn:(id:string,section?:'resources')=>void;onEvidence:(e:KnowledgeEvidence)=>void;onSource:(id:string)=>void;onUpdated:()=>void;allNodes?:KnowledgeNode[];sources?:KnowledgeSource[];onClose?:()=>void;onCompare?:(node:KnowledgeNode)=>void;onPractice?:(id:string,mappingId?:string)=>void;onExpand?:(id:string)=>void;layoutControls?:GraphDetailControls}){
 const [detail,setDetail]=useState<NodeDetail>(),[error,setError]=useState(''),[revision,setRevision]=useState(0);
 const [editing,setEditing]=useState(false),[label,setLabel]=useState(''),[summary,setSummary]=useState(''),[latex,setLatex]=useState(''),[status,setStatus]=useState('unspecified'),[busy,setBusy]=useState(false),[merge,setMerge]=useState<string>(),[edge,setEdge]=useState<KnowledgeEdge>();
 const [tab,setTab]=useState<InspectorTab>('learning');
 const [recordsOpened,setRecordsOpened]=useState(false),[noteDraft,setNoteDraft]=useState<{text:string;evidence?:KnowledgeEvidence[];origin:'saved_ai_answer';nonce:string}>();
 const tabRefs=useRef<(HTMLButtonElement|null)[]>([]);
 const relationOpener=useRef<HTMLElement|null>(null);
 const body=useRef<HTMLDivElement>(null);
 useEffect(()=>{setTab('learning');setMerge(undefined);setRecordsOpened(false);setNoteDraft(undefined)},[projectId,nodeId]);
 useEffect(()=>{body.current?.scrollTo?.({top:0})},[tab,nodeId]);
 useEffect(()=>{
  const c=new AbortController();setDetail(undefined);setError('');setEditing(false);setEdge(undefined);
  getKnowledgeNode(projectId,nodeId,c.signal).then(d=>{
   if(c.signal.aborted)return;
   setDetail(d);setLabel(d.node.label);setSummary(d.node.summary);setLatex(typeof d.node.metadata.latex==='string'?d.node.metadata.latex:'');setStatus(d.node.research_status||'unspecified');
  }).catch(e=>{if(!c.signal.aborted)setError(String(e))});
  return()=>c.abort();
 },[projectId,nodeId,revision]);
 const update=()=>{setRevision(v=>v+1);onUpdated()};
 const action=async(fn:()=>Promise<unknown>)=>{setBusy(true);setError('');try{await fn();setEditing(false);update()}catch(e){setError(e instanceof Error?e.message:String(e))}finally{setBusy(false)}};
 const selectTab=(next:InspectorTab)=>{setTab(next);setEdge(undefined);if(next==='records')setRecordsOpened(true)};
 if(!detail)return <aside className="kw-node-inspector kw-node-panel" aria-label="知识节点详情">
  <Button className="kw-inspector-close" type="text" aria-label="关闭节点详情" icon={<CloseOutlined/>} onClick={onClose}/>
  {error?<Alert type="error" message="节点暂时无法读取" description={error} action={<Button onClick={()=>setRevision(v=>v+1)}>重试</Button>}/>:<div className="kw-loading"><Spin/><span role="status">读取节点与依据…</span></div>}
 </aside>;
 const {node}=detail;
 const prerequisites=detail.prerequisites||[],neighbors=detail.neighbors||[],evidence=detail.evidence||[],foundations=detail.suggested_foundations||[];
 const teaching=node.metadata.knowledge_role==='teaching_supplement'||node.metadata.educational===true;
 const directEvidence=evidence.filter(item=>node.evidence_ids.includes(item.id)&&item.source_id===node.source_id&&!item.source_missing&&!item.source_changed&&!item.unresolved);
 const otherEvidence=evidence.filter(item=>!directEvidence.some(direct=>direct.id===item.id));
 const contextNodes=new Map([...allNodes,...neighbors,...prerequisites,...foundations,node].map(value=>[value.id,value]));
 const relationPriority=['PREREQUISITE_OF','USES','IMPLEMENTED_BY','SUPPORTS','CONTRADICTS','RELATED_TO','SUPPLEMENTS'];
 const roleRelations=(detail.edges||[]).filter(item=>
  (item.source===node.id||item.target===node.id)&&item.source!==item.target&&
  contextNodes.has(item.source)&&contextNodes.has(item.target)&&!item.hidden&&!item.source_missing&&!item.quality_review_stale&&
  !['withdrawn','rejected','disputed'].includes(item.quality_status||'')&&!item.metadata?.source_withdrawn&&
  item.evidence_ids.every(id=>evidence.some(quote=>quote.id===id&&!quote.source_missing&&!quote.source_changed&&!quote.unresolved))
 ).sort((a,b)=>{
  const rank=(kind:string)=>{const index=relationPriority.indexOf(kind);return index===-1?relationPriority.length:index};
  return rank(a.kind)-rank(b.kind)||a.label.localeCompare(b.label);
 });
 const normalizedLabel=(label:string)=>label.normalize('NFKC').trim().replace(/\s+/g,' ').toLocaleLowerCase();
 const sameNameCandidates=allNodes.filter(candidate=>candidate.id!==node.id&&candidate.source_id!==node.source_id&&normalizedLabel(candidate.label)===normalizedLabel(node.label)&&!candidate.hidden&&!candidate.source_missing&&!['withdrawn','rejected'].includes(candidate.quality_status||'')).slice(0,3);
 const sourceTitle=(id:string)=>sources.find(source=>source.id===id)?.title||evidence.find(item=>item.source_id===id)?.source_title||id;
 const canRead=directEvidence.length>0||!!node.source_id&&!node.source_missing&&node.metadata.missing_source!==true&&!teaching;
 const readSource=()=>{if(directEvidence[0])onEvidence(directEvidence[0]);else if(canRead)onSource(node.source_id)};
 const openNode=(id:string)=>{const found=allNodes.find(n=>n.id===id)||neighbors.find(n=>n.id===id)||prerequisites.find(n=>n.id===id);if(found)onNode(found)};
 const tabId=(id:InspectorTab)=>'kw-node-tab-'+id;
 const closeRelation=()=>{setEdge(undefined);if(relationOpener.current?.isConnected)relationOpener.current.focus()};
 const relationItem=(relationship:KnowledgeEdge)=>{
  const from=contextNodes.get(relationship.source)!,to=contextNodes.get(relationship.target)!;
  const relationOrigin=relationship.kind==='SUPPLEMENTS'?'教学补充':relationship.origin==='user'?'用户判断':relationship.origin==='inference'?'平台建议':'原文关系';
  const endpoint=(value:KnowledgeNode)=>value.id===node.id?<strong>{value.label}</strong>:<button type="button" onClick={()=>onNode(value)}>{value.label}</button>;
  return <li key={relationship.id}><div className="kw-node-role-statement">{endpoint(from)}<span className="kw-node-role-predicate"><span aria-hidden>→ </span>{relationship.label}<span aria-hidden> →</span></span>{endpoint(to)}</div>
   {relationship.explanation&&<div className="kw-node-role-explanation"><MathText text={relationship.explanation}/></div>}
   <div className="kw-node-role-actions"><small>{relationOrigin}</small><Button size="small" type="text" aria-label={'查看关系：'+from.label+' '+relationship.label+' '+to.label} onClick={event=>{relationOpener.current=event.currentTarget;setEdge(relationship)}}>查看关系依据</Button></div>
  </li>;
 };
 return <aside className="kw-node-inspector kw-node-panel" aria-label="知识节点详情">
  <header className="kw-node-panel-header">
   <Button className="kw-inspector-close" type="text" aria-label="关闭节点详情" icon={<CloseOutlined/>} onClick={onClose}/>
   <NodeBadges node={node}/>
   <h2>{node.label}</h2>
   <div className="kw-node-panel-utilities">
    {onExpand&&<Button size="small" type="text" onClick={()=>onExpand(node.id)}>查看关联</Button>}
    <Button size="small" type="text" onClick={()=>setEditing(v=>!v)}>{editing?'结束编辑':'编辑节点'}</Button>
    {layoutControls&&<span className="kw-node-width-controls"><Button size="small" type="text" icon={layoutControls.expanded?<ShrinkOutlined/>:<ExpandAltOutlined/>} aria-expanded={layoutControls.expanded} disabled={!layoutControls.canSplit} title={!layoutControls.canSplit?'放宽窗口后可恢复分栏':undefined} onClick={layoutControls.onToggleExpanded}>{layoutControls.expanded?'还原分栏':'展开节点详情'}</Button><Button size="small" type="text" aria-label="恢复默认宽度" title="恢复默认宽度" icon={<ColumnWidthOutlined/>} onClick={layoutControls.onResetWidth}/></span>}
   </div>
  </header>
  {!editing&&<div className="kw-node-tabs" role="tablist" aria-label="节点详情内容">
   {inspectorTabs.map((item,index)=><button key={item.id} ref={el=>{tabRefs.current[index]=el}} id={tabId(item.id)} type="button" role="tab" aria-selected={tab===item.id} aria-controls={'kw-node-panel-'+item.id} tabIndex={tab===item.id?0:-1} onClick={()=>selectTab(item.id)} onKeyDown={event=>{
    let next=index;
    if(event.key==='ArrowRight')next=(index+1)%inspectorTabs.length;
    else if(event.key==='ArrowLeft')next=(index+inspectorTabs.length-1)%inspectorTabs.length;
    else if(event.key==='Home')next=0;
    else if(event.key==='End')next=inspectorTabs.length-1;
    else return;
    event.preventDefault();selectTab(inspectorTabs[next].id);tabRefs.current[next]?.focus();
   }}>{item.label}</button>)}
  </div>}
  <div className="kw-node-panel-body" ref={body}>
   {error&&<Alert type="error" message={error}/>}
   {editing?<div className="kw-edit-form">
    <label>节点名称<Input aria-label="节点名称" value={label} onChange={e=>setLabel(e.target.value)}/></label>
    <label>节点解释<Input.TextArea aria-label="节点解释" rows={7} value={summary} onChange={e=>setSummary(e.target.value)}/></label>
    {node.kind==='formula'&&<label>公式 LaTeX<Input.TextArea aria-label="公式 LaTeX" rows={4} value={latex} onChange={e=>setLatex(e.target.value)} maxLength={10000}/><small>对照原文修改公式，修订保存在本空间。</small>{latex&&<MathText text={displayMath(latex)} showSourceOnError/>}</label>}
    <label>研究状态<Select aria-label="研究状态" value={status} onChange={setStatus} options={Object.entries(researchStatusLabels).map(([value,label])=>({value,label}))}/></label>
    <Space wrap><Button type="primary" loading={busy} onClick={()=>void action(()=>patchKnowledgeNode(projectId,node.id,{expected_version:node.version,label,summary,research_status:status,...(node.kind==='formula'?{latex}:{})}))}>保存修订</Button><Button disabled={busy} onClick={()=>setEditing(false)}>取消</Button></Space>
   </div>:<>
    <section role="tabpanel" id="kw-node-panel-learning" aria-labelledby={tabId('learning')} hidden={tab!=='learning'}>
     <NodeNoteSummary projectId={projectId} nodeId={node.id} onEdit={()=>selectTab('records')}/>
     <NodeStudyGuide guide={detail.study_guide} compact/>
     <section className="kw-node-overview"><h3>{detail.study_guide?(node.origin==='source'&&!teaching?'资料中的描述':'节点说明'):'知识说明'}</h3>
      {node.summary?.trim()?<div className="kw-node-summary"><MathText text={node.summary}/></div>:<p className="kw-node-panel-muted">当前节点还没有独立说明。可先查看原文，或进入深入学习查看基础内容。</p>}
      {typeof node.metadata.latex==='string'&&!!node.metadata.latex&&<MathText text={displayMath(node.metadata.latex)} showSourceOnError/>}
     </section>
     {directEvidence[0]&&<section className="kw-node-source-excerpt" aria-label="当前知识的原文片段"><h3>原文怎么说</h3><blockquote><EvidenceQuote evidence={{...directEvidence[0],quote:panelExcerpt(directEvidence[0].quote)}}/></blockquote><small>{directEvidence[0].source_title}{directEvidence[0].locator.page?' · 第 '+directEvidence[0].locator.page+' 页':directEvidence[0].locator.heading?' · '+directEvidence[0].locator.heading:''}</small></section>}
     {canRead&&<div className="kw-node-primary-evidence"><Button onClick={readSource}>查看原文依据</Button></div>}
     {!!roleRelations.length&&<section className="kw-node-graph-role" aria-label="在知识图谱中的作用"><div className="kw-node-section-label"><h3>在知识图谱中的作用</h3><span>{roleRelations.length} 条关系</span></div><ul className="kw-node-role-list">{roleRelations.slice(0,3).map(relationItem)}</ul>{roleRelations.length>3&&<details><summary>其余 {roleRelations.length-3} 条关系</summary><ul className="kw-node-role-list">{roleRelations.slice(3).map(relationItem)}</ul></details>}{edge&&tab==='learning'&&<EdgeEditor key={edge.id} projectId={projectId} edge={edge} nodes={[...contextNodes.values()]} onClose={closeRelation} onSaved={update} onEvidence={onEvidence}/>}</section>}
     {!!prerequisites.length&&<section className="kw-node-foundations"><div className="kw-node-section-label"><h3>先补充基础</h3><span>{prerequisites.length} 个前置知识</span></div><ul className="kw-node-links">{prerequisites.map(n=><li key={n.id}><div><button type="button" onClick={()=>onNode(n)}>{n.label}</button>{n.summary?.trim()&&<p>{n.summary.slice(0,140)}</p>}</div><small>{nodeKindLabels[n.kind]||n.kind}</small></li>)}</ul></section>}
     {!!foundations.length&&<section className="kw-node-foundations" aria-label="可选基础补充"><div className="kw-node-section-label"><h3>可选基础补充</h3><span>教学参考</span></div><ul className="kw-node-links">{foundations.slice(0,2).map(n=><li key={n.id}><div><button type="button" onClick={()=>onNode(n)}>{n.label}</button>{n.summary?.trim()&&<p>{n.summary.slice(0,140)}</p>}</div></li>)}</ul>{foundations.length>2&&<details><summary>其余 {foundations.length-2} 项基础</summary><ul className="kw-node-links">{foundations.slice(2).map(n=><li key={n.id}><button type="button" onClick={()=>onNode(n)}>{n.label}</button></li>)}</ul></details>}</section>}
     {!!sameNameCandidates.length&&<section className="kw-same-name-candidates"><h3>跨资料同名候选</h3><p className="kw-node-panel-muted">标签相同，含义与适用条件待核对。</p><p className="kw-same-name-current">当前出处 · {sourceTitle(node.source_id)}</p><ul>{sameNameCandidates.map(candidate=><li key={candidate.id}><strong>{candidate.label}</strong><small>候选出处 · {sourceTitle(candidate.source_id)}</small><span>待核对</span><Button size="small" onClick={()=>onNode(candidate)}>查看候选节点</Button></li>)}</ul>{onCompare&&<Button onClick={()=>onCompare(node)}>比较相关资料</Button>}</section>}
     {['concept','formula','method','module','algorithm','hypothesis'].includes(node.kind)&&!teaching&&<ConceptCorrespondence key={node.id} projectId={projectId} nodeId={node.id} onEvidence={onEvidence} onNode={onNode} onSaved={onUpdated} onCompare={onCompare?()=>onCompare(node):undefined}/>}
     {!!neighbors.length&&<details className="kw-neighbor-details"><summary>相关知识 · {neighbors.length} 个</summary><ul className="kw-node-links">{neighbors.map(n=><li key={n.id}><button type="button" onClick={()=>onNode(n)}>{n.label}</button><small>{nodeKindLabels[n.kind]||n.kind}</small></li>)}</ul></details>}
     <div className="kw-node-next-links"><Button onClick={()=>onLearn(node.id,'resources')}>学习资源</Button>{onCompare&&<Button onClick={()=>onCompare(node)}>方法比较</Button>}</div>
    </section>
    <section role="tabpanel" id="kw-node-panel-sources" aria-labelledby={tabId('sources')} hidden={tab!=='sources'}>
     <>
      <NodeMaterials projectId={projectId} nodeId={node.id} sources={sources} enabled={tab==='sources'} onRead={onSource} onUpdated={onUpdated}/>
      <section className="kw-node-evidence"><h3>原文依据{directEvidence.length?' · '+directEvidence.length+' 处':''}</h3>
       {directEvidence.length?<EvidenceList items={directEvidence} onOpen={onEvidence}/>:<p className="kw-node-panel-muted">{teaching?'此节点是基础教学参考；学习资源见下方。':'当前知识的原文依据尚未就绪，可先阅读来源。'}</p>}
       {!!otherEvidence.length&&<details className="kw-node-associated-evidence"><summary>关联与历史片段 · {otherEvidence.length}</summary><EvidenceList items={otherEvidence} onOpen={onEvidence}/></details>}
       <Button disabled={!canRead} onClick={readSource}>阅读原文</Button>
      <KnowledgeReview projectId={projectId} record={node} evidence={evidence} onSaved={update}/>
      </section>
      <ImplementationCorrespondence key={node.id} projectId={projectId} nodeId={node.id} onEvidence={onEvidence} onPractice={onPractice}/>
      <ResourceExplorer projectId={projectId} nodeId={node.id} initialItems={detail.resources||[]} onEvidence={onEvidence}/>
      {!!detail.edges?.length&&<details className="kw-relations"><summary>关系说明与修订 · {detail.edges.length} 条</summary>{detail.edges.map(e=><button type="button" key={e.id} onClick={()=>setEdge(e)}><span>{e.label}</span><small>{e.explanation||originLabels[e.origin]}</small></button>)}</details>}
      {edge&&tab==='sources'&&<EdgeEditor key={edge.id} projectId={projectId} edge={edge} nodes={[...contextNodes.values()]} onClose={closeRelation} onSaved={update} onEvidence={onEvidence}/>}
     </>
    </section>
    <section role="tabpanel" id="kw-node-panel-records" aria-labelledby={tabId('records')} hidden={tab!=='records'}>
     <>
      {recordsOpened&&<NodeNotebook projectId={projectId} node={node} initialDraft={noteDraft} onEvidence={onEvidence}/>}
      <details><summary>围绕节点提问</summary><NodeQuestion key={node.id} projectId={projectId} nodeId={node.id} onEvidence={onEvidence} onNode={openNode} onSaveAnswer={(text,evidence)=>setNoteDraft({text,evidence,origin:'saved_ai_answer',nonce:String(Date.now())})}/></details>
      <section className="kw-node-learning-record"><h3>学习状态与小结</h3><LearningProgress key={node.id} projectId={projectId} nodeId={node.id} onUpdated={onUpdated} onNode={openNode}/></section>
     </>
    </section>
    <details className="kw-node-maintenance"><summary>节点整理</summary><p>合并仅影响当前空间，原始来源和成员保留。</p><Select aria-label="选择要合并的节点" value={merge} onChange={setMerge} placeholder="选择另一个节点" showSearch optionFilterProp="label" options={allNodes.filter(n=>n.id!==node.id&&n.kind===node.kind).map(n=>({value:n.id,label:n.label}))}/><Space wrap><Button disabled={!merge||busy} onClick={()=>void action(async()=>{const merged=await mergeKnowledgeNodes(projectId,[node.id,merge!],node.label);if(merged?.id)onNode(merged)})}>合并节点</Button><Button disabled={busy} onClick={()=>void action(()=>splitKnowledgeNode(projectId,node.id))}>拆分已合并成员</Button><Button disabled={busy} onClick={()=>void action(()=>patchKnowledgeNode(projectId,node.id,{expected_version:node.version,hidden:!node.hidden}))}>{node.hidden?'恢复显示':'隐藏节点'}</Button></Space></details>
   </>}
  </div>
  {!editing&&<footer className="kw-node-panel-footer"><Button type="primary" onClick={()=>onLearn(node.id)}>深入学习</Button>{onPractice&&<Button onClick={()=>onPractice(node.id)}>动态练习</Button>}</footer>}
 </aside>;
}
