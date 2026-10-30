const BASE = import.meta.env.VITE_API_BASE ?? "";
let csrfToken: string | undefined;

export interface SessionUser { id: string; username: string; role: string; email?: string | null; pending_email?: string | null }
export interface Session { mode: "local" | "multiuser"; user: SessionUser | null; csrf_token?: string; require_login?: boolean; registration_enabled?: boolean; recovery_email_enabled?: boolean; session_expired?: boolean; message?: string }
export interface ManagedUser extends SessionUser { disabled: boolean }
export interface AccountSession { id: string; created_at: number; expires_at: number; current: boolean }
export interface AccountResult { ok: boolean; message?: string; requires_login?: boolean }

export function setCsrfToken(token?: string) { csrfToken = token; }

/** All API entry points share the session cookie and the current in-memory CSRF token. */
export async function authenticatedFetch(input: RequestInfo | URL, options: RequestInit = {}, signalSessionExpiry = true): Promise<Response> {
  const requestToken = csrfToken;
  const headers = new Headers(options.headers);
  if (!/^(GET|HEAD|OPTIONS)$/i.test(options.method ?? "GET") && requestToken) headers.set("X-Atlas-CSRF", requestToken);
  const response = await fetch(input, { ...options, credentials: "same-origin", headers });
  if (signalSessionExpiry && response.status === 401 && requestToken && requestToken === csrfToken) window.dispatchEvent(new Event("atlas:session-expired"));
  return response;
}

async function request<T>(path: string, method = "GET", body?: unknown, signal?: AbortSignal): Promise<T> {
  const response = await authenticatedFetch(`${BASE}/api/auth/${path}`, {
    method, signal,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  }, !["login", "register", "recovery-code", "email", "recover", "reset-password", "verify-email"].includes(path));
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const value = (await response.json()).detail;
      if (typeof value === "string") detail = value;
      else if (Array.isArray(value)) detail = value.map(item => item.msg ?? "请求校验失败").join("；");
    } catch { /* Preserve the HTTP error when a proxy returns non-JSON. */ }
    throw new Error(detail);
  }
  return response.status === 204 ? undefined as T : response.json() as Promise<T>;
}

export const getSession = (signal?: AbortSignal) => request<Session>("session", "GET", undefined, signal);
export const login = (username: string, password: string) => request<Session>("login", "POST", { username, password });
export const register = (username: string, password: string, email?: string) => request<Session>("register", "POST", { username, password, ...(email ? { email } : {}) });
export const logout = () => request<void>("logout", "POST");
export const changePassword = (current_password: string, new_password: string) => request<void>("password", "POST", { current_password, new_password });
export const listUsers = () => request<{ items: ManagedUser[] }>("users");
export const createUser = (username: string, password: string) => request<ManagedUser>("users", "POST", { username, password });
export const setUserDisabled = (id: string, disabled: boolean) => request<ManagedUser>(`users/${encodeURIComponent(id)}`, "PATCH", { disabled });
export const forgotPassword = (email: string) => request<AccountResult>("forgot-password", "POST", { email });
export const resetPassword = (token: string, new_password: string) => request<AccountResult>("reset-password", "POST", { token, new_password });
export const recoverWithCode = (username: string, code: string, new_password: string) => request<AccountResult>("recover", "POST", { username, code, new_password });
export const verifyEmail = (token: string) => request<AccountResult>("verify-email", "POST", { token });
export const bindEmail = (email: string, password: string) => request<AccountResult>("email", "POST", { email, password });
export const issueRecoveryCode = (password: string) => request<{ code: string }>("recovery-code", "POST", { password });
export const getAccountSessions = () => request<{ items: AccountSession[] }>("sessions");
export const revokeOtherSessions = () => request<AccountResult>("sessions/revoke-others", "POST");

export function notifyAccountChanged(session?: Session, notice?: string, requireLogin = false) {
  try { localStorage.setItem("atlas:session-revision", crypto.randomUUID()); } catch { /* Storage can be disabled. */ }
  window.dispatchEvent(new CustomEvent("atlas:account-changed", { detail: { session, notice, requireLogin } }));
}

export function clearBrowserDrafts() {
  for (const name of ["localStorage", "sessionStorage"] as const) {
    try {
      const storage = window[name];
      const keys = Array.from({ length: storage.length }, (_, index) => storage.key(index));
      keys.forEach(key => { if (key && /^(atlas:|research-atlas:|paperstride:)/.test(key)) storage.removeItem(key); });
    } catch { /* Session changes must still work when browser storage is disabled. */ }
  }
}
