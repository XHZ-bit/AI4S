import {useState} from "react";
import {Alert,Button,Radio} from "antd";
import {apiPost} from "../../api/client";
import MathText from "./MathText";
import type {LearningQuiz} from "./types";
export default function Quiz({questions,path,onRecord,projectId}:{projectId?:string;questions:LearningQuiz[];path:string;onRecord?:()=>void}){
 const [answers,setAnswers]=useState<Record<number,number>>({}),[results,setResults]=useState<Record<number,{correct:boolean;explanation:string}>>({}),[busy,setBusy]=useState<number>(),[error,setError]=useState("");
 return <section className="learning-quiz"><h3>停下来，检查一下理解</h3><p>先自己判断。答错后可以回到对应的小问题继续练习。</p>{questions.map((question,i)=><fieldset key={i}><legend><MathText text={question.question}/></legend><Radio.Group value={answers[i]} onChange={e=>{setAnswers(a=>({...a,[i]:e.target.value}));setResults(old=>{const next={...old};delete next[i];return next;});}}>{question.options.map((option,j)=><Radio key={j} value={j}><MathText text={option}/></Radio>)}</Radio.Group><Button disabled={answers[i]===undefined||busy!==undefined} loading={busy===i} onClick={async()=>{setBusy(i);setError("");try{const result=await apiPost<{correct:boolean;explanation:string}>(path,{question_index:i,answer:answers[i],project_id:projectId});setResults(r=>({...r,[i]:result}));onRecord?.();}catch(e){setError(String(e));}finally{setBusy(undefined);}}}>检查答案</Button>{results[i]&&<div role="status" className={`learning-feedback ${results[i].correct?"is-correct":"needs-review"}`}><strong>{results[i].correct?"这道题答对了":"再看一下推理过程"}</strong><p><MathText text={results[i].explanation}/></p></div>}</fieldset>)}{error&&<Alert type="error" message={error}/>}</section>;
}
