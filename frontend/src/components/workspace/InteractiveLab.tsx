import { useEffect, useState } from "react";
import { Alert, Button, Card, InputNumber, Radio, Slider, Space, Tabs, Tag } from "antd";
import { getCaseSession } from "../../api/cases";
import type { CaseSession } from "../../api/cases";
import { apiPost } from "../../api/client";
import { getInsights, type Exercise, type Report } from "../../api/assistant";
import { useInspector } from "./InspectorContext";
import { useSearchParams } from "react-router-dom";

function useStored<T>(key: string, initial: T) {
  const [value, setValue] = useState<T>(() => { try { return JSON.parse(localStorage.getItem(key) || "null") ?? initial; } catch { return initial; } });
  useEffect(() => { try { localStorage.setItem(key, JSON.stringify(value)); } catch {} }, [key, value]);
  return [value, setValue] as const;
}

export function WindowAnimation() {
  const [to, setTo] = useStored("atlas:lab:windowTo",3), [ta, setTa] = useStored("atlas:lab:windowTa",4), [position, setPosition] = useStored("atlas:lab:windowPosition",0), [playing, setPlaying] = useState(false);
  const inspector = useInspector(); const length = 8 + to + ta - 1;
  useEffect(() => {
    if (!playing) return;
    const timer = window.setInterval(() => setPosition(p => (p + 1) % 8), 800);
    return () => window.clearInterval(timer);
  }, [playing]);
  useEffect(() => {
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) setPlaying(false);
  }, []);
  return <div className="atlas-window-animation">
    <Space wrap><label>观测 To <InputNumber aria-label="动画观测步数" min={1} max={6} value={to} onChange={v => setTo(v || 1)} /></label><label>动作 Ta <InputNumber aria-label="动画动作步数" min={1} max={6} value={ta} onChange={v => setTa(v || 1)} /></label></Space>
    <div className="atlas-time-window" aria-label="观测与动作时间轴"><span>过去观测</span><div style={{gridTemplateColumns:`repeat(${length},minmax(0,1fr))`}}>{Array.from({ length }, (_, i) => <span key={i} className={i >= position && i < position + to ? "window-observation" : "window-empty"}>{i - position - to + 1}</span>)}</div><span>预测动作</span><div style={{gridTemplateColumns:`repeat(${length},minmax(0,1fr))`}}>{Array.from({ length }, (_, i) => <span key={i} className={i >= position + to - 1 && i < position + to + ta - 1 ? "window-action" : "window-empty"}>{i - position - to + 1}</span>)}</div></div>
    <Space wrap><Button onClick={() => setPlaying(p => !p)}>{playing ? "暂停动画" : "播放动画"}</Button><Button onClick={() => { setPlaying(false); setPosition(p => (p + 1) % 8); }}>单步</Button><Button onClick={() => { setPlaying(false); setPosition(0); }}>重置</Button><Button onClick={()=>inspector.inspect({kind:"source",id:"diffusion_policy/policy/base_lowdim_policy.py",line:16})}>对照窗口源码</Button><Tag>源码示意：To=3 · Ta=4 · T=6</Tag></Space>
    <p className="atlas-muted">当前步为观测末端与动作起点。窗口长度表示不同含义，示意不运行策略、不代表实验效果。</p>
  </div>;
}

export function TensorAnimation() {
  const [p, setP] = useStored("atlas:lab:tensor", { B: 2, To: 3, Do: 20, Ta: 4, Da: 2 });
  return <div>
    <div className="atlas-parameter-grid">{Object.entries(p).map(([key, value]) => <label key={key}>{key}<Slider aria-label={`张量参数 ${key}`} min={1} max={key === "Do" ? 32 : key === "B" ? 8 : 12} value={value} onChange={v => setP(old => ({ ...old, [key]: v }))} /><InputNumber aria-label={`设置 ${key}`} min={1} max={64} value={value} onChange={v => setP(old => ({ ...old, [key]: v || 1 }))} /></label>)}</div>
    <div className="atlas-tensor-flow"><Tensor title="观测输入" shape={[p.B, p.To, p.Do]} labels={["批次 B", "观测步 To", "维度 Do"]} /><span className="atlas-flow-arrow">→<small>predict_action</small></span><Tensor title="动作输出" shape={[p.B, p.Ta, p.Da]} labels={["批次 B", "动作步 Ta", "维度 Da"]} /></div>
    <p className="atlas-muted">参数是教学假设。固定 pusht_lowdim 配置为 Do=20、Da=2；本图仅演示接口形状。</p>
  </div>;
}

function Tensor({ title, shape, labels }: { title: string; shape: number[]; labels: string[] }) {
  return <div className="atlas-tensor"><span className="atlas-eyebrow">{title}</span><div className="atlas-tensor-visual" aria-hidden="true">{Array.from({ length: Math.min(shape[0], 4) }, (_, i) => <div className="atlas-tensor-layer" key={i} style={{ transform: `translate(${i * 7}px, ${-i * 5}px)`, gridTemplateColumns: `repeat(${Math.min(shape[2], 10)}, 1fr)` }}>{Array.from({ length: Math.min(shape[1], 6) * Math.min(shape[2], 10) }, (_, j) => <i key={j} />)}</div>)}</div><strong aria-live="polite">[{shape.join(", ")}]</strong><div className="atlas-tensor-labels">{labels.map((label, i) => <span key={label}>{label}<b>{shape[i]}</b></span>)}</div></div>;
}

function Practice({ exercise, caseId, session, onSaved }: { exercise: Exercise; caseId: string; session: CaseSession; onSaved: (session: CaseSession) => void }) {
  const [shape, setShape] = useStored<(number | null)[]>(`atlas:practice:${session.id}:${exercise.id}:shape`, Array.isArray(exercise.result?.answer) ? exercise.result.answer : [null, null, null]); const [choice, setChoice] = useStored<number | undefined>(`atlas:practice:${session.id}:${exercise.id}:choice`, typeof exercise.result?.answer === "number" ? exercise.result.answer : undefined);
  const [busy, setBusy] = useState(false), [error, setError] = useState(""); const inspector = useInspector();
  const submit = async () => {
    if (busy) return;
    setBusy(true); setError("");
    try {
      const saved = await apiPost<CaseSession>(`/api/cases/${caseId}/sessions/${session.id}/practice/${exercise.id}/answers`, { version: session.version, ...(exercise.kind === "shape" ? { shape } : { choice }) });
      onSaved(saved);
    } catch (e) { setError(String(e)); } finally { setBusy(false); }
  };
  return <Card size="small" title={exercise.prompt} className="atlas-practice"><Space wrap>{Object.entries(exercise.parameters).map(([key, value]) => <Tag key={key}>{key} = {value}</Tag>)}</Space><div style={{ margin: "12px 0" }}>{exercise.kind === "shape" ? <Space><span>[</span>{shape.map((value, i) => <InputNumber key={i} aria-label={`${exercise.id} 第${i + 1}维`} min={1} max={64} value={value} onChange={v => setShape(old => old.map((x, j) => j === i ? v : x))} />)}<span>]</span></Space> : <Radio.Group value={choice} onChange={e => setChoice(e.target.value)}>{exercise.options.map((text, i) => <Radio key={i} value={i}>{text}</Radio>)}</Radio.Group>}</div><Space wrap><Button type="primary" loading={busy} disabled={session.stale || (exercise.kind === "shape" ? shape.some(x => x === null) : choice === undefined)} onClick={() => void submit()}>提交练习</Button><Button onClick={() => inspector.inspect(exercise.references[0])}>查看接口源码</Button></Space>{error && <Alert type="error" message={error} description="作答保留；请重新加载记录后提交。" action={<Button size="small" onClick={async()=>{try{onSaved(await getCaseSession(caseId,session.id));setError("");inspector.refresh();}catch(e){setError(String(e));}}}>重新加载练习记录</Button>} />}{exercise.result && <Alert style={{ marginTop: 12 }} type={exercise.result.correct ? "success" : "warning"} message={exercise.result.correct ? "本题答对 · 建议已更新" : "再观察一次维度顺序"} description={exercise.result.explanation} />}</Card>;
}

export default function InteractiveLab({ caseId, session, onSaved }: { caseId: string; session?: CaseSession; onSaved: (session: CaseSession) => void }) {
  const [params, setParams] = useSearchParams();
  const [report, setReport] = useState<Report>(); const [error, setError] = useState("");
  useEffect(() => {
    if (!session) return;
    const c = new AbortController();
    getInsights("case", caseId, session.id, c.signal).then(value => { if (!c.signal.aborted) { setReport(value); setError(""); } }).catch(e => { if (!c.signal.aborted) setError(String(e)); });
    return () => c.abort();
  }, [caseId, session?.id, session?.version]);
  return <Card id="atlas-interactive-lab" className="atlas-lab" title={<Space wrap><span>交互实验室</span><Tag color="cyan">图解 · 源码 · 自动练习</Tag></Space>}><Tabs activeKey={["tensor","windows","practice"].includes(params.get("lab")||"")?params.get("lab")!:"tensor"} onChange={lab=>setParams(old=>{const n=new URLSearchParams(old);n.set("lab",lab);return n;})} items={[{ key: "tensor", label: "张量形状", children: <TensorAnimation /> }, { key: "windows", label: "时间窗口", children: <WindowAnimation /> }, { key: "practice", label: "动手练习", children: <Space direction="vertical" style={{ width: "100%" }}>{!session && <Alert type="info" message="开始学习并保存进度后，可以提交自动练习" />}{error && <Alert type="error" message={error} />}{report?.exercises?.map(e => <Practice key={`${session!.id}:${e.id}`} exercise={e} caseId={caseId} session={session!} onSaved={onSaved} />)}</Space> }]} /></Card>;
}
