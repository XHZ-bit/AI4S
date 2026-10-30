import {useEffect,useState} from 'react';
import {Alert,Button,Input,Segmented,Slider,Space,Skeleton} from 'antd';
import {Link,useSearchParams} from 'react-router-dom';
import {apiGet,apiPost} from '../../api/client';
import MathText from '../learning/MathText';
import CodePractice from '../learning/CodePractice';
import Quiz from '../learning/Quiz';
import type {Lesson} from '../learning/types';
import SyncedDraft from './SyncedDraft';
import {contextLink,safeReturnTo} from '../../api/workContext';
import '../../pages/learn.css';
import './diffusion-practice.css';

function Experiment({id}:{id:string}){
 const [value,setValue]=useState(50);
 const a=value/100;
 const points=Array.from({length:32},(_,i)=>{const x=i/31*6.28;const signal=Math.sin(x);const noise=Math.sin(i*13.7);return {x:12+i*12,y:85-55*(Math.sqrt(a)*signal+Math.sqrt(1-a)*noise)}});
 const window=Math.max(1,Math.round(value/10));
 return <section className="stride-experiment"><h4>改变条件，观察结果</h4><label>{id==='dp-1'?'左侧动作的概率':id==='dp-2'?'历史窗口长度':id==='dp-3'?'原信号保留系数 alpha':id==='dp-4'?'噪声预测的缩放比例':'本次执行动作数'}<Slider aria-label="实验参数" min={0} max={100} value={value} onChange={setValue}/></label>
 {id==='dp-1'?<><div className="stride-probability"><span style={{width:`${value}%`}}>左 {value}%</span><span>右 {100-value}%</span></div><p>左右动作设为 −1 与 +1，均值为 {(1-2*a).toFixed(2)}。50% 时均值是 0，但两种动作都不等于 0。</p></>:id==='dp-2'||id==='dp-5'?<><div className="stride-sequence" aria-label="时间序列">{Array.from({length:10},(_,i)=><span className={(id==='dp-2'?i>=10-window:i<window)?'selected':''} key={i}>{i}</span>)}</div><p>{id==='dp-2'?`当前索引 9，取最后 ${window} 个历史时刻。`:`预测 10 步，这次先执行 ${window} 步，再读取新的观测。`}</p></>:id==='dp-3'?<><svg viewBox="0 0 400 170" role="img" aria-label="固定信号加噪结果"><path d={'M'+points.map(p=>`${p.x},${p.y}`).join(' L')} fill="none" stroke="currentColor" strokeWidth="2"/></svg><p>alpha = {a.toFixed(2)}。曲线使用固定的示意噪声，便于对照；真实扩散训练使用采样的高斯噪声。</p></>:<><svg viewBox="0 0 400 140" role="img" aria-label="预测误差平方柱状图">{[1,-1,2,-2].map((v,i)=><rect key={i} x={30+i*95} y={125-(v-a*v)**2*25} width={45} height={(v-a*v)**2*25} fill="currentColor"/>)}</svg><p>真实噪声 [1,−1,2,−2]，预测为它的 {a.toFixed(2)} 倍；MSE = {(2.5*(1-a)**2).toFixed(3)}。</p></>}
 </section>;
}
export default function DiffusionPractice({projectId}:{projectId?:string}){
 const [params,setParams]=useSearchParams();
 projectId=projectId||params.get('project')||undefined;
 const persona=params.get('persona')==='generative'?'generative':'robotics';
 const [data,setData]=useState<any>(),[error,setError]=useState(''),[revision,setRevision]=useState(0),[reflection,setReflection]=useState(''),[saved,setSaved]=useState('');
 useEffect(()=>{const c=new AbortController();void apiGet<any>('/api/stride/curriculum',{project_id:projectId,persona},c.signal).then(r=>{setData(r);setError('')}).catch(e=>{if(!c.signal.aborted)setError(String(e))});return()=>c.abort()},[projectId,persona,revision]);
 const lessons=(data?.items||[]) as (Lesson&{sources:{url:string;title:string}[]})[];
 useEffect(()=>{setReflection('');setSaved('')},[params.get('unit'),projectId]);
 const selected=lessons.find(x=>x.id===params.get('unit'))||lessons[0];
 const flags=data?.features||{};
 const phases=[...(flags.foundations?[{value:'explain',label:'理解原理'}]:[]),...(flags.visuals?[{value:'visual',label:'预测与实验'}]:[]),...(flags.coding&&selected?.exercise?[{value:'code',label:'代码实践'}]:[]),...(flags.quizzes&&selected?.quiz.length?[{value:'quiz',label:'变式检查'}]:[]),{value:'reflect',label:'记录与回顾'}];
 const phase=phases.some(p=>p.value===params.get('activity'))?params.get('activity')!:phases[0].value;
 const step=Math.max(0,Math.min(Number(params.get('step'))||0,(selected?.steps.length||1)-1));
 const change=(values:Record<string,string|null>)=>setParams(old=>{const n=new URLSearchParams(old);Object.entries(values).forEach(([k,v])=>v===null?n.delete(k):n.set(k,v));if(projectId)n.set('project',projectId);return n});
 const nextPhase=phases[phases.findIndex(p=>p.value===phase)+1];
 const nextUnit=lessons[lessons.findIndex(l=>l.id===selected?.id)+1];
 const returnTo=safeReturnTo(params.get('returnTo'));
 return <section className="stride-practice"><header className="practice-heading">{returnTo&&<Link to={returnTo}>返回刚才的阅读</Link>}<h2>Diffusion Policy 实践</h2><p>从条件分布到动作序列，一次完成一个小实验。</p><details><summary>调整学习起点与查看参考实现</summary><Segmented aria-label="已有背景" value={persona} options={[{label:'机器人背景',value:'robotics'},{label:'生成模型背景',value:'generative'}]} onChange={v=>change({persona:String(v),unit:null,step:'0',activity:null})}/>{data&&<p>{data.recommendation}</p>}<Link to={contextLink('/cases/diffusion-policy-intro',params,{project:projectId})}>查看固定源码与一致性检查</Link></details></header>{error&&<Alert type="error" message={error} action={<Button onClick={()=>setRevision(v=>v+1)}>重试课程</Button>}/>} {!data&&!error&&<Skeleton active paragraph={{rows:6}}/>}
 {data&&!lessons.length&&<p>本课题学习支持已关闭，可继续阅读和研究规划。<Link to="/settings?tab=learning">调整个人偏好</Link></p>}
 <div className="stride-practice-layout"><nav aria-label="实践单元">{lessons.map(l=><button key={l.id} aria-current={selected?.id===l.id?'step':undefined} onClick={()=>change({unit:l.id,step:'0',activity:null})}><strong>{l.title}</strong><span>{data.checks.find((s:any)=>s.id===l.id)?.state}</span></button>)}</nav>{selected&&<article key={selected.id} className="practice-unit"><header><h3>{selected.title}</h3><p>{selected.summary}</p></header><Segmented aria-label="实践环节" value={phase} options={phases} onChange={v=>change({activity:String(v)})}/>
 {phase==='explain'&&selected.steps[step]&&<section className="practice-current-question"><p className="practice-step-count">问题 {step+1} / {selected.steps.length}</p><h4>{selected.steps[step].question}</h4><div className="learning-prose"><MathText text={selected.steps[step].explanation}/></div>{selected.steps[step].example&&<details className="practice-example"><summary>展开一个例子</summary><MathText text={selected.steps[step].example!}/></details>}<div className="practice-step-actions"><Button disabled={step===0} onClick={()=>change({step:String(step-1)})}>上一个问题</Button><Button type="primary" onClick={()=>step<selected.steps.length-1?change({step:String(step+1)}):nextPhase&&change({activity:nextPhase.value})}>{step<selected.steps.length-1?'下一个问题':nextPhase?.label||'回顾本节'}</Button></div></section>}
 {phase==='visual'&&flags.visuals&&<><p className="practice-predict-prompt">先预测：这个参数变大时，会怎样影响结果？再调整参数验证你的判断。</p><Experiment id={selected.id}/></>}
 {phase==='code'&&flags.coding&&selected.exercise&&<CodePractice key={selected.id+':'+projectId} exercise={selected.exercise} lessonId={selected.id} projectId={projectId} onRecord={()=>setRevision(v=>v+1)}/>}
 {phase==='quiz'&&flags.quizzes&&!!selected.quiz.length&&<Quiz key={selected.id} questions={selected.quiz} path={`/api/tutor/lessons/${selected.id}/quiz`} projectId={projectId} onRecord={()=>setRevision(v=>v+1)}/>}
 {phase==='reflect'&&<section><h4>保存实验解释</h4><Input.TextArea aria-label="课题实验解释" rows={6} value={reflection} onChange={e=>setReflection(e.target.value)} placeholder="我预测了什么，改变条件后发生了什么，还有哪些问题？"/><SyncedDraft key={selected.id+':'+projectId} identity={`paperstride:experiment:${projectId||'personal'}:${selected.id}`} title={selected.title+' · 实验解释'} value={reflection} onLoad={setReflection} projectId={projectId}/><Button onClick={async()=>{try{await apiPost('/api/workbench/records',{kind:'experiment',title:selected.title,body:reflection+'\n教学版本：'+data.version,project_id:projectId});setSaved('已加入课题实验记录')}catch(e){setError(String(e))}}} disabled={!reflection.trim()}>加入实验记录</Button>{saved&&<p role="status">{saved}</p>}<p className="learning-footnote">本轮通过表示完成这些教学检查；实验使用轻量合成数据。七天后提示复测。</p>{nextUnit?<Button onClick={()=>change({unit:nextUnit.id,step:'0',activity:null})}>下一个单元：{nextUnit.title}</Button>:projectId&&<Link to={`/research/${projectId}?tab=outcomes`}>整理研究方案</Link>}</section>}
 {phase!=='explain'&&nextPhase&&<div className="practice-step-actions"><Button type="primary" onClick={()=>change({activity:nextPhase.value})}>继续：{nextPhase.label}</Button>{returnTo&&<Link to={returnTo}>回到论文</Link>}</div>}
 <details className="practice-sources"><summary>来源与教学说明</summary><p>内容版本：{data.version}。公式经过教学整理；合成实验不代表论文结果或真实策略复现。</p>{selected.sources.map(s=><p key={s.url}><a href={s.url} target="_blank" rel="noreferrer">{s.title}</a></p>)}</details></article>}</div></section>;
}
