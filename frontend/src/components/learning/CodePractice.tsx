import SyncedDraft from "../workbench/SyncedDraft";
import {useSearchParams} from "react-router-dom";
import {useEffect,useRef,useState} from "react";
import {Alert,Button} from "antd";
import {apiPost} from "../../api/client";
import type {Exercise} from "./types";
export default function CodePractice({exercise,lessonId,onRecord,session=false,projectId}:{projectId?:string;session?:boolean;exercise:Exercise;lessonId:string;onRecord:()=>void}){
 const [params]=useSearchParams();
 const scope=projectId||params.get("project")||undefined;
 const key=scope?`atlas:code:${scope}:${lessonId}:${exercise.id}`:`atlas:code:${lessonId}:${exercise.id}`;
 const [code,setCode]=useState(()=>{try{return localStorage.getItem(key)||exercise.starter;}catch{return exercise.starter;}}),[busy,setBusy]=useState(false),[output,setOutput]=useState(""),[state,setState]=useState("idle"),[hint,setHint]=useState(false),[error,setError]=useState("");
 const [prediction,setPrediction]=useState(""),[reflection,setReflection]=useState("");
 const worker=useRef<HTMLIFrameElement>(),listener=useRef<(event:MessageEvent)=>void>(),timer=useRef<ReturnType<typeof setTimeout>>();
 const stop=()=>{worker.current?.remove();worker.current=undefined;if(listener.current)window.removeEventListener("message",listener.current);listener.current=undefined;clearTimeout(timer.current);setBusy(false);};
 useEffect(()=>()=>{worker.current?.remove();if(listener.current)window.removeEventListener("message",listener.current);clearTimeout(timer.current);},[]);
 useEffect(()=>{try{const saved=JSON.parse(localStorage.getItem(`${key}:reflection`)||"{}");setPrediction(saved.prediction||"");setReflection(saved.reflection||"");}catch{}},[key]);
 useEffect(()=>{try{localStorage.setItem(key,code);}catch{}},[code,key]);
 const run=(check:boolean)=>{
  stop();setBusy(true);setState("loading");setOutput("首次运行正在加载本地 Python 环境…");setError("");
  const current=document.createElement("iframe");current.setAttribute("sandbox","allow-scripts");current.title="隔离的 Python 运行环境";current.hidden=true;current.src="/python-frame.html";worker.current=current;
  timer.current=setTimeout(()=>{stop();setState("failed");setOutput("Python 环境加载超时，请重试。首次加载需要下载约 14MB 本地运行文件。");},45000);
  listener.current=async event=>{
   if(worker.current!==current||event.source!==current.contentWindow||!event.data||!["ready","result","error"].includes(event.data.type))return;
   if(event.data.type==="ready"){
    clearTimeout(timer.current);setState("running");setOutput("正在运行…");
    timer.current=setTimeout(()=>{stop();setState("failed");setOutput("运行超过 5 秒，已停止。请检查无限循环或缩小输入。");},5000);
    current.contentWindow?.postMessage({type:"execute",code,tests:check?exercise.tests:""},"*");return;
   }
   const result=event.data;stop();setOutput(result.output);setState(result.type==="error"?"failed":check?(result.passed?"passed":"failed"):"ran");
   if(result.type==="result"&&check)try{await apiPost(`/api/tutor/${session?"sessions":"lessons"}/${lessonId}/practice`,{project_id:scope,exercise_id:exercise.id,code,passed:result.passed,output:String(result.output).slice(0,4000)});onRecord();}catch(e){setError("代码已检查，但记录未保存："+String(e));}
  };
  window.addEventListener("message",listener.current);document.body.appendChild(current);
 };
 return <section className="code-practice"><header><h3>{exercise.title} <span className="code-practice-kind">{exercise.kind}</span></h3></header><p>{exercise.prompt}</p><details open><summary>先预测，再运行</summary><label>写下预期输出或输入输出形状<textarea aria-label="代码运行预测" value={prediction} onChange={e=>setPrediction(e.target.value)} /></label><p>先阅读输入和返回值，补全或修复代码，再运行比较。检查通过后，修改一个边界输入，观察结果是否符合预期。</p></details><label className="learning-code-label" htmlFor={`code-${lessonId}`}>Python 代码 <span className="learning-footnote">Tab 缩进，Shift+Tab 离开编辑器</span></label><textarea aria-label="Python 代码" id={`code-${lessonId}`} className="learning-code-editor" value={code} spellCheck={false} disabled={busy} onChange={e=>setCode(e.target.value)} onKeyDown={e=>{if(e.key==="Tab"&&!e.shiftKey){e.preventDefault();const editor=e.currentTarget,start=editor.selectionStart,end=editor.selectionEnd;setCode(code.slice(0,start)+"    "+code.slice(end));requestAnimationFrame(()=>{editor.setSelectionRange(start+4,start+4);});}}}/><SyncedDraft identity={scope?`code:${scope}:${lessonId}:${exercise.id}`:`code:${lessonId}:${exercise.id}`} title={exercise.title} value={code} onLoad={setCode} projectId={scope}/><div className="learning-code-actions"><Button type="primary" disabled={busy} onClick={()=>run(true)}>运行并检查</Button><Button disabled={busy} onClick={()=>run(false)}>仅运行</Button>{busy&&<Button onClick={()=>{stop();setState("idle");setOutput("已停止，代码已保留。");}}>停止运行</Button>}<Button type="text" onClick={()=>setHint(v=>!v)} aria-expanded={hint}>给我一点提示</Button><Button type="text" disabled={busy} onClick={()=>setCode(exercise.starter)}>重置代码</Button></div>{hint&&<p className="learning-hint">{exercise.hint}</p>}
 <div className={`learning-console ${state}`} aria-live="polite"><strong>{state==="passed"?`${exercise.test_count} 项示例检查通过`:busy?"运行中":state==="failed"?"需要调整":"运行输出"}</strong><pre>{output||"修改代码后运行，查看真实输出和检查反馈。"}</pre></div>{error&&<Alert type="error" message={error}/>}<details><summary>实验与解释</summary><label>改变输入后发生了什么？这说明了什么？<textarea aria-label="代码实验解释" value={reflection} onChange={e=>setReflection(e.target.value)}/></label><SyncedDraft identity={scope?`reflection:${scope}:${lessonId}:${exercise.id}`:`reflection:${lessonId}:${exercise.id}`} title={exercise.title+" · 实验解释"} value={reflection} onLoad={setReflection} projectId={scope}/><Button onClick={()=>{try{localStorage.setItem(`${key}:reflection`,JSON.stringify({prediction,reflection}));setError("学习笔记已保存到当前浏览器。");}catch{setError("浏览器无法保存笔记。");}}}>保存实验笔记</Button></details><details><summary>查看检查条件</summary><pre>{exercise.tests}</pre></details><details><summary>查看一种参考实现</summary><pre>{exercise.solution}</pre></details><p className="learning-footnote">代码在浏览器独立线程中运行，5 秒超时可停止。通过示例检查不等于完成论文复现；记录标注为浏览器练习结果。</p></section>;
}
