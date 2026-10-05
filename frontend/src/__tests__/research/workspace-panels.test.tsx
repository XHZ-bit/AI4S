import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import ComparisonPanel from "../../components/research/ComparisonPanel";
import EvidencePanel from "../../components/research/EvidencePanel";
import PlansPanel from "../../components/research/PlansPanel";
import ProjectSettingsPanel from "../../components/research/ProjectSettingsPanel";
import { ProjectApiError } from "../../api/projects";
import { comparison, decision, facts, plan, project, snapshot } from "./fixtures";

const api = vi.hoisted(() => {
  class MockProjectApiError extends Error {
    status: number; code: string | null; currentVersion: number | null;
    constructor(status: number, message: string, detail?: { code?: string; current_version?: number | null }) {
      super(message); this.status = status; this.code = detail?.code ?? null; this.currentVersion = detail?.current_version ?? null;
    }
  }
  return {
    getProjectFacts: vi.fn(), listProjectPapers: vi.fn(), getProjectTask: vi.fn(), linkProjectPaper: vi.fn(), retryProjectTask: vi.fn(), startProjectExtraction: vi.fn(), transitionFact: vi.fn(),
    compareProjectCandidates: vi.fn(), saveProjectDecision: vi.fn(), updateProject: vi.fn(),
    listProjectDecisions: vi.fn(), listProjectPlans: vi.fn(), listProjectSnapshots: vi.fn(), generateProjectPlan: vi.fn(), saveProjectPlan: vi.fn(), createProjectSnapshot: vi.fn(),
    snapshotExportUrl: vi.fn(() => "http://example.test/export"), getProjectGraph: vi.fn(), getProjectProjectionStatus: vi.fn(), retryProjectProjection: vi.fn(),
    isVersionConflict: (error: unknown) => error instanceof MockProjectApiError && error.status === 409,
    ProjectApiError: MockProjectApiError,
  };
});
const papers = vi.hoisted(() => ({ listPapers: vi.fn(), uploadPdf: vi.fn() }));
vi.mock("../../api/projects", () => api);
vi.mock("../../api/papers", () => papers);

beforeEach(() => {
  localStorage.clear();
  Object.values(api).forEach(value => { if (typeof value === "function" && "mockReset" in value) (value as ReturnType<typeof vi.fn>).mockReset(); });
  papers.listPapers.mockReset().mockResolvedValue({ items: [], total: 0 });
  papers.uploadPdf.mockReset();
  api.getProjectFacts.mockResolvedValue(facts);
  api.listProjectPapers.mockResolvedValue({ items: [] });
  api.compareProjectCandidates.mockResolvedValue(comparison);
  api.saveProjectDecision.mockResolvedValue(decision);
  api.listProjectDecisions.mockResolvedValue({ items: [decision] });
  api.listProjectPlans.mockResolvedValue({ items: [{ ...plan, version: 2, title: "最新方案" }, plan] });
  api.listProjectSnapshots.mockResolvedValue({ items: [snapshot] });
  api.getProjectGraph.mockRejectedValue(new ProjectApiError(501, "尚未接入"));
});

test("refresh restores the explicitly selected saved plan instead of the oldest plan", async () => {
  api.listProjectPlans.mockResolvedValue({ items: [plan, { ...plan, id: "saved-new-plan", title: "最近保存的人工方案" }] });
  localStorage.setItem(`research-atlas:selected-plan:${project.id}`, "saved-new-plan");
  render(<PlansPanel project={project} />);
  expect(await screen.findByDisplayValue("最近保存的人工方案")).toBeTruthy();
});

test("partial extraction stays visible and manual correction remains a local draft", async () => {
  const view = render(<MemoryRouter><EvidencePanel project={project} onProjectReload={async () => undefined} /></MemoryRouter>);
  expect(await screen.findByText("抽取结果可能不完整")).toBeTruthy();
  expect(screen.getAllByText("候选·待确认").length).toBeGreaterThan(0);
  const correction = screen.getByDisplayValue("Patch based method");
  fireEvent.change(correction, { target: { value: "人工修正但未提交" } });
  expect(localStorage.getItem(`research-atlas:fact-draft:${project.id}:method-1`)).toBe("人工修正但未提交");
  view.unmount();
  render(<MemoryRouter><EvidencePanel project={project} onProjectReload={async () => undefined} /></MemoryRouter>);
  expect(await screen.findByDisplayValue("人工修正但未提交")).toBeTruthy();
  expect(screen.getAllByText("未保存到服务端").length).toBeGreaterThan(0);
});

test("upload failure is shown without inventing a linked paper", async () => {
  papers.uploadPdf.mockRejectedValue(new Error("上传失败：解析器离线"));
  const { container } = render(<MemoryRouter><EvidencePanel project={project} onProjectReload={async () => undefined} /></MemoryRouter>);
  await screen.findByText("尚未关联论文");
  const input = container.querySelector('input[type="file"]') as HTMLInputElement;
  fireEvent.change(input, { target: { files: [new File(["pdf"], "paper.pdf", { type: "application/pdf" })] } });
  expect(await screen.findByText("上传失败：解析器离线")).toBeTruthy();
  expect(screen.getByText("尚未关联论文")).toBeTruthy();
});

test("comparison separates project constraints from literature comparability", async () => {
  render(<ComparisonPanel project={project} />);
  expect((await screen.findAllByText("课题约束匹配")).length).toBe(2);
  expect(screen.getAllByText("未知/待补").length).toBeGreaterThan(0);
  const checks = screen.getAllByRole("checkbox");
  fireEvent.click(checks[0]); fireEvent.click(checks[1]);
  fireEvent.click(screen.getByRole("button", { name: /比较选中的 2 个候选/ }));
  expect(await screen.findByText("文献实验条件检查")).toBeTruthy();
  expect(screen.getByText("没有可直接比较的组")).toBeTruthy();
}, 30_000);

test("409 keeps settings form values instead of clearing the draft", async () => {
  api.updateProject.mockRejectedValue(new ProjectApiError(409, "项目已更新", { code: "version_conflict", current_version: 4 }));
  render(<ProjectSettingsPanel project={project} onSaved={vi.fn()} />);
  const objective = screen.getByLabelText("首轮验证目标");
  fireEvent.change(objective, { target: { value: "本地新目标" } });
  fireEvent.click(screen.getByRole("button", { name: "保存新版本" }));
  expect(await screen.findByText("服务端已有新版本")).toBeTruthy();
  expect((objective as HTMLTextAreaElement).value).toBe("本地新目标");
});

test("generation failure does not hide saved plan history and graph stays honest", async () => {
  api.generateProjectPlan.mockRejectedValue(new ProjectApiError(503, "模型不可用"));
  render(<PlansPanel project={project} />);
  expect(await screen.findByText("保存与快照历史")).toBeTruthy();
  fireEvent.click(screen.getByText("使用模型生成"));
  expect(await screen.findByText("模型不可用")).toBeTruthy();
  expect(screen.getAllByText("首轮验证").length).toBeGreaterThan(0);
  expect(screen.getAllByText("v1").length).toBeGreaterThan(0);
  expect(screen.getAllByText("v2").length).toBeGreaterThan(0);
  expect(await screen.findByText("课题图谱尚未接入")).toBeTruthy();
});

test("model failure can fall back to an empty user-input draft and save through the existing API", async () => {
  api.generateProjectPlan.mockRejectedValue(new ProjectApiError(503, "模型不可用"));
  api.saveProjectPlan.mockImplementation(async (_projectId: string, planId: string, request: { plan: typeof plan }) => ({
    ...request.plan,
    id: planId,
    version: 1,
    status: "saved" as const,
  }));
  render(<PlansPanel project={project} />);

  await screen.findByText("保存与快照历史");
  fireEvent.click(screen.getByText("使用模型生成"));
  expect(await screen.findByText("模型不可用")).toBeTruthy();

  fireEvent.click(screen.getByText("人工创建空白草稿"));
  expect(screen.getByText("用户输入")).toBeTruthy();
  expect(screen.getByText("模型不可用")).toBeTruthy();
  expect(api.generateProjectPlan).toHaveBeenCalledTimes(1);
  expect((screen.getByLabelText("方案标题") as HTMLInputElement).value).toBe("");
  expect((screen.getByLabelText("方案目标") as HTMLTextAreaElement).value).toBe("");

  fireEvent.change(screen.getByLabelText("方案标题"), { target: { value: "人工首轮验证" } });
  fireEvent.change(screen.getByLabelText("方案目标"), { target: { value: "由用户填写的验证目标" } });
  fireEvent.click(screen.getByText("确认保存"));
  fireEvent.click(await screen.findByText("保存新版本"));

  await waitFor(() => expect(api.saveProjectPlan).toHaveBeenCalledTimes(1));
  const [projectId, planId, request] = api.saveProjectPlan.mock.calls[0];
  expect(projectId).toBe(project.id);
  expect(planId).toMatch(/^draft-/);
  expect(request).toMatchObject({
    expected_project_version: project.version,
    expected_plan_version: 0,
    plan: {
      id: planId,
      project_id: project.id,
      version: 1,
      status: "draft",
      title: "人工首轮验证",
      objective: "由用户填写的验证目标",
      hypothesis: null,
      selected_method_id: decision.selected_method_id,
      selected_experiment_setting_ids: decision.selected_experiment_setting_ids,
      assumptions: [],
      unknowns: [],
      steps: [],
      target_measurements: [],
      risks: [],
      source_kind: "user_input",
      review_status: "current",
      review_reasons: [],
    },
  });
});

test("an unsaved manual draft is restored from browser storage without replacing server history", async () => {
  api.listProjectPlans.mockResolvedValue({ items: [] });
  const first = render(<PlansPanel project={project} />);
  await screen.findByText("保存与快照历史");
  fireEvent.click(screen.getByText("人工创建空白草稿"));
  fireEvent.change(screen.getByLabelText("方案标题"), { target: { value: "刷新后继续填写" } });

  const key = `research-atlas:plan-draft:${project.id}:new`;
  await waitFor(() => expect(JSON.parse(localStorage.getItem(key) ?? "null")).toMatchObject({
    id: null,
    title: "刷新后继续填写",
    source_kind: "user_input",
  }));
  first.unmount();

  render(<PlansPanel project={project} />);
  expect(await screen.findByDisplayValue("刷新后继续填写")).toBeTruthy();
  expect(screen.getByText("用户输入")).toBeTruthy();
  expect(api.generateProjectPlan).not.toHaveBeenCalled();
});
