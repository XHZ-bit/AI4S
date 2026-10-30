import {useEffect,useState} from 'react';
import {Alert,Button,Input,Space} from 'antd';
import {apiGet,apiPost} from '../../api/client';
import SyncedDraft from './SyncedDraft';
import {download} from './Notebook';
import {Link} from 'react-router-dom';
export default function ResearchPlan({projectId}:{projectId:string}){
 const [plan,setPlan]=useState(''),[version,setVersion]=useState<number>(),[current,setCurrent]=useState<number>(),[error,setError]=useState(''),[notice,setNotice]=useState('');
 const [stage,setStage]=useState('validating');
 useEffect(()=>{void apiGet<any>('/api/projects/'+projectId).then(p=>{setCurrent(p.constraints.version);setStage(p.stage||'validating')}).catch(e=>setError(String(e)))},[projectId]);
 const prepare=async()=>{try{const r=await apiGet<any>(`/api/workbench/projects/${projectId}/next-experiment`);setPlan(r.markdown);setVersion(r.constraints_version)}catch(e){setError(String(e))}};
 return <section><h3>{stage==="validating"?"下一步验证实验":"保存探索进展"}</h3>{stage!=="validating"?<p>可以先保存观察、资料和候选问题。<Link to={`/research/${projectId}?tab=overview`}>返回概览探索方向</Link></p>:<p>根据当前条件整理最小实验，补充假设、评价方式与继续条件。尚未确认的资源保持未知。</p>}{error&&<Alert type="error" message={error}/>} {version!=null&&current!=null&&version!==current&&<Alert type="warning" message="课题约束已变化，请复核此实验草稿；已保存版本仍保留"/>}<Button onClick={()=>void prepare()}>{stage==="validating"?"按当前条件准备实验草稿":"准备探索记录"}</Button><Input.TextArea aria-label="研究实验方案" rows={18} value={plan} onChange={e=>setPlan(e.target.value)}/><SyncedDraft identity={`paperstride:plan:${projectId}`} title="下一步实验草稿" value={plan} onLoad={text=>{setPlan(text);const v=/约束版本：v(\d+)/.exec(text);if(v)setVersion(Number(v[1]))}} projectId={projectId}/><Space><Button disabled={!plan} onClick={async()=>{try{await apiPost('/api/workbench/records',{kind:'report',title:'首轮验证实验方案',body:plan,project_id:projectId});setNotice('已保存为独立成果记录')}catch(e){setError(String(e))}}}>保存方案版本</Button><Button disabled={!plan} onClick={()=>download('paperstride-experiment-plan.md',plan)}>导出方案</Button></Space>{notice&&<p role="status">{notice}</p>}</section>;
}
