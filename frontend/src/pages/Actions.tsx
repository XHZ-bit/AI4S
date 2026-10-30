import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Alert, Button, Card, Input, InputNumber, Pagination, Select, Space, Tag, Typography } from "antd";
import { apiGet, apiPost } from "../api/client";

export default function Actions() {
  const [params, setParams] = useSearchParams();
  const id = params.get("id");
  const version = params.get("version");
  const [papers, setPapers] = useState<any[]>([]);
  const [selected, setSelected] = useState<string[]>(params.get("paper") ? [params.get("paper")!] : []);
  const [hours, setHours] = useState(10);
  const [title, setTitle] = useState("我的自动行动清单");
  const [goal, setGoal] = useState(params.get("goal") || "");
  const [targets, setTargets] = useState<any[]>([]);
  const [target, setTarget] = useState<string | undefined>(params.get("target") || undefined);
  const [lists, setLists] = useState<any[]>([]);
  const [listPage, setListPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [current, setCurrent] = useState<any>();
  const [preview, setPreview] = useState<any>();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const generation = useRef(0);
  const pendingAction = useRef<AbortController>();
  const invalidatePreview = () => {
    generation.current++;
    pendingAction.current?.abort();
    pendingAction.current = undefined;
    setPreview(undefined);
    setBusy(false);
  };
  const inputs = { paper_uids: selected, weekly_hours: hours,
    profile: target ? { goal: goal.trim(), target_uid: target, weekly_hours: hours, known_concepts: [] } : null };
  const loadPapers = (q = "") => apiGet<any>("/api/papers", { q, limit: 100 }).then(result => setPapers(result.items)).catch(caught => setError(String(caught)));
  useEffect(() => { void loadPapers(); void apiGet<any>("/api/roadmap/auto-targets").then(result => setTargets(result.items)).catch(caught => setError(`候选目标加载失败：${caught}`)); }, []);
  useEffect(() => {
    const controller = new AbortController();
    apiGet<any>("/api/actions/v1", { offset: (listPage-1)*20, limit:20 }, controller.signal).then(result => { setLists(result.items); setTotal(result.total); }).catch(caught => { if (!controller.signal.aborted) setError(String(caught)); });
    return () => controller.abort();
  }, [refresh, listPage]);
  useEffect(() => {
    invalidatePreview();
    setCurrent(undefined);
    setError("");
    const controller = new AbortController();
    if (id) apiGet<any>(`/api/actions/v1/${id}`, { version: version || undefined }, controller.signal).then(result => {
      if (!controller.signal.aborted) { setCurrent(result); setError(""); }
    }).catch(caught => { if (!controller.signal.aborted) setError(String(caught)); });
    return () => { controller.abort(); pendingAction.current?.abort(); };
  }, [id, version, refresh]);
  async function run(path: string, body: any, saving = false) {
    if (pendingAction.current) return;
    const controller = new AbortController();
    pendingAction.current = controller;
    const requestGeneration = generation.current;
    setBusy(true); setError("");
    try {
      const result = await apiPost<any>(path, body, controller.signal);
      if (controller.signal.aborted || requestGeneration !== generation.current) return;
      if (saving) { setParams({ id: result.id }); setPreview(undefined); setRefresh(value => value+1); }
      else setPreview(result);
    } catch (caught) {
      if (!controller.signal.aborted && requestGeneration === generation.current) setError(String(caught));
    } finally {
      if (pendingAction.current === controller) { pendingAction.current = undefined; setBusy(false); }
    }
  }
  const shown = preview || current;
  return <Space direction="vertical" size="large" style={{ width: "100%" }}>
    <Typography.Title level={2}>自动行动清单</Typography.Title>
    <p className="atlas-page-lead">选择资料和每周时间，生成可预览、可保存的行动清单。</p>
    {error && <Alert type="error" message={error} action={<Button onClick={() => setRefresh(value => value+1)}>重新加载</Button>} />}
    <Card title="已保存清单"><Space wrap>{lists.map(list => <Button key={list.id} onClick={() => setParams({ id: list.id })}>{list.title} · v{list.version}</Button>)}<Button onClick={() => { setParams({}); setPreview(undefined); }}>新建清单</Button></Space>
      {total > 20 && <Pagination current={listPage} total={total} pageSize={20} onChange={setListPage} />}
    </Card>
    {id && !current && !error && <p aria-live="polite">正在加载行动清单…</p>}
    {!id && <Card title="选择资料与时间预算"><Space direction="vertical" style={{ width:"100%" }}>
      <Input aria-label="行动清单名称" value={title} onChange={event => setTitle(event.target.value)} />
      <Select aria-label="行动清单论文" mode="multiple" showSearch filterOption={false} style={{width:"100%"}} placeholder="选择或搜索自己的论文" value={selected} onSearch={q => void loadPapers(q)} onChange={value => { setSelected(value); invalidatePreview(); }} options={papers.map(paper => ({value:paper.uid,label:paper.title}))} />
      <Select aria-label="可选机器路线目标" allowClear style={{width:"100%"}} placeholder="可选：使用机器核查候选目标" value={target} onChange={value => { setTarget(value); invalidatePreview(); }} options={targets.map(item => ({value:item.uid,label:item.name}))} />
      {target && <Input aria-label="自动行动学习目标" value={goal} onChange={event => { setGoal(event.target.value); invalidatePreview(); }} placeholder="描述学习目标" />}
      <Space>每周 <InputNumber aria-label="行动清单每周小时" min={1} max={80} value={hours} onChange={value => { setHours(value || 10); invalidatePreview(); }} /> 小时
        <Button loading={busy} disabled={!selected.length && !target || !!target && !goal.trim()} onClick={() => void run("/api/actions/v1/preview",inputs)}>预览自动行动清单</Button>
        {preview && <Button type="primary" loading={busy} disabled={!title.trim()} onClick={() => void run("/api/actions/v1", { ...inputs, title:title.trim(), input_fingerprint:preview.input_fingerprint },true)}>保存自动行动清单</Button>}
      </Space><Link to="/manage">先导入论文 →</Link>
    </Space></Card>}
    {current && <Card title={`${current.title} · v${current.version}`}><Space wrap>
      <Tag color={current.needs_review ? "orange" : "blue"}>{current.needs_review ? "来源变化，待复核" : "机器行动清单"}</Tag>
      {current.needs_adjustment && !current.needs_review && <Tag>执行记录变化，可预览调整</Tag>}
      <Select aria-label="行动清单历史版本" value={current.version} onChange={value => setParams({id:id!,version:String(value)})} options={current.versions.map((value:number) => ({value,label:`版本 ${value}`}))} />
      <Button loading={busy} onClick={() => void run(`/api/actions/v1/${id}/replan-preview`, {expected_version:current.version})}>预览清单调整</Button>
      {preview && <Button type="primary" loading={busy} onClick={() => void run(`/api/actions/v1/${id}/replan`,{expected_version:current.version,input_fingerprint:preview.input_fingerprint},true)}>确认保存清单新版本</Button>}
    </Space></Card>}
    {shown && <Card title={preview ? "待保存预览" : "执行活动"}>
      <p>估算 {shown.estimated_minutes} 分钟；未排期 {shown.unscheduled_count} 项。{shown.notice}</p>
      {preview?.diff && <p>新增 {preview.diff.added.length} 项 · 移除 {preview.diff.removed.length} 项 · 沿用 {preview.diff.retained.length} 项</p>}
      {shown.items.map((item:any) => <div key={item.id} className="atlas-list-row"><Space wrap>
        <Link to={item.url}>{item.title}</Link><Tag>{({pending:"待执行",in_progress:"进行中",completed:"已记录",needs_review:"待复核"} as Record<string,string>)[item.status]}</Tag>
        <Tag>{item.week ? `第 ${item.week} 周 · 估算 ${item.estimated_minutes} 分钟` : "未排期"}</Tag>
      </Space><p>{item.duration_basis}</p></div>)}
    </Card>}
  </Space>;
}
