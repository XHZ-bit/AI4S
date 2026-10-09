import { useInspector } from "../workspace/InspectorContext";
import { useEffect, useRef, useState } from "react";
import { Alert, Button, Card, Empty, Input, Modal, Select, Space, Spin, Tag, Timeline, Typography, message } from "antd";
import type { AsyncTask, ProtocolStep, ResearchDecision, ResearchProject, ProjectSnapshot, ValidationPlan } from "../../api/project-types";
import {
  createProjectSnapshot,
  generateProjectPlan,
  getProjectTask,
  isVersionConflict,
  listProjectDecisions,
  listProjectPlans,
  listProjectSnapshots,
  saveProjectPlan,
  snapshotExportUrl,
} from "../../api/projects";
import ProjectGraphPanel from "./ProjectGraphPanel";
import { ReviewStatusTag, SourceKindTag, TaskStatusTag } from "./StatusLabels";

const terminal = new Set(["succeeded", "failed", "interrupted"]);
const splitLines = (value: string) => value.split(/\n/).map(item => item.trim()).filter(Boolean);

function emptyStep(): ProtocolStep {
  return { id: crypto.randomUUID(), title: "", purpose: "", inputs: [], procedure: [], expected_observation: null, acceptance_criteria: [], evidence_ids: [] };
}

function emptyUserPlan(projectId: string, decision: ResearchDecision): ValidationPlan {
  return {
    id: null,
    project_id: projectId,
    version: 1,
    status: "draft",
    title: "",
    objective: "",
    hypothesis: null,
    selected_method_id: decision.selected_method_id,
    selected_experiment_setting_ids: decision.selected_experiment_setting_ids,
    assumptions: [],
    unknowns: [],
    steps: [],
    target_measurements: [],
    risks: [],
    source_kind: "user_input",
    review_status: "current",
    review_reasons: [],
  };
}

function recoverNewUserDraft(projectId: string): ValidationPlan | null {
  const key = `research-atlas:plan-draft:${projectId}:new`;
  const saved = localStorage.getItem(key);
  if (!saved) return null;
  try {
    const candidate = JSON.parse(saved) as Partial<ValidationPlan>;
    if (
      candidate.project_id === projectId
      && candidate.id === null
      && candidate.source_kind === "user_input"
      && candidate.status === "draft"
      && typeof candidate.version === "number"
      && typeof candidate.title === "string"
      && typeof candidate.objective === "string"
      && typeof candidate.selected_method_id === "string"
      && Array.isArray(candidate.selected_experiment_setting_ids)
      && Array.isArray(candidate.assumptions)
      && Array.isArray(candidate.unknowns)
      && Array.isArray(candidate.steps)
      && Array.isArray(candidate.target_measurements)
      && Array.isArray(candidate.risks)
      && Array.isArray(candidate.review_reasons)
    ) {
      return candidate as ValidationPlan;
    }
  } catch {
    // Invalid browser-local data is not a saved plan and must not block server history.
  }
  localStorage.removeItem(key);
  return null;
}

export default function PlansPanel({ project }: { project: ResearchProject }) {
  const inspector = useInspector();
  const [decisions, setDecisions] = useState<ResearchDecision[]>([]);
  const [plans, setPlans] = useState<ValidationPlan[]>([]);
  const [snapshots, setSnapshots] = useState<ProjectSnapshot[]>([]);
  const [draft, setDraft] = useState<ValidationPlan | null>(null);
  const [selectedPlanId, setSelectedPlanId] = useState<string | null>(null);
  const [selectedSnapshotId, setSelectedSnapshotId] = useState<string | null>(null);
  const [task, setTask] = useState<AsyncTask | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [conflict, setConflict] = useState(false);
  const [confirmSave, setConfirmSave] = useState(false);
  const lock = useRef(false);

  const reload = async (signal?: AbortSignal) => {
    setLoading(true);
    try {
      const [decisionResult, planResult, snapshotResult] = await Promise.all([
        listProjectDecisions(project.id, signal),
        listProjectPlans(project.id, signal),
        listProjectSnapshots(project.id, signal),
      ]);
      setDecisions(decisionResult.items);
      setPlans(planResult.items);
      setSnapshots(snapshotResult.items);
      setSelectedSnapshotId(current => current ?? snapshotResult.items[0]?.id ?? null);
      if (!draft) {
        const recovered = recoverNewUserDraft(project.id);
        if (recovered) {
          setDraft(recovered);
          setSelectedPlanId(null);
        } else if (planResult.items.length) {
          const remembered = localStorage.getItem(`research-atlas:selected-plan:${project.id}`);
          selectPlan(planResult.items.find(plan => plan.id === remembered) ?? planResult.items[0]);
        }
      }
    } catch (caught) {
      if (!(caught instanceof DOMException && caught.name === "AbortError")) setError(caught instanceof Error ? caught.message : "方案历史加载失败");
    } finally { if (!signal?.aborted) setLoading(false); }
  };

  useEffect(() => {
    const controller = new AbortController();
    void reload(controller.signal);
    return () => controller.abort();
  }, [project.id]);

  useEffect(() => {
    if (!task || terminal.has(task.status)) return;
    let disposed = false;
    const timer = window.setInterval(() => {
      void getProjectTask(task.id).then(next => {
        if (disposed) return;
        setTask(next);
        if (next.status === "succeeded") {
          const result = next.result as { plan?: ValidationPlan } | ValidationPlan | null;
          const plan = result && "project_id" in result ? result : result?.plan;
          if (plan) selectPlan(plan);
          void reload();
        }
      }).catch(caught => { if (!disposed) setError(caught instanceof Error ? caught.message : "生成任务状态读取失败"); });
    }, 1800);
    return () => { disposed = true; window.clearInterval(timer); };
  }, [task]);

  useEffect(() => {
    if (!draft) return;
    localStorage.setItem(`research-atlas:plan-draft:${project.id}:${draft.id ?? "new"}`, JSON.stringify(draft));
  }, [draft, project.id]);

  const selectPlan = (plan: ValidationPlan) => {
    if (plan.id) localStorage.setItem(`research-atlas:selected-plan:${project.id}`, plan.id);
    const key = `research-atlas:plan-draft:${project.id}:${plan.id ?? "new"}`;
    const saved = localStorage.getItem(key);
    let recovered = plan;
    if (saved) {
      try { recovered = JSON.parse(saved) as ValidationPlan; } catch { localStorage.removeItem(key); }
    }
    setDraft(recovered);
    setSelectedPlanId(plan.id);
  };

  const runOnce = async (operation: () => Promise<void>) => {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setError("");
    setConflict(false);
    try { await operation(); } finally { lock.current = false; setBusy(false); }
  };

  const generate = (decision: ResearchDecision) => void runOnce(async () => {
    try {
      const created = await generateProjectPlan(project.id, { expected_project_version: project.version, decision_id: decision.id, decision_version: decision.version });
      setTask(created);
      message.success("方案生成任务已提交；历史方案仍可查看");
    } catch (caught) { setError(caught instanceof Error ? caught.message : "方案生成失败"); }
  });

  const createManualDraft = (decision: ResearchDecision) => {
    if (draft?.id === null) {
      message.warning("已有未保存的人工草稿，请先保存后再新建");
      return;
    }
    setDraft(emptyUserPlan(project.id, decision));
    setSelectedPlanId(null);
    message.info("已创建人工草稿；未调用模型，也未生成任何实验结论");
  };

  const save = () => void runOnce(async () => {
    if (!draft) return;
    const stableId = draft.id ?? `draft-${crypto.randomUUID()}`;
    const bodyPlan = { ...draft, id: stableId };
    try {
      const saved = await saveProjectPlan(project.id, stableId, { expected_project_version: project.version, expected_plan_version: draft.id ? draft.version : 0, plan: bodyPlan });
      localStorage.removeItem(`research-atlas:plan-draft:${project.id}:${draft.id ?? "new"}`);
      setDraft(saved);
      setSelectedPlanId(saved.id);
      if (saved.id) localStorage.setItem(`research-atlas:selected-plan:${project.id}`, saved.id);
      setConfirmSave(false);
      message.success("方案已保存为新版本");
      await reload();
    } catch (caught) {
      if (isVersionConflict(caught)) setConflict(true);
      setError(caught instanceof Error ? caught.message : "方案保存失败");
    }
  });

  const patchDraft = (patch: Partial<ValidationPlan>) => setDraft(current => current ? { ...current, ...patch } : current);
  const patchStep = (index: number, patch: Partial<ProtocolStep>) => setDraft(current => current ? { ...current, steps: current.steps.map((step, stepIndex) => stepIndex === index ? { ...step, ...patch } : step) } : current);

  if (loading) return <Spin />;
  return <Space direction="vertical" size="large" className="research-plans" style={{ width: "100%" }}>
    {conflict && <Alert type="warning" showIcon message="方案版本冲突" description="本地草稿已保留在浏览器中。请查看服务端历史并人工合并，系统不会静默重试或清空输入。" />}
    {error && <Alert type="error" showIcon message="方案操作失败" description={error} />}
    {task && <Alert type={task.status === "failed" ? "error" : task.status === "succeeded" ? "success" : "info"} showIcon message={<Space>生成任务 <TaskStatusTag status={task.status} /></Space>} description={task.error?.message ?? (terminal.has(task.status) ? "任务已结束；历史方案仍然可用。" : "任务进行中，可离开页面后稍后回来查看。")}/>} 
    <Card title="创建首轮验证方案">
      <Alert type="info" showIcon message="两种创建方式来源不同" description="模型生成会提交异步任务，服务不可用时明确失败；人工草稿不调用模型，来源固定为用户输入，除路线引用外所有内容保持空白并由你填写。" style={{ marginBottom: 16 }} />
      {decisions.length === 0 ? <Empty description="还没有保存的路线选择。请先在候选比较中选定路线并填写理由，才能创建与路线绑定的方案。" /> : <Space direction="vertical" style={{ width: "100%" }}>{decisions.map(decision => <Space key={`${decision.id}:${decision.version}`} wrap>
        <Typography.Text>路线 {decision.id.slice(-8)} v{decision.version}</Typography.Text>
        <Button loading={busy && !task} onClick={() => generate(decision)}>使用模型生成</Button>
        <Button disabled={draft?.id === null} onClick={() => createManualDraft(decision)}>人工创建空白草稿</Button>
      </Space>)}</Space>}
    </Card>
    <Card title="方案编辑" extra={<Space><Select value={selectedPlanId ?? undefined} placeholder="选择已保存版本" style={{ minWidth: 220 }} options={plans.map(plan => ({ value: plan.id!, label: `${plan.title} · v${plan.version}${plan.review_status === "needs_review" ? " · 待复核" : ""}` }))} onChange={id => { const plan = plans.find(item => item.id === id); if (plan) selectPlan(plan); }} /><Button disabled={!draft} type="primary" onClick={() => setConfirmSave(true)}>确认保存</Button></Space>}>
      {!draft ? <Empty description="可使用模型生成，或不调用模型直接创建人工草稿；生成失败不会覆盖历史内容。" /> : <Space direction="vertical" style={{ width: "100%" }}>
        <Space wrap><Tag color="orange">本地草稿·自动恢复</Tag><SourceKindTag source={draft.source_kind} /><ReviewStatusTag status={draft.review_status} />{draft.review_reasons.map(reason => <Tag color="volcano" key={reason}>{reason}</Tag>)}<a href={`/research/${project.id}/print/draft?plan_id=${encodeURIComponent(draft.id ?? "new")}`} target="_blank" rel="noreferrer">打印未保存草稿</a></Space>
        <Typography.Text strong>标题</Typography.Text><Input aria-label="方案标题" value={draft.title} onChange={event => patchDraft({ title: event.target.value })} />
        <Typography.Text strong>目标</Typography.Text><Input.TextArea aria-label="方案目标" rows={3} value={draft.objective} onChange={event => patchDraft({ objective: event.target.value })} />
        <Typography.Text strong>待验证假设</Typography.Text><Input.TextArea rows={3} value={draft.hypothesis ?? ""} onChange={event => patchDraft({ hypothesis: event.target.value || null })} placeholder="没有假设时保持为空，不要编造" />
        <Typography.Text strong>假设条件（每行一项）</Typography.Text><Input.TextArea rows={3} value={draft.assumptions.join("\n")} onChange={event => patchDraft({ assumptions: splitLines(event.target.value) })} />
        <Typography.Text strong>未知项（每行一项）</Typography.Text><Input.TextArea rows={3} value={draft.unknowns.join("\n")} onChange={event => patchDraft({ unknowns: splitLines(event.target.value) })} />
        <Typography.Title level={5}>验证步骤</Typography.Title>
        {draft.steps.map((step, index) => <Card size="small" key={step.id} title={<Space wrap><span>步骤 {index + 1}</span>{step.evidence_ids.map(id=><Button size="small" key={id} onClick={()=>inspector.inspect({kind:"evidence",id})}>查看步骤依据</Button>)}</Space>} extra={<Button danger onClick={() => patchDraft({ steps: draft.steps.filter(item => item.id !== step.id) })}>移除</Button>}>
          <Input style={{ marginBottom: 8 }} value={step.title} onChange={event => patchStep(index, { title: event.target.value })} placeholder="步骤标题" />
          <Input.TextArea style={{ marginBottom: 8 }} value={step.purpose} onChange={event => patchStep(index, { purpose: event.target.value })} placeholder="目的" />
          <Input.TextArea style={{ marginBottom: 8 }} value={step.procedure.join("\n")} onChange={event => patchStep(index, { procedure: splitLines(event.target.value) })} placeholder="操作，每行一步" />
          <Input.TextArea value={step.acceptance_criteria.join("\n")} onChange={event => patchStep(index, { acceptance_criteria: splitLines(event.target.value) })} placeholder="验收标准，每行一项" />
        </Card>)}
        <Button onClick={() => patchDraft({ steps: [...draft.steps, emptyStep()] })}>添加步骤</Button>
        <Typography.Text strong>目标测量 ID（每行一项）</Typography.Text><Input.TextArea rows={2} value={draft.target_measurements.join("\n")} onChange={event => patchDraft({ target_measurements: splitLines(event.target.value) })} />
        <Typography.Text strong>风险（每行一项）</Typography.Text><Input.TextArea rows={3} value={draft.risks.join("\n")} onChange={event => patchDraft({ risks: splitLines(event.target.value) })} />
      </Space>}
    </Card>
    <Card title="保存与快照历史">
      {plans.length === 0 ? <Empty description="没有已保存方案版本" /> : <Timeline items={plans.map(plan => ({ color: plan.review_status === "needs_review" ? "orange" : "green", children: <Space wrap><strong>{plan.title}</strong><Tag>v{plan.version}</Tag><ReviewStatusTag status={plan.review_status} />{plan.review_reasons.map(reason => <Tag color="volcano" key={reason}>{reason}</Tag>)}<Button disabled={!plan.id || busy} onClick={() => void runOnce(async () => { if (!plan.id) return; try { const snapshot = await createProjectSnapshot(project.id, { expected_project_version: project.version, plan_id: plan.id, plan_version: plan.version }); message.success("不可变快照已创建"); setSelectedSnapshotId(snapshot.id); await reload(); } catch (caught) { setError(caught instanceof Error ? caught.message : "快照创建失败"); } })}>创建不可变快照</Button></Space> }))} />}
      <Typography.Title level={5}>快照</Typography.Title>
      {snapshots.length === 0 ? <Typography.Text type="secondary">没有快照。打印和导出应基于不可变快照，而不是未保存草稿。</Typography.Text> : <Space direction="vertical" style={{ width: "100%" }}>{snapshots.map(snapshot => <Card size="small" key={snapshot.id}><Space wrap><Button type={selectedSnapshotId === snapshot.id ? "primary" : "default"} onClick={() => setSelectedSnapshotId(snapshot.id)}>快照 v{snapshot.snapshot_version}</Button><ReviewStatusTag status={snapshot.review_status} />{snapshot.review_reasons.map(reason => <Tag color="volcano" key={reason}>{reason}</Tag>)}<a href={snapshotExportUrl(project.id, snapshot.id, "json")}>导出 JSON</a><a href={snapshotExportUrl(project.id, snapshot.id, "markdown")}>导出 Markdown</a><a href={`/research/${project.id}/print/${snapshot.id}`} target="_blank" rel="noreferrer">打印 / 保存 PDF</a><a href={`/research/${project.id}/graph?snapshot_id=${encodeURIComponent(snapshot.id)}&mode=evidence&node_id=${encodeURIComponent(snapshot.plan.id ?? snapshot.id)}`}>查看依据</a></Space></Card>)}</Space>}
      <p><a href={`/research/${project.id}/graph${selectedSnapshotId ? `?snapshot_id=${encodeURIComponent(selectedSnapshotId)}` : ""}`}>打开完整课题图谱</a></p>
    </Card>
    <Card title="快照依据关系"><ProjectGraphPanel projectId={project.id} snapshotId={selectedSnapshotId} /></Card>
    <Modal title="确认保存方案" open={confirmSave} confirmLoading={busy} onCancel={() => setConfirmSave(false)} onOk={save} okText="保存新版本">
      <Alert type="warning" showIcon message="保存不会自动确认未知项" description="请确认来源、未知项、未保存状态和待复核原因均已如实保留。保存将创建新版本，不会覆盖旧版本。" />
    </Modal>
  </Space>;
}
