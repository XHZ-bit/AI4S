import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, expect, test, vi } from "vitest";
import DecisionOverview from "../../components/research/DecisionOverview";
import FactEditor from "../../components/research/FactEditor";
import { displayMeasurement } from "../../components/research/StatusLabels";
import { decision, evidence, facts, method, plan, project, snapshot } from "./fixtures";

const api = vi.hoisted(() => ({ getProject: vi.fn(), getProjectAudit: vi.fn(), getProjectFacts: vi.fn(), listProjectDecisions: vi.fn(), listProjectPapers: vi.fn(), listProjectPlans: vi.fn(), listProjectSnapshots: vi.fn(), reviseProjectFact: vi.fn(), isVersionConflict: (error: unknown) => error instanceof Error && error.message === "409" }));
vi.mock("../../api/projects", () => api);
vi.mock("../../components/research/EvidenceDrawer", () => ({ default: ({ evidence: source }: { evidence: { quote: string } | null }) => source ? <div>{source.quote}</div> : null }));
beforeEach(() => {
  Object.values(api).forEach(fn => { if ("mockReset" in fn) fn.mockReset(); });
  localStorage.clear();
  api.getProject.mockResolvedValue(project); api.getProjectFacts.mockResolvedValue(facts);
  api.getProjectAudit.mockResolvedValue({ issues: [] }); api.listProjectDecisions.mockResolvedValue({ items: [decision] });
  api.listProjectPapers.mockResolvedValue({ items: [] }); api.listProjectPlans.mockResolvedValue({ items: [plan] }); api.listProjectSnapshots.mockResolvedValue({ items: [snapshot] });
});

test("overview shows saved rationale, unknowns and immutable snapshot links", async () => {
  render(<MemoryRouter><DecisionOverview project={project} /></MemoryRouter>);
  expect(await screen.findByText(decision.rationale)).toBeTruthy();
  expect(screen.getByText(`待补充：${plan.unknowns[0]}`)).toBeTruthy();
  expect(screen.getByRole("link", { name: "查看快照 v1（待复核）" }).getAttribute("href")).toContain(snapshot.id);
  fireEvent.click(screen.getByRole("button", { name: /查看依据/ }));
  expect(screen.getByText(evidence.quote!)).toBeTruthy();
});

test("failed refresh clears outdated decisions and retry restores current server data", async () => {
  render(<MemoryRouter><DecisionOverview project={project} /></MemoryRouter>);
  await screen.findByText(decision.rationale);
  api.getProjectFacts.mockRejectedValueOnce(new Error("Connection lost"));
  fireEvent.click(screen.getByRole("button", { name: "刷新总览" }));
  expect(await screen.findByText("决策总览加载失败")).toBeTruthy();
  expect(screen.queryByText(decision.rationale)).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "重试总览" }));
  expect(await screen.findByText(decision.rationale)).toBeTruthy();
});

test("an old project response cannot replace the new project's overview", async () => {
  let resolveOld!: (value: typeof facts) => void;
  api.getProjectFacts.mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve; }));
  const view = render(<MemoryRouter><DecisionOverview project={project} /></MemoryRouter>);
  const next = { ...project, id: "other-project" };
  api.getProject.mockResolvedValue(next); api.listProjectDecisions.mockResolvedValue({ items: [{ ...decision, rationale: "New rationale" }] });
  view.rerender(<MemoryRouter><DecisionOverview project={next} /></MemoryRouter>);
  await screen.findByText("New rationale");
  await act(async () => resolveOld(facts));
  expect(screen.queryByText(decision.rationale)).toBeNull();
});

test("content corrections save through the API and preserve input on version conflict", async () => {
  const onSaved = vi.fn().mockResolvedValue(undefined);
  api.reviseProjectFact.mockRejectedValueOnce(new Error("409")).mockResolvedValue({ ...method, version: 2 });
  render(<FactEditor fact={method} evidence={[evidence]} onSaved={onSaved} />);
  fireEvent.click(screen.getByRole("button", { name: "修订内容" }));
  fireEvent.change(screen.getByLabelText("修订内容"), { target: { value: "Corrected method" } });
  fireEvent.change(screen.getByLabelText("修订人"), { target: { value: "Reviewer" } });
  fireEvent.change(screen.getByLabelText("修订理由"), { target: { value: "Checked source" } });
  fireEvent.click(screen.getByRole("button", { name: "保存新版本" }));
  await screen.findByText(/修正未覆盖新版本/);
  expect((screen.getByLabelText("修订内容") as HTMLTextAreaElement).value).toBe("Corrected method");
  expect(onSaved).not.toHaveBeenCalled();
  expect(api.reviseProjectFact).toHaveBeenCalledWith(project.id, method.id, expect.objectContaining({ expected_version: 1, changes: { name: "Corrected method" }, actor: "Reviewer" }));
  fireEvent.click(await screen.findByRole("button", { name: "保存新版本" }));
  await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1));
});

test("upper bounds and unknown values cannot look like exact measured scores", () => {
  expect(displayMeasurement({ value: 99.6, unit: null, scale: "percent", lower: null, upper: 99.6 })).toBe("上界 ≤ 99.6 (percent)");
  expect(displayMeasurement(null)).toBe("未知/未报告");
});
