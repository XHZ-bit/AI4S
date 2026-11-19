import {useEffect,useLayoutEffect,useRef,useState,type CSSProperties,type ReactNode} from 'react';
import {Alert,Button,Input,Select,Space,Spin,Tag} from 'antd';
import {Link} from 'react-router-dom';
import {apiGet} from '../../api/client';
import {analyzeKnowledgeSource,analysisStatusLabels,attachKnowledgePaper,cancelKnowledgeAnalysis,getKnowledgeNode,getKnowledgeSource,linkKnowledgeSource,nodeKindLabels,patchKnowledgeSource,sourceFileUrl,sourceImageUrl,uploadKnowledgeSource} from '../../api/knowledge';
import type {AnalysisRun,KnowledgeEvidence,KnowledgeSource,NodeDetail,SourceBlock,SourceKind} from '../../api/knowledge';
import PdfReader from '../workspace/PdfReader';
import MathText,{displayMath} from '../learning/MathText';
import EvidenceQuote from './EvidenceQuote';
import ProjectWorkbench from '../workbench/ProjectWorkbench';
import SourceFormulas from './SourceFormulas';
import SourceCoverage from './SourceCoverage';
import FormulaContext from './FormulaContext';
import './source-readiness.css';

export const sourceKindLabels:Record<string,string>={paper:'论文',report:'研究报告',results:'实验结果',code:'代码'};
const stages:Record<string,string>={save:'原文保存',parse:'结构解析',extract:'知识抽取',graph:'空间图谱'};
const stageStatuses:Record<string,string>={pending:'等待',running:'处理中',done:'完成',partial:'部分完成',failed:'失败',skipped:'未执行'};
export function AnalysisStatus({run,compact=false,demo=false}:{run?:AnalysisRun;compact?:boolean;demo?:boolean}){
 if(!run)return <span className="kw-muted">{demo?'原创演示资料 · 已准备':'尚未分析'}</span>;
 return <div className="kw-analysis"><span className={'kw-run-status kw-run-'+run.status}>{analysisStatusLabels[run.status]||run.status}</span>{!compact&&<ol className="kw-stage-list">{Object.entries(stages).map(([key,label])=><li key={key} data-status={run.stages?.[key as keyof AnalysisRun['stages']]||'pending'}><span>{label}</span><small>{stageStatuses[run.stages?.[key as keyof AnalysisRun['stages']]]||'等待'}</small></li>)}</ol>}{!compact&&!!run.errors?.length&&<Alert type="warning" message="处理尚未全部完成" description={run.errors.join('；')}/>} {!compact&&!!run.warnings?.length&&<details><summary>查看处理说明</summary><ul>{run.warnings.map((warning,i)=><li key={i}>{warning}</li>)}</ul></details>}</div>;
}
export function evidenceLocation(e:KnowledgeEvidence){const l=e.locator||{};return [l.page?`第 ${l.page} 页`:'',l.heading,l.start_line?`第 ${l.start_line}${l.end_line&&l.end_line!==l.start_line?'—'+l.end_line:''} 行`:'',l.sheet,l.cell_range,l.path,l.commit?'版本 '+l.commit.slice(0,8):'',l.ordinal!==undefined&&l.ordinal!==null&&!l.page&&!l.start_line?`段落 ${l.ordinal+1}`:''].filter(Boolean).join(' · ');}
export function EvidenceList({items,onOpen}:{items:KnowledgeEvidence[];onOpen:(e:KnowledgeEvidence)=>void}){
 return items.length?<ol className="kw-evidence-list">{items.map(e=><li key={e.id}><button type="button" onClick={()=>onOpen(e)}><strong>{e.source_title||'查看原文'}</strong><span>{evidenceLocation(e)||'查看来源段落'}</span>{(e.source_missing||e.source_changed||e.unresolved)&&<small className="kw-evidence-state">{e.source_missing?'原资料已移除':e.source_changed?'来源已变化，需重新核对':'当前依据无法定位，请核对原文'}</small>}</button>{e.formula?<SourceFormulas items={[e.formula]} evidence={[e]} onEvidence={onOpen}/>:e.quote&&<blockquote><EvidenceQuote evidence={e}/></blockquote>}</li>)}</ol>:null;
}
function Cells({block}:{block:SourceBlock}){
 const raw=block.metadata.cells||block.metadata.rows;let rows:unknown[][]=[];
 if(Array.isArray(raw))rows=raw.map(row=>Array.isArray(row)?row:Object.values((row||{}) as Record<string,unknown>));
 if(!rows.length)return <pre>{block.text}</pre>;
 return <div className="kw-table-scroll"><table className="kw-source-table"><tbody>{rows.map((row,i)=><tr key={i}>{row.map((cell,j)=><td key={j}>{typeof cell==='object'?JSON.stringify(cell):<MathText text={String(cell??'')} showSourceOnError/>}</td>)}</tr>)}</tbody></table></div>;
}
export interface SourceKnowledgeContext {block?:string;page?:number}
function ReadingFormulaContext({projectId,nodeId,onEvidence,onLearn}:{projectId:string;nodeId:string;onEvidence?:(evidence:KnowledgeEvidence)=>void;onLearn?:()=>void}){
 const [detail,setDetail]=useState<NodeDetail>(),[error,setError]=useState(''),[retry,setRetry]=useState(0);
 useEffect(()=>{
  const controller=new AbortController();setDetail(undefined);setError('');
  getKnowledgeNode(projectId,nodeId,controller.signal).then(value=>{if(!controller.signal.aborted)setDetail(value)})
   .catch(cause=>{if(!controller.signal.aborted)setError(String(cause))});
  return()=>controller.abort();
 },[projectId,nodeId,retry]);
 if(error)return <Alert type="warning" message="公式说明暂未读到" description={error} action={<Button onClick={()=>setRetry(value=>value+1)}>重新读取</Button>}/>;
 return detail?<FormulaContext metadata={detail.node.metadata} evidence={detail.evidence} onEvidence={onEvidence} onLearn={onLearn} showEmpty/>:<div role="status"><Spin size="small"/> 读取本公式的已保存说明…</div>;
}

export function SourceReader({projectId,sourceId,sourcePicker,page=1,targetPage,blockId,quote,bbox,startLine,endLine,onPageChange,onNode,onLearn,onEvidence}:{projectId:string;sourceId?:string;sourcePicker?:ReactNode;page?:number;targetPage?:number;blockId?:string;quote?:string;bbox?:number[];startLine?:number;endLine?:number;onPageChange?:(page:number)=>void;onNode?:(id:string,context:SourceKnowledgeContext)=>void;onLearn?:(id:string,context:SourceKnowledgeContext)=>void;onEvidence?:(evidence:KnowledgeEvidence)=>void}){
 const [source,setSource]=useState<KnowledgeSource>(),[error,setError]=useState(''),[retry,setRetry]=useState(0),[find,setFind]=useState(''),[activeBlock,setActiveBlock]=useState(blockId),[relatedSelection,setRelatedSelection]=useState('');
 const [formulaExpanded,setFormulaExpanded]=useState(false);
 const documentLayout=useRef<HTMLDivElement>(null),documentBody=useRef<HTMLElement>(null),commandBar=useRef<HTMLDivElement>(null),[documentHeight,setDocumentHeight]=useState(480);
 const locate=(target:HTMLElement|null)=>{const body=documentBody.current;if(body&&target&&body.contains(target))body.scrollTop+=target.getBoundingClientRect().top-body.getBoundingClientRect().top-Math.max(16,(body.clientHeight-target.getBoundingClientRect().height)/2)};
 useEffect(()=>{setActiveBlock(blockId);setRelatedSelection('');setFormulaExpanded(false)},[sourceId,blockId]);
 useEffect(()=>{setSource(undefined);setError('');setFind('');if(!sourceId)return;const controller=new AbortController();getKnowledgeSource(projectId,sourceId,controller.signal).then(value=>{if(!controller.signal.aborted)setSource(value)}).catch(e=>{if(!controller.signal.aborted)setError(String(e))});return()=>controller.abort()},[projectId,sourceId,retry]);
 useEffect(()=>{if(!source||!blockId)return;const frame=requestAnimationFrame(()=>locate(startLine?document.getElementById('kw-line-'+blockId+'-'+startLine):document.getElementById('kw-block-'+blockId)));return()=>cancelAnimationFrame(frame)},[source,blockId,startLine]);
 useLayoutEffect(()=>{
  const element=documentLayout.current;if(!element)return;
  const measure=()=>{const next=Math.max(240,Math.floor(window.innerHeight-Math.max(0,element.getBoundingClientRect().top)-12));setDocumentHeight(old=>old===next?old:next)};
  measure();const observer=new ResizeObserver(measure);observer.observe(element);if(commandBar.current)observer.observe(commandBar.current);const workspace=element.closest('.kw-workspace');if(workspace)observer.observe(workspace);window.addEventListener('resize',measure);
  return()=>{observer.disconnect();window.removeEventListener('resize',measure)};
 },[source?.id]);
 if(!sourceId)return <section className="kw-empty"><h2>选择一份资料开始阅读</h2><p>原文和结构解析分开保存，解析进行时也能打开已保存的 PDF。</p></section>;
 if(error)return <Alert type="error" message="资料暂时无法打开" description={error} action={<Button onClick={()=>setRetry(x=>x+1)}>重试</Button>}/>;
 if(!source)return <div className="kw-loading"><Spin/><span role="status">读取资料…</span></div>;
 const pdf=source.media_type==='application/pdf'||/\.pdf$/i.test(source.filename||'');
 const blocks=source.blocks||[];const visible=blocks.filter(b=>!find||[b.heading,b.text].join(' ').toLowerCase().includes(find.toLowerCase()));
 const selected=blocks.find(b=>b.id===blockId);const isCode=source.kind==='code';
 const contextBlock=blocks.find(b=>b.id===activeBlock)||visible[0];
 const contextIds=new Set(pdf?blocks.filter(b=>b.page===page).map(b=>b.id):contextBlock?[contextBlock.id]:[]);
 const related=(source.knowledge_nodes||[]).filter(n=>n.block_ids.some(id=>contextIds.has(id)));
 const currentRelated=related.find(n=>n.id===relatedSelection)||related.find(n=>n.kind==='formula'&&n.block_ids.includes(blockId||''))||related.find(n=>n.block_ids.includes(blockId||''))||related.find(n=>n.kind==='formula')||related[0];
 const knowledgeContext={block:pdf?(currentRelated?.block_ids.find(id=>id===blockId&&contextIds.has(id))||currentRelated?.block_ids.find(id=>contextIds.has(id))):contextBlock?.id,page:pdf?page:undefined};
 return <section className={'kw-source-reader kw-source-reading-space '+(pdf?'kw-pdf-reader':'')}>
  <div className="kw-source-command-bar" ref={commandBar}>
   <div className="kw-reader-heading"><div>{sourcePicker?<div className="kw-reader-source-select"><span>当前资料</span>{sourcePicker}</div>:<><h2 title={source.title}>{source.title}</h2><span title={source.filename}>{sourceKindLabels[source.kind]}{source.filename?' · '+source.filename:''}</span></>}</div><a href={sourceFileUrl(projectId,source.id)} download={source.filename||undefined}>{source.filename?.endsWith('.repo.json')?'下载仓库快照':'下载原文件'}</a></div>
  {currentRelated?.kind==='formula'&&<div className="kw-reading-formula-tools" aria-label="当前公式操作" title={currentRelated.label}>
   {onLearn&&<Button size="small" onClick={()=>onLearn(currentRelated.id,knowledgeContext)}>学习这条公式</Button>}
   <details className="kw-source-formula-disclosure" open={formulaExpanded} onToggle={event=>{if(event.target===event.currentTarget)setFormulaExpanded(event.currentTarget.open)}}><summary>查看公式符号与条件</summary>
    {formulaExpanded&&<ReadingFormulaContext projectId={projectId} nodeId={currentRelated.id} onEvidence={onEvidence} onLearn={onLearn?()=>onLearn(currentRelated.id,knowledgeContext):undefined}/>}
   </details></div>}
  {(onNode||onLearn)&&!!related.length&&<details className="kw-related-knowledge"><summary title={currentRelated.label}>{pdf?'第 '+page+' 页关联知识':'当前段落关联知识'} · {related.length}</summary><div className="kw-source-knowledge"><Select size="small" aria-label="当前原文关联知识" value={currentRelated.id} onChange={setRelatedSelection} showSearch optionFilterProp="label" options={related.map(n=>({value:n.id,label:(nodeKindLabels[n.kind]||n.kind)+'：'+n.label}))}/>{onNode&&<Button size="small" onClick={()=>onNode(currentRelated.id,knowledgeContext)}>查看关联知识</Button>}{onLearn&&<Button size="small" type="primary" onClick={()=>onLearn(currentRelated.id,knowledgeContext)}>深入学习此处</Button>}</div></details>}
  </div>
  {source.removed&&<Alert type="warning" message="此资料已从空间移除，保留历史原文与记录"/>}
  {pdf?<PdfReader resource={{id:source.id,kind:'pdf',title:source.title,origin:'source',version:source.version,url:sourceFileUrl(projectId,source.id),passages:blocks.map(b=>({id:b.id,heading:b.heading,text:b.text,page:b.page}))}} initialPage={page} quote={quote||selected?.text} bbox={bbox||selected?.bbox||undefined} targetPage={targetPage||selected?.page||page} onPageChange={onPageChange}/>:<>
   <div ref={documentLayout} className="kw-document-layout" style={{'--kw-document-height':documentHeight+'px'} as CSSProperties}><nav aria-label="资料章节"><div className="kw-document-find"><Input.Search aria-label="在当前资料中查找" placeholder="查找文字或代码" value={find} onChange={e=>setFind(e.target.value)} allowClear/></div>{blocks.filter(b=>b.heading||b.metadata.symbol).map(b=><a key={b.id} onClick={event=>{event.preventDefault();setActiveBlock(b.id);locate(document.getElementById('kw-block-'+b.id))}} href={'#kw-block-'+b.id}>{String(b.metadata.symbol||b.heading||'段落 '+(b.ordinal+1))}</a>)}</nav><article ref={documentBody} aria-label={isCode?'源码阅读区':'原文内容'} className={'kw-document '+(isCode?'kw-code-document':'')}>{visible.length?visible.map(b=><section key={b.id} tabIndex={0} onFocus={()=>setActiveBlock(b.id)} onClick={()=>setActiveBlock(b.id)} id={'kw-block-'+b.id} className={blockId===b.id?'kw-source-block kw-source-highlight':activeBlock===b.id?'kw-source-block kw-active-source-block':'kw-source-block'}>
    {b.heading&&<h3>{b.heading}</h3>}{typeof (b.metadata.path||b.metadata.file_path)==='string'&&<p className="kw-code-path"><code>{String(b.metadata.path||b.metadata.file_path)}</code>{typeof b.metadata.commit==='string'&&<span>版本 {b.metadata.commit.slice(0,8)}</span>}{typeof b.metadata.url==='string'&&/^https?:\/\//i.test(b.metadata.url)&&<a href={b.metadata.url} target="_blank" rel="noreferrer">固定版本源码</a>}</p>}{!!b.metadata.symbol&&<p className="kw-code-symbol">{String(b.metadata.symbol)} · 第 {String(b.metadata.start_line||1)}—{String(b.metadata.end_line||1)} 行</p>}
    {b.kind==='table'||b.metadata.cells||b.metadata.rows?<Cells block={b}/>:isCode||b.kind==='code'?<pre className="kw-code-lines">{b.text.split('\n').map((line,index)=><span key={index} id={'kw-line-'+b.id+'-'+(Number(b.metadata.start_line||1)+index)} className={b.id===blockId&&startLine&&Number(b.metadata.start_line||1)+index>=startLine&&Number(b.metadata.start_line||1)+index<=(endLine||startLine)?'kw-code-line-highlight':undefined}><i>{Number(b.metadata.start_line||1)+index}</i><code>{line||' '}</code></span>)}</pre>:<MathText text={b.metadata.latex?displayMath(String(b.metadata.latex)):b.kind==='formula'?displayMath(b.text):b.text} showSourceOnError/>}
    {(b.kind==='image'||b.kind==='picture'||b.kind==='figure'||!!b.metadata.image_base64)&&<img src={sourceImageUrl(projectId,source.id,b.id)} alt={b.heading||'原文图示'}/>}
    {typeof b.metadata.image_url==='string'&&/^(\/|https?:\/\/|data:image\/)/i.test(b.metadata.image_url)&&<img src={b.metadata.image_url} alt={b.heading||'原文图示'}/>}
   </section>):<p>{blocks.length?'没有匹配内容。':'结构解析尚未完成。可下载原文件，或在资料页查看处理状态。'}</p>}</article></div></>}
 </section>;
}

function SourceQuality({source}:{source:KnowledgeSource}){
 const quality=source.quality||{};const raw=quality.formula_coverage;const coverage=raw&&typeof raw==='object'?raw as Record<string,unknown>:undefined;
 if(coverage&&typeof coverage.total==='number'&&coverage.total>0)return <p className="kw-source-quality">公式识别：已识别 {Number(coverage.recognized||0)} / 检测到 {coverage.total} 处{Number(coverage.recognized||0)<coverage.total?'，其余内容仍可查看原图。':'，可对照原文核对。'}</p>;
 if(quality.formula_status==='not_parsed')return <p className="kw-source-quality">公式尚未完成结构识别，可先阅读原文。</p>;
 return null;
}

type SourceAvailability={original:boolean;parsed:boolean;blocks:number;semantic_nodes:number;parse_partial:boolean};
export function SourceReadiness({source}:{source:KnowledgeSource}){
 const available=(source as KnowledgeSource&{availability?:SourceAvailability}).availability;
 const status=source.analysis?.status;
 const working=status==='queued'||status==='running';
 const summary=available?.original===false?'原文件暂不可用':working?'原文已保存 · 分析中':status==='succeeded'?'分析完成':status==='partial'?'部分分析完成':status==='interrupted'?'原文已保存 · 可继续分析':status==='cancelled'?'处理已停止 · 已有内容保留':status==='failed'?'分析未完成 · 可重试':source.demo?'演示资料已就绪':'原文已保存';
 return <details className="kw-source-readiness"><summary>{summary}</summary><div className="kw-source-readiness-body">
  {available&&<dl><div><dt>原文</dt><dd>{available.original?'可阅读':'文件缺失'}</dd></div><div><dt>文本结构</dt><dd>{available.parsed?(available.parse_partial?'部分可用':'已保存')+' · '+available.blocks+' 个内容块':working?'处理中':'尚未完成'}</dd></div><div><dt>语义知识</dt><dd>{available.semantic_nodes?available.semantic_nodes+' 个节点':'尚未生成'}</dd></div></dl>}
  <SourceQuality source={source}/>
  <AnalysisStatus run={source.analysis} demo={source.demo||source.parser==='original-teaching-fixture'}/>
  {available?.parse_partial&&<p className="kw-source-readiness-note">可先阅读原文和已有知识。继续分析会复用已保存的文本结构，并补充未完成的知识抽取。</p>}
 </div></details>;
}

export default function KnowledgeSources({projectId,sources,onUpdated,onRead,onGraph,onEvidence,workspace}:{projectId:string;sources:KnowledgeSource[];onUpdated:()=>void;onRead:(source:string)=>void;onGraph:(source:string)=>void;onEvidence?:(evidence:KnowledgeEvidence)=>void;workspace?:unknown}){
 const [importOpen,setImportOpen]=useState(()=>!sources.some(source=>!source.removed));
 const [materialTab,setMaterialTab]=useState<'sources'|'records'>('sources');
 useEffect(()=>setImportOpen(!sources.some(source=>!source.removed)),[projectId]);
 const [kind,setKind]=useState<SourceKind|'auto'>('auto'),[busy,setBusy]=useState(''),[error,setError]=useState(''),[notice,setNotice]=useState(''),[url,setUrl]=useState(''),[papers,setPapers]=useState<{uid:string;title:string}[]>([]),[paper,setPaper]=useState(''),[renaming,setRenaming]=useState<{id:string;title:string}>();const input=useRef<HTMLInputElement>(null);const alive=useRef(true);
 useEffect(()=>{alive.current=true;const c=new AbortController();apiGet<unknown>('/api/papers',undefined,c.signal).then(raw=>{if(!alive.current)return;const data=raw as {items?:{uid:string;title:string}[];papers?:{uid:string;title:string}[]};setPapers(Array.isArray(raw)?raw:data.items||data.papers||[])}).catch(()=>{});return()=>{alive.current=false;c.abort()}},[projectId]);
 const act=async(id:string,fn:()=>Promise<unknown>,success='已保存。')=>{if(busy)return;setBusy(id);setError('');setNotice('');try{const raw=await fn();if(alive.current){onUpdated();const result=raw as {scheduled?:boolean;notice?:string}|undefined;setNotice(result?.scheduled===false?(result.notice||'原文已保存，分析暂未开始，可稍后继续。'):success)}}catch(e){if(alive.current){onUpdated();setError(e instanceof Error?e.message:String(e))}}finally{if(alive.current)setBusy('')}};
 const upload=async(files:FileList|null)=>{if(!files?.length||busy)return;const picked=Array.from(files);await act('upload',async()=>{const pending:string[]=[];for(const file of picked){const result=await uploadKnowledgeSource(projectId,file,kind==='auto'?undefined:kind) as {scheduled?:boolean;notice?:string};if(alive.current)onUpdated();if(result.scheduled===false)pending.push(file.name)}return pending.length?{scheduled:false,notice:'原文已保存；'+pending.join('、')+' 的分析暂未开始，可在资料列表继续。'}:undefined},'资料已保存，分析状态会自动更新。');if(input.current)input.current.value='';};
 return <section className="kw-materials"><header className="kw-section-heading"><div className="kw-material-title"><h2>资料与记录</h2><div className="kw-material-tabs" role="tablist" aria-label="资料与记录分区" onKeyDown={event=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;event.preventDefault();const next=event.key==='Home'?'sources':event.key==='End'?'records':materialTab==='sources'?'records':'sources';setMaterialTab(next);document.getElementById('kw-material-'+next+'-tab')?.focus()}}><button type="button" role="tab" id="kw-material-sources-tab" tabIndex={materialTab==='sources'?0:-1} aria-selected={materialTab==='sources'} aria-controls="kw-material-sources-panel" onClick={()=>setMaterialTab('sources')}>资料</button><button type="button" role="tab" id="kw-material-records-tab" tabIndex={materialTab==='records'?0:-1} aria-selected={materialTab==='records'} aria-controls="kw-material-records-panel" onClick={()=>setMaterialTab('records')}>研究记录</button></div></div><Button type={importOpen&&materialTab==='sources'?'default':'primary'} aria-expanded={materialTab==='sources'&&importOpen} aria-controls="kw-material-import" onClick={()=>{setMaterialTab('sources');setImportOpen(value=>materialTab==='records'?true:!value)}}>{materialTab==='sources'&&importOpen?'收起导入':'添加资料'}</Button></header>
 {error&&<Alert type="error" showIcon message="操作未完成" description={error}/>} {notice&&<p role="status">{notice}</p>}
 <section id="kw-material-sources-panel" role="tabpanel" aria-labelledby="kw-material-sources-tab" hidden={materialTab!=='sources'}>
 <div id="kw-material-import" className="kw-material-import" hidden={!importOpen}><p className="kw-material-import-intro">上传后自动解析、抽取知识并更新当前空间。不同空间的修订分别保存。</p>
 <div className="kw-upload-area" onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();void upload(e.dataTransfer.files)}}><div><strong>把资料拖到这里，或选择文件</strong><p>PDF、DOCX、Markdown、文本、实验表格、JSON 和代码文件。</p></div><Space wrap><Select aria-label="上传资料类型" value={kind} onChange={setKind} options={[{value:'auto',label:'自动识别类型'},...Object.entries(sourceKindLabels).map(([value,label])=>({value,label}))]}/><Button type="primary" loading={busy==='upload'} disabled={!!busy} onClick={()=>input.current?.click()}>选择文件并分析</Button><input ref={input} aria-label="上传研究资料" type="file" multiple accept=".pdf,.docx,.md,.markdown,.txt,.csv,.xlsx,.json,.py,.js,.ts,.tsx,.jsx,.cpp,.c,.h,.yaml,.yml,.ipynb" hidden onChange={e=>void upload(e.target.files)}/></Space></div>
 <div className="kw-import-lines"><label><span>添加论文或公开仓库链接</span><Space.Compact block><Input aria-label="资料链接" placeholder="https://…" value={url} onChange={e=>setUrl(e.target.value)}/><Button disabled={!url.trim()||!!busy} loading={busy==='link'} onClick={()=>void act('link',()=>linkKnowledgeSource(projectId,url,kind==='auto'?undefined:kind).then(r=>{setUrl('');return r}))}>添加并分析</Button></Space.Compact></label><label><span>关联资料库中已有论文</span><Space.Compact block><Select aria-label="关联已有论文" showSearch optionFilterProp="label" value={paper||undefined} onChange={setPaper} placeholder="选择论文" options={papers.filter(p=>!sources.some(s=>s.paper_uid===p.uid&&!s.removed)).map(p=>({value:p.uid,label:p.title}))}/><Button disabled={!paper||!!busy} loading={busy==='attach'} onClick={()=>void act('attach',()=>attachKnowledgePaper(projectId,paper).then(r=>{setPaper('');return r}))}>关联并分析</Button></Space.Compact></label></div>
 </div>
 <ul className="kw-source-list">{sources.map(source=><li key={source.id} className={source.removed?'kw-source-removed':''}><div className="kw-source-list-title">{renaming?.id===source.id?<Space.Compact><Input aria-label="资料标题" value={renaming.title} onChange={e=>setRenaming({id:source.id,title:e.target.value})}/><Button loading={busy==='rename-'+source.id} disabled={!renaming.title.trim()} onClick={()=>void act('rename-'+source.id,()=>patchKnowledgeSource(projectId,source.id,{title:renaming.title.trim()}).then(result=>{setRenaming(undefined);return result}))}>保存标题</Button><Button onClick={()=>setRenaming(undefined)}>取消</Button></Space.Compact>:<button type="button" onClick={()=>onRead(source.id)}>{source.title}</button>}<span>{sourceKindLabels[source.kind]} · {source.filename||source.url}{source.removed?' · 已移除':''}</span></div><SourceReadiness source={source}/>{!source.removed&&<SourceCoverage key={projectId+source.id} projectId={projectId} sourceId={source.id} sourceVersion={source.version} analysisVersion={source.analysis?.updated_at} onRead={onRead} onGraph={onGraph} onEvidence={onEvidence} onUpdated={onUpdated}/>}<Space wrap><Button onClick={()=>onRead(source.id)}>打开资料</Button><Button type="text" onClick={()=>setRenaming({id:source.id,title:source.title})}>修改标题</Button>{!source.removed&&<><Button onClick={()=>onGraph(source.id)}>{source.analysis&&['succeeded','partial'].includes(source.analysis.status)?'查看新增知识':'查看拆解图'}</Button>{source.analysis&&['queued','running'].includes(source.analysis.status)?<Button disabled={!!busy} onClick={()=>void act(source.id,()=>cancelKnowledgeAnalysis(projectId,source.analysis!.id))}>取消处理</Button>:<Button disabled={!!busy} loading={busy===source.id} onClick={()=>void act(source.id,()=>analyzeKnowledgeSource(projectId,source.id,true))}>{source.analysis?.status==='failed'&&!source.analysis?.stages?.parse?.match(/done|partial/)?'重试分析':'继续知识分析'}</Button>}<Button type="text" disabled={!!busy} onClick={()=>void act('remove-'+source.id,()=>patchKnowledgeSource(projectId,source.id,{removed:true}))}>从空间移除</Button></>}{source.removed&&<Button onClick={()=>void act(source.id,()=>patchKnowledgeSource(projectId,source.id,{removed:false}))}>恢复关联</Button>}</Space></li>)}</ul>
 {!sources.length&&<p className="kw-empty">从一篇论文或你的研究报告开始，处理结果会出现在这里。</p>}
 </section>
 <section className="kw-notebook" id="kw-material-records-panel" role="tabpanel" aria-labelledby="kw-material-records-tab" hidden={materialTab!=='records'}><div className="kw-section-heading"><h2>笔记与研究记录</h2><Link to={`/research/${projectId}?legacy=1&tab=outcomes&output=formal`}>正式方案与历史工具</Link></div><ProjectWorkbench projectId={projectId} workspace={workspace}/></section>
 </section>;
}
