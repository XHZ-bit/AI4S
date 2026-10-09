import { useEffect, useState } from "react";
import { Alert, Skeleton, Tag } from "antd";
import { useSearchParams } from "react-router-dom";
import { apiGet } from "../../api/client";
import { getInsights, type Report } from "../../api/assistant";
import { getProjectFacts } from "../../api/projects";
import type { GraphQueryResult, ProjectFactsResponse, ResearchProject } from "../../api/project-types";
import ProjectGraphExplorer from "../research/ProjectGraphExplorer";
export default function ResearchCanvas({ project }: { project: ResearchProject }) {
  const [data, setData] = useState<GraphQueryResult>(), [facts, setFacts] = useState<ProjectFactsResponse>(), [report, setReport] = useState<Report>();
  const [revision,setRevision]=useState(0);
  useEffect(()=>{let timer=0;const refresh=()=>{clearTimeout(timer);timer=window.setTimeout(()=>setRevision(v=>v+1),200);};window.addEventListener("atlas:data-change",refresh);return()=>{clearTimeout(timer);window.removeEventListener("atlas:data-change",refresh);};},[]);
  const [error, setError] = useState(""); const [params] = useSearchParams();
  useEffect(() => { const c = new AbortController(); Promise.all([apiGet<GraphQueryResult>(`/api/projects/${project.id}/canvas`, undefined, c.signal), getProjectFacts(project.id, {}, c.signal), getInsights("project", project.id, null, c.signal)]).then(([d, f, r]) => { if (!c.signal.aborted) { setData(d); setFacts(f); setReport(r); } }).catch(e => { if (!c.signal.aborted) setError(String(e)); }); return () => c.abort(); }, [project.id, project.version,revision]);
  return <div><Tag color="cyan">当前资料关系 · SQLite · 离线可用</Tag><div className="atlas-overview-stats">{[[report?.coverage.candidates, "候选实验设置"], [report?.coverage.bound_fields, "有绑定的字段"], [report?.coverage.issues, "待处理问题"]].map(([v, label]) => <div className="atlas-overview-stat" key={label}><strong>{v ?? "—"}</strong><span>{label}</span></div>)}</div>{error && <Alert type="warning" message={error} />}{!data && !error && <Skeleton active paragraph={{ rows: 10 }} />}{data && facts && <ProjectGraphExplorer data={data} evidence={facts.evidence} mode="evidence" requestedNodeId={params.get("focus")} />}</div>;
}
