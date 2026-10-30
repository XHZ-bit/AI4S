import { useEffect, useState } from "react";
import { Alert, Button } from "antd";
import { Link } from "react-router-dom";
import { BookOutlined } from "@ant-design/icons";
import { listLibraryPapers, type LibraryPaper } from "../api/library";

export default function ReadLaterPreview() {
  const [papers, setPapers] = useState<LibraryPaper[]>([]), [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let controller: AbortController | undefined;
    function load() {
      controller?.abort();
      const request = new AbortController(); controller = request;
      listLibraryPapers({ filter: "read_later", limit: 3 }, request.signal)
        .then(result => { if (!request.signal.aborted) { setPapers(result.items.slice(0, 3)); setError(""); } })
        .catch(caught => { if (!request.signal.aborted) setError(String(caught)); });
    }
    function changed(event: Event) {
      const path = (event as CustomEvent<{ path?: string }>).detail?.path;
      if (!path || path.startsWith("/api/library/")) load();
    }
    load(); window.addEventListener("atlas:data-change", changed);
    return () => { controller?.abort(); window.removeEventListener("atlas:data-change", changed); };
  }, [retry]);
  if (!papers.length && !error) return null;
  return <section className="home-panel home-readlater" aria-label="稍后阅读预览">
    <header className="home-section-heading"><div><span className="home-eyebrow">SAVED FOR LATER</span><h2>稍后阅读</h2></div><Link to="/manage?filter=read_later">打开稍后阅读 →</Link></header>
    {error && <Alert type="warning" message="稍后阅读暂不可用" description={error} action={<Button onClick={() => setRetry(value => value + 1)}>重试稍后阅读</Button>} />}
    <div className="home-paper-grid">{papers.map(paper => <article className="home-paper" key={paper.uid}>
      <div className="home-paper-meta"><BookOutlined aria-hidden="true" /><span>已加入稍后阅读</span>{!!paper.year && <span>{paper.year}</span>}</div>
      <h3>{paper.title || "未命名论文"}</h3><div className="home-paper-actions"><Link className="home-reading-link" to={`/papers/${encodeURIComponent(paper.uid)}?tab=reading`}>阅读原文 ↗</Link></div>
    </article>)}</div>
  </section>;
}
