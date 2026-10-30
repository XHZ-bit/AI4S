import {useEffect,useState} from 'react';
import {Alert,Button,Input,Select,Space} from 'antd';
import type {ProjectStage,ResearchProject} from '../../api/project-types';
import {PROJECT_STAGES} from '../../api/project-types';
import {updateProject} from '../../api/projects';
import TopicExplorer from './TopicExplorer';
import {apiPost} from '../../api/client';

export default function ProjectTopicPanel({project,onSaved}:{project:ResearchProject;onSaved:(p:ResearchProject)=>void}){
 const [question,setQuestion]=useState(project.research_question),[objective,setObjective]=useState(project.constraints.objective),[stage,setStage]=useState<ProjectStage>(project.stage||'validating'),[open,setOpen]=useState(project.stage!=='validating'),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
 useEffect(()=>{setQuestion(project.research_question);setObjective(project.constraints.objective);setStage(project.stage||'validating')},[project.id,project.version]);
 return <section><Button onClick={()=>setOpen(v=>!v)}>{open?'收起选题探索':'继续探索或调整研究方向'}</Button>{open&&<><TopicExplorer project={project} initialInterest={project.custom_domain||project.title} onChoose={(d)=>{setQuestion(d.question);setStage('framing');setNotice('已载入暂拟问题，请改成自己的表述后保存。')}}/>
 <h3>把想法整理成自己的问题</h3><label>暂拟研究问题<Input.TextArea aria-label="暂拟研究问题" value={question} onChange={e=>setQuestion(e.target.value)} maxLength={4000} rows={3}/></label><label>当前目标<Input.TextArea aria-label="探索当前目标" value={objective} onChange={e=>setObjective(e.target.value)} maxLength={4000} rows={2}/></label>
 <Space wrap style={{marginTop:16}}><Select aria-label="当前研究阶段" value={stage} onChange={setStage} options={Object.entries(PROJECT_STAGES).map(([value,label])=>({value,label}))}/><Button type="primary" loading={busy} onClick={async()=>{if(stage==='validating'&&(!question.trim()||!objective.trim())){setError('验证阶段需要明确问题和目标；也可以继续探索。');return}setBusy(true);setError('');try{const saved=await updateProject(project.id,{expected_version:project.version,title:null,research_question:question,stage,status:null,constraints:{...project.constraints,objective,version:project.constraints.version+1}});onSaved(saved);setNotice('方向已保存为新的课题版本，之前的方案仍保留。')}catch(e){setError(String(e))}finally{setBusy(false)}}}>保存方向与阶段</Button><Button disabled={!question.trim()} onClick={async()=>{try{await apiPost('/api/workbench/records',{kind:'question',title:'选题候选：'+question.slice(0,80),body:question,project_id:project.id});window.dispatchEvent(new Event('paperstride:records-change'));setNotice('已作为候选问题保存，可保留多个想法再比较。')}catch(e){setError(String(e))}}}>先存为候选，不改课题</Button></Space>
 {error&&<Alert type="error" message={error}/ >}{notice&&<p role="status">{notice}</p>}</>}</section>;
}
