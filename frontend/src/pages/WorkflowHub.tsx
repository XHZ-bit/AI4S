import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Alert, Button, Card, Checkbox, Input, Modal, Pagination, Select, Space, Tag, Typography } from "antd";
import { apiGet } from "../api/client";
import { changeMastery, getMastery, getStepRecord, listMastery, saveStepRecord, workflowActivities, workflowOverview, type ActivityKind, type Mastery, type StepRecord, type WorkflowActivity, type WorkflowOverview } from "../api/workflow";

const statusText = { pending: "待执行", in_progress: "进行中", completed: "已记录", needs_review: "待复核" };
const evidenceText = { none: "暂无记录", recorded: "用户记录", checked: "固定检查通过" };
const kindText = { roadmap: "正式路线", paper: "论文", case: "案例", project: "课题快照" };

export default function WorkflowHub() {
  const [overview, setOverview] = useState<WorkflowOverview>();
  const [items, setItems] = useState<WorkflowActivity[]>([]);
  const [total, setTotal] = useState(0);
  const [kind, setKind] = useState<ActivityKind | undefined>();
  const [page, setPage] = useState(1);
  const [mastery, setMastery] = useState<Mastery[]>([]);
  const [targets, setTargets] = useState<{uid: string; name: string}[]>([]);
  const [concept, setConcept] = useState<string>();
  const [activityId, setActivityId] = useState<string>();
  const [reason, setReason] = useState("");
  const [selected, setSelected] = useState<WorkflowActivity>();
  const [step, setStep] = useState<StepRecord>();
  const [done, setDone] = useState(false);
  const [outcome, setOutcome] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const reload = async () => {
    const [summary, activities, known] = await Promise.all([
      workflowOverview(), workflowActivities({ source_kind: kind, offset: (page - 1) * 50, limit: 50 }), listMastery(),
    ]);
    setOverview(summary); setItems(activities.items); setTotal(activities.total); setMastery(known.items);
  };
  useEffect(() => { let live = true; Promise.all([
    workflowOverview(), workflowActivities({ source_kind: kind, offset: (page - 1) * 50, limit: 50 }), listMastery(),
  ]).then(([summary, activities, known]) => { if (live) { setOverview(summary); setItems(activities.items); setTotal(activities.total); setMastery(known.items); } })
    .catch(caught => { if (live) setError(String(caught)); }); return () => { live = false; }; }, [kind, page]);
  useEffect(() => { void apiGet<{items: typeof targets}>("/api/roadmap/targets").then(r => setTargets(r.items)).catch(() => {}); }, []);

  const openStep = async (item: WorkflowActivity) => {
    if (!item.project_id) return;
    try {
      const current = await getStepRecord(item.project_id, item.source_id, item.item_id);
      setSelected(item); setStep(current); setDone(!!current.done); setOutcome(current.outcome); setError("");
    } catch (caught) { setError(String(caught)); }
  };
  const saveStep = async () => {
    if (!selected?.project_id || !step) return;
    setBusy(true);
    try {
      await saveStepRecord(selected.project_id, selected.source_id, selected.item_id, { expected_version: step.version, done, outcome });
      setSelected(undefined); setStep(undefined); await reload(); setError("");
    } catch (caught) { setError(String(caught)); }
    finally { setBusy(false); }
  };
  const updateMastery = async (uid: string, action: "confirm" | "revoke") => {
    if (!reason.trim()) { setError("请填写确认或撤销的理由"); return; }
    setBusy(true);
    try {
      const current = await getMastery(uid);
      await changeMastery(uid, { expected_version: current.version, action, reason: reason.trim(), activity_id: action === "confirm" ? activityId || null : null });
      await reload(); setReason(""); setActivityId(undefined); setError("");
    } catch (caught) { setError(String(caught)); }
    finally { setBusy(false); }
  };

  return <Space direction="vertical" size="large" style={{ width: "100%" }}>
    <Typography.Title level={2}>统一任务与掌握记录</Typography.Title>
    <Alert type="info" message="任务进度、检查通过与确认掌握分别记录" description="阅读和自评只说明做过；固定题目答对只说明该题通过。确认掌握由你明确作出并可撤销。课题方案需创建不可变快照，步骤才进入执行清单。" />
    {error && <Alert type="error" message={error} closable onClose={() => setError("")} />}
    {overview && <Card title="当前概览"><Space wrap><Tag>待执行 {overview.counts.pending}</Tag><Tag>进行中 {overview.counts.in_progress}</Tag><Tag>待复核 {overview.counts.needs_review}</Tag><Tag>已记录 {overview.counts.completed}</Tag></Space>{overview.snapshot_required > 0 && <p>有 {overview.snapshot_required} 份已保存方案尚无对应快照。<Link to="/research">创建快照后再执行 →</Link></p>}</Card>}
    <Card title="全部活动" extra={<Select allowClear placeholder="按来源筛选" style={{ width: 170 }} value={kind} onChange={value => { setKind(value); setPage(1); }} options={Object.entries(kindText).map(([value, label]) => ({ value, label }))} />}>
      {items.map(item => <div key={item.id} style={{ borderBottom: "1px solid #e8eef0", padding: "12px 0" }}><Space wrap><Link to={item.url}>{item.title}</Link><Tag>{kindText[item.source_kind]}</Tag><Tag color={item.status === "needs_review" ? "orange" : undefined}>{statusText[item.status]}</Tag><Tag>{evidenceText[item.evidence_level]}</Tag>{item.estimated_minutes != null && <Tag>估算 {item.estimated_minutes} 分钟</Tag>}{item.source_kind === "project" && <Button size="small" disabled={item.status === "needs_review"} onClick={() => void openStep(item)}>记录步骤产出</Button>}</Space><div style={{ color: "#667", marginTop: 4 }}>{item.detail}</div></div>)}
      {!items.length && <p>暂无符合条件的活动。</p>}
      {total > 50 && <Pagination current={page} pageSize={50} total={total} onChange={setPage} style={{ marginTop: 16 }} />}
    </Card>
    <Card title="确认或撤销概念掌握"><Space direction="vertical" style={{ width: "100%" }}>
      <Select showSearch filterOption={false} placeholder="选择已核验的概念或方法" value={concept} onChange={setConcept} onSearch={q => void apiGet<{items: typeof targets}>("/api/roadmap/targets", {q}).then(r => setTargets(r.items)).catch(caught => setError(String(caught)))} options={targets.map(t => ({ value: t.uid, label: `${t.name} · ${t.uid}` }))} />
      <Select allowClear placeholder="关联一项活动（可选）" value={activityId} onChange={setActivityId} showSearch optionFilterProp="label" options={items.map(item => ({ value: item.id, label: item.title }))} />
      <Input.TextArea aria-label="掌握记录理由" value={reason} onChange={event => setReason(event.target.value)} placeholder="写下确认或撤销的理由，以及可复查的依据" rows={2} />
      <Button type="primary" disabled={!concept || !reason.trim()} loading={busy} onClick={() => concept && void updateMastery(concept, "confirm")}>确认掌握</Button>
      {mastery.filter(item => item.confirmed).map(item => <Space key={item.concept_uid} wrap><Tag color="blue">已确认</Tag><span>{item.concept_uid}</span><span>{item.reason}</span><Button size="small" disabled={!reason.trim()} loading={busy} onClick={() => void updateMastery(item.concept_uid, "revoke")}>撤销（使用上方理由）</Button></Space>)}
    </Space></Card>
    <Modal open={!!selected} title={selected?.title} onCancel={() => setSelected(undefined)} onOk={() => void saveStep()} okButtonProps={{ loading: busy, disabled: !!selected && selected.status === "needs_review" }}>
      <p>来源：不可变课题快照。记录产出不等于科研结论得到验证。</p>
      <Checkbox checked={done} onChange={event => setDone(event.target.checked)}>按快照验收条件完成</Checkbox>
      <Input.TextArea aria-label="步骤产出或观察" rows={4} style={{ marginTop: 12 }} value={outcome} onChange={event => setOutcome(event.target.value)} placeholder="记录观察、日志或结果文件位置" />
    </Modal>
  </Space>;
}
