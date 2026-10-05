import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { beforeEach, expect, test, vi } from "vitest";
import type { GraphQueryResult, ProjectSnapshot } from "../../api/project-types";
import { ProjectApiError } from "../../api/projects";
import ProjectGraph from "../../pages/research/ProjectGraph";
import { graphView, impactPaths } from "../../components/research/project-graph-utils";
import { evidence, facts, project, snapshot } from "./fixtures";

const api = vi.hoisted(() => {
  class MockProjectApiError extends Error { status: number; constructor(status: number, message: string) { super(message); this.status = status; } }
  return { getProject: vi.fn(), listProjectSnapshots: vi.fn(), getProjectFacts: vi.fn(), getProjectGraph: vi.fn(), getProjectProjectionStatus: vi.fn(), retryProjectProjection: vi.fn(), ProjectApiError: MockProjectApiError };
});
vi.mock("../../api/projects", () => api);
vi.mock("react-force-graph-2d", async () => {
  const React = await import("react");
  return { default: React.forwardRef((props: any, ref) => {
    React.useImperativeHandle(ref, () => ({ zoomToFit: vi.fn() }));
    return <div data-testid="graph-canvas">{props.graphData.nodes.map((node: any) => <button key={node.id} onClick={() => props.onNodeClick(node)}>node-{node.name}</button>)}</div>;
  }) };
});

const graph: GraphQueryResult = {
  project_id: project.id,
  snapshot_id: snapshot.id,
  nodes: [
    { id: "plan-1", kind: "plan", label: "Validation Plan", properties: { review_status: "needs_review" } },
    { id: "decision-1", kind: "decision", label: "Chosen Route", properties: { source_kind: "user_input" } },
    { id: "method-1", kind: "method", label: "Patch Method", properties: { status: "candidate" } },
    { id: "setting-a", kind: "experiment_setting", label: "Setting A", properties: { dataset: "MVTec AD", status: "candidate" } },
    { id: "setting-b", kind: "experiment_setting", label: "Setting B", properties: { dataset: "VisA", status: "candidate" } },
    { id: "measurement-1", kind: "measurement", label: "Image AUROC", properties: { finding_status: "reported" } },
    { id: evidence.id, kind: "evidence", label: "Evidence One", properties: { source_kind: "literature_report", finding_status: "reported" } },
  ],
  edges: [
    { id: "e1", kind: "USES_DECISION", source_id: "plan-1", target_id: "decision-1", fact_ids: [], evidence_ids: [], properties: {} },
    { id: "e2", kind: "SELECTS", source_id: "decision-1", target_id: "setting-a", fact_ids: ["setting-a"], evidence_ids: [], properties: {} },
    { id: "e3", kind: "CONFIGURES", source_id: "method-1", target_id: "setting-a", fact_ids: ["method-1", "setting-a"], evidence_ids: [], properties: {} },
    { id: "e4", kind: "CONFIGURES", source_id: "method-1", target_id: "setting-b", fact_ids: ["method-1", "setting-b"], evidence_ids: [], properties: {} },
    { id: "e5", kind: "MEASURES", source_id: "setting-a", target_id: "measurement-1", fact_ids: ["setting-a", "measurement-1"], evidence_ids: [], properties: {} },
    { id: "e6", kind: "SUPPORTED_BY", source_id: "measurement-1", target_id: evidence.id, fact_ids: ["measurement-1"], evidence_ids: [evidence.id], properties: {} },
  ],
};

const renderPage = (url = `/research/${project.id}/graph?snapshot_id=${snapshot.id}&mode=evidence&node_id=plan-1`) => {
  const router = createMemoryRouter([{ path: "/research/:projectId/graph", element: <ProjectGraph /> }], { initialEntries: [url] });
  return { router, ...render(<RouterProvider router={router} />) };
};

beforeEach(() => {
  api.getProject.mockReset().mockResolvedValue(project);
  api.listProjectSnapshots.mockReset().mockResolvedValue({ items: [snapshot] });
  api.getProjectFacts.mockReset().mockResolvedValue(facts);
  api.getProjectGraph.mockReset().mockResolvedValue(graph);
  api.getProjectProjectionStatus.mockReset().mockRejectedValue(new Error("status unavailable"));
  api.retryProjectProjection.mockReset();
});

test("isolates graph by project and rejects a foreign response", async () => {
  api.getProjectGraph.mockResolvedValue({ ...graph, project_id: "other-project" });
  renderPage();
  expect(await screen.findByText("图谱版本不一致")).toBeTruthy();
  expect(screen.queryByTestId("graph-canvas")).toBeNull();
});

test("shows node details and readable evidence with a document jump", async () => {
  renderPage();
  fireEvent.click(await screen.findByRole("button", { name: "node-Evidence One" }));
  expect(screen.getByText(evidence.quote!)).toBeTruthy();
  const link = screen.getByRole("link", { name: "打开论文与定位章节" });
  expect(link.getAttribute("href")).toContain("/papers/paper-1");
  expect(link.getAttribute("href")).toContain("passage-1");
});

test("method view keeps same method experiment settings separate", async () => {
  renderPage(`/research/${project.id}/graph?snapshot_id=${snapshot.id}&mode=method&node_id=method-1`);
  expect(await screen.findByRole("button", { name: "node-Setting A" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "node-Setting B" })).toBeTruthy();
});

test("impact view highlights dependency paths without calling the plan wrong", async () => {
  renderPage(`/research/${project.id}/graph?snapshot_id=${snapshot.id}&mode=impact&node_id=${evidence.id}`);
  expect(await screen.findByText("影响范围表示需要复核，不表示方案已经错误")).toBeTruthy();
  expect(screen.getByText("Validation Plan")).toBeTruthy();
  expect(impactPaths(graph.nodes, graph.edges, evidence.id)[0]).toContain("plan-1");
});

test("default task view does not pile the whole projection", () => {
  const view = graphView(graph.nodes, graph.edges, "overview", "plan-1", new Set());
  expect(view.nodeIds.size).toBeLessThan(graph.nodes.length);
  expect(view.nodeIds.has("plan-1")).toBe(true);
});

test("shows empty graph state", async () => {
  api.getProjectGraph.mockResolvedValue({ ...graph, nodes: [], edges: [] });
  renderPage();
  expect(await screen.findByText("当前快照没有图谱数据")).toBeTruthy();
});

test("shows service failure while preserving return links", async () => {
  api.getProjectGraph.mockRejectedValue(new ProjectApiError(503, "Neo4j unavailable"));
  renderPage();
  expect(await screen.findByText("图服务不可用或查询失败")).toBeTruthy();
  expect(screen.getAllByRole("link", { name: "返回方案" }).length).toBeGreaterThan(0);
  expect(screen.getByRole("link", { name: "查看资料" })).toBeTruthy();
});

test("rejects snapshot revision mismatch", async () => {
  api.getProjectGraph.mockResolvedValue({ ...graph, snapshot_id: "old-snapshot" });
  renderPage();
  expect(await screen.findByText("图谱版本不一致")).toBeTruthy();
  expect(screen.queryByText("Validation Plan")).toBeNull();
});

test("older request cannot overwrite a newly navigated project", async () => {
  let resolveOld!: (value: GraphQueryResult) => void;
  let resolveNew!: (value: GraphQueryResult) => void;
  api.getProject.mockImplementation((id: string) => Promise.resolve({ ...project, id, title: id }));
  api.listProjectSnapshots.mockImplementation((id: string) => Promise.resolve({ items: [{ ...snapshot, id: `snapshot-${id}`, project_id: id } as ProjectSnapshot] }));
  api.getProjectGraph.mockImplementation((id: string) => new Promise(resolve => { if (id === "old") resolveOld = resolve; else resolveNew = resolve; }));
  const { router } = renderPage("/research/old/graph?snapshot_id=snapshot-old");
  await waitFor(() => expect(api.getProjectGraph).toHaveBeenCalledWith("old", "snapshot-old", expect.anything(), expect.anything()));
  await router.navigate("/research/new/graph?snapshot_id=snapshot-new");
  await waitFor(() => expect(api.getProjectGraph).toHaveBeenCalledWith("new", "snapshot-new", expect.anything(), expect.anything()));
  resolveNew({ ...graph, project_id: "new", snapshot_id: "snapshot-new", nodes: [{ id: "new-node", kind: "plan", label: "New Project Plan", properties: {} }], edges: [] });
  expect(await screen.findByRole("button", { name: "node-New Project Plan" })).toBeTruthy();
  resolveOld({ ...graph, project_id: "old", snapshot_id: "snapshot-old", nodes: [{ id: "old-node", kind: "plan", label: "Old Project Plan", properties: {} }], edges: [] });
  await new Promise(resolve => setTimeout(resolve, 0));
  expect(screen.queryByRole("button", { name: "node-Old Project Plan" })).toBeNull();
  expect(screen.getByRole("button", { name: "node-New Project Plan" })).toBeTruthy();
});
