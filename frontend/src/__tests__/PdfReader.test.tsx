import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, test, vi } from "vitest";
import type { Resource } from "../api/assistant";
import PdfReader from "../components/workspace/PdfReader";

const pdf = vi.hoisted(() => ({ getDocument: vi.fn(), getPage: vi.fn() }));
vi.mock("pdfjs-dist", () => ({
  GlobalWorkerOptions: { workerSrc: "" },
  getDocument: pdf.getDocument,
  TextLayer: class { render() { return Promise.resolve(); } cancel() {} },
}));
vi.mock("pdfjs-dist/build/pdf.worker.min.mjs?url", () => ({ default: "/test-worker.mjs" }));

let resize: ((entries: ResizeObserverEntry[]) => void) | undefined;
const document = { numPages: 7, getPage: pdf.getPage, getOutline: vi.fn(), getDestination: vi.fn(), getPageIndex: vi.fn(), destroy: vi.fn() };
const resource: Resource = { id: "pdf-one", kind: "pdf", title: "Test PDF", url: "/api/files/test", version: "v1", origin: "original", passages: [] };

beforeEach(() => {
  document.numPages = 7;
  pdf.getDocument.mockReturnValue({ promise: Promise.resolve(document), destroy: vi.fn() });
  document.getOutline.mockResolvedValue(null);
  document.getDestination.mockResolvedValue(null);
  document.getPageIndex.mockResolvedValue(0);
  pdf.getPage.mockImplementation(async (page: number) => {
    if (!Number.isInteger(page) || page < 1 || page > document.numPages) throw new Error("Invalid page");
    return { getViewport: ({ scale }: { scale: number }) => ({ width: 612 * scale, height: 792 * scale }),
      render: () => ({ promise: Promise.resolve(), cancel: vi.fn() }), getTextContent: async () => ({ items: [] }), cleanup: vi.fn() };
  });
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({} as CanvasRenderingContext2D);
  vi.stubGlobal("ResizeObserver", class {
    constructor(private callback: (entries: ResizeObserverEntry[]) => void) {}
    observe(target: Element) { if (target.classList.contains("atlas-reader")) resize = this.callback; }
    disconnect() {} unobserve() {}
  });
});

test("a version mismatch shows one recoverable error without repeated reading advice", async () => {
  pdf.getDocument.mockReturnValue({ promise: Promise.reject(Object.assign(new Error("Unexpected response (409)"), { status: 409 })), destroy: vi.fn() });
  render(<PdfReader resource={{ ...resource, current_file_url: "/api/papers/current/file", passages: Array.from({ length: 100 }, (_, i) => ({ id: String(i), heading: "Method", text: `Saved original passage ${i}`, page: 14 })) }} initialPage={14} />);
  await screen.findByText("此文档版本的 PDF 无法核对");
  expect(screen.getAllByRole("alert")).toHaveLength(1);
  expect(screen.queryByText("阅读建议")).toBeNull();
  expect(screen.getByRole("link", { name: "打开当前保存的 PDF" }).getAttribute("href")).toBe("/api/papers/current/file");
  const fallback = screen.getByText("查看已解析文字（100 段）").closest("details");
  expect(fallback?.open).toBe(false);
});

test("a 21-page paper opens evidence page 14 without saving a different reading position", async () => {
  document.numPages = 21;
  const changed = vi.fn();
  render(<PdfReader resource={resource} initialPage={14} onPageChange={changed} />);
  await loaded();
  expect(screen.getByLabelText("PDF 页码")).toHaveValue("14");
  expect(screen.getByText("/ 21")).toBeTruthy();
  expect(window.document.querySelector('[data-pdf-page="14"] canvas')).toBeTruthy();
  expect(changed).not.toHaveBeenCalled();
});
afterEach(async () => {
  // Unmount before restoring canvas/observer mocks, then settle the reader's
  // lazy imports so one test cannot finish a render in the next test's globals.
  cleanup();
  await act(async () => { await vi.dynamicImportSettled(); });
  vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.clearAllMocks(); resize = undefined;
});

async function loaded() {
  await act(async () => { await vi.dynamicImportSettled(); });
  // Label queries avoid repeatedly computing every Ant Design button's CSS in
  // JSDOM. Actual roles/keyboard behavior remain asserted in their own tests.
  await waitFor(() => expect(screen.getByLabelText("PDF 页码")).toBeEnabled());
  await waitFor(() => expect(window.document.querySelector("canvas")?.style.width).toMatch(/^\d/));
}
async function resizeTo(width: number) {
  await act(async () => { resize?.([{ contentRect: { width } } as ResizeObserverEntry]); });
}
async function chooseZoom(label: string) {
  const input = screen.getByLabelText("PDF 缩放", {selector: 'input'});
  expect(input).toHaveAttribute('role', 'combobox');
  fireEvent.mouseDown(input);
  fireEvent.click(await screen.findByText(label, { selector: ".ant-select-item-option-content" }));
}

test("fixed zoom keeps its accurate label and scale through resizes until fit width is selected", async () => {
  render(<PdfReader resource={resource} />);
  await loaded();
  await resizeTo(330);
  await waitFor(() => expect(window.document.querySelector("canvas")?.style.width).toBe("306px"));
  await chooseZoom("100%");
  const selector = screen.getByLabelText("PDF 缩放", {selector: 'input'}).closest(".ant-select") as HTMLElement;
  expect(within(selector).getByTitle("100%")).toBeTruthy();
  await waitFor(() => expect(window.document.querySelector("canvas")?.style.width).toBe("612px"));
  await resizeTo(636);
  await resizeTo(942);
  expect(within(selector).getByTitle("100%")).toBeTruthy();
  expect(window.document.querySelector("canvas")?.style.width).toBe("612px");
  await chooseZoom("适应宽度");
  await waitFor(() => expect(window.document.querySelector("canvas")?.style.width).toBe("918px"));
  await resizeTo(330);
  await waitFor(() => expect(window.document.querySelector("canvas")?.style.width).toBe("306px"));
});

test("page controls wait for the PDF and accept keyboard page navigation", async () => {
  let resolve!: (value: typeof document) => void;
  pdf.getDocument.mockReturnValue({ promise: new Promise(done => { resolve = done; }), destroy: vi.fn() });
  const changed = vi.fn();
  render(<PdfReader resource={resource} initialPage={3} onPageChange={changed} />);
  const input = screen.getByLabelText("PDF 页码") as HTMLInputElement;
  expect(input).toHaveAttribute('role', 'spinbutton');
  expect(input.disabled).toBe(true);
  await act(async () => { resolve(document); });
  await loaded();
  await act(async () => { input.focus(); });
  fireEvent.keyDown(input, { key: "ArrowUp" });
  await waitFor(() => expect(input.value).toBe("4"));
  expect(changed).toHaveBeenLastCalledWith(4);
  fireEvent.keyDown(input, { key: "ArrowDown" });
  await waitFor(() => expect(input.value).toBe("3"));
  expect(changed).toHaveBeenLastCalledWith(3);
});

test("typed out-of-range and empty page values cannot request invalid PDF pages", async () => {
  const changed = vi.fn();
  render(<PdfReader resource={resource} initialPage={3} onPageChange={changed} />);
  await loaded();
  const input = screen.getByLabelText("PDF 页码") as HTMLInputElement;
  fireEvent.change(input, { target: { value: "999" } });
  fireEvent.blur(input);
  await waitFor(() => expect(input.value).toBe("7"));
  expect(changed).toHaveBeenLastCalledWith(7);
  fireEvent.change(input, { target: { value: "-4" } });
  fireEvent.blur(input);
  await waitFor(() => expect(input.value).toBe("1"));
  expect(changed).toHaveBeenLastCalledWith(1);
  fireEvent.change(input, { target: { value: "" } });
  fireEvent.blur(input);
  await waitFor(() => expect(input.value).toBe("1"));
  pdf.getPage.mock.calls.forEach(([page]) => { expect(Number.isInteger(page) && page >= 1 && page <= 7).toBe(true); });
});

test.each([[-4, 1], [Number.NaN, 1], [Number.POSITIVE_INFINITY, 1], [2.7, 2], [999, 7]])("invalid initial page %s is bounded to %s before rendering", async (initialPage, expected) => {
  render(<PdfReader resource={resource} initialPage={initialPage} />);
  await loaded();
  expect(screen.getByLabelText("PDF 页码")).toHaveValue(String(expected));
  pdf.getPage.mock.calls.forEach(([page]) => { expect(Number.isInteger(page) && page >= 1 && page <= 7).toBe(true); });
});

test("continuous reading keeps all page positions but renders only nearby pages", async () => {
  const observed: Element[] = [];
  let intersect: ((entries: Partial<IntersectionObserverEntry>[]) => void) | undefined;
  vi.stubGlobal("IntersectionObserver", class {
    constructor(callback: typeof intersect) { intersect = callback; }
    observe(element: Element) { observed.push(element); }
    disconnect() {}
  });
  render(<PdfReader resource={resource} />);
  await loaded();
  expect(window.document.querySelectorAll("[data-pdf-page]")).toHaveLength(7);
  expect(window.document.querySelectorAll("canvas").length).toBeLessThanOrEqual(3);
  expect(observed).toHaveLength(7);
  const first = window.document.querySelector('[data-pdf-page="1"]')!;
  const sixth = window.document.querySelector('[data-pdf-page="6"]')!;
  await act(async () => { intersect?.([{ target: first, isIntersecting: false }, { target: sixth, isIntersecting: true }]); });
  await waitFor(() => expect(sixth.querySelector("canvas")).toBeTruthy());
  expect(first.querySelector("canvas")).toBeNull();
});

test("fit width uses the actual dimensions of landscape and portrait pages", async () => {
  pdf.getPage.mockImplementation(async (page: number) => ({
    getViewport: ({ scale }: { scale: number }) => ({ width: (page === 2 ? 1000 : 612) * scale, height: (page === 2 ? 600 : 792) * scale }),
    render: () => ({ promise: Promise.resolve(), cancel: vi.fn() }), getTextContent: async () => ({ items: [] }), cleanup: vi.fn(),
  }));
  render(<PdfReader resource={resource} />);
  await loaded(); await resizeTo(636);
  const landscape = window.document.querySelector<HTMLElement>('[data-pdf-page="2"]')!;
  await waitFor(() => expect(landscape.querySelector("canvas")?.style.width).toBe("612px"));
  expect(landscape.style.height).toBe("367.2px");
  await chooseZoom("100%");
  await waitFor(() => expect(landscape.querySelector("canvas")?.style.width).toBe("1000px"));
  await chooseZoom("适应宽度"); await resizeTo(330);
  await waitFor(() => expect(landscape.querySelector("canvas")?.style.width).toBe("306px"));
});

test("fit width follows the actual scroll viewport after padding and scrollbar space", async () => {
  render(<PdfReader resource={resource} />); await loaded();
  await act(async () => { resize?.([{ target: screen.getByLabelText("连续阅读页面"), contentRect: { width: 480 } } as unknown as ResizeObserverEntry]); });
  await waitFor(() => expect(window.document.querySelector("canvas")?.style.width).toBe("480px"));
});

test("full text search finds unrendered pages and navigates matching pages", async () => {
  pdf.getPage.mockImplementation(async (page: number) => ({
    getViewport: ({ scale }: { scale: number }) => ({ width: 612 * scale, height: 792 * scale }),
    render: () => ({ promise: Promise.resolve(), cancel: vi.fn() }),
    getTextContent: async () => ({ items: [{ str: page === 2 || page === 5 ? "A bounded residual controls the policy." : "Other text" }] }), cleanup: vi.fn(),
  }));
  const changed = vi.fn(); render(<PdfReader resource={resource} onPageChange={changed} />); await loaded();
  const search = screen.getByLabelText("搜索论文全文");
  fireEvent.change(search, { target: { value: "bounded residual" } });
  fireEvent.click(within(search.closest('.ant-input-search') as HTMLElement).getByRole("button", { name: "搜索" }));
  await screen.findByText(/2 处匹配，分布于 2 页/);
  expect(changed).toHaveBeenLastCalledWith(2);
  const next = screen.getByText("下一匹配页").closest('button')!;
  expect(next).toHaveAccessibleName("下一匹配页");
  fireEvent.click(next);
  await waitFor(() => expect(changed).toHaveBeenLastCalledWith(5));
  expect(screen.getByLabelText("PDF 页码")).toHaveValue("5");
});

test("PDF outline resolves named destinations and navigates nested chapters", async () => {
  document.getOutline.mockResolvedValue([{ title: "Methods", dest: "methods", items: [{ title: "Gating", dest: [{ num: 5, gen: 0 }], items: [] }] }]);
  document.getDestination.mockResolvedValue([{ num: 3, gen: 0 }]); document.getPageIndex.mockResolvedValue(3);
  const changed = vi.fn(); render(<PdfReader resource={resource} onPageChange={changed} />); await loaded();
  fireEvent.click(screen.getByLabelText("目录"));
  const outline = within(screen.getByLabelText("论文目录"));
  fireEvent.click(await outline.findByRole("button", { name: "Methods" }));
  await waitFor(() => expect(changed).toHaveBeenLastCalledWith(4));
  expect(document.getDestination).toHaveBeenCalledWith("methods");
  expect(outline.getByRole("button", { name: "Gating" })).toBeTruthy();
});

test("source boxes use PDF coordinates on only the targeted page", async () => {
  render(<PdfReader resource={resource} targetPage={4} bbox={[10, 20, 100, 40]} />); await loaded(); await resizeTo(636);
  const box = screen.getByLabelText("原文定位区域");
  expect(box.closest("[data-pdf-page]")?.getAttribute("data-pdf-page")).toBe("4");
  expect(box.style.left).toBe("10px"); expect(box.style.top).toBe("20px"); expect(box.style.width).toBe("90px");
});

test("parsed section headings provide navigation when the PDF has no embedded outline", async () => {
  const changed = vi.fn();
  const withSections = { ...resource, passages: [{ id: "block-1", heading: "Page 1", text: "Title", page: 1 }, { id: "block-2", heading: "3 Method", text: "Method text", page: 3 }] };
  render(<PdfReader resource={withSections} onPageChange={changed} />); await loaded();
  fireEvent.click(screen.getByLabelText("目录"));
  const outline = within(screen.getByLabelText("论文目录"));
  fireEvent.click(outline.getByRole("button", { name: "3 Method" }));
  await waitFor(() => expect(changed).toHaveBeenLastCalledWith(3));
  expect(outline.queryByRole("button", { name: "Page 1" })).toBeNull();
});

test("expanded reading works when the browser does not offer native fullscreen", async () => {
  render(<PdfReader resource={resource} />); await loaded();
  fireEvent.click(screen.getByLabelText("全屏"));
  await waitFor(() => expect(screen.getByLabelText("PDF 阅读器").classList.contains("is-expanded")).toBe(true));
  fireEvent.keyDown(window, { key: "Escape" });
  await waitFor(() => expect(screen.getByLabelText("PDF 阅读器").classList.contains("is-expanded")).toBe(false));
});

test("scroll position reports the visible page without snapping when the saved page echoes back", async () => {
  const changed = vi.fn(); const view = render(<PdfReader resource={resource} onPageChange={changed} />); await loaded();
  const viewport = screen.getByLabelText("连续阅读页面");
  Array.from(viewport.querySelectorAll<HTMLElement>("[data-pdf-page]")).forEach((element, index) => Object.defineProperty(element, "offsetTop", { value: index * 1000 }));
  Object.defineProperty(viewport, "clientHeight", { value: 600 });
  viewport.scrollTop = 2100; fireEvent.scroll(viewport);
  await waitFor(() => expect(changed).toHaveBeenLastCalledWith(3));
  view.rerender(<PdfReader resource={resource} initialPage={3} onPageChange={changed} />);
  expect(viewport.scrollTop).toBe(2100);
});
