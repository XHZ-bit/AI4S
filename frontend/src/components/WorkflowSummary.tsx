import { useEffect, useState } from "react";
import { Alert, Card, Space, Tag } from "antd";
import { Link } from "react-router-dom";
import { workflowActivities, type ActivityKind, type WorkflowActivity } from "../api/workflow";

const statusText = { pending: "待执行", in_progress: "进行中", completed: "已记录", needs_review: "待复核" };
const evidenceText = { none: "暂无记录", recorded: "用户记录", checked: "固定检查通过" };

export default function WorkflowSummary({ kind, id }: { kind: "project" | "paper" | "case"; id: string }) {
  const [items, setItems] = useState<WorkflowActivity[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    let live = true;
    const load = () => workflowActivities({ source_kind: kind as ActivityKind, ...(kind === "project" ? { project_id: id } : kind === "paper" ? { source_id: id } : {}), limit: 500 })
      .then(result => { if (live) { setItems(Array.isArray(result?.items) ? result.items : []); setError(""); } })
      .catch(caught => { if (live) setError(String(caught)); });
    void load();
    window.addEventListener("atlas:data-change", load);
    return () => { live = false; window.removeEventListener("atlas:data-change", load); };
  }, [kind, id]);
  return <Card size="small" title="执行进度" extra={<Link to="/workflow">查看统一任务 →</Link>} style={{ marginTop: 20 }}>
    {error && <Alert type="warning" message={`活动状态暂不可用：${error}`} />}
    {!error && !items.length && <p>暂无可执行活动。课题方案保存后请创建快照；阅读资料后也会在这里出现任务。</p>}
    {items.length > 0 && <><p>共 {items.length} 项，待执行 {items.filter(item => item.status === "pending").length} 项，待复核 {items.filter(item => item.status === "needs_review").length} 项。</p>
      {items.filter(item => item.status !== "completed").slice(0, 3).map(item => <div key={item.id} style={{ marginBottom: 8 }}><Space wrap><Link to={item.url}>{item.title}</Link><Tag>{statusText[item.status]}</Tag><Tag>{evidenceText[item.evidence_level]}</Tag></Space></div>)}</>}
  </Card>;
}
