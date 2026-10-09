import { useEffect, useState } from "react";
import { Alert, Button, Card, Space, Tag } from "antd";
import { Link } from "react-router-dom";
import { commitReplan, previewReplan, type ReplanPreview, type RoadmapResult } from "../api/roadmap";

export default function RoadmapReplan({ route, onSaved }: { route: RoadmapResult; onSaved: (saved: RoadmapResult) => void }) {
  const [preview, setPreview] = useState<ReplanPreview>();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { setPreview(undefined); setError(""); }, [route.id, route.version]);
  if (route.id == null) return null;
  const id = route.id;
  const version = route.version || 1;
  const load = async () => {
    setBusy(true);
    try { setPreview(await previewReplan(id, version)); setError(""); }
    catch (caught) { setError(String(caught)); }
    finally { setBusy(false); }
  };
  const save = async () => {
    if (!preview) return;
    setBusy(true);
    try { onSaved(await commitReplan(id, version, preview.input_fingerprint)); setPreview(undefined); setError(""); }
    catch (caught) { setError(String(caught)); }
    finally { setBusy(false); }
  };
  return <Card title="按学习记录调整路线" extra={<Link to="/workflow">查看掌握与任务记录 →</Link>}>
    <p>预览会重新读取当前已人工核验的关系、明确确认的掌握记录和固定练习反馈。旧路线及完成历史保留。</p>
    <Button onClick={() => void load()} loading={busy}>预览调整</Button>
    {error && <Alert type="error" style={{ marginTop: 12 }} message={error} />}
    {preview && <div style={{ marginTop: 16 }}>
      <Space wrap><Tag>每周 {preview.schedule.weekly_hours} 小时</Tag><Tag>阅读与练习估算 {preview.schedule.estimated_minutes} 分钟</Tag><Tag>未排期 {preview.schedule.unscheduled_count} 项</Tag><Tag>已确认掌握 {preview.confirmed_concepts.length} 项</Tag></Space>
      {!preview.roadmap.phases.length && <Alert type="success" message="目标已由你确认掌握，当前不再安排新任务" />}
      {preview.roadmap.phases.map(phase => <Card size="small" key={phase.phase} title={`${phase.title} · ${phase.weeks}`} style={{ marginTop: 10 }}>
        {phase.items.map(item => <div key={item.task_id || item.title}><Space wrap><span>{item.title}</span>{item.done && <Tag>沿用完成记录</Tag>}{item.scheduled_week && <Tag>第 {item.scheduled_week} 周</Tag>}{item.estimated_minutes != null && <Tag>估算 {item.estimated_minutes} 分钟</Tag>}{item.source_url && <Link to={item.source_url}>打开来源</Link>}</Space></div>)}
      </Card>)}
      <Button type="primary" style={{ marginTop: 14 }} loading={busy} onClick={() => void save()}>确认生成新路线版本</Button>
    </div>}
  </Card>;
}
