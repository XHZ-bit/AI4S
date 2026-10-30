import { useRef, useState } from "react";
import { Alert, Button, Form, Input } from "antd";
import { ArrowLeftOutlined } from "@ant-design/icons";
import { forgotPassword, login, recoverWithCode, register, resetPassword, verifyEmail, type Session } from "../api/session";
import "./session.css";

type AuthMode = "login" | "register" | "forgot" | "recovery" | "reset" | "verify";
interface AuthValues { username: string; password: string; email?: string; code: string; new_password: string }
export const usernameRules = [{ required: true, message: "请输入用户名" }, { pattern: /^[A-Za-z0-9][A-Za-z0-9_.-]{2,63}$/, message: "使用 3–64 位字母、数字、点、横线或下划线，并以字母或数字开头" }];
export const newPasswordRules = [{ required: true, message: "请输入密码" }, { min: 12, message: "密码至少需要 12 个字符" }, { max: 1024, message: "密码不能超过 1024 个字符" }];

export function ConfirmPassword({ name = "confirm_password", dependency = "password", label = "确认密码" }: { name?: string; dependency?: string; label?: string }) {
  return <Form.Item name={name} label={label} dependencies={[dependency]} rules={[
    { required: true, message: "请再次输入密码" },
    ({ getFieldValue }) => ({ validator(_, value) { return !value || getFieldValue(dependency) === value ? Promise.resolve() : Promise.reject(new Error("两次输入的密码不一致")); } }),
  ]}><Input.Password autoComplete="new-password" maxLength={1024} /></Form.Item>;
}

export default function AuthenticationForm({ registrationEnabled = false, emailRecoveryEnabled = false, onAuthenticated, onPasswordReset, onVerified, resetToken, verificationToken, notice, onBack }: {
  registrationEnabled?: boolean; emailRecoveryEnabled?: boolean; onAuthenticated: (session: Session) => void;
  onPasswordReset?: () => void; onVerified?: () => void; resetToken?: string; verificationToken?: string; notice?: string; onBack?: () => void;
}) {
  const [mode, setMode] = useState<AuthMode>(resetToken ? "reset" : verificationToken ? "verify" : "login");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const pending = useRef(false);
  const [form] = Form.useForm<AuthValues>();
  const go = (next: AuthMode) => { if (pending.current) return; setMode(next); setError(""); setSuccess(""); form.resetFields(); };
  const finishRecovery = () => {
    setSuccess("密码已更新，请使用新密码登录。所有旧的登录会话已退出。");
    setMode("login"); form.resetFields(); onPasswordReset?.();
  };
  const submit = async (values: AuthValues) => {
    if (pending.current) return;
    pending.current = true; setBusy(true); setError(""); setSuccess("");
    try {
      if (mode === "login") onAuthenticated(await login(values.username.trim(), values.password));
      else if (mode === "register") onAuthenticated(await register(values.username.trim(), values.password, values.email?.trim()));
      else if (mode === "forgot") {
        const result = await forgotPassword(values.email!.trim());
        setSuccess(result.message || "如果该邮箱已绑定账号，重置邮件将发送到你的邮箱。请检查收件箱和垃圾邮件。");
      } else if (mode === "recovery") { await recoverWithCode(values.username.trim(), values.code.trim(), values.new_password); finishRecovery(); }
      else if (mode === "reset") { await resetPassword(resetToken!, values.new_password); finishRecovery(); }
      else if (mode === "verify") { const result = await verifyEmail(verificationToken!); setSuccess(result.message || "邮箱验证成功，可以使用这个邮箱登录和找回密码。"); onVerified?.(); }
    } catch (caught) { setError(caught instanceof Error ? caught.message : "操作未完成，请稍后重试。"); }
    finally { pending.current = false; setBusy(false); }
  };
  const titles: Record<AuthMode, string> = { login: "登录 PaperStride", register: "创建你的账号", forgot: "找回密码", recovery: "使用恢复码", reset: "设置新密码", verify: "验证邮箱" };
  const descriptions: Record<AuthMode, string> = {
    login: "继续阅读，回到你的研究空间。", register: "用一个账号保存论文、笔记和学习进度。",
    forgot: "输入已验证的邮箱，我们会向你发送密码重置链接。", recovery: "输入预先保存的一次性恢复码，重新设置账号密码。",
    reset: "设置一个至少 12 个字符的新密码。", verify: "确认此邮箱属于你，之后即可用它登录和找回密码。",
  };
  return <section className="atlas-auth-form" aria-label={titles[mode]}>
    <header><h1>{titles[mode]}</h1><p>{descriptions[mode]}</p></header>
    {notice && !success && <Alert type="info" message={notice} showIcon />}
    {error && <Alert type="error" message={error} showIcon />}
    {success && <Alert type="success" message={success} showIcon />}
    <Form form={form} key={mode} name={`account-${mode}`} layout="vertical" onFinish={submit} disabled={busy} requiredMark={false}>
      {(["login", "register", "recovery"] as AuthMode[]).includes(mode) && <Form.Item name="username" label={mode === "login" && emailRecoveryEnabled ? "用户名或邮箱" : mode === "recovery" ? "账号用户名" : "用户名"} rules={mode === "register" ? usernameRules : [{ required: true, whitespace: true, message: "请输入用户名" }]} extra={mode === "register" ? "3–64 位英文字母、数字、点、横线或下划线" : undefined}>
        <Input autoComplete="username" maxLength={mode === "login" ? 254 : 64} autoCapitalize="none" spellCheck={false} />
      </Form.Item>}
      {((mode === "register" && emailRecoveryEnabled) || mode === "forgot") && <Form.Item name="email" label={mode === "register" ? "邮箱（选填）" : "已验证的邮箱"} rules={[{ required: mode === "forgot", message: "请输入邮箱" }, { type: "email", message: "请输入有效的邮箱地址" }]} extra={mode === "register" ? "验证后可用于找回密码；也可以稍后在账号设置中绑定。" : undefined}>
        <Input type="email" autoComplete="email" maxLength={254} autoCapitalize="none" spellCheck={false} />
      </Form.Item>}
      {(mode === "login" || mode === "register") && <Form.Item name="password" label="密码" rules={mode === "register" ? newPasswordRules : [{ required: true, message: "请输入密码" }]} extra={mode === "register" ? "至少 12 个字符，建议使用容易记住的长密码。" : undefined}>
        <Input.Password autoComplete={mode === "register" ? "new-password" : "current-password"} maxLength={1024} />
      </Form.Item>}
      {mode === "register" && <ConfirmPassword />}
      {mode === "recovery" && <Form.Item name="code" label="一次性恢复码" rules={[{ required: true, whitespace: true, message: "请输入已保存的恢复码" }]}><Input.Password autoComplete="off" maxLength={160} /></Form.Item>}
      {(mode === "reset" || mode === "recovery") && <><Form.Item name="new_password" label="新密码" rules={newPasswordRules}><Input.Password autoComplete="new-password" maxLength={1024} /></Form.Item><ConfirmPassword dependency="new_password" label="确认新密码" /></>}
      {mode === "login" && <div className="atlas-auth-forgot"><Button type="link" onClick={() => go(emailRecoveryEnabled ? "forgot" : "recovery")}>忘记密码？</Button></div>}
      {!(mode === "verify" && success) && <Button type="primary" htmlType="submit" loading={busy} block>{({ login: "登录", register: "注册并进入", forgot: "发送重置邮件", recovery: "重设密码", reset: "保存新密码", verify: "验证邮箱" })[mode]}</Button>}
    </Form>
    <div className="atlas-auth-secondary">
      {mode === "login" && registrationEnabled && <p>还没有账号？<Button type="link" disabled={busy} onClick={() => go("register")}>创建新账号</Button></p>}
      {mode === "login" && !registrationEnabled && <p>此站点未开放注册，请联系维护者创建账号。</p>}
      {mode === "register" && <Button type="link" disabled={busy} onClick={() => go("login")}>已有账号，去登录</Button>}
      {mode === "forgot" && <Button type="link" disabled={busy} onClick={() => go("recovery")}>使用一次性恢复码</Button>}
      {mode === "recovery" && <p className="atlas-auth-help">恢复码需要事先在“账号与安全”中生成。{emailRecoveryEnabled ? <Button type="link" disabled={busy} onClick={() => go("forgot")}>改用邮箱找回</Button> : "未保存恢复码时，请联系维护者协助重置。"}</p>}
      {["forgot", "recovery", "reset", "verify"].includes(mode) && <Button type="text" icon={<ArrowLeftOutlined aria-hidden="true" />} disabled={busy} onClick={() => { if (onBack && (resetToken || verificationToken)) onBack(); else go("login"); }}>{mode === "verify" && success ? "返回工作空间" : "返回登录"}</Button>}
    </div>
  </section>;
}
