import { useEffect, useRef } from "react";
export default function SourceView({ text, line = 1 }: { text: string; line?: number }) {
  const host = useRef<HTMLDivElement>(null);
  useEffect(() => { const selected = host.current?.querySelector<HTMLElement>(`[data-line="${line}"]`); if (selected && host.current) host.current.scrollTop = selected.offsetTop - host.current.offsetTop - host.current.clientHeight / 2; }, [line, text]);
  return <div ref={host} className="atlas-source" aria-label="源码与行号" tabIndex={0}>{text.split("\n").map((value, i) => <div key={i} data-line={i + 1} className={`atlas-source-line ${i + 1 === line ? "selected" : ""}`}><span className="atlas-line-number">{i + 1}</span><code>{value || " "}</code></div>)}</div>;
}
