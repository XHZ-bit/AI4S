import { useCallback, useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { Alert, Button, Space, Spin, Tabs, Tag, Typography } from "antd";
import type { ResearchProject } from "../../api/project-types";
import { DOMAIN_PROFILES } from "../../api/project-types";
import { getProject } from "../../api/projects";
import ComparisonPanel from "../../components/research/ComparisonPanel";
import EvidencePanel from "../../components/research/EvidencePanel";
import PlansPanel from "../../components/research/PlansPanel";
import ProjectSettingsPanel from "../../components/research/ProjectSettingsPanel";
import "./research-workspace.css";

export const WORKFLOW_GUIDANCE: Record<string, { message: string; description: string; next: string; action: string }> = {
  evidence: { message: "第 1 步：关联资料并确认事实", description: "先关联带原文的论文，再提取候选。逐项核对方法、实验设置和测量；表格未解析时保留待补录标记，不直接采信数值。未报告的信息保持未知。", next: "compare", action: "前往条件比较" },
  compare: { message: "第 2 步：比较条件，再由你选择路线", description: "核对数据集、划分、评估协议和指标范围。不可比不等于方法不好；资源信息不足不等于可行。保存选择理由后进入方案编辑。", next: "plans", action: "前往方案编辑" },
  plans: { message: "第 3 步：审核方案，保存并冻结版本", description: "模型建议不是实验结果。模型不可用时可创建人工草稿；失败后请保留输入并检查错误，避免重复生成。确认保存后创建快照，再导出 PDF / JSON 并查看依据。", next: "evidence", action: "返回核对证据" },
  settings: { message: "修改条件后复核相关成果", description: "条件变更可能影响既有路线。核对待复核提示并重新比较；旧方案和快照仍保留，不会自动改写。", next: "compare", action: "重新比较候选" },
};

export default function ResearchProjectPage() {
  const { projectId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const [project, setProject] = useState<ResearchProject | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const reload = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setError("");
    try { setProject(await getProject(projectId, signal)); }
    catch (caught) {
      if (!(caught instanceof DOMException && caught.name === "AbortError")) setError(caught instanceof Error ? caught.message : "课题加载失败");
    } finally { if (!signal?.aborted) setLoading(false); }
  }, [projectId]);

  useEffect(() => {
    const controller = new AbortController();
    void reload(controller.signal);
    return () => controller.abort();
  }, [reload]);

  if (loading && !project) return <Spin />;
  if (!project) return <Alert type="error" showIcon message="无法打开课题" description={error || "课题不存在"} action={<Button onClick={() => void reload()}>重试</Button>} />;

  const requestedTab = params.get("tab") ?? "evidence";
  const tab = Object.prototype.hasOwnProperty.call(WORKFLOW_GUIDANCE, requestedTab) ? requestedTab : "evidence";
  const guidance = WORKFLOW_GUIDANCE[tab];
  return <Space direction="vertical" size="large" style={{ width: "100%" }}>
    <div><Link to="/research">← 返回课题列表</Link><div className="research-page-heading"><div><Typography.Title level={2}>{project.title}</Typography.Title><Typography.Paragraph>{project.research_question}</Typography.Paragraph><Space wrap><Tag>{DOMAIN_PROFILES[project.domain].label}</Tag><Tag>项目 v{project.version}</Tag><Tag>约束 v{project.constraints.version}</Tag><Tag color={project.status === "active" ? "green" : "default"}>{project.status === "active" ? "进行中" : "已归档"}</Tag></Space></div><Button onClick={() => void reload()}>刷新服务端版本</Button></div></div>
    {error && <Alert type="error" showIcon message="刷新失败，当前仍显示上次已加载内容" description={error} />}
    <Alert type="info" showIcon message={guidance.message} description={<Space direction="vertical"><span>{guidance.description}</span><Button onClick={() => setParams({ tab: guidance.next })}>{guidance.action}</Button></Space>} />
    <Tabs activeKey={tab} onChange={key => setParams({ tab: key })} items={[
      { key: "evidence", label: "资料与证据", children: <EvidencePanel project={project} onProjectReload={() => reload()} /> },
      { key: "compare", label: "候选比较与选择", children: <ComparisonPanel project={project} /> },
      { key: "plans", label: "方案编辑与历史", children: <PlansPanel project={project} /> },
      { key: "settings", label: "课题设置", children: <ProjectSettingsPanel project={project} onSaved={setProject} /> },
    ]} />
  </Space>;
}
