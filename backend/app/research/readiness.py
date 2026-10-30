"""Explain whether saved experiment settings can be compared, without ranking results."""

from itertools import combinations, product

from app.db import projects as store
from app.research.audit import project_audit
from app.research.constraints import evaluate_constraints, norm
from app.research.service import project_facts

MAX_PAIRS = 200


def _reported(measurement):
    return (measurement.status.value != "withdrawn"
            and measurement.finding_status.value == "reported"
            and measurement.value is not None)


def _metric_key(measurement):
    scale = measurement.value.scale.value
    if scale in {"fraction", "percent"}:
        scale = "fraction_or_percent"
    return (norm(measurement.metric_name), norm(measurement.metric_scope),
            measurement.direction.value if measurement.direction else None,
            scale, norm(measurement.value.unit), norm(measurement.aggregation))


def _condition_check(left, right, field, *, required=False):
    a, b = getattr(left, field), getattr(right, field)
    if field == "preprocessing":
        a, b = "; ".join(a), "; ".join(b)
    if not required and not a and not b:
        return None
    status = "missing" if not a or not b else "conflict" if norm(a) != norm(b) else "match"
    return {"field": field, "status": status, "left_value": a or None,
            "right_value": b or None,
            "reason": "至少一侧没有记录" if status == "missing" else
                      "两侧记录不一致" if status == "conflict" else "两侧记录一致"}


def _measurement_index(measurements):
    result = {}
    for item in measurements:
        if item.metric_scope:
            result.setdefault(_metric_key(item), []).append(item)
    return result


def _metric_checks(left_rows, right_rows):
    candidates = [(left, right) for left, right in product(left_rows, right_rows)
                  if norm(left.metric_name) == norm(right.metric_name)]
    if not candidates:
        return [{"field": "metric_name", "status": "conflict",
                 "left_value": ", ".join(sorted({item.metric_name for item in left_rows})),
                 "right_value": ", ".join(sorted({item.metric_name for item in right_rows})),
                 "reason": "没有同名报告指标"}]
    left, right = min(candidates, key=lambda pair: (
        sum(a != b for a, b in zip(_metric_key(pair[0]), _metric_key(pair[1]))),
        pair[0].id, pair[1].id))
    dimensions = (("metric_scope", left.metric_scope, right.metric_scope),
                  ("metric_direction", left.direction.value, right.direction.value),
                  ("metric_scale", left.value.scale.value, right.value.scale.value),
                  ("metric_unit", left.value.unit, right.value.unit),
                  ("metric_aggregation", left.aggregation, right.aggregation))
    result = []
    for field, a, b in dimensions:
        if field == "metric_scale" and {a, b} <= {"fraction", "percent"}:
            continue
        if norm(a) == norm(b):
            continue
        missing = not a or not b or field == "metric_direction" and "unspecified" in {a, b}
        result.append({"field": field, "status": "missing" if missing else "conflict",
                       "left_value": a, "right_value": b,
                       "reason": "至少一侧没有明确记录" if missing else "指标定义不一致"})
    return result


def _source_issue_codes(audit, fact_ids, evidence_ids, paper_uids):
    return sorted({issue["code"] for issue in audit["issues"]
                   if issue["severity"] == "blocking" and (
                       set(issue["fact_ids"]) & fact_ids
                       or set(issue["evidence_ids"]) & evidence_ids
                       or set(issue["paper_uids"]) & paper_uids)})


def _evidence_ids(records):
    return {identity for record in records for field in record.field_evidence
            for identity in field.evidence_ids}


def _binding_gaps(setting, measurements):
    gaps = []
    for record, fields in [(setting, ("dataset", "dataset_version", "subset", "split",
                                    "evaluation_protocol", "preprocessing")),
                           *((item, ("metric_name", "metric_scope", "value", "aggregation",
                                     "sample_size")) for item in measurements)]:
        if record.source_kind.value != "literature_report":
            continue
        bound = {field.field_path for field in record.field_evidence
                 if field.finding_status.value == "reported" and field.evidence_ids}
        for field in fields:
            if getattr(record, field) and field not in bound:
                gaps.append(f"{record.id}.{field}")
    return sorted(gaps)


def comparison_readiness(conn, project_id: str) -> dict:
    project = store.get_project(conn, project_id)
    if project is None:
        raise store.NotFoundError("项目不存在")
    facts = project_facts(conn, project_id)
    active_links = [item for item in store.list_paper_links(conn, project_id)
                    if item.status.value == "active"]
    links = {item.id for item in active_links}
    paper_by_link = {item.id: item.paper_uid for item in active_links}
    methods = {item.id: item for item in facts.methods
               if item.status.value != "withdrawn"
               and (not item.paper_link_id or item.paper_link_id in links)}
    settings = sorted((item for item in facts.experiment_settings
                       if item.status.value != "withdrawn" and item.method_id in methods
                       and (not item.paper_link_id or item.paper_link_id in links)),
                      key=lambda item: item.id)
    measurements = [item for item in facts.measurements if _reported(item)]
    by_setting = {setting.id: [item for item in measurements
                               if item.experiment_setting_id == setting.id]
                  for setting in settings}
    constraints = {item.id: item for item in evaluate_constraints(
        project, list(methods.values()), settings, measurements)}
    audit = project_audit(conn, project_id)
    candidates = []
    source_gaps_by_setting = {}
    binding_gaps_by_setting = {}
    for setting in settings:
        missing = [field for field in ("dataset", "split", "evaluation_protocol")
                   if not getattr(setting, field)]
        if not by_setting[setting.id]:
            missing.append("reported_measurement")
        elif not any(item.metric_scope for item in by_setting[setting.id]):
            missing.append("metric_scope")
        records = [setting, methods[setting.method_id], *by_setting[setting.id]]
        paper_uids = {paper_by_link[record.paper_link_id] for record in records
                      if getattr(record, "paper_link_id", None) in paper_by_link}
        source_gaps = _source_issue_codes(
            audit, {record.id for record in records}, _evidence_ids(records), paper_uids)
        source_gaps_by_setting[setting.id] = source_gaps
        binding_gaps = _binding_gaps(setting, by_setting[setting.id])
        binding_gaps_by_setting[setting.id] = binding_gaps
        checked = constraints[setting.id]
        candidates.append({"setting_id": setting.id, "method_id": setting.method_id,
                           "label": checked.label, "constraint_status": checked.status,
                           "missing_fields": missing, "source_gaps": source_gaps,
                           "evidence_gaps": binding_gaps,
                           "constraint_gaps": [{"dimension": check.dimension,
                                                "status": check.status, "reason": check.reason}
                                               for check in checked.checks
                                               if check.status in {"unknown", "conflict"}]})
    pairs = []
    total_pairs = len(settings) * (len(settings) - 1) // 2
    for left, right in combinations(settings, 2):
        if len(pairs) >= MAX_PAIRS:
            break
        checks = [check for field, required in (("dataset", True), ("dataset_version", False),
                                                ("subset", False), ("split", True),
                                                ("evaluation_protocol", True),
                                                ("preprocessing", False))
                  if (check := _condition_check(left, right, field, required=required))]
        missing = [check["field"] for check in checks if check["status"] == "missing"]
        conflicts = [check["field"] for check in checks if check["status"] == "conflict"]
        left_metrics = _measurement_index(by_setting[left.id])
        right_metrics = _measurement_index(by_setting[right.id])
        common = sorted(left_metrics.keys() & right_metrics.keys())
        shared = []
        metric_checks = []
        if not by_setting[left.id] or not by_setting[right.id]:
            missing.append("reported_measurement")
        elif not common:
            metric_checks = _metric_checks(by_setting[left.id], by_setting[right.id])
            missing.extend(check["field"] for check in metric_checks if check["status"] == "missing")
            conflicts.extend(check["field"] for check in metric_checks if check["status"] == "conflict")
        for key in common:
            left_rows, right_rows = left_metrics[key], right_metrics[key]
            if len(left_rows) != 1 or len(right_rows) != 1:
                missing.append("unique_reported_measurement")
                continue
            left_metric, right_metric = left_rows[0], right_rows[0]
            if left_metric.sample_size is not None or right_metric.sample_size is not None:
                if left_metric.sample_size is None or right_metric.sample_size is None:
                    missing.append("sample_size")
                elif left_metric.sample_size != right_metric.sample_size:
                    conflicts.append("sample_size")
            shared.append({"metric_name": left_metric.metric_name,
                           "metric_scope": left_metric.metric_scope,
                           "scale": key[3], "unit": left_metric.value.unit,
                           "aggregation": left_metric.aggregation,
                           "left_measurement_id": left_metric.id,
                           "right_measurement_id": right_metric.id})
        source_gaps = sorted(set(source_gaps_by_setting[left.id]) |
                             set(source_gaps_by_setting[right.id]))
        binding_gaps = sorted(set(binding_gaps_by_setting[left.id]) |
                              set(binding_gaps_by_setting[right.id]))
        state = "conflict" if conflicts else "information_insufficient" if missing or source_gaps or binding_gaps else "comparable"
        pairs.append({"left_setting_id": left.id, "right_setting_id": right.id,
                      "status": state, "missing_fields": sorted(set(missing)),
                      "conflicting_fields": sorted(set(conflicts)),
                      "condition_checks": checks, "metric_checks": metric_checks,
                      "shared_metrics": shared,
                      "source_gaps": source_gaps, "evidence_gaps": binding_gaps,
                      "next_action": "核对冲突条件并分别分析，勿合并数值" if conflicts else
                      "补齐缺失的原文条件或测量" if missing else
                      "先处理阻断级来源问题" if source_gaps else
                      "补齐关键字段的来源绑定" if binding_gaps else
                      "仅在列出的共同指标上并排查看报告值；不推断结果优劣"})
    return {"contract_version": "comparison-readiness-v1", "project_id": project_id,
            "input_fingerprint": audit["input_fingerprint"], "candidates": candidates,
            "pairs": pairs, "total_pairs": total_pairs,
            "truncated": total_pairs > len(pairs),
            "notice": "仅检查已保存的条件、共同指标与逐字段来源；可比较只适用于列出的指标，不排名，也不验证科研结论。"}
