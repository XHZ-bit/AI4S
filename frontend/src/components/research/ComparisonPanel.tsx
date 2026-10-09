import { useEffect, useMemo, useRef, useState } from "react";
import { Alert, Button, Card, Checkbox, Descriptions, Empty, Input, Modal, Space, Spin, Table, Tag, Typography, message } from "antd";
import type { ComparisonResult, EvidenceRef, ExperimentSetting, ProjectFactsResponse, ResearchProject } from "../../api/project-types";
import { compareProjectCandidates, getProjectFacts, isVersionConflict, saveProjectDecision } from "../../api/projects";
import EvidenceDrawer from "./EvidenceDrawer";
import { FindingStatusTag, RecordStatusTag, displayKnown } from "./StatusLabels";

import { getInsights, statusLabels, type Report } from "../../api/assistant";
import { useInspector } from "../workspace/InspectorContext";

type Candidate = { key: string; methodId: string; methodName: string; setting: ExperimentSetting };

export default function ComparisonPanel({ project }: { project: ResearchProject }) {
  const inspector = useInspector();
  const [report, setReport] = useState<Report>();
  useEffect(() => { const c = new AbortController(); getInsights("project", project.id, null, c.signal).then(r=>{if(!c.signal.aborted)setReport(r);}).catch(()=>{}); return ()=>c.abort(); }, [project.id, project.version]);
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
  }, [project.id, project.version, project.constraints.version]);

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
