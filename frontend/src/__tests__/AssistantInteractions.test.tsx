import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import ScenarioPanel from "../components/workspace/ScenarioPanel";
import InteractiveLab, { TensorAnimation, WindowAnimation } from "../components/workspace/InteractiveLab";
import { project } from "./research/fixtures";
import { getInsights, evaluateScenarios } from "../api/assistant";
import { apiPost } from "../api/client";
import { getCaseSession } from "../api/cases";
vi.mock("../api/assistant", async original => ({ ...await original<typeof import("../api/assistant")>(), getInsights: vi.fn(), evaluateScenarios: vi.fn() }));
vi.mock("../api/client", () => ({ apiPost: vi.fn() }));
vi.mock("../api/cases", () => ({ getCaseSession: vi.fn() }));
const report: any = { input_fingerprint: "f", actions: [], candidates: [], exercises: [{ id: "observation-v1", kind: "shape", prompt: "填写观测张量", parameters: { B: 2, To: 3, Do: 20 }, references: [{ kind: "source", id: "code" }], result: null }] };
const session: any = { id: "s", version: 0, stale: false, state: {}, runs: [] };
beforeEach(() => { vi.clearAllMocks(); localStorage.clear(); vi.mocked(getInsights).mockResolvedValue(report); vi.mocked(evaluateScenarios).mockResolvedValue({ input_fingerprint: "f", baseline: [], scenarios: [] }); });
test("tensor feedback follows the numeric control and windows support single step/reset", () => {
  render(<><TensorAnimation /><WindowAnimation /></>);
  fireEvent.change(screen.getByLabelText("设置 B"), { target: { value: "4" } });
  expect(screen.getByText("[4, 3, 20]")).toBeTruthy();
  const cells = document.querySelectorAll(".window-observation");
  const first = cells[0]; fireEvent.click(screen.getByRole("button", {name:/单.*步/}));
  expect(first.classList.contains("window-observation")).toBe(false);
  fireEvent.click(screen.getByRole("button", {name:/重.*置/})); expect(first.classList.contains("window-observation")).toBe(true);
});
test("scenarios cancel old requests and keep only the latest response", async () => {
  let resolveOld!: (r: any) => void;
  vi.mocked(evaluateScenarios).mockImplementationOnce(() => new Promise(r => { resolveOld = r; })).mockResolvedValue({ input_fingerprint: "f", baseline: [], scenarios: [{ id: "new", label: "LATEST", changes: [], candidates: [] }] });
  render(<ScenarioPanel project={project} />);
  await waitFor(() => expect(evaluateScenarios).toHaveBeenCalledTimes(1));
  fireEvent.change(screen.getByLabelText("情景 1 显存数值"), { target: { value: "24" } });
  expect(screen.getByText("条件已更新 · 结果待更新")).toBeTruthy();
  await waitFor(() => expect(evaluateScenarios).toHaveBeenCalledTimes(2));
  await screen.findByText("LATEST");
  await act(async () => resolveOld({ baseline: [], scenarios: [{ id: "old", label: "STALE", changes: [] }] }));
  expect(screen.queryByText("STALE")).toBeNull();
  expect((vi.mocked(evaluateScenarios).mock.calls[0][4] as AbortSignal).aborted).toBe(true);
});
test("four scenarios are the limit and drafts survive a project version refresh", async () => {
  localStorage.setItem(`atlas:scenarios:${project.id}`, JSON.stringify({
    version: project.version,
    items: Array.from({ length: 4 }, (_, i) => ({
      id: `scenario-${i + 1}`,
      label: `情景 ${i + 1}`,
      constraints: project.constraints,
    })),
  }));
  const view = render(<ScenarioPanel project={project} />);
  expect((screen.getByRole("button", { name: /添加对照情景/ }) as HTMLButtonElement).disabled).toBe(true);
  view.unmount(); render(<ScenarioPanel project={{...project,version:project.version+1}} />);
  expect(screen.getByLabelText("情景 4 名称")).toBeTruthy();
  expect(screen.getByText(/课题基准已更新，本地情景输入已保留/)).toBeTruthy();
}, 30000);
test("practice conflict preserves the answer and reload enables a versioned retry", async () => {
  vi.mocked(apiPost).mockRejectedValueOnce(Object.assign(new Error("409 冲突"), { status: 409 })).mockResolvedValue({ ...session, version: 2 });
  vi.mocked(getCaseSession).mockResolvedValue({ ...session, version: 1 });
  const saved = vi.fn();
  const view = render(<MemoryRouter><InteractiveLab caseId="case" session={session} onSaved={saved} /></MemoryRouter>);
  fireEvent.click(screen.getByRole("tab", { name: "动手练习" }));
  for (const [i, v] of [2, 3, 20].entries()) fireEvent.change(await screen.findByLabelText(`observation-v1 第${i + 1}维`), { target: { value: String(v) } });
  fireEvent.click(screen.getByText("提交练习")); await screen.findByText(/409 冲突/);
  expect((screen.getByLabelText("observation-v1 第1维") as HTMLInputElement).value).toBe("2");
  fireEvent.click(screen.getByText("重新加载练习记录")); await waitFor(() => expect(saved).toHaveBeenCalled());
  view.rerender(<MemoryRouter><InteractiveLab caseId="case" session={{ ...session, version: 1 }} onSaved={saved} /></MemoryRouter>);
  fireEvent.click(screen.getByText("提交练习"));
  await waitFor(() => expect(apiPost).toHaveBeenLastCalledWith(expect.any(String), { version: 1, shape: [2, 3, 20] }));
});
