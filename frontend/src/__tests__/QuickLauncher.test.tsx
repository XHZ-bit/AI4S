import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { beforeEach, expect, test, vi } from "vitest";
import QuickLauncher from "../components/QuickLauncher";
import Workspace from "../components/workspace/Workspace";
import {getUnifiedGraph} from "../api/unifiedGraph";
import { quickFindPapers } from "../api/quickFind";

vi.mock("../api/client", () => ({apiGet:vi.fn().mockResolvedValue({items:[]})}));
vi.mock("../api/unifiedGraph",()=>({getUnifiedGraph:vi.fn().mockResolvedValue({nodes:[]})}));
vi.mock("../api/quickFind", () => ({ quickFindPapers: vi.fn() }));
vi.mock("../api/assistant", () => ({
  getResources: vi.fn().mockResolvedValue({ items: [] }),
  getInsights: vi.fn().mockResolvedValue({ actions: [], coverage: {}, notice: "", input_fingerprint: "fixture" }),
  explainActions: vi.fn(),
}));

function Location() {
  const location = useLocation();
  return <output data-testid="location">{location.pathname}{location.search}</output>;
}
function renderLauncher() { return render(<MemoryRouter><QuickLauncher /><Location /></MemoryRouter>); }
function open() { fireEvent.click(screen.getByRole("button", { name: "快速查找与跳转" })); }
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return { promise, resolve };
}
beforeEach(() => { vi.mocked(quickFindPapers).mockReset(); });

test("global shortcut opens focused keyboard navigation without any background search", async () => {
  renderLauncher();
  fireEvent.keyDown(window, { key: "k", ctrlKey: true });
  const input = await screen.findByRole("combobox", { name: "查找论文或页面" });
  await waitFor(() => expect(document.activeElement).toBe(input));
  expect(quickFindPapers).not.toHaveBeenCalled();
  fireEvent.keyDown(input, { key: "ArrowDown" });
  expect(screen.getByRole("option", { selected: true }).textContent).toContain("开始 / 继续");
  fireEvent.keyDown(input, { key: "Enter" });
  expect(screen.getByTestId("location").textContent).toBe("/");
});

test("metadata results support keyboard opening and safely encode the paper ID", async () => {
  vi.mocked(quickFindPapers).mockResolvedValue({ total: 1, items: [{ uid: "paper:one", title: "Diffusion source", year: 2025 }] });
  renderLauncher(); open();
  const input = screen.getByRole("combobox");
  fireEvent.change(input, { target: { value: "  diffusion  " } });
  expect(await screen.findByText("Diffusion source")).toBeTruthy();
  expect(vi.mocked(quickFindPapers).mock.calls[0][0]).toBe("diffusion");
  const active = input.getAttribute("aria-activedescendant");
  expect(document.getElementById(active!)?.textContent).toContain("Diffusion source");
  fireEvent.keyDown(input, { key: "Enter", keyCode: 229 });
  expect(screen.getByTestId("location").textContent).toBe("/");
  fireEvent.keyDown(input, { key: "Enter" });
  expect(screen.getByTestId("location").textContent).toBe("/papers/paper%3Aone?tab=reading");
});

test("query changes cancel work and ignore old responses even when a transport ignores abort", async () => {
  const old = deferred<{ total: number; items: { uid: string; title: string }[] }>();
  const next = deferred<{ total: number; items: { uid: string; title: string }[] }>();
  vi.mocked(quickFindPapers).mockReturnValueOnce(old.promise).mockReturnValueOnce(next.promise);
  renderLauncher(); open();
  const input = screen.getByRole("combobox");
  fireEvent.change(input, { target: { value: "old" } });
  await waitFor(() => expect(quickFindPapers).toHaveBeenCalledTimes(1));
  const signal = vi.mocked(quickFindPapers).mock.calls[0][1];
  fireEvent.change(input, { target: { value: "new" } });
  expect(signal?.aborted).toBe(true);
  await waitFor(() => expect(quickFindPapers).toHaveBeenCalledTimes(2));
  await act(async () => next.resolve({ total: 1, items: [{ uid: "n", title: "Current paper" }] }));
  await act(async () => old.resolve({ total: 1, items: [{ uid: "o", title: "Wrong old paper" }] }));
  expect(screen.getByText("Current paper")).toBeTruthy();
  expect(screen.queryByText("Wrong old paper")).toBeNull();
});

test("failure can retry; escape cancels pending requests and restores trigger focus", async () => {
  vi.mocked(quickFindPapers).mockRejectedValueOnce(new Error("Offline fixture"))
    .mockResolvedValueOnce({ total: 0, items: [] });
  renderLauncher(); open();
  const input = screen.getByRole("combobox");
  fireEvent.change(input, { target: { value: "missing" } });
  expect(await screen.findByText("Offline fixture")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "重试查找" }));
  expect(await screen.findByText("没有匹配记录，可调整关键词。")).toBeTruthy();
  fireEvent.keyDown(input, { key: "Escape" });
  await waitFor(() => expect(screen.queryByRole("combobox")).toBeNull());
  // JSDOM does not focus a button after fireEvent.click, so reopen with an
  // explicit focused trigger as a real keyboard user would.
  const trigger = screen.getByRole("button", { name: "快速查找与跳转" });
  act(() => trigger.focus()); open();
  const pending = deferred<{ total: number; items: [] }>();
  vi.mocked(quickFindPapers).mockReturnValueOnce(pending.promise);
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "pending" } });
  await waitFor(() => expect(quickFindPapers).toHaveBeenCalledTimes(3));
  const signal = vi.mocked(quickFindPapers).mock.calls[2][1];
  fireEvent.keyDown(screen.getByRole("combobox"), { key: "Escape" });
  expect(signal?.aborted).toBe(true);
  await waitFor(() => expect(document.activeElement).toBe(trigger));
});

test("global and workspace shortcuts open only their own dialog", async () => {
  render(<MemoryRouter><QuickLauncher /><Workspace scope="paper" id="p"><p>Reading fixture</p></Workspace></MemoryRouter>);
  fireEvent.keyDown(window, { key: "k", ctrlKey: true });
  expect(await screen.findByRole("dialog", { name: "快速查找与跳转" })).toBeTruthy();
  expect(screen.queryByRole("dialog", { name: "在当前工作空间中查找" })).toBeNull();
  fireEvent.keyDown(screen.getByRole("combobox"), { key: "Escape" });
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  fireEvent.keyDown(window, { key: "K", ctrlKey: true, shiftKey: true });
  // Ant Design uses the same synthetic "test-id" label for every modal under
  // NODE_ENV=test. Check the visible dialog's own title, not that shared ID.
  const context = await screen.findByRole("dialog");
  expect(within(context).getByText("在当前工作空间中查找")).toBeTruthy();
  expect(screen.getAllByRole("dialog")).toHaveLength(1);
  await waitFor(() => expect(document.activeElement).toBe(screen.getByPlaceholderText("查找资源、缺口和下一步…")));
  fireEvent.keyDown(window, { key: "k", ctrlKey: true });
  await waitFor(() => {
    expect(screen.getAllByRole("dialog")).toHaveLength(1);
    expect(within(screen.getByRole("dialog")).getByText("快速查找与跳转")).toBeTruthy();
  });
  await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("combobox")));
  fireEvent.keyDown(window, { key: "K", ctrlKey: true, shiftKey: true });
  await waitFor(() => expect(document.activeElement).toBe(screen.getByPlaceholderText("查找资源、缺口和下一步…")));
});


test("knowledge search names its space and opens the exact unified node",async()=>{
 vi.mocked(quickFindPapers).mockResolvedValue({items:[],total:0});
 vi.mocked(getUnifiedGraph).mockResolvedValueOnce({nodes:[{id:'node-1',label:'状态门控知识',source_title:'论文 A',scope:{kind:'project',project_id:'space-1',id:'space-1',title:'协同方法'}}]} as any);
 renderLauncher();open();fireEvent.change(screen.getByRole('combobox'),{target:{value:'状态门控'}});
 fireEvent.click(await screen.findByText('状态门控知识'));
 expect(screen.getByTestId('location').textContent).toBe('/research/space-1?view=graph&node=node-1');
 expect(getUnifiedGraph).toHaveBeenCalledWith({q:'状态门控',limit:8},expect.any(AbortSignal));
});
