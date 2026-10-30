import { useEffect, useRef, useState } from "react";
import { Alert, Button, Form, Input, Skeleton } from "antd";
import { DownloadOutlined, ReloadOutlined } from "@ant-design/icons";
import { apiGet } from "../../api/client";
import { bindEmail, getAccountSessions, getSession, issueRecoveryCode, revokeOtherSessions, type AccountSession, type Session } from "../../api/session";
import { download } from "./Notebook";
import "../session.css";

export default function AccountServices({ signedIn, allowExport = true }: { signedIn: boolean; allowExport?: boolean }) {
  const [sessions, setSessions] = useState<AccountSession[]>([]);
  const [session, setSession] = useState<Session>();
  const [loading, setLoading] = useState(signedIn);
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const pending = useRef(false);
  const [emailForm] = Form.useForm();
  const [codeForm] = Form.useForm();
  const refresh = async () => { const [list, current] = await Promise.all([getAccountSessions(), getSession()]); setSessions(list.items); setSession(current); };
  useEffect(() => {
    let active = true;
    if (signedIn) {
      setLoading(true);
      void Promise.all([getAccountSessions(), getSession()]).then(([list, current]) => { if (active) { setSessions(list.items); setSession(current); } })
        .catch(caught => { if (active) setError(caught instanceof Error ? caught.message : "无法加载账号信息，请重试。"); })
        .finally(() => { if (active) setLoading(false); });
    }
    return () => { active = false; };
  }, [signedIn]);
  const run = async (fn: () => Promise<void>) => {
    if (pending.current) return;
    pending.current = true; setBusy(true); setError(""); setNotice("");
    try { await fn(); } catch (caught) { setError(caught instanceof Error ? caught.message : "操作未完成，请重试。"); }
    finally { pending.current = false; setBusy(false); }
  };
  return <div className="atlas-account-services">
    {error && <Alert type="error" message={error} showIcon />}
    {notice && <Alert type="success" message={notice} showIcon />}
    {signedIn && <>
      <section className="atlas-account-section">
        <h3>恢复邮箱</h3>
        {loading ? <Skeleton active paragraph={{ rows: 1 }} /> : <>
          {session?.user?.email ? <p><strong>{session.user.email}</strong><span className="atlas-account-verified">已验证</span></p> : <p>尚未绑定已验证的邮箱。</p>}
          {session?.user?.pending_email && <Alert type="info" message={`等待验证：${session.user.pending_email}`} description="请打开邮箱中的验证链接。需要重发时，在下方填写相同邮箱并确认当前密码。" />}
          {session?.recovery_email_enabled ? <details className="atlas-account-disclosure" open={!session.user?.email}>
            <summary>{session.user?.email ? "更换恢复邮箱" : "绑定邮箱或重发验证邮件"}</summary>
            <Form form={emailForm} name="account-email" layout="vertical" disabled={busy} requiredMark={false} onFinish={values => void run(async () => {
              const result = await bindEmail(values.email.trim(), values.password); emailForm.resetFields(["password"]); await refresh(); setNotice(result.message || "验证邮件已发送，请打开邮箱完成验证。");
            })}>
              <Form.Item name="email" label="恢复邮箱" rules={[{ required: true, message: "请输入邮箱" }, { type: "email", message: "请输入有效的邮箱地址" }]}><Input type="email" autoComplete="email" maxLength={254} /></Form.Item>
              <Form.Item name="password" label="确认当前密码" rules={[{ required: true, message: "请输入当前密码" }]}><Input.Password autoComplete="current-password" maxLength={1024} /></Form.Item>
              <Button htmlType="submit" loading={busy}>发送验证邮件</Button>
            </Form>
          </details> : <p className="atlas-account-muted">此站点尚未开启邮件服务。请保存下方的一次性恢复码，用于忘记密码时恢复账号。</p>}
        </>}
      </section>
      <section className="atlas-account-section">
        <h3>一次性恢复码</h3><p>忘记密码时可用恢复码重设密码。生成新码后旧码立即失效，请离线妥善保存。</p>
        <Form form={codeForm} name="issue-recovery" layout="vertical" disabled={busy} requiredMark={false} onFinish={values => void run(async () => {
          setCode(""); const result = await issueRecoveryCode(values.password); codeForm.resetFields(); setCode(result.code);
        })}>
          <Form.Item name="password" label="生成恢复码的当前密码" rules={[{ required: true, message: "请输入当前密码" }]}><Input.Password autoComplete="current-password" maxLength={1024} /></Form.Item>
          <Button htmlType="submit" loading={busy}>生成新恢复码</Button>
        </Form>
        {code && <Alert type="success" message="恢复码仅显示本次" description={<><code className="atlas-recovery-code">{code}</code><Button icon={<DownloadOutlined aria-hidden="true" />} onClick={() => download("paperstride-recovery.txt", code)}>保存恢复码文件</Button></>} />}
      </section>
      <section className="atlas-account-section">
        <div className="atlas-account-section-title"><h3>登录会话</h3><Button type="text" icon={<ReloadOutlined aria-hidden="true" />} disabled={busy} onClick={() => void run(refresh)}>刷新会话</Button></div>
        {loading ? <Skeleton active paragraph={{ rows: 2 }} /> : <ul className="atlas-account-sessions">{sessions.map(item => <li key={item.id}><strong>{item.current ? "当前会话" : "其他会话"}</strong><span>登录于 {new Date(item.created_at * 1000).toLocaleString()}</span><small>到期 {new Date(item.expires_at * 1000).toLocaleString()}</small></li>)}</ul>}
        {!loading && !sessions.length && <p>暂无可显示的登录会话，可刷新重试。</p>}
        <Button disabled={loading || !sessions.some(item => !item.current)} loading={busy} onClick={() => void run(async () => { await revokeOtherSessions(); await refresh(); setNotice("其他登录会话已退出，当前会话已保留。"); })}>退出其他会话</Button>
      </section>
    </>}
    {allowExport && <section className="atlas-account-section"><h3>导出研究数据</h3><p>包含书目、课题、笔记、辅导与练习记录，不包含密码、API 密钥或 PDF 文件。</p><Button icon={<DownloadOutlined aria-hidden="true" />} loading={busy} onClick={() => void run(async () => { download("paperstride-data.json", JSON.stringify(await apiGet("/api/workbench/export"), null, 2), "application/json"); setNotice("研究数据已导出。"); })}>导出我的研究数据</Button></section>}
  </div>;
}
