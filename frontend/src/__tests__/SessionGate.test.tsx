import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, test, vi } from "vitest";
import SessionGate from "../components/SessionGate";
import { useAccessMode } from "../components/SessionContext";
import { apiGet, apiPatch, apiPost } from "../api/client";
import { uploadPdf } from "../api/papers";
import { updateProject } from "../api/projects";
import { authenticatedFetch, clearBrowserDrafts, setCsrfToken } from "../api/session";
import { project } from "./research/fixtures";

const member = { mode: "multiuser", user: { id: "u1", username: "alice", role: "user" }, csrf_token: "csrf-1" };
function response(body: unknown, status = 200) { return { ok: status < 400, status, statusText: "Error", json: async () => body } as Response; }
function ModeProbe() { return <p data-testid="verified-mode">{useAccessMode()}</p>; }
beforeEach(() => { localStorage.clear(); sessionStorage.clear(); setCsrfToken(); vi.restoreAllMocks(); });
afterEach(() => { setCsrfToken(); });

test("independent components default to local mode without requesting a session", () => {
  globalThis.fetch = vi.fn();
  render(<ModeProbe />);
  expect(screen.getByTestId("verified-mode").textContent).toBe("local");
  expect(fetch).not.toHaveBeenCalled();
});

test("children receive only the verified access mode and unmount when the session expires", async () => {
  let resolve!: (value: Response) => void;
  globalThis.fetch = vi.fn().mockReturnValueOnce(new Promise<Response>(done => { resolve = done; }))
    .mockResolvedValue(response({ mode: "multiuser", user: null }));
  render(<SessionGate><ModeProbe /></SessionGate>);
  expect(screen.queryByTestId("verified-mode")).toBeNull();
  await act(async () => { resolve(response(member)); });
  expect((await screen.findByTestId("verified-mode")).textContent).toBe("multiuser");
  expect(fetch).toHaveBeenCalledTimes(1);
  await act(async () => { window.dispatchEvent(new Event("atlas:session-expired")); });
  expect(screen.queryByTestId("verified-mode")).toBeNull();
  expect(await screen.findByRole("button", { name: /^登\s*录$/ })).toBeTruthy();
  expect(fetch).toHaveBeenCalledTimes(2);
});

test("local mode opens the existing workspace without a login form", async () => {
  globalThis.fetch = vi.fn().mockResolvedValue(response({ mode: "local", user: null }));
  render(<SessionGate><p>研究工作空间</p></SessionGate>);
  expect(await screen.findByText("研究工作空间")).toBeTruthy();
  expect(screen.queryByRole("button", { name: /^登\s*录$/ })).toBeNull();
  expect(globalThis.fetch).toHaveBeenCalledWith("/api/auth/session", expect.objectContaining({ credentials: "same-origin" }));
});

test("session verification fails closed and can be retried", async () => {
  globalThis.fetch = vi.fn().mockRejectedValueOnce(new Error("offline")).mockResolvedValue(response({ mode: "local", user: null }));
  render(<SessionGate><p>研究工作空间</p></SessionGate>);
  expect(await screen.findByText("无法验证访问会话")).toBeTruthy();
  expect(screen.queryByText("研究工作空间")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "重试验证" }));
  expect(await screen.findByText("研究工作空间")).toBeTruthy();
});

test("multiuser login gates the workspace and logout clears only Atlas drafts", async () => {
  localStorage.setItem("atlas:paper-input:p", "old draft");
  localStorage.setItem("research-atlas:plan-draft:p:new", "old plan");
  localStorage.setItem("unrelated-setting", "keep");
  sessionStorage.setItem("atlas:scenario", "old scenario");
  globalThis.fetch = vi.fn().mockImplementation(async input => String(input).endsWith("/session") ? response({ mode: "multiuser", user: null }) : String(input).endsWith("/login") ? response(member) : response({ ok: true }));
  render(<SessionGate><p>研究工作空间</p></SessionGate>);
  fireEvent.change(await screen.findByLabelText("用户名"), { target: { value: "alice" } });
  fireEvent.change(screen.getByLabelText("密码"), { target: { value: "a long password" } });
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: /^登\s*录$/ })); });
  expect(await screen.findByText("研究工作空间")).toBeTruthy();
  expect(localStorage.getItem("atlas:paper-input:p")).toBeNull();
  localStorage.setItem("atlas:paper-input:p", "alice draft");
  fireEvent.click(screen.getByRole("button", { name: "退出登录" }));
  expect(await screen.findByRole("button", { name: /^登\s*录$/ })).toBeTruthy();
  expect(screen.queryByText("研究工作空间")).toBeNull();
  expect(localStorage.getItem("atlas:paper-input:p")).toBeNull();
  expect(localStorage.getItem("research-atlas:plan-draft:p:new")).toBeNull();
  expect(sessionStorage.getItem("atlas:scenario")).toBeNull();
  expect(localStorage.getItem("unrelated-setting")).toBe("keep");
  const logoutOptions = vi.mocked(fetch).mock.calls.find(call => String(call[0]).endsWith("/logout"))![1]!;
  expect(new Headers(logoutOptions.headers).get("X-Atlas-CSRF")).toBe("csrf-1");
});

test("local login-required mode hides the workspace until authentication", async () => {
  globalThis.fetch = vi.fn().mockResolvedValue(response({ mode: "local", user: null, require_login: true, registration_enabled: true }));
  render(<SessionGate><p>私人研究空间</p></SessionGate>);
  expect(await screen.findByRole("heading", { name: "登录 PaperStride" })).toBeTruthy();
  expect(screen.queryByText("私人研究空间")).toBeNull();
  expect(screen.getByText("创建新账号")).toBeTruthy();
});

test("expired sessions unmount the workspace before another login", async () => {
  globalThis.fetch = vi.fn().mockResolvedValueOnce(response(member)).mockResolvedValue(response({ mode: "multiuser", user: null }));
  render(<SessionGate><p>研究工作空间</p></SessionGate>);
  await screen.findByText("研究工作空间");
  await act(async () => { window.dispatchEvent(new Event("atlas:session-expired")); });
  expect(screen.queryByText("研究工作空间")).toBeNull();
  expect(await screen.findByRole("button", { name: /^登\s*录$/ })).toBeTruthy();
});

test("changing the password forces a fresh login and clears browser drafts", async () => {
  globalThis.fetch = vi.fn().mockResolvedValue(response(member));
  render(<SessionGate><p>研究工作空间</p></SessionGate>);
  fireEvent.click(await screen.findByRole("button", { name: "修改密码" }));
  fireEvent.change(screen.getByLabelText("当前密码"), { target: { value: "old password" } });
  fireEvent.change(screen.getByLabelText("新密码"), { target: { value: "a new long password" } });
  fireEvent.change(screen.getByLabelText("确认新密码"), { target: { value: "a new long password" } });
  localStorage.setItem("atlas:paper-input:p", "private draft");
  fireEvent.click(screen.getByRole("button", { name: "保存新密码并退出" }));
  expect(await screen.findByText("密码已修改，全部会话已退出，请重新登录。")).toBeTruthy();
  expect(screen.queryByText("研究工作空间")).toBeNull();
  expect(localStorage.getItem("atlas:paper-input:p")).toBeNull();
  expect(fetch).toHaveBeenCalledWith("/api/auth/password", expect.objectContaining({ body: JSON.stringify({ current_password: "old password", new_password: "a new long password" }) }));
});

test("all API entry points send credentials and writes send CSRF without breaking multipart upload", async () => {
  setCsrfToken("shared-token");
  globalThis.fetch = vi.fn().mockResolvedValue(response({}));
  await apiGet("/api/papers");
  await apiPost("/api/actions/v1", {});
  await apiPatch("/api/papers/p", {});
  await updateProject(project.id, { expected_version: 1, title: "Updated", research_question: null, status: null, constraints: null });
  await uploadPdf(new File(["%PDF"], "paper.pdf", { type: "application/pdf" }));
  vi.mocked(fetch).mock.calls.forEach(([, options]) => {
    expect(options?.credentials).toBe("same-origin");
    const headers = new Headers(options?.headers);
    expect(headers.get("X-Atlas-CSRF")).toBe(options?.method && options.method !== "GET" ? "shared-token" : null);
  });
  const uploadOptions = vi.mocked(fetch).mock.calls[4][1]!;
  expect(uploadOptions.body).toBeInstanceOf(FormData);
  expect(new Headers(uploadOptions.headers).has("Content-Type")).toBe(false);
});

test("administrators create and disable accounts with authenticated requests", async () => {
  const admin = { ...member, user: { id: "admin", username: "owner", role: "admin" } };
  let disabled = false;
  globalThis.fetch = vi.fn().mockImplementation(async (input, options) => {
    if (String(input).endsWith("/session")) return response(admin);
    if (options?.method === "PATCH") { disabled = true; return response({ id: "u1", username: "alice", role: "user", disabled }); }
    if (options?.method === "POST") return response({ id: "u2", username: "bob", role: "user", disabled: false });
    return response({ items: [{ ...admin.user, disabled: false }, { ...member.user, disabled }] });
  });
  render(<SessionGate><p>研究工作空间</p></SessionGate>);
  fireEvent.click(await screen.findByRole("button", { name: "账号管理" }));
  await screen.findByRole("cell", { name: "alice" });
  fireEvent.change(screen.getByLabelText("新账号用户名"), { target: { value: "bob" } });
  fireEvent.change(screen.getByLabelText("新账号初始密码"), { target: { value: "a long initial password" } });
  fireEvent.submit(screen.getByRole("button", { name: "创建用户账号" }).closest("form")!);
  await waitFor(() => expect(fetch).toHaveBeenCalledWith("/api/auth/users", expect.objectContaining({ method: "POST", body: JSON.stringify({ username: "bob", password: "a long initial password" }) })));
  const disable = screen.getAllByRole("button", { name: "停用账号" }).find(button => !(button as HTMLButtonElement).disabled)!;
  fireEvent.click(disable);
  expect(await screen.findByText("已停用")).toBeTruthy();
  expect(fetch).toHaveBeenCalledWith("/api/auth/users/u1", expect.objectContaining({ method: "PATCH", body: JSON.stringify({ disabled: true }) }));
}, 30000);

test("an old unauthorized request cannot expire a newly logged in session", async () => {
  let resolve!: (response: Response) => void;
  globalThis.fetch = vi.fn().mockReturnValue(new Promise<Response>(done => { resolve = done; }));
  const expired = vi.fn();
  window.addEventListener("atlas:session-expired", expired);
  setCsrfToken("old-token");
  const pending = authenticatedFetch("/api/papers");
  setCsrfToken("new-token");
  resolve(response({}, 401));
  await pending;
  expect(expired).not.toHaveBeenCalled();
  window.removeEventListener("atlas:session-expired", expired);
  clearBrowserDrafts();
});
