import { useCallback, useEffect, useRef, useState } from "react";
import { Alert, Button, Input, InputNumber, Select, Space, Spin } from "antd";
import { FullscreenExitOutlined, FullscreenOutlined, MenuOutlined, SearchOutlined } from "@ant-design/icons";
import type { PDFDocumentProxy, PDFPageProxy, RenderTask } from "pdfjs-dist";
import type { Resource } from "../../api/assistant";
import ReadingExcerpt from "./ReadingExcerpt";
import "./pdf-reader.css";

type PageSize = { width: number; height: number };
type OutlineItem = { title: string; depth: number; dest: string | unknown[] | null };
type SearchHit = { page: number; count: number; snippet: string };
const normalizePage = (value: number, maximum = Number.MAX_SAFE_INTEGER) => Math.max(1, Math.min(Number.isFinite(value) ? Math.trunc(value) : 1, maximum));
const normalized = (value: string) => value.replace(/\s+/g, " ").trim();

function loadFailure(error: unknown) {
  const value = error as { status?: number; name?: string; message?: string };
  if (value?.status === 401 || value?.status === 403) return { message: "当前账号无法读取此 PDF", description: "请确认登录状态和资料所属账号，然后重新打开原文。" };
  if (value?.status === 409) return { message: "此文档版本的 PDF 无法核对", description: "当前保存的 PDF 不能替代这份历史解析版本。可重试，或明确打开当前保存的 PDF。" };
  if (value?.status === 404) return { message: "未找到此版本的 PDF 原文件", description: "原文链接对应的文件暂不可用。可重试，或打开当前保存的 PDF。" };
  if (value?.name === "PasswordException") return { message: "此 PDF 需要密码", description: "请用原文件入口打开，或上传可直接阅读的版本。" };
  return { message: "PDF 暂时无法显示", description: "原文件可能仍可打开。请重试阅读器，或通过原文件入口核对；已解析文字保留在下方。" };
}

function highlightText(layer: HTMLElement, query?: string | null) {
  if (!query?.trim()) return;
  const entries = Array.from(layer.querySelectorAll("span")).map(span => ({ span, text: normalized(span.textContent || "") }));
  const full = entries.map(entry => entry.text).join(" ").toLocaleLowerCase(), needle = normalized(query).toLocaleLowerCase();
  const ranges: number[] = [];
  for (let at = full.indexOf(needle); at >= 0; at = full.indexOf(needle, at + Math.max(1, needle.length))) ranges.push(at);
  let offset = 0;
  entries.forEach(({ span, text }) => {
    if (ranges.some(start => offset < start + needle.length && offset + text.length > start)) span.classList.add("atlas-pdf-match");
    offset += text.length + 1;
  });
}

function RenderedPage({ doc, page, scale, query }: { doc: PDFDocumentProxy; page: number; scale: number; query?: string | null }) {
  const canvas = useRef<HTMLCanvasElement>(null), text = useRef<HTMLDivElement>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let dead = false; let render: RenderTask | undefined; let pdfPage: PDFPageProxy | undefined; let layer: { cancel: () => void } | undefined;
    setError("");
    void doc.getPage(page).then(async p => {
      if (dead || !canvas.current || !text.current) return;
      pdfPage = p;
      const library = await import("pdfjs-dist");
      if (dead || !canvas.current || !text.current) return;
      const viewport = p.getViewport({ scale }), ratio = Math.min(window.devicePixelRatio || 1, 2), c = canvas.current;
      c.width = Math.ceil(viewport.width * ratio); c.height = Math.ceil(viewport.height * ratio);
      c.style.width = `${viewport.width}px`; c.style.height = `${viewport.height}px`;
      const context = c.getContext("2d"); if (!context) throw Error("浏览器无法显示 PDF 画布");
      render = p.render({ canvasContext: context, canvas: c, viewport, transform: ratio === 1 ? undefined : [ratio, 0, 0, ratio, 0, 0] });
      await render.promise;
      if (dead || !text.current) return;
      const content = await p.getTextContent();
      if (dead || !text.current) return;
      text.current.replaceChildren(); text.current.style.setProperty("--total-scale-factor", String(scale));
      const task = new library.TextLayer({ textContentSource: content, container: text.current, viewport }); layer = task;
      await task.render();
      if (!dead && text.current) highlightText(text.current, query);
    }).catch(e => { if (!dead && e?.name !== "RenderingCancelledException") setError("此页暂时无法渲染，请重试或查看原文片段。"); });
    return () => { dead = true; render?.cancel(); layer?.cancel(); pdfPage?.cleanup(); };
  }, [doc, page, scale, query]);
  return <>{error && <Alert type="warning" message={error} />}<canvas ref={canvas} aria-label={`第 ${page} 页内容`} /><div ref={text} className="textLayer" /></>;
}

export interface PdfReaderProps {
  resource: Resource;
  initialPage?: number;
  quote?: string | null;
  onPageChange?: (page: number) => void;
  /** [left, top, right, bottom], unscaled PDF points with a top-left origin. */
  bbox?: readonly number[] | null;
  targetPage?: number;
}

export default function PdfReader({ resource, initialPage = 1, quote, onPageChange, bbox, targetPage }: PdfReaderProps) {
  const host = useRef<HTMLDivElement>(null), pages = useRef<HTMLDivElement>(null);
  const [doc, setDoc] = useState<PDFDocumentProxy>(), [sizes, setSizes] = useState<PageSize[]>([]), [error, setError] = useState("");
  const [errorDetail, setErrorDetail] = useState("");
  const [reload, setReload] = useState(0), [page, setPage] = useState(() => normalizePage(targetPage || initialPage));
  const [width, setWidth] = useState(640), [viewportWidth, setViewportWidth] = useState<number>(), [readerHeight, setReaderHeight] = useState(600);
  const [zoom, setZoom] = useState<"fit" | number>("fit"), [expanded, setExpanded] = useState(false);
  const [outline, setOutline] = useState<OutlineItem[]>([]), [outlineOpen, setOutlineOpen] = useState(false);
  const [activePages, setActivePages] = useState<Set<number>>(() => new Set([normalizePage(initialPage)]));
  const [search, setSearch] = useState(""), [searchQuery, setSearchQuery] = useState("");
  const [hits, setHits] = useState<SearchHit[]>([]), [hitIndex, setHitIndex] = useState(0), [searching, setSearching] = useState(false), [searchError, setSearchError] = useState("");
  const pageRef = useRef(page), onPageRef = useRef(onPageChange), lastNotified = useRef<number | null>(null);
  const searchGeneration = useRef(0), textCache = useRef(new Map<number, string>()), docGeneration = useRef(0);
  const focusedBox = useRef("");
  const scrollTimer = useRef<ReturnType<typeof setTimeout>>();
  pageRef.current = page; onPageRef.current = onPageChange;

  useEffect(() => {
    let dead = false; let loadingTask: { destroy: () => Promise<void> } | undefined;
    const generation = ++docGeneration.current;
    setDoc(undefined); setSizes([]); setViewportWidth(undefined); setError(""); setErrorDetail(""); setOutline([]); setHits([]); setSearchQuery(""); setSearch(""); setSearchError(""); setSearching(false);
    textCache.current.clear(); searchGeneration.current++; lastNotified.current = null; focusedBox.current = "";
    void Promise.all([import("pdfjs-dist"), import("pdfjs-dist/build/pdf.worker.min.mjs?url")]).then(async ([pdf, worker]) => {
      if (dead) return;
      if (!resource.url) throw new Error("没有 PDF 文件地址");
      pdf.GlobalWorkerOptions.workerSrc = worker.default;
      const base = new URL("/pdf-assets/", window.location.origin).href;
      const task = pdf.getDocument({ url: resource.url, cMapUrl: `${base}cmaps/`, cMapPacked: true, standardFontDataUrl: `${base}standard_fonts/`, wasmUrl: `${base}wasm/` });
      loadingTask = task;
      const loaded = await task.promise;
      if (dead) return;
      // Read geometry only here. Canvas and text rendering stay lazy.
      const dimensions: PageSize[] = new Array(loaded.numPages); let next = 1;
      await Promise.all(Array.from({ length: Math.min(4, loaded.numPages) }, async () => {
        while (!dead && next <= loaded.numPages) {
          const number = next++, pdfPage = await loaded.getPage(number), viewport = pdfPage.getViewport({ scale: 1 });
          dimensions[number - 1] = { width: viewport.width, height: viewport.height };
        }
      }));
      if (dead || generation !== docGeneration.current) return;
      const first = normalizePage(targetPage || initialPage, loaded.numPages);
      setSizes(dimensions); setPage(first); pageRef.current = first;
      setActivePages(new Set([first, Math.max(1, first - 1), Math.min(loaded.numPages, first + 1)])); setDoc(loaded);
      if (typeof loaded.getOutline === "function") void loaded.getOutline().then(items => {
        if (dead) return;
        const result: OutlineItem[] = [];
        const walk = (nodes: NonNullable<typeof items>, depth: number) => nodes.forEach(item => {
          result.push({ title: item.title || "未命名章节", depth, dest: item.dest as OutlineItem["dest"] });
          if (item.items?.length) walk(item.items, depth + 1);
        });
        if (items) walk(items, 0); setOutline(result);
      }).catch(() => undefined);
    }).catch(cause => { if (!dead) { const failure = loadFailure(cause); setError(failure.message); setErrorDetail(failure.description); } });
    return () => { dead = true; searchGeneration.current++; clearTimeout(scrollTimer.current); void Promise.resolve(loadingTask?.destroy()).catch(() => undefined); };
    // Navigation updates below without reloading the PDF.
  }, [resource.id, resource.url, reload]);

  useEffect(() => {
    if (!host.current) return;
    const measureHeight = () => {
      const top = pages.current?.getBoundingClientRect().top ?? host.current?.getBoundingClientRect().top ?? 120;
      setReaderHeight(Math.max(280, window.innerHeight - Math.max(0, top) - 24));
    };
    const observer = new ResizeObserver(entries => {
      entries.forEach(entry => {
        if (entry.contentRect.width <= 0) return;
        if (entry.target && entry.target === pages.current) setViewportWidth(entry.contentRect.width);
        else setWidth(entry.contentRect.width);
      });
      measureHeight();
    });
    observer.observe(host.current); if (pages.current) observer.observe(pages.current);
    measureHeight(); window.addEventListener("resize", measureHeight);
    const frame = requestAnimationFrame(measureHeight);
    return () => { observer.disconnect(); window.removeEventListener("resize", measureHeight); cancelAnimationFrame(frame); };
  }, [resource.id, doc, expanded, outlineOpen]);

  const notify = useCallback((next: number) => {
    if (lastNotified.current === next) return;
    lastNotified.current = next; onPageRef.current?.(next);
  }, []);
  const jump = useCallback((number: number, announce = true) => {
    if (!doc) return;
    const next = normalizePage(number, doc.numPages); pageRef.current = next; setPage(next);
    setActivePages(old => new Set([...old, next, Math.max(1, next - 1), Math.min(doc.numPages, next + 1)]));
    const viewport = pages.current, selected = viewport?.querySelector<HTMLElement>(`[data-pdf-page="${next}"]`);
    if (viewport && selected) viewport.scrollTop = Math.max(0, selected.offsetTop - 12);
    if (announce) notify(next);
  }, [doc, notify]);
  useEffect(() => {
    if (!doc) return;
    const next = normalizePage(targetPage || initialPage, doc.numPages);
    const boxKey = bbox?.length === 4 && bbox.every(Number.isFinite) ? `${next}:${bbox.join(",")}` : "";
    const focusChanged = boxKey && focusedBox.current !== boxKey;
    // Saved-position callbacks echo the current page; do not snap while scrolling.
    if (next !== pageRef.current || lastNotified.current === null || focusChanged) jump(next, false);
    if (focusChanged && pages.current && bbox) {
      const selected = pages.current.querySelector<HTMLElement>(`[data-pdf-page="${next}"]`), size = sizes[next - 1];
      if (selected && size) {
        const actualScale = selected.getBoundingClientRect().width / size.width;
        pages.current.scrollTop = Math.max(0, selected.offsetTop + Math.min(bbox[1], bbox[3]) * actualScale - pages.current.clientHeight / 4);
      }
    }
    focusedBox.current = boxKey;
  }, [doc, initialPage, targetPage, jump, bbox?.join(",")]);

  useEffect(() => {
    if (!doc || !pages.current || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(entries => setActivePages(old => {
      const next = new Set(old);
      entries.forEach(entry => { const number = Number((entry.target as HTMLElement).dataset.pdfPage); if (entry.isIntersecting) next.add(number); else next.delete(number); });
      return next;
    }), { root: pages.current, rootMargin: "600px 0px", threshold: 0 });
    pages.current.querySelectorAll("[data-pdf-page]").forEach(element => observer.observe(element));
    return () => observer.disconnect();
  }, [doc]);
  useEffect(() => {
    const change = () => setExpanded(window.document.fullscreenElement === host.current);
    const escape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      if (window.document.fullscreenElement === host.current) void Promise.resolve(window.document.exitFullscreen?.()).catch(() => setExpanded(false));
      else if (!window.document.fullscreenElement) setExpanded(false);
    };
    window.document.addEventListener("fullscreenchange", change); window.addEventListener("keydown", escape);
    return () => { window.document.removeEventListener("fullscreenchange", change); window.removeEventListener("keydown", escape); };
  }, []);

  function onScroll() {
    clearTimeout(scrollTimer.current);
    scrollTimer.current = setTimeout(() => {
      const viewport = pages.current; if (!viewport || !doc) return;
      const point = viewport.scrollTop + Math.min(120, viewport.clientHeight / 4); let current = 1;
      for (const element of viewport.querySelectorAll<HTMLElement>("[data-pdf-page]")) { if (element.offsetTop <= point) current = Number(element.dataset.pdfPage); else break; }
      if (current !== pageRef.current) { pageRef.current = current; setPage(current); notify(current); }
      if (typeof IntersectionObserver === "undefined") setActivePages(new Set([current, Math.max(1, current - 1), Math.min(doc.numPages, current + 1)]));
    }, 140);
  }
  async function searchDocument(value: string) {
    const query = normalized(value), generation = ++searchGeneration.current;
    setSearchQuery(query); setHits([]); setHitIndex(0); setSearchError("");
    if (!query || !doc) { setSearching(false); return; }
    setSearching(true);
    try {
      const found: SearchHit[] = [];
      for (let number = 1; number <= doc.numPages; number++) {
        if (generation !== searchGeneration.current) return;
        let text = textCache.current.get(number);
        if (text === undefined) {
          const pdfPage = await doc.getPage(number), content = await pdfPage.getTextContent();
          if (generation !== searchGeneration.current) return;
          text = normalized(content.items.filter(item => "str" in item).map(item => "str" in item ? item.str : "").join(" "));
          textCache.current.set(number, text);
        }
        const lowered = text.toLocaleLowerCase(), needle = query.toLocaleLowerCase(); let count = 0, first = -1;
        for (let at = lowered.indexOf(needle); at >= 0; at = lowered.indexOf(needle, at + needle.length)) { if (first < 0) first = at; count++; }
        if (count) found.push({ page: number, count, snippet: text.slice(Math.max(0, first - 45), first + needle.length + 75) });
      }
      if (generation !== searchGeneration.current) return;
      setHits(found); if (found.length) jump(found[0].page);
    } catch { if (generation === searchGeneration.current) setSearchError("全文搜索暂时失败，请重试。扫描页需要先有文字层。"); }
    finally { if (generation === searchGeneration.current) setSearching(false); }
  }
  function moveHit(offset: number) {
    if (!hits.length) return;
    const index = (hitIndex + offset + hits.length) % hits.length; setHitIndex(index); jump(hits[index].page);
  }
  async function openOutline(item: OutlineItem) {
    if (!doc || !item.dest) return;
    try {
      const destination = typeof item.dest === "string" ? await doc.getDestination(item.dest) : item.dest;
      if (!destination?.length) return;
      const reference = destination[0], index = typeof reference === "number" ? reference : await doc.getPageIndex(reference as Parameters<PDFDocumentProxy["getPageIndex"]>[0]);
      jump(index + 1);
    } catch { setSearchError("此目录项无法定位，可以使用页码或全文搜索。"); }
  }
  async function toggleFullscreen() {
    if (expanded) { if (window.document.fullscreenElement === host.current) await window.document.exitFullscreen?.(); setExpanded(false); return; }
    try { await host.current?.requestFullscreen?.(); } catch { /* Embedded browsers may use expanded mode. */ }
    setExpanded(true);
  }

  const available = Math.max(80, viewportWidth ?? width - (outlineOpen ? Math.min(260, width * 0.32) : 0) - 24);
  const highlightPage = normalizePage(targetPage || initialPage, doc?.numPages);
  const sectionTitles = new Set<string>();
  const parsedOutline: OutlineItem[] = resource.passages.flatMap(passage => {
    const title = passage.heading?.trim();
    if (!passage.page || !title || sectionTitles.has(title) || /^(?:page\s*\d+|第\s*\d+\s*页|text|正文)$/i.test(title)) return [];
    sectionTitles.add(title); return [{ title, depth: 0, dest: [passage.page - 1] }];
  });
  const navigationOutline = outline.length ? outline : parsedOutline;
  return <div ref={host} className={`atlas-reader ps-continuous-reader${expanded ? " is-expanded" : ""}`} style={{ "--ps-reader-height": `${readerHeight}px` } as React.CSSProperties} aria-label="PDF 阅读器">
    <div className="atlas-reader-controls ps-pdf-toolbar"><Space wrap>
      <Button size="small" aria-label="目录" icon={<MenuOutlined aria-hidden />} aria-pressed={outlineOpen} onClick={() => setOutlineOpen(value => !value)} disabled={!doc}>目录</Button>
      <Button size="small" disabled={!doc || page <= 1} onClick={() => jump(page - 1)}>上一页</Button>
      <InputNumber aria-label="PDF 页码" size="small" disabled={!doc} precision={0} min={1} max={doc?.numPages || 1} value={page} onChange={value => value !== null && jump(value)} onBlur={event => { if (!event.target.value) event.target.value = String(pageRef.current); }} />
      <span className="ps-pdf-page-count">/ {doc?.numPages || "—"}</span>
      <Button size="small" disabled={!doc || page >= doc.numPages} onClick={() => jump(page + 1)}>下一页</Button>
      <Select<"fit" | number> aria-label="PDF 缩放" size="small" value={zoom} onChange={setZoom} options={[{ value: "fit", label: "适应宽度" }, { value: 0.75, label: "75%" }, { value: 1, label: "100%" }, { value: 1.5, label: "150%" }, { value: 2, label: "200%" }]} />
      <Button size="small" aria-label={expanded ? "退出全屏" : "全屏"} icon={expanded ? <FullscreenExitOutlined aria-hidden /> : <FullscreenOutlined aria-hidden />} onClick={() => void toggleFullscreen()}>{expanded ? "退出全屏" : "全屏"}</Button>
    </Space><Input.Search aria-label="搜索论文全文" placeholder="搜索论文全文" value={search} onChange={event => setSearch(event.target.value)} onSearch={value => void searchDocument(value)} disabled={!doc} loading={searching} allowClear enterButton={<SearchOutlined aria-label="搜索" />} /></div>
    {quote && <details className="ps-pdf-citation"><summary>定位依据片段</summary><ReadingExcerpt text={quote} compact /></details>}
    {searchQuery && <div className="ps-pdf-search-status" role="status" aria-live="polite">{searching ? "正在搜索全文…" : hits.length ? <><span>{hits.reduce((sum, hit) => sum + hit.count, 0)} 处匹配，分布于 {hits.length} 页；当前第 {hits[hitIndex]?.page} 页</span><Button size="small" onClick={() => moveHit(-1)}>上一匹配页</Button><Button size="small" onClick={() => moveHit(1)}>下一匹配页</Button><span className="ps-pdf-search-snippet">{hits[hitIndex]?.snippet}</span></> : "未找到匹配文字。扫描件需要先完成文字识别。"}</div>}
    {searchError && <Alert type="warning" message={searchError} closable onClose={() => setSearchError("")} />}
    {!doc && !error && <Spin tip="加载原文与页面尺寸…"><div style={{ minHeight: 280 }} /></Spin>}
    {error ? <div className="ps-pdf-load-error"><Alert type="warning" showIcon message={error} description={errorDetail} action={<Space wrap><Button size="small" onClick={() => setReload(value => value + 1)}>重试原文</Button>{(resource.current_file_url || resource.url) && <Button size="small" href={resource.current_file_url || resource.url} target="_blank" rel="noreferrer">{resource.current_file_url ? "打开当前保存的 PDF" : "打开原文件"}</Button>}</Space>} />{!!resource.passages.length && <details className="ps-pdf-saved-text"><summary>查看已解析文字（{resource.passages.length} 段）</summary><p>解析文字用于检索和定位，公式、上下标及表格请以相应版本的原文为准。</p><div>{resource.passages.map(passage => <section key={passage.id}>{passage.heading && <h4>{passage.heading}{passage.page ? ` · 第 ${passage.page} 页` : ""}</h4>}<p>{passage.text}</p></section>)}</div></details>}</div> : doc && <div className="ps-pdf-layout">
      {outlineOpen && <nav className="ps-pdf-outline" aria-label="论文目录">{navigationOutline.length ? navigationOutline.map((item, index) => <button key={index} type="button" style={{ paddingInlineStart: `${12 + Math.min(item.depth, 6) * 12}px` }} onClick={() => void openOutline(item)}>{item.title}</button>) : <p>此 PDF 暂无可用目录。可以使用页码或全文搜索定位。</p>}</nav>}
      <div ref={pages} className="atlas-pdf-pages" aria-label="连续阅读页面" onScroll={onScroll} tabIndex={0}>
        {sizes.map((size, index) => {
          const number = index + 1, scale = zoom === "fit" ? available / size.width : zoom;
          const box = number === highlightPage && bbox?.length === 4 && bbox.every(Number.isFinite) ? bbox : null;
          return <section key={`${resource.id}:${number}`} className="atlas-pdf-page" data-pdf-page={number} aria-label={`PDF 第 ${number} 页`} style={{ width: size.width * scale, height: size.height * scale }}>
            <span className="atlas-page-label">第 {number} 页</span>
            {activePages.has(number) ? <RenderedPage doc={doc} page={number} scale={scale} query={searchQuery || (number === highlightPage ? quote : undefined)} /> : <div className="ps-pdf-placeholder">第 {number} 页</div>}
            {box && <div className="ps-pdf-source-box" aria-label="原文定位区域" style={{ left: Math.min(box[0], box[2]) * scale, top: Math.min(box[1], box[3]) * scale, width: Math.abs(box[2] - box[0]) * scale, height: Math.abs(box[3] - box[1]) * scale }} />}
          </section>;
        })}
      </div>
    </div>}
  </div>;
}
