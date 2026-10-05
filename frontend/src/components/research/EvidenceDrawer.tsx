import { Descriptions, Drawer, Empty, Space, Typography } from "antd";
import type { EvidenceRef } from "../../api/project-types";
import { FindingStatusTag, SourceKindTag, displayKnown } from "./StatusLabels";
import { Link } from "react-router-dom";

export default function EvidenceDrawer({
  evidence,
  onClose,
  projectId,
}: {
  evidence: EvidenceRef | null;
  onClose: () => void;
  projectId?: string;
}) {
  return <Drawer open={!!evidence} width={620} title="字段来源" onClose={onClose} destroyOnHidden>
    {!evidence ? <Empty /> : <Space direction="vertical" size="middle" style={{ width: "100%" }}>
      <Space wrap><SourceKindTag source={evidence.source_kind} /><FindingStatusTag status={evidence.finding_status} /></Space>
      <Descriptions bordered size="small" column={1} items={[
        { key: "paper", label: "论文", children: displayKnown(evidence.paper_uid) },
        { key: "document", label: "文档版本", children: evidence.document_id ? `${evidence.document_id} · ${displayKnown(evidence.document_version)}` : "未知/未绑定" },
        { key: "passage", label: "片段", children: displayKnown(evidence.passage_id) },
        { key: "page", label: "页码", children: displayKnown(evidence.locator?.page) },
        { key: "heading", label: "章节", children: displayKnown(evidence.locator?.heading) },
        { key: "table", label: "表格位置", children: evidence.locator?.table_id ? `${evidence.locator.table_id} / ${displayKnown(evidence.locator.row_label)} / ${displayKnown(evidence.locator.column_label)}` : "不适用或未知" },
      ]} />
      <div><Typography.Text strong>原文摘录</Typography.Text><Typography.Paragraph style={{ whiteSpace: "pre-wrap", marginTop: 8 }}>{evidence.quote || "当前来源没有可显示的摘录。"}</Typography.Paragraph></div>
      {evidence.note && <div><Typography.Text strong>说明</Typography.Text><Typography.Paragraph>{evidence.note}</Typography.Paragraph></div>}
      {projectId && <Link to={`/research/${projectId}/graph?mode=impact&node_id=${encodeURIComponent(evidence.id)}`}>查看该证据的影响范围</Link>}
      <Typography.Text type="secondary">可定位仅表示能够回到来源，不代表该结论已经被独立验证。</Typography.Text>
    </Space>}
  </Drawer>;
}
