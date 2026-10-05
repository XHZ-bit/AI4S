// Frozen JSON contract shared by the Research Atlas project workflow.
// Keep field names and enum values in sync with backend/app/models/research.py.

export const CONTRACT_VERSION = "research-v1.1" as const;

export type DomainId = "image_anomaly_detection" | "time_series_forecasting";
export type SourceKind = "literature_report" | "user_input" | "model_suggestion";
export type RecordStatus = "candidate" | "user_confirmed" | "disputed" | "withdrawn";
export type FindingStatus = "unknown" | "not_found" | "not_parsed" | "conflicting" | "reported";
export type ReviewStatus = "current" | "needs_review";
export type ProjectStatus = "active" | "archived";
export type PaperRole = "primary" | "method" | "baseline" | "dataset" | "evaluation" | "background";
export type PaperLinkStatus = "active" | "removed";
export type EvidenceKind = "text" | "table" | "figure" | "caption" | "user_note";
export type MetricDirection = "higher_is_better" | "lower_is_better" | "target_is_better" | "unspecified";
export type NumericScale = "raw" | "fraction" | "percent";
export type TaskKind = "project_extraction" | "comparison" | "plan_generation" | "graph_projection" | "export";
export type TaskStatus = "queued" | "running" | "succeeded" | "failed" | "interrupted";
export type ProjectionStatus = "pending" | "running" | "succeeded" | "failed";
export type PlanStatus = "draft" | "saved" | "superseded";
export type DecisionStatus = "active" | "superseded" | "withdrawn";

export const ALLOWED_RECORD_STATUS_TRANSITIONS: Readonly<Record<RecordStatus, readonly RecordStatus[]>> = {
  candidate: ["user_confirmed", "disputed", "withdrawn"],
  user_confirmed: ["disputed", "withdrawn"],
  disputed: ["user_confirmed", "withdrawn"],
  withdrawn: ["candidate"],
};

export interface VersionRef {
  id: string;
  version: number;
}

export interface NumericValue {
  value: number;
  unit: string | null;
  scale: NumericScale;
  lower: number | null;
  upper: number | null;
}

export interface NamedValue {
  name: string;
  value: string | number | boolean | null;
  unit: string | null;
  finding_status: FindingStatus;
}

export interface EvidenceLocator {
  page: number | null;
  heading: string | null;
  start_offset: number | null;
  end_offset: number | null;
  table_id: string | null;
  row_label: string | null;
  column_label: string | null;
}

export interface EvidenceRef {
  id: string;
  source_kind: SourceKind;
  finding_status: FindingStatus;
  kind: EvidenceKind;
  paper_uid: string | null;
  document_id: string | null;
  document_version: string | null;
  passage_id: string | null;
  locator: EvidenceLocator | null;
  quote: string | null;
  note: string | null;
  extraction_version: string | null;
  conflict_group_id: string | null;
}

export interface FieldEvidence {
  field_path: string;
  source_kind: SourceKind;
  finding_status: FindingStatus;
  evidence_ids: string[];
  note: string | null;
}

export interface ComputeConstraint {
  device_kind: string | null;
  device_model: string | null;
  device_count: number | null;
  memory: NumericValue | null;
  availability: string | null;
}

export interface ProjectConstraints {
  version: number;
  objective: string;
  allowed_datasets: string[];
  excluded_datasets: string[];
  required_metrics: string[];
  compute: ComputeConstraint[];
  time_budget: NumericValue | null;
  cost_budget: NumericValue | null;
  data_access: string[];
  notes: string[];
}

export interface ResearchProjectCreate {
  title: string;
  research_question: string;
  domain: DomainId;
  constraints: ProjectConstraints;
}

export interface ResearchProjectPatch {
  expected_version: number;
  title: string | null;
  research_question: string | null;
  status: ProjectStatus | null;
  constraints: ProjectConstraints | null;
}

export interface ResearchProject {
  id: string;
  version: number;
  title: string;
  research_question: string;
  domain: DomainId;
  domain_profile_version: string;
  status: ProjectStatus;
  constraints: ProjectConstraints;
  created_at: string;
  updated_at: string;
}

export interface PaperLinkCreate {
  expected_project_version: number;
  paper_uid: string;
  role: PaperRole;
  note: string | null;
}

export interface PaperLinkPatch {
  expected_version: number;
  role: PaperRole | null;
  status: PaperLinkStatus | null;
  note: string | null;
}

export interface PaperLink {
  id: string;
  project_id: string;
  version: number;
  paper_uid: string;
  role: PaperRole;
  status: PaperLinkStatus;
  note: string | null;
  linked_document_id: string | null;
  linked_document_version: string | null;
  created_at: string;
  updated_at: string;
}

export interface FactBase {
  id: string;
  project_id: string;
  version: number;
  status: RecordStatus;
  source_kind: SourceKind;
  finding_status: FindingStatus;
  field_evidence: FieldEvidence[];
  created_at: string | null;
  updated_at: string | null;
}

export interface MethodCard extends FactBase {
  paper_link_id: string | null;
  name: string;
  task: string | null;
  summary: string | null;
  inputs: string[];
  outputs: string[];
  mechanisms: string[];
  assumptions: string[];
  limitations: string[];
}

export interface ExperimentSetting extends FactBase {
  paper_link_id: string | null;
  method_id: string;
  name: string;
  dataset: string | null;
  dataset_version: string | null;
  subset: string | null;
  split: string | null;
  evaluation_protocol: string | null;
  preprocessing: string[];
  hyperparameters: NamedValue[];
  resources: NamedValue[];
  random_seed: string | null;
  notes: string[];
}

export interface Measurement extends FactBase {
  experiment_setting_id: string;
  metric_name: string;
  metric_scope: string | null;
  value: NumericValue | null;
  direction: MetricDirection;
  aggregation: string | null;
  uncertainty: NumericValue | null;
  sample_size: number | null;
}

export interface CandidateBundle {
  contract_version: typeof CONTRACT_VERSION;
  project_id: string;
  paper_link_id: string;
  document_id: string;
  document_version: string;
  extraction_version: string;
  evidence: EvidenceRef[];
  methods: MethodCard[];
  experiment_settings: ExperimentSetting[];
  measurements: Measurement[];
  warnings: string[];
}

export interface ExtractionStartRequest {
  expected_project_version: number;
  document_id: string;
}

export interface StatusTransitionRequest {
  expected_version: number;
  from_status: RecordStatus;
  to_status: RecordStatus;
  actor: string;
  reason: string;
}

export interface ComparisonCandidate {
  method_id: string;
  experiment_setting_id: string;
  measurement_ids: string[];
}

export interface ComparisonRequest {
  project_id: string;
  project_version: number;
  domain: DomainId;
  candidates: ComparisonCandidate[];
}

export interface ComparisonDimension {
  name: string;
  values: Record<string, string | number | boolean | null>;
  comparable: boolean;
  reason: string | null;
}

export interface ComparisonGroup {
  id: string;
  candidate_ids: string[];
  condition_signature: Record<string, string | number | boolean | null>;
  comparable: boolean;
  reasons: string[];
}

export interface ComparisonResult {
  contract_version: typeof CONTRACT_VERSION;
  project_id: string;
  project_version: number;
  dimensions: ComparisonDimension[];
  groups: ComparisonGroup[];
  warnings: string[];
}

export interface ResearchDecisionCreate {
  expected_project_version: number;
  selected_method_id: string;
  selected_experiment_setting_ids: string[];
  considered_candidate_ids: string[];
  rationale: string;
  evidence_ids: string[];
}

export interface ResearchDecision {
  id: string;
  project_id: string;
  version: number;
  status: DecisionStatus;
  source_kind: "user_input";
  project_version: number;
  selected_method_id: string;
  selected_experiment_setting_ids: string[];
  considered_candidate_ids: string[];
  rationale: string;
  evidence_ids: string[];
  created_at: string;
}

export interface ProtocolStep {
  id: string;
  title: string;
  purpose: string;
  inputs: string[];
  procedure: string[];
  expected_observation: string | null;
  acceptance_criteria: string[];
  evidence_ids: string[];
}

export interface ValidationPlan {
  id: string | null;
  project_id: string;
  version: number;
  status: PlanStatus;
  title: string;
  objective: string;
  hypothesis: string | null;
  selected_method_id: string;
  selected_experiment_setting_ids: string[];
  assumptions: string[];
  unknowns: string[];
  steps: ProtocolStep[];
  target_measurements: string[];
  risks: string[];
  source_kind: SourceKind;
  review_status: ReviewStatus;
  review_reasons: string[];
}

export interface PlanSaveRequest {
  expected_project_version: number;
  expected_plan_version: number;
  plan: ValidationPlan;
}

export interface PlanGenerateRequest {
  expected_project_version: number;
  decision_id: string;
  decision_version: number;
}

export interface FrozenDocument {
  paper_link_id: string;
  paper_uid: string;
  document_id: string;
  document_version: string;
  content_hash: string;
}

export interface ProjectSnapshot {
  id: string;
  contract_version: typeof CONTRACT_VERSION;
  project_id: string;
  snapshot_version: number;
  frozen_project_version: number;
  frozen_constraint_version: number;
  frozen_domain_profile_version: string;
  frozen_decision: VersionRef;
  frozen_documents: FrozenDocument[];
  frozen_facts: VersionRef[];
  plan: ValidationPlan;
  review_status: ReviewStatus;
  review_reasons: string[];
  created_at: string;
}

export interface SnapshotCreateRequest {
  expected_project_version: number;
  plan_id: string;
  plan_version: number;
}

export interface ExtractionInput {
  contract_version: typeof CONTRACT_VERSION;
  project_id: string;
  paper_link: PaperLink;
  document: FrozenDocument;
  passages: Record<string, unknown>[];
  domain: DomainId;
  domain_profile_version: string;
}

export interface DecisionValidationRequest {
  project: ResearchProject;
  decision: ResearchDecisionCreate;
  methods: MethodCard[];
  experiment_settings: ExperimentSetting[];
  measurements: Measurement[];
}

export interface DecisionValidationResult {
  valid: boolean;
  errors: string[];
  warnings: string[];
  referenced_fact_ids: string[];
}

export interface PlanBuildInput {
  project: ResearchProject;
  decision: ResearchDecision;
  methods: MethodCard[];
  experiment_settings: ExperimentSetting[];
  measurements: Measurement[];
  evidence: EvidenceRef[];
}

export interface SnapshotBuildInput extends PlanBuildInput {
  plan: ValidationPlan;
  frozen_documents: FrozenDocument[];
}

export interface GraphNode {
  id: string;
  kind: string;
  label: string;
  properties: Record<string, string | number | boolean | null>;
}

export interface GraphEdge {
  id: string;
  kind: string;
  source_id: string;
  target_id: string;
  fact_ids: string[];
  evidence_ids: string[];
  properties: Record<string, string | number | boolean | null>;
}

export interface GraphProjection {
  contract_version: typeof CONTRACT_VERSION;
  project_id: string;
  snapshot_id: string;
  snapshot_version: number;
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface GraphProjectionResult {
  project_id: string;
  snapshot_id: string;
  projected_nodes: number;
  projected_edges: number;
}

export interface GraphQuery {
  project_id: string;
  snapshot_id: string;
  node_ids: string[];
  kinds: string[];
  limit: number;
}

export interface GraphQueryResult {
  project_id: string;
  snapshot_id: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface ErrorDetail {
  code: string;
  message: string;
  retryable: boolean;
  fields: Record<string, string>;
  current_version: number | null;
  request_id: string | null;
}

export interface ErrorResponse {
  detail: ErrorDetail;
}

export interface AsyncTask {
  id: string;
  kind: TaskKind;
  status: TaskStatus;
  project_id: string;
  progress: number | null;
  result: Record<string, unknown> | null;
  error: ErrorDetail | null;
  created_at: string;
  updated_at: string;
}

export interface GraphProjectionStatus {
  project_id: string;
  snapshot_id: string;
  status: ProjectionStatus;
  task_id: string | null;
  attempt_count: number;
  last_error: string | null;
  updated_at: string;
}

export interface ProjectListResponse {
  items: ResearchProject[];
  next_cursor: string | null;
}

export interface PaperLinkListResponse {
  items: PaperLink[];
}

export interface ProjectFactsResponse {
  methods: MethodCard[];
  experiment_settings: ExperimentSetting[];
  measurements: Measurement[];
  evidence: EvidenceRef[];
}

export interface DecisionListResponse {
  items: ResearchDecision[];
}

export interface PlanListResponse {
  items: ValidationPlan[];
}

export interface SnapshotListResponse {
  items: ProjectSnapshot[];
}

export interface DomainProfile {
  id: DomainId;
  version: string;
  label: string;
  comparison_dimensions: string[];
  common_metrics: string[];
  incompatibility_rules: string[];
}

export const DOMAIN_PROFILES: Readonly<Record<DomainId, DomainProfile>> = {
  image_anomaly_detection: {
    id: "image_anomaly_detection",
    version: "image-anomaly-v1",
    label: "图像异常检测",
    comparison_dimensions: [
      "dataset",
      "dataset_version",
      "category_or_defect_scope",
      "supervision",
      "training_regime",
      "image_resolution",
      "preprocessing",
      "score_level",
      "threshold_selection",
      "split",
      "evaluation_protocol",
    ],
    common_metrics: ["image_auroc", "pixel_auroc", "average_precision", "aupro"],
    incompatibility_rules: [
      "Do not merge image-level and pixel-level metrics.",
      "Do not rank results across different datasets, category scopes, or split protocols.",
    ],
  },
  time_series_forecasting: {
    id: "time_series_forecasting",
    version: "time-series-forecasting-v1",
    label: "时间序列预测",
    comparison_dimensions: [
      "dataset",
      "dataset_version",
      "target_variables",
      "forecast_horizon",
      "context_length",
      "frequency",
      "split",
      "covariates",
      "scaling",
      "evaluation_protocol",
    ],
    common_metrics: ["mae", "rmse", "mape", "smape", "mase"],
    incompatibility_rules: [
      "Do not rank results across different horizons, frequencies, splits, or target scopes.",
      "Percentage metrics require the paper's zero-value handling to be known.",
    ],
  },
};
