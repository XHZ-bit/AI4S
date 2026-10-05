import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { Alert, Button, Descriptions, Divider, Space, Spin, Tag, Typography } from "antd";
import type { ProjectSnapshot, ValidationPlan } from "../../api/project-types";
import { getProjectSnapshot } from "../../api/projects";
import { ReviewStatusTag, SourceKindTag } from "../../components/research/StatusLabels";
import "./research-workspace.css";

const reference = (value: string) => <span className="research-print-reference">{value}</span>;

export default function ResearchPrintPage() {
  const { projectId = "", snapshotId = "" } = useParams();
  const [params] = useSearchParams();
  const [snapshot, setSnapshot] = useState<ProjectSnapshot | null>(null);
  const [draft, setDraft] = useState<ValidationPlan | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (snapshotId === "draft") {
      const planId = params.get("plan_id") ?? "new";
      const raw = localStorage.getItem(`research-atlas:plan-draft:${projectId}:${planId}`);
      if (!raw) setError("本机没有可恢复的未保存草稿");
      else {
        try { setDraft(JSON.parse(raw) as ValidationPlan); }
        catch { setError("本地草稿已损坏，无法打印"); }
      }
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    getProjectSnapshot(projectId, snapshotId, controller.signal).then(setSnapshot).catch(caught => {
      if (!(caught instanceof DOMException && caught.name === "AbortError")) setError(caught instanceof Error ? caught.message : "快照加载失败");
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [params, projectId, snapshotId]);

  if (loading) return <Spin />;
  const plan = draft ?? snapshot?.plan ?? null;
  if (!plan) return <Alert type="error" message="无法生成打印页" description={error} />;
  const unsaved = !!draft;

  return <article className="research-print-page">
    <div className="research-print-actions"><Button type="primary" onClick={() => window.print()}>打印 / 保存为 PDF</Button></div>
    <Typography.Title>{plan.title}</Typography.Title>
    <Space wrap className="research-print-status">
      {unsaved ? <Tag color="orange">未保存的本地草稿</Tag> : <Tag color="green">不可变快照 v{snapshot!.snapshot_version}</Tag>}
      <Tag>{plan.status === "draft" ? "草稿状态" : plan.status === "saved" ? "已保存" : "已被新版本取代"}</Tag>
      <ReviewStatusTag status={snapshot?.review_status ?? plan.review_status} />
      <SourceKindTag source={plan.source_kind} />
    </Space>
    {unsaved && <Alert type="warning" showIcon message="此打印件来自未保存草稿" description="它只存在于当前浏览器，不能作为已保存或已确认的方案版本。" />}
    {(snapshot?.review_reasons ?? plan.review_reasons).length > 0 && <Alert type="warning" showIcon message="待复核原因" description={(snapshot?.review_reasons ?? plan.review_reasons).join("；")} />}
    <Descriptions bordered column={1} items={[
      { key: "project", label: "课题", children: reference(projectId) },
      { key: "snapshot", label: "快照 ID", children: snapshot ? reference(snapshot.id) : "未保存" },
      { key: "method", label: "选定方法", children: reference(plan.selected_method_id) },
      { key: "settings", label: "实验设置", children: plan.selected_experiment_setting_ids.map(id => <span key={id}>{reference(id)} </span>) },
      { key: "created", label: "快照时间", children: snapshot?.created_at ?? "未保存" },
    ]} />
    <Divider />
    <Typography.Title level={2}>目标</Typography.Title><Typography.Paragraph>{plan.objective}</Typography.Paragraph>
    <Typography.Title level={2}>待验证假设</Typography.Title><Typography.Paragraph>{plan.hypothesis || "未填写/未知"}</Typography.Paragraph>
    <Typography.Title level={2}>假设条件</Typography.Title>{plan.assumptions.length ? <ul>{plan.assumptions.map(item => <li key={item}>{item}</li>)}</ul> : <Typography.Paragraph>未填写/未知</Typography.Paragraph>}
    <Typography.Title level={2}>未知项</Typography.Title>{plan.unknowns.length ? <ul>{plan.unknowns.map(item => <li key={item}>{item}</li>)}</ul> : <Typography.Paragraph>当前没有记录未知项；这不等于没有未知。</Typography.Paragraph>}
    <Typography.Title level={2}>验证步骤</Typography.Title>{plan.steps.length ? plan.steps.map((step, index) => <section key={step.id} className="research-print-step"><Typography.Title level={3}>{index + 1}. {step.title}</Typography.Title><p><strong>目的：</strong>{step.purpose}</p><ol>{step.procedure.map(item => <li key={item}>{item}</li>)}</ol><p><strong>验收：</strong>{step.acceptance_criteria.length ? step.acceptance_criteria.join("；") : "待确认"}</p>{step.evidence_ids.length ? <p><strong>依据：</strong>{step.evidence_ids.join("、")}</p> : <p><strong>依据：</strong>未绑定/待补</p>}</section>) : <Typography.Paragraph>尚未填写验证步骤。</Typography.Paragraph>}
    <Typography.Title level={2}>目标测量</Typography.Title><Typography.Paragraph>{plan.target_measurements.length ? plan.target_measurements.join("、") : "未填写/待确认"}</Typography.Paragraph>
    <Typography.Title level={2}>风险</Typography.Title>{plan.risks.length ? <ul>{plan.risks.map(item => <li key={item}>{item}</li>)}</ul> : <Typography.Paragraph>未填写；不代表无风险。</Typography.Paragraph>}
    {snapshot && <><Divider /><Typography.Title level={2}>冻结引用</Typography.Title><p>项目版本：{snapshot.frozen_project_version}；约束版本：{snapshot.frozen_constraint_version}；领域配置：{reference(snapshot.frozen_domain_profile_version)}</p><p>决策：{reference(snapshot.frozen_decision.id)} v{snapshot.frozen_decision.version}</p><p>事实：{snapshot.frozen_facts.map(ref => <span key={ref.id}>{reference(ref.id)} v{ref.version}； </span>)}</p><div>文档：{snapshot.frozen_documents.map(doc => <p key={doc.paper_link_id}>{reference(doc.paper_uid)} / {reference(doc.document_id)} / {reference(doc.document_version)}</p>)}</div></>}
  </article>;
}
