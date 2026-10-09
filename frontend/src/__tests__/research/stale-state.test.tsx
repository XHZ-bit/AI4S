import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import ComparisonPanel from "../../components/research/ComparisonPanel";
import ProjectGraphPanel from "../../components/research/ProjectGraphPanel";
import { comparison, facts, project } from "./fixtures";

const api = vi.hoisted(() => ({
  getProjectFacts: vi.fn(), compareProjectCandidates: vi.fn(), saveProjectDecision: vi.fn(),
  getProjectGraph: vi.fn(), isVersionConflict: () => false,
  ProjectApiError: class extends Error { status = 503; },
}));
vi.mock("../../api/projects", () => api);
vi.mock("../../api/assistant",async importOriginal=>({...await importOriginal<typeof import("../../api/assistant")>(),getInsights:vi.fn(async()=>({candidates:[{id:facts.experiment_settings[0].id,checks:[{dimension:"dataset_policy",status:"conflict",actual:"MVTec AD",reason:"排除列表 excluded_datasets 优先"}]}]}))}));
vi.mock("react-force-graph-2d", () => ({ default: ({ graphData }: { graphData: unknown }) => <pre>{JSON.stringify(graphData)}</pre> }));

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return { promise, resolve };
}

beforeEach(() => {
  api.getProjectFacts.mockReset().mockResolvedValue(facts);
  api.compareProjectCandidates.mockReset().mockResolvedValue(comparison);
  api.saveProjectDecision.mockReset();
  api.getProjectGraph.mockReset();
});

test("excluded datasets override the allowlist", async () => {
  render(<ComparisonPanel project={{ ...project, constraints: { ...project.constraints, excluded_datasets: ["MVTec AD"] } }} />);
  expect(await screen.findByText(/排除列表 excluded_datasets 优先/)).toBeTruthy();
});

test("withdrawn methods cannot appear as route candidates", async () => {
  api.getProjectFacts.mockResolvedValue({ ...facts, methods: facts.methods.map(method => ({ ...method, status: "withdrawn" })) });
  render(<ComparisonPanel project={project} />);
  await screen.findByText("没有可比较的实验设置。请先关联论文并审核抽取结果。");
  expect(screen.queryAllByRole("checkbox")).toHaveLength(0);
});

test("changing selection invalidates an existing comparison", async () => {
  render(<ComparisonPanel project={project} />);
  const checks = await screen.findAllByRole("checkbox");
  fireEvent.click(checks[0]); fireEvent.click(checks[1]);
  fireEvent.click(screen.getByRole("button", { name: /比较选中的 2 个候选/ }));
  await screen.findByText("文献实验条件检查");
  fireEvent.click(checks[0]);
  expect(screen.queryByText("文献实验条件检查")).toBeNull();
});

test("a comparison arriving after project version change is ignored", async () => {
  const old = deferred<typeof comparison>();
  api.compareProjectCandidates.mockReturnValue(old.promise);
  const view = render(<ComparisonPanel project={project} />);
  const checks = await screen.findAllByRole("checkbox");
  fireEvent.click(checks[0]); fireEvent.click(checks[1]);
  fireEvent.click(screen.getByRole("button", { name: /比较选中的 2 个候选/ }));
  expect((checks[0] as HTMLInputElement).disabled).toBe(true);
  view.rerender(<ComparisonPanel project={{ ...project, version: project.version + 1 }} />);
  await act(async () => { old.resolve(comparison); });
  expect(screen.queryByText("文献实验条件检查")).toBeNull();
  expect(api.getProjectFacts).toHaveBeenCalledTimes(2);
});

test("late graph responses cannot overwrite the selected snapshot", async () => {
  const old = deferred<unknown>();
  api.getProjectGraph.mockReturnValueOnce(old.promise).mockResolvedValueOnce({
    project_id: project.id, snapshot_id: "new", nodes: [{ id: "new-node", label: "new-result", kind: "method" }], edges: [],
  });
  const view = render(<ProjectGraphPanel projectId={project.id} snapshotId="old" />);
  view.rerender(<ProjectGraphPanel projectId={project.id} snapshotId="new" />);
  await screen.findByText(/new-result/);
  await act(async () => { old.resolve({ project_id: project.id, snapshot_id: "old", nodes: [{ id: "old", label: "old-result" }], edges: [] }); });
  expect(screen.queryByText(/old-result/)).toBeNull();
  expect(screen.getByText(/new-result/)).toBeTruthy();
  view.rerender(<ProjectGraphPanel projectId={project.id} snapshotId={null} />);
  expect(screen.queryByText(/new-result/)).toBeNull();
});

test("a graph response for the wrong snapshot fails explicitly", async () => {
  api.getProjectGraph.mockResolvedValue({ project_id: project.id, snapshot_id: "wrong", nodes: [], edges: [] });
  render(<ProjectGraphPanel projectId={project.id} snapshotId="selected" />);
  expect(await screen.findByText("图谱响应不属于当前课题与快照")).toBeTruthy();
});
