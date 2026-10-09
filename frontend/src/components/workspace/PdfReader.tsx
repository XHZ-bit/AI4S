import { useEffect, useRef, useState } from "react";
import { Alert, Button, InputNumber, Select, Space, Spin } from "antd";
import type { PDFDocumentProxy, PDFPageProxy, RenderTask } from "pdfjs-dist";
import type { Resource } from "../../api/assistant";

function Page({ doc, page, scale, quote }: { doc: PDFDocumentProxy; page: number; scale: number; quote?: string | null }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const text = useRef<HTMLDivElement>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let dead = false; let render: RenderTask | undefined; let pdfPage: PDFPageProxy | undefined; let layer: { cancel: () => void } | undefined;
    void doc.getPage(page).then(async p => {
      if (dead || !canvas.current || !text.current) return;
      pdfPage = p;
      const library = await import("pdfjs-dist");
      if (dead || !canvas.current || !text.current) return;
      const viewport = p.getViewport({ scale }); const ratio = Math.min(window.devicePixelRatio || 1, 2);
      const c = canvas.current; c.width = viewport.width * ratio; c.height = viewport.height * ratio;
      c.style.width = `${viewport.width}px`; c.style.height = `${viewport.height}px`;
      const context = c.getContext("2d"); if (!context) throw Error("浏览器无法显示 PDF 画布");
      render = p.render({ canvasContext: context, canvas: c, viewport, transform: ratio === 1 ? undefined : [ratio, 0, 0, ratio, 0, 0] });
      await render.promise;
      if (dead || !text.current) return;
      text.current.replaceChildren(); text.current.style.setProperty("--total-scale-factor", String(scale));
      const task = new library.TextLayer({ textContentSource: await p.getTextContent(), container: text.current, viewport }); layer = task;
      await task.render();
      if (!dead && quote && text.current) {
        const spans = Array.from(text.current.querySelectorAll("span"));
        const entries = spans.map(span => ({ span, value: (span.textContent || "").replace(/\s+/g, " ").trim() }));
        const all = entries.map(e => e.value).join(" "), exact = quote.replace(/\s+/g, " ").trim();
        const found = all.indexOf(exact);
        if (found >= 0 && all.indexOf(exact, found + 1) < 0) {
          let offset = 0;
          entries.forEach(e => { if (offset < found + exact.length && offset + e.value.length > found) e.span.classList.add("atlas-pdf-match"); offset += e.value.length + 1; });
        }
      }
    }).catch(e => { if (!dead && e.name !== "RenderingCancelledException") setError("PDF 页面无法渲染，请使用原文片段"); });
    return () => { dead = true; render?.cancel(); layer?.cancel(); pdfPage?.cleanup(); };
  }, [doc, page, scale, quote]);
  return <div className="atlas-pdf-page" data-pdf-page={page}><span className="atlas-page-label">第 {page} 页</span>{error && <Alert type="warning" message={error} />}<canvas ref={canvas} /><div ref={text} className="textLayer" /></div>;
}

export default function PdfReader({ resource, initialPage = 1, quote, onPageChange }: { resource: Resource; initialPage?: number; quote?: string | null; onPageChange?: (page: number) => void }) {
  const [doc, setDoc] = useState<PDFDocumentProxy>(); const [error, setError] = useState("");
  const [page, setPage] = useState(initialPage); const [scale, setScale] = useState(0.6);
  const host = useRef<HTMLDivElement>(null);
  useEffect(() => { setPage(initialPage); }, [initialPage]);
  useEffect(() => {
    let dead = false; let task: { destroy: () => Promise<void> } | undefined;
    setDoc(undefined); setError("");
    void Promise.all([import("pdfjs-dist"), import("pdfjs-dist/build/pdf.worker.min.mjs?url")]).then(async ([pdf, worker]) => {
      if (dead) return;
      pdf.GlobalWorkerOptions.workerSrc = worker.default;
      const base = new URL("/pdf-assets/", window.location.origin).href;
      const loading = pdf.getDocument({ url: resource.url!, cMapUrl: `${base}cmaps/`, cMapPacked: true, standardFontDataUrl: `${base}standard_fonts/`, wasmUrl: `${base}wasm/` }); task = loading;
      const loaded = await loading.promise;
      if (!dead) { setDoc(loaded); setPage(p=>Math.max(1,Math.min(p,loaded.numPages))); } else await loading.destroy();
    }).catch(() => { if (!dead) setError("PDF 原文件缺失、损坏或与版本不匹配，已保留抽取原文。扫描件可能没有可选文字。"); });
    return () => { dead = true; void task?.destroy(); };
  }, [resource.id, resource.url]);
  useEffect(() => {
    if (!host.current) return;
    const observer = new ResizeObserver(([entry]) => setScale(Math.max(0.25, Math.min(1.4, (entry.contentRect.width - 24) / 612))));
    observer.observe(host.current); return () => observer.disconnect();
  }, [resource.id]);
  useEffect(() => {
    if (!doc) return;
    const p = Math.max(1, Math.min(page, doc.numPages));
    const pages = host.current?.querySelector<HTMLElement>(".atlas-pdf-pages");
    const selected = pages?.querySelector<HTMLElement>(`[data-pdf-page="${p}"]`);
    if (pages && selected) pages.scrollTop = selected.offsetTop;
  }, [doc, page]);
  const move = (p: number) => { const next = Math.max(1, Math.min(p, doc?.numPages || 1)); setPage(next); onPageChange?.(next); };
  return <div ref={host} className="atlas-reader">
    <Space wrap className="atlas-reader-controls"><Button size="small" disabled={!doc || page <= 1} onClick={() => move(page - 1)}>上一页</Button><InputNumber aria-label="PDF 页码" size="small" min={1} max={doc?.numPages || 1} value={page} onChange={v => v && move(v)} /><span>/ {doc?.numPages || "—"}</span><Button size="small" disabled={!doc || page >= doc.numPages} onClick={() => move(page + 1)}>下一页</Button><Select aria-label="PDF 缩放" size="small" value={scale} onChange={setScale} options={[{ value: scale, label: "适应宽度" }, { value: 0.75, label: "75%" }, { value: 1, label: "100%" }, { value: 1.5, label: "150%" }]} /></Space>
    {quote && <blockquote className="atlas-quote">{quote}</blockquote>}
    {!doc && !error && <Spin tip="加载图文…"><div style={{ height: 80 }} /></Spin>}
    {error ? <><Alert type="info" message={error} />{resource.passages.map(p => <section key={p.id}><h4>{p.heading}</h4><p style={{ whiteSpace: "pre-wrap" }}>{p.text}</p></section>)}</> : doc && <div className="atlas-pdf-pages">{Array.from({ length: Math.min(3, doc.numPages) }, (_, i) => Math.max(1, Math.min(page - 1, doc.numPages - 2)) + i).map(p => <Page key={`${resource.id}:${p}`} doc={doc} page={p} scale={scale} quote={p === page ? quote : null} />)}</div>}
  </div>;
}
