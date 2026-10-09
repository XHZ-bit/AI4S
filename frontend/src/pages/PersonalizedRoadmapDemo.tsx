import { useEffect, useState } from "react";
import { Alert, Button, Card, Select, Space, Tag, Typography } from "antd";
import { Link } from "react-router-dom";
import { apiPost } from "../api/client";
import type { RoadmapResult } from "../api/roadmap";
import EvidenceButton from "../components/EvidenceButton";

const concepts = [
  { value: "Imitation learning", label: "已了解模仿学习" },
  { value: "Diffusion models", label: "已了解扩散模型" },
];
const cases = [
  { label: "学习者 A · 机器人方向", initial: ["Imitation learning"] },
  { label: "学习者 B · 生成模型方向", initial: ["Diffusion models"] },
];

function LearnerColumn({ label, initial }: { label: string; initial: string[] }) {
  const [known, setKnown] = useState(initial);
  const [route, setRoute] = useState<RoadmapResult | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let live = true;
    setBusy(true);
    apiPost<RoadmapResult>("/api/roadmap/preview", {
      profile: { goal: "理解 Diffusion Policy", target_uid: "method:diffusion-policy", known_concepts: known, weekly_hours: 10 },
    }).then(data => { if (live) { setRoute(data); setError(""); } })
      .catch(e => { if (live) { setRoute(null); setError(String(e)); } })
      .finally(() => { if (live) setBusy(false); });
    return () => { live = false; };
  }, [known]);
  return <Card title={label} style={{ height: "100%" }} loading={busy}>
    <Typography.Paragraph>共同目标：理解 Diffusion Policy。改变已掌握知识，观察待学阶段。</Typography.Paragraph>
    <Select mode="multiple" aria-label={`${label}已掌握概念`} value={known} onChange={setKnown}
      options={concepts} style={{ width: "100%", marginBottom: 16 }} placeholder="选择已掌握概念" />
    {error && <Alert type="warning" message="尚未准备演示资料" description={error} style={{ marginBottom: 12 }} />}
    {route?.phases.map((phase, index) => <div key={phase.title} style={{ borderLeft: "3px solid #147d92", paddingLeft: 16, marginBottom: 22 }}>
      <Space wrap><Tag color="cyan">第 {index + 1} 阶段</Tag><Typography.Text strong>{phase.title.replace(/^(concept|method):/, "").replace(/-/g, " ")}</Typography.Text></Space>
      {phase.items.map(item => <div key={item.uid} style={{ marginTop: 9 }}>
        <Typography.Text>{item.title}</Typography.Text><br />
        <Space wrap style={{ marginTop: 6 }}>
          {item.evidence_ids?.map(id => <EvidenceButton key={id} id={id} />)}
          {item.uid && <Link to={`/papers/${item.uid}`}>论文工作区 ↗</Link>}
        </Space>
      </div>)}
    </div>)}
    {route && <Typography.Text type="secondary">{known.length ? `已掌握：${known.join("、")}` : "未声明已掌握概念"}；路线只展示当前缺口。</Typography.Text>}
  </Card>;
}

export default function PersonalizedRoadmapDemo() {
  return <Space direction="vertical" size="large" style={{ width: "100%" }}>
    <div><Tag color="blue">第二个体验案例 · 同一研究目标，不同学习起点</Tag>
      <Typography.Title level={2} style={{ marginTop: 10 }}>从论文证据走向个人学习路线</Typography.Title>
      <Typography.Paragraph>两位学习者都想理解 Diffusion Policy。平台依据各自已有知识，裁剪先修阶段；每篇推荐可返回原文段落。</Typography.Paragraph>
    </div>
    <Alert type="warning" showIcon message="自动核查预览 · 教学顺序仍是假设"
      description="系统自动检查资料版本、原文定位、关系结构、先修环路和画像差异。它不能由此证明教学判断正确或真实学习效果；此页不保存为正式路线。" />
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(320px,1fr))", gap: 16 }}>
      {cases.map(c => <LearnerColumn key={c.label} {...c} />)}
    </div>
    <Card title="资料与下一步">
      <Typography.Paragraph>资料版本固定为 RoboMimic 2108.03298v2、DDPM 2006.11239v2、Diffusion Policy 2303.04137v4。本页与 <Link to="/roadmap">科研路线推荐</Link> 使用同一规划算法，但证据级别和结果状态明确区分。</Typography.Paragraph>
      <Link to="/cases/diffusion-policy-intro"><Button>进入原有源码交互案例 →</Button></Link>
    </Card>
  </Space>;
}
