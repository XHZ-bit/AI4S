import { useCallback, useEffect, useState } from "react";
import { Alert, Button, Card, Empty, Space, Spin, Tag, Typography } from "antd";
import { Link } from "react-router-dom";
import { getProjectAudit, type ProjectAudit } from "../../api/projects";

const severityLabel = { blocking: "来源失效", warning: "需要核查", notice: "变化提示" };
const severityColor = { blocking: "red", warning: "orange", notice: "blue" };

export default function ProjectAuditPanel({ projectId }: { projectId: string }) {
  const [report, setReport] = useState<ProjectAudit | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const reload = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setError("");
    try { setReport(await getProjectAudit(projectId, signal)); }
    catch (caught) {
      if (!(caught instanceof DOMException && caught.name === "AbortError"))
        setError(caught instanceof Error ? caught.message : "自动核查读取失败");
    } finally { if (!signal?.aborted) setLoading(false); }
  }, [projectId]);

  useEffect(() => {
    const controller = new AbortController();
    void reload(controller.signal);
    const changed = () => void reload();
    window.addEventListener("atlas:data-change", changed);
    return () => { controller.abort(); window.removeEventListener("atlas:data-change", changed); };
  }, [reload]);

  return <Space direction="vertical" size="middle" style={{ width: "100%" }}>
    <Alert type="info" showIcon message="自动证据与条件核查" description="检查来源版本、原文引用、实验条件和跨论文可比性。结果是机器检查，不改变事实、方案或正式路线的审核状态。" />
    <Space wrap>
      <Tag color="red">来源失效 {report?.summary.blocking ?? 0}</Tag>
      <Tag color="orange">需要核查 {report?.summary.warning ?? 0}</Tag>
      <Tag color="blue">变化提示 {report?.summary.notice ?? 0}</Tag>
      <Button onClick={() => void reload()} loading={loading}>重新核查</Button>
    </Space>
    {error && <Alert type="error" showIcon message={error} />}
    {loading && !report ? <Spin /> : report?.issues.length ? report.issues.map(issue =>
      <Card key={issue.id} size="small" title={<Space wrap><Tag color={severityColor[issue.severity]}>{severityLabel[issue.severity]}</Tag>{issue.title}</Space>}>
        <Typography.Paragraph>{issue.detail}</Typography.Paragraph>
        <Space wrap>
          {issue.paper_uids.map(uid => <Link key={uid} to={`/papers/${encodeURIComponent(uid)}`}>论文 {uid}</Link>)}
          {issue.fact_ids.length > 0 && <Link to={`?tab=evidence`}>相关事实 {issue.fact_ids.length} 项</Link>}
          {issue.evidence_ids.length > 0 && <Link to={`?tab=evidence`}>来源引用 {issue.evidence_ids.length} 项</Link>}
          {issue.affected_plan_ids.length > 0 && <Link to="?tab=plans">影响方案 {issue.affected_plan_ids.length} 项</Link>}
          {issue.affected_snapshot_ids.length > 0 && <Link to="?tab=changes">影响快照 {issue.affected_snapshot_ids.length} 项</Link>}
        </Space>
        {(issue.fact_ids.length > 0 || issue.evidence_ids.length > 0) &&
          <Typography.Paragraph type="secondary" style={{ marginTop: 10, marginBottom: 0, overflowWrap: "anywhere" }}>
            {issue.fact_ids.length > 0 && <>事实：{issue.fact_ids.join("、")}　</>}
            {issue.evidence_ids.length > 0 && <>证据：{issue.evidence_ids.join("、")}</>}
          </Typography.Paragraph>}
      </Card>) : <Empty description="当前规则未发现来源或条件问题；这不代表科研结论已经验证。" />}
    {report && <Typography.Text type="secondary">规则 {report.rule_version} · 输入指纹 {report.input_fingerprint.slice(0, 12)} · {report.notice}</Typography.Text>}
  </Space>;
}
