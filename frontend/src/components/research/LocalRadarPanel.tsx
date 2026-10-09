import { useEffect, useState } from "react";
import { Alert, Button, Card, Empty, Space, Tag, Typography } from "antd";
import { Link } from "react-router-dom";
import { getProjectRadar, type LocalRadar } from "../../api/projects";

export default function LocalRadarPanel({ projectId }: { projectId: string }) {
  const [report, setReport] = useState<LocalRadar | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const refresh = async () => {
    setLoading(true); setError("");
    try { setReport(await getProjectRadar(projectId)); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "本地资料扫描失败"); }
    finally { setLoading(false); }
  };
  useEffect(() => { void refresh(); }, [projectId]);
  return <Space direction="vertical" size="middle" style={{ width: "100%" }}>
    <Alert type="info" showIcon message="本地资料变化雷达" description="扫描已进入本机论文库但尚未关联此课题的资料，根据方法名和数据集名提示可能相关的论文。此页不联网采集，也不自动改写方案。" />
    <Space><Tag>可能相关 {report?.total ?? 0}</Tag><Button loading={loading} onClick={() => void refresh()}>重新扫描</Button></Space>
    {error && <Alert type="error" message={error} />}
    {report?.items.length ? report.items.map(item => <Card size="small" key={item.uid} title={<Link to={item.source_url}>{item.title}</Link>}>
      <Space wrap>{item.match_reasons.map(reason => <Tag key={reason}>{reason}</Tag>)}</Space>
      <Typography.Paragraph type="secondary" style={{ marginTop: 8 }}>来源：{item.source} · 年份：{item.year ?? "未知"} · 可能影响方案：{item.potentially_affected_plan_ids.length} 项</Typography.Paragraph>
      {item.potentially_affected_plan_ids.length > 0 && <Link to="?tab=plans">查看方案</Link>}
    </Card>) : <Empty description="本地论文库暂无名称匹配的未关联资料。" />}
    {report && <Typography.Text type="secondary">{report.notice} 输入指纹 {report.input_fingerprint.slice(0, 12)}</Typography.Text>}
  </Space>;
}
