"""Convert frozen document passages into source-grounded research candidates.

The adapter is deliberately conservative:

* each text passage is extracted independently, preventing accidental
  cross-passage experiment assembly;
* every literature value is bound to an exact quote in the supplied passage;
* locators are copied from the input, never trusted from model output;
* tables produce manual-review evidence only and are never sent to the model;
* the module has no database imports and performs no persistence.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field

from app.research.model_runtime import ResearchModelError, structured_chat
from app.models.research import (
    CandidateBundle,
    EvidenceKind,
    EvidenceLocator,
    EvidenceRef,
    ExperimentSetting,
    ExtractionInput,
    FieldEvidence,
    FindingStatus,
    Measurement,
    MethodCard,
    MetricDirection,
    NamedValue,
    NumericScale,
    NumericValue,
    RecordStatus,
    SourceKind,
)
from app.research_extraction.prompts import (
    PROMPT_VERSION,
    SCHEMA_VERSION,
    build_messages,
)


EXTRACTION_VERSION = f"{PROMPT_VERSION}:{SCHEMA_VERSION}"


def chat(messages: list[dict], json_mode: bool = False) -> str:
    """Keep the local test seam while using the opt-in, bounded transport."""
    return structured_chat(
        messages, schema=_PassageExtraction.model_json_schema(),
        prompt_version=PROMPT_VERSION, schema_version=SCHEMA_VERSION,
    )


class CandidateExtractionError(RuntimeError):
    """Base class for explicit extraction failures."""


class ExtractionInputError(CandidateExtractionError):
    """The frozen document or passage input is inconsistent."""


class ModelInvocationError(CandidateExtractionError):
    """The configured model could not produce a response."""


class ModelOutputError(CandidateExtractionError):
    """The model returned malformed or schema-invalid JSON."""


class ExtractionBatchError(CandidateExtractionError):
    """Every eligible text passage failed extraction."""

    def __init__(self, failures: list[str]):
        self.failures = list(failures)
        super().__init__("all eligible passages failed: " + "; ".join(failures))


class _PrivateModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class _RawEvidence(_PrivateModel):
    passage_id: str = Field(min_length=1)
    quote: str = Field(min_length=1)
    document_id: str | None = None
    page: int | None = Field(default=None, ge=1)
    heading: str | None = None


class _TextClaim(_PrivateModel):
    value: str | None = None
    finding_status: FindingStatus = FindingStatus.UNKNOWN
    evidence: list[_RawEvidence] = Field(default_factory=list)


class _TextListClaim(_PrivateModel):
    value: list[str] = Field(default_factory=list)
    finding_status: FindingStatus = FindingStatus.UNKNOWN
    evidence: list[_RawEvidence] = Field(default_factory=list)


class _ScalarClaim(_PrivateModel):
    value: str | int | float | bool | None = None
    finding_status: FindingStatus = FindingStatus.UNKNOWN
    evidence: list[_RawEvidence] = Field(default_factory=list)


class _NumericDraft(_PrivateModel):
    value: float
    unit: str | None = None
    scale: NumericScale = NumericScale.RAW
    lower: float | None = None
    upper: float | None = None


class _NumericClaim(_PrivateModel):
    value: _NumericDraft | None = None
    finding_status: FindingStatus = FindingStatus.UNKNOWN
    evidence: list[_RawEvidence] = Field(default_factory=list)


class _IntegerClaim(_PrivateModel):
    value: int | None = Field(default=None, ge=1)
    finding_status: FindingStatus = FindingStatus.UNKNOWN
    evidence: list[_RawEvidence] = Field(default_factory=list)


class _DirectionClaim(_PrivateModel):
    value: MetricDirection | None = None
    finding_status: FindingStatus = FindingStatus.UNKNOWN
    evidence: list[_RawEvidence] = Field(default_factory=list)


def _unknown_text() -> _TextClaim:
    return _TextClaim()


def _unknown_text_list() -> _TextListClaim:
    return _TextListClaim()


class _NamedDraft(_PrivateModel):
    name: _TextClaim
    value: _ScalarClaim = Field(default_factory=_ScalarClaim)
    unit: _TextClaim = Field(default_factory=_unknown_text)


class _MeasurementDraft(_PrivateModel):
    local_id: str = Field(min_length=1)
    metric_name: _TextClaim
    metric_scope: _TextClaim = Field(default_factory=_unknown_text)
    value: _NumericClaim = Field(default_factory=_NumericClaim)
    direction: _DirectionClaim = Field(default_factory=_DirectionClaim)
    aggregation: _TextClaim = Field(default_factory=_unknown_text)
    uncertainty: _NumericClaim = Field(default_factory=_NumericClaim)
    sample_size: _IntegerClaim = Field(default_factory=_IntegerClaim)


class _SettingDraft(_PrivateModel):
    local_id: str = Field(min_length=1)
    name: _TextClaim
    dataset: _TextClaim = Field(default_factory=_unknown_text)
    dataset_version: _TextClaim = Field(default_factory=_unknown_text)
    subset: _TextClaim = Field(default_factory=_unknown_text)
    split: _TextClaim = Field(default_factory=_unknown_text)
    evaluation_protocol: _TextClaim = Field(default_factory=_unknown_text)
    preprocessing: _TextListClaim = Field(default_factory=_unknown_text_list)
    hyperparameters: list[_NamedDraft] = Field(default_factory=list)
    resources: list[_NamedDraft] = Field(default_factory=list)
    random_seed: _TextClaim = Field(default_factory=_unknown_text)
    notes: _TextListClaim = Field(default_factory=_unknown_text_list)
    measurements: list[_MeasurementDraft] = Field(default_factory=list)


class _MethodDraft(_PrivateModel):
    local_id: str = Field(min_length=1)
    claim_role: Literal[
        "current_paper_method", "cited_method", "comparison_method", "unclear"
    ]
    attributed_to: _TextClaim = Field(default_factory=_unknown_text)
    name: _TextClaim
    task: _TextClaim = Field(default_factory=_unknown_text)
    summary: _TextClaim = Field(default_factory=_unknown_text)
    inputs: _TextListClaim = Field(default_factory=_unknown_text_list)
    outputs: _TextListClaim = Field(default_factory=_unknown_text_list)
    mechanisms: _TextListClaim = Field(default_factory=_unknown_text_list)
    assumptions: _TextListClaim = Field(default_factory=_unknown_text_list)
    limitations: _TextListClaim = Field(default_factory=_unknown_text_list)
    experiment_settings: list[_SettingDraft] = Field(default_factory=list)


class _PassageExtraction(_PrivateModel):
    methods: list[_MethodDraft] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class _Passage:
    id: str
    document_id: str
    text: str
    page: int | None
    heading: str | None
    kind: str
    ordinal: int | None
    metadata: dict[str, Any]


_PASSAGE_KEYS = {
    "id",
    "passage_id",
    "document_id",
    "text",
    "page",
    "heading",
    "section",
    "kind",
    "ordinal",
    "metadata",
    "metadata_json",
    "table_id",
    "row_label",
    "column_label",
}


def _stable_id(kind: str, *parts: object) -> str:
    raw = "\x1f".join(str(part) for part in parts)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return f"{kind}_{digest}"


def _normalize_passage(raw: dict[str, Any], document_id: str) -> _Passage:
    if not isinstance(raw, dict):
        raise ExtractionInputError("each passage must be an object")
    unknown = sorted(set(raw) - _PASSAGE_KEYS)
    if unknown:
        raise ExtractionInputError(f"passage contains unknown fields: {unknown}")

    pid = raw.get("passage_id") or raw.get("id")
    if raw.get("passage_id") and raw.get("id") and raw["passage_id"] != raw["id"]:
        raise ExtractionInputError("passage id and passage_id disagree")
    if not isinstance(pid, str) or not pid.strip():
        raise ExtractionInputError("passage requires a non-empty id")

    supplied_document_id = raw.get("document_id")
    if supplied_document_id is not None and supplied_document_id != document_id:
        raise ExtractionInputError(f"passage {pid} references a different document")
    text = raw.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ExtractionInputError(f"passage {pid} requires non-empty text")
    page = raw.get("page")
    if page is not None and (isinstance(page, bool) or not isinstance(page, int) or page < 1):
        raise ExtractionInputError(f"passage {pid} has an invalid page")
    ordinal = raw.get("ordinal")
    if ordinal is not None and (
        isinstance(ordinal, bool) or not isinstance(ordinal, int) or ordinal < 0
    ):
        raise ExtractionInputError(f"passage {pid} has an invalid ordinal")

    heading = raw.get("heading")
    section = raw.get("section")
    if heading is not None and section is not None and heading != section:
        raise ExtractionInputError(f"passage {pid} heading and section disagree")
    heading = heading if heading is not None else section
    if heading is not None and not isinstance(heading, str):
        raise ExtractionInputError(f"passage {pid} has an invalid heading")

    kind = raw.get("kind", "text")
    if not isinstance(kind, str) or not kind.strip():
        raise ExtractionInputError(f"passage {pid} has an invalid kind")
    kind = kind.strip().lower()

    metadata = raw.get("metadata", {})
    metadata_json = raw.get("metadata_json")
    if metadata_json is not None:
        if metadata:
            raise ExtractionInputError(f"passage {pid} supplies duplicate metadata")
        if not isinstance(metadata_json, str):
            raise ExtractionInputError(f"passage {pid} metadata_json must be a string")
        try:
            metadata = json.loads(metadata_json)
        except json.JSONDecodeError as exc:
            raise ExtractionInputError(f"passage {pid} metadata_json is invalid") from exc
    if not isinstance(metadata, dict):
        raise ExtractionInputError(f"passage {pid} metadata must be an object")
    for key in ("table_id", "row_label", "column_label"):
        if raw.get(key) is not None:
            metadata[key] = raw[key]

    return _Passage(
        id=pid,
        document_id=document_id,
        text=text,
        page=page,
        heading=heading,
        kind=kind,
        ordinal=ordinal,
        metadata=metadata,
    )


def _parse_model_output(raw: str) -> _PassageExtraction:
    if not isinstance(raw, str):
        raise ModelOutputError("model output is not text")
    text = raw.strip()
    match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        text = match.group(1)
    try:
        return _PassageExtraction.model_validate_json(text)
    except Exception as exc:
        raise ModelOutputError(f"invalid extraction JSON: {type(exc).__name__}") from None


def _validate_input(value: ExtractionInput) -> list[_Passage]:
    if not value.project_id.strip():
        raise ExtractionInputError("project_id must not be empty")
    if not value.domain_profile_version.strip():
        raise ExtractionInputError("domain_profile_version must not be empty")
    if value.paper_link.project_id != value.project_id:
        raise ExtractionInputError("paper link belongs to a different project")
    if value.document.paper_link_id != value.paper_link.id:
        raise ExtractionInputError("frozen document belongs to a different paper link")
    if value.document.paper_uid != value.paper_link.paper_uid:
        raise ExtractionInputError("frozen document paper_uid does not match paper link")
    if (
        value.paper_link.linked_document_id is not None
        and value.paper_link.linked_document_id != value.document.document_id
    ):
        raise ExtractionInputError("paper link and frozen document id disagree")
    if (
        value.paper_link.linked_document_version is not None
        and value.paper_link.linked_document_version != value.document.document_version
    ):
        raise ExtractionInputError("paper link and frozen document version disagree")
    if not value.passages:
        raise ExtractionInputError("extraction requires at least one passage")

    passages = [_normalize_passage(raw, value.document.document_id) for raw in value.passages]
    ids = [passage.id for passage in passages]
    if len(ids) != len(set(ids)):
        raise ExtractionInputError("passage ids must be unique within an extraction input")
    return passages


class _Assembler:
    def __init__(self, extraction_input: ExtractionInput):
        self.input = extraction_input
        self.evidence: dict[str, EvidenceRef] = {}
        self.methods: list[MethodCard] = []
        self.settings: list[ExperimentSetting] = []
        self.measurements: list[Measurement] = []
        self.warnings: list[str] = []

    def warn(self, code: str) -> None:
        self.warnings.append(code[:1000])

    def _evidence_kind(self, passage: _Passage) -> EvidenceKind:
        return {
            "table": EvidenceKind.TABLE,
            "figure": EvidenceKind.FIGURE,
            "caption": EvidenceKind.CAPTION,
        }.get(passage.kind, EvidenceKind.TEXT)

    def add_table_placeholder(self, passage: _Passage) -> None:
        evidence_id = _stable_id("ev", passage.document_id, passage.id, "table_manual")
        locator = EvidenceLocator(
            page=passage.page,
            heading=passage.heading,
            table_id=str(passage.metadata.get("table_id") or passage.id),
            row_label=_optional_string(passage.metadata.get("row_label")),
            column_label=_optional_string(passage.metadata.get("column_label")),
        )
        self.evidence[evidence_id] = EvidenceRef(
            id=evidence_id,
            source_kind=SourceKind.LITERATURE_REPORT,
            finding_status=FindingStatus.NOT_PARSED,
            kind=EvidenceKind.TABLE,
            paper_uid=self.input.document.paper_uid,
            document_id=self.input.document.document_id,
            document_version=self.input.document.document_version,
            passage_id=passage.id,
            locator=locator,
            note="Table content was not automatically extracted; manual confirmation or entry is required.",
            extraction_version=EXTRACTION_VERSION,
        )
        self.warn(f"table_requires_manual_confirmation:{passage.id}")

    def resolve_claim(
        self,
        passage: _Passage,
        claim: _TextClaim | _TextListClaim | _ScalarClaim | _NumericClaim | _IntegerClaim | _DirectionClaim,
        field_path: str,
        empty_value: Any,
    ) -> tuple[Any, FindingStatus, FieldEvidence]:
        status = claim.finding_status
        value = claim.value
        evidence_ids: list[str] = []

        if status in {FindingStatus.REPORTED, FindingStatus.CONFLICTING}:
            if value is None or value == []:
                self.warn(f"reported_value_missing:{passage.id}:{field_path}")
                status = FindingStatus.NOT_PARSED
                value = empty_value
            else:
                conflict_group_id = (
                    _stable_id("conflict", passage.id, field_path)
                    if status == FindingStatus.CONFLICTING
                    else None
                )
                for raw_evidence in claim.evidence:
                    evidence_id = self._add_validated_evidence(
                        passage,
                        raw_evidence,
                        field_path,
                        status,
                        conflict_group_id,
                    )
                    if evidence_id is not None:
                        evidence_ids.append(evidence_id)
                if not evidence_ids:
                    self.warn(f"evidence_not_located:{passage.id}:{field_path}")
                    status = FindingStatus.NOT_PARSED
                    value = empty_value
                elif status == FindingStatus.REPORTED and _requires_lexical_grounding(
                    field_path
                ):
                    quotes = [self.evidence[evidence_id].quote or "" for evidence_id in evidence_ids]
                    if not _lexically_grounded(value, quotes):
                        self.warn(
                            f"value_not_lexically_grounded:{passage.id}:{field_path}"
                        )
                        for evidence_id in evidence_ids:
                            self.evidence.pop(evidence_id, None)
                        evidence_ids = []
                        status = FindingStatus.NOT_PARSED
                        value = empty_value
                elif status == FindingStatus.CONFLICTING:
                    value = empty_value
        else:
            if value is not None and value != []:
                self.warn(f"non_reported_value_removed:{passage.id}:{field_path}")
            if claim.evidence:
                self.warn(f"non_reported_evidence_removed:{passage.id}:{field_path}")
            value = empty_value

        return value, status, FieldEvidence(
            field_path=field_path,
            source_kind=SourceKind.LITERATURE_REPORT,
            finding_status=status,
            evidence_ids=evidence_ids,
        )

    def _add_validated_evidence(
        self,
        passage: _Passage,
        raw: _RawEvidence,
        field_path: str,
        status: FindingStatus,
        conflict_group_id: str | None,
    ) -> str | None:
        if raw.passage_id != passage.id:
            self.warn(f"invalid_evidence_passage:{passage.id}:{field_path}")
            return None
        if raw.document_id is not None and raw.document_id != passage.document_id:
            self.warn(f"invalid_evidence_document:{passage.id}:{field_path}")
            return None
        if raw.page is not None and raw.page != passage.page:
            self.warn(f"invalid_evidence_page:{passage.id}:{field_path}")
            return None
        if raw.heading is not None and raw.heading != passage.heading:
            self.warn(f"invalid_evidence_heading:{passage.id}:{field_path}")
            return None
        start = passage.text.find(raw.quote)
        if start < 0:
            self.warn(f"quote_not_found:{passage.id}:{field_path}")
            return None
        end = start + len(raw.quote)
        evidence_id = _stable_id(
            "ev", passage.document_id, passage.id, field_path, status.value, start, end
        )
        self.evidence[evidence_id] = EvidenceRef(
            id=evidence_id,
            source_kind=SourceKind.LITERATURE_REPORT,
            finding_status=status,
            kind=self._evidence_kind(passage),
            paper_uid=self.input.document.paper_uid,
            document_id=self.input.document.document_id,
            document_version=self.input.document.document_version,
            passage_id=passage.id,
            locator=EvidenceLocator(
                page=passage.page,
                heading=passage.heading,
                start_offset=start,
                end_offset=end,
            ),
            quote=raw.quote,
            extraction_version=EXTRACTION_VERSION,
            conflict_group_id=conflict_group_id,
        )
        return evidence_id

    def add_passage_result(self, passage: _Passage, result: _PassageExtraction) -> None:
        for warning in result.warnings:
            self.warn(f"model_warning:{passage.id}:{warning}")
        seen_method_ids: set[str] = set()
        for method_index, draft in enumerate(result.methods):
            if draft.local_id in seen_method_ids:
                self.warn(f"duplicate_method_local_id:{passage.id}:{draft.local_id}")
                continue
            seen_method_ids.add(draft.local_id)
            self._add_method(passage, draft, method_index)

    def _add_method(self, passage: _Passage, draft: _MethodDraft, method_index: int) -> None:
        prefix = f"methods[{method_index}]"
        name, name_status, name_evidence = self.resolve_claim(
            passage, draft.name, f"{prefix}.name", None
        )
        if name_status != FindingStatus.REPORTED or not name:
            self.warn(f"method_skipped_without_grounded_name:{passage.id}:{draft.local_id}")
            return
        # Reject sentence-spanning names; never trim them into invented facts.
        # Decimal/model version dots and abbreviations are not sentence endings.
        if re.search(r"[。！？!?;；\r\n]|(?<!\b[A-Z])\.(?=\s+[A-Z])", name) or len(name) > 200:
            self.warn(f"method_name_boundary_ambiguous:{passage.id}:{draft.local_id}")
            return
        attribution, _, attribution_evidence = self.resolve_claim(
            passage, draft.attributed_to, f"{prefix}.attribution", None
        )
        name_evidence.note = json.dumps(
            {"claim_role": draft.claim_role, "attributed_to": attribution},
            ensure_ascii=False,
            sort_keys=True,
        )
        method_id = _stable_id(
            "method", passage.document_id, passage.id, draft.local_id, method_index
        )
        fields: list[FieldEvidence] = [name_evidence, attribution_evidence]
        task, _, field = self.resolve_claim(passage, draft.task, f"{prefix}.task", None)
        fields.append(field)
        summary, _, field = self.resolve_claim(
            passage, draft.summary, f"{prefix}.summary", None
        )
        fields.append(field)
        list_values: dict[str, list[str]] = {}
        for field_name in ("inputs", "outputs", "mechanisms", "assumptions", "limitations"):
            value, _, field = self.resolve_claim(
                passage,
                getattr(draft, field_name),
                f"{prefix}.{field_name}",
                [],
            )
            list_values[field_name] = value
            fields.append(field)

        self.methods.append(
            MethodCard(
                id=method_id,
                project_id=self.input.project_id,
                version=1,
                status=RecordStatus.CANDIDATE,
                source_kind=SourceKind.LITERATURE_REPORT,
                finding_status=FindingStatus.REPORTED,
                field_evidence=fields,
                paper_link_id=(
                    self.input.paper_link.id
                    if draft.claim_role == "current_paper_method"
                    else None
                ),
                name=name,
                task=task,
                summary=summary,
                inputs=list_values["inputs"],
                outputs=list_values["outputs"],
                mechanisms=list_values["mechanisms"],
                assumptions=list_values["assumptions"],
                limitations=list_values["limitations"],
            )
        )

        seen_setting_ids: set[str] = set()
        for setting_index, setting in enumerate(draft.experiment_settings):
            if setting.local_id in seen_setting_ids:
                self.warn(f"duplicate_setting_local_id:{passage.id}:{setting.local_id}")
                continue
            seen_setting_ids.add(setting.local_id)
            self._add_setting(
                passage,
                setting,
                method_id,
                draft.claim_role,
                f"{prefix}.experiment_settings[{setting_index}]",
                setting_index,
            )

    def _add_named_values(
        self,
        passage: _Passage,
        drafts: list[_NamedDraft],
        prefix: str,
        fields: list[FieldEvidence],
    ) -> list[NamedValue]:
        values: list[NamedValue] = []
        for index, draft in enumerate(drafts):
            name, name_status, name_field = self.resolve_claim(
                passage, draft.name, f"{prefix}[{index}].name", None
            )
            fields.append(name_field)
            if name_status != FindingStatus.REPORTED or not name:
                self.warn(f"named_value_skipped_without_name:{passage.id}:{prefix}[{index}]")
                continue
            value, value_status, value_field = self.resolve_claim(
                passage, draft.value, f"{prefix}[{index}].value", None
            )
            fields.append(value_field)
            unit, _, unit_field = self.resolve_claim(
                passage, draft.unit, f"{prefix}[{index}].unit", None
            )
            fields.append(unit_field)
            values.append(
                NamedValue(
                    name=name,
                    value=value,
                    unit=unit,
                    finding_status=value_status,
                )
            )
        return values

    def _add_setting(
        self,
        passage: _Passage,
        draft: _SettingDraft,
        method_id: str,
        claim_role: str,
        prefix: str,
        setting_index: int,
    ) -> None:
        name, name_status, name_field = self.resolve_claim(
            passage, draft.name, f"{prefix}.name", None
        )
        if name_status != FindingStatus.REPORTED or not name:
            self.warn(f"setting_skipped_without_grounded_name:{passage.id}:{draft.local_id}")
            return
        setting_id = _stable_id(
            "setting", passage.document_id, passage.id, method_id, draft.local_id, setting_index
        )
        fields = [name_field]
        scalar_values: dict[str, str | None] = {}
        for field_name in (
            "dataset",
            "dataset_version",
            "subset",
            "split",
            "evaluation_protocol",
            "random_seed",
        ):
            value, _, field = self.resolve_claim(
                passage,
                getattr(draft, field_name),
                f"{prefix}.{field_name}",
                None,
            )
            scalar_values[field_name] = value
            fields.append(field)
        preprocessing, _, field = self.resolve_claim(
            passage, draft.preprocessing, f"{prefix}.preprocessing", []
        )
        fields.append(field)
        notes, _, field = self.resolve_claim(
            passage, draft.notes, f"{prefix}.notes", []
        )
        fields.append(field)
        hyperparameters = self._add_named_values(
            passage, draft.hyperparameters, f"{prefix}.hyperparameters", fields
        )
        resources = self._add_named_values(
            passage, draft.resources, f"{prefix}.resources", fields
        )
        self.settings.append(
            ExperimentSetting(
                id=setting_id,
                project_id=self.input.project_id,
                version=1,
                status=RecordStatus.CANDIDATE,
                source_kind=SourceKind.LITERATURE_REPORT,
                finding_status=FindingStatus.REPORTED,
                field_evidence=fields,
                paper_link_id=(self.input.paper_link.id if claim_role == "current_paper_method" else None),
                method_id=method_id,
                name=name,
                dataset=scalar_values["dataset"],
                dataset_version=scalar_values["dataset_version"],
                subset=scalar_values["subset"],
                split=scalar_values["split"],
                evaluation_protocol=scalar_values["evaluation_protocol"],
                preprocessing=preprocessing,
                hyperparameters=hyperparameters,
                resources=resources,
                random_seed=scalar_values["random_seed"],
                notes=notes,
            )
        )

        seen_measurement_ids: set[str] = set()
        for measurement_index, measurement in enumerate(draft.measurements):
            if measurement.local_id in seen_measurement_ids:
                self.warn(
                    f"duplicate_measurement_local_id:{passage.id}:{measurement.local_id}"
                )
                continue
            seen_measurement_ids.add(measurement.local_id)
            self._add_measurement(
                passage,
                measurement,
                setting_id,
                f"{prefix}.measurements[{measurement_index}]",
                measurement_index,
            )

    def _add_measurement(
        self,
        passage: _Passage,
        draft: _MeasurementDraft,
        setting_id: str,
        prefix: str,
        measurement_index: int,
    ) -> None:
        metric_name, name_status, name_field = self.resolve_claim(
            passage, draft.metric_name, f"{prefix}.metric_name", None
        )
        if name_status != FindingStatus.REPORTED or not metric_name:
            self.warn(
                f"measurement_skipped_without_grounded_metric:{passage.id}:{draft.local_id}"
            )
            return
        fields = [name_field]
        metric_scope, _, field = self.resolve_claim(
            passage, draft.metric_scope, f"{prefix}.metric_scope", None
        )
        fields.append(field)
        numeric, value_status, field = self.resolve_claim(
            passage, draft.value, f"{prefix}.value", None
        )
        fields.append(field)
        direction, _, field = self.resolve_claim(
            passage, draft.direction, f"{prefix}.direction", None
        )
        fields.append(field)
        aggregation, _, field = self.resolve_claim(
            passage, draft.aggregation, f"{prefix}.aggregation", None
        )
        fields.append(field)
        uncertainty, _, field = self.resolve_claim(
            passage, draft.uncertainty, f"{prefix}.uncertainty", None
        )
        fields.append(field)
        sample_size, _, field = self.resolve_claim(
            passage, draft.sample_size, f"{prefix}.sample_size", None
        )
        fields.append(field)

        value = NumericValue(**numeric.model_dump()) if numeric is not None else None
        uncertainty_value = (
            NumericValue(**uncertainty.model_dump()) if uncertainty is not None else None
        )
        measurement_id = _stable_id(
            "measurement",
            passage.document_id,
            passage.id,
            setting_id,
            draft.local_id,
            measurement_index,
        )
        self.measurements.append(
            Measurement(
                id=measurement_id,
                project_id=self.input.project_id,
                version=1,
                status=RecordStatus.CANDIDATE,
                source_kind=SourceKind.LITERATURE_REPORT,
                finding_status=value_status,
                field_evidence=fields,
                experiment_setting_id=setting_id,
                metric_name=metric_name,
                metric_scope=metric_scope,
                value=value,
                direction=direction or MetricDirection.UNSPECIFIED,
                aggregation=aggregation,
                uncertainty=uncertainty_value,
                sample_size=sample_size,
            )
        )

    def bundle(self) -> CandidateBundle:
        if not self.methods and not self.settings and not self.measurements:
            self.warn("no_automatic_candidates_found")
        return CandidateBundle(
            project_id=self.input.project_id,
            paper_link_id=self.input.paper_link.id,
            document_id=self.input.document.document_id,
            document_version=self.input.document.document_version,
            extraction_version=EXTRACTION_VERSION,
            evidence=list(self.evidence.values()),
            methods=self.methods,
            experiment_settings=self.settings,
            measurements=self.measurements,
            warnings=self.warnings,
        )


def _optional_string(value: Any) -> str | None:
    return str(value) if value is not None else None


def _requires_lexical_grounding(field_path: str) -> bool:
    if field_path.endswith(
        (".name", ".dataset", ".dataset_version", ".metric_name", ".random_seed")
    ):
        return True
    return field_path.endswith(".value") and any(
        marker in field_path
        for marker in (".measurements[", ".resources[", ".hyperparameters[")
    )


def _lexically_grounded(value: Any, quotes: list[str]) -> bool:
    joined = " ".join(quotes)
    normalized_quote = re.sub(r"\s+", " ", joined.casefold()).strip()
    if isinstance(value, _NumericDraft):
        numbers = [
            float(token.replace(",", ""))
            for token in re.findall(r"[-+]?\d[\d,]*(?:\.\d+)?", joined)
        ]
        required = [value.value]
        if value.lower is not None:
            required.append(value.lower)
        if value.upper is not None:
            required.append(value.upper)
        return all(any(abs(number - item) <= 1e-12 for number in numbers) for item in required)
    if isinstance(value, bool):
        return str(value).casefold() in normalized_quote
    if isinstance(value, (int, float)):
        return _lexically_grounded(_NumericDraft(value=float(value)), quotes)
    if isinstance(value, str):
        normalized_value = re.sub(r"\s+", " ", value.casefold()).strip()
        return bool(normalized_value) and normalized_value in normalized_quote
    if isinstance(value, list):
        return all(_lexically_grounded(item, quotes) for item in value)
    return False


def extract_candidates(input: ExtractionInput) -> CandidateBundle:
    """Extract passage-scoped candidates without reading or writing persistence.

    Text passages may fail independently.  A partial bundle carries explicit
    ``passage_failed`` warnings.  If every eligible text passage fails, an
    :class:`ExtractionBatchError` is raised rather than returning an empty
    success-looking bundle.  Table-only inputs return NOT_PARSED evidence and a
    manual-confirmation warning without invoking the model.
    """

    if not isinstance(input, ExtractionInput):
        try:
            input = ExtractionInput.model_validate(input)
        except Exception as exc:
            raise ExtractionInputError(f"invalid ExtractionInput: {exc}") from exc
    passages = _validate_input(input)
    assembler = _Assembler(input)
    eligible = 0
    succeeded = 0
    failures: list[str] = []

    for passage in passages:
        if passage.kind == "table":
            assembler.add_table_placeholder(passage)
            continue
        eligible += 1
        passage_payload = {
            "document_id": passage.document_id,
            "passage_id": passage.id,
            "text": passage.text,
            "page": passage.page,
            "heading": passage.heading,
            "kind": passage.kind,
        }
        try:
            raw = chat(
                build_messages(
                    passage=passage_payload,
                    domain=input.domain,
                    domain_profile_version=input.domain_profile_version,
                    output_schema=_PassageExtraction.model_json_schema(),
                ),
                json_mode=True,
            )
        except ResearchModelError:
            # Authorization/budget/transport failures must not look like a
            # successfully completed extraction of an empty/partial document.
            raise
        except (TimeoutError, httpx.TimeoutException) as exc:
            failure = f"model_timeout:{passage.id}:{type(exc).__name__}"
            failures.append(failure)
            assembler.warn(f"passage_failed:{failure}")
            continue
        except (RuntimeError, ValueError, httpx.HTTPError) as exc:
            failure = f"model_unavailable:{passage.id}:{type(exc).__name__}"
            failures.append(failure)
            assembler.warn(f"passage_failed:{failure}")
            continue
        try:
            result = _parse_model_output(raw)
        except ModelOutputError as exc:
            failure = f"invalid_model_output:{passage.id}:{exc}"
            failures.append(failure)
            assembler.warn(f"passage_failed:{failure}")
            continue
        assembler.add_passage_result(passage, result)
        succeeded += 1

    if eligible and not succeeded:
        if failures and all(failure.startswith("model_timeout:") for failure in failures):
            raise ModelInvocationError("all model calls timed out: " + "; ".join(failures))
        if failures and all(failure.startswith("model_unavailable:") for failure in failures):
            raise ModelInvocationError("model unavailable: " + "; ".join(failures))
        if len(failures) == 1 and failures[0].startswith("invalid_model_output:"):
            raise ModelOutputError(failures[0])
        raise ExtractionBatchError(failures)
    return assembler.bundle()
