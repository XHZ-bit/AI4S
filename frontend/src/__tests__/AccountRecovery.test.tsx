import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import AuthenticationForm from "../components/AuthenticationForm";
import SessionGate from "../components/SessionGate";
import { issueRecoveryCode, setCsrfToken } from "../api/session";

const anonymous = { mode: "multiuser", user: null, registration_enabled: true, recovery_email_enabled: true };
const member = { ...anonymous, user: { id: "alice-id", username: "alice", role: "user", pending_email: "alice@example.com" }, csrf_token: "csrf" };
const response = (body: unknown, status = 200) => ({ ok: status < 400, status, statusText: "Error", json: async () => body }) as Response;
const fill = (label: string, value: string) => fireEvent.change(screen.getByLabelText(label), { target: { value } });
beforeEach(() => { vi.restoreAllMocks(); setCsrfToken(); window.history.replaceState(null, "", "/"); localStorage.clear(); });
afterEach(() => { setCsrfToken(); window.history.replaceState(null, "", "/"); });

test("registration checks confirmation before creating an account and forwards optional email", async () => {
  const onAuthenticated = vi.fn();
  globalThis.fetch = vi.fn().mockResolvedValue(response(member));
  render(<AuthenticationForm registrationEnabled emailRecoveryEnabled onAuthenticated={onAuthenticated}/>);
  fireEvent.click(screen.getByRole("button", { name: "创建新账号" }));
  fill("用户名", "alice"); fill("邮箱（选填）", "alice@example.com"); fill("密码", "correct horse battery"); fill("确认密码", "different password");
  fireEvent.click(screen.getByRole("button", { name: "注册并进入" }));
  expect(await screen.findByText("两次输入的密码不一致")).toBeTruthy(); expect(fetch).not.toHaveBeenCalled();
  fill("确认密码", "correct horse battery"); fireEvent.click(screen.getByRole("button", { name: "注册并进入" }));
  await waitFor(() => expect(onAuthenticated).toHaveBeenCalledWith(member));
  expect(fetch).toHaveBeenCalledWith("/api/auth/register", expect.objectContaining({ body: JSON.stringify({ username: "alice", password: "correct horse battery", email: "alice@example.com" }) }));
});

test("email recovery shows a neutral receipt and offers the offline recovery path", async () => {
  globalThis.fetch = vi.fn().mockResolvedValue(response({ ok: true, message: "如果邮箱已绑定账号，重置邮件将发送到邮箱。" }));
  render(<AuthenticationForm emailRecoveryEnabled onAuthenticated={vi.fn()}/>);
  fireEvent.click(screen.getByRole("button", { name: "忘记密码？" })); fill("已验证的邮箱", "reader@example.com");
  fireEvent.click(screen.getByRole("button", { name: "发送重置邮件" }));
  expect(await screen.findByText("如果邮箱已绑定账号，重置邮件将发送到邮箱。")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "使用一次性恢复码" })); expect(screen.getByLabelText("一次性恢复码")).toBeTruthy();
});

test("a reset link works in local mode, removes its token from the URL, and returns to sign-in", async () => {
  window.history.replaceState(null, "", "/#auth=reset-password&token=test-reset-secret");
  globalThis.fetch = vi.fn().mockImplementation(async input => String(input).endsWith("/session") ? response({ ...anonymous, mode: "local" }) : response({ ok: true, requires_login: true }));
  render(<SessionGate><p>工作空间内容</p></SessionGate>);
  await screen.findByRole("heading", { name: "设置新密码" }); expect(window.location.hash).toBe(""); expect(screen.queryByText("工作空间内容")).toBeNull();
  fill("新密码", "new correct horse battery"); fill("确认新密码", "new correct horse battery"); fireEvent.click(screen.getByRole("button", { name: "保存新密码" }));
  expect(await screen.findByText("密码已修改，全部会话已退出，请重新登录。")).toBeTruthy(); expect(screen.getByRole("heading", { name: "登录 PaperStride" })).toBeTruthy();
  expect(fetch).toHaveBeenCalledWith("/api/auth/reset-password", expect.objectContaining({ body: JSON.stringify({ token: "test-reset-secret", new_password: "new correct horse battery" }) }));
});

test("a verification link waits for confirmation and preserves the signed-in workspace", async () => {
  window.history.replaceState(null, "", "/#auth=verify-email&token=test-verification");
  globalThis.fetch = vi.fn().mockImplementation(async input => String(input).endsWith("/session") ? response(member) : response({ ok: true, message: "邮箱验证成功" }));
  render(<SessionGate><p>工作空间内容</p></SessionGate>);
  await screen.findByRole("heading", { name: "验证邮箱" }); expect(window.location.hash).toBe("");
  expect(vi.mocked(fetch).mock.calls.filter(([url]) => String(url).endsWith("/verify-email"))).toHaveLength(0);
  fireEvent.click(screen.getByRole("button", { name: "验证邮箱" })); await screen.findByText("邮箱验证成功");
  fireEvent.click(screen.getByRole("button", { name: "返回工作空间" })); expect(await screen.findByText("工作空间内容")).toBeTruthy();
});

test("recovery without mail explains the fallback and invalid code leaves the form retryable", async () => {
  globalThis.fetch = vi.fn().mockResolvedValue(response({ detail: "用户名或恢复码不正确" }, 401));
  render(<AuthenticationForm onAuthenticated={vi.fn()}/>);
  fireEvent.click(screen.getByRole("button", { name: "忘记密码？" })); expect(screen.getByText(/未保存恢复码时/)).toBeTruthy();
  fill("账号用户名", "alice"); fill("一次性恢复码", "bad-code"); fill("新密码", "another long password"); fill("确认新密码", "another long password");
  fireEvent.click(screen.getByRole("button", { name: "重设密码" })); expect(await screen.findByText("用户名或恢复码不正确")).toBeTruthy();
  expect(screen.getByRole("button", { name: "重设密码" })).not.toBeDisabled();
});

test("password confirmation failure for a recovery code does not expire the session", async () => {
  const expired = vi.fn(); window.addEventListener("atlas:session-expired", expired); setCsrfToken("current-session");
  globalThis.fetch = vi.fn().mockResolvedValue(response({ detail: "当前密码不正确" }, 401));
  await expect(issueRecoveryCode("wrong")).rejects.toThrow("当前密码不正确"); expect(expired).not.toHaveBeenCalled();
  window.removeEventListener("atlas:session-expired", expired);
});

test("registration stays hidden when disabled, including after signing out", async () => {
  globalThis.fetch = vi.fn().mockImplementation(async input => String(input).endsWith("/session") ? response({ ...member, registration_enabled: false }) : response({ ok: true }));
  render(<SessionGate><p>工作空间内容</p></SessionGate>); fireEvent.click(await screen.findByRole("button", { name: "退出登录" }));
  await screen.findByRole("heading", { name: "登录 PaperStride" }); expect(screen.queryByRole("button", { name: "创建新账号" })).toBeNull();
});

test("pending authentication cannot be submitted a second time", async () => {
  let done!: (value: Response) => void;
  globalThis.fetch = vi.fn().mockReturnValue(new Promise<Response>(resolve => { done = resolve; }));
  render(<AuthenticationForm onAuthenticated={vi.fn()}/>); fill("用户名", "alice"); fill("密码", "correct horse battery");
  const form = screen.getByRole("button", { name: /^登\s*录$/ }).closest("form")!;
  await act(async () => { fireEvent.submit(form); }); await act(async () => { fireEvent.submit(form); }); expect(fetch).toHaveBeenCalledTimes(1);
  await act(async () => { done(response(member)); });
});

test("an expired local account stays at sign-in until explicitly leaving that account", async () => {
  globalThis.fetch = vi.fn().mockImplementation(async input => String(input).endsWith("/session") ? response({ ...anonymous, mode: "local", session_expired: true }) : response({ ok: true }));
  render(<SessionGate><p>本机工作空间</p></SessionGate>);
  expect(await screen.findByText("登录已过期，请重新登录。")).toBeTruthy();
  expect(screen.queryByText("本机工作空间")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "退出账号并返回本机空间" }));
  expect(await screen.findByText("本机工作空间")).toBeTruthy();
  expect(fetch).toHaveBeenCalledWith("/api/auth/logout", expect.objectContaining({ method: "POST" }));
});

test("another tab signing in releases a local password-reset sign-in prompt", async () => {
  globalThis.fetch = vi.fn().mockResolvedValueOnce(response({ ...anonymous, mode: "local", session_expired: true })).mockResolvedValue(response({ ...member, mode: "local" }));
  render(<SessionGate><p>个人工作空间</p></SessionGate>);
  await screen.findByText("登录已过期，请重新登录。");
  await act(async () => { window.dispatchEvent(new StorageEvent("storage", { key: "atlas:session-revision", oldValue: "old", newValue: "fresh" })); });
  expect(await screen.findByText("个人工作空间")).toBeTruthy();
});
