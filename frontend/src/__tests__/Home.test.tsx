import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, test, vi } from "vitest";
import useRecentProjects from "../components/workbench/useRecentProjects";
import Home from "../pages/Home";
import { listPapers } from "../api/papers";
import { workflowOverview, type WorkflowOverview } from "../api/workflow";

vi.mock("../components/workbench/useRecentProjects", () => ({default:vi.fn(()=>({items:[],loading:false,error:"",retry:vi.fn()}))}));
vi.mock("../api/papers", () => ({ listPapers: vi.fn() }));
vi.mock("../api/workflow", () => ({ workflowOverview: vi.fn() }));
vi.mock("../components/RuntimeStatus", () => ({ default: () => <p>Runtime diagnostics</p> }));
vi.mock("../components/ReadLaterPreview", () => ({ default: () => null }));

function overview(pending = 0, title?: string): WorkflowOverview {
  return { counts: { pending, in_progress: 0, completed: 0, needs_review: 0 }, total: pending, snapshot_required: 0,
    next: title ? [{ id: title, title, url: "/papers/source?tab=reading", detail: "Read the source", source_kind: "paper", source_id: "source", source_version: "1", item_id: "read", status: "pending", evidence_level: "none", estimated_minutes: 5, evidence_ids: [], project_id: null }] : [] };
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<T>((done, fail) => { resolve = done; reject = fail; });
  return { promise, resolve, reject };
}
function show() { return render(<MemoryRouter><Home /></MemoryRouter>); }
const link = (label: string) => screen.getByText(label).closest("a")!;

beforeEach(() => {
  vi.clearAllMocks(); localStorage.clear();
  vi.mocked(useRecentProjects).mockReturnValue({account:"local",items:[],loading:false,error:"",retry:vi.fn()});
  vi.mocked(listPapers).mockResolvedValue({ items: [], total: 0 });
  vi.mocked(workflowOverview).mockResolvedValue(overview());
});

test("new workbench exposes two starts without duplicate tool lists or hero search", async () => {
  localStorage.setItem("atlas:lastWorkspace", "https://elsewhere.invalid/");
  show();
  expect(await screen.findByText("添加第一篇论文，即可开始阅读和记录理解。")).toBeTruthy();
  expect(link("从论文开始").getAttribute("href")).toBe("/manage?add=1");
  expect(link("探索一个想法").getAttribute("href")).toBe("/research?new=1");
  expect(screen.queryByText("继续上次任务")).toBeNull();
  expect(screen.queryByRole('searchbox')).toBeNull();
  expect(screen.queryByText("自动行动清单")).toBeNull();
  expect(link("任务面板").getAttribute("href")).toBe("/workflow");
});

test("returning users resume the exact reading location and recent paper titles are direct links", async () => {
  localStorage.setItem("atlas:lastWorkspace", "/papers/paper%3Aone?tab=reading&page=4");
  vi.mocked(listPapers).mockResolvedValue({ items: [{ uid: "paper:one", title: "Original paper", source: "upload", year: 2025 }], total: 1 });
  show();
  expect(link("继续上次任务").getAttribute("href")).toBe("/papers/paper%3Aone?tab=reading&page=4");
  await screen.findByText("Original paper");
  expect(link("Original paper").getAttribute("href")).toBe("/papers/paper%3Aone?tab=reading");
  expect(screen.getByText("本地 PDF · 2025")).toBeTruthy();
});

test("latest workflow event wins even if an aborted older request later resolves", async () => {
  const old = deferred<WorkflowOverview>(), next = deferred<WorkflowOverview>();
  const oldFailure = deferred<WorkflowOverview>(), latest = deferred<WorkflowOverview>();
  vi.mocked(workflowOverview).mockReturnValueOnce(old.promise).mockReturnValueOnce(next.promise)
    .mockReturnValueOnce(oldFailure.promise).mockReturnValueOnce(latest.promise);
  const view = show();
  const oldSignal = vi.mocked(workflowOverview).mock.calls[0][0];
  act(() => { window.dispatchEvent(new Event("atlas:data-change")); });
  expect(oldSignal?.aborted).toBe(true);
  await act(async () => { next.resolve(overview(2, "Current task")); });
  expect(screen.getByText("Current task")).toBeTruthy();
  await act(async () => { old.resolve(overview(99, "Obsolete task")); });
  expect(screen.queryByText("Obsolete task")).toBeNull();
  expect(screen.getByText(/优先显示与当前研究相关的事项/)).toBeTruthy();
  act(() => { window.dispatchEvent(new Event("atlas:data-change")); window.dispatchEvent(new Event("atlas:data-change")); });
  await act(async () => { latest.resolve(overview(3, "Latest successful task")); });
  await act(async () => { oldFailure.reject(new Error("Stale failed overview")); });
  expect(screen.getByText("Latest successful task")).toBeTruthy();
  expect(screen.getByText(/优先显示与当前研究相关的事项/)).toBeTruthy();
  expect(screen.queryByText(/Stale failed overview/)).toBeNull();
  const currentSignal = vi.mocked(workflowOverview).mock.calls[3][0];
  view.unmount(); expect(currentSignal?.aborted).toBe(true);
  act(() => { window.dispatchEvent(new Event("atlas:data-change")); });
  expect(workflowOverview).toHaveBeenCalledTimes(4);
});

test("stale success cannot clear the latest workflow error and local retry recovers", async () => {
  const old = deferred<WorkflowOverview>();
  vi.mocked(workflowOverview).mockReturnValueOnce(old.promise).mockRejectedValueOnce(new Error("Latest overview offline"))
    .mockResolvedValueOnce(overview(1, "Recovered task")).mockRejectedValueOnce(new Error("Fresh refresh offline"));
  show();
  await act(async () => { window.dispatchEvent(new Event("atlas:data-change")); });
  expect(screen.getByText(/Latest overview offline/)).toBeTruthy();
  await act(async () => { old.resolve(overview(42, "Old successful task")); });
  expect(screen.getByText(/Latest overview offline/)).toBeTruthy();
  expect(screen.queryByText("Old successful task")).toBeNull();
  fireEvent.click(screen.getByText("重试摘要"));
  expect(await screen.findByText("Recovered task")).toBeTruthy();
  expect(screen.queryByText(/Latest overview offline/)).toBeNull();
  expect(screen.getByText(/优先显示与当前研究相关的事项/)).toBeTruthy();
  await act(async () => { window.dispatchEvent(new Event("atlas:data-change")); });
  expect(screen.getByText(/Fresh refresh offline/)).toBeTruthy();
  expect(screen.queryByText("Recovered task")).toBeNull();
  expect(screen.queryByText(/优先显示与当前研究相关的事项/)).toBeNull();
});

test("a recent-paper failure can retry without hiding the task summary", async () => {
  vi.mocked(listPapers).mockRejectedValueOnce(new Error("Paper list offline"))
    .mockResolvedValueOnce({ items: [{ uid: "retry", title: "Recovered paper" }], total: 1 });
  vi.mocked(workflowOverview).mockResolvedValue(overview(1, "Available task"));
  show();
  expect(await screen.findByText(/Paper list offline/)).toBeTruthy();
  expect(screen.getByText("Available task")).toBeTruthy();
  fireEvent.click(screen.getByText("重试论文列表"));
  expect(await screen.findByText("Recovered paper")).toBeTruthy();
  expect(screen.queryByText(/Paper list offline/)).toBeNull();
  expect(listPapers).toHaveBeenCalledTimes(2);
});


test('current-space next actions omit completed, other-space and duplicate historical entries',async()=>{
 vi.mocked(useRecentProjects).mockReturnValue({items:[{id:'p1',title:'当前课题',research_question:'如何控制误差？'}],loading:false,error:'',retry:vi.fn()} as any);
 const item=overview(99,'继续学习').next[0];
 vi.mocked(workflowOverview).mockResolvedValue({...overview(99),next:[{...item,id:'a',project_id:'p1'},{...item,id:'duplicate',project_id:'p1'},{...item,id:'old',title:'已完成的历史',project_id:'p1',status:'completed'},{...item,id:'else',title:'其他空间任务',project_id:'p10'}]});
 show();await screen.findByText('继续学习');
 expect(screen.getAllByText('继续学习')).toHaveLength(1);expect(screen.queryByText('已完成的历史')).toBeNull();expect(screen.queryByText('其他空间任务')).toBeNull();
 expect(link('进入当前研究图谱').getAttribute('href')).toBe('/research/p1?view=graph');expect(screen.getAllByText('如何控制误差？')).toHaveLength(2);
});
