import { useEffect, useState } from "react";
import { Alert, Button, Card, Empty, Space, Spin, Tag, Typography } from "antd";
import { apiGet } from "../api/client";

interface RelationIssue {
  id: string;
  code: string;
  relation_ids: number[];
  detail: string;
}

interface RelationAudit {
  contract_version: "relation-audit-v1";
  rule_version: string;
  input_fingerprint: string;
  checked_relations: number;
  issues: RelationIssue[];
  mechanically_clean: boolean;
  notice: string;
}

export default function RelationAuditPanel() {
  const [report, setReport] = useState<RelationAudit | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const refresh = async () => {
    setLoading(true);
    setError("");
    try { setReport(await apiGet<RelationAudit>("/api/learning/relations/audit")); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "关系诊断失败"); }
    finally { setLoading(false); }
  };
  useEffect(() => { void refresh(); }, []);
  return <Space direction="vertical" size="middle" style={{ width: "100%", paddingTop: 16 }}>
    <Alert type="info" showIcon message="知识关系自动诊断" description="检查关系端点、原文定位、同名歧义和先修环路。此结果不修改候选状态，也不批准正式路线。" />
    <Space><Tag>检查关系 {report?.checked_relations ?? 0}</Tag><Tag color={report?.issues.length ? "orange" : "green"}>发现问题 {report?.issues.length ?? 0}</Tag><Button loading={loading} onClick={() => void refresh()}>重新诊断</Button></Space>
    {error && <Alert type="error" showIcon message={error} />}
    {loading && !report ? <Spin /> : report?.issues.length ? report.issues.map(item =>
      <Card size="small" key={item.id} title={item.detail}>
        <Typography.Text type="secondary">规则 {item.code} · 关系 ID：{item.relation_ids.join("、")}</Typography.Text>
      </Card>) : <Empty description="当前规则未发现结构问题；这不代表关系的教学判断正确。" />}
    {report && <Typography.Text type="secondary">{report.notice} 输入指纹 {report.input_fingerprint.slice(0, 12)}</Typography.Text>}
  </Space>;
}
