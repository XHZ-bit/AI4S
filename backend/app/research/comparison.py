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
    NumericValue,
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


_TIME_FACTORS = {
    "s": 1.0,
    "sec": 1.0,
    "second": 1.0,
    "seconds": 1.0,
    "min": 60.0,
    "minute": 60.0,
    "minutes": 60.0,
    "h": 3600.0,
    "hr": 3600.0,
    "hour": 3600.0,
    "hours": 3600.0,
    "day": 86400.0,
    "days": 86400.0,
}
_MEMORY_FACTORS = {
    "b": 1.0,
    "kb": 1000.0,
    "mb": 1000.0**2,
    "gb": 1000.0**3,
    "tb": 1000.0**4,
    "kib": 1024.0,
    "mib": 1024.0**2,
    "gib": 1024.0**3,
    "tib": 1024.0**4,
}


def _number(item: NamedValue | None) -> float | None:
    if item is None or isinstance(item.value, bool) or not isinstance(item.value, (int, float)):
        return None
    return float(item.value)


def _convert_pair(value: float, unit: str | None, budget: NumericValue, kind: str):
    source_unit = _norm_name(unit or "")
    target_unit = _norm_name(budget.unit or "")
    if source_unit == target_unit:
        return value, budget.value, f"同单位 {unit or '(未标单位)'}"
    factors = _TIME_FACTORS if kind == "time" else _MEMORY_FACTORS if kind == "memory" else {}
    if source_unit in factors and target_unit in factors:
        return (
            value * factors[source_unit],
            budget.value * factors[target_unit],
            f"按固定因子换算: 1 {source_unit}={factors[source_unit]} 基准单位, "
            f"1 {target_unit}={factors[target_unit]} 基准单位",
        )
    return None


def _resource(setting: ExperimentSetting, aliases: set[str]) -> NamedValue | None:
    return next(
        (item for item in setting.resources if _norm_name(item.name) in aliases), None
    )


def compare_candidates_to_constraints(
    project: ResearchProject, facts: CandidateBundle
) -> ComparisonResult:
    """Compare candidates with user constraints, separately from paper parity."""

    if project.id != facts.project_id:
        raise ValueError("project and facts belong to different projects")
    dimensions: list[ComparisonDimension] = []
    settings = [s for s in facts.experiment_settings if s.status != RecordStatus.WITHDRAWN]
    measurements_by_setting: dict[str, list[Measurement]] = {}
    for measurement in facts.measurements:
        measurements_by_setting.setdefault(measurement.experiment_setting_id, []).append(
            measurement
        )

    checks: dict[str, dict[str, str]] = {
        "dataset_policy": {},
        "required_metrics": {},
        "compute": {},
        "time_budget": {},
        "cost_budget": {},
        "data_access": {},
        "preferences": {},
    }
    details: dict[str, dict[str, list[str]]] = {
        name: {"conflicts": [], "missing": [], "evidence": [], "proof": []}
        for name in checks
    }
    allowed = {_norm_scalar(x) for x in project.constraints.allowed_datasets}
    excluded = {_norm_scalar(x) for x in project.constraints.excluded_datasets}
    required_metrics = {_norm_name(x) for x in project.constraints.required_metrics}
    for setting in settings:
        key = setting.id
        dataset = _norm_scalar(setting.dataset) if setting.dataset else None
        checks["dataset_policy"][key] = setting.dataset
        if dataset is None and (allowed or excluded):
            details["dataset_policy"]["missing"].append(f"{key}:dataset")
        elif dataset in excluded:
            details["dataset_policy"]["conflicts"].append(
                f"{key}:{setting.dataset} 在 excluded_datasets"
            )
        elif allowed and dataset not in allowed:
            details["dataset_policy"]["conflicts"].append(
                f"{key}:{setting.dataset} 不在 allowed_datasets"
            )
        dataset_evidence, _ = _evidence_for_paths(setting, ["dataset"])
        details["dataset_policy"]["evidence"].extend(dataset_evidence)

        found_metrics = {
            _norm_name(m.metric_name) for m in measurements_by_setting.get(key, [])
        }
        checks["required_metrics"][key] = _display_list(sorted(found_metrics))
        missing_metrics = required_metrics - found_metrics
        if missing_metrics:
            # An absent extracted measurement does not prove the method cannot
            # support it; retain as information insufficiency.
            details["required_metrics"]["missing"].append(
                f"{key}:{','.join(sorted(missing_metrics))}"
            )
        for measurement in measurements_by_setting.get(key, []):
            metric_evidence, _ = _evidence_for_paths(
                measurement, ["metric_name", "value"]
            )
            details["required_metrics"]["evidence"].extend(metric_evidence)

        compute_values = [
            f"{item.name}={item.value}{f' {item.unit}' if item.unit else ''}"
            for item in setting.resources
            if _norm_name(item.name)
            in {"device", "device_kind", "device_model", "device_count", "memory", "gpu_memory"}
        ]
        checks["compute"][key] = _display_list(compute_values)
        if project.constraints.compute and not compute_values:
            details["compute"]["missing"].append(f"{key}:compute")
        elif project.constraints.compute:
            device_kind = _resource(setting, {"device", "device_kind"})
            device_count = _resource(setting, {"device_count"})
            reported_kind = (
                _norm_scalar(str(device_kind.value)) if device_kind else None
            )
            available_kinds = {
                _norm_scalar(item.device_kind)
                for item in project.constraints.compute
                if item.device_kind
            }
            if reported_kind and available_kinds and reported_kind not in available_kinds:
                details["compute"]["conflicts"].append(
                    f"{key}:需求设备 {device_kind.value} 不在用户可用设备 {sorted(available_kinds)}"
                )
            required_count = _number(device_count)
            available_counts = [
                item.device_count
                for item in project.constraints.compute
                if item.device_count is not None
            ]
            if (
                required_count is not None
                and available_counts
                and required_count > max(available_counts)
            ):
                details["compute"]["conflicts"].append(
                    f"{key}:需求设备数 {required_count:g} 超过用户可用 {max(available_counts)}"
                )
        compute_evidence, _ = _evidence_for_paths(
            setting, ["device", "device_kind", "device_count", "memory", "gpu_memory"]
        )
        details["compute"]["evidence"].extend(compute_evidence)

        for name, budget, aliases, kind in (
            (
                "time_budget",
                project.constraints.time_budget,
                {"training_time", "runtime", "time"},
                "time",
            ),
            (
                "cost_budget",
                project.constraints.cost_budget,
                {"training_cost", "cost"},
                "cost",
            ),
        ):
            resource = _resource(setting, aliases)
            checks[name][key] = (
                f"{resource.value}{f' {resource.unit}' if resource and resource.unit else ''}"
                if resource
                else None
            )
            if budget is None:
                continue
            resource_evidence, _ = _evidence_for_paths(setting, list(aliases))
            details[name]["evidence"].extend(resource_evidence)
            number = _number(resource)
            if resource is None or number is None:
                details[name]["missing"].append(f"{key}:{name}")
                continue
            converted = _convert_pair(number, resource.unit, budget, kind)
            if converted is None:
                details[name]["missing"].append(
                    f"{key}:无法证明 {resource.unit!r} 到 {budget.unit!r} 的换算"
                )
                continue
            candidate_value, budget_value, proof = converted
            details[name]["proof"].append(f"{key}:{proof}")
            if candidate_value > budget_value:
                details[name]["conflicts"].append(
                    f"{key}:{resource.value} {resource.unit or ''} 超过 "
                    f"{budget.value} {budget.unit or ''}"
                )

        checks["data_access"][key] = _display_list(project.constraints.data_access)
        if project.constraints.data_access and not setting.dataset:
            details["data_access"]["missing"].append(f"{key}:dataset/data_access")
        details["data_access"]["evidence"].extend(dataset_evidence)
        checks["preferences"][key] = _display_list(project.constraints.notes)

    for name, values in checks.items():
        conflicts = details[name]["conflicts"]
        missing = details[name]["missing"]
        evidence = sorted(set(details[name]["evidence"]))
        proof = details[name]["proof"]
        if conflicts:
            state = "已知冲突"
        elif missing:
            state = "信息不足"
        else:
            state = "尚未发现冲突"
        note = (
            "偏好仅用于提示，不作为硬约束淘汰候选。"
            if name == "preferences"
            else "未发现冲突不等于已证明可行。"
        )
        note += (
            f" 用户约束来源=user_input:{project.id}:constraints-v{project.constraints.version}."
        )
        if proof:
            note += " 换算依据=" + ", ".join(proof)
        dimensions.append(
            ComparisonDimension(
                name=name,
                values=values,
                comparable=not conflicts and not missing,
                reason=_reason(state, conflicts, missing, evidence, [], note),
            )
        )
    groups = [
        ComparisonGroup(
            id=f"constraint-{setting.id}",
            candidate_ids=[setting.id],
            condition_signature={
                "project_version": project.version,
                "constraint_version": project.constraints.version,
            },
            comparable=not any(
                setting.id in item
                for detail in details.values()
                for item in [*detail["conflicts"], *detail["missing"]]
            ),
            reasons=[
                item
                for detail in details.values()
                for item in [*detail["conflicts"], *detail["missing"]]
                if setting.id in item
            ],
        )
        for setting in settings
    ]
    return ComparisonResult(
        project_id=project.id,
        project_version=project.version,
        dimensions=dimensions,
        groups=groups,
        warnings=[
            "这是候选与用户课题约束的核对，不是文献实验可比性结论。",
            "不生成综合分数、默认最佳方法或自动路线选择。",
        ],
    )
