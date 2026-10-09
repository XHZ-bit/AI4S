import { lazy, Suspense, useEffect, useState } from "react";
import { Alert, Card, Skeleton } from "antd";
import { useSearchParams } from "react-router-dom";
import { getResources, type Resource } from "../../api/assistant";
const PdfReader = lazy(() => import("./PdfReader"));
export default function PaperReader({ uid }: { uid: string }) {
  const [resources, setResources] = useState<Resource[]>([]), [error, setError] = useState("");
  const [params, setParams] = useSearchParams();
  useEffect(() => { const c = new AbortController(); getResources("paper", uid, c.signal).then(r => { if (!c.signal.aborted) setResources(r.items || []); }).catch(e => { if (!c.signal.aborted) setError(String(e)); }); return () => c.abort(); }, [uid]);
  const resource = resources.find(r => r.kind === "pdf");
  return <Card title="图文阅读" extra={<span className="atlas-muted">原文 · 可选择文本</span>}>{error && <Alert type="info" message={error} />}{resource ? <Suspense fallback={<Skeleton active />}><PdfReader resource={resource} initialPage={Number(params.get("page")) || 1} onPageChange={p => setParams(old => { const n = new URLSearchParams(old); n.set("page", String(p)); return n; }, { replace: true })} /></Suspense> : <p className="atlas-muted">解析原文后即可使用图文阅读；现有学习任务仍可继续。</p>}</Card>;
}
