import { useCallback, useEffect, useState } from "react";
import { Alert, Button, Card, Empty, Space, Spin, Tag, Typography } from "antd";
import { Link } from "react-router-dom";
import { getImpactChanges, getImpactCheckpoint, getProjectAudit, getProjectImpact, saveImpactCheckpoint,
  type ImpactChanges, type ImpactCheckpoint, type ProjectAudit, type ProjectImpact } from "../../api/projects";

const severityLabel = { blocking: "来源失效", warning: "需要核查", notice: "变化提示" };
const severityColor = { blocking: "red", warning: "orange", notice: "blue" };

export default function ProjectAuditPanel({ projectId }: { projectId: string }) {
  const [report, setReport] = useState<ProjectAudit | null>(null);
  const [impact, setImpact] = useState<ProjectImpact | null>(null);
  const [checkpoint, setCheckpoint] = useState<ImpactCheckpoint | null>(null);
  const [changes, setChanges] = useState<ImpactChanges | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const reload = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setError("");
    try {
      const [nextReport, nextImpact, saved] = await Promise.all([
        getProjectAudit(projectId, signal), getProjectImpact(projectId, signal), getImpactCheckpoint(projectId, signal),
      ]);
      const nextChanges = saved.checkpoint
        ? await getImpactChanges(projectId, saved.checkpoint.checkpoint_id, signal) : null;
      if (!signal?.aborted) {
        setReport(nextReport); setImpact(nextImpact);
        setCheckpoint(saved.checkpoint); setChanges(nextChanges);
      }
    }
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

  const recordBaseline = async () => {
    if (!report) return;
    setSaving(true);
    setError("");
    try {
      await saveImpactCheckpoint(projectId, report.input_fingerprint);
      await reload();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "记录核查基线失败");
    } finally { setSaving(false); }
  };

  return <Space direction="vertical" size="middle" style={{ width: "100%" }}>
    <Alert type="info" showIcon message="自动证据与条件核查" description="检查来源版本、原文引用、实验条件和跨论文可比性。结果是机器检查，不改变事实、方案或正式路线的审核状态。" />
    <Space wrap>
      <Tag color="red">来源失效 {report?.summary.blocking ?? 0}</Tag>
      <Tag color="orange">需要核查 {report?.summary.warning ?? 0}</Tag>
      <Tag color="blue">变化提示 {report?.summary.notice ?? 0}</Tag>
      <Button onClick={() => void reload()} loading={loading}>重新核查</Button>
      <Button onClick={() => void recordBaseline()} loading={saving} disabled={!report}>记录当前核查基线</Button>
    </Space>
    {error && <Alert type="error" showIcon message={error} />}
    {checkpoint && changes && <Card size="small" title="相对已记录基线的变化">
      <Typography.Paragraph type="secondary">
        基线 {checkpoint.created_at} · {checkpoint.input_fingerprint.slice(0, 12)}
        {changes.current_fingerprint === changes.baseline_fingerprint ? " · 当前输入相同" : " · 来源输入已变化"}
      </Typography.Paragraph>
      <Space wrap>
        <Tag color="red">新增问题 {changes.added.length}</Tag>
        <Tag color="green">已消失 {changes.resolved.length}</Tag>
        <Tag color="orange">内容变化 {changes.changed.length}</Tag>
      </Space>
      {[...changes.added.map(issue => ({ label: "新增", issue })),
        ...changes.resolved.map(issue => ({ label: "已消失", issue })),
        ...changes.changed.map(pair => ({ label: "变化", issue: pair.after }))].map(({ label, issue }) =>
        <Typography.Paragraph key={`${label}:${issue.id}`} style={{ marginTop: 8, marginBottom: 0 }}>
          {label}：{issue.title} · {issue.detail}
          {issue.affected_plan_ids.length > 0 && <Link to="?tab=plans"> · 方案 {issue.affected_plan_ids.length}</Link>}
          {issue.affected_snapshot_ids.length > 0 && <Link to="?tab=changes"> · 快照 {issue.affected_snapshot_ids.length}</Link>}
        </Typography.Paragraph>)}
      <Typography.Text type="secondary">{changes.notice}</Typography.Text>
    </Card>}
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
        {impact?.input_fingerprint === report.input_fingerprint &&
          impact.issues.find(entry => entry.issue_id === issue.id)?.affected.some(entry => entry.kind === "activity") &&
          <Typography.Paragraph type="secondary" style={{ marginTop: 10 }}>
            影响执行任务：{impact.issues.find(entry => entry.issue_id === issue.id)?.affected
              .filter(entry => entry.kind === "activity").map(entry =>
                <Link key={entry.id} to={entry.url} style={{ marginRight: 12 }}>{entry.id.split(":").slice(-1)[0]} · 查看依据</Link>)}
          </Typography.Paragraph>}
        {(issue.fact_ids.length > 0 || issue.evidence_ids.length > 0) &&
          <Typography.Paragraph type="secondary" style={{ marginTop: 10, marginBottom: 0, overflowWrap: "anywhere" }}>
            {issue.fact_ids.length > 0 && <>事实：{issue.fact_ids.join("、")}　</>}
            {issue.evidence_ids.length > 0 && <>证据：{issue.evidence_ids.join("、")}</>}
          </Typography.Paragraph>}
      </Card>) : <Empty description="当前规则未发现来源或条件问题；这不代表科研结论已经验证。" />}
    {report && <Typography.Text type="secondary">规则 {report.rule_version} · 输入指纹 {report.input_fingerprint.slice(0, 12)} · {report.notice}</Typography.Text>}
  </Space>;
}
