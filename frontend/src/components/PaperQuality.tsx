import { useEffect, useState } from "react";
import { Alert, Button, Space, Tag } from "antd";
import { Link } from "react-router-dom";
import { apiGet, apiPost } from "../api/client";

export default function PaperQuality({ uid }: { uid: string }) {
  const [data, setData] = useState<any>();
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setData(undefined); setError("");
    apiGet<any>(`/api/papers/${encodeURIComponent(uid)}/quality`, undefined, controller.signal)
      .then(value => { if (!controller.signal.aborted) { setData(value); setError(""); } }).catch(caught => { if (!controller.signal.aborted) setError(String(caught)); });
    return () => controller.abort();
  }, [uid, refresh]);
  const statusLabel = ({ ready: "正文可读", partial: "部分页面可读", no_text: "没有文字层", unknown: "旧资料，覆盖率未知", pending: "等待解析" } as Record<string, string>)[data?.status] || "状态待确认";
  return <section className="atlas-paper-quality" aria-label="资料就绪情况">
    <div className="atlas-quality-primary">
      <strong>资料就绪情况</strong>
      {data && <Space wrap className="atlas-quality-status"><Tag>{statusLabel}</Tag>
        {data.page_count != null && <span>有文字层 {data.text_page_count}/{data.page_count} 页</span>}
        {data.document_versions > 1 && <Tag>已保存 {data.document_versions} 个文档版本</Tag>}</Space>}
      <Button className="atlas-quality-refresh" size="small" onClick={() => setRefresh(value => value + 1)}>重新检查</Button>
    </div>
    {error && <Alert type="warning" message="资料状态加载失败" description={error} />}
    {!data && !error && <p className="atlas-quality-notice" role="status">正在检查原文可读性…</p>}
    {data && <>
      <p className="atlas-quality-notice">文字层检测不代表内容已核验。{data.status === "no_text" ? "扫描页暂时无法抽取文字，可查看 PDF 原件。" : data.status === "partial" ? "部分页面没有文字层，可在 PDF 中继续查看。" : ""}</p>
      <div className="atlas-quality-footer">
        <details className="atlas-quality-details"><summary>解析覆盖说明</summary>{(data.warnings || []).map((warning: string) => <p key={warning}>{warning}</p>)}<p>{data.measurement}</p></details>
        <Space className="atlas-quality-actions" wrap><Link to="/tasks">查看解析任务</Link><Link to={`/actions?paper=${encodeURIComponent(uid)}`}>生成自动行动清单</Link>
          <Button size="small" onClick={()=>void apiPost(`/api/papers/${encodeURIComponent(uid)}/parse`).then(()=>setRefresh(value=>value+1)).catch(caught=>setError(String(caught)))}>重新处理原文</Button>
        </Space>
      </div>
    </>}
  </section>;
}
