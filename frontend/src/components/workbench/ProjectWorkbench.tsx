import {useEffect,useState} from 'react';
import {Alert,Button,Dropdown,Skeleton} from 'antd';
import {useSearchParams} from 'react-router-dom';
import {apiGet,apiPost} from '../../api/client';
import Notebook,{download} from './Notebook';

export default function ProjectWorkbench({projectId,workspace}:{projectId:string;workspace?:any}){
 const [loaded,setLoaded]=useState<any>(),[error,setError]=useState(''),[busy,setBusy]=useState(false),[revision,setRevision]=useState(0);
 const [,setParams]=useSearchParams();const data=workspace||loaded;
 useEffect(()=>{if(workspace!==undefined)return;const c=new AbortController();void apiGet<any>('/api/workbench/projects/'+projectId,undefined,c.signal).then(setLoaded).catch(e=>{if(!c.signal.aborted)setError(String(e))});return()=>c.abort()},[projectId,workspace]);
 const generate=async(type:string)=>{if(busy)return;setBusy(true);setError('');try{
  const d=await apiGet<any>('/api/workbench/projects/'+projectId);let text=`# ${d.project.title} — ${type}\n\n研究问题：${d.project.research_question||'待明确'}\n\n`;
  if(type==='文献对比表')text+='| 论文 | 年份 | 比较结论（待填写） |\n|---|---|---|\n'+d.papers.map((p:any)=>`| ${p.title.replaceAll('|','／')} | ${p.year||'未知'} | 待核对 |`).join('\n')+'\n\n';
  else text+='## 相关论文\n'+d.papers.map((p:any)=>`- ${p.title}（${p.year||'年份未知'}）\n  /research/${projectId}?tab=reading&paper=${encodeURIComponent(p.uid)}`).join('\n')+'\n\n';
  if(type==='组会提纲')text+='## 本次进展\n- 待根据研究记录填写。\n\n## 需要讨论的问题\n'+d.records.filter((r:any)=>r.kind==='question').map((r:any)=>'- '+r.title+': '+r.body).join('\n')+'\n\n';
  if(type==='实验记录')text+='## 实验条件\n- 数据集与版本：待填写\n- 方法与参数：待填写\n- 运行环境：待填写\n- 结果与局限：待填写\n\n';
  text+='## 已保存的研究记录\n'+d.records.filter((r:any)=>r.kind!=='draft'&&r.kind!=='report').map((r:any)=>`### ${r.title}\n${r.body}\n来源：${r.paper_uid||'用户记录'} ${r.source_json||''}`).join('\n\n')+'\n\n## 后续行动\n- 待补充结论、实验结果与下一步。\n';
  const record=await apiPost<any>('/api/workbench/records',{kind:type==='实验记录'?'experiment':'report',title:d.project.title+' · '+type,body:text,project_id:projectId});
  window.dispatchEvent(new Event('paperstride:records-change'));setRevision(v=>v+1);setParams(old=>{const next=new URLSearchParams(old);next.set('record',record.id);next.set('tab','outcomes');return next});
 }catch(e){setError(String(e))}finally{setBusy(false)}};
 if(!data&&!error)return <Skeleton active paragraph={{rows:4}}/>;
 return <section className="ps-outcomes-records"><div className="ps-outcome-actions"><Dropdown menu={{items:['阅读报告','文献对比表','组会提纲','实验记录'].map(type=>({key:type,label:type})),onClick:({key})=>void generate(key)}} trigger={['click']}><Button loading={busy}>从现有记录整理文稿</Button></Dropdown><Button type="text" onClick={async()=>{try{download('paperstride-project.json',JSON.stringify(await apiGet('/api/workbench/export',{project_id:projectId}),null,2),'application/json')}catch(e){setError(String(e))}}}>导出课题数据</Button></div>{error&&<Alert type="error" message={error}/>}
 <Notebook key={`${projectId}:${revision}`} projectId={projectId}/></section>;
}
