import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, test, vi } from "vitest";
import { searchPapers, type PaperSearchResponse } from "../api/search";
import PaperSearchPanel from "../components/PaperSearchPanel";

vi.mock("../api/search", () => ({ searchPapers: vi.fn() }));

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return { promise, resolve };
}

function result(title: string): PaperSearchResponse {
  return { mode: "keyword", items: [{ uid: title, title, score: 1, snippet: `${title} snippet`, hit_reason: "标题匹配" }] };
}

function submit(value: string) {
  const input = screen.getByRole("searchbox", { name: "论文检索关键词" });
  fireEvent.change(input, { target: { value } });
  fireEvent.keyDown(input, { key: "Enter", code: "Enter", keyCode: 13 });
  fireEvent.keyUp(input, { key: "Enter", code: "Enter", keyCode: 13 });
}

beforeEach(() => { vi.resetAllMocks(); });

test("results show exact source text and page links while older results remain usable", async () => {
  const quote = "原文片段 <script>not executable</script>\nThe measured value is 5 ms.";
  vi.mocked(searchPapers).mockResolvedValue({ mode: "hybrid", items: [
    { uid: "paper:one", title: "Source paper", score: 1, snippet: "Old abstract snippet", hit_reason: "原文片段匹配：Results", passage_id: "document-4", document_id: "document", document_version: "sha256:version", page: 4, quote },
    { uid: "p2", title: "Unknown page", score: 0.5, snippet: "Another source", passage_id: "document-5", page: null },
    { uid: "p3", title: "Legacy result", score: 0.1, snippet: "Available abstract", hit_reason: "摘要匹配" },
  ] });
  render(<MemoryRouter><PaperSearchPanel /></MemoryRouter>);
  submit(" measured ");
  expect(await screen.findByText("Source paper")).toBeTruthy();
  expect(screen.getByText(/原文片段 <script>/).textContent).toBe(quote);
  expect(screen.queryByText("Old abstract snippet")).toBeNull();
  expect(screen.getByText("第 4 页")).toBeTruthy();
  expect(screen.getByText("页码未记录")).toBeTruthy();
  expect(screen.getByText("Available abstract")).toBeTruthy();
  expect(screen.getByText(/混合检索 · 显示 3 篇论文/)).toBeTruthy();
  const links = screen.getAllByRole("link", { name: "查看原文" });
  expect(links).toHaveLength(2);
  const url = new URL(links[0].getAttribute("href")!, window.location.origin);
  expect(url.pathname).toBe("/papers/paper%3Aone");
  expect(Object.fromEntries(url.searchParams)).toEqual({ tab: "reading", focus: "document-4", panel: "evidence", ref: "passage:document-4", page: "4" });
  expect(vi.mocked(searchPapers).mock.calls[0][0]).toBe("measured");
});

test("late responses cannot replace the newest search or end its loading state", async () => {
  const old = deferred<PaperSearchResponse>(), next = deferred<PaperSearchResponse>();
  vi.mocked(searchPapers).mockReturnValueOnce(old.promise).mockReturnValueOnce(next.promise);
  render(<MemoryRouter><PaperSearchPanel /></MemoryRouter>);
  submit("old query");
  expect(screen.getByRole("status").textContent).toContain("old query");
  const oldSignal = vi.mocked(searchPapers).mock.calls[0][2];
  submit("new query");
  expect(oldSignal?.aborted).toBe(true);
  await act(async () => { old.resolve(result("Old response")); });
  expect(screen.queryByText("Old response")).toBeNull();
  expect(screen.getByRole("status").textContent).toContain("new query");
  await act(async () => { next.resolve(result("New response")); });
  expect(screen.getByText("New response")).toBeTruthy();
  expect(screen.queryByRole("status")).toBeNull();
});

test("empty input clears pending results and unmount cancels active requests", async () => {
  const old = deferred<PaperSearchResponse>(), next = deferred<PaperSearchResponse>();
  vi.mocked(searchPapers).mockReturnValueOnce(old.promise).mockReturnValueOnce(next.promise);
  const view = render(<MemoryRouter><PaperSearchPanel /></MemoryRouter>);
  submit("   ");
  expect(searchPapers).not.toHaveBeenCalled();
  expect(screen.getByText("输入关键词并搜索，可查看匹配片段及其原文位置。")).toBeTruthy();
  submit("pending");
  fireEvent.change(screen.getByRole("searchbox", { name: "论文检索关键词" }), { target: { value: "" } });
  expect(vi.mocked(searchPapers).mock.calls[0][2]?.aborted).toBe(true);
  await act(async () => { old.resolve(result("Obsolete result")); });
  expect(screen.queryByText("Obsolete result")).toBeNull();
  expect(screen.queryByRole("status")).toBeNull();
  submit("another");
  const signal = vi.mocked(searchPapers).mock.calls[1][2];
  view.unmount();
  expect(signal?.aborted).toBe(true);
  await act(async () => { next.resolve(result("Unmounted result")); });
});

test("search failures can be retried and an empty response has an explicit state", async () => {
  vi.mocked(searchPapers).mockRejectedValueOnce(new Error("Search offline")).mockResolvedValueOnce({ mode: "keyword", items: [] });
  render(<MemoryRouter><PaperSearchPanel /></MemoryRouter>);
  submit("missing");
  expect(await screen.findByText("论文检索失败")).toBeTruthy();
  expect(screen.getByText("Search offline")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "重试检索" }));
  expect(await screen.findByText("没有找到与“missing”相关的资料，请尝试其他关键词。")).toBeTruthy();
  expect(screen.getByText(/本地关键词检索/)).toBeTruthy();
  expect(screen.queryByText("Search offline")).toBeNull();
  expect(searchPapers).toHaveBeenCalledTimes(2);
});
