import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Alert, Button, Drawer, Empty, Input, Modal, Segmented, Skeleton, Space, Tag } from "antd";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { apiGet } from "../../api/client";
import { explainActions, getInsights, getResources, type Action, type Reference, type Report, type Resource, type Scope } from "../../api/assistant";
import { InspectorContext } from "./InspectorContext";
import SourceView from "./SourceView";
import { TensorAnimation, WindowAnimation } from "./InteractiveLab";
const PdfReader = lazy(() => import("./PdfReader"));

function read(key: string, fallback: string) { try { return localStorage.getItem(key) || fallback; } catch { return fallback; } }
function write(key: string, value: string) { try { localStorage.setItem(key, value); } catch { /* In-memory navigation remains available. */ } }

export default function Workspace({ scope, id, children }: { scope: Scope; id: string; children: ReactNode }) {
  const [params, setParams] = useSearchParams(); const location = useLocation(), navigate = useNavigate();
  const sid = params.get("session") || (scope === "case" ? read(`atlas:case:${id}`, "") : "");
  const storage = `atlas:workspace:${scope}:${id}:v1`;
  const [width, setWidth] = useState(() => Math.max(280, Math.min(480, Number(read(`${storage}:width`, "360")) || 360)));
  const [open, setOpen] = useState(false), [revision, setRevision] = useState(0), [resourceRevision, setResourceRevision] = useState(0);
  const [viewport, setViewport] = useState(window.innerWidth);
  useEffect(() => { const resize = () => setViewport(window.innerWidth); window.addEventListener("resize", resize); return () => window.removeEventListener("resize", resize); }, []);
  const [report, setReport] = useState<Report>(), [resources, setResources] = useState<Resource[]>([]);
  const [reference, setReference] = useState<Reference | null>(null), [resource, setResource] = useState<Resource | null>(null);
  const [error, setError] = useState(""), [sourceError, setSourceError] = useState(""), [loading, setLoading] = useState(true);
  const [search, setSearch] = useState(false), [query, setQuery] = useState("");
  const [explanations, setExplanations] = useState<Record<string, string>>({}), [explaining, setExplaining] = useState(false);
  const latestFingerprint = useRef(report?.input_fingerprint); latestFingerprint.current=report?.input_fingerprint;
  const drag = useRef(false); const scopeKey = `${scope}:${id}:${sid}`; const active = useRef(scopeKey); active.current = scopeKey;
  const panel = params.get("panel") || "coach";
  const refresh = useCallback(() => { setRevision(x => x + 1); setResourceRevision(x=>x+1); }, []);
  useEffect(() => {
    setReport(undefined); setReference(null); setResource(null); setExplanations({}); setExplaining(false); setError(""); setOpen(false);
    setWidth(Math.max(280, Math.min(480, Number(read(`${storage}:width`, "360")) || 360)));
  }, [scope, id, storage, sid]);
  useEffect(() => { setResources([]); }, [scope,id]);
  useEffect(() => {
    const c = new AbortController();
    getResources(scope,id,c.signal).then(r=>{if(!c.signal.aborted)setResources(r.items);}).catch(e=>{if(!c.signal.aborted)setError(String(e));});
    return ()=>c.abort();
  },[scope,id,resourceRevision]);
  useEffect(() => {
    const c = new AbortController(); setLoading(true); setError("");

    if (scope === "case" && !sid) { setLoading(false); return () => c.abort(); }
    void getInsights(scope, id, sid, c.signal).then(r => { if (!c.signal.aborted) { setReport(r); setExplanations({}); } }).catch(e => { if (!c.signal.aborted) setError(String(e)); }).finally(() => { if (!c.signal.aborted) setLoading(false); });
    return () => c.abort();
  }, [scope, id, sid, revision]);
  useEffect(() => {
    let timer = 0;
    const update = (event: Event) => { clearTimeout(timer); timer = window.setTimeout(() => { setRevision(x=>x+1); if (!/\/sessions(?:\/|$)/.test((event as CustomEvent<{path?:string}>).detail?.path || "")) setResourceRevision(x=>x+1); }, 200); };
    const keyboard = (e: KeyboardEvent) => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setSearch(v => !v); } };
    window.addEventListener("atlas:data-change", update); window.addEventListener("keydown", keyboard);
    return () => { clearTimeout(timer); window.removeEventListener("atlas:data-change", update); window.removeEventListener("keydown", keyboard); };
  }, [refresh]);
  useEffect(() => {
    const stored = `${location.pathname}${location.search}`;
    write("atlas:lastWorkspace", stored);
    if (location.search || !read(`${storage}:location`, "")) write(`${storage}:location`, stored);
  }, [location, storage]);
  useEffect(() => {
    const last = read(`${storage}:location`, "");
    if (!location.search && last.startsWith(`${location.pathname}?`)) navigate(last, { replace: true });
  }, [storage, location.pathname, navigate]);
  const updateURL = useCallback((values: Record<string, string | null>, replace = false) => {
    setParams(previous => { const next = new URLSearchParams(previous); Object.entries(values).forEach(([k, v]) => v === null ? next.delete(k) : next.set(k, v)); return next; }, { replace });
  }, [setParams]);
  const inspect = useCallback((ref: Reference, selection:Record<string,string|null>={}) => { setReference(ref); setOpen(true); updateURL({ panel: "evidence", ref: `${ref.kind}:${ref.id}`, focus: ref.id, line: ref.line ? String(ref.line) : null, page: ref.page ? String(ref.page) : null, change:null, ...selection }); }, [updateURL]);
  const openResource = useCallback((r: Resource) => { setResource(r); setReference(null); setOpen(true); updateURL({ panel: "resources", resource: r.id, ref: null }); }, [updateURL]);
  const refKey = params.get("ref"), resourceKey = params.get("resource");
  useEffect(() => { if (refKey || resourceKey) setOpen(true); }, [refKey, resourceKey]);
  useEffect(() => {
    if (!refKey) { setReference(null); return; }
    const split = refKey.indexOf(":"); if (split < 0) return;
    const kind = refKey.slice(0, split), identity = refKey.slice(split + 1);
    setReference(previous => previous?.id === identity ? previous : { kind, id: identity, line: Number(params.get("line")) || null });
    setSourceError(""); const c = new AbortController();
    if (kind === "passage") {
      apiGet<{ text: string; page: number | null; document_id: string; paper_uid: string }>(`/api/learning/evidence/${encodeURIComponent(identity)}`, undefined, c.signal).then(p => { if (!c.signal.aborted) setReference({ kind, id: identity, quote: p.text, page: p.page, document_id: p.document_id, paper_uid: p.paper_uid }); }).catch(e => { if (!c.signal.aborted) setSourceError(String(e)); });
    } else if ((kind === "evidence" || kind === "fact") && scope === "project") {
      apiGet<{ evidence: { id: string; quote?: string; paper_uid?: string; document_id?: string; document_version?: string; locator?: { page?: number } }[]; methods: { id: string; field_evidence: { evidence_ids: string[] }[] }[]; experiment_settings: { id: string; field_evidence: { evidence_ids: string[] }[] }[]; measurements: { id: string; field_evidence: { evidence_ids: string[] }[] }[] }>(`/api/projects/${id}/facts`, undefined, c.signal).then(f => {
        if (c.signal.aborted) return;
        const fact = [...f.methods, ...f.experiment_settings, ...f.measurements].find(x => x.id === identity);
        const ev = f.evidence.find(e => e.id === (kind === "fact" ? fact?.field_evidence.flatMap(x => x.evidence_ids)[0] : identity));
        if (ev) setReference({ kind: "evidence", id: ev.id, quote: ev.quote, paper_uid: ev.paper_uid, document_id: ev.document_id, document_version: ev.document_version, page: ev.locator?.page });
        else { setReference({ kind, id: identity }); setSourceError("此项没有可读取的原文绑定，可继续查看资源或补充来源。"); }
      }).catch(e => { if (!c.signal.aborted) setSourceError(String(e)); });
    } else setReference(previous => previous?.id === identity ? previous : { kind, id: identity, line: Number(params.get("line")) || null });
    return () => c.abort();
  }, [refKey, scope, id]);
  useEffect(() => {
    if (resourceKey) setResource(resources.find(r => r.id === resourceKey) || null);
  }, [resources, resourceKey]);
  const selectedResource = reference ? resources.find(r => (r.id === reference.document_id && !!reference.page && (!reference.document_version || reference.document_version.replace(/^sha256:/, "") === r.version.replace(/^sha256:/, ""))) || (reference.kind === "source" && r.id === reference.id)) || null : resource;
  const versionMismatch = !!reference?.document_version && resources.some(r=>r.id===reference.document_id && r.version.replace(/^sha256:/, "")!==reference.document_version!.replace(/^sha256:/, ""));
  const go = (action: Action) => {
    const target = action.target;
    if (target.scope === scope && target.id === id) {
      const ref = action.references[0];
      updateURL({ tab: target.view === "learn" ? params.get("tab") || "reading" : target.view, focus: target.focus || null, ...(target.scope === "case" && target.view === "animation" ? {lab:"practice"} : {}), ...(ref ? { panel: "evidence", ref: `${ref.kind}:${ref.id}`, line: ref.line ? String(ref.line) : null } : {}) });
      if (ref) { setReference(ref); setOpen(true); }
      if (target.view === "animation") document.getElementById("atlas-interactive-lab")?.scrollIntoView({ behavior: "smooth", block: "start" });
    } else navigate(`${target.scope === "project" ? "/research" : target.scope === "paper" ? "/papers" : "/cases"}/${encodeURIComponent(target.id)}?tab=${target.view}`);
    setSearch(false);
  };
  const enhance = async () => {
    if (!report || explaining) return;
    const context = active.current; setExplaining(true);
    try { const r = await explainActions(scope, id, report, sid); if (context === active.current && latestFingerprint.current === report.input_fingerprint) setExplanations(Object.fromEntries(r.explanations.map(x => [x.action_id, x.text]))); }
    catch (e) { if (context === active.current) setError(String(e)); } finally { if (context === active.current) setExplaining(false); }
  };
  const content = <>
    <div className="atlas-inspector-head"><span className="atlas-eyebrow">上下文检查器</span><Button size="small" type="text" aria-label="关闭检查器" onClick={() => setOpen(false)}>×</Button></div>
    <Segmented block value={panel} onChange={value => { setOpen(true); updateURL({ panel: String(value) }); }} options={[{ label: "下一步", value: "coach" }, { label: "来源", value: "evidence" }, { label: "图文资源", value: "resources" }]} />
    <div className="atlas-inspector-body">
      {panel === "coach" && <><h3>现在可以做什么</h3><p className="atlas-muted">建议随资料与学习记录更新</p>{scope==="case"&&report&&<Tag color="cyan">交互练习答对 {report.coverage.practice_correct || 0} / 3</Tag>}{loading && !report && <Skeleton active paragraph={{ rows: 5 }} />}{error && <Alert type="warning" message={error} action={<Button size="small" onClick={refresh}>刷新</Button>} />}{report?.actions.slice(0, 6).map((a, i) => <button key={a.id} className="atlas-action-card" onClick={() => go(a)}><span className="atlas-action-index">{String(i + 1).padStart(2, "0")}</span><div><strong>{a.title}</strong><p>{a.reason}</p><small>{a.impact}</small>{explanations[a.id] && <p className="atlas-ai-explanation">AI 辅助解释：{explanations[a.id]}</p>}</div><span>↗</span></button>)}{report && !report.actions.length && <Empty description="当前规则未发现待处理项" />}{scope === "case" && !sid && <p>开始学习后，教练会根据你的作答更新建议。</p>}{!!report?.actions.length && <Button size="small" loading={explaining} onClick={() => void enhance()}>可选：AI 解释建议</Button>}{report && <p className="atlas-muted">{report.notice}</p>}</>}
      {panel === "evidence" && <><h3>来源定位</h3>{sourceError && <Alert type="info" message={sourceError} />}{!reference && <Empty description="点击图谱节点、字段依据或方案步骤" />}{reference && <><Tag>{reference.kind}</Tag><p className="atlas-id">{reference.id}</p>{!selectedResource && reference.quote && <blockquote className="atlas-quote">{reference.quote}</blockquote>}{versionMismatch && <Alert type="warning" message="引用与原文件版本不匹配，保留抽取文字，不进行精确高亮。" />}{reference.kind==="snapshot" && <p className="atlas-muted">历史快照 · {params.get("change") || "冻结资料与方案"}</p>}{reference.page && !versionMismatch ? <Tag>第 {reference.page} 页</Tag> : <p className="atlas-muted">没有可靠页码时保留文字定位</p>}</>}</>}
      {panel === "resources" && !resource && <><h3>图文与交互资源</h3>{resources.map(r => <button className="atlas-resource-card" key={r.id} onClick={() => openResource(r)}><span className={`atlas-resource-icon ${r.kind}`}>{r.kind === "pdf" ? "▤" : r.kind === "source" ? "⌘" : "◈"}</span><div><strong>{r.title}</strong><small>{r.origin === "illustrative" ? "教学示意" : r.origin === "source_repo" ? "固定源码" : "原始资料"} · {r.version.slice(0, 10)}</small>{!!r.tasks?.length && <small>适用：{r.tasks.join(" · ")}</small>}</div><span>↗</span></button>)}{!resources.length && <Empty description="关联原文后，资源将在这里出现" />}{error && <Alert type="warning" message={error} />}</>}
      {(panel === "evidence" || panel === "resources") && selectedResource && <div className="atlas-selected-resource"><Space wrap><Button size="small" onClick={() => { setResource(null); setReference(null); updateURL({ resource: null, ref: null, panel: "resources" }); }}>← 资源目录</Button><Tag>{selectedResource.origin === "illustrative" ? "教学示意" : "来源版本"}</Tag></Space><h4>{selectedResource.title}</h4>{selectedResource.kind === "pdf" ? <Suspense fallback={<Skeleton active />}><PdfReader key={selectedResource.id} resource={selectedResource} initialPage={Number(params.get("page")) || reference?.page || 1} quote={reference?.quote} onPageChange={p => updateURL({ page: String(p) }, true)} /></Suspense> : selectedResource.kind === "source" ? <SourceView text={selectedResource.text || ""} line={Number(params.get("line")) || reference?.line || selectedResource.line} /> : selectedResource.kind === "animation" ? selectedResource.id === "windows" ? <WindowAnimation /> : <TensorAnimation /> : <div className="atlas-evidence-diagram">{["原文资料", "方法与条件", "比较与选择", "可执行任务"].map((t, i) => <div key={t}><span>{i + 1}</span><strong>{t}</strong>{i < 3 && <b>↓</b>}</div>)}<p className="atlas-muted">教学示意：引用路径用于追溯输入。</p></div>}</div>}
    </div>
  </>;
  const api = useMemo(() => ({ available: true, inspect, openResource, refresh }), [inspect, openResource, refresh]);
  return <InspectorContext.Provider value={api}>
    <div className="atlas-workspace-toolbar"><div><span className="atlas-eyebrow">{scope === "project" ? "RESEARCH CANVAS" : scope === "paper" ? "READING STUDIO" : "INTERACTIVE LAB"}</span><span className="atlas-status-dot" />上下文联动</div><Space><Button size="small" onClick={() => setSearch(true)}>搜索资源 / 下一步 <kbd>⌘ K</kbd></Button><Button size="small" onClick={() => { setOpen(true); updateURL({ panel: "coach" }); }}>来源与教练</Button></Space></div>
    <div className={`atlas-workspace ${open ? "inspector-open" : ""}`} style={{ "--inspector-width": `${width}px` } as React.CSSProperties}>
      <main className="atlas-canvas">{children}</main><div className="atlas-resize-handle" role="separator" aria-label="调整检查器宽度" tabIndex={0} aria-valuemin={280} aria-valuemax={480} aria-valuenow={width} onKeyDown={e => { if (e.key === "ArrowLeft" || e.key === "ArrowRight") { const w = Math.max(280, Math.min(480, width + (e.key === "ArrowLeft" ? 20 : -20))); setWidth(w); write(`${storage}:width`, String(w)); } }} onPointerDown={e => { drag.current = true; e.currentTarget.setPointerCapture(e.pointerId); }} onPointerMove={e => { if (drag.current) { const w = Math.max(280, Math.min(480, window.innerWidth - e.clientX - 24)); setWidth(w); write(`${storage}:width`, String(w)); } }} onPointerUp={() => { drag.current = false; }} />
      {viewport >= 1280 && <aside className="atlas-inspector">{content}</aside>}
    </div>
    <Drawer className="atlas-mobile-inspector" title="来源与教练" open={open && viewport < 1280} onClose={() => setOpen(false)} placement={viewport < 768 ? "bottom" : "right"} height="82vh" width={Math.min(width, viewport)}>{viewport < 1280 && content}</Drawer>
    <Modal title="在当前工作空间中查找" open={search} onCancel={() => setSearch(false)} footer={null}><Input autoFocus value={query} onChange={e => setQuery(e.target.value)} placeholder="查找资源、缺口和下一步…" />{report?.actions.filter(a => `${a.title}${a.reason}`.includes(query)).slice(0, 6).map(a => <button className="atlas-search-result" key={a.id} onClick={() => go(a)}>{a.title} ↗</button>)}{resources.filter(r => r.title.toLowerCase().includes(query.toLowerCase())).slice(0, 6).map(r => <button className="atlas-search-result" key={r.id} onClick={() => { openResource(r); setSearch(false); }}>{r.title} ↗</button>)}</Modal>
  </InspectorContext.Provider>;
}
