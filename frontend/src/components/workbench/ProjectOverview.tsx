import ProjectTopicPanel from "./ProjectTopicPanel";
import type {ResearchProject} from "../../api/project-types";
import {useEffect,useState} from 'react';
import {Alert,Button,Skeleton} from 'antd';
import {Link} from 'react-router-dom';
import {apiGet} from '../../api/client';

export default function ProjectOverview({projectId,workspace,onUpdated}:{projectId:string;workspace?:any;onUpdated?:(p:ResearchProject)=>void}){
 const [loaded,setLoaded]=useState<any>(),[error,setError]=useState(''),[topicOpen,setTopicOpen]=useState(false),[retry,setRetry]=useState(0);
 const data=workspace||loaded;
 useEffect(()=>{if(workspace!==undefined)return;const c=new AbortController();void apiGet<any>('/api/workbench/projects/'+projectId,undefined,c.signal).then(setLoaded).catch(e=>{if(!c.signal.aborted)setError(String(e))});return()=>c.abort()},[projectId,workspace,retry]);
 if(!data)return error?<Alert type="error" message={error} action={<Button onClick={()=>setRetry(v=>v+1)}>重试</Button>}/>:<Skeleton active paragraph={{rows:4}}/>;
 const project=data.project as ResearchProject;
 const questions=(data.records||[]).filter((r:any)=>r.kind==='question').slice(0,4);
 const recent=(data.records||[]).filter((r:any)=>r.kind!=='draft'&&r.kind!=='question').slice(0,4);
 const papers=data.papers||[];
 const recordUrl=(id:string)=>`/research/${projectId}?tab=outcomes&record=${encodeURIComponent(id)}`;
 return <section className="ps-project-overview">
  <section className="ps-research-question"><div className="ps-section-title"><h2>当前研究问题</h2><Button type="text" onClick={()=>setTopicOpen(v=>!v)}>{topicOpen?'收起方向编辑':'调整方向'}</Button></div><p>{project.research_question||'还没有明确的问题。可以先收集资料，记下你感到好奇或不理解的地方。'}</p>{project.constraints.objective&&<p className="ps-objective">当前目标：{project.constraints.objective}</p>}
  {topicOpen&&<ProjectTopicPanel project={project} onSaved={p=>{setLoaded({...data,project:p});onUpdated?.(p)}}/>}</section>
  <section className="ps-project-next"><div><h2>{papers.length?'接着读，找出下一个问题':'从一份资料开始'}</h2><p>{papers.length?papers[0].title:'添加与你的方向相关的论文，或先探索一个可能的研究问题。'}</p></div><Link className="home-action home-action-primary" to={papers.length?`/research/${projectId}?tab=reading&project=${projectId}`:`/manage?project=${projectId}&add=1`}>{papers.length?'继续阅读':'添加研究资料'}</Link></section>
  <div className="ps-overview-columns"><section><div className="ps-section-title"><h2>待解决问题</h2><Link to={`/research/${projectId}?tab=outcomes`}>查看记录</Link></div>{questions.length?<ul className="ps-record-preview">{questions.map((r:any)=><li key={r.id}><Link to={recordUrl(r.id)}>{r.title}</Link></li>)}</ul>:<p className="ps-empty-copy">阅读时选中文字，存为问题；这些线索会汇集在这里。</p>}</section>
  <section><div className="ps-section-title"><h2>近期进展</h2><Link to={`/research/${projectId}?tab=outcomes`}>全部成果</Link></div>{recent.length?<ul className="ps-record-preview">{recent.map((r:any)=><li key={r.id}><Link to={recordUrl(r.id)}>{r.title}</Link><span>{r.kind==='experiment'?'实验记录':r.kind==='report'?'报告':'笔记'}</span></li>)}</ul>:<p className="ps-empty-copy">保存的笔记、实验记录和报告会出现在这里。</p>}</section></div>
 </section>;
}
