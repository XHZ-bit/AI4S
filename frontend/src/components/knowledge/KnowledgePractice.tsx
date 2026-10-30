import {useEffect,useRef,useState} from 'react';
import {Alert,Button,Input,Select,Space,Spin,Tag} from 'antd';
import type {KnowledgeEvidence} from '../../api/knowledge';
import {generateNodePractice,getNodePractice,getPracticeVersion,recordPracticeRun,savePracticeDraft} from '../../api/knowledgePractice';
import type {KnowledgePracticeArtifact,PracticeDifficulty} from '../../api/knowledgePractice';
import KnowledgeText from './KnowledgeText';
import {runBrowserPython} from './practiceRuntime';
import type {BrowserPythonResult} from './practiceRuntime';
import './knowledge-practice.css';
import PracticeVisuals,{VISUAL_EXAMPLE} from './PracticeVisuals';
import LearningProgress from './LearningProgress';

const difficultyLabels:Record<PracticeDifficulty,string>={foundation:'基础 · 分步观察',intermediate:'进阶 · 比较与边界',advanced:'深入 · 反例与消融'};
const runLabels:Record<string,string>={idle:'运行输出',loading:'加载本地 Python 环境',running:'正在运行',success:'教学运行完成',error:'运行报错',timeout:'已超时停止',cancelled:'已停止'};
function localKey(project:string,id:string){return `paperstride:node-practice:${project}:${id}`}
function readDraft(project:string,item:KnowledgePracticeArtifact){
 try{const raw=JSON.parse(localStorage.getItem(localKey(project,item.id))||'null');if(raw&&typeof raw.code==='string'&&typeof raw.input_json==='string')return raw as {code:string;input_json:string}}catch{/* Storage is optional. */}
 return {code:item.draft_code||item.starter_code,input_json:item.input_json||'{}'};
}
export default function KnowledgePractice({projectId,nodeId,onBack,onNode,onEvidence}:{projectId:string;nodeId?:string;onBack:()=>void;onNode?:(id:string)=>void;onEvidence?:(e:KnowledgeEvidence)=>void}){
 const [artifact,setArtifact]=useState<KnowledgePracticeArtifact>(),[goal,setGoal]=useState(''),[difficulty,setDifficulty]=useState<PracticeDifficulty>('foundation'),[adjustment,setAdjustment]=useState('');
 const [code,setCode]=useState(''),[inputJson,setInputJson]=useState('{}'),[output,setOutput]=useState(''),[runState,setRunState]=useState('idle');
 const [error,setError]=useState(''),[notice,setNotice]=useState(''),[busy,setBusy]=useState(false),[loading,setLoading]=useState(false),[retry,setRetry]=useState(0),[showHints,setShowHints]=useState(false);
 const sequence=useRef(0),request=useRef<AbortController>(),operation=useRef(false),runtime=useRef<ReturnType<typeof runBrowserPython>>();
 const running=runState==='loading'||runState==='running';
 const hasResult=runState!=='idle'||!!output;
 const dirty=!!artifact&&(code!==artifact.draft_code||inputJson!==artifact.input_json);
 function accept(item:KnowledgePracticeArtifact){const draft=readDraft(projectId,item);setArtifact(item);setCode(draft.code);setInputJson(draft.input_json);setOutput('');setRunState('idle');setShowHints(false)}
 useEffect(()=>{
  const token=++sequence.current,c=new AbortController();request.current?.abort();runtime.current?.cancel();runtime.current=undefined;operation.current=false;
  setArtifact(undefined);setGoal('');setDifficulty('foundation');setAdjustment('');setError('');setNotice('');setBusy(false);setLoading(!!nodeId);setRunState('idle');
  if(nodeId)void getNodePractice(projectId,nodeId,undefined,c.signal).then(item=>{if(token===sequence.current){accept(item);setGoal(item.goal);setDifficulty(item.difficulty)}}).catch(e=>{if(!c.signal.aborted&&token===sequence.current)setError(String(e))}).finally(()=>{if(token===sequence.current)setLoading(false)});
  return()=>{sequence.current++;c.abort();request.current?.abort();runtime.current?.cancel();runtime.current=undefined};
 },[projectId,nodeId,retry]);
 useEffect(()=>{if(!artifact)return;try{localStorage.setItem(localKey(projectId,artifact.id),JSON.stringify({code,input_json:inputJson}))}catch{/* Server save remains available. */}},[projectId,artifact?.id,code,inputJson]);
 async function saveCurrent(signal?:AbortSignal){
  if(!artifact)return undefined;
  if(!dirty)return artifact;
  const item=await savePracticeDraft(projectId,artifact.id,{expected_revision:artifact.revision,code,input_json:inputJson},signal);
  return item;
 }
 async function save(){
  if(operation.current||!artifact)return;operation.current=true;setBusy(true);setError('');const token=sequence.current,c=new AbortController();request.current=c;
  try{const item=await saveCurrent(c.signal);if(item&&token===sequence.current){setArtifact(item);setNotice('编辑稿和输入已保存到当前空间。')}}catch(e){if(!c.signal.aborted&&token===sequence.current)setError(String(e))}finally{if(token===sequence.current){setBusy(false);operation.current=false}}
 }
 async function generate(){
  if(operation.current||running||!nodeId||!artifact)return;operation.current=true;setBusy(true);setError('');setNotice('');const token=sequence.current,c=new AbortController();request.current=c;
  try{
   const saved=await saveCurrent(c.signal);if(token!==sequence.current)return;if(saved)setArtifact(saved);
   const item=await generateNodePractice(projectId,nodeId,{goal,difficulty,adjustment,previous_practice_id:saved?.id||artifact.id,refresh:artifact.status==='ready'&&artifact.goal===goal&&artifact.difficulty===difficulty},c.signal);
   if(token===sequence.current){accept(item);setNotice('已保留上一练习版本及编辑稿。新练习尚未运行。')}
  }catch(e){if(!c.signal.aborted&&token===sequence.current)setError(String(e))}finally{if(token===sequence.current){setBusy(false);operation.current=false}}
 }
 async function switchVersion(id:string){
  if(operation.current||running||id===artifact?.id)return;operation.current=true;setBusy(true);setError('');const token=sequence.current,c=new AbortController();request.current=c;
  try{await saveCurrent(c.signal);const item=await getPracticeVersion(projectId,id,c.signal);if(token===sequence.current){accept(item);setGoal(item.goal);setDifficulty(item.difficulty);setAdjustment(item.adjustment||'');setNotice('已恢复该练习版本与保存的编辑稿。')}}catch(e){if(!c.signal.aborted&&token===sequence.current)setError(String(e))}finally{if(token===sequence.current){setBusy(false);operation.current=false}}
 }
 function run(check:boolean){
  if(!artifact||running||busy)return;
  let inputs:unknown;try{inputs=JSON.parse(inputJson)}catch{setError('输入不是有效 JSON，请修正后再运行。');return}
  setError('');setNotice('');setOutput('');const token=sequence.current,item=artifact,executedCode=code,executedInputs=inputJson;
  runtime.current=runBrowserPython(executedCode,inputs,check?item.test_code:'',{
   onState:state=>{if(token===sequence.current)setRunState(state)},
   onOutput:text=>{if(token===sequence.current)setOutput(text)},
   onComplete:(result:BrowserPythonResult)=>{
    if(token!==sequence.current)return;runtime.current=undefined;setRunState(result.status);setOutput(result.output);
    void recordPracticeRun(projectId,item.id,{...result,checked:check,code:executedCode,input_json:executedInputs}).then(record=>{
     if(token===sequence.current)setArtifact(old=>old?.id===item.id?{...old,runs:[record,...old.runs].slice(0,10)}:old);
    }).catch(e=>{if(token===sequence.current)setNotice('运行结果已显示，但未保存到空间：'+String(e))});
   },
  });
 }
 if(!nodeId)return <section className="kw-empty"><h2>选择一个知识节点开始练习</h2><p>从图谱中的公式、概念或方法进入，再设定你希望用代码理解的问题。</p><Button onClick={onBack}>返回研究图谱</Button></section>;
 if(loading)return <div className="kw-loading"><Spin/><span role="status">读取当前节点与练习版本…</span></div>;
 if(!artifact)return <Alert type="error" message="练习暂时无法打开" description={error} action={<Button onClick={()=>setRetry(v=>v+1)}>重试</Button>}/>;
 return <article className="kw-practice"><header className="kw-learning-heading"><div><Button type="text" onClick={onBack}>返回原位置</Button><h2>{artifact.node_label} · 代码练习</h2><p>从当前节点和目标设计练习，修改代码、输入并观察真实结果。</p></div><Button onClick={()=>onNode?.(artifact.node_id)} disabled={!onNode}>定位图谱节点</Button></header>
  <LearningProgress key={nodeId} projectId={projectId} nodeId={nodeId}/>
  {error&&<Alert type="error" message="操作未完成" description={error}/>} {notice&&<p role="status" className="kw-muted">{notice}</p>}
  {artifact.stale&&<Alert type="warning" message="节点或来源已变化，保存的练习对应历史版本。请重新生成并核对。"/>}
  <section className="kw-practice-goal"><label>我想用代码理解什么<Input.TextArea aria-label="练习学习目标" value={goal} maxLength={1000} autoSize={{minRows:2,maxRows:5}} onChange={e=>setGoal(e.target.value)} disabled={busy}/></label>
   <label>学习深度<Select aria-label="练习难度" value={difficulty} onChange={setDifficulty} disabled={busy} options={Object.entries(difficultyLabels).map(([value,label])=>({value,label}))}/></label>
   <label>这次如何调整<Input aria-label="练习调整要求" value={adjustment} maxLength={1500} onChange={e=>setAdjustment(e.target.value)} disabled={busy} placeholder="例如：保留同一公式，增加一个极端输入和反例"/></label>
   <Button type="primary" loading={busy} disabled={running} onClick={()=>void generate()}>{artifact.status==='starter'?'按目标生成练习':'按目标调整练习'}</Button>
   <p className="kw-muted">生成会调用平台模型；改代码、改输入和运行均不调用模型。当前显示：{artifact.goal} · {difficultyLabels[artifact.difficulty]}</p>
  </section>
  <div className="kw-practice-version"><Tag>{artifact.status==='starter'?'可编辑起点 · 尚未生成专属练习':artifact.status==='ready'?'教学练习 · 尚非论文复现':'部分完成'}</Tag><label>保留的练习版本<Select aria-label="练习版本" value={artifact.id} onChange={id=>void switchVersion(id)} disabled={busy||running} options={artifact.versions.map((v,i)=>({value:v.id,label:`${i===0?'最新 · ':''}${v.title} · ${difficultyLabels[v.difficulty]} · ${new Date(v.created_at).toLocaleTimeString()}`}))}/></label></div>
  {!!artifact.errors.length&&<Alert type="info" message={artifact.errors.join('；')}/>}
  <section className="kw-practice-instructions"><h3>{artifact.title}</h3><KnowledgeText text={artifact.prompt}/>{artifact.expected_behavior.trim()&&<p><strong>预期观察：</strong>{artifact.expected_behavior}</p>}{artifact.simplifications.length>0&&<details><summary>教学假设与简化</summary><ul>{artifact.simplifications.map((text,i)=><li key={i}>{text}</li>)}</ul></details>}</section>
  <div className={'kw-practice-workspace'+(hasResult?'':' kw-practice-workspace-single')}><section className="kw-practice-editor"><label htmlFor="knowledge-practice-input">输入值（JSON）</label><textarea id="knowledge-practice-input" aria-label="练习输入 JSON" value={inputJson} spellCheck={false} onChange={e=>setInputJson(e.target.value)} disabled={running}/>
   <label htmlFor="knowledge-practice-code">Python 代码 <span className="kw-muted">Tab 插入缩进，Shift+Tab 移出编辑器</span></label><textarea id="knowledge-practice-code" className="learning-code-editor" aria-label="节点练习 Python 代码" value={code} spellCheck={false} disabled={running} onChange={e=>setCode(e.target.value)} onKeyDown={e=>{if(e.key==='Tab'&&!e.shiftKey){e.preventDefault();const input=e.currentTarget,start=input.selectionStart,end=input.selectionEnd;setCode(code.slice(0,start)+'    '+code.slice(end));requestAnimationFrame(()=>input.setSelectionRange(start+4,start+4))}}}/>
   <details className="kw-visual-help"><summary>让运行结果显示为图表</summary><p>在标准库 Python 中输出 PAPERSTRIDE_VISUAL: 加 JSON，可展示表格、折线、柱状或散点。点击下方按钮会在现有代码末尾追加一个线性缩放示例；这是通用教学示例，不是论文实验结果。</p><Button disabled={running||busy||code.includes("# PaperStride 通用绘图示例")} onClick={()=>{setCode(current=>current+VISUAL_EXAMPLE);setNotice('已追加绘图示例。可在 JSON 输入中添加 "visual_scale": 2，再运行观察曲线。')}}>追加可运行绘图示例</Button></details>
   <Space wrap><Button type="primary" disabled={running||busy} onClick={()=>run(false)}>运行代码</Button><Button disabled={running||busy||!artifact.test_code} onClick={()=>run(true)}>运行并检查示例</Button>{running&&<Button danger onClick={()=>runtime.current?.cancel()}>停止运行</Button>}<Button disabled={running||busy||!dirty} onClick={()=>void save()}>保存编辑稿</Button><Button type="text" disabled={running||busy} onClick={()=>{setCode(artifact.starter_code);setNotice('已恢复本版本起始代码，可继续编辑。')}}>恢复起始代码</Button></Space>
   <p className="kw-muted">{dirty?'编辑稿已保留在本浏览器，尚未保存到空间。':'当前编辑稿已保存。'} 支持 Python 标准库；第三方包与机器人接口未接入。初次运行从本机加载环境，执行 5 秒超时后终止。</p>
  </section>{hasResult&&<section className="kw-practice-result" aria-live="polite"><h3>{runLabels[runState]}</h3>{running&&<Spin size="small"/>}<PracticeVisuals output={output}/><p className="kw-muted">浏览器教学运行结果，未经独立实验核验。代码在隔离线程执行，不访问平台账号或机器人。</p>
   {artifact.runs.length>0&&<details><summary>最近运行记录（{artifact.runs.length}）</summary>{artifact.runs.map(run=><div key={run.id}><strong>{runLabels[run.status]} · {run.elapsed_ms} ms</strong><PracticeVisuals output={run.output}/></div>)}</details>}
  </section>}</div>
  {(!!artifact.hints.length||!!artifact.test_code.trim()||!!artifact.reference_code.trim()||!!artifact.evidence.length)&&<section className="kw-practice-support">{!!artifact.hints.length&&<><Button type="text" onClick={()=>setShowHints(v=>!v)} aria-expanded={showHints}>{showHints?'收起提示':'给我一点提示'}</Button>{showHints&&<ul>{artifact.hints.map((hint,i)=><li key={i}>{hint}</li>)}</ul>}</>}
   {artifact.test_code&&<details><summary>查看透明检查条件</summary><pre>{artifact.test_code}</pre></details>}{artifact.reference_code&&<details><summary>查看一种教学参考实现</summary><pre>{artifact.reference_code}</pre></details>}
   {!!artifact.evidence.length&&<details><summary>当前练习的原文依据（{artifact.evidence.length}）</summary><ul>{artifact.evidence.map(e=><li key={e.id}><Button type="link" disabled={!onEvidence} onClick={()=>onEvidence?.(e)}>{e.source_title} · {e.locator.page?`第 ${e.locator.page} 页`:e.locator.path||e.locator.heading||'来源段落'}</Button><blockquote>{e.quote}</blockquote></li>)}</ul></details>}
  </section>}
 </article>;
}
