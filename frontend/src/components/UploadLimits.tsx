import { useEffect, useState } from "react";
import { Alert, Button, Typography } from "antd";
import { apiGet } from "../api/client";

type Limits = { pdf_max_bytes?: number | null; pdf_max_pages?: number | null; max_papers?: number | null; storage_max_bytes?: number | null };
const valid = (value: unknown): value is number => typeof value === "number" && Number.isInteger(value) && value > 0;
const megabytes = (bytes: number) => new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 }).format(bytes / 1024 ** 2);

export default function UploadLimits({ onMaxBytes }: { onMaxBytes?: (bytes: number) => void }) {
  const [limits, setLimits] = useState<Limits>(), [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController(); setError("");
    apiGet<{ limits?: Limits }>("/api/system/status", undefined, controller.signal)
      .then(result => {
        if (controller.signal.aborted) return;
        setLimits(result.limits);
        if (valid(result.limits?.pdf_max_bytes)) onMaxBytes?.(result.limits.pdf_max_bytes);
        if (![result.limits?.pdf_max_bytes, result.limits?.pdf_max_pages, result.limits?.max_papers, result.limits?.storage_max_bytes].every(valid)) {
          setError("无法完整读取上传配额，请重试。上传时仍由服务器校验实际限制。");
        }
      })
      .catch(() => { if (!controller.signal.aborted) setError("无法读取上传配额，请重试。上传时仍由服务器校验实际限制。"); });
    return () => controller.abort();
  }, [retry, onMaxBytes]);
  const details = [
    valid(limits?.pdf_max_bytes) ? `每份 PDF ≤ ${megabytes(limits.pdf_max_bytes)} MB` : "",
    valid(limits?.pdf_max_pages) ? `每份 ≤ ${limits.pdf_max_pages} 页` : "",
    valid(limits?.max_papers) ? `最多 ${limits.max_papers} 篇论文` : "",
    valid(limits?.storage_max_bytes) ? `个人 PDF 总量 ≤ ${megabytes(limits.storage_max_bytes)} MB` : "",
  ].filter(Boolean);
  return <>
    {!!details.length && <Typography.Paragraph type="secondary">当前上传配额：{details.join(" · ")}</Typography.Paragraph>}
    {error && <Alert type="warning" message={error} action={<Button size="small" onClick={() => setRetry(value => value + 1)}>重试读取配额</Button>} />}
  </>;
}
