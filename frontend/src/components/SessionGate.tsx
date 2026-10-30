import { Fragment, useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { Alert, Button, Skeleton } from "antd";
import { BookOutlined } from "@ant-design/icons";
import { clearBrowserDrafts, getSession, logout, setCsrfToken, type Session } from "../api/session";
import AuthenticationForm from "./AuthenticationForm";
import SessionControls from "./SessionControls";
import { AccessModeProvider } from "./SessionContext";
import "./session.css";

function readMailAction() {
  const values = new URLSearchParams(window.location.hash.slice(1));
  const action = values.get("auth"), token = values.get("token");
  return token && (action === "reset-password" || action === "verify-email") ? { action, token } : null;
}

function broadcastSessionChange() {
  try { localStorage.setItem("atlas:session-revision", crypto.randomUUID()); } catch { /* Other tabs revalidate on their next request. */ }
}

export default function SessionGate({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session>();
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [mailAction, setMailAction] = useState(readMailAction);
  const [forceLogin, setForceLogin] = useState(false);
  const request = useRef(0);

  const adopt = useCallback((value: Session) => {
    if (!["local", "multiuser"].includes(value?.mode) || value.user && (!value.user.id || !value.user.username || !value.csrf_token)) {
      throw new Error("会话响应无效，请重试或联系维护者。");
    }
    setCsrfToken(value.user ? value.csrf_token : undefined);
    try {
      const owner = value.user ? String(value.user.id) : null;
      const previous = localStorage.getItem("atlas:session-owner");
      if (previous !== owner) clearBrowserDrafts();
      if (owner) localStorage.setItem("atlas:session-owner", owner);
    } catch { /* Authentication does not depend on browser storage. */ }
    setSession(value);
    if (value.user) {
      setForceLogin(false);
      setNotice(current => ["登录已过期，请重新登录。", "密码已修改，全部会话已退出，请重新登录。"].includes(current) ? "" : current);
    }
    else if (value.session_expired) { setForceLogin(true); setNotice("登录已过期，请重新登录。"); }
    setError("");
  }, []);

  const check = useCallback(async () => {
    const generation = ++request.current;
    setSession(undefined); setCsrfToken(); setLoading(true); setError("");
    try {
      const value = await getSession();
      if (generation === request.current) adopt(value);
    } catch (caught) {
      if (generation === request.current) setError(caught instanceof Error ? caught.message : String(caught));
    } finally { if (generation === request.current) setLoading(false); }
  }, [adopt]);

  useEffect(() => {
    const consumeLink = () => {
      const action = readMailAction();
      if (action) { setMailAction(action); window.history.replaceState(window.history.state, "", window.location.pathname + window.location.search); }
    };
    consumeLink();
    window.addEventListener("hashchange", consumeLink);
    return () => window.removeEventListener("hashchange", consumeLink);
  }, []);

  useEffect(() => {
    const expired = () => { clearBrowserDrafts(); setForceLogin(true); setNotice("登录已过期，请重新登录。"); void check(); };
    const changed = (event: StorageEvent) => {
      if (["atlas:session-owner", "atlas:session-revision"].includes(event.key ?? "") && event.oldValue !== event.newValue) void check();
    };
    const accountChanged = (event: Event) => {
      const detail = (event as CustomEvent<{ session?: Session; notice?: string; requireLogin?: boolean }>).detail;
      if (detail?.session) { adopt(detail.session); setNotice(detail.session.message || ""); setForceLogin(false); }
      else { if (detail?.notice) setNotice(detail.notice); if (detail?.requireLogin) setForceLogin(true); void check(); }
    };
    void check();
    window.addEventListener("atlas:session-expired", expired);
    window.addEventListener("storage", changed);
    window.addEventListener("atlas:account-changed", accountChanged);
    return () => { request.current++; setCsrfToken(); window.removeEventListener("atlas:account-changed", accountChanged); window.removeEventListener("atlas:session-expired", expired); window.removeEventListener("storage", changed); };
  }, [check, adopt]);

  const signIn = (value: Session) => {
    if (value.require_login || value.mode === "multiuser") { window.history.replaceState(window.history.state, "", "/"); window.dispatchEvent(new PopStateEvent("popstate")); }
    adopt(value); setNotice(value.message || ""); setMailAction(null); setForceLogin(false); broadcastSessionChange();
  };
  const signOut = async () => {
    setBusy(true); setError("");
    try { await logout(); clearBrowserDrafts(); adopt({ ...session!, user: null, csrf_token: undefined, session_expired: false }); setNotice(""); setForceLogin(false); setMailAction(null); broadcastSessionChange(); }
    catch (caught) { setError(caught instanceof Error ? caught.message : String(caught)); }
    finally { setBusy(false); }
  };
  const passwordChanged = () => {
    clearBrowserDrafts(); adopt({ ...session!, user: null, csrf_token: undefined }); setForceLogin(true); setMailAction(null); setNotice("密码已修改，全部会话已退出，请重新登录。"); broadcastSessionChange();
  };

  if (loading) return <div className="atlas-session-gate"><Skeleton active paragraph={{ rows: 4 }} /><p>正在检查访问会话…</p></div>;
  if (!session) return <div className="atlas-session-gate"><Alert type="error" message="无法验证访问会话" description={error} action={<Button onClick={() => void check()}>重试验证</Button>} /></div>;
  if (mailAction || forceLogin || (session.mode === "multiuser" || session.require_login) && !session.user) return <main className="atlas-session-page">
    <a className="atlas-session-brand" href="/"><BookOutlined aria-hidden="true" />PaperStride</a>
    <div className="atlas-session-sheet">
      <AuthenticationForm key={mailAction?.token || "login"} registrationEnabled={session.registration_enabled} emailRecoveryEnabled={session.recovery_email_enabled}
        notice={notice} onAuthenticated={signIn} onPasswordReset={passwordChanged}
        resetToken={mailAction?.action === "reset-password" ? mailAction.token : undefined}
        verificationToken={mailAction?.action === "verify-email" ? mailAction.token : undefined}
        onVerified={() => { setNotice("邮箱已验证，可用于登录和找回密码。"); void getSession().then(adopt).catch(() => {}); broadcastSessionChange(); }}
        onBack={() => { setMailAction(null); setForceLogin(!!session.session_expired); }} />
      {session.mode === "local" && !session.require_login && forceLogin && !mailAction && <div className="atlas-auth-secondary"><Button type="text" loading={busy} onClick={() => void signOut()}>退出账号并返回本机空间</Button>{error && <Alert type="error" message={error} />}</div>}
    </div>
    <p className="atlas-session-footer">论文、笔记与研究进度，保存在你的个人空间。</p>
  </main>;
  return <Fragment key={`${session.mode}:${session.user?.id ?? "local"}`}>
    <AccessModeProvider mode={session.mode} user={session.user}>
    {notice && session.user && <Alert className="atlas-account-notice" type="info" message={notice} closable onClose={() => setNotice("")} />}
    {session.mode === "multiuser" && session.user && <SessionControls user={session.user} busy={busy} error={error} onLogout={signOut} onPasswordChanged={passwordChanged} />}
    {children}
    </AccessModeProvider>
  </Fragment>;
}
