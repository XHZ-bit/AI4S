import useRecentProjects from "../components/workbench/useRecentProjects";
import {useCurrentAccount} from "../components/SessionContext";
import {PROJECT_STAGES} from "../api/project-types";
import {apiPost} from "../api/client";
import { useEffect, useState } from "react";
import { Alert, Button, Skeleton } from "antd";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRightOutlined, PlusOutlined } from "@ant-design/icons";
import RuntimeStatus from "../components/RuntimeStatus";
import { listPapers } from "../api/papers";
import { workflowOverview, type WorkflowOverview } from "../api/workflow";
import "./home.css";

type RecentPaper = { uid: string; title: string; year?: number | null; source?: string; parse_status?: string };

function lastWorkspace(account?:string) {
  try {
    const value = localStorage.getItem(`paperstride:${account||"local"}:lastWorkspace`) || (!account ? localStorage.getItem("atlas:lastWorkspace") : "") || "";
    return /^\/(research|papers|cases)\/[A-Za-z0-9._%/-]+(?:\?.*)?$/.test(value) ? value : "";
  } catch { return ""; }
}

export default function Home() {
  const navigate = useNavigate();
  const [demoBusy,setDemoBusy]=useState(false),[demoError,setDemoError]=useState("");
  const account=useCurrentAccount();
  const last=lastWorkspace(account?.id);
  const projects=useRecentProjects();
  const [papers, setPapers] = useState<RecentPaper[]>([]), [paperError, setPaperError] = useState("");
  const [papersLoading, setPapersLoading] = useState(true), [paperRetry, setPaperRetry] = useState(0);
  const [workflow, setWorkflow] = useState<WorkflowOverview>(), [workflowError, setWorkflowError] = useState("");
  const [workflowLoading, setWorkflowLoading] = useState(true), [workflowRetry, setWorkflowRetry] = useState(0);

  useEffect(() => {
    let live = true; setPapersLoading(true); setPaperError("");
    listPapers(6).then(result => { if (live) {setPapers(result.items.slice(0, 6));setPapersLoading(false);} })
      .catch(error => { if (live) {setPaperError(String(error));setPapersLoading(false);} });
    return () => { live = false; };
  }, [paperRetry]);

  useEffect(() => {
    let live = true, generation = 0;
    let controller: AbortController | undefined;
    async function load() {
      const request = ++generation;
      controller?.abort();
      const current = new AbortController(); controller = current;
      setWorkflowLoading(true);
      try {
        const result = await workflowOverview(current.signal);
        if (!live || current.signal.aborted || request !== generation) return;
        if (!result?.counts || !Array.isArray(result.next) ||
            ![result.counts.pending, result.counts.in_progress, result.counts.needs_review].every(value => Number.isFinite(value) && value >= 0)) {
          throw new Error("任务摘要格式不完整，请重试。");
        }
        setWorkflow(result); setWorkflowError("");
      } catch (error) {
        if (live && !current.signal.aborted && request === generation) { setWorkflow(undefined); setWorkflowError(String(error)); }
      }
      finally { if (live && !current.signal.aborted && request === generation) setWorkflowLoading(false); }
    }
    void load(); window.addEventListener("atlas:data-change", load);
    return () => { live = false; generation++; controller?.abort(); window.removeEventListener("atlas:data-change", load); };
  }, [workflowRetry]);

  const lastProject=last.match(/^\/research\/([^/?]+)/)?.[1];
  const validLast=lastProject&&!projects.loading&&!projects.items.some(p=>p.id===decodeURIComponent(lastProject))?'':last;
  const continueUrl=validLast || (projects.items[0] ? `/research/${projects.items[0].id}` : "");
  const currentProject=projects.items.find(p=>continueUrl.includes(p.id))||projects.items[0];
  const nextItems=[...new Map((workflow?.next||[]).filter(item=>['pending','in_progress','needs_review'].includes(item.status)&&(!currentProject||item.project_id===currentProject.id||item.url.split('?')[0]==='/research/'+encodeURIComponent(currentProject.id))).map(item=>[item.url+'|'+item.title,item])).values()].slice(0,3);
  return <div className="atlas-home-workbench ps-home">
    <header className="ps-home-heading"><div><h1>研究工作台</h1><p>从知识关系出发，追溯原文、比较方法，继续学习与实践。</p></div><Link className="home-action home-action-secondary" to="/research?new=1"><PlusOutlined/>新建研究空间</Link></header>
    {continueUrl && <section className="ps-resume" aria-label="继续当前研究"><div><h2>继续当前研究</h2><p>{projects.items.find(p=>continueUrl.includes(p.id))?.title || (continueUrl.includes('/papers/') ? '回到上次阅读的论文与位置' : '回到上次的工作位置')}</p></div><Link className="home-action home-action-primary" to={continueUrl}>继续上次任务 <ArrowRightOutlined/></Link></section>}
    {!continueUrl && !projects.loading && <section className="ps-start"><h2>开始一项研究</h2><p>添加论文开始阅读，或建立研究空间整理一个问题。</p><div><Link className="home-action home-action-primary" to="/manage?add=1">从论文开始 <ArrowRightOutlined/></Link><Link className="home-action home-action-secondary" to="/research?new=1">探索一个想法</Link></div></section>}
    <section className="ps-knowledge-entry" aria-label="知识图谱入口"><div><h2>知识图谱</h2><p>{currentProject?.research_question||'把资料里的问题、方法、概念与依据连接起来。'}</p></div><div><Link className="home-action home-action-primary" to={currentProject?`/research/${currentProject.id}?view=graph`:'/graph'}>进入当前研究图谱 <ArrowRightOutlined/></Link><Link className="home-action home-action-secondary" to="/graph">查看全部知识</Link></div></section>
    <div className="ps-home-columns"><section aria-labelledby="home-spaces-title"><header className="home-section-heading"><h2 id="home-spaces-title">最近研究空间</h2><Link to="/research">全部课题 <ArrowRightOutlined/></Link></header>
      {projects.error && <Alert type="warning" message="研究空间暂不可用" description={projects.error} action={<Button onClick={projects.retry}>重试</Button>}/>}
      {projects.loading&&!projects.items.length&&<Skeleton active title={false} paragraph={{rows:3}}/>}
      {!!projects.items.length&&<ul className="ps-project-list">{projects.items.map(project=><li key={project.id}><Link to={`/research/${project.id}`}><div><strong>{project.title}</strong><p>{project.research_question||'尚未填写研究问题。'}</p></div><span>{PROJECT_STAGES[project.stage||'validating']}</span><ArrowRightOutlined/></Link></li>)}</ul>}
      {!projects.loading&&!projects.items.length&&!projects.error&&<div className="home-empty"><p>把同一个方向的资料、问题与成果放在一个研究空间。</p><Link to="/research?new=1">建立第一个研究空间</Link></div>}
    </section>
    <section className="ps-home-next" aria-labelledby="home-next-title" aria-busy={workflowLoading}><header className="home-section-heading"><h2 id="home-next-title">当前研究的下一步</h2><Link to="/workflow">任务面板</Link></header>
      {workflowError&&<Alert type="warning" message="任务摘要暂不可用" description={workflowError} action={<Button loading={workflowLoading} onClick={()=>setWorkflowRetry(v=>v+1)}>重试摘要</Button>}/>}
      {workflowLoading&&!workflow&&!workflowError&&<Skeleton active title={false} paragraph={{rows:2}}/>}
      {workflow&&<><p className="home-task-counts">{currentProject?.title||"最近任务"} · 优先显示与当前研究相关的事项</p>{nextItems.length?<ul className="home-next-list">{nextItems.map(item=><li key={item.id}><Link to={item.url}><span className="home-next-copy"><strong>{item.title}</strong>{item.detail&&<small>{item.detail}</small>}</span><ArrowRightOutlined/></Link></li>)}</ul>:<p className="ps-muted">当前研究没有待办任务。可从图谱选择一个尚未理解的节点继续学习。</p>}</>}
    </section></div>
    <section className="home-recent" aria-labelledby="home-recent-title"><header className="home-section-heading"><h2 id="home-recent-title">最近资料</h2><Link to="/manage">打开资料库 <ArrowRightOutlined/></Link></header>
      {paperError&&<Alert type="warning" message="最近论文暂不可用" description={paperError} action={<Button loading={papersLoading} onClick={()=>setPaperRetry(v=>v+1)}>重试论文列表</Button>}/>}
      {papersLoading&&!papers.length&&<Skeleton active title={false} paragraph={{rows:2}}/>}
      {!!papers.length&&<ul className="ps-paper-list">{papers.slice(0,4).map(paper=><li key={paper.uid}><Link to={`/papers/${encodeURIComponent(paper.uid)}?tab=reading`}><strong>{paper.title||'未命名论文'}</strong><span>{paper.source==='upload'?'本地 PDF':paper.source==='arxiv'?'arXiv':'论文资料'} · {paper.year||'年份未记录'}</span><ArrowRightOutlined/></Link></li>)}</ul>}
      {!papersLoading&&!papers.length&&!paperError&&<div className="home-empty"><p>添加第一篇论文，即可开始阅读和记录理解。</p><Link to="/manage?add=1">添加论文</Link></div>}
    </section>
    <div className="home-support"><details className="ps-example"><summary>示例：知识图谱研究流程</summary><p>合成资料演示导入、原文定位、知识关系、交互学习和方法比较，不代表真实科研结论。</p><Button loading={demoBusy} onClick={async()=>{setDemoBusy(true);setDemoError('');try{const r=await apiPost<{project_id:string}>("/api/stride/demo",{});navigate(`/research/${r.project_id}?view=graph`)}catch(e){setDemoError(String(e))}finally{setDemoBusy(false)}}}>打开示例研究空间</Button>{demoError&&<Alert type="error" message={demoError}/>}</details>
    <details className="home-runtime"><summary>运行状态</summary><RuntimeStatus/></details></div>
  </div>;
}
