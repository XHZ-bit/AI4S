import { useEffect, useRef, useState } from "react";
import { Link,useSearchParams } from "react-router-dom";
import { Alert, Button, Card, Checkbox, Input, Modal, Pagination, Select, Space, Tag, Typography, Segmented } from "antd";
import { apiGet } from "../api/client";
import { changeMastery, getMastery, getStepRecord, listMastery, saveStepRecord, workflowActivities, workflowOverview, workflowRecommendations, type ActivityKind, type Mastery, type StepRecord, type WorkflowActivity, type WorkflowOverview, type WorkflowRecommendations } from "../api/workflow";
import "./workflow-hub.css";
import Tasks from "./Tasks";

const statusText = { pending: "待执行", in_progress: "进行中", completed: "已记录", needs_review: "待复核" };
const evidenceText = { none: "暂无记录", recorded: "用户记录", checked: "固定检查通过" };
const kindText = { roadmap: "正式路线", paper: "论文", case: "案例", project: "课题快照" };

export default function WorkflowHub() {
 const [params,setParams]=useSearchParams();const processing=params.get("view")==="processing";
 return <section className="workflow-unified"><header className="workflow-unified-head"><h1>任务与行动</h1><p>继续自己的研究，或查看资料在后台的处理情况。</p></header><Segmented aria-label="任务视图" value={processing?"processing":"actions"} options={[{value:"actions",label:"我的行动"},{value:"processing",label:"系统处理"}]} onChange={value=>setParams(old=>{const n=new URLSearchParams(old);n.set("view",String(value));return n;})}/>{processing?<div className="workflow-system"><Tasks/></div>:<PersonalActions/>}</section>;
}

function PersonalActions() {
  const [overview, setOverview] = useState<WorkflowOverview>();
  const [recommendations, setRecommendations] = useState<WorkflowRecommendations>();
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
  const [minutes, setMinutes] = useState(60);
  const [agenda, setAgenda] = useState<any>();
  const [agendaError, setAgendaError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    apiGet<any>("/api/workflow/v1/agenda", {minutes}, controller.signal).then(value=>{setAgenda(value);setAgendaError("");})
      .catch(caught=>{if(!controller.signal.aborted)setAgendaError(String(caught));});
    return()=>controller.abort();
  }, [minutes, items]);

  const request = useRef(0);
  const [sectionErrors, setSectionErrors] = useState<Record<string,string>>({});
  const reload = async () => {
    const generation = ++request.current;
    const results = await Promise.allSettled([
      workflowOverview(), workflowActivities({ source_kind: kind, offset: (page - 1) * 50, limit: 50 }), listMastery(), workflowRecommendations(),
    ]);
    if (generation !== request.current) return;
    const errors: Record<string,string> = {};
    const names = ["概览", "活动", "掌握记录", "建议"];
    results.forEach((result,index) => { if (result.status === "rejected") errors[names[index]] = String(result.reason); });
    if (results[0].status === "fulfilled") setOverview(results[0].value as WorkflowOverview);
    if (results[1].status === "fulfilled") { const value = results[1].value as {items:WorkflowActivity[];total:number};setItems(value.items);setTotal(value.total); }
    if (results[2].status === "fulfilled") setMastery((results[2].value as {items:Mastery[]}).items);
    if (results[3].status === "fulfilled") setRecommendations(results[3].value as WorkflowRecommendations);
    setSectionErrors(errors);
  };
  useEffect(() => { void reload(); return () => { request.current++; }; }, [kind,page]);
  useEffect(() => { void apiGet<{items: typeof targets}>("/api/roadmap/targets").then(result=>setTargets(result.items)).catch(caught=>setError(`概念候选加载失败：${caught}`)); }, []);

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

  return <div className="atlas-workflow-page">
    <header className="workflow-page-head">
      <Link to="/actions">打开已保存的自动行动清单 →</Link>
    </header>
    {Object.entries(sectionErrors).map(([name, detail]) => <Alert key={name} type="warning" message={`${name}加载失败；其它分区仍可使用`} description={detail} action={<Button onClick={() => void reload()}>重试分区</Button>} />)}
    <div className="workflow-summary-grid"><Card className="workflow-agenda" title="按本次时间安排活动" extra={<Select aria-label="本次时间预算" value={minutes} onChange={setMinutes} options={[30,60,120].map(value=>({value,label:`${value} 分钟`}))}/> }>
      {agendaError && <Alert type="warning" message="时间安排暂不可用" description={agendaError}/>}
      {agenda?.items?.map((item:WorkflowActivity)=><p className="workflow-agenda-item" key={item.id}><Link to={item.url}>{item.title}</Link><span>估算 {item.estimated_minutes} 分钟</span></p>)}
      {agenda?.notice&&<p className="workflow-agenda-notice">{agenda.notice} 未排期 {agenda.unscheduled_count} 项。</p>}
    </Card>
    {overview && <Card className="workflow-overview" title="当前概览"><div className="workflow-counts"><span>待执行 <strong>{overview.counts.pending}</strong></span><span>进行中 <strong>{overview.counts.in_progress}</strong></span><span>待复核 <strong>{overview.counts.needs_review}</strong></span><span>已记录 <strong>{overview.counts.completed}</strong></span></div>{overview.snapshot_required > 0 && <p>有 {overview.snapshot_required} 份已保存方案尚无对应快照。<Link to="/research">创建快照后再执行 →</Link></p>}</Card>}</div>
    {error && <Alert type="error" message={error} closable onClose={() => setError("")} />}
    {recommendations && <Card className="workflow-recommendations" title="根据当前记录建议下一步" extra={<Tag>自动建议 {recommendations.total}</Tag>}>
      {recommendations.items.length ? recommendations.items.map(item => <div key={item.id} className="atlas-list-row">
        <Space wrap><Tag color={item.kind === "source_review" ? "orange" : item.kind === "practice_review" ? "red" : "blue"}>第 {item.rank} 项</Tag><Link to={item.url}>{item.title}</Link>{item.estimated_minutes != null && <Tag>估算 {item.estimated_minutes} 分钟</Tag>}</Space>
        <Typography.Paragraph type="secondary" style={{ margin: "4px 0 0" }}>排序依据：{item.priority_reason}（规则分 {item.priority_score}） · {item.reason}{item.related_activity_count > 1 && ` · 同源活动 ${item.related_activity_count} 项`}</Typography.Paragraph>
      </div>) : <Typography.Text type="secondary">暂无待复核、待重试或可继续的活动。</Typography.Text>}
      {recommendations.truncated && <Typography.Paragraph type="secondary">当前显示前 20 项；其余活动可在下方列表查找。</Typography.Paragraph>}
      <Typography.Paragraph type="secondary" style={{ marginTop: 12 }}>{recommendations.notice}</Typography.Paragraph>
    </Card>}
    <Card className="workflow-activities" title="全部活动" extra={<Select allowClear placeholder="按来源筛选" style={{ width: 170 }} value={kind} onChange={value => { setKind(value); setPage(1); }} options={Object.entries(kindText).map(([value, label]) => ({ value, label }))} />}>
      {items.map(item => <div key={item.id} className="atlas-list-row"><Space wrap><Link to={item.url}>{item.title}</Link><Tag>{kindText[item.source_kind]}</Tag><Tag color={item.status === "needs_review" ? "orange" : undefined}>{statusText[item.status]}</Tag><Tag>{evidenceText[item.evidence_level]}</Tag>{item.estimated_minutes != null && <Tag>估算 {item.estimated_minutes} 分钟</Tag>}{item.source_kind === "project" && <Button size="small" disabled={item.status === "needs_review"} onClick={() => void openStep(item)}>记录步骤产出</Button>}</Space><div className="atlas-list-row-detail">{item.detail}</div></div>)}
      {!items.length && !sectionErrors["活动"] && <p>暂无符合条件的活动。</p>}
      {total > 50 && <Pagination current={page} pageSize={50} total={total} onChange={setPage} style={{ marginTop: 16 }} />}
    </Card>
    <details className="workflow-mastery-disclosure"><summary>查看与调整概念掌握记录</summary><Card className="workflow-mastery" title="确认或撤销概念掌握"><Space direction="vertical" style={{ width: "100%" }}>
      <Typography.Paragraph type="secondary">请写明可复查的理由。练习通过不会自动确认掌握，确认后也可以撤销。</Typography.Paragraph>
      <Select showSearch filterOption={false} placeholder="选择已核验的概念或方法" value={concept} onChange={setConcept} onSearch={q => void apiGet<{items: typeof targets}>("/api/roadmap/targets", {q}).then(r => setTargets(r.items)).catch(caught => setError(String(caught)))} options={targets.map(t => ({ value: t.uid, label: `${t.name} · ${t.uid}` }))} />
      <Select allowClear placeholder="关联一项活动（可选）" value={activityId} onChange={setActivityId} showSearch optionFilterProp="label" options={items.map(item => ({ value: item.id, label: item.title }))} />
      <Input.TextArea aria-label="掌握记录理由" value={reason} onChange={event => setReason(event.target.value)} placeholder="写下确认或撤销的理由，以及可复查的依据" rows={2} />
      <Button type="primary" disabled={!concept || !reason.trim()} loading={busy} onClick={() => concept && void updateMastery(concept, "confirm")}>确认掌握</Button>
      {mastery.filter(item => item.confirmed).map(item => <Space key={item.concept_uid} wrap><Tag color="blue">已确认</Tag><span>{item.concept_uid}</span><span>{item.reason}</span><Button size="small" disabled={!reason.trim()} loading={busy} onClick={() => void updateMastery(item.concept_uid, "revoke")}>撤销（使用上方理由）</Button></Space>)}
    </Space></Card></details>
    <Modal open={!!selected} title={selected?.title} onCancel={() => setSelected(undefined)} onOk={() => void saveStep()} okButtonProps={{ loading: busy, disabled: !!selected && selected.status === "needs_review" }}>
      <p>来源：不可变课题快照。记录产出不等于科研结论得到验证。</p>
      <Checkbox checked={done} onChange={event => setDone(event.target.checked)}>按快照验收条件完成</Checkbox>
      <Input.TextArea aria-label="步骤产出或观察" rows={4} style={{ marginTop: 12 }} value={outcome} onChange={event => setOutcome(event.target.value)} placeholder="记录观察、日志或结果文件位置" />
    </Modal>
  </div>;
}
