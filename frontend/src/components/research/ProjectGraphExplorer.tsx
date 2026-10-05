import { useEffect, useMemo, useRef, useState } from "react";
import { Alert, Button, Card, Checkbox, Descriptions, Empty, List, Select, Space, Tag, Typography } from "antd";
import ForceGraph2D from "react-force-graph-2d";
import type { EvidenceRef, GraphQueryResult } from "../../api/project-types";
import { graphView, initialFocus, nodeTypeColors, nodeTypeLabels, type ProjectGraphMode } from "./project-graph-utils";
import { FindingStatusTag, SourceKindTag, displayKnown } from "./StatusLabels";

type CanvasNode = { id: string; name: string; kind: string; color: string };

export default function ProjectGraphExplorer({ data, evidence, mode, requestedNodeId }: { data: GraphQueryResult; evidence: EvidenceRef[]; mode: ProjectGraphMode; requestedNodeId?: string | null }) {
  const [selectedId, setSelectedId] = useState<string | null>(() => initialFocus(data.nodes, requestedNodeId));
  const [focusId, setFocusId] = useState<string | null>(() => initialFocus(data.nodes, requestedNodeId));
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [types, setTypes] = useState<string[]>([]);
  const [width, setWidth] = useState(800);
  const host = useRef<HTMLDivElement>(null);
  const graph = useRef<any>(null);

  useEffect(() => {
    const next = initialFocus(data.nodes, requestedNodeId);
    setSelectedId(next); setFocusId(next); setExpanded(new Set());
  }, [data, requestedNodeId]);
  useEffect(() => {
    if (!host.current) return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(320, entry.contentRect.width)));
    observer.observe(host.current); return () => observer.disconnect();
  }, []);

  const view = useMemo(() => graphView(data.nodes, data.edges, mode, focusId, expanded), [data, mode, focusId, expanded]);
  const availableTypes = Array.from(new Set(data.nodes.map(node => node.kind)));
  const visibleNodes = data.nodes.filter(node => view.nodeIds.has(node.id) && (!types.length || types.includes(node.kind)));
  const visibleIds = new Set(visibleNodes.map(node => node.id));
  const visibleEdges = data.edges.filter(edge => visibleIds.has(edge.source_id) && visibleIds.has(edge.target_id));
  const selected = data.nodes.find(node => node.id === selectedId) ?? null;
  const selectedEvidence = selected?.kind === "evidence" ? evidence.find(item => item.id === selected.id) ?? null : null;
  const canvas = {
    nodes: visibleNodes.map(node => ({ id: node.id, name: node.label, kind: node.kind, color: view.highlighted.has(node.id) ? "#cf1322" : nodeTypeColors[node.kind] ?? "#8c8c8c" })),
    links: visibleEdges.map(edge => ({ source: edge.source_id, target: edge.target_id, name: edge.kind })),
  };
  const labels = new Map(data.nodes.map(node => [node.id, node.label]));

  if (!data.nodes.length) return <Empty description="当前快照没有图谱数据" />;
  return <Space direction="vertical" size="middle" style={{ width: "100%" }}>
    {mode === "impact" && <Alert type="warning" showIcon message="影响范围表示需要复核，不表示方案已经错误" description="红色节点位于该证据与决策/方案之间的依赖路径上；系统不会自动改写已保存成果。" />}
    <Space wrap><Select mode="multiple" allowClear value={types} onChange={setTypes} placeholder="按节点类型筛选" style={{ minWidth: 280 }} options={availableTypes.map(kind => ({ value: kind, label: nodeTypeLabels[kind] ?? kind }))} /><Button onClick={() => graph.current?.zoomToFit(400, 40)}>适配画布</Button><Button onClick={() => { setExpanded(new Set()); setFocusId(initialFocus(data.nodes, requestedNodeId)); }}>收起到任务子图</Button><Typography.Text type="secondary">显示 {visibleNodes.length}/{data.nodes.length} 个节点</Typography.Text></Space>
    <Space wrap>{availableTypes.map(kind => <Checkbox key={kind} checked={!types.length || types.includes(kind)} onChange={event => setTypes(current => event.target.checked ? Array.from(new Set([...current, kind])) : (current.length ? current.filter(item => item !== kind) : availableTypes.filter(item => item !== kind)))}><Tag color={nodeTypeColors[kind]}>{nodeTypeLabels[kind] ?? kind}</Tag></Checkbox>)}</Space>
    <div className="research-graph-layout">
      <div ref={host} className="research-graph-canvas"><ForceGraph2D ref={graph} width={width} height={560} graphData={canvas} nodeId="id" nodeLabel={(node: CanvasNode) => `${nodeTypeLabels[node.kind] ?? node.kind} · ${node.name}`} nodeColor={(node: CanvasNode) => node.color} linkLabel={(link: { name: string }) => link.name} linkDirectionalArrowLength={4} onNodeClick={(node: CanvasNode) => setSelectedId(node.id)} /></div>
      <Space direction="vertical" style={{ width: "100%" }}>
        <Card title="节点详情" size="small">{!selected ? <Empty description="请选择节点" /> : <><Space wrap><Tag color={nodeTypeColors[selected.kind]}>{nodeTypeLabels[selected.kind] ?? selected.kind}</Tag><Typography.Text copyable>{selected.id}</Typography.Text></Space><Typography.Title level={5}>{selected.label}</Typography.Title><Descriptions size="small" column={1} items={Object.entries(selected.properties).map(([key, value]) => ({ key, label: key, children: displayKnown(value) }))} />{selected.properties.source_kind && <SourceKindTag source={selected.properties.source_kind as any} />}{selected.properties.finding_status && <FindingStatusTag status={selected.properties.finding_status as any} />}<p><Button onClick={() => { setFocusId(selected.id); setExpanded(current => new Set([...current, selected.id])); }}>局部展开并定位</Button></p></>}</Card>
        {selectedEvidence && <Card title="原文证据" size="small"><Space wrap><SourceKindTag source={selectedEvidence.source_kind} /><FindingStatusTag status={selectedEvidence.finding_status} /></Space><Typography.Paragraph style={{ whiteSpace: "pre-wrap", marginTop: 8 }}>{selectedEvidence.quote || "当前没有可显示的原文片段"}</Typography.Paragraph><p>位置：{displayKnown(selectedEvidence.locator?.heading)} / {selectedEvidence.locator?.page ? `第 ${selectedEvidence.locator.page} 页` : "页码未知"}</p>{selectedEvidence.paper_uid && <a href={`/papers/${encodeURIComponent(selectedEvidence.paper_uid)}?tab=reading&passage=${encodeURIComponent(selectedEvidence.passage_id ?? "")}`}>打开论文与定位章节</a>}</Card>}
      </Space>
    </div>
    <Card title={mode === "impact" ? "受影响成果与关系路径" : "可阅读的依据路径"}>{view.paths.length ? <List dataSource={view.paths} renderItem={(path, index) => <List.Item><Space wrap><Tag>{index + 1}</Tag>{path.map((id, i) => <span key={`${id}:${i}`}>{i > 0 && " → "}<Button type="link" onClick={() => setSelectedId(id)}>{labels.get(id) ?? id}</Button></span>)}</Space></List.Item>} /> : <Typography.Text type="secondary">当前任务子图没有找到相应路径。缺失路径不证明没有影响或没有依据。</Typography.Text>}</Card>
  </Space>;
}
