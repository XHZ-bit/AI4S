import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { vi } from "vitest";
import PaperReader from "../components/workspace/PaperReader";
import { getResources, type Resource } from "../api/assistant";
import { getReadingPosition, saveReadingPosition, type PositionResponse } from "../api/readingPosition";

vi.mock("../api/assistant", () => ({ getResources: vi.fn() }));
vi.mock("../api/readingPosition", () => ({ getReadingPosition: vi.fn(), saveReadingPosition: vi.fn() }));
vi.mock("../components/workspace/PdfReader", () => ({ default: ({ resource, initialPage, onPageChange }: any) => <div data-testid="reader">{resource.title}: page {initialPage}{[2, 3, 4].map(page => <button key={page} onClick={() => onPageChange(page)}>page {page}</button>)}</div> }));
const resource = (uid = "one", id = "document-one"): Resource => ({ id, document_id: id, paper_uid: uid, kind: "pdf", title: uid, origin: "literature", version: "hash", url: "/file", passages: [] });
const position = (page: number): PositionResponse => ({ position: { paper_uid: "one", document_id: "document-one", document_version: "sha256:hash", page, page_count: 4, updated_at: "now" } });
function Location() { return <output data-testid="url">{useLocation().search}</output>; }
function view(uid = "one", url = "/papers/one") { return <MemoryRouter initialEntries={[url]}><PaperReader uid={uid} /><Location /></MemoryRouter>; }
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(getResources).mockResolvedValue({ contract_version: "assistant-v1", input_fingerprint: "f", items: [resource()] });
  vi.mocked(getReadingPosition).mockResolvedValue({ position: null });
  vi.mocked(saveReadingPosition).mockImplementation(async (_, __, page) => position(page));
});

test("restores the exact document's saved page without writing or changing other URL context", async () => {
  vi.mocked(getReadingPosition).mockResolvedValue(position(3));
  render(view("one", "/papers/one?tab=reading&panel=evidence"));
  await screen.findByText("one: page 3");
  expect(screen.getByTestId("url").textContent).toContain("panel=evidence");
  expect(getReadingPosition).toHaveBeenCalledWith("one", "document-one", expect.any(AbortSignal));
  expect(saveReadingPosition).not.toHaveBeenCalled();
});

test("an explicit source link to page one wins over a saved page", async () => {
  vi.mocked(getReadingPosition).mockResolvedValue(position(3));
  render(view("one", "/papers/one?page=1&focus=source"));
  await screen.findByText("one: page 1");
  expect(screen.getByTestId("url").textContent).toContain("focus=source");
  expect(saveReadingPosition).not.toHaveBeenCalled();
});

test("serializes slow writes and coalesces later navigation to the latest page", async () => {
  let finish!: (value: PositionResponse) => void;
  vi.mocked(saveReadingPosition).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  render(view()); await screen.findByTestId("reader");
  fireEvent.click(screen.getByText("page 2", { exact: true }));
  fireEvent.click(screen.getByText("page 3", { exact: true }));
  fireEvent.click(screen.getByText("page 4", { exact: true }));
  expect(saveReadingPosition).toHaveBeenCalledTimes(1);
  await act(async () => finish(position(2)));
  await screen.findByText("阅读位置已保存：第 4 页。");
  expect(vi.mocked(saveReadingPosition).mock.calls.map(call => call[2])).toEqual([2, 4]);
  expect(screen.getByTestId("url").textContent).toContain("page=4");
});

test("a failed position service does not block reading and only retries the failed save", async () => {
  vi.mocked(getReadingPosition).mockRejectedValueOnce(new Error("offline"));
  vi.mocked(saveReadingPosition).mockRejectedValueOnce(new Error("offline"));
  render(view()); await screen.findByText("one: page 1");
  expect(screen.getByText(/无法读取上次阅读位置/)).toBeTruthy();
  fireEvent.click(screen.getByText("page 2", { exact: true }));
  await screen.findByText(/阅读位置保存失败/);
  fireEvent.click(screen.getByText("重试保存位置"));
  await screen.findByText("阅读位置已保存：第 2 页。");
  expect(saveReadingPosition).toHaveBeenCalledTimes(2);
  expect(getReadingPosition).toHaveBeenCalledTimes(1);
});

test("switching papers removes the previous document and aborts its pending writes", async () => {
  vi.mocked(saveReadingPosition).mockImplementationOnce(() => new Promise(() => {}));
  const screenView = render(view()); await screen.findByTestId("reader");
  fireEvent.click(screen.getByText("page 2", { exact: true }));
  const previousSignal = vi.mocked(saveReadingPosition).mock.calls[0][3];
  let finish!: (value: Awaited<ReturnType<typeof getResources>>) => void;
  vi.mocked(getResources).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  screenView.rerender(view("two"));
  expect(previousSignal?.aborted).toBe(true);
  expect(screen.queryByTestId("reader")).toBeNull();
  await act(async () => finish({ contract_version: "assistant-v1", input_fingerprint: "f2", items: [resource("two", "document-two")] }));
  await waitFor(() => expect(getReadingPosition).toHaveBeenLastCalledWith("two", "document-two", expect.any(AbortSignal)));
  await screen.findByTestId("reader");
  expect(screen.queryByText(/one: page/)).toBeNull();
});

test("an explicit historical document link retains document and page 14 instead of substituting the latest version", async () => {
  const latest = { ...resource("latest", "latest-doc"), paper_uid: "one" };
  const historical = { ...resource("historical", "historical-doc"), paper_uid: "one" };
  vi.mocked(getResources).mockResolvedValue({ contract_version: "assistant-v1", input_fingerprint: "f", items: [latest, historical] });
  render(view("one", "/papers/one?document_id=historical-doc&page=14&returnTo=%2Fresearch%2Fspace"));
  await screen.findByText("historical: page 14");
  expect(getReadingPosition).toHaveBeenCalledWith("one", "historical-doc", expect.any(AbortSignal));
  expect(saveReadingPosition).not.toHaveBeenCalled();
  expect(screen.getByTestId("url").textContent).toContain("document_id=historical-doc");
});

test("a missing explicit version offers current original as a deliberate action and does not silently select another version", async () => {
  render(view("one", "/papers/one?document_id=missing-doc&page=14"));
  await screen.findByText("链接中的文档版本暂不可用");
  expect(screen.queryByTestId("reader")).toBeNull();
  expect(getReadingPosition).not.toHaveBeenCalled();
  expect(saveReadingPosition).not.toHaveBeenCalled();
  expect(screen.getByRole("link", { name: "打开当前保存的 PDF" }).getAttribute("href")).toBe("/api/papers/one/file");
});
