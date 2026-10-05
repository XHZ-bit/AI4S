import { useEffect, useMemo, useState } from "react";
import { Alert, Empty, Spin, Typography } from "antd";
import ForceGraph2D from "react-force-graph-2d";
import type { GraphQueryResult } from "../../api/project-types";
import { getProjectGraph, ProjectApiError } from "../../api/projects";

export default function ProjectGraphPanel({ projectId, snapshotId }: { projectId: string; snapshotId: string | null }) {
  const [data, setData] = useState<GraphQueryResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [unavailable, setUnavailable] = useState(false);

  useEffect(() => {
    setData(null);
    setLoading(false);
    setError("");
    setUnavailable(false);
    if (!snapshotId) return;
    const controller = new AbortController();
    setLoading(true);
    setError("");
    setUnavailable(false);
    getProjectGraph(projectId, snapshotId, {}, controller.signal).then(result => {
      if (controller.signal.aborted) return;
      if (result.project_id !== projectId || result.snapshot_id !== snapshotId) throw new Error("图谱响应不属于当前课题与快照");
      setData(result);
    }).catch(caught => {
      if (controller.signal.aborted || (caught instanceof DOMException && caught.name === "AbortError")) return;
      if (caught instanceof ProjectApiError && [501, 503].includes(caught.status)) setUnavailable(true);
      setError(caught instanceof Error ? caught.message : "图谱读取失败");
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [projectId, snapshotId]);

  const graphData = useMemo(() => ({
    nodes: (data?.nodes ?? []).map(node => ({ id: node.id, name: node.label, kind: node.kind })),
    links: (data?.edges ?? []).map(edge => ({ source: edge.source_id, target: edge.target_id, kind: edge.kind })),
  }), [data]);

  if (!snapshotId) return <Empty description="创建或选择方案快照后，才能按该快照查看依据关系。" />;
  if (loading) return <Spin />;
  if (unavailable) return <Alert type="info" showIcon message="课题图谱尚未接入" description={`${error}。这里不会生成演示关系或用旧图谱冒充课题快照。`} />;
  if (error) return <Alert type="error" showIcon message="图谱读取失败" description={error} />;
  if (!data || (!data.nodes.length && !data.edges.length)) return <Empty description="该快照没有可显示的关系数据。" />;
  return <div className="research-graph"><Typography.Paragraph type="secondary">仅展示当前课题与所选快照内的依据关系；点击节点不会改变业务事实。</Typography.Paragraph><ForceGraph2D width={760} height={420} graphData={graphData} nodeLabel="name" linkLabel="kind" nodeAutoColorBy="kind" /></div>;
}
