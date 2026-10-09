import { useEffect, useState } from "react";
import { Alert, Button, Card, Input, InputNumber, Select, Space, Tag, Typography } from "antd";
import { Link } from "react-router-dom";
import { apiGet, apiPost } from "../api/client";
import type { RoadmapResult } from "../api/roadmap";

type Target = { uid: string; name: string; type: string };
type Preview = { evidence_level: "machine_checked_preview"; route: RoadmapResult;
  schedule: { estimated_minutes: number; unscheduled_count: number }; checked_relations: number; notice: string };

export default function AutomaticRoadmapPreview() {
  const [targets, setTargets] = useState<Target[]>([]);
  const [target, setTarget] = useState<string>();
  const [goal, setGoal] = useState("");
  const [weeklyHours, setWeeklyHours] = useState(10);
  const [known, setKnown] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const search = async (q: string) => {
    try { setTargets((await apiGet<{ items: Target[] }>("/api/roadmap/auto-targets", { q })).items); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "候选目标读取失败"); }
  };
  useEffect(() => { void search(""); }, []);
  const run = async () => {
    if (!target || !goal.trim()) return;
    setBusy(true); setError(""); setPreview(null);
    try {
      const result = await apiPost<Preview>("/api/roadmap/auto-preview", { profile: {
        goal: goal.trim(), target_uid: target,
        known_concepts: known.split(/[,，]/).map(value => value.trim()).filter(Boolean),
        weekly_hours: weeklyHours,
      } });
      setPreview(result);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "候选路线无法生成"); }
    finally { setBusy(false); }
  };
  return <Card title="机器核查候选路线" extra={<Tag color="blue">只读预览</Tag>}>
    <Space direction="vertical" style={{ width: "100%" }}>
      <Typography.Text type="secondary">使用自动检查过的来源关系提出学习顺序假设。不会保存为正式路线，也不宣称已掌握或教学有效。</Typography.Text>
      <Input aria-label="候选路线目标描述" placeholder="学习目标描述" value={goal} onChange={event => setGoal(event.target.value)} />
      <Select aria-label="机器核查目标实体" showSearch filterOption={false} placeholder="搜索机器核查候选目标" value={target} onSearch={q => void search(q)} onChange={value => { setTarget(value); setPreview(null); }} options={targets.map(item => ({ value: item.uid, label: `${item.name} · ${item.type}` }))} />
      <Input aria-label="候选路线已学内容" placeholder="已学概念，逗号分隔；只影响此预览" value={known} onChange={event => setKnown(event.target.value)} />
      <Space>每周时间 <InputNumber aria-label="候选路线每周小时" min={1} max={80} value={weeklyHours} onChange={value => setWeeklyHours(value ?? 10)} /> 小时 <Button type="primary" disabled={!target || !goal.trim()} loading={busy} onClick={() => void run()}>生成候选预览</Button></Space>
      {error && <Alert type="warning" showIcon message="候选资料不足或检查失败" description={error} />}
      {preview && <>
        <Alert type="info" showIcon message={`已检查 ${preview.checked_relations} 条关系`} description={preview.notice} />
        <Typography.Text type="secondary">阅读与练习估算 {preview.schedule.estimated_minutes} 分钟；未排期任务 {preview.schedule.unscheduled_count} 项。</Typography.Text>
        {preview.route.phases.map(phase => <Card size="small" key={phase.phase} title={`${phase.title} · ${phase.weeks}`}>
          {phase.items.map((item, index) => <div key={item.task_id ?? index} style={{ marginBottom: 12 }}>
            <strong>{item.title}</strong><p>{item.reason}</p>
            {item.uid && <Link to={`/papers/${encodeURIComponent(item.uid)}`}>查看论文原文</Link>}
          </div>)}
        </Card>)}
      </>}
    </Space>
  </Card>;
}
