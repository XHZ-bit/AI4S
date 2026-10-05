import { useEffect, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { Alert, Button, Card, Empty, Select, Space, Spin, Tag, Typography, message } from "antd";
import type { GraphQueryResult, ProjectFactsResponse, ProjectSnapshot, ResearchProject } from "../../api/project-types";
import { getProject, getProjectFacts, getProjectGraph, getProjectProjectionStatus, listProjectSnapshots, ProjectApiError, retryProjectProjection } from "../../api/projects";
import ProjectGraphExplorer from "../../components/research/ProjectGraphExplorer";
import type { ProjectGraphMode } from "../../components/research/project-graph-utils";
import { ReviewStatusTag } from "../../components/research/StatusLabels";
import "./research-workspace.css";

type SyncState = "idle" | "loading" | "synced" | "pending" | "failed" | "empty" | "mismatch";

export default function ProjectGraph() {
  const { projectId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const [project, setProject] = useState<ResearchProject | null>(null);
  const [snapshots, setSnapshots] = useState<ProjectSnapshot[]>([]);
  const [facts, setFacts] = useState<ProjectFactsResponse>({ methods: [], experiment_settings: [], measurements: [], evidence: [] });
  const [data, setData] = useState<GraphQueryResult | null>(null);
  const [state, setState] = useState<SyncState>("idle");
  const [error, setError] = useState("");
  const [retrying, setRetrying] = useState(false);
  const requestId = useRef(0);
  const requestedSnapshot = params.get("snapshot_id");
  const requestedNode = params.get("node_id");
  const rawMode = params.get("mode");
  const mode: ProjectGraphMode = rawMode === "evidence" || rawMode === "method" || rawMode === "impact" ? rawMode : "overview";

  useEffect(() => {
    const controller = new AbortController();
    setError("");
    Promise.all([getProject(projectId, controller.signal), listProjectSnapshots(projectId, controller.signal), getProjectFacts(projectId, {}, controller.signal)]).then(([projectResult, snapshotResult, factResult]) => {
      setProject(projectResult); setFacts(factResult);
      const sorted = [...snapshotResult.items].sort((a, b) => b.snapshot_version - a.snapshot_version);
      setSnapshots(sorted);
      if (!requestedSnapshot && sorted[0]) setParams(current => { const next = new URLSearchParams(current); next.set("snapshot_id", sorted[0].id); return next; }, { replace: true });
    }).catch(caught => {
      if (!(caught instanceof DOMException && caught.name === "AbortError")) setError(caught instanceof Error ? caught.message : "课题图谱元数据加载失败");
    });
    return () => controller.abort();
  }, [projectId]);

  useEffect(() => {
    if (!requestedSnapshot) { setData(null); setState(snapshots.length ? "idle" : "empty"); return; }
    const snapshot = snapshots.find(item => item.id === requestedSnapshot);
    if (snapshots.length && !snapshot) { setData(null); setState("mismatch"); setError("请求的快照不属于当前课题或已经不可用"); return; }
    const controller = new AbortController();
    const currentRequest = ++requestId.current;
    setData(null); setState("loading"); setError("");
    const kind = mode === "evidence" ? "dependency_path" : mode === "method" ? "method_context" : mode === "impact" ? "impact_path" : null;
    getProjectGraph(
      projectId,
      requestedSnapshot,
      { node_ids: requestedNode ? [requestedNode] : undefined, kinds: kind ? [kind] : undefined },
      controller.signal,
    ).then(result => {
      if (currentRequest !== requestId.current) return;
      if (result.project_id !== projectId || result.snapshot_id !== requestedSnapshot) {
        setData(null); setState("mismatch"); setError("图服务返回了其他课题或其他快照的数据，已拒绝显示"); return;
      }
      setData(result); setState(result.nodes.length ? "synced" : "empty");
    }).catch(async caught => {
      if (currentRequest !== requestId.current || (caught instanceof DOMException && caught.name === "AbortError")) return;
      setData(null);
      const fallbackError = caught instanceof Error ? caught.message : "图查询失败";
      if (caught instanceof ProjectApiError && [404, 503].includes(caught.status)) {
        try {
          const projection = await getProjectProjectionStatus(projectId, requestedSnapshot, controller.signal);
          if (currentRequest !== requestId.current) return;
          setState(projection.status === "pending" || projection.status === "running" ? "pending" : "failed");
          setError(projection.last_error ?? fallbackError);
          return;
        } catch {
          // Keep the original graph failure when projection status is unavailable.
        }
      }
      setState("failed");
      setError(fallbackError);
    });
    return () => { controller.abort(); requestId.current += 1; };
  }, [projectId, requestedSnapshot, requestedNode, mode, snapshots.map(item => item.id).join("|")]);

  const selectedSnapshot = snapshots.find(item => item.id === requestedSnapshot) ?? null;
  const latest = snapshots[0] ?? null;
  const selectSnapshot = (id: string) => setParams(current => { const next = new URLSearchParams(current); next.set("snapshot_id", id); return next; });
  const selectMode = (nextMode: ProjectGraphMode) => setParams(current => { const next = new URLSearchParams(current); next.set("mode", nextMode); return next; });
  const retryProjection = async () => {
    if (!requestedSnapshot || retrying) return;
    setRetrying(true);
    try {
      await retryProjectProjection(projectId, requestedSnapshot);
      setState("pending");
      setError("新的图投影任务已提交，请稍后刷新");
      message.success("图投影重试任务已提交");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "图投影重试失败");
    } finally { setRetrying(false); }
  };

  return <Space direction="vertical" size="large" style={{ width: "100%" }}>
    <div><Link to={`/research/${projectId}?tab=plans`}>← 返回方案与历史</Link><div className="research-page-heading"><div><Typography.Title level={2}>课题图谱</Typography.Title><Typography.Text>{project?.title ?? projectId}</Typography.Text></div><Space wrap><Link to={`/research/${projectId}?tab=evidence`}>查看已保存资料</Link><Link to={`/research/${projectId}?tab=plans`}>返回方案</Link></Space></div></div>
    <Card size="small"><Space wrap><Select value={requestedSnapshot ?? undefined} placeholder="选择不可变快照" style={{ minWidth: 260 }} onChange={selectSnapshot} options={snapshots.map(snapshot => ({ value: snapshot.id, label: `快照 v${snapshot.snapshot_version}${snapshot.id === latest?.id ? " · 最新" : " · 历史"}` }))} /><Select value={mode} onChange={selectMode} options={[{ value: "overview", label: "任务相关子图" }, { value: "evidence", label: "查看依据" }, { value: "method", label: "查看实验设置" }, { value: "impact", label: "查看影响范围" }]} /><Tag>图 revision：{selectedSnapshot ? `${selectedSnapshot.snapshot_version} / ${selectedSnapshot.id}` : "无"}</Tag><Tag color={state === "synced" ? "green" : state === "loading" || state === "pending" ? "blue" : state === "failed" || state === "mismatch" ? "red" : "default"}>{({ idle: "未查询", loading: "同步检查中", synced: "已同步", pending: "待同步", failed: "同步/查询失败", empty: "无数据", mismatch: "版本不一致" } as Record<SyncState, string>)[state]}</Tag>{selectedSnapshot && <ReviewStatusTag status={selectedSnapshot.review_status} />}</Space></Card>
    {selectedSnapshot && latest && selectedSnapshot.id !== latest.id && <Alert type="warning" showIcon message="正在查看历史图谱 revision" description={`当前显示快照 v${selectedSnapshot.snapshot_version}，最新快照为 v${latest.snapshot_version}。历史图不会标记为当前最新图。`} />}
    {state === "loading" && <Spin />}
    {state === "pending" && <Alert type="info" showIcon message="图谱待同步" description={`${error || "该快照尚未完成投影"}。已保存方案和资料仍可查看。`} action={<Button loading={retrying} onClick={() => void retryProjection()}>重试投影</Button>} />}
    {(state === "failed" || state === "mismatch") && <Alert type="error" showIcon message={state === "mismatch" ? "图谱版本不一致" : "图服务不可用或查询失败"} description={error} action={<Space>{state === "failed" && <Button loading={retrying} onClick={() => void retryProjection()}>重试投影</Button>}<Link to={`/research/${projectId}?tab=plans`}>返回方案</Link><Link to={`/research/${projectId}?tab=evidence`}>查看资料</Link></Space>} />}
    {state === "empty" && <Empty description={snapshots.length ? "当前快照没有图谱数据" : "课题还没有可投影的不可变快照"} />}
    {state === "synced" && data && <ProjectGraphExplorer data={data} evidence={facts.evidence} mode={mode} requestedNodeId={requestedNode} />}
  </Space>;
}
