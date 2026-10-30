import DeferredSection from "../../components/workbench/DeferredSection";
import {featureLabels,Feature} from "../../api/preferences";
import {apiGet,apiPost} from "../../api/client";
import EvidenceMatrix from "../../components/workbench/EvidenceMatrix";
import ProjectReading from "../../components/workbench/ProjectReading";
import ProjectOverview from "../../components/workbench/ProjectOverview";
import DiffusionPractice from "../../components/workbench/DiffusionPractice";
import SceneSync from "../../components/workbench/SceneSync";
import ResearchPlan from "../../components/workbench/ResearchPlan";
import {usePreferences} from "../../components/PreferencesContext";
import ProjectWorkbench from "../../components/workbench/ProjectWorkbench";
import { useCallback, useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { Alert, Button, Space, Skeleton, Tabs, Tag, Select, Switch, Dropdown } from "antd";
import type { ResearchProject } from "../../api/project-types";
import { DOMAIN_PROFILES,projectDomainLabel,PROJECT_STAGES } from "../../api/project-types";
import { getProject } from "../../api/projects";
import ComparisonPanel from "../../components/research/ComparisonPanel";
import EvidencePanel from "../../components/research/EvidencePanel";
import PlansPanel from "../../components/research/PlansPanel";
import ProjectSettingsPanel from "../../components/research/ProjectSettingsPanel";
import "./research-workspace.css";
import ResearchCanvas from "../../components/workspace/ResearchCanvas";
import DecisionOverview from "../../components/research/DecisionOverview";
import ScenarioPanel from "../../components/workspace/ScenarioPanel";
import DiffPanel from "../../components/workspace/DiffPanel";
import ProjectAuditPanel from "../../components/research/ProjectAuditPanel";
import LocalRadarPanel from "../../components/research/LocalRadarPanel";
import KnowledgeWorkbench from "../../components/knowledge/KnowledgeWorkbench";

export const WORKFLOW_GUIDANCE: Record<string, { message: string; description: string; next: string; action: string }> = {
  evidence: { message: "第 1 步：关联资料并确认事实", description: "先关联带原文的论文，再提取候选。逐项核对方法、实验设置和测量；表格未解析时保留待补录标记，不直接采信数值。未报告的信息保持未知。", next: "compare", action: "前往条件比较" },
  compare: { message: "第 2 步：比较条件，再由你选择路线", description: "核对数据集、划分、评估协议和指标范围。不可比不等于方法不好；资源信息不足不等于可行。保存选择理由后进入方案编辑。", next: "plans", action: "前往方案编辑" },
  plans: { message: "第 3 步：审核方案，保存并冻结版本", description: "模型建议不是实验结果。模型不可用时可创建人工草稿；失败后请保留输入并检查错误，避免重复生成。确认保存后创建快照，再导出 PDF / JSON 并查看依据。", next: "evidence", action: "返回核对证据" },
  settings: { message: "修改条件后复核相关成果", description: "条件变更可能影响既有路线。核对待复核提示并重新比较；旧方案和快照仍保留，不会自动改写。", next: "compare", action: "重新比较候选" },
};

export default function ResearchProjectPage() {
  const {projectId = ''} = useParams();
  const [params,setParams] = useSearchParams();
  const tab=params.get('tab')||'';
  const primary:Record<string,string>={overview:'graph',reading:'reading',compare:'compare',practice:'practice',workbench:'materials',outcomes:'materials',evidence:'materials'};
  const historical=params.get('legacy')==='1'&&(tab==='settings'||['plans','audit','changes','scenarios','radar'].includes(tab)||tab==='outcomes'&&['formal','plan','audit','changes'].includes(params.get('output')||'')||tab==='compare'&&params.get('tool')==='historical-matrix');
  useEffect(()=>{if(historical||params.has('view')||!primary[tab])return;const next=new URLSearchParams(params);next.set('view',primary[tab]);next.delete('tab');next.delete('legacy');if(tab==='compare'&&!/^[a-f0-9]{32}$/.test(next.get('comparison')||''))next.delete('comparison');setParams(next,{replace:true})},[historical,tab,params,setParams]);
  return historical ? <LegacyResearchProjectPage key={projectId}/> : <KnowledgeWorkbench key={projectId} projectId={projectId}/>;
}

export function LegacyResearchProjectPage() {
  const { projectId = "" } = useParams();
  const {preferences}=usePreferences();
  const [overrides,setOverrides]=useState<Record<string,boolean>>({});
  const [workspace,setWorkspace]=useState<any>(null);
  const [workspaceRetry,setWorkspaceRetry]=useState(0);
  const flags=Object.fromEntries(Object.entries(preferences.features).map(([k,v])=>[k,!!workspace&&v&&overrides[k]!==false]));
  useEffect(()=>{let active=true;let generation=0;const controller=new AbortController();const load=()=>{const current=++generation;apiGet<any>("/api/workbench/projects/"+projectId,undefined,controller.signal).then(r=>{if(active&&current===generation){setWorkspace(r);setOverrides(r.features||{});setError('')}}).catch(e=>{if(!controller.signal.aborted&&active)setError(String(e))})};void load();window.addEventListener("atlas:data-change",load);window.addEventListener("paperstride:records-change",load);return()=>{active=false;controller.abort();window.removeEventListener("atlas:data-change",load);window.removeEventListener("paperstride:records-change",load)}},[projectId,workspaceRetry]);
  const [params, setParams] = useSearchParams();
  const [project, setProject] = useState<ResearchProject | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const reload = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setError("");
    try { setProject(await getProject(projectId, signal)); }
    catch (caught) {
      if (!(caught instanceof DOMException && caught.name === "AbortError")) setError(caught instanceof Error ? caught.message : "课题加载失败");
    } finally { if (!signal?.aborted) setLoading(false); }
  }, [projectId]);

  useEffect(() => {
    const controller = new AbortController();
    void reload(controller.signal);
    return () => controller.abort();
  }, [reload]);

  if (loading && !project) return <Skeleton active paragraph={{rows:5}}/>;
  if (!project) return <Alert type="error" showIcon message="无法打开课题" description={error || "课题不存在"} action={<Button onClick={() => void reload()}>重试</Button>} />;

  const requestedTab = params.get("tab") ?? "overview";
  const aliases:Record<string,string>={workbench:params.has('record')?'outcomes':'overview',evidence:'reading',scenarios:'compare',changes:'outcomes',audit:'outcomes',plans:'outcomes',radar:'explore'};
  const tab=aliases[requestedTab]||requestedTab;
  const switchTab=(key:string)=>setParams(previous=>{const next=new URLSearchParams(previous);next.set('tab',key);next.set('project',projectId);return next});
  const choose=(key:string,value:string)=>setParams(previous=>{const next=new URLSearchParams(previous);next.set(key,value);if(key==='output')next.delete('record');return next});
  const learning=flags.foundations||flags.quizzes||flags.coding||flags.visuals||flags.paper_guidance;
  const diffusionRelevant=project.domain==='robot_policy_learning'&&/diffusion[ _-]*policy|扩散策略/i.test([project.title,project.research_question,...(workspace?.papers||[]).map((p:any)=>p.title)].join(' '));
  const output=params.has('record')?'records':params.get('output')||({plans:'formal',changes:'changes',audit:'audit'} as Record<string,string>)[requestedTab]||'records';
  const comparison=params.get('comparison')||(requestedTab==='scenarios'?'resources':'matrix');
  const projectContext=workspace?{...workspace,project}:workspace;
  const saved=(next:ResearchProject)=>{setProject(next);setWorkspace((old:any)=>old?{...old,project:next}:old)};
  return <div className="ps-project-page">
    <header className="ps-project-heading"><div><Link className="ps-back-link" to="/research">研究空间</Link><h1>{project.title}</h1><span className="ps-project-stage">{project.status==='archived'?'已归档':PROJECT_STAGES[project.stage||'validating']}</span></div><Space wrap>{flags.graph&&<Link to={`/explore?project=${projectId}`}>探索相关工作</Link>}<Dropdown trigger={['click']} menu={{items:[{key:'settings',label:'课题设置与学习支持'},{key:'version',label:`项目 v${project.version} · 约束 v${project.constraints.version}`,disabled:true},{key:'domain',label:projectDomainLabel(project),disabled:true},{key:'refresh',label:'刷新服务端版本'}],onClick:({key})=>key==='refresh'?void reload():switchTab('settings')}}><Button>课题详情</Button></Dropdown></Space></header>
    {error&&<Alert type="warning" message="部分内容暂未更新" description={error} action={<Button onClick={()=>{setWorkspaceRetry(v=>v+1);void reload()}}>重试</Button>}/>}
    <SceneSync key={projectId} projectId={projectId} view={['overview','reading','compare','practice','outcomes','explore'].includes(tab)?tab:'overview'}/>
    {tab==='settings'?<section className="ps-project-settings"><Button type="text" onClick={()=>switchTab('overview')}>返回概览</Button><ProjectSettingsPanel project={project} onSaved={saved}/><ProjectSupport projectId={projectId} overrides={overrides} globalFlags={preferences.features}/></section>:tab==='explore'?<><Button onClick={()=>switchTab('overview')}>返回概览</Button><LocalRadarPanel projectId={project.id}/></>:<Tabs destroyOnHidden activeKey={tab} onChange={switchTab} items={[
      {key:'overview',label:'概览',children:<ProjectOverview projectId={projectId} workspace={projectContext} onUpdated={saved}/>},
      {key:'reading',label:'阅读',children:<><ProjectReading projectId={projectId} workspace={projectContext}/><DeferredSection title="核对方法与实验事实" initialOpen={requestedTab==='evidence'}><EvidencePanel project={project} onProjectReload={()=>reload()}/></DeferredSection></>},
      {key:'compare',label:'比较',children:<><div className="ps-view-tools"><Select aria-label="比较内容" value={comparison} onChange={v=>choose('comparison',v)} options={[{value:'matrix',label:'证据整理表'},{value:'conditions',label:'严格条件比较与路线选择'},{value:'resources',label:'资源条件推演'},{value:'decisions',label:'决策总览'}]}/></div>{comparison==='conditions'?<ComparisonPanel project={project}/>:comparison==='resources'?<ScenarioPanel project={project}/>:comparison==='decisions'?<><DecisionOverview project={project}/>{flags.graph&&<ResearchCanvas project={project}/>}</>:<EvidenceMatrix projectId={projectId}/>}</>},
      ...(learning?[{key:'practice',label:'实践',children:diffusionRelevant?<DiffusionPractice projectId={projectId}/>:<section className="ps-practice-start"><h2>围绕当前问题补充知识</h2><p>{project.research_question||'从阅读中遇到的一个问题开始，按需学习原理或练习代码。'}</p><Space wrap>{flags.paper_guidance&&<Link className="home-action home-action-primary" to={`/learn?project=${projectId}&view=tutor&returnTo=${encodeURIComponent('/research/'+projectId+'?tab=practice')}&question=${encodeURIComponent('我正在研究'+(project.custom_domain||project.title)+'。请先了解我卡在哪个问题，再按需要拆解基础知识。')}`}>带着问题开始学习</Link>}{(flags.foundations||flags.quizzes||flags.coding)&&<Link to={`/learn?project=${projectId}&view=foundations&returnTo=${encodeURIComponent('/research/'+projectId+'?tab=practice')}`}>选择基础与代码课程</Link>}</Space>{!!workspace?.sessions?.length&&<section><h3>继续本课题的辅导</h3><ul className="ps-record-preview">{workspace.sessions.slice(0,5).map((session:any)=><li key={session.id}><Link to={`/learn?project=${projectId}&session=${session.id}&returnTo=${encodeURIComponent('/research/'+projectId+'?tab=practice')}`}>{session.topic}</Link></li>)}</ul></section>}</section>}]:[]),
      {key:'outcomes',label:'成果',children:<><div className="ps-view-tools"><Select aria-label="成果内容" value={output} onChange={v=>choose('output',v)} options={[{value:'records',label:'笔记与文稿'},{value:'plan',label:'研究计划'},{value:'formal',label:'正式方案与冻结历史'},{value:'changes',label:'变化解释'},{value:'audit',label:'自动核查'}]}/></div>{output==='plan'?<ResearchPlan projectId={projectId}/>:output==='formal'?<PlansPanel project={project}/>:output==='changes'?<DiffPanel projectId={projectId}/>:output==='audit'?<ProjectAuditPanel projectId={projectId}/>:<ProjectWorkbench projectId={projectId} workspace={projectContext}/>}</>},
    ]}/>}
    {tab==='practice'&&!!workspace&&!learning&&<Alert type="info" message="本课题的学习支持已关闭" description={<><Link to={`/research/${projectId}?tab=reading`}>继续阅读论文</Link>，或在课题详情中调整学习支持。</>}/>}
  </div>;
}

function ProjectSupport({projectId,overrides,globalFlags}:{projectId:string;overrides:Record<string,boolean>;globalFlags:Record<Feature,boolean>}){
 const [values,setValues]=useState(overrides),[busy,setBusy]=useState(false),[notice,setNotice]=useState(''),[error,setError]=useState('');
 useEffect(()=>setValues(overrides),[overrides]);
 return <section className="ps-project-support"><h2>本课题的学习支持</h2><p>选择当前需要的辅助内容。个人设置中已关闭的功能保持关闭。</p>{(Object.keys(featureLabels) as Feature[]).map(key=><label key={key}><span><strong>{featureLabels[key][0]}</strong><small>{featureLabels[key][1]}</small></span><Switch aria-label={'课题'+featureLabels[key][0]} checked={globalFlags[key]&&values[key]!==false} disabled={!globalFlags[key]} onChange={value=>setValues(old=>({...old,[key]:value}))}/></label>)}<Button type="primary" loading={busy} onClick={async()=>{setBusy(true);setError('');setNotice('');try{await apiPost('/api/workbench/projects/'+projectId+'/preferences',{features:{...globalFlags,...values}});setNotice('学习支持已保存')}catch(e){setError(String(e))}finally{setBusy(false)}}}>保存学习支持</Button>{notice&&<p role="status">{notice}</p>}{error&&<Alert type="error" message={error}/>}</section>;
}
