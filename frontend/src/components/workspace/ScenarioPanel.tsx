import { useEffect, useState } from "react";
import { Alert, Button, Empty, Input, InputNumber, Progress, Select, Slider, Space, Tag } from "antd";
import type { ProjectConstraints, ResearchProject } from "../../api/project-types";
import { evaluateScenarios, getInsights, statusLabels, type Scenario, type ScenarioResult } from "../../api/assistant";
import { RecordStatusTag } from "../research/StatusLabels";
import type { RecordStatus } from "../../api/project-types";
import { useInspector } from "./InspectorContext";

const numeric = (value: number, unit: string) => ({ value, unit, scale: "raw" as const, lower: null, upper: null });
const memoryGB=(memory:ProjectConstraints["compute"][number]["memory"])=>{if(!memory)return null;const units:Record<string,number>={gb:1,mb:.001,tb:1000,gib:2**30/1e9,mib:2**20/1e9,tib:2**40/1e9};const factor=units[(memory.unit||"").toLowerCase()];return factor===undefined?null:Math.round(memory.value*factor*1000)/1000;};
const copy = <T,>(value: T): T => JSON.parse(JSON.stringify(value));
function CommaList({ values, label, onChange }: { values: string[]; label: string; onChange: (value: string[]) => void }) {
  const [text, setText] = useState(values.join(", "));
  return <Input aria-label={label} value={text} onChange={e => { setText(e.target.value); onChange(e.target.value.split(/[,，]/).map(v => v.trim()).filter(Boolean)); }} />;
}
export default function ScenarioPanel({ project }: { project: ResearchProject }) {
  const key = `atlas:scenarios:${project.id}`;
  const [scenarios, setScenarios] = useState<Scenario[]>(() => { try { const s = JSON.parse(localStorage.getItem(key) || "null"); if (s && Array.isArray(s.items) && s.items.length <= 4 && s.items.length) return s.items; } catch {} return [{ id: "scenario-1", label: "情景 1", constraints: copy(project.constraints) }]; });
  const [rebased] = useState(()=>{try{const saved=JSON.parse(localStorage.getItem(key)||"null");return saved&&saved.version!==project.version;}catch{return false;}});
  const [fingerprint, setFingerprint] = useState(""), [result, setResult] = useState<ScenarioResult>();
  const [pending, setPending] = useState(true), [error, setError] = useState(""), [revision, setRevision] = useState(0);
  const inspector = useInspector();
  useEffect(() => {
    const c = new AbortController(); setError("");
    getInsights("project", project.id, null, c.signal).then(r => { if (!c.signal.aborted) setFingerprint(r.input_fingerprint); }).catch(e => { if (!c.signal.aborted) { setError(String(e)); setPending(false); } });
    return () => c.abort();
  }, [project.id, project.version, revision]);
  useEffect(() => {
    try { localStorage.setItem(key, JSON.stringify({ version: project.version, items: scenarios })); } catch {}
    if (!fingerprint) return;
    const c = new AbortController(); setPending(true); setError("");
    const timer = window.setTimeout(() => {
      evaluateScenarios(project.id, project.version, fingerprint, scenarios, c.signal).then(r => { if (!c.signal.aborted) setResult(r); }).catch(e => { if (!c.signal.aborted) setError(String(e)); }).finally(() => { if (!c.signal.aborted) setPending(false); });
    }, 250);
    return () => { clearTimeout(timer); c.abort(); };
  }, [project.id, project.version, scenarios, fingerprint, revision, key]);
  const update = (index: number, patch: Partial<ProjectConstraints>) => setScenarios(old => old.map((s, i) => i === index ? { ...s, constraints: { ...s.constraints, ...patch } } : s));
  const device = (i: number, patch: object) => update(i, { compute: [{ ...(scenarios[i].constraints.compute[0] || { device_kind: null, device_model: null, device_count: null, memory: null, availability: null }), ...patch }, ...scenarios[i].constraints.compute.slice(1)] });
  const columns = result?.scenarios || [];
  return <div>
    <Space wrap><Tag color="cyan">情景预览 · 正式决策保持原值</Tag><Tag aria-live="polite">{pending ? "条件已更新 · 结果待更新" : error ? "计算未完成" : "已按最新条件计算"}</Tag><Button disabled={scenarios.length >= 4} onClick={() => setScenarios(old => [...old, { id: crypto.randomUUID(), label: `情景 ${old.length + 1}`, constraints: copy(old[old.length - 1].constraints) }])}>添加对照情景 ({scenarios.length}/4)</Button></Space>
    <p className="atlas-muted">拖动后 250ms 计算。候选资料可直接参与分析；“匹配”仅表示已报告条件满足当前上限。</p>
    {rebased && <Alert type="info" message="课题基准已更新，本地情景输入已保留；以下结果使用当前资料重新计算。" />}
    {error && <Alert type="warning" message={error} description="已保留输入与上次结果。版本发生变化时，刷新课题版本后继续。" action={<Button onClick={() => setRevision(v => v + 1)}>刷新分析输入</Button>} />}
    <div className="atlas-scenario-grid">{scenarios.map((s, i) => <section className="atlas-scenario" key={s.id}>
      <header><Input aria-label={`情景 ${i + 1} 名称`} maxLength={100} value={s.label} onChange={e => setScenarios(old => old.map((v, j) => j === i ? { ...v, label: e.target.value || `情景 ${i + 1}` } : v))} /><Button size="small" aria-label={`移除情景 ${i + 1}`} disabled={scenarios.length === 1} onClick={() => setScenarios(old => old.filter((_, j) => j !== i))}>×</Button></header>
      <label>显存上限 GB {s.constraints.compute[0]?.memory?.unit && !["GB", "gb"].includes(s.constraints.compute[0].memory.unit) && <small>（原值 {s.constraints.compute[0].memory.value} {s.constraints.compute[0].memory.unit}；修改后使用 GB）</small>}<div className="atlas-budget-input"><Slider aria-label={`情景 ${i + 1} 显存`} min={1} max={128} value={memoryGB(s.constraints.compute[0]?.memory) ?? 1} onChange={v => device(i, { memory: numeric(v, "GB") })} /><InputNumber aria-label={`情景 ${i + 1} 显存数值`} min={0} max={4096} value={memoryGB(s.constraints.compute[0]?.memory)} placeholder="未设置" onChange={v => device(i, { memory: v === null ? null : numeric(v, "GB") })} /></div></label>
      <label>设备数量<div className="atlas-budget-input"><Slider aria-label={`情景 ${i + 1} 设备数量`} min={1} max={16} value={s.constraints.compute[0]?.device_count || 1} onChange={v => device(i, { device_count: v })} /><InputNumber aria-label={`情景 ${i + 1} 设备数量数值`} min={1} max={1024} value={s.constraints.compute[0]?.device_count} placeholder="未设置" onChange={v => device(i, { device_count: v })} /></div></label>
      <label>设备类型<Input aria-label={`情景 ${i + 1} 设备类型`} value={s.constraints.compute[0]?.device_kind || ""} placeholder="如 GPU；空白表示不限" onChange={e => device(i, { device_kind: e.target.value || null })} /></label>
      <label>时间预算<Slider aria-label={`情景 ${i + 1} 时间预算滑块`} min={0} max={Math.max(240,s.constraints.time_budget?.value || 0)} value={s.constraints.time_budget?.value ?? 0} onChange={v=>update(i,{time_budget:numeric(v,s.constraints.time_budget?.unit || "h")})} /><div className="atlas-budget-input"><InputNumber aria-label={`情景 ${i + 1} 时间预算`} min={0} value={s.constraints.time_budget?.value} placeholder="未设置" onChange={v => update(i, { time_budget: v === null ? null : numeric(v, s.constraints.time_budget?.unit || "h") })} /><Select aria-label={`情景 ${i + 1} 时间单位`} value={s.constraints.time_budget?.unit || "h"} options={["s", "min", "h", "day"].map(value => ({ value, label: value }))} onChange={v => { if (s.constraints.time_budget) update(i, { time_budget: { ...s.constraints.time_budget, unit: v } }); }} /></div></label>
      <label>费用预算<Slider aria-label={`情景 ${i + 1} 费用预算滑块`} min={0} max={Math.max(1000,s.constraints.cost_budget?.value || 0)} value={s.constraints.cost_budget?.value ?? 0} onChange={v=>update(i,{cost_budget:numeric(v,s.constraints.cost_budget?.unit || "USD")})} /><div className="atlas-budget-input"><InputNumber aria-label={`情景 ${i + 1} 费用预算`} min={0} value={s.constraints.cost_budget?.value} placeholder="未设置" onChange={v => update(i, { cost_budget: v === null ? null : numeric(v, s.constraints.cost_budget?.unit || "USD") })} /><Select aria-label={`情景 ${i + 1} 费用单位`} value={s.constraints.cost_budget?.unit || "USD"} options={["USD", "CNY", "EUR"].map(value => ({ value, label: value }))} onChange={v => { if (s.constraints.cost_budget) update(i, { cost_budget: { ...s.constraints.cost_budget, unit: v } }); }} /></div></label>
      <label>允许的数据集（逗号分隔）<CommaList label={`情景 ${i + 1} 数据范围`} values={s.constraints.allowed_datasets} onChange={v=>update(i,{allowed_datasets:v})} /></label>
      <label>必需指标（逗号分隔）<CommaList label={`情景 ${i + 1} 必需指标`} values={s.constraints.required_metrics} onChange={v=>update(i,{required_metrics:v})} /></label>
      <p className="atlas-muted">排除数据集：{s.constraints.excluded_datasets.join("、") || "无"}；{s.constraints.compute.length > 1 ? "其余可用设备配置沿用课题值" : "设备需求不完整时保持未知"}</p>
    </section>)}</div>
    {result && <><h3>候选路线与约束矩阵</h3><div className="atlas-constraint-matrix" aria-busy={pending}><table><thead><tr><th>候选 / 基准</th>{columns.map(s => <th key={s.id}>{s.label}<small style={{ display: "block" }}>{s.changes.length} 项条件变化</small></th>)}</tr></thead><tbody>{result.baseline.map(candidate => <tr key={candidate.id}><th>{candidate.label}{candidate.setting_status && <p>资料状态 <RecordStatusTag status={candidate.setting_status as RecordStatus} /></p>}<p><Tag>{statusLabels[candidate.status]}</Tag></p></th>{columns.map(s => { const next = s.candidates.find(c => c.id === candidate.id); return <td key={s.id}><Tag color={next?.status === "match" ? "cyan" : next?.status === "conflict" ? "red" : "gold"}>{next ? statusLabels[next.status] : "信息不足"}</Tag>{next?.checks.filter(c => c.status !== "not_applicable").map(c => <button key={c.dimension} onClick={() => inspector.inspect(c.references[0] || { kind: "fact", id: candidate.id })}><strong className={`atlas-check-${c.status}`}>{c.dimension} · {statusLabels[c.status]}</strong><small>{c.actual ?? "未知"}{c.limit !== null && ` / 上限 ${c.limit}`}</small><small>{c.reason}</small>{c.utilization!=null&&<Progress status={c.status==="conflict"?"exception":"normal"} percent={Math.min(100,c.utilization*100)} size="small" strokeColor={c.status==="conflict"?"#bc4646":"#087f8c"} format={()=>`${Math.round(c.utilization!*100)}%`} />}</button>)}</td>; })}</tr>)}</tbody></table></div>{!result.baseline.length && <Empty description="关联资料并添加实验设置后，候选将在这里出现" />}</>}
  </div>;
}
