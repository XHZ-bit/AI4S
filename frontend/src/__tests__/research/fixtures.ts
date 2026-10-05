import type {
  ComparisonResult,
  EvidenceRef,
  ExperimentSetting,
  MethodCard,
  ProjectFactsResponse,
  ProjectSnapshot,
  ResearchDecision,
  ResearchProject,
  ValidationPlan,
} from "../../api/project-types";

export const project: ResearchProject = {
  id: "project-1",
  version: 3,
  title: "异常检测课题",
  research_question: "哪条路线适合首轮验证？",
  domain: "image_anomaly_detection",
  domain_profile_version: "image-anomaly-v1",
  status: "active",
  constraints: {
    version: 2,
    objective: "验证小样本可行性",
    allowed_datasets: ["MVTec AD"],
    excluded_datasets: [],
    required_metrics: ["image_auroc"],
    compute: [],
    time_budget: null,
    cost_budget: null,
    data_access: [],
    notes: ["显存未知"],
  },
  created_at: "2026-10-04T08:00:00Z",
  updated_at: "2026-10-04T09:00:00Z",
};

export const evidence: EvidenceRef = {
  id: "evidence-1",
  source_kind: "literature_report",
  finding_status: "reported",
  kind: "text",
  paper_uid: "paper-1",
  document_id: "doc-1",
  document_version: "sha256:abc",
  passage_id: "passage-1",
  locator: { page: 4, heading: "Experiments", start_offset: 0, end_offset: 30, table_id: null, row_label: null, column_label: null },
  quote: "We evaluate on MVTec AD.",
  note: null,
  extraction_version: "v1",
  conflict_group_id: null,
};

export const method: MethodCard = {
  id: "method-1", project_id: project.id, version: 1, status: "candidate", source_kind: "literature_report", finding_status: "reported",
  field_evidence: [{ field_path: "name", source_kind: "literature_report", finding_status: "reported", evidence_ids: [evidence.id], note: null }],
  created_at: null, updated_at: null, paper_link_id: "link-1", name: "Patch Method", task: "anomaly detection", summary: "Patch based method", inputs: [], outputs: [], mechanisms: [], assumptions: [], limitations: [],
};

export const settingA: ExperimentSetting = {
  id: "setting-a", project_id: project.id, version: 1, status: "candidate", source_kind: "literature_report", finding_status: "reported",
  field_evidence: [{ field_path: "dataset", source_kind: "literature_report", finding_status: "reported", evidence_ids: [evidence.id], note: null }],
  created_at: null, updated_at: null, paper_link_id: "link-1", method_id: method.id, name: "MVTec setting", dataset: "MVTec AD", dataset_version: null, subset: null, split: "official", evaluation_protocol: "image-level", preprocessing: [], hyperparameters: [], resources: [], random_seed: null, notes: [],
};

export const settingB: ExperimentSetting = { ...settingA, id: "setting-b", name: "Unknown setting", dataset: null, split: null, evaluation_protocol: null };

export const facts: ProjectFactsResponse = { methods: [method], experiment_settings: [settingA, settingB], measurements: [], evidence: [evidence] };

export const comparison: ComparisonResult = {
  contract_version: "research-v1.1", project_id: project.id, project_version: project.version,
  dimensions: [{ name: "dataset", values: { "setting-a": "MVTec AD", "setting-b": null }, comparable: false, reason: "候选 B 数据集未知" }],
  groups: [{ id: "group-1", candidate_ids: ["setting-a", "setting-b"], condition_signature: { dataset: null }, comparable: false, reasons: ["数据集未知"] }], warnings: [],
};

export const decision: ResearchDecision = {
  id: "decision-1", project_id: project.id, version: 1, status: "active", source_kind: "user_input", project_version: project.version,
  selected_method_id: method.id, selected_experiment_setting_ids: [settingA.id], considered_candidate_ids: [settingA.id, settingB.id], rationale: "先做低成本验证", evidence_ids: [evidence.id], created_at: "2026-10-04T10:00:00Z",
};

export const plan: ValidationPlan = {
  id: "plan-1", project_id: project.id, version: 1, status: "saved", title: "首轮验证", objective: "验证路线", hypothesis: null,
  selected_method_id: method.id, selected_experiment_setting_ids: [settingA.id], assumptions: [], unknowns: ["真实显存未知"], steps: [], target_measurements: [], risks: ["数据许可待确认"], source_kind: "user_input", review_status: "needs_review", review_reasons: ["project_constraints_changed"],
};

export const snapshot: ProjectSnapshot = {
  id: "snapshot-1", contract_version: "research-v1.1", project_id: project.id, snapshot_version: 1, frozen_project_version: 3, frozen_constraint_version: 2,
  frozen_domain_profile_version: "image-anomaly-v1", frozen_decision: { id: decision.id, version: 1 }, frozen_documents: [{ paper_link_id: "link-1", paper_uid: "paper-1", document_id: "doc-1", document_version: "sha256:abc", content_hash: "abc" }], frozen_facts: [{ id: method.id, version: 1 }], plan, review_status: "needs_review", review_reasons: ["project_constraints_changed"], created_at: "2026-10-04T11:00:00Z",
};
