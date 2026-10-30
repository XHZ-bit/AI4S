import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, test, vi } from "vitest";
import { apiGet, apiPost } from "../api/client";
import { getUploadTask, reparsePaper, uploadPdf, type TaskStatus, type UploadReceipt } from "../api/papers";
import PdfUploadQueue from "../components/PdfUploadQueue";

vi.mock("../api/client", () => ({ apiGet: vi.fn(), apiPost:vi.fn() }));
vi.mock("../api/papers", () => ({ uploadPdf: vi.fn(), getUploadTask: vi.fn(), reparsePaper: vi.fn() }));
const file = (name: string, size = 10) => new File(["x".repeat(size)], name, { type: "application/pdf" });
const receipt = (task_id: number): UploadReceipt => ({ uid: `paper-${task_id}`, task_id, parse_status: "queued" });
const done = (id: number): TaskStatus<{ warnings?: unknown[] }> => ({ id, status: "done" });
function deferred<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>(accept => { resolve = accept; }); return { promise, resolve }; }
const changed = vi.fn();
function show(maxFileBytes: number | undefined = 100) { return render(<MemoryRouter><PdfUploadQueue maxFileBytes={maxFileBytes} onLibraryChange={changed} /></MemoryRouter>); }
async function add(...files: File[]) { await act(async () => { fireEvent.change(screen.getByLabelText("选择 PDF 文件"), { target: { files } }); }); }
beforeEach(() => {
  vi.resetAllMocks();
  vi.spyOn(document, "hidden", "get").mockReturnValue(false);
  vi.mocked(uploadPdf).mockImplementation(async () => receipt(vi.mocked(uploadPdf).mock.calls.length));
  vi.mocked(getUploadTask).mockImplementation(async id => done(id));
});
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); });

test("files wait for the preceding parse terminal state rather than just its upload receipt", async () => {
  vi.useFakeTimers();
  vi.mocked(getUploadTask).mockResolvedValueOnce({ id: 1, status: "running" }).mockResolvedValueOnce(done(1)).mockResolvedValueOnce(done(2));
  show(); await add(file("one.pdf"), file("two.pdf"));
  expect(uploadPdf).toHaveBeenCalledTimes(1);
  expect(screen.getByText("已保存 · 解析中")).toBeTruthy();
  expect(screen.getByText("打开已保存论文").getAttribute("href")).toBe("/papers/paper-1?tab=reading");
  await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
  expect(uploadPdf).toHaveBeenCalledTimes(2);
  expect(screen.getAllByText("解析完成")).toHaveLength(2);
  expect(changed).toHaveBeenCalledTimes(4);
});

test("invalid or oversized files never reach upload and do not block later valid files", async () => {
  show(20); await add(file("wrong.txt"), file("empty.pdf", 0), file("large.pdf", 21), file("valid.pdf"));
  expect(uploadPdf).toHaveBeenCalledTimes(1);
  expect(vi.mocked(uploadPdf).mock.calls[0][0].name).toBe("valid.pdf");
  expect(screen.getByText(/文件超过当前单份大小上限/)).toBeTruthy();
  expect(screen.getAllByText("请选择非空的 PDF 文件；此文件未提交。")).toHaveLength(2);
  expect(screen.getByText("解析完成")).toBeTruthy();
  expect(apiGet).not.toHaveBeenCalled();
});

test("parse failure advances the queue and only failed parsing is retried without resending its PDF", async () => {
  vi.mocked(getUploadTask).mockResolvedValueOnce({ id: 1, status: "failed", error: "Parse failed" }).mockResolvedValueOnce(done(2)).mockResolvedValueOnce(done(3));
  vi.mocked(reparsePaper).mockResolvedValue({ task_id: 3 });
  show(); await add(file("one.pdf"), file("two.pdf"));
  expect(screen.getByText(/原文已保存；解析失败/)).toBeTruthy();
  expect(uploadPdf).toHaveBeenCalledTimes(2);
  await act(async () => { fireEvent.click(screen.getByText("重试失败项")); });
  expect(reparsePaper).toHaveBeenCalledWith("paper-1", expect.any(AbortSignal));
  expect(uploadPdf).toHaveBeenCalledTimes(2);
  expect(screen.getAllByText("解析完成")).toHaveLength(2);
  expect(screen.getByText("查看任务 #3")).toBeTruthy();
});

test("429 pauses later uploads and never claims the first file was not saved", async () => {
  vi.mocked(uploadPdf).mockRejectedValueOnce(Object.assign(new Error("已有活动任务"), { status: 429 })).mockResolvedValueOnce(receipt(1)).mockResolvedValueOnce(receipt(2));
  show(); await add(file("one.pdf"), file("two.pdf"));
  expect(uploadPdf).toHaveBeenCalledTimes(1);
  expect(screen.getByText(/文件可能已保存：已有活动任务/)).toBeTruthy();
  fireEvent.click(screen.getByText("继续队列"));
  expect(uploadPdf).toHaveBeenCalledTimes(1);
  await act(async () => { fireEvent.click(screen.getByText("确认后重试此文件")); });
  expect(uploadPdf).toHaveBeenCalledTimes(3);
  expect(screen.getAllByText("解析完成")).toHaveLength(2);
});

test("lost task status pauses and resumes its known task before uploading the next file", async () => {
  vi.mocked(getUploadTask).mockRejectedValueOnce(new Error("Status offline")).mockResolvedValueOnce(done(1)).mockResolvedValueOnce(done(2));
  show(); await add(file("one.pdf"), file("two.pdf"));
  expect(uploadPdf).toHaveBeenCalledTimes(1);
  expect(screen.getByText(/恢复队列时将先查询此任务/)).toBeTruthy();
  expect(screen.getByText("查看任务 #1")).toBeTruthy();
  await act(async () => { fireEvent.click(screen.getByText("继续队列")); });
  expect(getUploadTask).toHaveBeenNthCalledWith(2, 1, expect.any(AbortSignal));
  expect(uploadPdf).toHaveBeenCalledTimes(2);
  expect(screen.getAllByText("解析完成")).toHaveLength(2);
});

test("hidden pages defer status polling and unmount aborts the active upload and future files", async () => {
  const visibility = vi.mocked(Object.getOwnPropertyDescriptor(document, "hidden")!.get!);
  visibility.mockReturnValue(true);
  const next = deferred<UploadReceipt>();
  vi.mocked(uploadPdf).mockResolvedValueOnce(receipt(1)).mockReturnValueOnce(next.promise);
  const view = show(); await add(file("one.pdf"), file("two.pdf"), file("three.pdf"));
  expect(getUploadTask).not.toHaveBeenCalled();
  expect(uploadPdf).toHaveBeenCalledTimes(1);
  await act(async () => { visibility.mockReturnValue(false); document.dispatchEvent(new Event("visibilitychange")); });
  expect(uploadPdf).toHaveBeenCalledTimes(2);
  const signal = vi.mocked(uploadPdf).mock.calls[1][1];
  view.unmount(); expect(signal?.aborted).toBe(true);
  await act(async () => { next.resolve(receipt(2)); });
  expect(uploadPdf).toHaveBeenCalledTimes(2);
});

test("pausing and cancelling a waiting item only changes the local queue", async () => {
  const first = deferred<UploadReceipt>();
  vi.mocked(uploadPdf).mockReturnValueOnce(first.promise);
  show(); await add(file("one.pdf"), file("two.pdf"), file("three.pdf"));
  fireEvent.click(screen.getByText("暂停后续"));
  const row = screen.getByText("two.pdf").closest("li")!;
  fireEvent.click(within(row).getByText("取消此待上传项"));
  await act(async () => { first.resolve(receipt(1)); });
  expect(uploadPdf).toHaveBeenCalledTimes(1);
  expect(screen.getByText("已从本地队列取消")).toBeTruthy();
  await act(async () => { fireEvent.click(screen.getByText("继续队列")); });
  expect(uploadPdf).toHaveBeenCalledTimes(2);
  expect(vi.mocked(uploadPdf).mock.calls[1][0].name).toBe("three.pdf");
});

test("the bounded queue reads actual limits once and does not repeat rejected uploads", async () => {
  vi.mocked(apiGet).mockResolvedValue({ limits: { pdf_max_bytes: 5 } });
  render(<MemoryRouter><PdfUploadQueue onLibraryChange={changed} /></MemoryRouter>);
  await add(...Array.from({ length: 22 }, (_, index) => file(`${index}.pdf`, 10)));
  expect(screen.getByText(/本地队列最多保留 20 份/)).toBeTruthy();
  expect(screen.getAllByText(/文件超过当前单份大小上限/)).toHaveLength(20);
  expect(apiGet).toHaveBeenCalledTimes(1);
  expect(uploadPdf).not.toHaveBeenCalled();
});

test("a saved 429 receipt is retained and resumed by parsing its UID without reuploading", async () => {
  vi.mocked(uploadPdf).mockRejectedValueOnce(Object.assign(new Error("原文已保存，尚未排入解析"), { status: 429, saved: true, uid: "saved-paper" }))
    .mockResolvedValueOnce(receipt(2));
  vi.mocked(reparsePaper).mockResolvedValue({ task_id: 1 });
  show(); await add(file("one.pdf"), file("two.pdf"));
  expect(screen.getByText("原文已保存 · 等待排队")).toBeTruthy();
  expect(screen.getByText("打开已保存论文").getAttribute("href")).toBe("/papers/saved-paper?tab=reading");
  expect(uploadPdf).toHaveBeenCalledTimes(1);
  await act(async () => { fireEvent.click(screen.getByText("继续队列")); });
  expect(reparsePaper).toHaveBeenCalledWith("saved-paper", expect.any(AbortSignal));
  expect(uploadPdf).toHaveBeenCalledTimes(2);
  expect(vi.mocked(uploadPdf).mock.calls[1][0].name).toBe("two.pdf");
  expect(screen.getAllByText("解析完成")).toHaveLength(2);
});

test("an unrecognized task state pauses rather than submitting a later PDF", async () => {
  vi.mocked(getUploadTask).mockResolvedValueOnce({ id: 1, status: "unknown" } as unknown as Awaited<ReturnType<typeof getUploadTask>>);
  show(); await add(file("one.pdf"), file("two.pdf"));
  expect(screen.getByText(/任务状态无法确认/)).toBeTruthy();
  expect(screen.getByText("查看任务 #1")).toBeTruthy();
  expect(uploadPdf).toHaveBeenCalledTimes(1);
});

test("the native file chooser and keyboard-activated upload button remain accessible", async () => {
  show();
  const chooser = screen.getByLabelText("选择 PDF 文件") as HTMLInputElement;
  const trigger = screen.getByRole("button", { name: "上传 PDF" });
  expect(chooser.type).toBe("file");
  expect(chooser.multiple).toBe(true);
  expect(chooser.tabIndex).toBe(0);
  expect(window.getComputedStyle(chooser).display).not.toBe("none");
  await act(async () => { chooser.focus(); });
  expect(document.activeElement).toBe(chooser);
  const click = vi.spyOn(chooser, "click").mockImplementation(() => {});
  // Native buttons receive a zero-detail click when activated by the keyboard.
  fireEvent.click(trigger, { detail: 0 });
  expect(trigger.tagName).toBe("BUTTON");
  expect(click).toHaveBeenCalledTimes(1);
  expect(uploadPdf).not.toHaveBeenCalled();
});

test("dropping files uses the same validation and sequential queue as choosing files", async () => {
  show();
  const zone = document.querySelector(".atlas-upload-dropzone")!;
  const transfer = { files: [file("wrong.txt"), file("dropped.pdf")], types: ["Files"], dropEffect: "none" };
  fireEvent.dragEnter(zone, { dataTransfer: transfer });
  expect(zone.classList.contains("is-dragging")).toBe(true);
  fireEvent.dragOver(zone, { dataTransfer: transfer });
  expect(transfer.dropEffect).toBe("copy");
  await act(async () => { fireEvent.drop(zone, { dataTransfer: transfer }); });
  expect(zone.classList.contains("is-dragging")).toBe(false);
  expect(uploadPdf).toHaveBeenCalledTimes(1);
  expect(vi.mocked(uploadPdf).mock.calls[0][0].name).toBe("dropped.pdf");
  expect(screen.getByText("请选择非空的 PDF 文件；此文件未提交。")).toBeTruthy();
  expect(screen.getByText("解析完成")).toBeTruthy();
  expect(screen.getByText("本地队列 2 份 · 解析完成 1 份")).toBeTruthy();
});


test("project upload confirms binding and opens the embedded reader",async()=>{
 vi.mocked(apiPost).mockResolvedValue({linked:true});
 render(<MemoryRouter><PdfUploadQueue projectId="project-a" maxFileBytes={100} onLibraryChange={changed}/></MemoryRouter>);
 await add(file("one.pdf"));
 expect(apiPost).toHaveBeenCalledWith("/api/workbench/projects/project-a/papers",{paper_uid:"paper-1"},expect.any(AbortSignal));
 expect(screen.getByText("已加入研究空间")).toBeTruthy();
 expect(screen.getByText("开始阅读").getAttribute("href")).toBe("/research/project-a?tab=reading&paper=paper-1");
});

test("binding failure can be retried without uploading the PDF again",async()=>{
 vi.mocked(apiPost).mockRejectedValueOnce(new Error("Offline")).mockResolvedValue({linked:true});
 render(<MemoryRouter><PdfUploadQueue projectId="project-a" maxFileBytes={100} onLibraryChange={changed}/></MemoryRouter>);
 await add(file("one.pdf"));
 expect(screen.getByText(/文件已保存，加入研究空间失败/)).toBeTruthy();
 await act(async()=>{fireEvent.click(screen.getByText("重试加入研究空间"))});
 expect(uploadPdf).toHaveBeenCalledTimes(1);expect(screen.getByText("已加入研究空间")).toBeTruthy();
 expect(screen.getByText("开始阅读").getAttribute("href")).toBe("/research/project-a?tab=reading&paper=paper-1");
});
