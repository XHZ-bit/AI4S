import {useEffect,useRef,useState} from 'react';
import {Button,Input} from 'antd';
import type {KnowledgeEvidence} from '../../api/knowledge';
import {askKnowledgeNode,type NodeAnswer} from '../../api/knowledgeExperience';
import KnowledgeText from './KnowledgeText';
import EvidenceQuote from './EvidenceQuote';
import './knowledge-experience.css';
import './node-question-guidance.css';

const questionStarters=[
 {label:'通俗讲解',question:'请用初学者能理解的语言解释当前知识，给出一个简单例子，并区分原文依据与你的推断。'},
 {label:'补充基础',question:'理解当前知识需要哪些前置基础？请结合图谱已有的前置节点安排补学顺序，缺少的基础请明确说明。'},
 {label:'代码思路',question:'请结合当前知识说明一个适合初学者的最小代码练习，解释输入、输出和实现思路，并指出需要核对的假设。'},
 {label:'核对原文',question:'当前知识的关键结论分别来自哪些原文片段？哪些内容还缺少可靠依据？'},
];
const answerMechanismNotes=new Set(['当前展示节点及原文摘录，尚未生成针对问题的解释。']);

export default function NodeQuestion({projectId,nodeId,onEvidence,onNode,onSaveAnswer}:{projectId:string;nodeId:string;onEvidence?:(e:KnowledgeEvidence)=>void;onNode?:(id:string)=>void;onSaveAnswer?:(text:string,evidence?:KnowledgeEvidence[])=>void}){
 const [question,setQuestion]=useState(''),[answerQuestion,setAnswerQuestion]=useState(''),[answer,setAnswer]=useState<NodeAnswer>(),[busy,setBusy]=useState(false),[error,setError]=useState('');const controller=useRef<AbortController>();
 useEffect(()=>{controller.current?.abort();setQuestion('');setAnswerQuestion('');setAnswer(undefined);setError('');setBusy(false);return()=>controller.current?.abort()},[projectId,nodeId]);
 async function ask(){if(busy||!question.trim())return;controller.current?.abort();const c=new AbortController();controller.current=c;setBusy(true);setError('');const asked=question.trim();try{const result=await askKnowledgeNode(projectId,nodeId,asked,c.signal);if(!c.signal.aborted){setAnswer(result);setAnswerQuestion(asked)}}catch(e){if(!c.signal.aborted)setError(String(e))}finally{if(!c.signal.aborted)setBusy(false)}}
 const mechanismNotes=answer?.warnings?.filter(warning=>!answer.model_used&&answerMechanismNotes.has(warning))||[];
 const importantWarnings=answer?.warnings?.filter(warning=>answer.model_used||!answerMechanismNotes.has(warning))||[];
 return <section className="kw-node-question" aria-label="围绕当前知识提问">
  <label>针对当前节点提问<Input.TextArea aria-label="节点问题" value={question} maxLength={1500} onChange={e=>setQuestion(e.target.value)} autoSize={{minRows:2,maxRows:6}} placeholder="例如：这一步为什么需要前置条件？原文在哪？"/></label>
  <div className="kw-question-starters" role="group" aria-label="选择提问方向">{questionStarters.map(item=><Button key={item.label} size="small" disabled={busy} onClick={()=>setQuestion(item.question)}>{item.label}</Button>)}</div>
  <div className="kw-question-actions"><Button disabled={!question.trim()||busy} loading={busy} onClick={()=>void ask()}>结合图谱与原文回答</Button>{busy&&<Button onClick={()=>{controller.current?.abort();setBusy(false)}}>停止等待</Button>}</div>
  {error&&<p role="alert">回答未完成：{error}</p>}
  {answer&&<div className="kw-node-answer">
   <p className="kw-muted">{answer.model_used?'AI 辅助回答':answer.origin==='source'?'原文摘录':'已保存内容摘录'}</p>
   <KnowledgeText text={answer.answer}/>
   {onSaveAnswer&&<Button size="small" disabled={busy} onClick={()=>onSaveAnswer('### 问题\n'+answerQuestion+'\n\n### 问答摘录\n'+answer.answer+'\n\n'+answer.citations.map(e=>'来源：'+e.source_title+(e.locator.page?' · 第 '+e.locator.page+' 页':'')).join('\n'),answer.citations)}>选入笔记</Button>}
   {importantWarnings.map((warning,i)=><p key={i} role="note">{warning}</p>)}
   {!!answer.citations?.length&&<ol className="kw-answer-citations">{answer.citations.map((e,i)=><li key={e.id}><button disabled={!onEvidence} onClick={()=>onEvidence?.(e)}>{i+1}. {e.source_title} · {e.locator?.page?`第 ${e.locator.page} 页`:e.locator?.heading||'来源片段'}</button><blockquote><EvidenceQuote evidence={e}/></blockquote></li>)}</ol>}
   {onNode&&answer.node_ids?.some(id=>id!==nodeId)&&<details><summary>查看回答涉及的图谱节点</summary>{answer.node_ids.filter(id=>id!==nodeId).map((id,i)=><button key={id} onClick={()=>onNode(id)}>定位关联节点 {i+1}</button>)}</details>}
  </div>}
  <details className="kw-answer-info"><summary>回答说明</summary><p>围绕当前空间的节点、关联关系与来源检索；已配置模型时按平台预算生成回答。</p>{mechanismNotes.map((note,i)=><p key={i}>{note}</p>)}</details>
 </section>;
}
