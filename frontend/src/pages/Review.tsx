import { useEffect, useState, useCallback } from "react";
import { Alert, Table, Button, Typography, Layout, Menu, Space, message, Tag, Modal, Input } from "antd";
import { Link } from "react-router-dom";
import { reviewQueue, decide } from "../api/review";

export default function Review() {
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [actingId, setActingId] = useState<number | null>(null);
  const [editing, setEditing] = useState<any | null>(null);
  const [editText, setEditText] = useState("");
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try { setItems((await reviewQueue()).items); setError(null); }
    catch (e) { setError(`审核队列加载失败：${e}`); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { refresh(); }, [refresh]);

  const act = async (pid: number, action: string, payload?: Record<string, unknown>) => {
    setActingId(pid);
    try { await decide(pid, action, payload); message.success(action === "reject" ? "已拒绝" : "已通过"); setEditing(null); await refresh(); }
    catch (e) { setError(`操作失败：${e}`); }
    finally { setActingId(null); }
  };

  const submitEdit = async () => {
    if (!editing) return;
    try { await act(editing.id, "edit", JSON.parse(editText)); }
    catch { setError("编辑内容必须是合法 JSON"); }
  };

  const columns = [
    { title: "ID", dataIndex: "id", width: 60 },
    { title: "类型", dataIndex: "kind", width: 80, render: (k: string) => <Tag color={k === "entity" ? "blue" : "green"}>{k}</Tag> },
    { title: "置信度", dataIndex: "confidence", width: 90, render: (c: unknown) => (typeof c === "number" ? c.toFixed(2) : "-") },
    { title: "内容", render: (_: any, r: any) => <Typography.Paragraph copyable style={{ maxWidth: 700, marginBottom: 0 }}>{JSON.stringify(r.payload, null, 2)}</Typography.Paragraph> },
    { title: "操作", width: 220, render: (_: any, r: any) => <Space>
      <Button size="small" type="primary" loading={actingId === r.id} onClick={() => act(r.id, "approve")}>通过</Button>
      <Button size="small" onClick={() => { setEditing(r); setEditText(JSON.stringify(r.payload, null, 2)); }}>编辑</Button>
      <Button size="small" danger loading={actingId === r.id} onClick={() => act(r.id, "reject")}>拒绝</Button>
    </Space> },
  ];

  return (
    <Layout>
      <Layout.Header style={{ display: "flex", alignItems: "center" }}>
        <Typography.Title level={4} style={{ color: "#fff", margin: 0, marginRight: 24 }}>审核工作台</Typography.Title>
        <Menu theme="dark" mode="horizontal" items={[
          { key: "g", label: <Link to="/graph">图谱</Link> },
          { key: "m", label: <Link to="/manage">数据</Link> },
          { key: "rm", label: <Link to="/roadmap">路线</Link> },
        ]} />
      </Layout.Header>
      <Layout.Content style={{ padding: 16 }}>
        {error && <Alert type="error" showIcon closable onClose={() => setError(null)} message={error} style={{ marginBottom: 12 }} />}
        <Typography.Title level={5}>待审核候选（{items.length}）</Typography.Title>
        <Table rowKey="id" columns={columns} dataSource={items} loading={loading} pagination={{ pageSize: 20 }} />
        <Modal title="编辑候选内容" open={!!editing} onOk={submitEdit} confirmLoading={actingId === editing?.id} onCancel={() => setEditing(null)} width={720}>
          <Input.TextArea value={editText} onChange={e => setEditText(e.target.value)} autoSize={{ minRows: 10, maxRows: 24 }} />
        </Modal>
      </Layout.Content>
    </Layout>
  );
}