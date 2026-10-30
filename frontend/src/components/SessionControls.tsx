import { useRef, useState } from "react";
import { Alert, Button, Form, Input, Modal, Space, Table, Tag } from "antd";
import { createUser, listUsers, setUserDisabled, type ManagedUser, type SessionUser } from "../api/session";

import PasswordChangeForm from "./PasswordChangeForm";
import { newPasswordRules, usernameRules } from "./AuthenticationForm";

export default function SessionControls({ user, busy, error, onLogout, onPasswordChanged }: {
  user: SessionUser; busy: boolean; error: string; onLogout: () => Promise<void>; onPasswordChanged: () => void;
}) {
  const [passwordOpen, setPasswordOpen] = useState(false);
  const [usersOpen, setUsersOpen] = useState(false);
  const [users, setUsers] = useState<ManagedUser[]>([]);
  const [working, setWorking] = useState(false);
  const [failure, setFailure] = useState("");
  const pending = useRef(false);
  const [userForm] = Form.useForm();
  const load = async () => {
    setWorking(true); setFailure("");
    try { setUsers((await listUsers()).items); }
    catch (caught) { setFailure(caught instanceof Error ? caught.message : String(caught)); }
    finally { setWorking(false); }
  };
  return <div className="atlas-session-controls">
    <Space wrap><span>当前账号：{user.username}</span><Tag>{user.role === "admin" ? "管理员" : "用户"}</Tag>
      <Button size="small" onClick={() => { setFailure(""); setPasswordOpen(true); }}>修改密码</Button>
      {user.role === "admin" && <Button size="small" onClick={() => { setUsersOpen(true); void load(); }}>账号管理</Button>}
      <Button size="small" loading={busy} onClick={() => void onLogout()}>退出登录</Button>
    </Space>
    {error && <Alert type="error" message="账号操作失败" description={error} />}
    <Modal title="修改密码" open={passwordOpen} footer={null} destroyOnHidden onCancel={() => setPasswordOpen(false)}>
      <PasswordChangeForm onChanged={onPasswordChanged}/>
    </Modal>
    {user.role === "admin" && <Modal title="账号管理" open={usersOpen} footer={null} width={760} onCancel={() => { if (!working) { setUsersOpen(false); userForm.resetFields(); } }}>
      {failure && <Alert type="error" message={failure} action={<Button onClick={() => void load()}>重试加载</Button>} />}
      <Button onClick={() => void load()} loading={working}>刷新账号列表</Button>
      <Table<ManagedUser> rowKey="id" dataSource={users} loading={working} pagination={false} columns={[
        { title: "用户名", dataIndex: "username" },
        { title: "角色", dataIndex: "role", render: role => role === "admin" ? "管理员" : "用户" },
        { title: "状态", dataIndex: "disabled", render: disabled => disabled ? "已停用" : "可用" },
        { title: "操作", render: (_, item) => <Button disabled={item.id === user.id || working} onClick={async () => {
          setWorking(true); setFailure("");
          try { await setUserDisabled(item.id, !item.disabled); await load(); }
          catch (caught) { setFailure(caught instanceof Error ? caught.message : String(caught)); }
          finally { setWorking(false); }
        }}>{item.disabled ? "启用账号" : "停用账号"}</Button> },
      ]} />
      <Form form={userForm} layout="vertical" onFinish={async values => {
        if (pending.current) return; pending.current = true;
        setWorking(true); setFailure("");
        try { await createUser(values.username.trim(), values.password); userForm.resetFields(); await load(); }
        catch (caught) { setFailure(caught instanceof Error ? caught.message : String(caught)); }
        finally { pending.current = false; setWorking(false); }
      }}>
        <Form.Item name="username" label="新账号用户名" rules={usernameRules}><Input autoComplete="off" maxLength={64} /></Form.Item>
        <Form.Item name="password" label="新账号初始密码" rules={newPasswordRules}><Input.Password autoComplete="new-password" maxLength={1024} /></Form.Item>
        <Button type="primary" htmlType="submit" loading={working}>创建用户账号</Button>
      </Form>
    </Modal>}
  </div>;
}
