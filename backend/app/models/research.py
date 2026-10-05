"""Frozen public contract models for the Research Atlas project workflow.

These models describe transport and cross-module values only.  Persistence,
extraction, comparison, planning, and graph projection live in their owning
modules.  JSON uses the snake_case field names declared here.
"""

from __future__ import annotations

import math
from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


CONTRACT_VERSION = "research-v1.1"


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class DomainId(str, Enum):
    IMAGE_ANOMALY_DETECTION = "image_anomaly_detection"
    TIME_SERIES_FORECASTING = "time_series_forecasting"


class SourceKind(str, Enum):
    LITERATURE_REPORT = "literature_report"
    USER_INPUT = "user_input"
    MODEL_SUGGESTION = "model_suggestion"


class RecordStatus(str, Enum):
    CANDIDATE = "candidate"
    USER_CONFIRMED = "user_confirmed"
    DISPUTED = "disputed"
    WITHDRAWN = "withdrawn"


class FindingStatus(str, Enum):
    UNKNOWN = "unknown"
    NOT_FOUND = "not_found"
    NOT_PARSED = "not_parsed"
    CONFLICTING = "conflicting"
    REPORTED = "reported"


class ReviewStatus(str, Enum):
    CURRENT = "current"
    NEEDS_REVIEW = "needs_review"


class ProjectStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class PaperRole(str, Enum):
    PRIMARY = "primary"
    METHOD = "method"
    BASELINE = "baseline"
    DATASET = "dataset"
    EVALUATION = "evaluation"
    BACKGROUND = "background"


class PaperLinkStatus(str, Enum):
    ACTIVE = "active"
    REMOVED = "removed"


class EvidenceKind(str, Enum):
    TEXT = "text"
    TABLE = "table"
    FIGURE = "figure"
    CAPTION = "caption"
    USER_NOTE = "user_note"


class MetricDirection(str, Enum):
    HIGHER_IS_BETTER = "higher_is_better"
    LOWER_IS_BETTER = "lower_is_better"
    TARGET_IS_BETTER = "target_is_better"
    UNSPECIFIED = "unspecified"


class NumericScale(str, Enum):
    RAW = "raw"
    FRACTION = "fraction"
    PERCENT = "percent"


class TaskKind(str, Enum):
    PROJECT_EXTRACTION = "project_extraction"
    COMPARISON = "comparison"
    PLAN_GENERATION = "plan_generation"
    GRAPH_PROJECTION = "graph_projection"
    EXPORT = "export"


class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class ProjectionStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class PlanStatus(str, Enum):
    DRAFT = "draft"
    SAVED = "saved"
    SUPERSEDED = "superseded"


class DecisionStatus(str, Enum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    WITHDRAWN = "withdrawn"


ALLOWED_RECORD_STATUS_TRANSITIONS: dict[RecordStatus, frozenset[RecordStatus]] = {
    RecordStatus.CANDIDATE: frozenset(
        {RecordStatus.USER_CONFIRMED, RecordStatus.DISPUTED, RecordStatus.WITHDRAWN}
    ),
    RecordStatus.USER_CONFIRMED: frozenset(
        {RecordStatus.DISPUTED, RecordStatus.WITHDRAWN}
    ),
    RecordStatus.DISPUTED: frozenset(
        {RecordStatus.USER_CONFIRMED, RecordStatus.WITHDRAWN}
    ),
    RecordStatus.WITHDRAWN: frozenset({RecordStatus.CANDIDATE}),
}


class VersionRef(ContractModel):
    id: str = Field(min_length=1)
    version: int = Field(ge=1)


class NumericValue(ContractModel):
    value: float
    unit: str | None = None
    scale: NumericScale = NumericScale.RAW
    lower: float | None = None
    upper: float | None = None

    @model_validator(mode="after")
    def validate_range(self) -> NumericValue:
        values = [self.value, self.lower, self.upper]
        if any(v is not None and not math.isfinite(v) for v in values):
            raise ValueError("numeric values must be finite")
        if self.lower is not None and self.upper is not None and self.lower > self.upper:
            raise ValueError("lower must be less than or equal to upper")
        if self.lower is not None and self.value < self.lower:
            raise ValueError("value must not be below lower")
        if self.upper is not None and self.value > self.upper:
            raise ValueError("value must not exceed upper")
        return self


class NamedValue(ContractModel):
    name: str = Field(min_length=1)
    value: str | int | float | bool | None
    unit: str | None = None
    finding_status: FindingStatus = FindingStatus.REPORTED


class EvidenceLocator(ContractModel):
    page: int | None = Field(default=None, ge=1)
    heading: str | None = None
    start_offset: int | None = Field(default=None, ge=0)
    end_offset: int | None = Field(default=None, ge=0)
    table_id: str | None = None
    row_label: str | None = None
    column_label: str | None = None

    @model_validator(mode="after")
    def validate_offsets(self) -> EvidenceLocator:
        if (
            self.start_offset is not None
            and self.end_offset is not None
            and self.end_offset < self.start_offset
        ):
            raise ValueError("end_offset must not precede start_offset")
        return self


class EvidenceRef(ContractModel):
    id: str = Field(min_length=1)
    source_kind: SourceKind
    finding_status: FindingStatus
    kind: EvidenceKind
    paper_uid: str | None = None
    document_id: str | None = None
    document_version: str | None = None
    passage_id: str | None = None
    locator: EvidenceLocator | None = None
    quote: str | None = None
    note: str | None = None
    extraction_version: str | None = None
    conflict_group_id: str | None = None

    @model_validator(mode="after")
    def validate_reported_literature(self) -> EvidenceRef:
        if (
            self.source_kind == SourceKind.LITERATURE_REPORT
            and self.finding_status == FindingStatus.REPORTED
        ):
            if not self.paper_uid or not self.document_id or not self.document_version:
                raise ValueError(
                    "reported literature evidence requires paper and document version"
                )
            if not self.passage_id and not self.locator:
                raise ValueError(
                    "reported literature evidence requires a passage or locator"
                )
        if self.finding_status == FindingStatus.CONFLICTING and not self.conflict_group_id:
            raise ValueError("conflicting evidence requires conflict_group_id")
        return self


class FieldEvidence(ContractModel):
    field_path: str = Field(min_length=1)
    source_kind: SourceKind
    finding_status: FindingStatus
    evidence_ids: list[str] = Field(default_factory=list)
    note: str | None = None

    @model_validator(mode="after")
    def validate_evidence_binding(self) -> FieldEvidence:
        if (
            self.source_kind == SourceKind.LITERATURE_REPORT
            and self.finding_status in {FindingStatus.REPORTED, FindingStatus.CONFLICTING}
            and not self.evidence_ids
        ):
            raise ValueError("reported or conflicting literature fields require evidence_ids")
        return self


class ComputeConstraint(ContractModel):
    device_kind: str | None = None
    device_model: str | None = None
    device_count: int | None = Field(default=None, ge=1)
    memory: NumericValue | None = None
    availability: str | None = None


class ProjectConstraints(ContractModel):
    version: int = Field(ge=1)
    objective: str = Field(min_length=1)
    allowed_datasets: list[str] = Field(default_factory=list)
    excluded_datasets: list[str] = Field(default_factory=list)
    required_metrics: list[str] = Field(default_factory=list)
    compute: list[ComputeConstraint] = Field(default_factory=list)
    time_budget: NumericValue | None = None
    cost_budget: NumericValue | None = None
    data_access: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ResearchProjectCreate(ContractModel):
    title: str = Field(min_length=1, max_length=300)
    research_question: str = Field(min_length=1, max_length=4000)
    domain: DomainId
    constraints: ProjectConstraints


class ResearchProjectPatch(ContractModel):
    expected_version: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=300)
    research_question: str | None = Field(default=None, min_length=1, max_length=4000)
    status: ProjectStatus | None = None
    constraints: ProjectConstraints | None = None


class ResearchProject(ContractModel):
    id: str = Field(min_length=1)
    version: int = Field(ge=1)
    title: str = Field(min_length=1)
    research_question: str = Field(min_length=1)
    domain: DomainId
    domain_profile_version: str = Field(min_length=1)
    status: ProjectStatus = ProjectStatus.ACTIVE
    constraints: ProjectConstraints
    created_at: datetime
    updated_at: datetime


class PaperLinkCreate(ContractModel):
    expected_project_version: int = Field(ge=1)
    paper_uid: str = Field(min_length=1)
    role: PaperRole
    note: str | None = Field(default=None, max_length=4000)


class PaperLinkPatch(ContractModel):
    expected_version: int = Field(ge=1)
    role: PaperRole | None = None
    status: PaperLinkStatus | None = None
    note: str | None = Field(default=None, max_length=4000)


class PaperLink(ContractModel):
    id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    version: int = Field(ge=1)
    paper_uid: str = Field(min_length=1)
    role: PaperRole
    status: PaperLinkStatus = PaperLinkStatus.ACTIVE
    note: str | None = None
    linked_document_id: str | None = None
    linked_document_version: str | None = None
    created_at: datetime
    updated_at: datetime


class FactBase(ContractModel):
    id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    version: int = Field(ge=1)
    status: RecordStatus = RecordStatus.CANDIDATE
    source_kind: SourceKind
    finding_status: FindingStatus
    field_evidence: list[FieldEvidence] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class MethodCard(FactBase):
    paper_link_id: str | None = None
    name: str = Field(min_length=1)
    task: str | None = None
    summary: str | None = None
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    mechanisms: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class ExperimentSetting(FactBase):
    paper_link_id: str | None = None
    method_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    dataset: str | None = None
    dataset_version: str | None = None
    subset: str | None = None
    split: str | None = None
    evaluation_protocol: str | None = None
    preprocessing: list[str] = Field(default_factory=list)
    hyperparameters: list[NamedValue] = Field(default_factory=list)
    resources: list[NamedValue] = Field(default_factory=list)
    random_seed: str | None = None
    notes: list[str] = Field(default_factory=list)


class Measurement(FactBase):
    experiment_setting_id: str = Field(min_length=1)
    metric_name: str = Field(min_length=1)
    metric_scope: str | None = None
    value: NumericValue | None = None
    direction: MetricDirection = MetricDirection.UNSPECIFIED
    aggregation: str | None = None
    uncertainty: NumericValue | None = None
    sample_size: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_measurement_state(self) -> Measurement:
        if self.finding_status == FindingStatus.REPORTED and self.value is None:
            raise ValueError("reported measurement requires value")
        if self.finding_status != FindingStatus.REPORTED and self.value is not None:
            raise ValueError("non-reported measurement must not carry a value")
        return self


class CandidateBundle(ContractModel):
    contract_version: Literal["research-v1.1"] = CONTRACT_VERSION
    project_id: str = Field(min_length=1)
    paper_link_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    document_version: str = Field(min_length=1)
    extraction_version: str = Field(min_length=1)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    methods: list[MethodCard] = Field(default_factory=list)
    experiment_settings: list[ExperimentSetting] = Field(default_factory=list)
    measurements: list[Measurement] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ExtractionStartRequest(ContractModel):
    expected_project_version: int = Field(ge=1)
    document_id: str = Field(min_length=1)


class StatusTransitionRequest(ContractModel):
    expected_version: int = Field(ge=1)
    from_status: RecordStatus
    to_status: RecordStatus
    actor: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=4000)

    @model_validator(mode="after")
    def validate_transition(self) -> StatusTransitionRequest:
        if self.to_status not in ALLOWED_RECORD_STATUS_TRANSITIONS[self.from_status]:
            raise ValueError(
                f"status transition {self.from_status.value}->{self.to_status.value} is not allowed"
            )
        return self


class ComparisonCandidate(ContractModel):
    method_id: str = Field(min_length=1)
    experiment_setting_id: str = Field(min_length=1)
    measurement_ids: list[str] = Field(default_factory=list)


class ComparisonRequest(ContractModel):
    project_id: str = Field(min_length=1)
    project_version: int = Field(ge=1)
    domain: DomainId
    candidates: list[ComparisonCandidate] = Field(min_length=2)


class ComparisonDimension(ContractModel):
    name: str = Field(min_length=1)
    values: dict[str, str | int | float | bool | None]
    comparable: bool
    reason: str | None = None


class ComparisonGroup(ContractModel):
    id: str = Field(min_length=1)
    candidate_ids: list[str] = Field(default_factory=list)
    condition_signature: dict[str, str | int | float | bool | None]
    comparable: bool
    reasons: list[str] = Field(default_factory=list)


class ComparisonResult(ContractModel):
    contract_version: Literal["research-v1.1"] = CONTRACT_VERSION
    project_id: str
    project_version: int = Field(ge=1)
    dimensions: list[ComparisonDimension] = Field(default_factory=list)
    groups: list[ComparisonGroup] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ResearchDecisionCreate(ContractModel):
    expected_project_version: int = Field(ge=1)
    selected_method_id: str = Field(min_length=1)
    selected_experiment_setting_ids: list[str] = Field(min_length=1)
    considered_candidate_ids: list[str] = Field(default_factory=list)
    rationale: str = Field(min_length=1, max_length=8000)
    evidence_ids: list[str] = Field(default_factory=list)


class ResearchDecision(ContractModel):
    id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    version: int = Field(ge=1)
    status: DecisionStatus = DecisionStatus.ACTIVE
    source_kind: Literal[SourceKind.USER_INPUT] = SourceKind.USER_INPUT
    project_version: int = Field(ge=1)
    selected_method_id: str = Field(min_length=1)
    selected_experiment_setting_ids: list[str] = Field(min_length=1)
    considered_candidate_ids: list[str] = Field(default_factory=list)
    rationale: str = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)
    created_at: datetime


class ProtocolStep(ContractModel):
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    inputs: list[str] = Field(default_factory=list)
    procedure: list[str] = Field(default_factory=list)
    expected_observation: str | None = None
    acceptance_criteria: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class ValidationPlan(ContractModel):
    id: str | None = None
    project_id: str = Field(min_length=1)
    version: int = Field(ge=1)
    status: PlanStatus = PlanStatus.DRAFT
    title: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    hypothesis: str | None = None
    selected_method_id: str = Field(min_length=1)
    selected_experiment_setting_ids: list[str] = Field(min_length=1)
    assumptions: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    steps: list[ProtocolStep] = Field(default_factory=list)
    target_measurements: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    source_kind: SourceKind
    review_status: ReviewStatus = ReviewStatus.CURRENT
    review_reasons: list[str] = Field(default_factory=list)


class PlanSaveRequest(ContractModel):
    expected_project_version: int = Field(ge=1)
    expected_plan_version: int = Field(ge=0)
    plan: ValidationPlan


class PlanGenerateRequest(ContractModel):
    expected_project_version: int = Field(ge=1)
    decision_id: str = Field(min_length=1)
    decision_version: int = Field(ge=1)


class FrozenDocument(ContractModel):
    paper_link_id: str = Field(min_length=1)
    paper_uid: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    document_version: str = Field(min_length=1)
    content_hash: str = Field(min_length=1)


class ProjectSnapshot(ContractModel):
    id: str = Field(min_length=1)
    contract_version: Literal["research-v1.1"] = CONTRACT_VERSION
    project_id: str = Field(min_length=1)
    snapshot_version: int = Field(ge=1)
    frozen_project_version: int = Field(ge=1)
    frozen_constraint_version: int = Field(ge=1)
    frozen_domain_profile_version: str = Field(min_length=1)
    frozen_decision: VersionRef
    frozen_documents: list[FrozenDocument] = Field(min_length=1)
    frozen_facts: list[VersionRef] = Field(min_length=1)
    plan: ValidationPlan
    review_status: ReviewStatus = ReviewStatus.CURRENT
    review_reasons: list[str] = Field(default_factory=list)
    created_at: datetime


class SnapshotCreateRequest(ContractModel):
    expected_project_version: int = Field(ge=1)
    plan_id: str = Field(min_length=1)
    plan_version: int = Field(ge=1)


class ExtractionInput(ContractModel):
    contract_version: Literal["research-v1.1"] = CONTRACT_VERSION
    project_id: str
    paper_link: PaperLink
    document: FrozenDocument
    passages: list[dict[str, Any]] = Field(default_factory=list)
    domain: DomainId
    domain_profile_version: str


class DecisionValidationRequest(ContractModel):
    project: ResearchProject
    decision: ResearchDecisionCreate
    methods: list[MethodCard]
    experiment_settings: list[ExperimentSetting]
    measurements: list[Measurement]


class DecisionValidationResult(ContractModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    referenced_fact_ids: list[str] = Field(default_factory=list)


class PlanBuildInput(ContractModel):
    project: ResearchProject
    decision: ResearchDecision
    methods: list[MethodCard]
    experiment_settings: list[ExperimentSetting]
    measurements: list[Measurement]
    evidence: list[EvidenceRef]


class SnapshotBuildInput(PlanBuildInput):
    plan: ValidationPlan
    frozen_documents: list[FrozenDocument] = Field(min_length=1)


class GraphNode(ContractModel):
    id: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    label: str = Field(min_length=1)
    properties: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class GraphEdge(ContractModel):
    id: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    fact_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    properties: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class GraphProjection(ContractModel):
    contract_version: Literal["research-v1.1"] = CONTRACT_VERSION
    project_id: str
    snapshot_id: str
    snapshot_version: int = Field(ge=1)
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)


class GraphProjectionResult(ContractModel):
    project_id: str
    snapshot_id: str
    projected_nodes: int = Field(ge=0)
    projected_edges: int = Field(ge=0)


class GraphQuery(ContractModel):
    project_id: str
    snapshot_id: str
    node_ids: list[str] = Field(default_factory=list)
    kinds: list[str] = Field(default_factory=list)
    limit: int = Field(default=200, ge=1, le=1000)


class GraphQueryResult(ContractModel):
    project_id: str
    snapshot_id: str
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)


class ErrorDetail(ContractModel):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    retryable: bool = False
    fields: dict[str, str] = Field(default_factory=dict)
    current_version: int | None = Field(default=None, ge=1)
    request_id: str | None = None


class ErrorResponse(ContractModel):
    detail: ErrorDetail


class AsyncTask(ContractModel):
    id: str = Field(min_length=1)
    kind: TaskKind
    status: TaskStatus
    project_id: str = Field(min_length=1)
    progress: float | None = Field(default=None, ge=0, le=1)
    result: dict[str, Any] | None = None
    error: ErrorDetail | None = None
    created_at: datetime
    updated_at: datetime


class GraphProjectionStatus(ContractModel):
    project_id: str = Field(min_length=1)
    snapshot_id: str = Field(min_length=1)
    status: ProjectionStatus
    task_id: str | None = None
    attempt_count: int = Field(ge=0)
    last_error: str | None = None
    updated_at: datetime


class ProjectListResponse(ContractModel):
    items: list[ResearchProject] = Field(default_factory=list)
    next_cursor: str | None = None


class PaperLinkListResponse(ContractModel):
    items: list[PaperLink] = Field(default_factory=list)


class ProjectFactsResponse(ContractModel):
    methods: list[MethodCard] = Field(default_factory=list)
    experiment_settings: list[ExperimentSetting] = Field(default_factory=list)
    measurements: list[Measurement] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)


class DecisionListResponse(ContractModel):
    items: list[ResearchDecision] = Field(default_factory=list)


class PlanListResponse(ContractModel):
    items: list[ValidationPlan] = Field(default_factory=list)


class SnapshotListResponse(ContractModel):
    items: list[ProjectSnapshot] = Field(default_factory=list)


class DomainProfile(ContractModel):
    id: DomainId
    version: str = Field(min_length=1)
    label: str = Field(min_length=1)
    comparison_dimensions: list[str] = Field(min_length=1)
    common_metrics: list[str] = Field(default_factory=list)
    incompatibility_rules: list[str] = Field(default_factory=list)


DOMAIN_PROFILES: dict[DomainId, DomainProfile] = {
    DomainId.IMAGE_ANOMALY_DETECTION: DomainProfile(
        id=DomainId.IMAGE_ANOMALY_DETECTION,
        version="image-anomaly-v1",
        label="图像异常检测",
        comparison_dimensions=[
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
        common_metrics=["image_auroc", "pixel_auroc", "average_precision", "aupro"],
        incompatibility_rules=[
            "Do not merge image-level and pixel-level metrics.",
            "Do not rank results across different datasets, category scopes, or split protocols.",
        ],
    ),
    DomainId.TIME_SERIES_FORECASTING: DomainProfile(
        id=DomainId.TIME_SERIES_FORECASTING,
        version="time-series-forecasting-v1",
        label="时间序列预测",
        comparison_dimensions=[
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
        common_metrics=["mae", "rmse", "mape", "smape", "mase"],
        incompatibility_rules=[
            "Do not rank results across different horizons, frequencies, splits, or target scopes.",
            "Percentage metrics require the paper's zero-value handling to be known.",
        ],
    ),
}
