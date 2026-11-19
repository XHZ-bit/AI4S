import {useEffect,useLayoutEffect,useRef,useState} from 'react';
import {Alert,Button,Input,Select,Space,Spin,Tag} from 'antd';
import type {KnowledgeEvidence} from '../../api/knowledge';
import {generateNodePractice,getNodePractice,getPracticeVersion,recordPracticeRun,reviewPracticeCode,savePracticeDraft,savePracticeExperience,getPracticeMappings,updatePracticeRunExplanation} from '../../api/knowledgePractice';
import type {KnowledgePracticeArtifact,PracticeDifficulty,PracticeMapping} from '../../api/knowledgePractice';
import KnowledgeText from './KnowledgeText';
import EvidenceQuote from './EvidenceQuote';
import {runBrowserPython} from './practiceRuntime';
import type {BrowserPythonResult} from './practiceRuntime';
import './knowledge-practice.css';
import PracticeVisuals,{VISUAL_EXAMPLE} from './PracticeVisuals';
import LearningProgress from './LearningProgress';
import {useAccessMode,useCurrentAccount} from '../SessionContext';
import PracticeWorkspace,{type PracticeTaskFocus,type PracticeResultFocus} from './PracticeWorkspace';
import './practice-desk.css';

const difficultyLabels:Record<PracticeDifficulty,string>={foundation:'基础 · 分步观察',intermediate:'进阶 · 比较与边界',advanced:'深入 · 反例与消融'};
const runLabels:Record<string,string>={idle:'运行输出',loading:'加载本地 Python 环境',running:'正在运行',success:'教学运行完成',error:'运行报错',timeout:'已超时停止',cancelled:'已停止'};
function localKey(account:string,project:string,id:string){return account==='local'?`paperstride:node-practice:${project}:${id}`:`paperstride:node-practice:account:${encodeURIComponent(account)}:${encodeURIComponent(project)}:${encodeURIComponent(id)}`}
function readDraft(account:string,project:string,item:KnowledgePracticeArtifact){
 try{const raw=JSON.parse(localStorage.getItem(localKey(account,project,item.id))||'null');if(raw&&typeof raw.code==='string'&&typeof raw.input_json==='string')return {code:raw.code,input_json:raw.input_json,revision:typeof raw.revision==='number'?raw.revision:item.revision}}catch{/* Storage is optional. */}
 return {code:item.draft_code??item.starter_code,input_json:item.input_json||'{}',revision:item.revision};
}
function stdinText(inputJson:string){
 try{
  const input=JSON.parse(inputJson);
  if(!input||typeof input!=='object'||Array.isArray(input))return '';
  return Array.isArray(input.stdin)?input.stdin.join('\n'):typeof input.stdin==='string'?input.stdin:'';
 }catch{return ''}
}
export default function KnowledgePractice({projectId,nodeId,mappingId,onBack,onNode,onEvidence}:{projectId:string;nodeId?:string;mappingId?:string;onBack:()=>void;onNode?:(id:string)=>void;onEvidence?:(e:KnowledgeEvidence)=>void}){
 const account=useCurrentAccount(),mode=useAccessMode();
 const accountScope=account?.id|| (mode==='local'?'local':'signed-out');
 const [artifact,setArtifact]=useState<KnowledgePracticeArtifact>(),[goal,setGoal]=useState(''),[difficulty,setDifficulty]=useState<PracticeDifficulty>('foundation'),[adjustment,setAdjustment]=useState('');
 const [code,setCode]=useState(''),[inputJson,setInputJson]=useState('{}'),[output,setOutput]=useState(''),[runState,setRunState]=useState('idle');
 const [checked,setChecked]=useState(false),[passed,setPassed]=useState<boolean|null>(null);
 const [outputCode,setOutputCode]=useState('');
 const [outputInput,setOutputInput]=useState('');
 const [error,setError]=useState(''),[notice,setNotice]=useState(''),[busy,setBusy]=useState(false),[loading,setLoading]=useState(false),[retry,setRetry]=useState(0),[showHints,setShowHints]=useState(false);
 const [feedback,setFeedback]=useState(''),[reviewing,setReviewing]=useState(false);
 const [mapping,setMapping]=useState<PracticeMapping>(),[prediction,setPrediction]=useState(''),[explanation,setExplanation]=useState(''),[latestRun,setLatestRun]=useState<string>(),[savingExplanation,setSavingExplanation]=useState(false);
 const [experienceDraft,setExperienceDraft]=useState(''),[savingExperience,setSavingExperience]=useState(false),[savedExperience,setSavedExperience]=useState('');
 const [taskFocus,setTaskFocus]=useState<PracticeTaskFocus>(),[resultFocus,setResultFocus]=useState<PracticeResultFocus>();
 const focusSequence=useRef(0),gutter=useRef<HTMLDivElement>(null),editor=useRef<HTMLTextAreaElement>(null);
 function syncLineNumbers(top:number){const numbers=gutter.current?.firstElementChild as HTMLElement|undefined;if(numbers)numbers.style.transform='translateY('+(-top)+'px)'}
 useLayoutEffect(()=>syncLineNumbers(editor.current?.scrollTop||0),[code]);
 const focusTask=(tab:PracticeTaskFocus['tab'])=>setTaskFocus({tab,nonce:++focusSequence.current});
 const focusResult=(tab:PracticeResultFocus['tab'])=>setResultFocus({tab,nonce:++focusSequence.current});
 const sequence=useRef(0),request=useRef<AbortController>(),operation=useRef(false),runtime=useRef<ReturnType<typeof runBrowserPython>>();
 const draftScope=useRef('');
 const draftRevision=useRef(0);
 const running=runState==='loading'||runState==='running';
 const hasResult=runState!=='idle'||!!output;
 const dirty=!!artifact&&(code!==artifact.draft_code||inputJson!==artifact.input_json);
 function accept(item:KnowledgePracticeArtifact){const draft=readDraft(accountScope,projectId,item);draftScope.current=localKey(accountScope,projectId,item.id);draftRevision.current=draft.revision;setArtifact(item);setMapping(current=>item.mapping_snapshot?{...item.mapping_snapshot,stale:!!item.mapping_stale}:mappingId?current:undefined);setCode(draft.code);setInputJson(draft.input_json);setOutput('');setOutputCode('');setOutputInput('');setFeedback('');setRunState('idle');setChecked(false);setPassed(null);setShowHints(false);setLatestRun(undefined);setPrediction('');setExplanation('');setSavingExplanation(false);focusResult('output');if(draft.revision!==item.revision)setError('服务端练习已更新，本地草稿仍保留。请先复制草稿，再重新打开最新版本。')}
 useEffect(()=>{
  const token=++sequence.current,c=new AbortController();request.current?.abort();runtime.current?.cancel();runtime.current=undefined;operation.current=false;
  setArtifact(undefined);setGoal('');setDifficulty('foundation');setAdjustment('');setError('');setNotice('');setFeedback('');setExperienceDraft('');setSavedExperience('');setSavingExperience(false);setReviewing(false);setBusy(false);setLoading(!!nodeId);setRunState('idle');setMapping(undefined);setPrediction('');setExplanation('');setLatestRun(undefined);setTaskFocus(undefined);setResultFocus(undefined);
  if(nodeId)void (async()=>{
   let parameters;
   if(mappingId){
    const data=await getPracticeMappings(projectId,nodeId,c.signal);
    const selected=data.items.find(item=>item.id===mappingId);
    parameters={goal:'',difficulty:'foundation' as PracticeDifficulty,mapping_id:mappingId,mapping_revision:selected?.revision};
   }
   return getNodePractice(projectId,nodeId,parameters,c.signal);
  })().then(item=>{if(token===sequence.current){accept(item);setGoal(item.goal);setDifficulty(item.difficulty)}}).catch(e=>{if(!c.signal.aborted&&token===sequence.current)setError(String(e))}).finally(()=>{if(token===sequence.current)setLoading(false)});
  return()=>{sequence.current++;c.abort();request.current?.abort();runtime.current?.cancel();runtime.current=undefined};
 },[projectId,nodeId,mappingId,retry,accountScope]);
 useEffect(()=>{if(!artifact||accountScope==='signed-out')return;const key=localKey(accountScope,projectId,artifact.id);if(draftScope.current!==key)return;try{if(code===artifact.draft_code&&inputJson===artifact.input_json)localStorage.removeItem(key);else localStorage.setItem(key,JSON.stringify({code,input_json:inputJson,revision:draftRevision.current}))}catch{/* Server save remains available. */}},[projectId,artifact?.id,artifact?.draft_code,artifact?.input_json,code,inputJson,accountScope]);

 async function saveCurrent(signal?:AbortSignal){
  if(!artifact)return undefined;
  if(!dirty)return artifact;
  const scope=localKey(accountScope,projectId,artifact.id);
  const item=await savePracticeDraft(projectId,artifact.id,{expected_revision:draftRevision.current,code,input_json:inputJson},signal);
  if(draftScope.current===scope)draftRevision.current=item.revision;
  return item;
 }
 async function save(){
  if(operation.current||savingExperience||!artifact)return;operation.current=true;setBusy(true);setError('');const token=sequence.current,c=new AbortController();request.current=c;
  try{const item=await saveCurrent(c.signal);if(item&&token===sequence.current){setArtifact(item);setNotice('编辑稿和输入已保存到当前空间。')}}catch(e){if(!c.signal.aborted&&token===sequence.current)setError(String(e))}finally{if(token===sequence.current){setBusy(false);operation.current=false}}
 }
 async function generate(){
  if(operation.current||running||savingExperience||!nodeId||!artifact)return;operation.current=true;setBusy(true);setError('');setNotice('');const token=sequence.current,c=new AbortController();request.current=c;
  try{
   const saved=await saveCurrent(c.signal);if(token!==sequence.current)return;if(saved)setArtifact(saved);
   const item=await generateNodePractice(projectId,nodeId,{goal,difficulty,adjustment,...(mapping?{mapping_id:mapping.id,mapping_revision:mapping.revision}:{}),previous_practice_id:saved?.id||artifact.id,refresh:artifact.status==='ready'&&artifact.goal===goal&&artifact.difficulty===difficulty},c.signal);
   if(token===sequence.current){accept(item);focusTask('instructions');setNotice('已保留上一练习版本及编辑稿。新练习尚未运行。')}
  }catch(e){if(!c.signal.aborted&&token===sequence.current)setError(String(e))}finally{if(token===sequence.current){setBusy(false);operation.current=false}}
 }
 async function switchVersion(id:string){
  if(operation.current||running||savingExperience||id===artifact?.id)return;operation.current=true;setBusy(true);setError('');const token=sequence.current,c=new AbortController();request.current=c;
  try{await saveCurrent(c.signal);const item=await getPracticeVersion(projectId,id,c.signal);if(token===sequence.current){accept(item);setGoal(item.goal);setDifficulty(item.difficulty);setAdjustment(item.adjustment||'');setNotice('已恢复该练习版本与保存的编辑稿。')}}catch(e){if(!c.signal.aborted&&token===sequence.current)setError(String(e))}finally{if(token===sequence.current){setBusy(false);operation.current=false}}
 }
 function run(check:boolean){
  if(!artifact||running||busy||savingExperience||((mappingId&&!mapping)||mapping?.stale))return;
  let inputs:unknown;try{inputs=JSON.parse(inputJson)}catch{focusTask('input');setError('输入不是有效 JSON，请修正后再运行。');return}
  focusResult('output');
  setError('');setNotice('');setOutput('');setOutputCode(code);setOutputInput(inputJson);setFeedback('');setChecked(check);setPassed(null);setLatestRun(undefined);const token=sequence.current,item=artifact,executedCode=code,executedInputs=inputJson;
  runtime.current=runBrowserPython(executedCode,inputs,check?item.test_code:'',{
   onState:state=>{if(token===sequence.current)setRunState(state)},
   onOutput:text=>{if(token===sequence.current)setOutput(text)},
   onComplete:(result:BrowserPythonResult)=>{
    if(token!==sequence.current)return;runtime.current=undefined;setRunState(result.status);setPassed(result.passed);setOutput(result.output);
    void recordPracticeRun(projectId,item.id,{...result,checked:check,code:executedCode,input_json:executedInputs,mapping_id:mapping?.id,mapping_revision:mapping?.revision,prediction,explanation}).then(record=>{
     if(token===sequence.current&&draftScope.current===localKey(accountScope,projectId,item.id)){setLatestRun(record.id);setArtifact(old=>old?.id===item.id?{...old,runs:[record,...old.runs].slice(0,10)}:old)}
    }).catch(e=>{if(token===sequence.current)setNotice('运行结果已显示，但未保存到空间：'+String(e))});
   },
  });
 }
 async function review(){
  if(!artifact||reviewing||running||busy||savingExperience)return;
  const token=sequence.current,c=new AbortController();request.current=c;
  focusResult('analysis');setReviewing(true);setError('');setFeedback('');
  try{
   const result=await reviewPracticeCode(projectId,artifact.id,{code,output:outputCode===code&&outputInput===inputJson?output:''},c.signal);
   if(token===sequence.current){setFeedback(result.feedback);setExperienceDraft(result.feedback);setSavedExperience('')}
  }catch(e){if(!c.signal.aborted&&token===sequence.current)setError(String(e))}
  finally{if(token===sequence.current)setReviewing(false)}
 }
 async function saveExperience(){
  if(!artifact||!nodeId||savingExperience||running||reviewing||busy||!experienceDraft.trim()||experienceDraft.trim().length>4000)return;
  const token=sequence.current,c=new AbortController();request.current=c;
  setSavingExperience(true);setError('');
  try{
   const result=await savePracticeExperience(projectId,nodeId,{content:experienceDraft.trim(),practice_id:artifact.id},c.signal);
   if(token===sequence.current){setSavedExperience(result.content);setNotice('已保存到当前节点的经验库。')}
  }catch(e){if(!c.signal.aborted&&token===sequence.current)setError(String(e))}
  finally{if(token===sequence.current)setSavingExperience(false)}
 }
 if(!nodeId)return <section className="kw-empty"><h2>选择一个知识节点开始练习</h2><p>从图谱中的公式、概念或方法进入，再设定你希望用代码理解的问题。</p><Button onClick={onBack}>返回研究图谱</Button></section>;
 if(loading)return <div className="kw-loading"><Spin/><span role="status">读取当前节点与练习版本…</span></div>;
 if(!artifact)return <Alert type="error" message="练习暂时无法打开" description={error} action={<Button onClick={()=>setRetry(v=>v+1)}>重试</Button>}/>;
 return <article className="kw-practice kw-practice-desk">
  <header className="kw-practice-desk-header"><div className="kw-practice-desk-title"><div><Button type="text" onClick={onBack}>返回原位置</Button><Tag>{artifact.status==='starter'?'起点模板':artifact.status==='ready'?'教学练习':'待完善'}</Tag></div><h2>{artifact.node_label} · 代码练习</h2></div><Space><Button type="primary" aria-label="生成或调整练习" disabled={busy||running||reviewing||savingExperience} onClick={()=>focusTask('settings')}>{artifact.status==='starter'?'生成专属练习':'调整练习'}</Button><Button onClick={()=>onNode?.(artifact.node_id)} disabled={!onNode}>定位图谱节点</Button></Space></header>
  <div className="kw-practice-desk-meta"><span title={artifact.goal}>当前目标：{artifact.goal} · {difficultyLabels[artifact.difficulty]}</span><label>练习版本<Select aria-label="练习版本" value={artifact.id} onChange={id=>void switchVersion(id)} disabled={busy||running||reviewing||savingExperience} options={artifact.versions.map((v,i)=>({value:v.id,label:`${i===0?'最新 · ':''}${v.title} · ${new Date(v.created_at).toLocaleTimeString()}`}))}/></label></div>
  {error&&<Alert type="error" message="操作未完成" description={error}/>} {notice&&<p role="status" className="kw-practice-desk-notice">{notice}</p>}
  {draftRevision.current!==artifact.revision&&<Alert type="warning" message="本地草稿基于较旧版本" description="先复制需要保留的内容，再选择服务端版本。" action={<Button onClick={()=>{try{localStorage.removeItem(localKey(accountScope,projectId,artifact.id))}catch{/* The server version remains available. */}draftRevision.current=artifact.revision;setCode(artifact.draft_code);setInputJson(artifact.input_json);setError('');setFeedback('')}}>使用服务端版本</Button>}/>}
  {artifact.stale&&<Alert type="warning" message="节点或来源已变化，保存的练习对应历史版本。请重新生成并核对。"/>}
  {((mappingId&&!mapping)||mapping?.stale)&&<Alert type="warning" message={mapping?.stale?'关联的论文与代码对应已变化，请先重新核对。':'当前练习缺少可用的对应快照，请从已确认的对应重新进入。'} description="核对完成前，运行和提交检查暂不可用。"/>}

  {!!artifact.errors.length&&<details><summary>练习内容有待补充</summary><ul>{artifact.errors.map((item,index)=><li key={index}>{item}</li>)}</ul></details>}
  <PracticeWorkspace projectId={projectId} nodeId={nodeId} taskFocus={taskFocus} resultFocus={resultFocus}
   instructions={<>
<section className="kw-practice-desk-instructions"><h3>{artifact.title}</h3><KnowledgeText text={artifact.prompt}/>{artifact.expected_behavior.trim()&&<div><strong>预期观察：</strong><KnowledgeText text={artifact.expected_behavior}/></div>}{artifact.simplifications.length>0&&<details><summary>教学假设与简化</summary><ul>{artifact.simplifications.map((text,i)=><li key={i}><KnowledgeText text={text}/></li>)}</ul></details>}
  {!!artifact.hints.length&&<><Button type="text" onClick={()=>setShowHints(v=>!v)} aria-expanded={showHints}>{showHints?'收起提示':'给我一点提示'}</Button>{showHints&&<ul>{artifact.hints.map((hint,i)=><li key={i}><KnowledgeText text={hint}/></li>)}</ul>}</>}
  {artifact.test_code&&<details><summary>查看检查条件</summary><pre>{artifact.test_code}</pre></details>}{artifact.reference_code&&<details><summary>查看参考实现</summary><pre>{artifact.reference_code}</pre></details>}
  {!!artifact.evidence.length&&<details><summary>查看原文依据（{artifact.evidence.length}）</summary><ul>{artifact.evidence.map(e=><li key={e.id}><Button type="link" disabled={!onEvidence} onClick={()=>onEvidence?.(e)}>{e.source_title} · {e.locator.page?`第 ${e.locator.page} 页`:e.locator.path||e.locator.heading||'来源段落'}</Button><blockquote><EvidenceQuote evidence={e}/></blockquote></li>)}</ul></details>}

</section>
   <details className="kw-practice-mapping" aria-label="关联映射"><summary>论文与代码对应</summary>{!(mappingId||mapping)?<p>当前练习未绑定特定的论文代码对应，可从已核对的对应关系进入练习。</p>:!mapping?<p>此历史练习未保存对应快照，请从已确认的对应重新进入。</p>:<><div>论文：<KnowledgeText text={mapping.paper_span}/></div><p>代码：{mapping.code_span}</p><p>核对状态：{mapping.status} · 修订 {mapping.revision} · {mapping.implementation_kind==='source'?'来源实现':'教学实现'}</p>{mapping.stale&&<Alert type="warning" message="映射来源已变化，请返回重新核对后再运行。"/>}{mapping.paper_evidence&&<Button type="link" disabled={!onEvidence} onClick={()=>onEvidence?.(mapping.paper_evidence!)}>查看论文依据</Button>}{mapping.code_evidence&&<Button type="link" disabled={!onEvidence} onClick={()=>onEvidence?.(mapping.code_evidence!)}>查看代码依据</Button>}</>}</details>
   <details><summary>练习与运行说明</summary><p>{artifact.status==='starter'?'当前是一份可编辑起点，尚未生成针对该节点的专属题目。':'当前内容是教学练习，不等同于完整的论文复现。'}</p><p>支持Python标准库；第三方包与机器人接口未接入。代码在浏览器隔离线程运行，5秒超时停止。生成练习和AI分析使用当前模型服务。</p>{!artifact.test_code&&<p>当前没有检查条件，可以先运行代码，或在设置中生成带检查条件的题目。</p>}</details>
   </>}
   input={<section className="kw-practice-desk-input">
    <label htmlFor="knowledge-practice-stdin">程序输入<span>使用 input() 时，每行对应一次输入。</span><textarea id="knowledge-practice-stdin" aria-label="程序输入" value={stdinText(inputJson)} disabled={running||busy||reviewing||savingExperience} onChange={e=>{try{const value=JSON.parse(inputJson);if(!value||typeof value!=='object'||Array.isArray(value))throw new Error();setInputJson(JSON.stringify({...value,stdin:e.target.value?e.target.value.split('\n'):[]},null,2));setError('');setFeedback('')}catch{setError('请先将输入值改为有效的 JSON 对象。')}}}/></label>
    <label htmlFor="knowledge-practice-input">输入值（JSON）<span>通过 inputs 读取，与上方程序输入同步。</span><textarea id="knowledge-practice-input" aria-label="练习输入 JSON" value={inputJson} spellCheck={false} onChange={e=>{setInputJson(e.target.value);setFeedback('')}} disabled={running||busy||reviewing||savingExperience}/></label>
    {mapping&&<label>运行前预测<Input.TextArea aria-label="运行前预测" maxLength={4000} value={prediction} onChange={e=>setPrediction(e.target.value)} disabled={running}/></label>}
   <details className="kw-visual-help"><summary>让运行结果显示为图表</summary><p>在标准库 Python 中输出 PAPERSTRIDE_VISUAL: 加 JSON，可展示表格、折线、柱状或散点。点击下方按钮会在现有代码末尾追加一个线性缩放示例；这是通用教学示例，不是论文实验结果。</p><Button disabled={running||busy||code.includes("# PaperStride 通用绘图示例")} onClick={()=>{setCode(current=>current+VISUAL_EXAMPLE);setNotice('已追加绘图示例。可在 JSON 输入中添加 "visual_scale": 2，再运行观察曲线。')}}>追加可运行绘图示例</Button></details>

   </section>}
   history={<section className="kw-practice-desk-records"><LearningProgress key={nodeId} projectId={projectId} nodeId={nodeId}/>
  {artifact.runs.length>0&&<details className="kw-practice-history"><summary>最近运行记录（{artifact.runs.length}）</summary>{artifact.runs.map(run=><div key={run.id}><strong>{runLabels[run.status]} · {run.elapsed_ms} ms{run.checked?(run.passed===null?' · 检查未完成':run.passed?' · 检查通过':' · 检查未通过'):''}</strong>{run.prediction&&<div>运行前预测：<KnowledgeText text={run.prediction}/></div>}<PracticeVisuals output={run.output}/>{run.explanation&&<div>运行解释：<KnowledgeText text={run.explanation}/></div>}<details><summary>查看当时的代码</summary><pre>{run.code}</pre></details></div>)}</details>}

    {!artifact.runs.length&&<p className="kw-muted">还没有运行记录，执行代码后会在这里保存本次输入与输出。</p>}
   </section>}
   settings={<section className="kw-practice-desk-settings"><label>我想用代码理解什么<Input.TextArea aria-label="练习学习目标" value={goal} maxLength={1000} autoSize={{minRows:3,maxRows:6}} onChange={e=>setGoal(e.target.value)} disabled={busy}/></label><label>学习深度<Select aria-label="练习难度" value={difficulty} onChange={setDifficulty} disabled={busy} options={Object.entries(difficultyLabels).map(([value,label])=>({value,label}))}/></label><label>这次如何调整<Input aria-label="练习调整要求" value={adjustment} maxLength={1500} onChange={e=>setAdjustment(e.target.value)} disabled={busy} placeholder="例如：保留公式，增加一个极端输入"/></label><Button type="primary" loading={busy} disabled={running||reviewing||savingExperience||!!mapping?.stale} onClick={()=>void generate()}>{artifact.status==='starter'?'按目标生成练习':'按目标调整练习'}</Button><p>生成前会保存当前编辑稿，并保留已有练习版本。修改代码、输入和本地运行不调用模型。</p></section>}
   editorToolbar={<div className="kw-practice-code-toolbar"><label htmlFor="knowledge-practice-code">Python 代码</label><small>Tab 缩进 · Shift+Tab 离开</small><span className={dirty?'is-dirty':''}>{dirty?'本地草稿 · 未保存到空间':'已保存'}</span></div>}
   editor={<div className="kw-practice-code-shell"><div className="kw-practice-line-numbers" ref={gutter} aria-hidden="true"><pre>{code.split('\n').map((_,index)=>index+1).join('\n')}</pre></div><textarea ref={editor} id="knowledge-practice-code" className="learning-code-editor" aria-label="节点练习 Python 代码" value={code} wrap="off" spellCheck={false} disabled={running||busy||reviewing||savingExperience} onChange={e=>{setCode(e.target.value);setFeedback('')}} onScroll={e=>syncLineNumbers(e.currentTarget.scrollTop)} onKeyDown={e=>{if(e.key==='Tab'&&!e.shiftKey){e.preventDefault();const input=e.currentTarget,start=input.selectionStart,end=input.selectionEnd;setCode(code.slice(0,start)+'    '+code.slice(end));setFeedback('');requestAnimationFrame(()=>input.setSelectionRange(start+4,start+4))}}}/></div>}
   actions={
   <div className="kw-practice-run-actions"><Button type="primary" disabled={running||busy||reviewing||savingExperience||!!((mappingId&&!mapping)||mapping?.stale)} onClick={()=>run(false)}>运行代码</Button><Button disabled={running||busy||reviewing||savingExperience||!artifact.test_code||!!((mappingId&&!mapping)||mapping?.stale)} onClick={()=>run(true)}>提交并检查</Button><Button loading={reviewing} disabled={running||busy||savingExperience||!code.trim()} onClick={()=>void review()}>AI 分析代码</Button>{running&&<Button danger onClick={()=>runtime.current?.cancel()}>停止运行</Button>}<Button disabled={running||busy||savingExperience||!dirty} onClick={()=>void save()}>保存编辑稿</Button><Button type="text" disabled={running||busy||savingExperience} onClick={()=>{setCode(artifact.starter_code);setNotice('已恢复本版本起始代码，可继续编辑。')}}>恢复起始代码</Button></div>

   }
   output={hasResult?<section className="kw-practice-result" aria-live="polite"><h3>{checked&&!running&&passed!==null?(passed?'提交检查通过':'提交检查未通过'):runLabels[runState]}</h3>{running&&<Spin size="small"/>}<PracticeVisuals output={output}/>{!running&&runState==='success'&&!output.trim()&&<p>本次运行没有标准输出。</p>}{checked&&passed!==null&&<p>检查基于当前输入与题目提供的检查条件。</p>}
    {mapping&&<div className="kw-run-explanation"><label>运行后的解释<Input.TextArea aria-label="运行后的解释" maxLength={4000} value={explanation} onChange={e=>setExplanation(e.target.value)}/></label>{latestRun&&<Button loading={savingExplanation} onClick={()=>{const token=sequence.current,scope=draftScope.current;setSavingExplanation(true);void updatePracticeRunExplanation(projectId,artifact.id,latestRun,explanation).then(record=>{if(token!==sequence.current||scope!==draftScope.current)return;setArtifact(old=>old?{...old,runs:old.runs.map(r=>r.id===record.id?record:r)}:old);setNotice('解释已保存到运行记录。')}).catch(e=>{if(token===sequence.current&&scope===draftScope.current)setError(String(e))}).finally(()=>{if(token===sequence.current&&scope===draftScope.current)setSavingExplanation(false)})}}>保存运行解释</Button>}</div>}
   </section>:<section className="kw-practice-result-empty"><strong>运行结果会显示在这里</strong><p>修改代码或输入后，点击“运行代码”。</p></section>}
   analysis={reviewing?<section role="status" className="kw-practice-result-empty"><Spin size="small"/><p>正在分析当前代码…</p></section>:feedback?<>
<section className="kw-practice-result" aria-live="polite"><h3>AI 代码分析</h3><KnowledgeText text={feedback}/><p className="kw-muted">分析基于代码和已显示的运行结果，复杂代码的执行结果需要另行验证。</p><details><summary>保存到经验库</summary><label htmlFor="practice-experience-draft">确认并编辑经验内容</label><textarea id="practice-experience-draft" aria-label="经验内容" value={experienceDraft} maxLength={4000} disabled={savingExperience} onChange={e=>setExperienceDraft(e.target.value)}/>{experienceDraft.trim().length>4000&&<p>请将经验内容缩短至 4000 字以内。</p>}<Button loading={savingExperience} disabled={!experienceDraft.trim()||experienceDraft.trim().length>4000||experienceDraft.trim()===savedExperience} onClick={()=>void saveExperience()}>{experienceDraft.trim()===savedExperience?'已保存':'确认保存经验'}</Button></details></section>
   </>:<section className="kw-practice-result-empty"><strong>针对当前代码获取建议</strong><p>点击“AI 分析代码”，结合代码及对应的运行输出检查思路。</p></section>}
  />
 </article>;
}
