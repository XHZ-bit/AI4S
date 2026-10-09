import { useEffect, useMemo, useRef, useState } from "react";
import { Alert, Button, Card, Checkbox, Descriptions, Empty, List, Select, Space, Tag, Typography } from "antd";
import ForceGraph2D from "react-force-graph-2d";
import type { EvidenceRef, GraphQueryResult } from "../../api/project-types";
import { graphView, initialFocus, neighborhood, nodeTypeColors, nodeTypeLabels, type ProjectGraphMode } from "./project-graph-utils";
import { FindingStatusTag, SourceKindTag, displayKnown } from "./StatusLabels";
import { useInspector } from "../workspace/InspectorContext";
import { useSearchParams } from "react-router-dom";

type CanvasNode = { id: string; name: string; kind: string; color: string; x?: number; y?: number; fx?: number; fy?: number };

export default function ProjectGraphExplorer({ data, evidence, mode, requestedNodeId }: { data: GraphQueryResult; evidence: EvidenceRef[]; mode: ProjectGraphMode; requestedNodeId?: string | null }) {
  const [selectedId, setSelectedId] = useState<string | null>(() => initialFocus(data.nodes, requestedNodeId));
  const [focusId, setFocusId] = useState<string | null>(() => initialFocus(data.nodes, requestedNodeId));
  const [localView,setLocalView]=useState(data.snapshot_id!=="current");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [types, setTypes] = useState<string[]>([]);
  const [width, setWidth] = useState(800);
  const host = useRef<HTMLDivElement>(null);
  const graph = useRef<any>(null);
  const nodes = useRef(new Map<string, CanvasNode>());
  const inspector = useInspector(); const [, setParams] = useSearchParams();
  const storageKey = `atlas:graph:${data.project_id}:${data.snapshot_id}`;
  const select = (id: string) => {
    setSelectedId(id);
    const node = data.nodes.find(n => n.id === id);
    if (!inspector.available || !node || !["method","experiment_setting","measurement","evidence"].includes(node.kind)) setParams(previous => { const next = new URLSearchParams(previous); next.set("focus", id); return next; });
    if (node && ["method", "experiment_setting", "measurement", "evidence"].includes(node.kind)) inspector.inspect({ kind: node.kind === "evidence" ? "evidence" : "fact", id });
  };
  const persist = () => {
    try { localStorage.setItem(storageKey, JSON.stringify({ nodes: Object.fromEntries([...nodes.current].map(([id, n]) => [id, { x: n.x, y: n.y }])), zoom: graph.current?.zoom(), center: graph.current?.centerAt() })); } catch {}
  };

  useEffect(() => {
    const next = initialFocus(data.nodes, requestedNodeId);
    setSelectedId(next); setFocusId(next);
  }, [data, requestedNodeId]);
  useEffect(() => {
    if (!host.current) return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(200, entry.contentRect.width)));
    observer.observe(host.current); return () => observer.disconnect();
  }, []);

  const view = useMemo(() => graphView(data.nodes, data.edges, mode, focusId, expanded), [data, mode, focusId, expanded]);
  const availableTypes = Array.from(new Set(data.nodes.map(node => node.kind)));
  const visibleNodes = data.nodes.filter(node => (!localView || view.nodeIds.has(node.id)) && (!types.length || types.includes(node.kind)));
  const related = neighborhood(data.edges, selectedId ? [selectedId] : [], 2);
  const visibleIds = new Set(visibleNodes.map(node => node.id));
  const visibleEdges = data.edges.filter(edge => visibleIds.has(edge.source_id) && visibleIds.has(edge.target_id));
  const selected = data.nodes.find(node => node.id === selectedId) ?? null;
  const selectedEvidence = selected?.kind === "evidence" ? evidence.find(item => item.id === selected.id) ?? null : null;
  const signature = visibleNodes.map(n => n.id).join("|") + visibleEdges.map(e => e.id).join("|");
  const canvas = useMemo(() => {
    let saved: Record<string, { x: number; y: number }> = {};
    try { saved = JSON.parse(localStorage.getItem(storageKey) || "{}").nodes || {}; } catch {}
    return { nodes: visibleNodes.map(node => {
      let n = nodes.current.get(node.id);
      if (!n) { n = { id: node.id, name: node.label, kind: node.kind, color: nodeTypeColors[node.kind] ?? "#8c8c8c", ...saved[node.id] }; if (saved[node.id]) { n.fx = n.x; n.fy = n.y; } nodes.current.set(node.id, n); }
      n.name = node.label; return n;
    }), links: visibleEdges.map(edge => ({ source: edge.source_id, target: edge.target_id, name: edge.kind })) };
  }, [signature, storageKey]);
  useEffect(() => { try { const saved = JSON.parse(localStorage.getItem(storageKey) || "{}"); if (saved.zoom) graph.current?.zoom(saved.zoom); if (saved.center) graph.current?.centerAt(saved.center.x, saved.center.y); } catch {} }, [storageKey]);
  const labels = new Map(data.nodes.map(node => [node.id, node.label]));

  if (!data.nodes.length) return <Empty description="当前快照没有图谱数据" />;
  return <Space direction="vertical" size="middle" style={{ width: "100%" }}>
    {mode === "impact" && <Alert type="warning" showIcon message="影响范围表示需要复核，不表示方案已经错误" description="红色节点位于该证据与决策/方案之间的依赖路径上；系统不会自动改写已保存成果。" />}
    <Space wrap><Select mode="multiple" allowClear value={types} onChange={setTypes} placeholder="按节点类型筛选" style={{ minWidth: 280 }} options={availableTypes.map(kind => ({ value: kind, label: nodeTypeLabels[kind] ?? kind }))} /><Button onClick={() => graph.current?.zoomToFit(400, 40)}>适配画布</Button><Button onClick={() => { setLocalView(true); setExpanded(new Set()); setFocusId(initialFocus(data.nodes, requestedNodeId)); }}>收起到任务子图</Button>{localView && <Button onClick={()=>setLocalView(false)}>返回全图</Button>}<Button disabled={!selectedId} onClick={()=>{const n=nodes.current.get(selectedId!);if(n?.x!==undefined&&n.y!==undefined)graph.current?.centerAt(n.x,n.y,window.matchMedia?.("(prefers-reduced-motion: reduce)").matches?0:200);}}>返回焦点</Button><Typography.Text type="secondary">显示 {visibleNodes.length}/{data.nodes.length} 个节点</Typography.Text></Space>
    <Space wrap>{availableTypes.map(kind => <Checkbox key={kind} checked={!types.length || types.includes(kind)} onChange={event => setTypes(current => event.target.checked ? Array.from(new Set([...current, kind])) : (current.length ? current.filter(item => item !== kind) : availableTypes.filter(item => item !== kind)))}><Tag color={nodeTypeColors[kind]}>{nodeTypeLabels[kind] ?? kind}</Tag></Checkbox>)}</Space>
    <div className="research-graph-layout">
      <div ref={host} className="research-graph-canvas"><ForceGraph2D ref={graph} width={width} height={440} graphData={canvas} cooldownTicks={70} onEngineStop={() => { canvas.nodes.forEach(n => { n.fx = n.x; n.fy = n.y; }); persist(); }} onNodeDragEnd={(node: CanvasNode) => { node.fx = node.x; node.fy = node.y; persist(); }} onZoomEnd={persist} nodeId="id" nodeLabel={(node: CanvasNode) => `${nodeTypeLabels[node.kind] ?? node.kind} · ${node.name}`} nodeColor={(node: CanvasNode) => node.id === selectedId ? "#087f8c" : related.has(node.id) ? node.color : "#cedbe0"} linkLabel={(link: { name: string }) => link.name} linkColor={(link:any)=>related.has(typeof link.source==="object"?link.source.id:link.source)&&related.has(typeof link.target==="object"?link.target.id:link.target)?"#73abb1":"#dce6ea"} nodeCanvasObject={(node:CanvasNode,ctx:CanvasRenderingContext2D,zoom:number)=>{if(node.x===undefined||node.y===undefined)return;ctx.beginPath();ctx.arc(node.x,node.y,node.id===selectedId?6:4,0,Math.PI*2);ctx.fillStyle=node.id===selectedId?"#087f8c":related.has(node.id)?node.color:"#cedbe0";ctx.fill();ctx.font=`${Math.max(3,11/zoom)}px sans-serif`;ctx.textAlign="center";ctx.fillStyle=related.has(node.id)?"#243d4b":"#90a4af";ctx.fillText(node.name.slice(0,22),node.x,node.y+12/zoom);}} linkDirectionalArrowLength={4} onNodeClick={(node: CanvasNode) => select(node.id)} /></div>
      <Space direction="vertical" style={{ width: "100%" }}>
        <Card title="节点详情" size="small">{!selected ? <Empty description="请选择节点" /> : <><Space wrap><Tag color={nodeTypeColors[selected.kind]}>{nodeTypeLabels[selected.kind] ?? selected.kind}</Tag><Typography.Text copyable>{selected.id}</Typography.Text></Space><Typography.Title level={5}>{selected.label}</Typography.Title><Descriptions size="small" column={1} items={Object.entries(selected.properties).map(([key, value]) => ({ key, label: key, children: displayKnown(value) }))} />{selected.properties.source_kind && <SourceKindTag source={selected.properties.source_kind as any} />}{selected.properties.finding_status && <FindingStatusTag status={selected.properties.finding_status as any} />}<p><Button onClick={() => { setLocalView(true); setFocusId(selected.id); setExpanded(current => new Set([...current, selected.id])); }}>局部展开并定位</Button></p></>}</Card>
        {selectedEvidence && <Card title="原文证据" size="small"><Space wrap><SourceKindTag source={selectedEvidence.source_kind} /><FindingStatusTag status={selectedEvidence.finding_status} /></Space><Typography.Paragraph style={{ whiteSpace: "pre-wrap", marginTop: 8 }}>{selectedEvidence.quote || "当前没有可显示的原文片段"}</Typography.Paragraph><p>位置：{displayKnown(selectedEvidence.locator?.heading)} / {selectedEvidence.locator?.page ? `第 ${selectedEvidence.locator.page} 页` : "页码未知"}</p><Button onClick={() => inspector.inspect({ kind: "evidence", id: selectedEvidence.id })}>侧栏定位原文</Button></Card>}
      </Space>
    </div>
    <Card title={mode === "impact" ? "受影响成果与关系路径" : "可阅读的依据路径"}>{view.paths.length ? <List dataSource={view.paths} renderItem={(path, index) => <List.Item><Space wrap><Tag>{index + 1}</Tag>{path.map((id, i) => <span key={`${id}:${i}`}>{i > 0 && " → "}<Button type="link" onClick={() => select(id)}>{labels.get(id) ?? id}</Button></span>)}</Space></List.Item>} /> : <Typography.Text type="secondary">当前任务子图没有找到相应路径。缺失路径不证明没有影响或没有依据。</Typography.Text>}</Card>
  </Space>;
}
