import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useNavigate } from "react-router-dom";
import { vi } from "vitest";
import PaperDetail from "../pages/PaperDetail";
import { apiGet, apiPatch } from "../api/client";
import { AccessModeProvider } from "../components/SessionContext";
vi.mock("../api/client", () => ({ apiGet: vi.fn(), apiPatch: vi.fn(), apiPost: vi.fn() }));
vi.mock("../components/PaperQuality", () => ({ default: () => null }));
vi.mock("../components/workspace/PaperReader", () => ({ default: () => null }));
const workspace = (uid: string) => ({ version: 0, paper: { uid, title: `Paper ${uid}`, year: 2024 }, documents: [], knowledge: [], reading_tasks: [], stages: [], checks: [{ id: "check", question: "What evidence supports this claim?" }], reproduction: { notice: "尚未实测", steps: [] }, state: { reading: {}, answers: {}, experiments: [], questions: [], profile: { weekly_hours: 10 } } });
function Switch() { const navigate = useNavigate(); return <button onClick={() => navigate("/papers/two?tab=experiment")}>switch paper</button>; }
function view(url = "/papers/one", multiuser = false) { return <MemoryRouter initialEntries={[url]}><AccessModeProvider mode={multiuser ? "multiuser" : "local"}><Switch /><Routes><Route path="/papers/:uid" element={<PaperDetail />} /></Routes></AccessModeProvider></MemoryRouter>; }
beforeEach(() => {
  localStorage.clear(); vi.clearAllMocks();
  vi.mocked(apiGet).mockImplementation(async path => path.endsWith("/guide") ? { guide: null } : workspace(path.split("/").pop()!));
});

test("a slow save preserves newer typing and advances the next save version", async () => {
  let finish!: (value: unknown) => void;
  vi.mocked(apiPatch).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; })).mockImplementationOnce(async (_, body: any) => ({ version: 2, state: body.state }));
  render(view()); const input = await screen.findByLabelText("What evidence supports this claim?");
  fireEvent.change(input, { target: { value: "submitted answer" } });
  fireEvent.click(screen.getByText("保存理解记录"));
  await waitFor(() => expect(apiPatch).toHaveBeenCalledTimes(1));
  const submitted = structuredClone((vi.mocked(apiPatch).mock.calls[0][1] as any).state);
  fireEvent.change(input, { target: { value: "newer unsaved answer" } });
  await act(async () => finish({ version: 1, state: submitted }));
  expect((input as HTMLTextAreaElement).value).toBe("newer unsaved answer");
  await waitFor(() => expect(JSON.parse(localStorage.getItem("atlas:paper-draft:one")!).state.answers.check.text).toBe("newer unsaved answer"));
  fireEvent.click(screen.getByText("保存理解记录"));
  await waitFor(() => expect(apiPatch).toHaveBeenCalledTimes(2));
  expect(vi.mocked(apiPatch).mock.calls[1][1]).toMatchObject({ version: 1, state: { answers: { check: { text: "newer unsaved answer" } } } });
});

test("switching to another paper never copies experimental input into its draft", async () => {
  render(view("/papers/one?tab=experiment"));
  const input = await screen.findByLabelText("仓库及提交版本");
  fireEvent.change(input, { target: { value: "private-one-commit" } });
  fireEvent.click(screen.getByText("switch paper"));
  await screen.findByText("Paper two");
  expect((screen.getByLabelText("仓库及提交版本") as HTMLTextAreaElement).value).toBe("");
  expect(JSON.parse(localStorage.getItem("atlas:paper-input:one")!).exp.code_version).toBe("private-one-commit");
  expect(JSON.parse(localStorage.getItem("atlas:paper-input:two")!).exp.code_version).toBe("");
});

test("a departed session's slow save cannot delete the reopened paper's newer draft", async () => {
  let finish!: (value: unknown) => void;
  vi.mocked(apiPatch).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  const oldView = render(view());
  fireEvent.change(await screen.findByLabelText("What evidence supports this claim?"), { target: { value: "old session answer" } });
  fireEvent.click(screen.getByText("保存理解记录"));
  await waitFor(() => expect(apiPatch).toHaveBeenCalledTimes(1));
  const submitted = structuredClone((vi.mocked(apiPatch).mock.calls[0][1] as any).state);
  oldView.unmount();
  render(view());
  fireEvent.change(await screen.findByLabelText("What evidence supports this claim?"), { target: { value: "new session draft" } });
  await waitFor(() => expect(JSON.parse(localStorage.getItem("atlas:paper-draft:one")!).state.answers.check.text).toBe("new session draft"));
  await act(async () => finish({ version: 1, state: submitted }));
  expect(JSON.parse(localStorage.getItem("atlas:paper-draft:one")!).state.answers.check.text).toBe("new session draft");
  expect((screen.getByLabelText("What evidence supports this claim?") as HTMLTextAreaElement).value).toBe("new session draft");
});

test("multiuser reading exposes named fields and explains unavailable processing before clicking", async () => {
  render(view("/papers/one", true)); await screen.findByText("Paper one");
  fireEvent.click(screen.getByText("资料详情"));
  expect((screen.getByText("获取 arXiv 全文").closest("button") as HTMLButtonElement).disabled).toBe(true);
  expect((screen.getByText("重新抽取 / 重试").closest("button") as HTMLButtonElement).disabled).toBe(true);
  expect((screen.getByText("生成有出处的辅助解读").closest("button") as HTMLButtonElement).disabled).toBe(true);
  expect(screen.getByText(/个人空间可阅读和记录/)).toBeTruthy();
  fireEvent.click(screen.getByText("修正元数据", { exact: true }));
  expect(await screen.findByLabelText("论文标题")).toBeTruthy();
  expect(screen.getByLabelText("发表年份")).toBeTruthy();
  expect(screen.getByLabelText("代码 HTTPS 链接")).toBeTruthy();
});
