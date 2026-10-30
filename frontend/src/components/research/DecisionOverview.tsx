import { useEffect, useState } from "react";
import { Alert, Button, Card, Descriptions, Empty, Space, Spin, Tag, Typography } from "antd";
import { Link, useSearchParams } from "react-router-dom";
import { getProject, getProjectAudit, getProjectFacts, listProjectDecisions, listProjectPapers, listProjectPlans, listProjectSnapshots } from "../../api/projects";
import type { EvidenceRef, ResearchProject } from "../../api/project-types";
import EvidenceDrawer from "./EvidenceDrawer";
import { RecordStatusTag, ReviewStatusTag, SourceKindTag } from "./StatusLabels";

async function loadOverview(id: string, signal: AbortSignal) {
  const [project, papers, facts, decisions, plans, snapshots, audit] = await Promise.all([
    getProject(id, signal), listProjectPapers(id, signal), getProjectFacts(id, {}, signal), listProjectDecisions(id, signal),
    listProjectPlans(id, signal), listProjectSnapshots(id, signal), getProjectAudit(id, signal),
  ]);
  return { project, papers: papers.items, facts, decisions: decisions.items, plans: plans.items, snapshots: snapshots.items, audit };
}
type Overview = Awaited<ReturnType<typeof loadOverview>>;

export default function DecisionOverview({ project }: { project: ResearchProject }) {
  const [data, setData] = useState<Overview | null>(null), [error, setError] = useState(""), [revision, setRevision] = useState(0);
  const [evidence, setEvidence] = useState<EvidenceRef | null>(null);
  const [, setParams] = useSearchParams();
  const go = (tab: string) => setParams(previous => { const next = new URLSearchParams(previous); next.set("tab", tab); return next; });
  useEffect(() => {
    let timer = 0;
    const refresh = () => { clearTimeout(timer); timer = window.setTimeout(() => setRevision(value => value + 1), 150); };
    window.addEventListener("atlas:data-change", refresh);
    return () => { clearTimeout(timer); window.removeEventListener("atlas:data-change", refresh); };
  }, []);
  useEffect(() => {
    const controller = new AbortController(); setData(null); setError(""); setEvidence(null);
    void loadOverview(project.id, controller.signal).then(result => { if (!controller.signal.aborted) setData(result); })
      .catch(caught => { if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : "总览加载失败"); });
    return () => controller.abort();
  }, [project.id, project.version, revision]);
  if (error) return <Alert type="error" message="决策总览加载失败" description={error} action={<Button onClick={() => setRevision(value => value + 1)}>重试总览</Button>} />;
  if (!data || data.project.id !== project.id) return <Spin aria-label="加载决策总览" />;
  const decision = [...data.decisions].filter(item => item.status === "active").sort((a, b) => b.created_at.localeCompare(a.created_at))[0];
  const method = data.facts.methods.find(item => item.id === decision?.selected_method_id);
  const settings = data.facts.experiment_settings.filter(item => decision?.selected_experiment_setting_ids.includes(item.id));
  const facts = [...data.facts.methods, ...data.facts.experiment_settings, ...data.facts.measurements];
  const activePapers = data.papers.filter(item => item.status === "active");
  const plans = data.plans.filter(item => item.status !== "superseded");
  const unknowns = [...new Set(plans.flatMap(item => item.unknowns))];
  const reviewSnapshots = data.snapshots.filter(item => item.review_status !== "current");
  const steps = [
    { label: "关联资料", detail: `${activePapers.length} 篇已关联`, tab: "evidence", done: activePapers.length > 0 },
    { label: "核对证据", detail: `${facts.filter(item => item.status === "user_confirmed").length} / ${facts.length} 条事实已确认`, tab: "evidence", done: facts.length > 0 && facts.every(item => item.status === "user_confirmed" || item.status === "withdrawn") && facts.some(item => item.status === "user_confirmed") },
    { label: "比较并保存选择", detail: decision ? "已保存人工选择" : "尚未选定路线", tab: "compare", done: !!decision },
    { label: "保存验证方案", detail: `${plans.length} 份已保存方案`, tab: "plans", done: plans.length > 0 },
    { label: "创建方案快照", detail: `${data.snapshots.length} 份历史快照`, tab: "plans", done: data.snapshots.length > 0 },
    { label: "检查依据变化", detail: `${data.audit.issues.length} 条核查提示 · ${reviewSnapshots.length} 份快照待复核`, tab: "audit", done: data.snapshots.length > 0 && !data.audit.issues.length && !reviewSnapshots.length },
  ];
  const next = steps.find(item => !item.done);
  return <Space direction="vertical" size="large" className="research-decision-overview" style={{ width: "100%" }}>
    <Card title="研究决策总览" extra={<Button onClick={() => setRevision(value => value + 1)}>刷新总览</Button>}>
      <Typography.Paragraph>{data.project.constraints.objective}</Typography.Paragraph>
      <Descriptions column={{ xs: 1, md: 2 }} items={[
        { key: "datasets", label: "允许的数据集", children: data.project.constraints.allowed_datasets.join("、") || "尚未限定" },
        { key: "metrics", label: "要求的指标", children: data.project.constraints.required_metrics.join("、") || "尚未指定" },
        { key: "compute", label: "计算约束", children: data.project.constraints.compute.length ? data.project.constraints.compute.map(item => `${item.device_kind ?? "设备未指定"} ${item.device_model ?? ""} · ${item.device_count ?? "未知"} 台 · 内存 ${item.memory ? `${item.memory.value} ${item.memory.unit ?? ""}` : "未知"}`).join("；") : "尚未设置" },
        { key: "notes", label: "约束说明", children: data.project.constraints.notes.join("；") || "无补充说明" },
      ]} />
      {next && <Alert type="info" showIcon message={`下一步：${next.label}`} description={next.detail} action={<Button onClick={() => go(next.tab)}>前往处理</Button>} />}
      <div className="research-card-grid" style={{ marginTop: 16 }}>{steps.map(step => <div key={step.label}><Button type="link" onClick={() => go(step.tab)}>{step.label}</Button><Tag color={step.done ? "green" : "default"}>{step.detail}</Tag></div>)}</div>
      <Typography.Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0 }}>进度来自服务端保存记录；完成操作不等于科研结论已被验证。</Typography.Paragraph>
    </Card>
    <div className="research-card-grid">
      <Card title="选了什么，为什么选" extra={<Button onClick={() => go("compare")}>比较与选择</Button>}>
        {decision ? <Space direction="vertical" style={{ width: "100%" }}>
          <Typography.Text strong>{method?.name ?? "所选方法当前不可用"}</Typography.Text>
          {method && <RecordStatusTag status={method.status} />}
          {settings.map(item => <span key={item.id}>{item.name} <RecordStatusTag status={item.status} /></span>)}
          <Typography.Paragraph style={{ whiteSpace: "pre-wrap" }}>{decision.rationale}</Typography.Paragraph>
          <Tag>用户保存的选择理由</Tag>
          {decision.project_version !== data.project.version && <Alert type="warning" message="选择后课题版本发生变化，请重新核对约束。" />}
          {decision.evidence_ids.length ? decision.evidence_ids.map(id => {
            const source = data.facts.evidence.find(item => item.id === id);
            return <Button key={id} disabled={!source} onClick={() => setEvidence(source ?? null)}>{source ? `查看依据：${source.quote?.slice(0, 55) || id}` : `依据不可用：${id}`}</Button>;
          }) : <Typography.Text type="warning">这项选择尚未绑定原文依据。</Typography.Text>}
        </Space> : <Empty description="尚未保存路线选择" />}
      </Card>
      <Card title="还缺什么，需要复核什么" extra={<Button onClick={() => go("audit")}>查看完整核查</Button>}>
        {unknowns.map(value => <Typography.Paragraph key={value}>待补充：{value}</Typography.Paragraph>)}
        {data.audit.issues.slice(0, 6).map(issue => <Alert key={issue.id} type={issue.severity === "blocking" ? "error" : "warning"} message={issue.title} description={issue.detail} style={{ marginBottom: 8 }} />)}
        {data.audit.issues.length > 6 && <Typography.Text>另有 {data.audit.issues.length - 6} 条，请查看完整核查。</Typography.Text>}
        {!unknowns.length && !data.audit.issues.length && <Typography.Paragraph>当前记录没有列出的未知项或规则核查问题；这不代表已完成科学有效性验证。</Typography.Paragraph>}
        {reviewSnapshots.length > 0 && <Typography.Paragraph type="warning">{reviewSnapshots.length} 份历史快照需要复核，冻结内容仍保留。</Typography.Paragraph>}
      </Card>
    </div>
    <Card title="已保存方案与历史快照" extra={<Button onClick={() => go("plans")}>编辑与导出</Button>}>
      {plans.length ? plans.map(plan => <div key={plan.id} style={{ marginBottom: 16 }}>
        <Typography.Text strong>{plan.title} · v{plan.version}</Typography.Text> <SourceKindTag source={plan.source_kind} /> <ReviewStatusTag status={plan.review_status} />
        <Typography.Paragraph>{plan.objective}</Typography.Paragraph>
        {plan.steps.map((step, index) => <div key={step.id}>{index + 1}. {step.title} · {step.acceptance_criteria.join("；") || "验收条件尚未填写"}</div>)}
        {!plan.steps.length && <Typography.Text type="warning">方案尚未填写执行步骤。</Typography.Text>}
      </div>) : <Empty description="尚未保存验证方案" />}
      <Space wrap>{data.snapshots.map(item => <Link key={item.id} to={`/research/${encodeURIComponent(project.id)}/print/${encodeURIComponent(item.id)}`}>查看快照 v{item.snapshot_version}（{item.review_status === "current" ? "当前" : "待复核"}）</Link>)}</Space>
    </Card>
    <EvidenceDrawer evidence={evidence} projectId={project.id} onClose={() => setEvidence(null)} />
  </Space>;
}
