import { useRef, useState } from "react";
import { Alert, Button, Form, Input } from "antd";
import { changePassword } from "../api/session";
import { ConfirmPassword, newPasswordRules } from "./AuthenticationForm";

export default function PasswordChangeForm({ onChanged }: { onChanged: () => void }) {
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  const pending = useRef(false);
  return <div className="atlas-password-form">
    <p>修改后所有设备的登录会话都会退出，请使用新密码重新登录。</p>
    {error && <Alert type="error" message={error} showIcon />}
    <Form name="change-password" layout="vertical" disabled={busy} requiredMark={false} onFinish={async values => {
      if (pending.current) return;
      pending.current = true; setBusy(true); setError("");
      try { await changePassword(values.current_password, values.new_password); onChanged(); }
      catch (caught) { setError(caught instanceof Error ? caught.message : "修改失败，请重试。"); }
      finally { pending.current = false; setBusy(false); }
    }}>
      <Form.Item name="current_password" label="当前密码" rules={[{ required: true, message: "请输入当前密码" }]}><Input.Password autoComplete="current-password" maxLength={1024} /></Form.Item>
      <Form.Item name="new_password" label="新密码" rules={newPasswordRules}><Input.Password autoComplete="new-password" maxLength={1024} /></Form.Item>
      <ConfirmPassword dependency="new_password" label="确认新密码" />
      <Button type="primary" htmlType="submit" loading={busy}>保存新密码并退出</Button>
    </Form>
  </div>;
}
