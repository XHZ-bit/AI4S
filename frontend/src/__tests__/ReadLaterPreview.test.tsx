import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, test, vi } from "vitest";
import { listLibraryPapers, type LibraryPage, type LibraryPaper } from "../api/library";
import ReadLaterPreview from "../components/ReadLaterPreview";

vi.mock("../api/library", () => ({ listLibraryPapers: vi.fn() }));
const paper = (uid: string) => ({ uid, title: `Read ${uid}` } as LibraryPaper);
const show = () => render(<MemoryRouter><ReadLaterPreview /></MemoryRouter>);
beforeEach(() => { vi.resetAllMocks(); });

test("an empty read later list does not add a home section", async () => {
  vi.mocked(listLibraryPapers).mockResolvedValue({ items: [], total: 0 });
  show();
  await act(async () => {});
  expect(listLibraryPapers).toHaveBeenCalledWith({ filter: "read_later", limit: 3 }, expect.any(AbortSignal));
  expect(screen.queryByRole("region", { name: "稍后阅读预览" })).toBeNull();
});

test("home shows at most three saved papers with reading and full-list links", async () => {
  vi.mocked(listLibraryPapers).mockResolvedValue({ items: ["1", "2", "3", "4"].map(paper), total: 4 });
  show();
  expect(await screen.findByText("Read 1")).toBeTruthy();
  expect(screen.getAllByRole("link", { name: "阅读原文 ↗" })).toHaveLength(3);
  expect(screen.queryByText("Read 4")).toBeNull();
  expect(screen.getByRole("link", { name: "打开稍后阅读 →" }).getAttribute("href")).toBe("/manage?filter=read_later");
  expect(screen.getAllByRole("link", { name: "阅读原文 ↗" })[0].getAttribute("href")).toBe("/papers/1?tab=reading");
});

test("read later failures are local to the preview and can be retried", async () => {
  vi.mocked(listLibraryPapers).mockRejectedValueOnce(new Error("Offline")).mockResolvedValueOnce({ items: [paper("retry")], total: 1 });
  show();
  fireEvent.click(await screen.findByRole("button", { name: "重试稍后阅读" }));
  expect(await screen.findByText("Read retry")).toBeTruthy();
  expect(screen.queryByText("稍后阅读暂不可用")).toBeNull();
});

test("a library update invalidates any earlier pending preview request", async () => {
  let old!: (value: LibraryPage) => void;
  vi.mocked(listLibraryPapers).mockReturnValueOnce(new Promise(resolve => { old = resolve; }))
    .mockResolvedValueOnce({ items: [paper("latest")], total: 1 });
  const view = show();
  const first = vi.mocked(listLibraryPapers).mock.calls[0][1];
  act(() => { window.dispatchEvent(new CustomEvent("atlas:data-change", { detail: { path: "/api/library/papers/1" } })); });
  expect(await screen.findByText("Read latest")).toBeTruthy();
  expect(first?.aborted).toBe(true);
  await act(async () => { old({ items: [paper("old")], total: 1 }); });
  expect(screen.queryByText("Read old")).toBeNull();
  const current = vi.mocked(listLibraryPapers).mock.calls[1][1];
  view.unmount();
  await waitFor(() => expect(current?.aborted).toBe(true));
});
