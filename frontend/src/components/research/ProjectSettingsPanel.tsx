import { useEffect, useRef, useState } from "react";
import { Alert, Button, Card, Form, Input, Select, Space, message } from "antd";
import type { ResearchProject, ResearchProjectPatch } from "../../api/project-types";
import { isVersionConflict, updateProject } from "../../api/projects";

type FormValues = {
  title: string;
  research_question: string;
  objective: string;
  allowed_datasets: string[];
  excluded_datasets: string[];
  required_metrics: string[];
  data_access: string[];
  notes: string;
};

const split = (value: string) => value.split(/[,，\n]/).map(item => item.trim()).filter(Boolean);

export default function ProjectSettingsPanel({
  project,
  onSaved,
}: {
  project: ResearchProject;
  onSaved: (project: ResearchProject) => void;
}) {
  const [form] = Form.useForm<FormValues>();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [conflict, setConflict] = useState(false);
  const submitting = useRef(false);

  useEffect(() => {
    if (form.isFieldsTouched()) return;
    form.setFieldsValue({
      title: project.title,
      research_question: project.research_question,
      objective: project.constraints.objective,
      allowed_datasets: project.constraints.allowed_datasets,
      excluded_datasets: project.constraints.excluded_datasets,
      required_metrics: project.constraints.required_metrics,
      data_access: project.constraints.data_access,
      notes: project.constraints.notes.join("\n"),
    });
  }, [form, project]);

  const save = async (values: FormValues) => {
    if (submitting.current) return;
    submitting.current = true;
    setSaving(true);
    setError("");
    setConflict(false);
    const body: ResearchProjectPatch = {
      expected_version: project.version,
      title: values.title,
      research_question: values.research_question,
      status: null,
      constraints: {
        ...project.constraints,
        version: project.constraints.version + 1,
        objective: values.objective,
        allowed_datasets: values.allowed_datasets ?? [],
        excluded_datasets: values.excluded_datasets ?? [],
        required_metrics: values.required_metrics ?? [],
        data_access: values.data_access ?? [],
        notes: split(values.notes ?? ""),
      },
    };
    try {
      const saved = await updateProject(project.id, body);
      onSaved(saved);
      form.resetFields();
      message.success("课题设置已保存并创建新版本");
    } catch (caught) {
      if (isVersionConflict(caught)) setConflict(true);
      setError(caught instanceof Error ? caught.message : "保存失败");
    } finally {
      submitting.current = false;
      setSaving(false);
    }
  };

  return <Card title="课题设置与约束">
    {conflict && <Alert style={{ marginBottom: 16 }} type="warning" showIcon message="服务端已有新版本" description="本地表单仍然保留。请在另一窗口核对新版本后，再决定如何合并；系统不会静默覆盖。" />}
    {error && <Alert style={{ marginBottom: 16 }} type="error" showIcon message="保存失败" description={error} />}
    <Form form={form} layout="vertical" onFinish={save}>
      <Form.Item name="title" label="课题名称" rules={[{ required: true, whitespace: true }]}><Input maxLength={300} /></Form.Item>
      <Form.Item name="research_question" label="研究问题" rules={[{ required: true, whitespace: true }]}><Input.TextArea rows={3} maxLength={4000} /></Form.Item>
      <Form.Item name="objective" label="首轮验证目标" rules={[{ required: true, whitespace: true }]}><Input.TextArea rows={3} /></Form.Item>
      <Form.Item name="allowed_datasets" label="允许的数据集"><Select mode="tags" tokenSeparators={[",", "，"]} placeholder="未填写表示未知，不代表无限制" /></Form.Item>
      <Form.Item name="excluded_datasets" label="排除的数据集"><Select mode="tags" tokenSeparators={[",", "，"]} placeholder="未填写" /></Form.Item>
      <Form.Item name="required_metrics" label="必须测量的指标"><Select mode="tags" tokenSeparators={[",", "，"]} placeholder="未填写表示尚未确定" /></Form.Item>
      <Form.Item name="data_access" label="数据访问条件"><Select mode="tags" tokenSeparators={[",", "，"]} placeholder="例如：仅公开数据" /></Form.Item>
      <Form.Item name="notes" label="其他约束与未知项"><Input.TextArea rows={4} placeholder="每行一项；无法确认的条件请明确写为未知" /></Form.Item>
      <Space><Button type="primary" htmlType="submit" loading={saving}>保存新版本</Button><Button onClick={() => form.resetFields()} disabled={saving}>撤销本地修改</Button></Space>
    </Form>
  </Card>;
}
