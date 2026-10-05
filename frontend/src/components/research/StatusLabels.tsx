import { Tag, Tooltip } from "antd";
import type { FindingStatus, RecordStatus, ReviewStatus, SourceKind, TaskStatus } from "../../api/project-types";

const recordLabels: Record<RecordStatus, { label: string; color: string }> = {
  candidate: { label: "候选·待确认", color: "gold" },
  user_confirmed: { label: "用户已确认", color: "green" },
  disputed: { label: "存在争议", color: "red" },
  withdrawn: { label: "已撤回", color: "default" },
};

const findingLabels: Record<FindingStatus, { label: string; color: string; tip: string }> = {
  unknown: { label: "未知", color: "default", tip: "尚未判断，不能按 0、无需求或已满足处理" },
  not_found: { label: "当前范围未找到", color: "orange", tip: "已在冻结文档范围查找，但没有找到报告值" },
  not_parsed: { label: "尚未解析", color: "blue", tip: "来源可能存在，但当前解析能力未覆盖" },
  conflicting: { label: "来源冲突", color: "red", tip: "不同来源给出冲突信息，需要人工处理" },
  reported: { label: "来源已报告", color: "cyan", tip: "表示可定位到来源，不代表科学结论一定正确" },
};

const sourceLabels: Record<SourceKind, string> = {
  literature_report: "文献报告",
  user_input: "用户输入",
  model_suggestion: "AI建议",
};

export function RecordStatusTag({ status }: { status: RecordStatus }) {
  const item = recordLabels[status];
  return <Tag color={item.color}>{item.label}</Tag>;
}

export function FindingStatusTag({ status }: { status: FindingStatus }) {
  const item = findingLabels[status];
  return <Tooltip title={item.tip}><Tag color={item.color}>{item.label}</Tag></Tooltip>;
}

export function SourceKindTag({ source }: { source: SourceKind }) {
  return <Tag>{sourceLabels[source]}</Tag>;
}

export function ReviewStatusTag({ status }: { status: ReviewStatus }) {
  return status === "needs_review" ? <Tag color="volcano">待复核</Tag> : <Tag color="green">当前有效</Tag>;
}

export function TaskStatusTag({ status }: { status: TaskStatus }) {
  const map: Record<TaskStatus, { label: string; color: string }> = {
    queued: { label: "排队中", color: "blue" },
    running: { label: "处理中", color: "processing" },
    succeeded: { label: "已完成", color: "success" },
    failed: { label: "失败", color: "error" },
    interrupted: { label: "已中断", color: "warning" },
  };
  return <Tag color={map[status].color}>{map[status].label}</Tag>;
}

export const displayKnown = (value: string | number | boolean | null | undefined) =>
  value === null || value === undefined || value === "" ? "未知/未填写" : String(value);
