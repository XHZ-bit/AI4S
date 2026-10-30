import { useEffect, useMemo, useRef, useState } from "react";
import { Alert, Button, Card, Checkbox, Descriptions, Empty, Input, Modal, Space, Spin, Table, Tag, Typography, message } from "antd";
import { Link } from "react-router-dom";
import type { ComparisonResult, EvidenceRef, ExperimentSetting, ProjectFactsResponse, ResearchProject } from "../../api/project-types";
import { compareProjectCandidates, getComparisonReadiness, getProjectFacts, isVersionConflict, saveProjectDecision, type ComparisonReadiness } from "../../api/projects";
import EvidenceDrawer from "./EvidenceDrawer";
import { FindingStatusTag, RecordStatusTag, displayKnown } from "./StatusLabels";

import { getInsights, statusLabels, type Report } from "../../api/assistant";
import { useInspector } from "../workspace/InspectorContext";

type Candidate = { key: string; methodId: string; methodName: string; setting: ExperimentSetting };
const fieldLabel: Record<string, string> = {
  dataset: "数据集", dataset_version: "数据集版本", subset: "子集", split: "划分",
  evaluation_protocol: "评估协议", preprocessing: "预处理", reported_measurement: "已报告测量",
  metric_name: "指标名称", metric_scope: "指标范围", metric_direction: "指标方向",
  metric_scale: "指标尺度", metric_unit: "指标单位", metric_aggregation: "聚合方式",
  sample_size: "样本量", unique_reported_measurement: "唯一测量记录",
};
const labelFields = (fields: string[]) => fields.map(field => fieldLabel[field] ?? field).join("、");

export default function ComparisonPanel({ project }: { project: ResearchProject }) {
  const inspector = useInspector();
  const [report, setReport] = useState<Report>();
  const [readiness, setReadiness] = useState<ComparisonReadiness>();
  const [refreshEpoch, setRefreshEpoch] = useState(0);
  useEffect(() => { const c = new AbortController(); getInsights("project", project.id, null, c.signal).then(r=>{if(!c.signal.aborted)setReport(r);}).catch(()=>{}); return ()=>c.abort(); }, [project.id, project.version]);
  useEffect(() => {
    const c = new AbortController();
    getComparisonReadiness(project.id, c.signal).then(value => { if (!c.signal.aborted) setReadiness(value); }).catch(() => {});
    return () => c.abort();
  }, [project.id, project.version, project.constraints.version, refreshEpoch]);
  const [facts, setFacts] = useState<ProjectFactsResponse | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [comparison, setComparison] = useState<ComparisonResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [decisionOpen, setDecisionOpen] = useState(false);
  const [decisionCandidate, setDecisionCandidate] = useState("");
  const [rationale, setRationale] = useState("");
  const [evidence, setEvidence] = useState<EvidenceRef | null>(null);
  const lock = useRef(false);
  const requestEpoch = useRef(0);
  const previousProject = useRef(project.id);

  useEffect(() => {
    const controller = new AbortController();
    ++requestEpoch.current;
    lock.current = false;
    setBusy(false);
    setFacts(null);
    setComparison(null);
    setDecisionOpen(false);
    setEvidence(null);
    setError("");
    if (previousProject.current !== project.id) {
      setSelected([]);
      setRationale("");
      setDecisionCandidate("");
      previousProject.current = project.id;
    }
    setLoading(true);
    getProjectFacts(project.id, {}, controller.signal).then(result => {
      if (!controller.signal.aborted) setFacts(result);
    }).catch(caught => {
      if (!controller.signal.aborted && !(caught instanceof DOMException && caught.name === "AbortError")) setError(caught instanceof Error ? caught.message : "候选加载失败");
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => { controller.abort(); ++requestEpoch.current; };
  }, [project.id, project.version, project.constraints.version, refreshEpoch]);

  const candidates = useMemo<Candidate[]>(() => {
    if (!facts) return [];
    const methods = new Map(facts.methods.map(method => [method.id, method]));
    return facts.experiment_settings
      .filter(setting => setting.status !== "withdrawn" && methods.has(setting.method_id) && methods.get(setting.method_id)?.status !== "withdrawn")
      .map(setting => ({ key: `${setting.method_id}:${setting.id}`, methodId: setting.method_id, methodName: methods.get(setting.method_id)?.name ?? "未知方法", setting }));
  }, [facts]);
  const selectedCandidates = candidates.filter(item => selected.includes(item.key));
  const evidenceById = new Map((facts?.evidence ?? []).map(item => [item.id, item]));

  const constraintCheck = (candidate: Candidate) => (report?.candidates.find(c=>c.id===candidate.setting.id)?.checks || []).map(c=>({key:c.dimension,label:c.dimension,value:String(c.actual??"未知"),status:c.status,explanation:c.reason}));

  const runComparison = async () => {
    if (lock.current || selectedCandidates.length < 2) return;
    const epoch = requestEpoch.current;
    lock.current = true;
    setBusy(true);
    setError("");
    try {
      const result = await compareProjectCandidates(project.id, {
        project_id: project.id,
        project_version: project.version,
        domain: project.domain,
        candidates: selectedCandidates.map(candidate => ({
          method_id: candidate.methodId,
          experiment_setting_id: candidate.setting.id,
          measurement_ids: (facts?.measurements ?? []).filter(item => item.experiment_setting_id === candidate.setting.id && item.status !== "withdrawn").map(item => item.id),
        })),
      });
      if (epoch !== requestEpoch.current) return;
      setComparison(result);
      message.success("条件比较已完成");
    } catch (caught) {
      if (epoch !== requestEpoch.current) return;
      setError(isVersionConflict(caught) ? `项目版本冲突：${caught.message}。候选选择已保留。` : caught instanceof Error ? caught.message : "比较失败");
    } finally { if (epoch === requestEpoch.current) { lock.current = false; setBusy(false); } }
  };

  const saveDecision = async () => {
    const candidate = candidates.find(item => item.key === decisionCandidate);
    if (!candidate || !rationale.trim() || lock.current || !comparison) return;
    const epoch = requestEpoch.current;
    lock.current = true;
    setBusy(true);
    setError("");
    const evidenceIds = Array.from(new Set([
      ...candidate.setting.field_evidence.flatMap(field => field.evidence_ids),
      ...(facts?.methods.find(item => item.id === candidate.methodId)?.field_evidence.flatMap(field => field.evidence_ids) ?? []),
    ]));
    try {
      await saveProjectDecision(project.id, {
        expected_project_version: project.version,
        selected_method_id: candidate.methodId,
        selected_experiment_setting_ids: [candidate.setting.id],
        considered_candidate_ids: selectedCandidates.flatMap(item => [item.methodId, item.setting.id]),
        rationale,
        evidence_ids: evidenceIds,
      });
      if (epoch !== requestEpoch.current) return;
      message.success("路线选择已保存；旧选择仍保留在历史中");
      setDecisionOpen(false);
    } catch (caught) {
      if (epoch !== requestEpoch.current) return;
      setError(isVersionConflict(caught) ? `项目版本冲突：${caught.message}。选择和理由已保留，请重新加载后人工处理。` : caught instanceof Error ? caught.message : "路线保存失败");
    } finally { if (epoch === requestEpoch.current) { lock.current = false; setBusy(false); } }
  };

  if (loading) return <Spin />;
  if (!facts || candidates.length === 0) return <Space direction="vertical" style={{ width: "100%" }}>{error && <Alert type="error" message={error} />}<Empty description="没有可比较的实验设置。请先关联论文并审核抽取结果。" /></Space>;

  return <Space direction="vertical" size="large" style={{ width: "100%" }}>
    <Alert type="info" showIcon message="先检查条件，再查看数值" description="课题约束匹配和文献实验条件可比性是两件事。不同数据集、划分、协议或指标范围不会被合并排名。" />
    {readiness && <Card title="比较准备度 · 自动核查" extra={<Space><Tag>已检查 {readiness.pairs.length} 组 · 其中 {readiness.pairs.filter(pair => pair.status === "comparable").length} 组有共同指标</Tag><Button size="small" onClick={() => setRefreshEpoch(value => value + 1)}>刷新比较依据</Button></Space>}>
      <Typography.Paragraph type="secondary">{readiness.notice}</Typography.Paragraph>
      {readiness.candidates.filter(candidate => candidate.missing_fields.length || candidate.constraint_gaps.length || candidate.source_gaps?.length || candidate.evidence_gaps?.length).map(candidate =>
        <div key={candidate.setting_id} style={{ marginBottom: 8 }}><strong>{candidate.label}</strong>：
          {candidate.missing_fields.length ? `待补齐 ${labelFields(candidate.missing_fields)}` : "关键条件已记录"}
          {candidate.constraint_gaps.length > 0 && `；课题约束仍有 ${candidate.constraint_gaps.length} 项冲突或未知`}
          {!!candidate.evidence_gaps?.length && `；关键字段缺少来源绑定 ${candidate.evidence_gaps.length} 项`}
          {!!candidate.source_gaps?.length && <>；<Link to="?tab=audit">阻断级来源问题 {candidate.source_gaps.length} 项</Link></>}</div>)}
      {readiness.pairs.slice(0, 20).map(pair => <div key={`${pair.left_setting_id}:${pair.right_setting_id}`} style={{ marginBottom: 6 }}>
        <Tag color={pair.status === "comparable" ? "green" : pair.status === "conflict" ? "red" : "gold"}>{pair.status === "comparable" ? "可比较" : pair.status === "conflict" ? "条件冲突" : "信息不足"}</Tag>
        {pair.left_setting_id} / {pair.right_setting_id} · {pair.next_action}
        {[...pair.conflicting_fields, ...pair.missing_fields].length > 0 && `（${labelFields([...pair.conflicting_fields, ...pair.missing_fields])}）`}
        {!!pair.evidence_gaps?.length && ` · 逐字段来源缺口：${pair.evidence_gaps.join("、")}`}
        {!!pair.source_gaps?.length && <> · <Link to="?tab=audit">查看来源问题</Link></>}
        {!!pair.shared_metrics?.length && <div style={{ marginLeft: 8, color: "#58656e" }}>共同指标仅限：{pair.shared_metrics.map(metric => `${metric.metric_name} / ${metric.metric_scope}${metric.aggregation ? ` / ${metric.aggregation}` : ""}`).join("；")}</div>}
        {!![...(pair.condition_checks ?? []), ...(pair.metric_checks ?? [])].length && <details style={{ marginLeft: 8 }}><summary>查看逐项条件与指标检查</summary>
          {[...(pair.condition_checks ?? []), ...(pair.metric_checks ?? [])].map(check =>
            <div key={check.field}><Tag color={check.status === "match" ? "green" : check.status === "conflict" ? "red" : "gold"}>{check.status === "match" ? "一致" : check.status === "conflict" ? "冲突" : "缺失"}</Tag>
              {fieldLabel[check.field] ?? check.field}：{check.left_value ?? "未记录"} / {check.right_value ?? "未记录"} · {check.reason}</div>)}</details>}
      </div>)}
      {readiness.pairs.length > 20 && <Typography.Text type="secondary">页面展示已检查的前 20 组；接口共检查 {readiness.pairs.length} 组。</Typography.Text>}
      {readiness.truncated && <Typography.Paragraph type="secondary">组合共 {readiness.total_pairs} 组，接口只检查前 {readiness.pairs.length} 组；未检查的组合不作判断。</Typography.Paragraph>}
    </Card>}
    {error && <Alert type="error" showIcon message="比较或保存失败" description={error} />}
    <div className="research-card-grid">{candidates.map(candidate => <Card key={candidate.key} title={<Checkbox disabled={busy} checked={selected.includes(candidate.key)} onChange={event => { setComparison(null); setDecisionOpen(false); setSelected(current => event.target.checked ? [...current, candidate.key] : current.filter(key => key !== candidate.key)); }}>{candidate.methodName} / {candidate.setting.name}</Checkbox>}>
      <Space wrap><RecordStatusTag status={candidate.setting.status} /><FindingStatusTag status={candidate.setting.finding_status} /></Space>
      <Descriptions size="small" column={1} style={{ marginTop: 12 }} items={[
        { key: "dataset", label: "数据集", children: displayKnown(candidate.setting.dataset) },
        { key: "split", label: "划分", children: displayKnown(candidate.setting.split) },
        { key: "protocol", label: "协议", children: displayKnown(candidate.setting.evaluation_protocol) },
      ]} />
      <Typography.Title level={5}>课题约束匹配</Typography.Title>
      {constraintCheck(candidate).map(row => <div key={row.key} className="research-constraint-row"><Tag color={row.status === "match" ? "green" : row.status === "conflict" ? "red" : "gold"}>{statusLabels[row.status]}</Tag><strong>{row.label}</strong>：{row.value}<Typography.Text type="secondary"> · {row.explanation}</Typography.Text></div>)}
      <Typography.Title level={5}>关键字段依据</Typography.Title>
      {candidate.setting.field_evidence.length ? candidate.setting.field_evidence.map(field => <div key={field.field_path} className="research-evidence-row"><Space wrap><Typography.Text code>{field.field_path}</Typography.Text><FindingStatusTag status={field.finding_status} />{field.evidence_ids.map(id => <Button key={id} size="small" onClick={() => inspector.available ? inspector.inspect({kind:"evidence",id}) : setEvidence(evidenceById.get(id) ?? null)}>查看来源</Button>)}</Space><Typography.Text type="secondary">{field.note || (field.evidence_ids.length ? "" : "没有来源绑定")}</Typography.Text></div>) : <Typography.Text type="secondary">没有逐字段依据，不能据此得出比较结论。</Typography.Text>}
    </Card>)}</div>
    <Button type="primary" loading={busy} disabled={selectedCandidates.length < 2} onClick={() => void runComparison()}>比较选中的 {selectedCandidates.length} 个候选</Button>
    {comparison && <Card title="文献实验条件检查" extra={<Tag color={comparison.groups.some(group => group.comparable) ? "green" : "orange"}>{comparison.groups.some(group => group.comparable) ? "存在可比组" : "没有可直接比较的组"}</Tag>}>
      {comparison.warnings.map(warning => <Alert key={warning} type="warning" message={warning} style={{ marginBottom: 8 }} />)}
      <Table pagination={false} rowKey="name" dataSource={comparison.dimensions} columns={[
        { title: "字段", dataIndex: "name" },
        { title: "候选值", render: (_, row) => <Space direction="vertical">{Object.entries(row.values).map(([id, value]) => <span key={id}><Typography.Text code>{id}</Typography.Text>：{displayKnown(value)}</span>)}</Space> },
        { title: "检查", render: (_, row) => <Space direction="vertical"><Tag color={row.comparable ? "green" : "orange"}>{row.comparable ? "条件一致" : "不可直接比较"}</Tag>{row.reason && <Typography.Text type="secondary">{row.reason}</Typography.Text>}</Space> },
      ]} />
      <Typography.Title level={5}>比较分组</Typography.Title>
      {comparison.groups.map(group => <Card size="small" key={group.id} style={{ marginBottom: 8 }}><Space wrap><Tag color={group.comparable ? "green" : "orange"}>{group.comparable ? "组内可比较" : "仅并排查看"}</Tag>{group.candidate_ids.map(id => <Typography.Text code key={id}>{id}</Typography.Text>)}</Space>{group.reasons.map(reason => <Typography.Paragraph key={reason} type="secondary">{reason}</Typography.Paragraph>)}</Card>)}
      <Button type="primary" onClick={() => { setDecisionCandidate(selectedCandidates[0]?.key ?? ""); setDecisionOpen(true); }}>选定路线</Button>
    </Card>}
    <Modal title="保存路线选择" open={decisionOpen} confirmLoading={busy} okButtonProps={{ disabled: !decisionCandidate || !rationale.trim() }} onCancel={() => setDecisionOpen(false)} onOk={() => void saveDecision()}>
      <Space direction="vertical" style={{ width: "100%" }}>
        <Typography.Text>选择仅表示用户决定采用该路线，不会改写成论文结论。</Typography.Text>
        {selectedCandidates.map(candidate => <Checkbox key={candidate.key} checked={decisionCandidate === candidate.key} onChange={() => setDecisionCandidate(candidate.key)}>{candidate.methodName} / {candidate.setting.name}</Checkbox>)}
        <Input.TextArea rows={5} value={rationale} onChange={event => setRationale(event.target.value)} placeholder="填写选择理由、已知限制和需要验证的假设" maxLength={8000} />
      </Space>
    </Modal>
    <EvidenceDrawer evidence={evidence} projectId={project.id} onClose={() => setEvidence(null)} />
  </Space>;
}
