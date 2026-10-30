import {useEffect,useRef,useState} from 'react';
import {Button,Input} from 'antd';
import type {KnowledgeEvidence} from '../../api/knowledge';
import {askKnowledgeNode,type NodeAnswer} from '../../api/knowledgeExperience';
import KnowledgeText from './KnowledgeText';
import './knowledge-experience.css';

export default function NodeQuestion({projectId,nodeId,onEvidence,onNode}:{projectId:string;nodeId:string;onEvidence?:(e:KnowledgeEvidence)=>void;onNode?:(id:string)=>void}){
 const [question,setQuestion]=useState(''),[answer,setAnswer]=useState<NodeAnswer>(),[busy,setBusy]=useState(false),[error,setError]=useState('');const controller=useRef<AbortController>();
 useEffect(()=>{controller.current?.abort();setQuestion('');setAnswer(undefined);setError('');setBusy(false);return()=>controller.current?.abort()},[projectId,nodeId]);
 async function ask(){if(busy||!question.trim())return;controller.current?.abort();const c=new AbortController();controller.current=c;setBusy(true);setError('');try{const result=await askKnowledgeNode(projectId,nodeId,question.trim(),c.signal);if(!c.signal.aborted)setAnswer(result)}catch(e){if(!c.signal.aborted)setError(String(e))}finally{if(!c.signal.aborted)setBusy(false)}}
 return <section className="kw-node-question" aria-label="围绕当前知识提问"><label>针对当前节点提问<Input.TextArea aria-label="节点问题" value={question} maxLength={1500} onChange={e=>setQuestion(e.target.value)} autoSize={{minRows:2,maxRows:6}} placeholder="例如：这一步为什么需要前置条件？原文在哪？"/></label><div className="kw-question-actions"><Button disabled={!question.trim()||busy} loading={busy} onClick={()=>void ask()}>结合图谱与原文回答</Button>{busy&&<Button onClick={()=>{controller.current?.abort();setBusy(false)}}>停止等待</Button>}</div><small>围绕当前空间的节点、关联关系与来源检索；已配置模型时按平台预算生成回答。</small>{error&&<p role="alert">回答未完成：{error}</p>}{answer&&<div className="kw-node-answer"><p className="kw-muted">{answer.model_used?'基于所列来源的模型回答':'已保存来源检索结果'}</p><KnowledgeText text={answer.answer}/>{answer.warnings?.map((warning,i)=><p key={i} role="note">{warning}</p>)}{!!answer.citations?.length&&<ol className="kw-answer-citations">{answer.citations.map((e,i)=><li key={e.id}><button disabled={!onEvidence} onClick={()=>onEvidence?.(e)}>{i+1}. {e.source_title} · {e.locator?.page?`第 ${e.locator.page} 页`:e.locator?.heading||'来源片段'}</button><blockquote>{e.quote}</blockquote></li>)}</ol>}{onNode&&answer.node_ids?.some(id=>id!==nodeId)&&<details><summary>查看回答涉及的图谱节点</summary>{answer.node_ids.filter(id=>id!==nodeId).map((id,i)=><button key={id} onClick={()=>onNode(id)}>定位关联节点 {i+1}</button>)}</details>}</div>}</section>;
}
