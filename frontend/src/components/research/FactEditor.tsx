import { useState } from "react";
import { Alert, Button, Input, InputNumber, Modal, Select, Space, Typography } from "antd";
import type { EvidenceRef, ExperimentSetting, Measurement, MethodCard, NamedValue, NumericValue } from "../../api/project-types";
import { isVersionConflict, reviseProjectFact } from "../../api/projects";

type Fact = MethodCard | ExperimentSetting | Measurement;
const labels: Record<string, string> = {
  name: "名称", task: "任务", summary: "方法说明", inputs: "输入", outputs: "输出", mechanisms: "机制", assumptions: "假设", limitations: "限制",
  dataset: "数据集", dataset_version: "数据版本", subset: "子集", split: "划分", evaluation_protocol: "评估协议", preprocessing: "预处理",
  hyperparameters: "超参数", resources: "资源条件", random_seed: "随机种子", notes: "实验说明",
  metric_name: "指标名称", metric_scope: "指标范围", value: "测量值", direction: "指标方向", aggregation: "汇总方式", uncertainty: "不确定度", sample_size: "样本数量",
};
const listFields = new Set(["inputs", "outputs", "mechanisms", "assumptions", "limitations", "preprocessing", "notes"]);
const methodFields = ["name", "summary", "task", "inputs", "outputs", "mechanisms", "assumptions", "limitations"];
const settingFields = ["name", "dataset", "dataset_version", "subset", "split", "evaluation_protocol", "preprocessing", "hyperparameters", "resources", "random_seed", "notes"];
const measurementFields = ["metric_name", "metric_scope", "value", "direction", "aggregation", "uncertainty", "sample_size"];

export default function FactEditor({ fact, evidence, onSaved }: { fact: Fact; evidence: EvidenceRef[]; onSaved: () => Promise<void> }) {
  const fields = "metric_name" in fact ? measurementFields : "method_id" in fact ? settingFields : methodFields;
  const [open, setOpen] = useState(false), [field, setField] = useState(fields[0]);
  const [value, setValue] = useState<unknown>(null), [actor, setActor] = useState(""), [reason, setReason] = useState("");
  const [ids, setIds] = useState<string[]>([]), [error, setError] = useState(""), [busy, setBusy] = useState(false);
  const [baseVersion, setBaseVersion] = useState(fact.version);
  function selectField(key: string) {
    setField(key);
    const raw = (fact as unknown as Record<string, unknown>)[key];
    const legacy = (key === "summary" || key === "notes") ? localStorage.getItem(`research-atlas:fact-draft:${fact.project_id}:${fact.id}`) : null;
    setValue(legacy ?? (listFields.has(key) ? (raw as string[]).join("\n") : structuredClone(raw)));
    setIds([]);
  }
  async function save() {
    if (busy || !actor.trim() || !reason.trim()) return;
    setBusy(true); setError("");
    const content = listFields.has(field) ? String(value ?? "").split("\n").map(line => line.trim()).filter(Boolean)
      : typeof value === "string" ? value.trim() || null : value;
    try {
      await reviseProjectFact(fact.project_id, fact.id, { expected_version: baseVersion, changes: { [field]: content }, evidence_ids: ids, actor, reason });
      if (field === "summary" || field === "notes") localStorage.removeItem(`research-atlas:fact-draft:${fact.project_id}:${fact.id}`);
      setOpen(false);
      await onSaved();
    } catch (caught) {
      setError(isVersionConflict(caught) ? "服务端内容已变化，修正未覆盖新版本。请保留当前输入，关闭并重新加载事实后再次核对。" : caught instanceof Error ? caught.message : "修订失败，输入已保留");
    } finally { setBusy(false); }
  }
  const named = field === "resources" || field === "hyperparameters";
  const numeric = field === "value" || field === "uncertainty";
  const namedValues = (Array.isArray(value) ? value : []) as NamedValue[];
  const numericValue = value as NumericValue | null;
  function updateNamed(index: number, patch: Partial<NamedValue>) { setValue(namedValues.map((item, n) => n === index ? { ...item, ...patch } : item)); }
  const title = "metric_name" in fact ? fact.metric_name : fact.name;
  return <>
    <Button disabled={fact.status === "withdrawn"} onClick={() => { selectField(fields[0]); setBaseVersion(fact.version); setError(""); setReason(""); setOpen(true); }}>修订内容</Button>
    <Modal title={`修订：${title}`} open={open} confirmLoading={busy} okText="保存新版本" cancelText="关闭" onCancel={() => { if (!busy) setOpen(false); }} onOk={() => void save()}
      okButtonProps={{ disabled: !actor.trim() || !reason.trim() }} maskClosable={false}>
      <Space direction="vertical" style={{ width: "100%" }}>
        <Alert type="info" message="修订保存为人工输入，回到待确认状态；旧版本与快照保留。" />
        {error && <Alert type="error" message={error} />}
        <Select aria-label="修订字段" style={{ width: "100%" }} value={field} onChange={selectField} disabled={busy} options={fields.map(key => ({ value: key, label: labels[key] }))} />
        {named ? <>
          {namedValues.map((item, index) => <Space key={index} direction="vertical" style={{ width: "100%", padding: 8, border: "1px solid #ddd" }}>
            <Input aria-label={`条件名称 ${index + 1}`} placeholder="条件名称" value={item.name} onChange={e => updateNamed(index, { name: e.target.value })} />
            <Input aria-label={`条件值 ${index + 1}`} placeholder="条件值，留空表示未知" value={item.value === null ? "" : String(item.value)} onChange={e => {
              const raw = e.target.value; const number = Number(raw);
              updateNamed(index, { value: raw.trim() === "" ? null : raw === "true" ? true : raw === "false" ? false : Number.isFinite(number) ? number : raw, finding_status: raw.trim() ? "reported" : "unknown" });
            }} />
            <Input aria-label={`条件单位 ${index + 1}`} placeholder="单位（可选）" value={item.unit ?? ""} onChange={e => updateNamed(index, { unit: e.target.value || null })} />
            <Button onClick={() => setValue(namedValues.filter((_, n) => n !== index))}>删除此项</Button>
          </Space>)}
          <Button onClick={() => setValue([...namedValues, { name: "", value: null, unit: null, finding_status: "unknown" }])}>添加条件</Button>
        </> : numeric ? <>
          <InputNumber aria-label="修订数值" style={{ width: "100%" }} value={numericValue?.value ?? null} placeholder="留空表示未知" onChange={number => setValue(number === null ? null : { value: number, unit: numericValue?.unit ?? null, scale: numericValue?.scale ?? "raw", lower: numericValue?.lower ?? null, upper: numericValue?.upper ?? null })} />
          {numericValue && <>
            <Input aria-label="数值单位" placeholder="单位" value={numericValue.unit ?? ""} onChange={e => setValue({ ...numericValue, unit: e.target.value || null })} />
            <Select aria-label="数值尺度" value={numericValue.scale} onChange={scale => setValue({ ...numericValue, scale })} options={[{ value: "raw", label: "原始值" }, { value: "fraction", label: "比例" }, { value: "percent", label: "百分数" }]} />
            <InputNumber aria-label="数值下界" placeholder="下界（可选）" value={numericValue.lower} onChange={lower => setValue({ ...numericValue, lower })} />
            <InputNumber aria-label="数值上界" placeholder="上界（可选）" value={numericValue.upper} onChange={upper => setValue({ ...numericValue, upper })} />
          </>}
        </> : field === "sample_size" ? <InputNumber aria-label="修订内容" min={1} precision={0} value={value as number | null} onChange={setValue} />
          : field === "direction" ? <Select aria-label="指标方向" value={value as string} onChange={setValue} options={[{ value: "higher_is_better", label: "越高越好" }, { value: "lower_is_better", label: "越低越好" }, { value: "target_is_better", label: "越接近目标越好" }, { value: "unspecified", label: "未指定" }]} />
          : <Input.TextArea aria-label="修订内容" rows={4} maxLength={8000} value={String(value ?? "")} onChange={e => setValue(e.target.value)} placeholder={listFields.has(field) ? "每行一项；留空表示未知" : "填写核对后的内容；可选字段留空表示未知"} />}
        <Select aria-label="修订依据" mode="multiple" style={{ width: "100%" }} placeholder="选择已核对的原文依据（可选）" value={ids} onChange={setIds} options={evidence.map(item => ({ value: item.id, label: item.quote?.slice(0, 100) || item.id }))} />
        <Typography.Text type="secondary">关联引文仍需人工核对其含义；未绑定证据的修订不会成为已核验的文献结论。</Typography.Text>
        <Input aria-label="修订人" placeholder="修订人" value={actor} onChange={e => setActor(e.target.value)} maxLength={200} />
        <Input.TextArea aria-label="修订理由" placeholder="修订理由" value={reason} onChange={e => setReason(e.target.value)} maxLength={4000} />
      </Space>
    </Modal>
  </>;
}
