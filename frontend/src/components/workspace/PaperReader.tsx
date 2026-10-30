import ReadingActions from "../workbench/ReadingActions";
import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { Alert, Button, Card, Skeleton } from "antd";
import { useSearchParams } from "react-router-dom";
import { getResources, type Resource } from "../../api/assistant";
import { getReadingPosition, saveReadingPosition } from "../../api/readingPosition";
const PdfReader = lazy(() => import("./PdfReader"));

const validPage = (value: string | null) => value && /^\d+$/.test(value) && Number.isSafeInteger(Number(value)) && Number(value) > 0 ? Number(value) : null;

function SavedPdfReader({ uid, resource }: { uid: string; resource: Resource }) {
  const [params, setParams] = useSearchParams();
  const paramsRef = useRef(params); paramsRef.current = params;
  const [loading, setLoading] = useState(true), [loadError, setLoadError] = useState("");
  const [reload, setReload] = useState(0), [saveError, setSaveError] = useState("");
  const [saveState, setSaveState] = useState("翻页时自动保存阅读位置，不改变阅读任务完成状态。");
  const pending = useRef<number | null>(null), writing = useRef(false);
  const lifetime = useRef<AbortController>();
  const documentId = resource.document_id || resource.id;

  useEffect(() => {
    const controller = new AbortController(); lifetime.current = controller;
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setLoadError("");
    if(!resource.document_id){setLoading(false);return ()=>controller.abort();}
    void getReadingPosition(uid, documentId, controller.signal).then(({ position }) => {
      if (controller.signal.aborted) return;
      // An explicit evidence link always wins, including a link to page one.
      if (position && !validPage(paramsRef.current.get("page"))) {
        setParams(old => { if (validPage(old.get("page"))) return old; const next = new URLSearchParams(old); next.set("page", String(position.page)); return next; }, { replace: true });
        setSaveState(`已恢复上次阅读位置：第 ${position.page} 页。`);
      }
    }).catch(error => { if (!controller.signal.aborted) setLoadError(`无法读取上次阅读位置：${String(error)}`); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [uid, documentId, reload]);

  async function flush() {
    if (writing.current || lifetime.current?.signal.aborted) return;
    writing.current = true;
    try {
      while (pending.current !== null && !lifetime.current?.signal.aborted) {
        const page = pending.current; pending.current = null;
        setSaveError(""); setSaveState("正在保存阅读位置…");
        try {
          await saveReadingPosition(uid, documentId, page, lifetime.current?.signal);
          if (!lifetime.current?.signal.aborted) setSaveState(`阅读位置已保存：第 ${page} 页。`);
        } catch (error) {
          if (!lifetime.current?.signal.aborted) {
            // Keep a newer navigation choice if one arrived during this write.
            if (pending.current === null) pending.current = page;
            setSaveError(`阅读位置保存失败，当前页仍可阅读：${String(error)}`);
            setSaveState("当前阅读位置尚未保存。");
          }
          break;
        }
      }
    } finally { writing.current = false; }
  }

  function move(page: number) {
    setParams(old => { const next = new URLSearchParams(old); next.set("page", String(page)); return next; }, { replace: true });
    if(resource.document_id){pending.current = page; void flush();}
  }

  return <>
    {loadError && <Alert type="warning" message={loadError} action={<Button size="small" onClick={() => setReload(value => value + 1)}>重试读取位置</Button>} />}
    {loading ? <Skeleton active paragraph={{ rows: 2 }} /> : <Suspense fallback={<Skeleton active />}><PdfReader resource={resource} initialPage={validPage(params.get("page")) || 1} onPageChange={move} /></Suspense>}
    {saveError && <Alert type="warning" message={saveError} action={<Button size="small" onClick={() => void flush()}>重试保存位置</Button>} />}
    <p className="atlas-muted" role="status" aria-live="polite">{saveState}</p>
  </>;
}

function PaperReaderSession({ uid }: { uid: string }) {
  const [params] = useSearchParams();
  const [resources, setResources] = useState<Resource[]>([]), [error, setError] = useState("");
  const [loading, setLoading] = useState(true), [reload, setReload] = useState(0);
  useEffect(() => {
    const controller = new AbortController(); setResources([]); setError(""); setLoading(true);
    void getResources("paper", uid, controller.signal).then(result => { if (!controller.signal.aborted) setResources(result.items || []); })
      .catch(error => { if (!controller.signal.aborted) setError(String(error)); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [uid, reload]);
  const requestedDocument = params.get("document_id");
  const pdfs = resources.filter(item => item.kind === "pdf");
  const resource = requestedDocument ? pdfs.find(item => item.document_id === requestedDocument) : pdfs.find(item => item.file_available !== false) || pdfs[0];
  useEffect(()=>{if(loading||error||requestedDocument||resource?.document_id||reload>=30)return;const timer=setTimeout(()=>setReload(v=>v+1),2000);return()=>clearTimeout(timer)},[loading,error,requestedDocument,resource,reload]);
  return <ReadingActions uid={uid} documentId={resource?.document_id||resource?.id} documentVersion={resource?.version}><section className="ps-paper-reader" aria-label="论文原文">
    {error && <Alert type="warning" message="无法加载图文资源" description={error} action={<Button onClick={() => setReload(value => value + 1)}>重试图文资源</Button>} />}
    {loading ? <Skeleton active /> : resource ? <SavedPdfReader key={`${resource.id}:${resource.version}`} uid={uid} resource={resource} /> : !error && (requestedDocument ? <Alert type="warning" message="链接中的文档版本暂不可用" description="没有自动切换到另一版本，以保留原文证据的准确位置。" action={<Button href={`/api/papers/${encodeURIComponent(uid)}/file`} target="_blank" rel="noreferrer">打开当前保存的 PDF</Button>} /> : <p className="atlas-muted">尚无可读取的本地 PDF，请先保存原文。<Button size="small" onClick={()=>setReload(v=>v+1)}>刷新图文资源</Button></p>)}
  </section></ReadingActions>;
}

export default function PaperReader({ uid }: { uid: string }) {
  // Replacing the paper immediately unmounts private resource and request state.
  return <PaperReaderSession key={uid} uid={uid} />;
}
