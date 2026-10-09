"""Deterministic comparison of project candidates and literature experiments.

No score or winner is produced.  Candidate-to-project constraints and
experiment-to-experiment compatibility are deliberately separate operations.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Iterable

from app.models.research import (
    CandidateBundle,
    ComparisonCandidate,
    ComparisonDimension,
    ComparisonGroup,
    ComparisonRequest,
    ComparisonResult,
    DomainId,
    ExperimentSetting,
    FindingStatus,
    Measurement,
    MethodCard,
    NamedValue,
    NumericScale,
    RecordStatus,
    ResearchProject,
)
from app.research.domain_profiles import DOMAIN_DIMENSIONS


_IMAGE_HINTS = {
    "image_auroc",
    "pixel_auroc",
    "average_precision",
    "aupro",
    "image",
    "pixel",
}
_TIME_HINTS = {"mae", "rmse", "mape", "smape", "mase"}


@dataclass(frozen=True)
class _FieldValue:
    raw: str | int | float | bool | None
    normalized: str | int | float | bool | None
    evidence_ids: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()


@dataclass(frozen=True)
class _CandidateFacts:
    key: str
    selection: ComparisonCandidate
    method: MethodCard
    setting: ExperimentSetting
    measurements: tuple[Measurement, ...]


def _norm_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")


def _norm_scalar(value):
    if isinstance(value, str):
        return " ".join(value.casefold().split())
    return value


def _display_list(values: Iterable[object]) -> str | None:
    items = [str(item).strip() for item in values if str(item).strip()]
    return json.dumps(items, ensure_ascii=False) if items else None


def _evidence_for_paths(fact, tokens: Iterable[str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    normalized_tokens = {_norm_name(token) for token in tokens}
    evidence: set[str] = set()
    conflicts: set[str] = set()
    for binding in fact.field_evidence:
        path = _norm_name(binding.field_path)
        if any(token in path or path in token for token in normalized_tokens):
            evidence.update(binding.evidence_ids)
            if binding.finding_status == FindingStatus.CONFLICTING:
                conflicts.update(binding.evidence_ids or {binding.field_path})
    return tuple(sorted(evidence)), tuple(sorted(conflicts))


def _named_value(setting: ExperimentSetting, aliases: list[str]) -> _FieldValue:
    wanted = {_norm_name(alias) for alias in aliases}
    matches: list[NamedValue] = []
    for item in [*setting.hyperparameters, *setting.resources]:
        if _norm_name(item.name) in wanted:
            matches.append(item)
    evidence, conflicts = _evidence_for_paths(setting, aliases)
    if not matches:
        return _FieldValue(None, None, evidence, (aliases[0],), conflicts)
    reported = [item for item in matches if item.finding_status == FindingStatus.REPORTED]
    unresolved = [item for item in matches if item.finding_status != FindingStatus.REPORTED]
    if not reported:
        return _FieldValue(
            None,
            None,
            evidence,
            tuple(f"{item.name}:{item.finding_status.value}" for item in unresolved),
            conflicts,
        )
    raw_values = [
        f"{item.value}{f' {item.unit}' if item.unit else ''}" for item in reported
    ]
    normalized = tuple(
        (_norm_scalar(item.value), _norm_name(item.unit) if item.unit else None)
        for item in reported
    )
    if len(set(normalized)) > 1:
        conflicts = tuple(sorted({*conflicts, *raw_values}))
    raw = raw_values[0] if len(raw_values) == 1 else _display_list(raw_values)
    return _FieldValue(
        raw,
        json.dumps(normalized, ensure_ascii=False, sort_keys=True),
        evidence,
        tuple(f"{item.name}:{item.finding_status.value}" for item in unresolved),
        conflicts,
    )


def _direct_value(setting: ExperimentSetting, attribute: str) -> _FieldValue:
    value = getattr(setting, attribute)
    evidence, conflicts = _evidence_for_paths(setting, [attribute])
    if setting.finding_status != FindingStatus.REPORTED and value is None:
        return _FieldValue(
            None,
            None,
            evidence,
            (f"{attribute}:{setting.finding_status.value}",),
            conflicts,
        )
    if value is None or value == []:
        return _FieldValue(None, None, evidence, (attribute,), conflicts)
    if isinstance(value, list):
        raw = _display_list(value)
        normalized = json.dumps(
            sorted(_norm_scalar(item) for item in value), ensure_ascii=False
        )
    else:
        raw = value
        normalized = _norm_scalar(value)
    return _FieldValue(raw, normalized, evidence, (), conflicts)


def _measurement_value(
    measurements: tuple[Measurement, ...], attribute: str
) -> _FieldValue:
    if not measurements:
        return _FieldValue(None, None, (), (attribute,), ())
    values: list[object] = []
    normalized: list[object] = []
    evidence: set[str] = set()
    missing: set[str] = set()
    conflicts: set[str] = set()
    for measurement in measurements:
        ids, field_conflicts = _evidence_for_paths(measurement, [attribute, "value"])
        evidence.update(ids)
        conflicts.update(field_conflicts)
        if attribute == "metric_scale_and_unit":
            if measurement.value is None:
                missing.add(f"{measurement.id}.value")
                continue
            scale = measurement.value.scale
            unit = measurement.value.unit
            raw = f"{scale.value}{f' ({unit})' if unit else ''}"
            # fraction and percent have a mathematically defined conversion.  The
            # raw representation stays visible while equality uses fraction.
            canonical_scale = (
                "fraction"
                if scale in {NumericScale.FRACTION, NumericScale.PERCENT}
                else scale.value
            )
            values.append(raw)
            normalized.append((canonical_scale, _norm_name(unit) if unit else None))
            continue
        value = getattr(measurement, attribute)
        if value is None:
            missing.add(f"{measurement.id}.{attribute}")
            continue
        values.append(value.value if hasattr(value, "value") else value)
        normalized.append(_norm_scalar(value.value if hasattr(value, "value") else value))
        if measurement.finding_status == FindingStatus.CONFLICTING:
            conflicts.add(measurement.id)
    unique_raw = list(dict.fromkeys(str(v) for v in values))
    unique_normalized = sorted({json.dumps(v, ensure_ascii=False) for v in normalized})
    raw_value = unique_raw[0] if len(unique_raw) == 1 else _display_list(unique_raw)
    normalized_value = (
        unique_normalized[0]
        if len(unique_normalized) == 1
        else json.dumps(unique_normalized, ensure_ascii=False)
    )
    if not values:
        normalized_value = None
    return _FieldValue(
        raw_value,
        normalized_value,
        tuple(sorted(evidence)),
        tuple(sorted(missing)),
        tuple(sorted(conflicts)),
    )


def _extract(candidate: _CandidateFacts, source: str) -> _FieldValue:
    if source.startswith("setting."):
        return _direct_value(candidate.setting, source.split(".", 1)[1])
    if source.startswith("named:"):
        return _named_value(candidate.setting, source[6:].split(","))
    if source.startswith("measurements."):
        return _measurement_value(candidate.measurements, source.split(".", 1)[1])
    raise ValueError(f"unsupported comparison source: {source}")


def _candidate_facts(
    request: ComparisonRequest, facts: CandidateBundle
) -> list[_CandidateFacts]:
    if request.project_id != facts.project_id:
        raise ValueError("comparison request and facts belong to different projects")
    methods = {item.id: item for item in facts.methods}
    settings = {item.id: item for item in facts.experiment_settings}
    measurements = {item.id: item for item in facts.measurements}
    candidates: list[_CandidateFacts] = []
    seen: set[str] = set()
    for selection in request.candidates:
        method = methods.get(selection.method_id)
        setting = settings.get(selection.experiment_setting_id)
        if method is None or setting is None:
            raise ValueError("comparison candidate references a missing method or setting")
        if method.project_id != request.project_id or setting.project_id != request.project_id:
            raise ValueError("comparison candidate belongs to another project")
        if setting.method_id != method.id:
            raise ValueError("experiment setting does not belong to the selected method")
        if method.status == RecordStatus.WITHDRAWN or setting.status == RecordStatus.WITHDRAWN:
            raise ValueError("withdrawn facts cannot be compared")
        if setting.id in seen:
            raise ValueError("comparison candidate settings must be unique")
        seen.add(setting.id)
        selected_measurements: list[Measurement] = []
        for measurement_id in selection.measurement_ids:
            measurement = measurements.get(measurement_id)
            if measurement is None:
                raise ValueError("comparison candidate references a missing measurement")
            if measurement.experiment_setting_id != setting.id:
                raise ValueError("measurement does not belong to the selected setting")
            if measurement.status == RecordStatus.WITHDRAWN:
                raise ValueError("withdrawn measurements cannot be compared")
            selected_measurements.append(measurement)
        candidates.append(
            _CandidateFacts(
                key=setting.id,
                selection=selection,
                method=method,
                setting=setting,
                measurements=tuple(selected_measurements),
            )
        )
    return candidates


def _infer_domain(candidates: list[_CandidateFacts]) -> DomainId:
    hints: set[str] = set()
    named_fields: set[str] = set()
    for candidate in candidates:
        for measurement in candidate.measurements:
            hints.add(_norm_name(measurement.metric_name))
            if measurement.metric_scope:
                hints.add(_norm_name(measurement.metric_scope))
        named_fields.update(
            _norm_name(item.name)
            for item in [
                *candidate.setting.hyperparameters,
                *candidate.setting.resources,
            ]
        )
    image = bool(hints & _IMAGE_HINTS) or bool(
        named_fields
        & {"supervision", "anomaly_sample_usage", "image_resolution"}
    )
    time_series = bool(hints & _TIME_HINTS) or bool(
        named_fields & {"forecast_horizon", "context_length", "variable_mode"}
    )
    if image == time_series:
        raise ValueError(
            "cannot determine a single domain from CandidateBundle; "
            "ComparisonRequest must carry an explicit domain"
        )
    return (
        DomainId.IMAGE_ANOMALY_DETECTION
        if image
        else DomainId.TIME_SERIES_FORECASTING
    )


def _reason(
    state: str,
    differences: list[str],
    missing: list[str],
    evidence: list[str],
    conflicts: list[str],
    note: str,
) -> str:
    def text(items: list[str]) -> str:
        return ", ".join(items) if items else "无"

    return (
        f"判断={state}；差异={text(differences)}；缺失={text(missing)}；"
        f"证据={text(evidence)}；冲突证据={text(conflicts)}；说明={note}"
    )


def compare_conditions(
    request: ComparisonRequest, facts: CandidateBundle
) -> ComparisonResult:
    """Compare literature experiments without ranking their measurements."""

    candidates = _candidate_facts(request, facts)
    domain = request.domain
    dimensions: list[ComparisonDimension] = []
    extracted: dict[str, dict[str, _FieldValue]] = {}
    critical_names: list[str] = []
    for spec in DOMAIN_DIMENSIONS[domain]:
        name = spec["name"]
        if spec["critical"]:
            critical_names.append(name)
        values = {candidate.key: _extract(candidate, spec["source"]) for candidate in candidates}
        conflicting_evidence_ids = {
            item.id
            for item in facts.evidence
            if item.finding_status == FindingStatus.CONFLICTING
        }
        values = {
            candidate_id: _FieldValue(
                raw=value.raw,
                normalized=value.normalized,
                evidence_ids=value.evidence_ids,
                missing=value.missing,
                conflicts=tuple(
                    sorted(
                        {
                            *value.conflicts,
                            *(set(value.evidence_ids) & conflicting_evidence_ids),
                        }
                    )
                ),
            )
            for candidate_id, value in values.items()
        }
        extracted[name] = values
        known = {
            candidate_id: value.normalized
            for candidate_id, value in values.items()
            if value.normalized is not None
        }
        distinct = set(known.values())
        differences = (
            [f"{candidate_id}={values[candidate_id].raw}" for candidate_id in known]
            if len(distinct) > 1
            else []
        )
        missing = [
            f"{candidate_id}:{item}"
            for candidate_id, value in values.items()
            for item in value.missing
        ]
        evidence = sorted(
            {
                evidence_id
                for value in values.values()
                for evidence_id in value.evidence_ids
            }
        )
        conflicts = sorted(
            {item for value in values.values() for item in value.conflicts}
        )
        if differences and missing:
            state = "存在差异+信息不足"
        elif differences or conflicts:
            state = "存在差异"
        elif missing:
            state = "信息不足"
        else:
            state = "已核对维度一致"
        comparable = not differences and not missing and not conflicts
        dimensions.append(
            ComparisonDimension(
                name=name,
                values={candidate_id: value.raw for candidate_id, value in values.items()},
                comparable=comparable,
                reason=_reason(
                    state,
                    differences,
                    missing,
                    evidence,
                    conflicts,
                    "维度一致仅表示当前已核对字段一致，不代表科学上完全可比。",
                ),
            )
        )

    grouped: dict[str, list[str]] = {}
    signatures: dict[str, dict[str, object]] = {}
    group_reasons: dict[str, list[str]] = {}
    for candidate in candidates:
        signature: dict[str, object] = {}
        reasons: list[str] = []
        for name in critical_names:
            value = extracted[name][candidate.key]
            signature[name] = value.normalized
            if value.missing:
                reasons.append(f"{name} 信息不足: {', '.join(value.missing)}")
            if value.conflicts:
                reasons.append(f"{name} 存在冲突证据: {', '.join(value.conflicts)}")
        encoded = json.dumps(signature, ensure_ascii=False, sort_keys=True)
        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:12]
        grouped.setdefault(digest, []).append(candidate.key)
        signatures[digest] = signature
        group_reasons.setdefault(digest, []).extend(reasons)
    groups = [
        ComparisonGroup(
            id=f"condition-{digest}",
            candidate_ids=ids,
            condition_signature=signatures[digest],
            comparable=not group_reasons[digest],
            reasons=list(dict.fromkeys(group_reasons[digest])),
        )
        for digest, ids in grouped.items()
    ]
    warnings = [
        "结果只比较实验条件，不生成综合分数、排行榜或默认最佳方法。",
        "已核对维度一致不表示科学结论正确，也不表示未建模条件完全一致。",
    ]
    if len(groups) > 1:
        warnings.append("候选被分入不同条件签名组，禁止跨组按测量值排序。")
    return ComparisonResult(
        project_id=request.project_id,
        project_version=request.project_version,
        dimensions=dimensions,
        groups=groups,
        warnings=warnings,
    )


def compare_candidates_to_constraints(project: ResearchProject, facts: CandidateBundle) -> ComparisonResult:
    """Adapt the shared evaluator to the existing research-v1.1 response."""
    from app.research.constraints import evaluate_constraints

    if project.id != facts.project_id:
        raise ValueError("project and facts belong to different projects")
    candidates = evaluate_constraints(project, facts.methods, facts.experiment_settings, facts.measurements)
    dimensions = []
    names = ["dataset_policy", "required_metrics", "compute", "time_budget", "cost_budget", "data_access", "preferences"]
    for name in names:
        conflicts, missing, evidence, proof, values = [], [], [], [], {}
        for candidate in candidates:
            checks = [c for c in candidate.checks if c.dimension == name or (name == "compute" and c.dimension in {"device_kind", "device_model", "device_count", "memory", "compute"})]
            values[candidate.id] = "; ".join(str(c.actual) for c in checks if c.actual is not None) or None
            for check in checks:
                text = f"{candidate.id}:{name}:{check.reason}"
                if check.status == "conflict":
                    conflicts.append(text)
                elif check.status == "unknown":
                    missing.append(text)
                evidence.extend(r.id for r in check.references)
                proof.append(check.reason)
            if name == "preferences":
                values[candidate.id] = _display_list(project.constraints.notes)
        state = "已知冲突" if conflicts else "信息不足" if missing else "尚未发现冲突"
        note = "偏好仅用于提示，不作为硬约束淘汰候选。" if name == "preferences" else "未发现冲突不等于已证明可行。"
        note += f" 用户约束来源=user_input:{project.id}:constraints-v{project.constraints.version}. " + "; ".join(proof)
        dimensions.append(ComparisonDimension(name=name, values=values, comparable=not conflicts and not missing,
                                              reason=_reason(state, conflicts, missing, sorted(set(evidence)), [], note)))
    return ComparisonResult(project_id=project.id, project_version=project.version, dimensions=dimensions,
                            groups=[ComparisonGroup(id=f"constraint-{c.id}", candidate_ids=[c.id],
                                                    condition_signature={"project_version": project.version, "constraint_version": project.constraints.version},
                                                    comparable=c.status not in {"conflict", "unknown"},
                                                    reasons=[x.reason for x in c.checks if x.status in {"conflict", "unknown"}]) for c in candidates],
                            warnings=["这是候选与用户课题约束的核对，不是文献实验可比性结论。", "不生成综合分数、默认最佳方法或自动路线选择。"])
