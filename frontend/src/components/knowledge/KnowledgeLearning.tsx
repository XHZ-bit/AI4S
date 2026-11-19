import {useEffect,useRef,useState} from 'react';
import {Alert,Button,Input,Space,Spin,Tag} from 'antd';
import {generateNodeLearning,getKnowledgeNode,getNodeLearning,patchNodeLearning} from '../../api/knowledge';
import type {KnowledgeEvidence,LearningArtifact,LearningResource,LearningSection,LearningOptions,NodeDetail,WorkspaceMode} from '../../api/knowledge';
import {damagedMathText,displayMath} from '../learning/MathText';
import KnowledgeText,{incompleteFormulaText,mathAwareText} from './KnowledgeText';
import KnowledgeDemos,{DEMO_KEYS} from './KnowledgeDemos';
import {NodeBadges} from './KnowledgeGraph';
import SourceFormulas from './SourceFormulas';
import LearningPath from './LearningPath';
import NodeQuestion from './NodeQuestion';
import ResourceExplorer from './ResourceExplorer';
import NodeNotebook from './NodeNotebook';
import ImplementationCorrespondence from './ImplementationCorrespondence';
import LearningCheck from './LearningCheck';
import FormulaContext from './FormulaContext';
import ConceptCorrespondence from './ConceptCorrespondence';
import NodeStudyGuide from './NodeStudyGuide';
import {useCurrentAccount} from '../SessionContext';
import './knowledge-learning.css';
import LearningWorkspace,{type LearningToolTab} from './LearningWorkspace';
import LearningEvidence from './LearningEvidence';
import './reading-comfort.css';

const sectionLabels:Record<LearningSection,string>={overview:'直观理解',definition:'原文与定义',derivation:'公式与推导',prerequisites:'需要的前置知识',implementation:'实现与代码',limitations:'适用边界与未知项'};
const sectionKeys=Object.keys(sectionLabels) as LearningSection[];
function safeUrl(url?:string){return url&&/^https?:\/\//i.test(url)?url:undefined;}
const emptyCopy=new Set([
 '当前尚无已保存内容。可准备深入讲解，或查看原文依据。',
 '当前未识别到明确的前置节点；可以从相邻知识继续探索。',
 '基础内容来自当前资料。深入讲解属于教学补充，需结合原文的条件和范围理解。',
]);
function contentText(value?:string,userEdited=false){
 const text=value?.trim()||'';
 if(userEdited)return text;
 if(emptyCopy.has(text))return '';
 return text.split(/\n\s*\n/).map(paragraph=>{
  if(!damagedMathText(paragraph))return paragraph;
  const outsideMath=paragraph.replace(/(\$\$[\s\S]*?\$\$|(?<!\\)\$(?!\$)[^$\n]+?(?<!\\)\$|\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\))/g,part=>damagedMathText(part)?'':part);
  // Preserve recoverable prose beside broken OCR, without retaining isolated equation fragments.
  return outsideMath.split('\n').filter(line=>!line.includes('\uFFFD')&&/[\u3400-\u9fff]{4}|(?:[A-Za-z]{2,}[ ,.;:]+){3}/.test(line)).join('\n').trim();
 }).filter(Boolean).join('\n\n');
}
function usableResource(item:LearningResource){return !!(safeUrl(item.url)||item.content?.trim()||(item.title||item.name)?.trim()&&(item.reason||item.description)?.trim());}
export function LearningResources({items}:{items:LearningResource[]}){
 const resources=items.filter(usableResource);
 if(!resources.length)return null;
 return <section id="kw-learning-resources" className="kw-learning-resources"><h3>学习资料与代码来源</h3><ul>{resources.map((r,i)=><li key={r.url||i}><strong>{safeUrl(r.url)?<a href={safeUrl(r.url)} target="_blank" rel="noreferrer">{r.title||r.name||r.url}</a>:r.title||r.name||'资料'}</strong>{(r.reason||r.description)&&<span>{r.reason||r.description}</span>}<small>{r.fetched?'已获取的来源内容':'资源入口，未作为全文依据'}</small></li>)}</ul></section>;
}
export default function KnowledgeLearning({projectId,nodeId,onNode,onEvidence,onBack,onPractice,focusResources=false,initialGoal='',workspaceMode='research',autoPrepare=false,compactControls=false}:{projectId:string;nodeId?:string;focusResources?:boolean;initialGoal?:string;workspaceMode?:WorkspaceMode;autoPrepare?:boolean;compactControls?:boolean;onNode:(id:string)=>void;onEvidence:(e:KnowledgeEvidence)=>void;onBack:()=>void;onPractice?:(id:string,mappingId?:string)=>void}){
 const account=useCurrentAccount(),automaticAttempts=useRef(new Set<string>());
 const [detail,setDetail]=useState<NodeDetail>(),[artifact,setArtifact]=useState<LearningArtifact>(),[error,setError]=useState(''),[busy,setBusy]=useState(false),[retry,setRetry]=useState(0);const generation=useRef(0),request=useRef<AbortController>(),inFlight=useRef(false);
 const defaults=useRef({goal:initialGoal,depth:workspaceMode==='explore'?'standard' as const:'deep' as const});
 defaults.current={goal:initialGoal,depth:workspaceMode==='explore'?'standard':'deep'};
 const [goal,setGoal]=useState(initialGoal),[depth,setDepth]=useState<'standard'|'deep'>(defaults.current.depth);
 const [controlsOpen,setControlsOpen]=useState(!compactControls);
 useEffect(()=>setControlsOpen(!compactControls),[compactControls,projectId,nodeId,account?.id]);
 const [tool,setTool]=useState<LearningToolTab>('question'),[notesOpen,setNotesOpen]=useState(false),[noteDraft,setNoteDraft]=useState<{text:string;origin:'saved_ai_answer';nonce:string;evidence?:KnowledgeEvidence[]}>();
 useEffect(()=>{setTool('question');setNotesOpen(false);setNoteDraft(undefined)},[projectId,nodeId,account?.id]);
 const chooseTool=(next:LearningToolTab)=>{setTool(next);if(next==='notes')setNotesOpen(true)};
 const accept=(value:LearningArtifact)=>{
  setArtifact(value);
  const saved=value.status==='ready'||!!value.user_edited_sections?.length||!!value.goal;
  setGoal(saved?value.goal||'':defaults.current.goal);
  setDepth(saved?value.depth||'deep':defaults.current.depth);
 };
 const [editing,setEditing]=useState<LearningSection>(),[draft,setDraft]=useState(''),[saving,setSaving]=useState(false),[saveMessage,setSaveMessage]=useState('');
 useEffect(()=>{const c=new AbortController();const token=++generation.current;setDetail(undefined);setArtifact(undefined);setGoal(defaults.current.goal);setDepth(defaults.current.depth);setError('');setBusy(false);setSaving(false);setEditing(undefined);setSaveMessage('');inFlight.current=false;request.current?.abort();if(nodeId)void Promise.all([getKnowledgeNode(projectId,nodeId,c.signal),getNodeLearning(projectId,nodeId,c.signal)]).then(([d,a])=>{if(!c.signal.aborted&&token===generation.current){setDetail(d);accept(a)}}).catch(e=>{if(!c.signal.aborted&&token===generation.current)setError(String(e))});return()=>{c.abort();request.current?.abort();generation.current++}},[projectId,nodeId,retry,account?.id]);
 const generate=async(refresh=false)=>{if(!nodeId||busy||saving||editing||inFlight.current)return;inFlight.current=true;const token=generation.current;const c=new AbortController();request.current=c;setBusy(true);setError('');setSaveMessage('');try{const result=await generateNodeLearning(projectId,nodeId,refresh&&goal.trim()===(artifact?.goal||'')&&depth===(artifact?.depth||'deep'),c.signal,{goal:goal.trim(),depth});if(token===generation.current)accept(result)}catch(e){if(!c.signal.aborted&&token===generation.current)setError(e instanceof Error?e.message:String(e))}finally{if(token===generation.current){inFlight.current=false;setBusy(false)}}};
 useEffect(()=>{
  if(!autoPrepare||!detail||!artifact||busy||saving||editing||artifact.status!=='basic'||artifact.stale||artifact.errors?.length||artifact.user_edited_sections?.length||artifact.hidden_sections?.length||detail.node.metadata.educational||detail.node.metadata.knowledge_role==='teaching_supplement')return;
  const key=JSON.stringify([account?.id||'local',projectId,nodeId,detail.node.version]);
  if(automaticAttempts.current.has(key))return;
  automaticAttempts.current.add(key);void generate();
 },[autoPrepare,detail,artifact,busy,saving,editing,account?.id,projectId,nodeId]);
 const [elapsed,setElapsed]=useState(0),[waitStopped,setWaitStopped]=useState(false);
 useEffect(()=>{setWaitStopped(false)},[projectId,nodeId,retry,account?.id]);
 useEffect(()=>{setElapsed(0);if(!busy)return;const start=Date.now(),timer=window.setInterval(()=>setElapsed(Math.floor((Date.now()-start)/1000)),1000);return()=>window.clearInterval(timer)},[busy]);
 const stopWaiting=()=>{request.current?.abort();generation.current++;inFlight.current=false;setBusy(false);setError('');setWaitStopped(true);setSaveMessage('已停止等待，可以继续阅读；稍后可重新读取已保存的讲解。')};
 const revise=async(body:{sections?:Partial<Record<LearningSection,string>>;hidden_sections?:LearningSection[]})=>{if(!nodeId||!artifact||busy||saving||inFlight.current)return;inFlight.current=true;const token=generation.current,c=new AbortController();request.current=c;setSaving(true);setError('');setSaveMessage('');try{const result=await patchNodeLearning(projectId,nodeId,{expected_revision:artifact.revision||1,...(artifact.goal!==undefined?{goal:artifact.goal,depth:artifact.depth||'deep'}:{}),...body},c.signal);if(token===generation.current){setArtifact(result);setEditing(undefined);setSaveMessage('学习内容已保存为用户补充。')}}catch(e){if(!c.signal.aborted&&token===generation.current)setError(e instanceof Error?e.message:String(e))}finally{if(token===generation.current){inFlight.current=false;setSaving(false)}}};
 const loadVariant=async(options:LearningOptions)=>{if(!nodeId||busy||saving||editing||inFlight.current)return;inFlight.current=true;const token=generation.current,c=new AbortController();request.current=c;setBusy(true);setError('');setSaveMessage('');try{const result=await getNodeLearning(projectId,nodeId,c.signal,options);if(token===generation.current)accept(result)}catch(e){if(!c.signal.aborted&&token===generation.current)setError(String(e))}finally{if(token===generation.current){inFlight.current=false;setBusy(false)}}};
 if(!nodeId)return <section className="kw-empty"><h2>从一个知识节点开始</h2><p>在研究图谱或方法比较中选择概念、公式或算法，再进入深入学习。</p><Button onClick={onBack}>返回研究图谱</Button></section>;
 if(!detail)return error?<Alert type="error" message="学习内容暂时无法加载" description={error} action={<Button onClick={()=>setRetry(v=>v+1)}>重试</Button>}/>:<div className="kw-loading"><Spin/><span role="status">读取节点与已保存内容…</span></div>;
 const sections=artifact?.sections,prerequisites=detail.prerequisites||[];
 const latex=typeof detail.node.metadata.latex==='string'?detail.node.metadata.latex.trim():'';
 const evidence=artifact?.evidence?.length?artifact.evidence:detail.evidence||[];
 const directEvidence=evidence.filter(e=>e.source_id===detail.node.source_id),associatedEvidence=evidence.filter(e=>e.source_id!==detail.node.source_id);
 const formulaEvidence=[...evidence,...(detail.evidence||[])];
 const formulaSources=(artifact?.formula_sources?.length?artifact.formula_sources:detail.formula_sources||[]).filter(item=>item.latex?.trim()||item.image_url?.startsWith('/api/')||formulaEvidence.some(e=>e.id===item.evidence_id));
 const textFor=(key:LearningSection)=>{
  const edited=artifact?.user_edited_sections?.includes(key);
  const text=contentText(sections?.[key],edited);
  if(!edited&&['paper','report','results','code'].includes(detail.node.kind)&&(text===detail.node.label||/^(已保存的论文|已导入的论文|已保存论文)[。.]?$/.test(text)))return '';
  if(key==='definition'&&!edited&&incompleteFormulaText(text))return '公式文本识别不完整，请查看下方原文依据中的公式。';
  if(text||edited)return text;
  return key==='overview'?contentText(detail.node.summary):key==='derivation'&&latex&&!formulaSources.length?displayMath(latex):'';
 };
 const visibleKeys=sectionKeys.filter(key=>editing===key||(!artifact?.hidden_sections?.includes(key)&&!!(textFor(key)||(key==='prerequisites'&&prerequisites.length)||(key==='definition'&&formulaSources.length))));
 const managedKeys=sectionKeys.filter(key=>!visibleKeys.includes(key));
 const guide=detail.study_guide;
 const isReadingGuide=guide?.kind==='reading_outline';
 const needsRetry=!!(error||artifact?.errors?.length||artifact?.last_generation&&artifact.last_generation.code!=='completed');
 const generationMessage=artifact?.last_generation?.message||(artifact?.errors?.some(item=>item.includes('一致性检查'))?'详细讲解未通过原文核对，基础内容仍可阅读。':'本次详细讲解未完成，已有内容仍可阅读。');
 const generationReasons=[...(artifact?.errors||[]),...(artifact?.last_generation?.issues||[]).map(item=>typeof item==='string'?item:item&&typeof item.description==='string'?((sectionLabels[item.section as LearningSection]||'核对意见')+'：'+item.description):'')].filter((item,index,all)=>typeof item==='string'&&item.trim()&&all.indexOf(item)===index);
 const recallOnly=artifact?.status==='ready'||!!artifact?.user_edited_sections?.length||!!detail.node.metadata.educational||detail.node.metadata.knowledge_role==='teaching_supplement';
 const displaySectionLabel=(key:LearningSection)=>guide&&!recallOnly&&key==='overview'?(detail.node.origin==='source'?'资料中的描述':'节点说明'):sectionLabels[key];
 const demos=DEMO_KEYS([...(guide?.demo_ids||[]),...(detail.demos||[]),...(artifact?.demos||[])]);
 const resources=(artifact?.resources?.length?artifact.resources:detail.resources||[]).filter(usableResource);
 const beginEdit=(key:LearningSection)=>{setEditing(key);setDraft(sections?.[key]||(key==='overview'?detail.node.summary:''));setWaitStopped(false);setSaveMessage('')};
 return <article className="kw-learning-view kw-learning-studio">
 <header className="kw-learning-studio-header">
  <div className="kw-learning-studio-identity"><Button type="text" onClick={onBack}>返回原位置</Button><h2 title={detail.node.label}>{detail.node.label}</h2><div className="kw-learning-studio-meta"><NodeBadges node={detail.node}/>{artifact?.status!=='ready'&&<span className="kw-learning-studio-kind">{isReadingGuide?'论文导读':guide?'基础讲解':detail.node.metadata.educational?'教学补充':'原文基础内容'}</span>}</div></div>
  <details className="kw-learning-customize" open={controlsOpen} onToggle={event=>setControlsOpen(event.currentTarget.open)}>
   <summary title={goal||'围绕当前节点理解'}><span>调整学习目标与深度</span><small>{depth==='standard'?'重点理解':'研究级详解'}</small></summary>
   <div className="kw-learning-request"><label>这次想学懂什么<Input.TextArea aria-label="深入学习目标" value={goal} onChange={e=>setGoal(e.target.value)} maxLength={1500} autoSize={{minRows:2,maxRows:5}} disabled={busy||saving||!!editing} placeholder="例如：解释变量和维度，逐步推导，再用数值例子说明边界"/></label><label>讲解深度<select aria-label="讲解深度" value={depth} onChange={e=>setDepth(e.target.value as 'standard'|'deep')} disabled={busy||saving||!!editing}><option value="deep">研究级详解</option><option value="standard">重点理解</option></select></label></div>
  </details>
  <Button className="kw-personal-learning-action" aria-label="生成个性化讲解" type="primary" loading={busy} disabled={busy||saving||!!editing} onClick={()=>{setWaitStopped(false);void generate(artifact?.status==='ready')}}>{needsRetry?'重试个性化讲解':artifact?.status==='ready'?'更新个性化讲解':'生成个性化讲解'}</Button>
 </header>
 {busy&&<div role="status" className="kw-generation-status kw-learning-preparing"><Spin size="small"/><div><strong>正在准备详细讲解{elapsed>0?' · '+elapsed+'秒':''}</strong><span>{elapsed>=45?'仍在核对讲解与原文，基础内容可先阅读。':'基础讲解和原文可先阅读，无需等待页面完成。'}</span></div><Button size="small" type="text" onClick={stopWaiting}>停止等待</Button></div>}
 {saveMessage&&<div role="status" className="kw-learning-read-status"><span>{saveMessage}</span>{waitStopped&&<Button size="small" onClick={()=>{setWaitStopped(false);setRetry(v=>v+1)}}>重新读取已保存版本</Button>}</div>}
 {error&&<Alert type="error" message="讲解未更新" description={error} action={<Space><Button disabled={busy||saving||!!editing} onClick={()=>void generate(true)}>重试个性化讲解</Button><Button disabled={busy||saving} onClick={()=>setRetry(v=>v+1)}>重新读取已保存版本</Button></Space>}/>}
 {artifact?.stale&&<Alert type="warning" message="依据或节点已更新，当前保存的讲解需要重新检查" action={<Button disabled={busy||saving||!!editing} onClick={()=>void generate(true)}>更新讲解</Button>}/>}
 {!busy&&!error&&needsRetry&&<section className="kw-learning-retry-feedback" role="status" aria-label="详细讲解准备结果"><div><strong>{generationMessage}</strong><details><summary>查看原因</summary><ul>{generationReasons.map((item,index)=><li key={index}>{item}</li>)}</ul></details></div><Button disabled={saving||!!editing} onClick={()=>void generate(true)}>重试个性化讲解</Button></section>}
 <LearningWorkspace projectId={projectId} nodeId={nodeId} focusResources={focusResources} tool={tool} onTool={chooseTool} onNode={onNode}
  chapters={[...(guide?[{id:'kw-learning-primer',label:recallOnly?'基础回顾':isReadingGuide?'论文导读':'基础讲解'}]:[]),...visibleKeys.map(key=>({id:'kw-learning-'+key,label:displaySectionLabel(key)}))]}
  lesson={<>
   {guide&&<section id="kw-learning-primer" tabIndex={-1}>{recallOnly?<details className="kw-learning-primer-recall"><summary>{isReadingGuide?'回顾论文导读':'回顾基础讲解'}</summary><NodeStudyGuide guide={guide}/></details>:<NodeStudyGuide guide={guide}/>}</section>}
 {visibleKeys.map(key=>{const label=displaySectionLabel(key),edited=artifact?.user_edited_sections?.includes(key),text=textFor(key);return <section tabIndex={-1} key={key} id={'kw-learning-'+key}><div className="kw-lesson-section-heading"><h3>{label}</h3>{edited&&<Tag>用户补充</Tag>}<Space size="small"><Button size="small" type="text" aria-label={'修订讲解：'+label} disabled={busy||saving||!!editing} onClick={()=>beginEdit(key)}>修订讲解</Button><Button size="small" type="text" disabled={busy||saving||!!editing} aria-label={'隐藏讲解：'+label} onClick={()=>void revise({hidden_sections:[...(artifact?.hidden_sections||[]),key]})}>隐藏此节</Button></Space></div>{editing===key?<div className="kw-lesson-editor"><label htmlFor={'kw-edit-lesson-'+key}>{label}内容</label><Input.TextArea id={'kw-edit-lesson-'+key} value={draft} onChange={e=>setDraft(e.target.value)} autoSize={{minRows:8,maxRows:24}} maxLength={25000} disabled={saving}/><p>支持 LaTeX 与代码块。保存后标为用户补充，重新生成保留人工修订与隐藏选择。</p><Space><Button type="primary" loading={saving} onClick={()=>void revise({sections:{[key]:draft}})}>保存讲解修订</Button><Button disabled={saving} onClick={()=>setEditing(undefined)}>取消修订</Button></Space></div>:<>{text&&<KnowledgeText text={mathAwareText(text,detail.node.metadata.latex)}/>} {key==='definition'&&!!formulaSources.length&&<SourceFormulas items={formulaSources} evidence={formulaEvidence} onEvidence={onEvidence}/>} {key==='prerequisites'&&!!prerequisites.length&&<div className="kw-prerequisite-map" aria-label="前置知识依赖图"><div className="kw-prerequisite-nodes">{prerequisites.map(n=><button key={n.id} onClick={()=>onNode(n.id)}><small>前置知识</small><strong>{n.label}</strong>{n.summary&&<span>{n.summary.slice(0,100)}</span>}</button>)}</div><div className="kw-prerequisite-target"><span>理解这些知识有助于学习</span><strong>{detail.node.label}</strong></div></div>}</>}</section>})}
 {(detail.node.kind==='formula'||!!detail.node.metadata.symbols)&&<FormulaContext metadata={detail.node.metadata} evidence={directEvidence} onEvidence={onEvidence} showEmpty={detail.node.kind==='formula'}/>}
 {!!managedKeys.length&&<details className="kw-learning-management"><summary>管理学习内容</summary><div>{managedKeys.map(key=><div key={key}><span>{sectionLabels[key]}</span>{artifact?.hidden_sections?.includes(key)?<Button size="small" type="text" disabled={busy||saving||!!editing} aria-label={'恢复讲解：'+sectionLabels[key]} onClick={()=>void revise({hidden_sections:(artifact.hidden_sections||[]).filter(k=>k!==key)})}>恢复此节</Button>:<Button size="small" type="text" disabled={busy||saving||!!editing} aria-label={'修订讲解：'+sectionLabels[key]} onClick={()=>beginEdit(key)}>补充内容</Button>}</div>)}</div></details>}
 {!!artifact?.variants&&artifact.variants.length>1&&<details className="kw-learning-history"><summary>已保存讲解 · {artifact.variants.length} 个问题与深度组合</summary><div>{artifact.variants.map(v=><button key={v.id} disabled={busy||saving||!!editing} title={v.goal} onClick={()=>void loadVariant({goal:v.goal,depth:v.depth})}>{v.depth==='deep'?'研究级详解':'重点理解'} · {v.goal||'完整理解当前节点'}</button>)}</div></details>}
 {!!artifact?.coverage?.checks?.length&&<details className="kw-learning-coverage"><summary>查看讲解覆盖情况</summary><ul>{artifact.coverage.checks.map(check=><li key={check.key}><strong>{check.label}</strong><span>{check.status==='complete'?'已包含':check.status==='not_applicable'?'不适用':'待补充'}</span>{check.note&&<small>{check.note}</small>}</li>)}</ul><p>此检查用于发现讲解缺项，不代表论文结论或实验已经独立验证。</p></details>}

  </>}
  evidence={<LearningEvidence key={projectId+nodeId} node={detail.node} items={[...evidence,...(detail.evidence||[])]} onEvidence={onEvidence}/>}
  practice={<>
   {!!demos.length&&<div id="kw-learning-demos"><KnowledgeDemos ids={demos}/></div>}
 {demos.some(key=>['dot_product','scaled_attention','softmax','probability','research_design','sampling'].includes(key))&&<LearningCheck projectId={projectId} nodeId={nodeId}/>}

   <ResourceExplorer key={'resources:'+nodeId} projectId={projectId} nodeId={nodeId} initialItems={resources} onEvidence={onEvidence}/>
 <LearningPath key={'path:'+nodeId} projectId={projectId} nodeId={nodeId} onNode={onNode}/>
 {onPractice&&<div className="kw-learning-practice-entry"><div><strong>动手检验理解</strong><p>从当前知识进入练习，随时返回讲解。</p></div><Button onClick={()=>onPractice(nodeId)}>进入代码练习</Button></div>}
 <ImplementationCorrespondence key={nodeId} projectId={projectId} nodeId={nodeId} onEvidence={onEvidence} onPractice={onPractice}/>
 {!detail.node.metadata.educational&&['concept','formula','method','module','algorithm','hypothesis'].includes(detail.node.kind)&&<ConceptCorrespondence projectId={projectId} nodeId={nodeId} onEvidence={onEvidence} onNode={node=>onNode(node.id)}/>}

   {!!detail.neighbors?.length&&<details><summary>继续探索相关知识</summary><ul className="kw-node-links">{detail.neighbors.map(n=><li key={n.id}><button onClick={()=>onNode(n.id)}>{n.label}</button><Tag>{n.kind}</Tag></li>)}</ul></details>}
  </>}
  question={<NodeQuestion key={'question:'+nodeId} projectId={projectId} nodeId={nodeId} onEvidence={onEvidence} onNode={onNode} onSaveAnswer={(text,evidence)=>{setNoteDraft({text,evidence,origin:'saved_ai_answer',nonce:String(Date.now())});chooseTool('notes')}}/>}
  notes={notesOpen?<NodeNotebook key={projectId+nodeId} projectId={projectId} node={detail.node} initialDraft={noteDraft} onEvidence={onEvidence}/>:null}
 />
 </article>;
}
