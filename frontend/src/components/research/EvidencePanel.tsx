import { useInspector } from "../workspace/InspectorContext";
import { useEffect, useMemo, useRef, useState } from "react";
import { Alert, Button, Card, Collapse, Descriptions, Empty, Form, Input, Modal, Select, Space, Spin, Tag, Typography, Upload, message } from "antd";
import { UploadOutlined } from "@ant-design/icons";
import { Link } from "react-router-dom";
import type {
  AsyncTask,
  EvidenceRef,
  ExperimentSetting,
  MethodCard,
  PaperLink,
  PaperRole,
  ProjectFactsResponse,
  RecordStatus,
  ResearchProject,
} from "../../api/project-types";
import { listPapers, uploadPdf } from "../../api/papers";
import {
  getProjectFacts,
  getProjectTask,
  isVersionConflict,
  linkProjectPaper,
  listProjectPapers,
  retryProjectTask,
  startProjectExtraction,
  transitionFact,
} from "../../api/projects";
import EvidenceDrawer from "./EvidenceDrawer";
import { FindingStatusTag, RecordStatusTag, SourceKindTag, TaskStatusTag, displayKnown } from "./StatusLabels";

type ExistingPaper = { uid: string; title: string; year?: number | null };
type TransitionTarget = { id: string; version: number; status: RecordStatus; label: string };

const roleOptions: { value: PaperRole; label: string }[] = [
  { value: "primary", label: "核心论文" },
  { value: "method", label: "方法" },
  { value: "baseline", label: "基线" },
  { value: "dataset", label: "数据集" },
  { value: "evaluation", label: "评估" },
  { value: "background", label: "背景" },
];

const terminal = new Set(["succeeded", "failed", "interrupted"]);

export default function EvidencePanel({ project, onProjectReload }: { project: ResearchProject; onProjectReload: () => Promise<void> }) {
  const inspector = useInspector();
  const [links, setLinks] = useState<PaperLink[]>([]);
  const [facts, setFacts] = useState<ProjectFactsResponse>({ methods: [], experiment_settings: [], measurements: [], evidence: [] });
  const [paperOptions, setPaperOptions] = useState<ExistingPaper[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [tasks, setTasks] = useState<Record<string, AsyncTask>>({});
  const [selectedEvidence, setSelectedEvidence] = useState<EvidenceRef | null>(null);
  const [transitionTarget, setTransitionTarget] = useState<TransitionTarget | null>(null);
  const [transitionStatus, setTransitionStatus] = useState<RecordStatus>("user_confirmed");
  const [transitionReason, setTransitionReason] = useState("");
  const [actor, setActor] = useState("");
  const [linkForm] = Form.useForm();
  const actionLock = useRef(false);

  const reload = async (signal?: AbortSignal) => {
    setLoading(true);
    setError("");
    try {
      const [paperLinks, factResult] = await Promise.all([
        listProjectPapers(project.id, signal),
        getProjectFacts(project.id, {}, signal),
      ]);
      setLinks(paperLinks.items);
      setFacts(factResult);
    } catch (caught) {
      if (!(caught instanceof DOMException && caught.name === "AbortError")) setError(caught instanceof Error ? caught.message : "资料加载失败");
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  };

  useEffect(() => {
    const controller = new AbortController();
    void reload(controller.signal);
    void listPapers(100, 0).then(result => setPaperOptions(result.items)).catch(caught => setError(caught instanceof Error ? caught.message : "论文库加载失败"));
    return () => controller.abort();
  }, [project.id]);

  useEffect(() => {
    const activeIds = Object.values(tasks).filter(task => !terminal.has(task.status)).map(task => task.id);
    if (!activeIds.length) return;
    let disposed = false;
    const timer = window.setInterval(() => {
      activeIds.forEach(taskId => {
        void getProjectTask(taskId).then(task => {
          if (!disposed) setTasks(current => ({ ...current, [task.id]: task }));
          if (!disposed && task.status === "succeeded") void reload();
        }).catch(caught => {
          if (!disposed) setError(caught instanceof Error ? caught.message : "任务状态读取失败");
        });
      });
    }, 1800);
    return () => { disposed = true; window.clearInterval(timer); };
  }, [tasks]);

  const evidenceById = useMemo(() => new Map(facts.evidence.map(item => [item.id, item])), [facts.evidence]);
  const settingsByMethod = (methodId: string) => facts.experiment_settings.filter(item => item.method_id === methodId);
  const measurementsBySetting = (settingId: string) => facts.measurements.filter(item => item.experiment_setting_id === settingId);

  const runOnce = async (operation: () => Promise<void>) => {
    if (actionLock.current) return;
    actionLock.current = true;
    setBusy(true);
    setError("");
    try { await operation(); } finally { actionLock.current = false; setBusy(false); }
  };

  const sourceButtons = (ids: string[]) => ids.length ? <Space wrap>{ids.map(id => <Button size="small" key={id} onClick={() => inspector.available ? inspector.inspect({kind:"evidence",id}) : setSelectedEvidence(evidenceById.get(id) ?? null)}>来源 {id.slice(-6)}</Button>)}</Space> : <Typography.Text type="secondary">无绑定来源；请按缺失项处理</Typography.Text>;

  const fieldEvidence = (item: MethodCard | ExperimentSetting) => item.field_evidence.length ? <Collapse size="small" items={item.field_evidence.map(field => ({
    key: field.field_path,
    label: <Space wrap><Typography.Text code>{field.field_path}</Typography.Text><SourceKindTag source={field.source_kind} /><FindingStatusTag status={field.finding_status} /></Space>,
    children: <Space direction="vertical"><Typography.Text>{field.note || "没有额外说明"}</Typography.Text>{sourceButtons(field.evidence_ids)}</Space>,
  }))} /> : <Alert type="warning" message="此记录没有逐字段来源绑定" />;

  const beginTransition = (item: MethodCard | ExperimentSetting, label: string) => {
    setTransitionTarget({ id: item.id, version: item.version, status: item.status, label });
    setTransitionStatus(item.status === "withdrawn" ? "candidate" : "user_confirmed");
    setTransitionReason("");
  };

  const localDraft = (item: MethodCard | ExperimentSetting) => {
    const key = `research-atlas:fact-draft:${project.id}:${item.id}`;
    const current = localStorage.getItem(key) ?? ("summary" in item ? item.summary ?? "" : item.notes.join("\n"));
    return <Card size="small" title="人工修正草稿（仅保存在本机）" extra={<Tag color="orange">未保存到服务端</Tag>}>
      <Input.TextArea defaultValue={current} rows={3} onChange={event => localStorage.setItem(key, event.target.value)} />
      <Typography.Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0 }}>公共契约尚无事实内容修订接口。此草稿刷新后保留，但不会伪装成已保存或文献报告。</Typography.Paragraph>
    </Card>;
  };

  const renderSetting = (setting: ExperimentSetting) => <Card size="small" key={setting.id} title={<Space wrap><span>{setting.name}</span><RecordStatusTag status={setting.status} /><FindingStatusTag status={setting.finding_status} /></Space>} extra={<Button onClick={() => beginTransition(setting, setting.name)}>审核状态</Button>}>
    <Descriptions size="small" column={{ xs: 1, sm: 2 }} items={[
      { key: "dataset", label: "数据集", children: displayKnown(setting.dataset) },
      { key: "version", label: "数据版本", children: displayKnown(setting.dataset_version) },
      { key: "split", label: "划分", children: displayKnown(setting.split) },
      { key: "protocol", label: "评估协议", children: displayKnown(setting.evaluation_protocol) },
      { key: "seed", label: "随机种子", children: displayKnown(setting.random_seed) },
      { key: "preprocess", label: "预处理", children: setting.preprocessing.length ? setting.preprocessing.join("；") : "未知/未报告" },
    ]} />
    <Typography.Title level={5}>测量结果</Typography.Title>
    {measurementsBySetting(setting.id).length ? measurementsBySetting(setting.id).map(measurement => <div key={measurement.id} className="research-measurement-row"><Space wrap><strong>{measurement.metric_name}</strong><span>{measurement.value ? `${measurement.value.value}${measurement.value.unit ?? ""} (${measurement.value.scale})` : "未知/未报告"}</span><RecordStatusTag status={measurement.status} /><FindingStatusTag status={measurement.finding_status} /></Space></div>) : <Typography.Text type="secondary">没有测量候选；不能按 0 处理。</Typography.Text>}
    <div style={{ marginTop: 12 }}>{fieldEvidence(setting)}</div><div style={{ marginTop: 12 }}>{localDraft(setting)}</div>
  </Card>;

  return <Space direction="vertical" size="large" style={{ width: "100%" }}>
    {error && <Alert type="error" showIcon message="资料操作失败" description={error} action={<Button onClick={() => void reload()}>重新加载</Button>} />}
    <Card title="关联论文与上传">
      <Alert style={{ marginBottom: 16 }} type="info" showIcon message="先复用论文库，再关联到课题" description="上传沿用现有论文能力；上传成功不等于已关联或抽取成功。" />
      <Form form={linkForm} layout="inline" onFinish={values => void runOnce(async () => {
        try {
          await linkProjectPaper(project.id, { expected_project_version: project.version, paper_uid: values.paper_uid, role: values.role, note: values.note || null });
          message.success("论文已关联");
          linkForm.resetFields();
          await onProjectReload();
          await reload();
        } catch (caught) {
          setError(isVersionConflict(caught) ? `项目版本冲突：${caught.message}。表单内容已保留。` : caught instanceof Error ? caught.message : "关联失败");
        }
      })} initialValues={{ role: "method" }}>
        <Form.Item name="paper_uid" rules={[{ required: true, message: "请选择已有论文" }]}><Select showSearch optionFilterProp="label" style={{ minWidth: 280 }} placeholder="选择论文库中的论文" options={paperOptions.map(paper => ({ value: paper.uid, label: `${paper.title}${paper.year ? ` · ${paper.year}` : ""}` }))} /></Form.Item>
        <Form.Item name="role"><Select style={{ width: 130 }} options={roleOptions} /></Form.Item>
        <Form.Item name="note"><Input placeholder="关联说明（可选）" /></Form.Item>
        <Button type="primary" htmlType="submit" loading={busy}>关联</Button>
      </Form>
      <Upload accept="application/pdf" showUploadList={false} customRequest={({ file, onSuccess, onError }) => void runOnce(async () => {
        try {
          const result = await uploadPdf(file as File);
          message.success(`上传任务已提交${result?.task_id ? `：${result.task_id}` : ""}；完成后请刷新论文库再关联`);
          onSuccess?.(result);
          const refreshed = await listPapers(100, 0);
          setPaperOptions(refreshed.items);
        } catch (caught) {
          setError(caught instanceof Error ? caught.message : "上传失败");
          onError?.(caught as Error);
        }
      })}><Button style={{ marginTop: 12 }} icon={<UploadOutlined />} loading={busy}>上传 PDF 到论文库</Button></Upload>
    </Card>
    <Card title="课题资料">
      {links.length === 0 ? <Empty description="尚未关联论文" /> : <Space direction="vertical" style={{ width: "100%" }}>{links.map(link => <Card size="small" key={link.id} title={<Space wrap><Typography.Text copyable>{link.paper_uid}</Typography.Text><Tag>{roleOptions.find(role => role.value === link.role)?.label}</Tag><Tag color={link.status === "active" ? "green" : "default"}>{link.status === "active" ? "已关联" : "已移除"}</Tag></Space>} extra={<Button disabled={link.status !== "active" || !link.linked_document_id} loading={busy} onClick={() => void runOnce(async () => {
        try {
          const task = await startProjectExtraction(project.id, link.id, { expected_project_version: project.version, document_id: link.linked_document_id! });
          setTasks(current => ({ ...current, [task.id]: task }));
          message.success("抽取任务已提交");
        } catch (caught) { setError(caught instanceof Error ? caught.message : "抽取任务提交失败"); }
      })}>{link.linked_document_id ? "提取方法与条件" : "没有可用文档版本"}</Button>}>
        <Typography.Text type="secondary">固定文档：{link.linked_document_id ? `${link.linked_document_id} · ${displayKnown(link.linked_document_version)}` : "未知/尚未解析"}</Typography.Text>
      </Card>)}</Space>}
    </Card>
    {Object.values(tasks).length > 0 && <Card title="本次任务状态"><Space direction="vertical" style={{ width: "100%" }}>{Object.values(tasks).map(task => <Card size="small" key={task.id}><Space wrap><Typography.Text copyable>{task.id}</Typography.Text><TaskStatusTag status={task.status} />{task.progress !== null && <span>{Math.round(task.progress * 100)}%</span>}{task.error && <Typography.Text type="danger">{task.error.message}</Typography.Text>}{["failed", "interrupted"].includes(task.status) && <Button onClick={() => void runOnce(async () => { const retried = await retryProjectTask(task.id); setTasks(current => ({ ...current, [retried.id]: retried })); })}>重试为新任务</Button>}</Space></Card>)}</Space></Card>}
    <Card title="方法、实验条件与来源">
      {loading ? <Spin /> : facts.methods.length === 0 ? <Empty description="尚无方法候选；历史资料仍可浏览，新的抽取失败时不会生成假数据。" /> : <>
        {(facts.experiment_settings.length === 0 || facts.measurements.length === 0) && <Alert style={{ marginBottom: 16 }} type="warning" message="抽取结果可能不完整" description="已有方法候选，但实验设置或测量候选为空。请查看任务错误和来源，不要把缺失解释为 0 或无条件。" />}
        <Space direction="vertical" style={{ width: "100%" }}>{facts.methods.map(method => <Card key={method.id} title={<Space wrap><span>{method.name}</span><RecordStatusTag status={method.status} /><FindingStatusTag status={method.finding_status} /><SourceKindTag source={method.source_kind} /></Space>} extra={<Space><Link to={`/research/${project.id}/graph?mode=method&node_id=${encodeURIComponent(method.id)}`}>查看实验设置</Link><Button onClick={() => beginTransition(method, method.name)}>审核状态</Button></Space>}>
          <Typography.Paragraph>{method.summary || "摘要未知/未报告"}</Typography.Paragraph>
          {fieldEvidence(method)}<div style={{ marginTop: 12 }}>{localDraft(method)}</div>
          <Typography.Title level={5} style={{ marginTop: 20 }}>实验设置</Typography.Title>
          <Space direction="vertical" style={{ width: "100%" }}>{settingsByMethod(method.id).length ? settingsByMethod(method.id).map(renderSetting) : <Typography.Text type="secondary">尚无实验设置，不能推断默认条件。</Typography.Text>}</Space>
        </Card>)}</Space></>}
    </Card>
    <Modal title={`修改审核状态：${transitionTarget?.label ?? ""}`} open={!!transitionTarget} confirmLoading={busy} onCancel={() => setTransitionTarget(null)} onOk={() => void runOnce(async () => {
      if (!transitionTarget || !actor.trim() || !transitionReason.trim()) { setError("审核人和理由不能为空"); return; }
      try {
        await transitionFact(project.id, transitionTarget.id, { expected_version: transitionTarget.version, from_status: transitionTarget.status, to_status: transitionStatus, actor, reason: transitionReason });
        message.success("审核状态已保存为新版本");
        setTransitionTarget(null);
        await reload();
      } catch (caught) { setError(isVersionConflict(caught) ? `事实版本冲突：${caught.message}` : caught instanceof Error ? caught.message : "状态更新失败"); }
    })}>
      <Space direction="vertical" style={{ width: "100%" }}>
        <Select value={transitionStatus} onChange={setTransitionStatus} options={transitionTarget?.status === "withdrawn" ? [{ value: "candidate", label: "恢复为候选（需重新确认）" }] : [
          ...(transitionTarget?.status !== "user_confirmed" ? [{ value: "user_confirmed", label: "用户确认" }] : []),
          { value: "disputed", label: "标记争议" },
          { value: "withdrawn", label: "撤回" },
        ]} />
        <Input value={actor} onChange={event => setActor(event.target.value)} placeholder="审核人" maxLength={200} />
        <Input.TextArea value={transitionReason} onChange={event => setTransitionReason(event.target.value)} placeholder="逐项核对后的理由" maxLength={4000} rows={4} />
      </Space>
    </Modal>
    <EvidenceDrawer evidence={selectedEvidence} projectId={project.id} onClose={() => setSelectedEvidence(null)} />
  </Space>;
}
