import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, test, vi } from "vitest";
import { apiGet, apiPost } from "../api/client";
import Actions from "../pages/Actions";

vi.mock("../api/client", () => ({ apiGet: vi.fn(), apiPost: vi.fn() }));

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return { promise, resolve };
}

function list(id: string, version = 1) {
  return { id, title: `清单 ${id}`, version, versions: [version], needs_review: false,
    estimated_minutes: 10, unscheduled_count: 0, input_fingerprint: id,
    items: [{ id: `${id}:read`, title: `阅读 ${id}`, url: `/papers/${id}`, status: "pending", week: 1, estimated_minutes: 10 }] };
}

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(apiGet).mockImplementation(async path => {
    if (path === "/api/papers") return { items: [{ uid: "p", title: "我的论文" }] };
    if (path === "/api/roadmap/auto-targets") return { items: [] };
    if (path === "/api/actions/v1") return { items: [list("a"), list("b", 2)], total: 2 };
    return list(path.endsWith("a") ? "a" : "b", path.endsWith("a") ? 1 : 2);
  });
});

test("switching lists clears the previous list before loading the next one", async () => {
  const next = deferred<ReturnType<typeof list>>();
  const load = vi.mocked(apiGet).getMockImplementation()!;
  vi.mocked(apiGet).mockImplementation((path, ...args) => path === "/api/actions/v1/b" ? next.promise : load(path, ...args));
  render(<MemoryRouter initialEntries={["/actions?id=a"]}><Actions /></MemoryRouter>);
  await screen.findByRole("link", { name: "阅读 a" });
  fireEvent.click(screen.getByRole("button", { name: "清单 b · v2" }));
  expect(screen.queryByRole("link", { name: "阅读 a" })).toBeNull();
  expect(screen.queryByRole("button", { name: "预览清单调整" })).toBeNull();
  expect(screen.getByText("正在加载行动清单…")).toBeTruthy();
  await act(async () => { next.resolve(list("b", 2)); });
  expect(await screen.findByRole("link", { name: "阅读 b" })).toBeTruthy();
});

test("a pending replan cannot attach its preview to another list", async () => {
  const old = deferred<ReturnType<typeof list>>();
  vi.mocked(apiPost).mockReturnValue(old.promise);
  render(<MemoryRouter initialEntries={["/actions?id=a"]}><Actions /></MemoryRouter>);
  await screen.findByRole("link", { name: "阅读 a" });
  fireEvent.click(screen.getByRole("button", { name: "预览清单调整" }));
  const signal = vi.mocked(apiPost).mock.calls[0][2];
  fireEvent.click(screen.getByRole("button", { name: "清单 b · v2" }));
  await screen.findByRole("link", { name: "阅读 b" });
  expect(signal?.aborted).toBe(true);
  await act(async () => { old.resolve(list("old-preview")); });
  expect(screen.queryByRole("link", { name: "阅读 old-preview" })).toBeNull();
  expect(screen.queryByRole("button", { name: "确认保存清单新版本" })).toBeNull();
});

test("changing the budget invalidates a preview that is still loading", async () => {
  const old = deferred<ReturnType<typeof list>>();
  vi.mocked(apiPost).mockReturnValue(old.promise);
  render(<MemoryRouter initialEntries={["/actions?paper=p"]}><Actions /></MemoryRouter>);
  fireEvent.click(await screen.findByRole("button", { name: "预览自动行动清单" }));
  fireEvent.change(screen.getByRole("spinbutton", { name: "行动清单每周小时" }), { target: { value: "20" } });
  await waitFor(() => expect(vi.mocked(apiPost).mock.calls[0][2]?.aborted).toBe(true));
  await act(async () => { old.resolve(list("old-preview")); });
  expect(screen.queryByRole("button", { name: "保存自动行动清单" })).toBeNull();
  expect(screen.queryByRole("link", { name: "阅读 old-preview" })).toBeNull();
  expect((screen.getByRole("spinbutton", { name: "行动清单每周小时" }) as HTMLInputElement).value).toBe("20");
});
