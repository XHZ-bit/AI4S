import {useEffect,useRef,useState} from 'react';
import {Alert,Button,Input,Space} from 'antd';
import {Link} from 'react-router-dom';
import {apiGet,apiPost} from '../../api/client';
import type {ResearchProject} from '../../api/project-types';
import SyncedDraft from './SyncedDraft';
import {usePreferences} from '../PreferencesContext';
import './topic-explorer.css';

export type TopicDirection={id:string;title:string;question:string;why:string;first_step:string;needed:string;paper_uids:string[]};
type Report={brief:{interests:string;background:string;resources:string};directions:TopicDirection[];papers:{uid:string;title:string;reason:string;url:string}[];notice:string;search_url:string};
export default function TopicExplorer({project,onChoose,initialInterest=''}:{project?:ResearchProject;initialInterest?:string;onChoose:(direction:TopicDirection,brief:{interests:string;background:string;resources:string})=>void}){
 const {preferences}=usePreferences();const [guidance,setGuidance]=useState(true);
 const [interests,setInterests]=useState(initialInterest),[background,setBackground]=useState(''),[resources,setResources]=useState(''),[report,setReport]=useState<Report>(),[busy,setBusy]=useState(false),[error,setError]=useState(''),[selected,setSelected]=useState('');
 const [papers,setPapers]=useState<{uid:string;title:string}[]>([]);
 useEffect(()=>{if(project)void apiGet<any>('/api/workbench/projects/'+project.id).then(r=>{setPapers(r.papers||[]);setGuidance(r.features?.paper_guidance!==false)}).catch(()=>{})},[project?.id]);
 const brief={interests,background,resources};const signature=JSON.stringify({...brief,project:project?.id});const latest=useRef(signature);latest.current=signature;
 useEffect(()=>{setReport(undefined);setSelected('')},[interests,background,resources,project?.id]);
 return <section className="topic-explorer" aria-label="研究方向探索"><h3>还没想好课题，从好奇的问题开始</h3><p>写一个关键词、困惑或应用场景就可以；也可以直接从已有资料里寻找线索。</p>
 <div className="topic-brief"><label>想了解的方向或现象<Input.TextArea aria-label="探索兴趣" placeholder="例如：怎样改善课堂参与、人如何与机器人协作，或任何你想弄懂的现象" value={interests} onChange={e=>setInterests(e.target.value)} maxLength={1500} autoSize={{minRows:2,maxRows:5}}/></label>
 <details><summary>补充我的基础和可用资源（可选）</summary><label>已经了解什么<Input.TextArea aria-label="已有基础" value={background} onChange={e=>setBackground(e.target.value)} maxLength={1500} placeholder="用日常语言描述即可，例如：学过 Python，还没接触这个领域"/></label><label>可以使用什么<Input.TextArea aria-label="探索可用资源" value={resources} onChange={e=>setResources(e.target.value)} maxLength={1500} placeholder="时间、数据、工具；不知道的可以留空"/></label></details></div>
 {project&&<SyncedDraft identity={'paperstride:topic-brief:'+project.id} title="选题探索草稿" projectId={project.id} value={JSON.stringify(brief)} onLoad={raw=>{try{const v=JSON.parse(raw);setInterests(v.interests||'');setBackground(v.background||'');setResources(v.resources||'')}catch{}}}/>}
 <Button loading={busy} onClick={async()=>{setBusy(true);setError('');try{const snapshot=signature;const result=await apiPost<Report>('/api/workbench/topic-exploration',{...brief,project_id:project?.id});if(latest.current!==snapshot){setError('输入已改变，请重新展开方向。');return}setReport(result);setSelected('')}catch(e){setError(String(e))}finally{setBusy(false)}}}>{interests.trim()?'帮我展开几个可探索的方向':'从已有资料寻找线索'}</Button>
 {error&&<Alert type="error" message={error}/ >}
 {guidance&&preferences.features.paper_guidance&&<p><Link to={'/learn?view=tutor'+(project?'&project='+encodeURIComponent(project.id):'')+'&question='+encodeURIComponent('请作为科研选题教练，先问我三个澄清问题，逐步帮助我找到方向，先不要锁定具体题目。兴趣：'+(interests.slice(0,450)||'暂未确定')+'；已有基础：'+(background.slice(0,450)||'暂未说明')+'；可用资源：'+(resources.slice(0,450)||'未知')+'。先整理不同可能，再讨论如何寻找论文与验证；不把推测说成研究空白。')}>请导师一起梳理思路</Link><span className="topic-muted"> · 打开后由你发送，使用当前辅导模型。</span></p>}
 {report&&<><p className="topic-notice">{report.notice}</p><div className="topic-directions">{report.directions.map((d,i)=><article key={d.id} className={selected===d.id?'is-selected':''}><h4>{d.title}</h4><p>{d.question}</p><p className="topic-muted">{d.why}</p><details open={i===0}><summary>先做什么，需要什么</summary><p>{d.first_step}</p><p>{d.needed}</p></details><Button onClick={()=>{setSelected(d.id);onChoose(d,report.brief)}}>{selected===d.id?'已采用，可继续修改':'以此为起点，继续修改'}</Button></article>)}</div>
 <h4>可以先看的资料</h4>{report.papers.length?<ul>{report.papers.map(p=><li key={p.uid}><Link to={project&&papers.some(x=>x.uid===p.uid)?`/research/${project.id}?tab=reading&project=${project.id}&paper=${encodeURIComponent(p.uid)}`:p.url}>{p.title}</Link><p className="topic-muted">{p.reason}</p>{project&&!papers.some(x=>x.uid===p.uid)&&<Button size="small" onClick={async()=>{try{await apiPost('/api/workbench/projects/'+project.id+'/papers',{paper_uid:p.uid});setPapers(old=>[...old,{uid:p.uid,title:p.title}])}catch(e){setError(String(e))}}}>关联到本课题</Button>}</li>)}</ul>:<p>本地资料还没有匹配内容。先查找一篇综述或入门论文，再回来比较方向。</p>}<Link to={report.search_url}>带着这些关键词去找资料</Link></>}
 </section>;
}
