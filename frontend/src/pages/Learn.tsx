import {useEffect,useState} from "react";
import {Alert,Button,Segmented,Skeleton} from "antd";
import {Link,Navigate,useSearchParams} from "react-router-dom";
import {apiGet} from "../api/client";
import {contextLink,safeReturnTo} from "../api/workContext";
import {usePreferences} from "../components/PreferencesContext";
import TutorChat from "../components/learning/TutorChat";
import Quiz from "../components/learning/Quiz";
import MathText from "../components/learning/MathText";
import CodePractice from "../components/learning/CodePractice";
import ConceptVisual from "../components/learning/ConceptVisual";
import type {Lesson} from "../components/learning/types";
import "./learn.css";
interface Attempt {lesson_id:string;exercise_id:string;kind:string;created_at:string;result:{correct?:boolean;passed?:boolean}}
export function projectPracticeTarget(params:URLSearchParams){
 const project=params.get('project'),view=params.get('view');
 if(!project||!(['foundations','coding','code','practice'].includes(view||'')||params.get('activity')==='code'))return undefined;
 const previous=safeReturnTo(params.get('returnTo'));
 const original=previous?new URL(previous,'http://paperstride.local').searchParams:new URLSearchParams();
 const target=new URLSearchParams({view:'practice'});
 for(const key of ['node','source','paper'] as const){const value=params.get(key)||original.get(key);if(value)target.set(key,value)}
 if(previous)target.set('returnTo',previous);
 return '/research/'+encodeURIComponent(project)+'?'+target;
}
export default function Learn(){
 const [params]=useSearchParams();const target=projectPracticeTarget(params);
 return target?<Navigate to={target} replace/>:<LearningLibrary/>;
}
function LearningLibrary(){
 const {preferences,loading:preferencesLoading}=usePreferences();
 const [params,setParams]=useSearchParams();const projectId=params.get("project")||undefined;
 const [projectFeatures,setProjectFeatures]=useState<Record<string,boolean>>({});
 const [featuresReady,setFeaturesReady]=useState(!projectId);
 const f=Object.fromEntries(Object.entries(preferences.features).map(([k,v])=>[k,v&&projectFeatures[k]!==false])) as typeof preferences.features;
 const [lessons,setLessons]=useState<Lesson[]>([]),[attempts,setAttempts]=useState<Attempt[]>([]),[loading,setLoading]=useState(true),[error,setError]=useState(""),[revision,setRevision]=useState(0);
 useEffect(()=>{const c=new AbortController();setProjectFeatures({});setFeaturesReady(!projectId);if(projectId)apiGet<any>(`/api/workbench/projects/${encodeURIComponent(projectId)}`,undefined,c.signal).then(r=>{if(!c.signal.aborted){setProjectFeatures(r.features);setFeaturesReady(true)}}).catch(e=>{if(!c.signal.aborted)setError(String(e))});return()=>c.abort()},[projectId]);
 const courses=f.foundations||f.quizzes||f.coding;
 const requestedView=params.get("view");
 const view=requestedView==="foundations"&&courses?"foundations":requestedView==="tutor"&&f.paper_guidance?"tutor":f.paper_guidance?"tutor":"foundations";
 useEffect(()=>{if(!courses||preferencesLoading||!featuresReady||view==="tutor"){setLoading(false);return;}const c=new AbortController();setLoading(true);apiGet<{items:Lesson[];attempts:Attempt[]}>("/api/tutor/lessons",undefined,c.signal).then(data=>{if(!c.signal.aborted){setLessons(data.items);setAttempts(data.attempts);setError("");}}).catch(e=>{if(!c.signal.aborted)setError(String(e));}).finally(()=>{if(!c.signal.aborted)setLoading(false);});return()=>c.abort();},[courses,featuresReady,view,f.quizzes,f.coding,f.glossary,f.visuals,preferencesLoading,revision]);
 const selected=lessons.find(item=>item.id===params.get("lesson"))||lessons[0];
 const activities=[...(f.foundations?[{value:"explain",label:"理解概念"}]:[]),...(selected?.visual&&f.visuals?[{value:"visual",label:"观察与预测"}]:[]),...(f.quizzes&&selected?.quiz.length?[{value:"quiz",label:"理解检查"}]:[]),...(f.coding&&selected?.exercise?[{value:"code",label:"代码实践"}]:[])];
 const activity=activities.some(a=>a.value===params.get("activity"))?params.get("activity")!:activities[0]?.value;
 const step=Math.max(0,Math.min(Number(params.get("step"))||0,(selected?.steps.length||1)-1));
 const change=(values:Record<string,string|null>)=>setParams(old=>{const n=new URLSearchParams(old);Object.entries(values).forEach(([k,v])=>v===null?n.delete(k):n.set(k,v));return n});
 const select=(lesson:string)=>change({lesson,view:"foundations",activity:null,step:"0"});
 const returnTo=safeReturnTo(params.get("returnTo"))||(projectId?contextLink(`/research/${encodeURIComponent(projectId)}?tab=reading`,params):params.get("paper")?contextLink(`/papers/${encodeURIComponent(params.get("paper")!)}?tab=reading`,params):undefined);
 const nextActivity=activities[activities.findIndex(a=>a.value===activity)+1];
 if(!featuresReady)return <section className="learning-page">{error?<Alert type="error" message="无法读取课题学习偏好" description={error} action={<Button onClick={()=>window.location.reload()}>重试</Button>}/>:<Skeleton active paragraph={{rows:5}}/>}</section>;
 if(!courses&&!f.paper_guidance)return <section className="learning-page"><h1>学习功能已关闭</h1><p>你可以继续梳理论文关系与规划科研方向。</p><Link to="/settings?tab=learning">调整学习功能</Link></section>;
 return <div className="learning-page"><header className="learning-heading"><div>{returnTo&&<Link className="learning-return" to={returnTo}>返回刚才的阅读</Link>}<h1>理解与实践</h1><p>围绕当前问题，按需要补充知识。</p></div><Link to="/settings?tab=learning">学习偏好</Link></header>
 <Segmented className="learning-view-picker" aria-label="学习方式" value={view} options={[...(f.paper_guidance?[{value:"tutor",label:"随文辅导"}]:[]),...(courses?[{value:"foundations",label:"基础与代码练习"}]:[])]} onChange={value=>change({view:String(value)})}/>
 {view==="tutor"&&f.paper_guidance?<TutorChat key={`${params.get("paper")}:${params.get("passage")}`} paperUid={params.get("paper")||undefined} passageId={params.get("passage")||undefined} initialQuestion={params.get("question")||""}/>:courses&&<div className="learning-course-layout"><aside className="learning-course-list"><h2>基础课程</h2><nav aria-label="基础课程">{lessons.map(lesson=><button key={lesson.id} aria-current={selected?.id===lesson.id?"page":undefined} onClick={()=>select(lesson.id)}><strong>{lesson.title}</strong><span>约 {lesson.minutes} 分钟{attempts.some(a=>a.lesson_id===lesson.id)?" · 有练习记录":""}</span></button>)}</nav></aside>
 <section className="learning-course-main">{error&&<Alert type="error" message={error} action={<Button onClick={()=>setRevision(v=>v+1)}>重试</Button>}/>} {loading&&!selected&&<Skeleton active paragraph={{rows:8}}/>}{!loading&&!selected&&!error&&<div className="learning-empty"><h2>暂时没有可用课程</h2><p>你可以回到论文继续阅读，或稍后重新加载课程。</p><Button onClick={()=>setRevision(v=>v+1)}>重新加载</Button>{returnTo&&<Link to={returnTo}>返回阅读</Link>}</div>}{selected&&<><header><h2>{selected.title}</h2><p>{selected.summary}</p><details className="learning-context-details"><summary>为什么需要它 · 建议基础</summary><p>{selected.connection}</p>{!!selected.prerequisites.length&&f.foundations&&<div className="learning-prerequisite-links">建议先看：{selected.prerequisites.map(id=><button key={id} onClick={()=>select(id)}>{lessons.find(item=>item.id===id)?.title||id}</button>)}</div>}</details></header>
 {!!activities.length&&<Segmented className="learning-activity-picker" aria-label="本节学习环节" value={activity} onChange={v=>change({activity:String(v)})} options={activities}/>}
 {activity==="explain"&&selected.steps[step]&&<section className="learning-explanation"><details className="learning-step-index"><summary>问题 {step+1} / {selected.steps.length} · 查看本节问题</summary><nav className="tutor-step-nav" aria-label="课程小问题">{selected.steps.map((item,i)=><button key={i} aria-current={step===i?"step":undefined} onClick={()=>change({step:String(i)})}><span>{i+1}</span>{item.question}</button>)}</nav></details><article><h3>{selected.steps[step].question}</h3><div className="learning-prose"><MathText text={selected.steps[step].explanation}/></div>{selected.steps[step].example&&<details className="learning-example"><summary>看一个例子</summary><p><MathText text={selected.steps[step].example!}/></p></details>}<div className="tutor-step-actions"><Button disabled={step===0} onClick={()=>change({step:String(step-1)})}>上一个问题</Button><span>{step+1} / {selected.steps.length}</span><Button type="primary" onClick={()=>{if(step<selected.steps.length-1)change({step:String(step+1)});else if(nextActivity)change({activity:nextActivity.value});else change({step:"0"});}}>{step<selected.steps.length-1?"下一个问题":nextActivity?nextActivity.label:"回顾本节"}</Button></div>{f.paper_guidance&&<Link to={contextLink('/learn',params,{view:'tutor',question:`我不理解${selected.steps[step].question}，请从基础解释`})}>这里没懂，换一种讲法</Link>}</article></section>}
 {activity==="visual"&&selected.visual&&f.visuals&&<section><p className="learning-prediction">先预测改变参数会发生什么，再动手试一试。</p><ConceptVisual key={`visual-${selected.id}`} kind={selected.visual}/></section>}
 {activity==="quiz"&&f.quizzes&&<Quiz key={`quiz-${selected.id}`} questions={selected.quiz} path={`/api/tutor/lessons/${selected.id}/quiz`} projectId={projectId} onRecord={()=>setRevision(v=>v+1)}/>}
 {activity==="code"&&f.coding&&selected.exercise&&<CodePractice key={`code-${selected.id}`} exercise={selected.exercise} lessonId={selected.id} projectId={projectId} onRecord={()=>setRevision(v=>v+1)}/>}
 {activity!=="explain"&&nextActivity&&<div className="learning-next-activity"><Button onClick={()=>change({activity:nextActivity.value})}>继续：{nextActivity.label}</Button>{returnTo&&<Link to={returnTo}>回到论文</Link>}</div>}
 {f.glossary&&!!selected.terms.length&&<details className="learning-glossary"><summary>查看本节术语</summary><dl>{selected.terms.map(term=><div key={term.term}><dt>{term.term}</dt><dd><MathText text={term.definition}/></dd></div>)}</dl></details>}
 <details className="learning-records"><summary>练习记录（{attempts.filter(a=>a.lesson_id===selected.id).length}）</summary><p>这些记录反映本次检查表现，可以继续做变式题或返回论文实践。</p>{attempts.filter(a=>a.lesson_id===selected.id).slice(0,10).map((a,i)=><p key={i}>{a.kind==="quiz"?"小测":"浏览器代码练习"}：{a.result.correct||a.result.passed?"本次检查通过":"需要继续练习"} · {a.created_at} UTC</p>)}</details>
 </>}</section></div>}
 </div>;
}
