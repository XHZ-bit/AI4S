import { useEffect, useRef, useState } from "react";
import { Alert, Button, Input, Select, Space, Spin, Tag } from "antd";
import type { KnowledgeEvidence } from "../../api/knowledge";
import {
  createImplementation,
  generateImplementations,
  getImplementations,
  patchImplementation,
} from "../../api/knowledgeImplementations";
import type {
  ImplementationCollection,
  ImplementationInput,
  ImplementationKind,
  ImplementationMapping,
  ImplementationStatus,
} from "../../api/knowledgeImplementations";
import "./implementation-correspondence.css";
import KnowledgeText from './KnowledgeText';
import EvidenceQuote from './EvidenceQuote';

const statusLabels: Record<ImplementationStatus, string> = {
  proposed: "待核对",
  confirmed: "已确认",
  rejected: "已否定",
};
const staleLabels: Record<string, string> = {
  paper_evidence_missing: "论文依据待补充",
  code_evidence_missing: "代码依据待补充",
  paper_evidence_changed_or_missing: "论文来源已变化或不可用",
  code_evidence_changed_or_missing: "代码来源已变化或不可用",
  node_changed: "知识节点已变化",
  node_missing: "知识节点不可用",
  node_unavailable: "知识节点不可用",
};
function location(e: KnowledgeEvidence | null) {
  if (!e) return "没有绑定来源";
  const l = e.locator || {};
  return [
    e.source_title,
    l.path,
    l.page ? `第 ${l.page} 页` : undefined,
    l.start_line
      ? `第 ${l.start_line}${l.end_line && l.end_line !== l.start_line ? `–${l.end_line}` : ""} 行`
      : undefined,
    l.commit ? `提交 ${l.commit.slice(0, 12)}` : undefined,
    e.source_version ? `版本 ${e.source_version.slice(0, 12)}` : undefined,
  ]
    .filter(Boolean)
    .join(" · ");
}
const emptyForm = (): ImplementationInput => ({
  paper_evidence_id: undefined,
  code_source_id: "",
  code_block_id: "",
  paper_span: "",
  code_span: "",
  explanation: "",
  implementation_kind: "source",
});
export default function ImplementationCorrespondence({
  projectId,
  nodeId,
  onEvidence,
  onPractice,
}: {
  projectId: string;
  nodeId: string;
  onEvidence: (e: KnowledgeEvidence) => void;
  onPractice?: (nodeId: string, mappingId?: string) => void;
}) {
  const [opened, setOpened] = useState(false),
    [data, setData] = useState<ImplementationCollection>(),
    [loading, setLoading] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [side, setSide] = useState<"paper" | "code">("paper"),
    [showAllCandidates, setShowAllCandidates] = useState(false);
  const [selected, setSelected] = useState<string[]>([]),
    [editing, setEditing] = useState<ImplementationMapping>(),
    [form, setForm] = useState<ImplementationInput>(emptyForm),
    [formOpen, setFormOpen] = useState(false);
  const generation = useRef(0);
  useEffect(() => {
    generation.current++;
    setOpened(false);
    setShowAllCandidates(false);
    setData(undefined);
    setSelected([]);
    setForm(emptyForm());
    setFormOpen(false);
    setEditing(undefined);
    setError("");
    setLoading(false);
    setBusy(false);
  }, [projectId, nodeId]);
  useEffect(() => {
    if (!opened || data) return;
    const c = new AbortController();
    const token = generation.current;
    setLoading(true);
    setError("");
    getImplementations(projectId, nodeId, c.signal)
      .then((value) => {
        if (token === generation.current) setData(value);
      })
      .catch((e) => {
        if (!c.signal.aborted && token === generation.current)
          setError(String(e));
      })
      .finally(() => {
        if (!c.signal.aborted && token === generation.current)
          setLoading(false);
      });
    return () => c.abort();
  }, [opened, data, projectId, nodeId]);
  const update = (mapping: ImplementationMapping) =>
    setData(
      (old) =>
        old && {
          ...old,
          items: [
            mapping,
            ...old.items.filter((item) => item.id !== mapping.id),
          ],
        },
    );
  const generate = async () => {
    if (!selected.length || busy) return;
    const token = generation.current;
    setBusy(true);
    setError("");
    try {
      const result = await generateImplementations(projectId, nodeId, {
        source_ids: selected,
        refresh: true,
      });
      if (token === generation.current) setData(result);
    } catch (e) {
      if (token === generation.current) setError(String(e));
    } finally {
      if (token === generation.current) setBusy(false);
    }
  };
  const save = async () => {
    if (busy || !form.code_source_id || !form.code_block_id) return;
    const token = generation.current;
    setBusy(true);
    setError("");
    try {
      const value = editing
        ? await patchImplementation(projectId, nodeId, editing.id, {
            ...form,
            paper_evidence_id: form.paper_evidence_id || null,
            start_line: form.start_line ?? null,
            end_line: form.end_line ?? null,
            expected_revision: editing.revision,
          })
        : await createImplementation(projectId, nodeId, form);
      if (token === generation.current) {
        update(value);
        setFormOpen(false);
        setEditing(undefined);
        setForm(emptyForm());
      }
    } catch (e) {
      if (token === generation.current) setError(String(e));
    } finally {
      if (token === generation.current) setBusy(false);
    }
  };
  const review = async (
    item: ImplementationMapping,
    status: ImplementationStatus,
  ) => {
    if (busy) return;
    const token = generation.current;
    setBusy(true);
    setError("");
    try {
      const value = await patchImplementation(projectId, nodeId, item.id, {
        expected_revision: item.revision,
        status,
      });
      if (token === generation.current) update(value);
    } catch (e) {
      if (token === generation.current) setError(String(e));
    } finally {
      if (token === generation.current) setBusy(false);
    }
  };
  const edit = (item: ImplementationMapping) => {
    const source = item.code_source_id || item.code_evidence?.source_id || "";
    setEditing(item);
    setForm({
      paper_evidence_id: item.paper_evidence?.id,
      code_source_id: source,
      code_block_id: item.code_block_id || item.code_evidence?.block_id || "",
      paper_span: item.paper_span,
      code_span: item.code_span,
      explanation: item.explanation,
      implementation_kind: item.implementation_kind,
      start_line: item.start_line ?? undefined,
      end_line: item.end_line ?? undefined,
    });
    setFormOpen(true);
  };
  const source = data?.code_sources.find((s) => s.id === form.code_source_id);
  const block = source?.blocks.find((b) => b.id === form.code_block_id);
  const paper = data?.paper_evidence.find(
    (e) => e.id === form.paper_evidence_id,
  );
  const candidates =
    data?.items.filter((item) => item.status === "proposed") || [];
  const visibleItems =
    data?.items.filter(
      (item) =>
        item.status !== "proposed" ||
        showAllCandidates ||
        candidates.slice(0, 3).some((candidate) => candidate.id === item.id),
    ) || [];
  return (
    <details
      className="kw-implementation"
      open={opened}
      onToggle={(e) => setOpened(e.currentTarget.open)}
    >
      <summary>论文与代码对应</summary>
      {opened && (
        <div className="kw-implementation-content">
          <p>
            将论文片段与选定代码对照；生成结果需要人工核对，教学示例不代表论文实现。
          </p>
          {loading && (
            <div role="status">
              <Spin size="small" /> 正在读取对应关系…
            </div>
          )}
          {error && (
            <Alert
              type="error"
              message="操作未完成"
              description={error}
              action={
                !data ? (
                  <Button
                    onClick={() => {
                      setError("");
                      setOpened(false);
                      setTimeout(() => setOpened(true), 0);
                    }}
                  >
                    重试
                  </Button>
                ) : undefined
              }
            />
          )}
          {data && (
            <>
              {data.generation && (
                <p role="status">
                  {data.generation === "model"
                    ? "模型生成候选"
                    : data.generation === "rule"
                      ? "规则生成候选"
                      : "使用已保存候选"}
                  ，需要人工核对。
                </p>
              )}
              {data.warning && <Alert type="warning" message={data.warning} />}
              <div className="kw-implementation-generate">
                <label>
                  选择代码资料
                  <Select
                    mode="multiple"
                    aria-label="选择代码资料"
                    value={selected}
                    onChange={setSelected}
                    placeholder="选择已导入的代码资料"
                    options={data.code_sources.map((s) => ({
                      value: s.id,
                      label: s.title,
                    }))}
                  />
                </label>
                <Button
                  disabled={!selected.length || busy}
                  loading={busy}
                  onClick={() => void generate()}
                >
                  生成待核对关系
                </Button>
                {!data.code_sources.length && (
                  <p>
                    当前空间没有可用的代码资料，请先导入代码文件并完成解析。
                  </p>
                )}
              </div>
              {!data.items.length && (
                <p>还没有对应关系。可以选择代码资料生成候选，或手动添加。</p>
              )}
              {visibleItems.map((item) => (
                <article
                  className="kw-implementation-item"
                  data-mapping-id={item.id}
                  key={item.id}
                >
                  <div className="kw-implementation-heading">
                    <Space wrap>
                      <Tag>{statusLabels[item.status] || item.status}</Tag>
                      <Tag>
                        {item.implementation_kind === "teaching"
                          ? "教学示例"
                          : "来源代码"}
                      </Tag>
                      {item.stale && (
                        <Tag color="warning">依据需补充或重新核对</Tag>
                      )}
                    </Space>
                  </div>
                  {item.stale && (
                    <p role="status">
                      {item.stale_reasons
                        ?.map((r) => staleLabels[r] || r)
                        .join("；") || "关联来源或节点发生变化。"}
                    </p>
                  )}
                  <div
                    className="kw-implementation-side-toggle"
                    role="group"
                    aria-label="选择对照片段"
                  >
                    <button
                      type="button"
                      aria-pressed={side === "paper"}
                      onClick={() => setSide("paper")}
                    >
                      论文
                    </button>
                    <button
                      type="button"
                      aria-pressed={side === "code"}
                      onClick={() => setSide("code")}
                    >
                      代码
                    </button>
                  </div>
                  <div className="kw-implementation-sides" data-side={side}>
                    <section className="kw-implementation-paper">
                      <h4>论文片段</h4>
                      <KnowledgeText text={item.paper_span || "未填写"}/>
                      <small title={item.paper_evidence?.source_version}>
                        {location(item.paper_evidence)}
                      </small>
                      {item.paper_evidence && (
                        <Button
                          type="link"
                          size="small"
                          onClick={() => onEvidence(item.paper_evidence!)}
                        >
                          查看原文
                        </Button>
                      )}
                    </section>
                    <section className="kw-implementation-code">
                      <h4>代码片段</h4>
                      <pre>{item.code_span || "未填写"}</pre>
                      <small
                        title={[
                          item.code_evidence?.locator?.commit,
                          item.code_evidence?.source_version,
                        ]
                          .filter(Boolean)
                          .join(" · ")}
                      >
                        {location(item.code_evidence)}
                      </small>
                      {item.code_evidence && (
                        <Button
                          type="link"
                          size="small"
                          onClick={() => onEvidence(item.code_evidence!)}
                        >
                          查看代码来源
                        </Button>
                      )}
                    </section>
                  </div>
                  <div>
                    <strong>对应说明：</strong>
                    <KnowledgeText text={item.explanation}/>
                  </div>
                  {item.reviewed_at && (
                    <small>
                      核对记录：{item.reviewed_by || "用户"} ·{" "}
                      {item.reviewed_at}
                    </small>
                  )}
                  <Space wrap>
                    <Button
                      size="small"
                      disabled={busy}
                      onClick={() => edit(item)}
                    >
                      编辑
                    </Button>
                    <Button
                      size="small"
                      disabled={
                        busy || item.stale || item.status === "confirmed"
                      }
                      onClick={() => void review(item, "confirmed")}
                    >
                      确认对应
                    </Button>
                    <Button
                      size="small"
                      disabled={busy || item.status === "rejected"}
                      onClick={() => void review(item, "rejected")}
                    >
                      否定对应
                    </Button>
                    {onPractice && (
                      <Button
                        size="small"
                        disabled={
                          busy || item.stale || item.status !== "confirmed"
                        }
                        onClick={() => onPractice(nodeId, item.id)}
                      >
                        用于练习
                      </Button>
                    )}
                  </Space>
                </article>
              ))}
              {candidates.length > 3 && (
                <Button
                  type="link"
                  onClick={() => setShowAllCandidates((value) => !value)}
                >
                  {showAllCandidates
                    ? "收起候选"
                    : `显示其余 ${candidates.length - 3} 条候选`}
                </Button>
              )}
              {!formOpen && (
                <Button
                  disabled={!data.code_sources.length || busy}
                  onClick={() => {
                    setEditing(undefined);
                    setForm(emptyForm());
                    setFormOpen(true);
                  }}
                >
                  手动添加对应
                </Button>
              )}
              {formOpen && (
                <div className="kw-implementation-form">
                  <h4>{editing ? "编辑对应关系" : "手动添加对应关系"}</h4>
                  <label>
                    论文依据（可选）
                    <Select
                      aria-label="论文依据"
                      allowClear
                      value={form.paper_evidence_id}
                      onChange={(v) =>
                        setForm({
                          ...form,
                          paper_evidence_id: v,
                          paper_span:
                            data.paper_evidence
                              .find((e) => e.id === v)
                              ?.quote.slice(0, 2500) ?? "",
                        })
                      }
                      options={data.paper_evidence.map((e) => ({
                        value: e.id,
                        label: `${e.source_title} · ${e.quote.slice(0, 70)}`,
                      }))}
                    />
                  </label>
                  <label>
                    代码资料
                    <Select
                      aria-label="代码资料"
                      value={form.code_source_id || undefined}
                      onChange={(v) =>
                        setForm({
                          ...form,
                          code_source_id: v,
                          code_block_id: "",
                          code_span: "",
                          start_line: undefined,
                          end_line: undefined,
                        })
                      }
                      options={data.code_sources.map((s) => ({
                        value: s.id,
                        label: s.title,
                      }))}
                    />
                  </label>
                  <label>
                    代码内容块
                    <Select
                      aria-label="代码内容块"
                      value={form.code_block_id || undefined}
                      onChange={(v) =>
                        setForm({
                          ...form,
                          code_block_id: v,
                          start_line: undefined,
                          end_line: undefined,
                          code_span:
                            source?.blocks
                              .find((b) => b.id === v)
                              ?.text.slice(0, 2500) ?? "",
                        })
                      }
                      options={(source?.blocks || []).map((b) => ({
                        value: b.id,
                        label: [
                          b.heading || `内容块 ${b.ordinal}`,
                          typeof b.metadata.path === "string"
                            ? b.metadata.path
                            : undefined,
                          typeof b.metadata.start_line === "number"
                            ? `第 ${b.metadata.start_line}${typeof b.metadata.end_line === "number" ? `–${b.metadata.end_line}` : ""} 行`
                            : undefined,
                        ]
                          .filter(Boolean)
                          .join(" · "),
                      }))}
                    />
                  </label>
                  {paper && (
                    <div>
                      <small>所选论文依据，可展开原文片段进行复制：</small>
                      <blockquote><EvidenceQuote evidence={paper}/></blockquote>
                      <details><summary>复制原文片段</summary><pre><code>{paper.quote}</code></pre></details>
                    </div>
                  )}
                  {block && (
                    <div>
                      <small>所选代码内容块，请从中复制片段：</small>
                      <pre>{block.text}</pre>
                    </div>
                  )}
                  <p>
                    片段须与所选来源原文完全一致。可以先留空并保存为待核对。
                  </p>
                  <label>
                    论文片段
                    <Input.TextArea
                      aria-label="论文片段"
                      value={form.paper_span}
                      onChange={(e) =>
                        setForm({ ...form, paper_span: e.target.value })
                      }
                      rows={3}
                    />
                  </label>
                  <label>
                    代码片段
                    <Input.TextArea
                      aria-label="代码片段"
                      value={form.code_span}
                      onChange={(e) =>
                        setForm({ ...form, code_span: e.target.value })
                      }
                      rows={4}
                    />
                  </label>
                  <label>
                    对应说明
                    <Input.TextArea
                      aria-label="对应说明"
                      value={form.explanation}
                      onChange={(e) =>
                        setForm({ ...form, explanation: e.target.value })
                      }
                      rows={3}
                    />
                  </label>
                  <label>
                    对应类型
                    <Select
                      aria-label="对应类型"
                      value={form.implementation_kind}
                      onChange={(v: ImplementationKind) =>
                        setForm({ ...form, implementation_kind: v })
                      }
                      options={[
                        { value: "source", label: "来源代码" },
                        { value: "teaching", label: "教学示例" },
                      ]}
                    />
                  </label>
                  <div className="kw-implementation-lines">
                    <label>
                      起始行（可选）
                      <Input
                        type="number"
                        min={1}
                        value={form.start_line ?? ""}
                        onChange={(e) =>
                          setForm({
                            ...form,
                            start_line: e.target.value
                              ? Number(e.target.value)
                              : undefined,
                          })
                        }
                      />
                    </label>
                    <label>
                      结束行（可选）
                      <Input
                        type="number"
                        min={1}
                        value={form.end_line ?? ""}
                        onChange={(e) =>
                          setForm({
                            ...form,
                            end_line: e.target.value
                              ? Number(e.target.value)
                              : undefined,
                          })
                        }
                      />
                    </label>
                  </div>
                  <Space>
                    <Button
                      type="primary"
                      loading={busy}
                      disabled={
                        !form.code_source_id ||
                        !form.code_block_id ||
                        (form.start_line === undefined) !==
                          (form.end_line === undefined) ||
                        (!!form.start_line &&
                          !!form.end_line &&
                          form.end_line < form.start_line)
                      }
                      onClick={() => void save()}
                    >
                      保存
                    </Button>
                    <Button
                      disabled={busy}
                      onClick={() => {
                        setFormOpen(false);
                        setEditing(undefined);
                      }}
                    >
                      取消
                    </Button>
                  </Space>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </details>
  );
}
