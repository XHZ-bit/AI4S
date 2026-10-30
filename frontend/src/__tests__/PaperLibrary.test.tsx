import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { beforeEach, test, vi } from "vitest";
import { listLibraryPapers, updateLibraryPaper, type LibraryPage, type LibraryPaper } from "../api/library";
import PaperLibrary from "../components/PaperLibrary";

vi.mock("../api/library", () => ({ listLibraryPapers: vi.fn(), updateLibraryPaper: vi.fn() }));

const paper = (changes: Partial<LibraryPaper> = {}): LibraryPaper => ({ uid: "p1", title: "First paper", abstract: "", authors: [], year: 2025,
  source: "upload", parse_status: "parsed", created_at: "", starred: false, read_later: false, library_updated_at: null, ...changes });

function renderLibrary(path = "/manage") { return render(<MemoryRouter initialEntries={[path]}><PaperLibrary /></MemoryRouter>); }
beforeEach(() => { vi.resetAllMocks(); vi.mocked(listLibraryPapers).mockResolvedValue({ items: [paper()], total: 45 }); });

test("library views preserve server query and parse filters while resetting pagination", async () => {
  renderLibrary("/manage?q=diffusion&status=parsed&page=2");
  await screen.findByText("First paper");
  expect(listLibraryPapers).toHaveBeenLastCalledWith({ filter: "all", q: "diffusion", parse_status: "parsed", limit: 20, offset: 20 }, expect.any(AbortSignal));
  fireEvent.click(screen.getByRole("radio", { name: "收藏" }));
  await waitFor(() => expect(listLibraryPapers).toHaveBeenLastCalledWith(expect.objectContaining({ filter: "starred", q: "diffusion", parse_status: "parsed", offset: 0 }), expect.any(AbortSignal)));
  await screen.findByText("First paper");
  const input = screen.getByRole("searchbox", { name: "论文库关键词" });
  fireEvent.change(input, { target: { value: " robot " } });
  fireEvent.keyDown(input, { key: "Enter", code: "Enter" }); fireEvent.keyUp(input, { key: "Enter", code: "Enter" });
  await waitFor(() => expect(listLibraryPapers).toHaveBeenLastCalledWith(expect.objectContaining({ filter: "starred", q: "robot", parse_status: "parsed", offset: 0 }), expect.any(AbortSignal)));
  await screen.findByText("First paper");
  fireEvent.click(screen.getByTitle("2"));
  await waitFor(() => expect(listLibraryPapers).toHaveBeenLastCalledWith(expect.objectContaining({ filter: "starred", q: "robot", parse_status: "parsed", offset: 20 }), expect.any(AbortSignal)));
});

test("starred and read later are independent persisted flags", async () => {
  let current = paper();
  vi.mocked(listLibraryPapers).mockImplementation(async () => ({ items: [current], total: 1 }));
  vi.mocked(updateLibraryPaper).mockImplementation(async (_, changes) => { current = { ...current, ...changes }; return current; });
  renderLibrary();
  fireEvent.click(await screen.findByLabelText("收藏：First paper"));
  expect((await screen.findByLabelText("取消收藏：First paper")).getAttribute("aria-pressed")).toBe("true");
  fireEvent.click(screen.getByLabelText("加入稍后阅读：First paper"));
  expect((await screen.findByLabelText("移出稍后阅读：First paper")).getAttribute("aria-pressed")).toBe("true");
  expect(screen.getByLabelText("取消收藏：First paper").getAttribute("aria-pressed")).toBe("true");
  expect(updateLibraryPaper).toHaveBeenNthCalledWith(1, "p1", { starred: true });
  expect(updateLibraryPaper).toHaveBeenNthCalledWith(2, "p1", { read_later: true });
});

test("a failed marker update keeps the previous state and permits another attempt", async () => {
  vi.mocked(updateLibraryPaper).mockRejectedValue(new Error("Save offline"));
  renderLibrary();
  fireEvent.click(await screen.findByLabelText("收藏：First paper"));
  expect(await screen.findByText(/Save offline/)).toBeTruthy();
  expect(screen.getByLabelText("收藏：First paper").getAttribute("aria-pressed")).toBe("false");
  expect((screen.getByLabelText("收藏：First paper") as HTMLButtonElement).disabled).toBe(false);
});

test("removing the last item of a filtered last page returns to a valid page", async () => {
  let removed = false;
  vi.mocked(listLibraryPapers).mockImplementation(async options => removed
    ? { items: options?.offset ? [] : [paper({ title: "Earlier paper", read_later: true })], total: 20 }
    : { items: [paper({ read_later: true })], total: 21 });
  vi.mocked(updateLibraryPaper).mockImplementation(async () => { removed = true; return paper(); });
  renderLibrary("/manage?filter=read_later&page=2");
  fireEvent.click(await screen.findByLabelText("移出稍后阅读：First paper"));
  expect(await screen.findByText("Earlier paper")).toBeTruthy();
  expect(listLibraryPapers).toHaveBeenLastCalledWith(expect.objectContaining({ filter: "read_later", offset: 0 }), expect.any(AbortSignal));
});

test("a response from an old library view cannot overwrite the latest view", async () => {
  let resolveOld!: (page: LibraryPage) => void;
  vi.mocked(listLibraryPapers).mockReturnValueOnce(new Promise(resolve => { resolveOld = resolve; }))
    .mockResolvedValue({ items: [paper({ title: "Starred paper", starred: true })], total: 1 });
  renderLibrary();
  const signal = vi.mocked(listLibraryPapers).mock.calls[0][1];
  fireEvent.click(screen.getByRole("radio", { name: "收藏" }));
  expect(await screen.findByText("Starred paper")).toBeTruthy();
  expect(signal?.aborted).toBe(true);
  await act(async () => { resolveOld({ items: [paper({ title: "Old paper" })], total: 1 }); });
  expect(screen.queryByText("Old paper")).toBeNull();
  expect(screen.getByText("Starred paper")).toBeTruthy();
});

test("filter feedback and clearing preserve unrelated URL state and reset server pagination", async () => {
  function Location() { return <output aria-label="当前库地址">{useLocation().search}</output>; }
  render(<MemoryRouter initialEntries={["/manage?filter=read_later&q=robot&status=parsed&page=2&context=keep"]}><PaperLibrary /><Location /></MemoryRouter>);
  await screen.findByText("First paper");
  expect(screen.getByText(/关键词“robot”/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "清空筛选" }));
  await waitFor(() => expect(listLibraryPapers).toHaveBeenLastCalledWith({ filter: "all", q: "", parse_status: undefined, limit: 20, offset: 0 }, expect.any(AbortSignal)));
  expect((screen.getByRole("searchbox", { name: "论文库关键词" }) as HTMLInputElement).value).toBe("");
  expect(screen.getByLabelText("当前库地址").textContent).toBe("?page=1&context=keep");
});

test("desktop papers show Chinese source and parse state with a direct reading action", async () => {
  renderLibrary();
  await screen.findByText("First paper");
  expect(screen.getByText("上传 PDF")).toBeTruthy();
  expect(screen.getByText("已解析")).toBeTruthy();
  expect(screen.getByRole("link", { name: "阅读原文：First paper" }).getAttribute("href")).toBe("/papers/p1?tab=reading");
  expect(screen.queryByText("parsed")).toBeNull();
  expect(screen.queryByText("upload")).toBeNull();
});

test("switching to mobile renders one accessible card and preserves selection and markers", async () => {
  let changed!: (event: MediaQueryListEvent) => void;
  const originalMedia = window.matchMedia;
  const media = { matches: false, media: "(max-width: 767px)", onchange: null,
    addEventListener: (_type: string, listener: (event: MediaQueryListEvent) => void) => { changed = listener; },
    removeEventListener: vi.fn(), addListener: vi.fn(), removeListener: vi.fn(), dispatchEvent: () => false };
  const spy = vi.spyOn(window, "matchMedia").mockImplementation(query => query === media.media ? media as unknown as MediaQueryList : originalMedia(query));
  try {
    renderLibrary();
    const title = await screen.findByText("First paper");
    const row = title.closest("tr")!;
    fireEvent.click(row.querySelector('input[type="checkbox"]')!);
    await act(async () => changed({ matches: true } as MediaQueryListEvent));
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.getAllByRole("article", { name: "论文：First paper" })).toHaveLength(1);
    expect(screen.getAllByLabelText("收藏：First paper")).toHaveLength(1);
    expect(screen.getAllByLabelText("加入稍后阅读：First paper")).toHaveLength(1);
    expect((screen.getByRole("checkbox", { name: "选择论文：First paper" }) as HTMLInputElement).checked).toBe(true);
    expect((screen.getByRole("button", { name: "批量抽取" }) as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(screen.getByTitle("2"));
    await waitFor(() => expect(listLibraryPapers).toHaveBeenLastCalledWith(expect.objectContaining({ offset: 20 }), expect.any(AbortSignal)));
  } finally { spy.mockRestore(); }
});
