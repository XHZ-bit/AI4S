import {useEffect,useRef,useState} from 'react';
import {Alert,Button,Input,Space,Spin,Tag} from 'antd';
import {generateNodeLearning,getKnowledgeNode,getNodeLearning,patchNodeLearning} from '../../api/knowledge';
import type {KnowledgeEvidence,LearningArtifact,LearningResource,LearningSection,LearningOptions,NodeDetail} from '../../api/knowledge';
import {damagedMathText} from '../learning/MathText';
import KnowledgeText,{mathAwareText} from './KnowledgeText';
import KnowledgeDemos,{DEMO_KEYS} from './KnowledgeDemos';
import {NodeBadges} from './KnowledgeGraph';
import {EvidenceList} from './KnowledgeSources';
import SourceFormulas from './SourceFormulas';
import LearningProgress from './LearningProgress';
import LearningPath from './LearningPath';
import NodeQuestion from './NodeQuestion';
import ResourceExplorer from './ResourceExplorer';
import './knowledge-learning.css';

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
export default function KnowledgeLearning({projectId,nodeId,onNode,onEvidence,onBack,focusResources=false}:{projectId:string;nodeId?:string;focusResources?:boolean;onNode:(id:string)=>void;onEvidence:(e:KnowledgeEvidence)=>void;onBack:()=>void}){
 const [detail,setDetail]=useState<NodeDetail>(),[artifact,setArtifact]=useState<LearningArtifact>(),[error,setError]=useState(''),[busy,setBusy]=useState(false),[retry,setRetry]=useState(0);const generation=useRef(0),request=useRef<AbortController>(),inFlight=useRef(false);
 const [goal,setGoal]=useState(''),[depth,setDepth]=useState<'standard'|'deep'>('deep');
 const accept=(value:LearningArtifact)=>{setArtifact(value);setGoal(value.goal||'');setDepth(value.depth||'deep')};
 const [editing,setEditing]=useState<LearningSection>(),[draft,setDraft]=useState(''),[saving,setSaving]=useState(false),[saveMessage,setSaveMessage]=useState('');
 useEffect(()=>{const c=new AbortController();const token=++generation.current;setDetail(undefined);setArtifact(undefined);setGoal('');setDepth('deep');setError('');setBusy(false);setSaving(false);setEditing(undefined);setSaveMessage('');inFlight.current=false;request.current?.abort();if(nodeId)void Promise.all([getKnowledgeNode(projectId,nodeId,c.signal),getNodeLearning(projectId,nodeId,c.signal)]).then(([d,a])=>{if(token===generation.current){setDetail(d);accept(a)}}).catch(e=>{if(!c.signal.aborted&&token===generation.current)setError(String(e))});return()=>{c.abort();request.current?.abort();generation.current++}},[projectId,nodeId,retry]);
 useEffect(()=>{if(!focusResources||!detail)return;const element=document.getElementById('kw-learning-resources') as HTMLDetailsElement|null;if(element){element.open=true;element.scrollIntoView?.({block:'start',behavior:'auto'})}},[focusResources,detail?.node.id]);
 const generate=async(refresh=false)=>{if(!nodeId||busy||saving||editing||inFlight.current)return;inFlight.current=true;const token=generation.current;const c=new AbortController();request.current=c;setBusy(true);setError('');setSaveMessage('');try{const result=await generateNodeLearning(projectId,nodeId,refresh&&goal.trim()===(artifact?.goal||'')&&depth===(artifact?.depth||'deep'),c.signal,{goal:goal.trim(),depth});if(token===generation.current)accept(result)}catch(e){if(!c.signal.aborted&&token===generation.current)setError(String(e))}finally{if(token===generation.current){inFlight.current=false;setBusy(false)}}};
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
  if(text||edited)return text;
  return key==='overview'?contentText(detail.node.summary):key==='derivation'&&latex&&!formulaSources.length?'$$'+latex+'$$':'';
 };
 const visibleKeys=sectionKeys.filter(key=>editing===key||(!artifact?.hidden_sections?.includes(key)&&!!(textFor(key)||(key==='prerequisites'&&prerequisites.length)||(key==='definition'&&formulaSources.length))));
 const managedKeys=sectionKeys.filter(key=>!visibleKeys.includes(key));
 const demos=DEMO_KEYS([...(detail.demos||[]),...(artifact?.demos||[])]);
 const resources=(artifact?.resources?.length?artifact.resources:detail.resources||[]).filter(usableResource);
 const hasToc=!!(visibleKeys.length||demos.length||resources.length||evidence.length);
 const beginEdit=(key:LearningSection)=>{setEditing(key);setDraft(sections?.[key]||(key==='overview'?detail.node.summary:''));setSaveMessage('')};
 return <article className="kw-learning-view"><header className="kw-learning-heading"><div><Button type="text" onClick={onBack}>返回原位置</Button><NodeBadges node={detail.node}/><h2>{detail.node.label}</h2><span className="kw-learning-content-kind">{artifact?.status==='basic'?'原文基础内容':artifact?.status==='ready'?(artifact.depth==='standard'?'重点理解':'研究级详解'):'讲解待补充'}</span></div><div className="kw-learning-request"><label>这次想学懂什么<Input.TextArea aria-label="深入学习目标" value={goal} onChange={e=>setGoal(e.target.value)} maxLength={1500} autoSize={{minRows:2,maxRows:5}} disabled={busy||saving||!!editing} placeholder="例如：解释变量和维度，逐步推导，再用数值例子说明边界"/></label><label>讲解深度<select aria-label="讲解深度" value={depth} onChange={e=>setDepth(e.target.value as 'standard'|'deep')} disabled={busy||saving||!!editing}><option value="deep">研究级详解</option><option value="standard">重点理解</option></select></label><Button type="primary" loading={busy} disabled={saving||!!editing} onClick={()=>void generate(artifact?.status==='ready')}>{artifact?.status==='ready'&&goal.trim()===(artifact.goal||'')&&depth===(artifact.depth||'deep')?'更新深入讲解':'准备深入讲解'}</Button></div></header>
 <LearningProgress key={'progress:'+nodeId} projectId={projectId} nodeId={nodeId}/>
 <LearningPath key={'path:'+nodeId} projectId={projectId} nodeId={nodeId} onNode={onNode}/>
 <details className="kw-node-question-fold"><summary>围绕当前知识提问</summary><NodeQuestion key={'question:'+nodeId} projectId={projectId} nodeId={nodeId} onEvidence={onEvidence} onNode={onNode}/></details>
 {!!artifact?.variants&&artifact.variants.length>1&&<details className="kw-learning-history"><summary>已保存讲解 · {artifact.variants.length} 个问题与深度组合</summary><div>{artifact.variants.map(v=><button key={v.id} disabled={busy||saving||!!editing} title={v.goal} onClick={()=>void loadVariant({goal:v.goal,depth:v.depth})}>{v.depth==='deep'?'研究级详解':'重点理解'} · {v.goal||'完整理解当前节点'}</button>)}</div></details>}
 {!!artifact?.coverage?.checks?.length&&<details className="kw-learning-coverage"><summary>查看讲解覆盖情况</summary><ul>{artifact.coverage.checks.map(check=><li key={check.key}><strong>{check.label}</strong><span>{check.status==='complete'?'已包含':check.status==='not_applicable'?'不适用':'待补充'}</span>{check.note&&<small>{check.note}</small>}</li>)}</ul><p>此检查用于发现讲解缺项，不代表论文结论或实验已经独立验证。</p></details>}
 {busy&&<div role="status" className="kw-generation-status"><Spin size="small"/><span>正在读取依据并准备讲解，已有内容仍可阅读。</span></div>}{saveMessage&&<p role="status" className="kw-muted">{saveMessage}</p>}{error&&<Alert type="error" message="讲解未更新" description={error} action={<Button disabled={busy||saving} onClick={()=>setRetry(v=>v+1)}>重新读取已保存版本</Button>}/>}{artifact?.stale&&<Alert type="warning" message="依据或节点已更新，当前保存的讲解需要重新检查" action={<Button disabled={busy||saving||!!editing} onClick={()=>void generate(true)}>更新讲解</Button>}/>}{!!artifact?.errors?.length&&<Alert type="warning" message="部分内容尚未准备完成" description={artifact.errors.join('；')}/>}
 <div className={'kw-learning-layout'+(hasToc?'':' kw-learning-without-toc')}>{hasToc&&<nav className="kw-learning-toc" aria-label="学习内容目录">{visibleKeys.map(key=><a key={key} href={'#kw-learning-'+key}>{sectionLabels[key]}</a>)}{!!demos.length&&<a href="#kw-learning-demos">交互演示</a>}{!!resources.length&&<a href="#kw-learning-resources">学习资料与代码来源</a>}{!!evidence.length&&<a href="#kw-learning-evidence">原文依据</a>}</nav>}<div className="kw-learning-main">
 {visibleKeys.map(key=>{const label=sectionLabels[key],edited=artifact?.user_edited_sections?.includes(key),text=textFor(key);return <section key={key} id={'kw-learning-'+key}><div className="kw-lesson-section-heading"><h3>{label}</h3>{edited&&<Tag>用户补充</Tag>}<Space size="small"><Button size="small" type="text" aria-label={'修订讲解：'+label} disabled={busy||saving||!!editing} onClick={()=>beginEdit(key)}>修订讲解</Button><Button size="small" type="text" disabled={busy||saving||!!editing} aria-label={'隐藏讲解：'+label} onClick={()=>void revise({hidden_sections:[...(artifact?.hidden_sections||[]),key]})}>隐藏此节</Button></Space></div>{editing===key?<div className="kw-lesson-editor"><label htmlFor={'kw-edit-lesson-'+key}>{label}内容</label><Input.TextArea id={'kw-edit-lesson-'+key} value={draft} onChange={e=>setDraft(e.target.value)} autoSize={{minRows:8,maxRows:24}} maxLength={25000} disabled={saving}/><p>支持 LaTeX 与代码块。保存后标为用户补充，重新生成保留人工修订与隐藏选择。</p><Space><Button type="primary" loading={saving} onClick={()=>void revise({sections:{[key]:draft}})}>保存讲解修订</Button><Button disabled={saving} onClick={()=>setEditing(undefined)}>取消修订</Button></Space></div>:<>{text&&<KnowledgeText text={mathAwareText(text,detail.node.metadata.latex)}/>} {key==='definition'&&!!formulaSources.length&&<SourceFormulas items={formulaSources} evidence={formulaEvidence} onEvidence={onEvidence}/>} {key==='prerequisites'&&!!prerequisites.length&&<div className="kw-prerequisite-map" aria-label="前置知识依赖图"><div className="kw-prerequisite-nodes">{prerequisites.map(n=><button key={n.id} onClick={()=>onNode(n.id)}><small>前置知识</small><strong>{n.label}</strong>{n.summary&&<span>{n.summary.slice(0,100)}</span>}</button>)}</div><div className="kw-prerequisite-target"><span>理解这些知识有助于学习</span><strong>{detail.node.label}</strong></div></div>}</>}</section>})}
 {!!demos.length&&<div id="kw-learning-demos"><KnowledgeDemos ids={demos}/></div>}
 <ResourceExplorer key={'resources:'+nodeId} projectId={projectId} nodeId={nodeId} initialItems={resources} onEvidence={onEvidence}/>
 {!!evidence.length&&<section id="kw-learning-evidence"><h3>原文依据</h3><h4>当前知识的直接依据</h4>{directEvidence.length?<EvidenceList items={directEvidence} onOpen={onEvidence}/>:<p>当前没有可定位的直接依据，请结合来源核对。</p>}{!!associatedEvidence.length&&<details><summary>比较与关联来源 · {associatedEvidence.length} 处</summary><p className="kw-muted">这些内容用于比较或解释关系，不代表当前方法的原作者陈述。</p><EvidenceList items={associatedEvidence} onOpen={onEvidence}/></details>}</section>}
 {!!detail.neighbors?.length&&<section><h3>继续探索</h3><ul className="kw-node-links">{detail.neighbors.map(n=><li key={n.id}><button onClick={()=>onNode(n.id)}>{n.label}</button><Tag>{n.kind}</Tag></li>)}</ul></section>}
 {!!managedKeys.length&&<details className="kw-learning-management"><summary>管理学习内容</summary><div>{managedKeys.map(key=><div key={key}><span>{sectionLabels[key]}</span>{artifact?.hidden_sections?.includes(key)?<Button size="small" type="text" disabled={busy||saving||!!editing} aria-label={'恢复讲解：'+sectionLabels[key]} onClick={()=>void revise({hidden_sections:(artifact.hidden_sections||[]).filter(k=>k!==key)})}>恢复此节</Button>:<Button size="small" type="text" disabled={busy||saving||!!editing} aria-label={'修订讲解：'+sectionLabels[key]} onClick={()=>beginEdit(key)}>补充内容</Button>}</div>)}</div></details>}
 </div></div></article>;
}
