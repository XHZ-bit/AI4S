import { useEffect, useRef, useState } from "react";
import { Alert, Button, Card, Empty, Input, Space, Typography } from "antd";
import { Link, useSearchParams } from "react-router-dom";
import { searchPapers, type PaperSearchResponse, type PaperSearchResult } from "../api/search";

const modeLabels: Record<PaperSearchResponse["mode"], string> = {
  keyword: "本地关键词检索", semantic: "语义检索", hybrid: "混合检索",
};

function sourcePath(result: PaperSearchResult, projectId?:string) {
  const params = new URLSearchParams({ tab: "reading", focus: result.passage_id!, panel: "evidence", ref: `passage:${result.passage_id}` });
  if (result.page != null && Number.isInteger(result.page) && result.page >= 1) params.set("page", String(result.page));
  if(projectId)params.set("project",projectId);
  return `/papers/${encodeURIComponent(result.uid)}?${params}`;
}

export default function PaperSearchPanel() {
  const [params]=useSearchParams();const projectId=params.get("project")||undefined;
  const [query, setQuery] = useState("");
  const [submitted, setSubmitted] = useState("");
  const [status, setStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [response, setResponse] = useState<PaperSearchResponse>();
  const [error, setError] = useState("");
  const generation = useRef(0);
  const pending = useRef<AbortController>();

  useEffect(() => () => { generation.current++; pending.current?.abort(); }, []);

  function reset() {
    generation.current++;
    pending.current?.abort();
    pending.current = undefined;
    setStatus("idle"); setResponse(undefined); setError(""); setSubmitted("");
  }

  async function search(value: string) {
    reset();
    const term = value.trim();
    if (!term) return;
    const request = generation.current;
    const controller = new AbortController();
    pending.current = controller;
    setSubmitted(term); setStatus("loading");
    try {
      const result = await searchPapers(term, 10, controller.signal);
      if (controller.signal.aborted || generation.current !== request) return;
      setResponse(result); setStatus("success");
    } catch (caught) {
      if (controller.signal.aborted || generation.current !== request) return;
      setError(caught instanceof Error ? caught.message : String(caught)); setStatus("error");
    } finally {
      if (pending.current === controller) pending.current = undefined;
    }
  }

  return <Card title="论文检索">
    <Input.Search aria-label="论文检索关键词" placeholder="标题、摘要或原文关键词" value={query} allowClear loading={status === "loading"}
      onChange={event => { setQuery(event.target.value); reset(); }} onSearch={value => void search(value)} />
    <Typography.Paragraph type="secondary" style={{ marginTop: 8 }}>匹配只表示检索相关，不能证明论文质量或结论可靠。</Typography.Paragraph>
    <div aria-live="polite" aria-busy={status === "loading"}>
      {status === "idle" && <Typography.Paragraph type="secondary">输入关键词并搜索，可查看匹配片段及其原文位置。</Typography.Paragraph>}
      {status === "loading" && <p role="status">正在检索“{submitted}”…</p>}
      {status === "error" && <Alert type="error" showIcon message="论文检索失败" description={error}
        action={<Button onClick={() => void search(submitted)}>重试检索</Button>} />}
      {status === "success" && response && <>
        <Typography.Paragraph type="secondary">{modeLabels[response.mode]} · 显示 {response.items.length} 篇论文</Typography.Paragraph>
        {response.items.length === 0 && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={`没有找到与“${submitted}”相关的资料，请尝试其他关键词。`} />}
        {response.items.map(result => <Card size="small" key={result.uid} style={{ marginTop: 8 }}>
          <Typography.Title level={5} style={{ marginTop: 0 }}><Link to={`/papers/${encodeURIComponent(result.uid)}?tab=reading${projectId?`&project=${encodeURIComponent(projectId)}`:""}`}>{result.title || result.uid}</Link></Typography.Title>
          {result.passage_id && <Space wrap style={{ marginBottom: 8 }}><Typography.Text strong>原文匹配片段</Typography.Text>
            <Typography.Text type="secondary">{result.page != null && Number.isInteger(result.page) && result.page >= 1 ? `第 ${result.page} 页` : "页码未记录"}</Typography.Text>
          </Space>}
          <Typography.Paragraph style={{ whiteSpace: "pre-wrap" }}>{result.quote || result.snippet || "暂无可展示片段。"}</Typography.Paragraph>
          <Space wrap><Typography.Text type="secondary">{result.hit_reason}</Typography.Text>
            {result.passage_id && <Link to={sourcePath(result,projectId)}>查看原文</Link>}
          </Space>
        </Card>)}
      </>}
    </div>
  </Card>;
}
