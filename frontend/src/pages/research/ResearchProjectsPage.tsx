import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Alert, Button, Card, Empty, Form, Input, Modal, Select, Space, Spin, Tag, Typography, message } from "antd";
import type { DomainId, ResearchProject, ResearchProjectCreate } from "../../api/project-types";
import { DOMAIN_PROFILES } from "../../api/project-types";
import { createProject, listProjects } from "../../api/projects";
import "./research-workspace.css";

type CreateValues = {
  title: string;
  research_question: string;
  domain: DomainId;
  objective: string;
  required_metrics?: string[];
  notes?: string;
};

export default function ResearchProjectsPage() {
  const navigate = useNavigate();
  const [items, setItems] = useState<ResearchProject[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState("");
  const [form] = Form.useForm<CreateValues>();
  const createLock = useRef(false);

  const reload = async (signal?: AbortSignal) => {
    setLoading(true);
    setError("");
    try {
      const result = await listProjects({ limit: 100 }, signal);
      setItems(result.items);
    } catch (caught) {
      if (!(caught instanceof DOMException && caught.name === "AbortError")) {
        setError(caught instanceof Error ? caught.message : "课题加载失败");
      }
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  };

  useEffect(() => {
    const controller = new AbortController();
    void reload(controller.signal);
    return () => controller.abort();
  }, []);

  const submit = async (values: CreateValues) => {
    if (createLock.current) return;
    createLock.current = true;
    setCreating(true);
    setError("");
    const body: ResearchProjectCreate = {
      title: values.title,
      research_question: values.research_question,
      domain: values.domain,
      constraints: {
        version: 1,
        objective: values.objective,
        allowed_datasets: [],
        excluded_datasets: [],
        required_metrics: values.required_metrics ?? [],
        compute: [],
        time_budget: null,
        cost_budget: null,
        data_access: [],
        notes: (values.notes ?? "").split(/\n/).map(item => item.trim()).filter(Boolean),
      },
    };
    try {
      const created = await createProject(body);
      message.success("课题已建立");
      setOpen(false);
      form.resetFields();
      navigate(`/research/${created.id}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "课题创建失败");
    } finally {
      createLock.current = false;
      setCreating(false);
    }
  };

  return <Space direction="vertical" size="large" style={{ width: "100%" }}>
    <div className="research-page-heading">
      <div><Typography.Title level={2}>科研课题</Typography.Title><Typography.Text type="secondary">从多篇论文证据出发，保存可追溯的路线选择与首轮验证方案。</Typography.Text></div>
      <Button type="primary" onClick={() => setOpen(true)}>建立课题</Button>
    </div>
    {error && <Alert type="error" showIcon message="操作失败" description={error} action={<Button onClick={() => void reload()}>重试</Button>} />}
    {loading ? <Spin /> : items.length === 0 ? <Card><Empty description="还没有课题"><Button type="primary" onClick={() => setOpen(true)}>建立第一个课题</Button></Empty></Card> :
      <div className="research-card-grid">{items.map(project => <Card key={project.id} hoverable onClick={() => navigate(`/research/${project.id}`)} title={project.title} extra={<Tag color={project.status === "active" ? "green" : "default"}>{project.status === "active" ? "进行中" : "已归档"}</Tag>}>
        <Typography.Paragraph ellipsis={{ rows: 2 }}>{project.research_question}</Typography.Paragraph>
        <Space wrap><Tag>{DOMAIN_PROFILES[project.domain].label}</Tag><Tag>项目 v{project.version}</Tag><Tag>约束 v{project.constraints.version}</Tag></Space>
        <Typography.Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0 }}>目标：{project.constraints.objective}</Typography.Paragraph>
      </Card>)}</div>}
    <Modal title="建立科研课题" open={open} onCancel={() => !creating && setOpen(false)} footer={null} destroyOnHidden>
      <Form form={form} layout="vertical" onFinish={submit} initialValues={{ domain: "image_anomaly_detection" }}>
        <Form.Item name="title" label="课题名称" rules={[{ required: true, whitespace: true }]}><Input maxLength={300} /></Form.Item>
        <Form.Item name="research_question" label="研究问题" rules={[{ required: true, whitespace: true }]}><Input.TextArea rows={3} maxLength={4000} /></Form.Item>
        <Form.Item name="domain" label="研究领域" rules={[{ required: true }]}><Select options={Object.values(DOMAIN_PROFILES).map(profile => ({ value: profile.id, label: profile.label }))} /></Form.Item>
        <Form.Item name="objective" label="首轮验证目标" rules={[{ required: true, whitespace: true }]}><Input.TextArea rows={3} /></Form.Item>
        <Form.Item name="required_metrics" label="预期关注指标"><Select mode="tags" tokenSeparators={[",", "，"]} placeholder="未确定可暂不填写" /></Form.Item>
        <Form.Item name="notes" label="已知约束与未知项"><Input.TextArea rows={3} placeholder="每行一项；不要猜测显存、耗时或实验结果" /></Form.Item>
        <Space><Button type="primary" htmlType="submit" loading={creating}>建立课题</Button><Button onClick={() => setOpen(false)} disabled={creating}>取消</Button></Space>
      </Form>
    </Modal>
  </Space>;
}
