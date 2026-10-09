"""One structured constraint evaluator for both comparison and scenarios."""
import math
import re
from app.assistant.models import Check, CandidateChecks, Reference


def norm(value):
    return re.sub(r"[\s_-]+", "", str(value or "").casefold())


def status(checks):
    values = {c.status for c in checks}
    return next((s for s in ("conflict", "unknown", "match") if s in values), "not_applicable")


def resource(setting, aliases):
    if any(f.finding_status != "reported" and ("resources" in f.field_path or any(norm(a) in norm(f.field_path) for a in aliases)) for f in setting.field_evidence):
        return None
    values = [r for r in setting.resources if norm(r.name) in {norm(a) for a in aliases}]
    if not values or any(r.finding_status != "reported" for r in values):
        return None
    if len({(str(r.value), norm(r.unit)) for r in values}) != 1:
        return None
    return values[0]


def number(item):
    if item is None or isinstance(item.value, bool):
        return None
    try:
        value = float(item.value)
        return value if math.isfinite(value) and value >= 0 else None
    except (TypeError, ValueError):
        return None


MEMORY = {"b": 1, "kb": 1000, "mb": 10**6, "gb": 10**9, "tb": 10**12, "kib": 1024, "mib": 2**20, "gib": 2**30, "tib": 2**40}
TIME = {"s": 1, "second": 1, "seconds": 1, "min": 60, "minute": 60, "minutes": 60,
        "h": 3600, "hr": 3600, "hour": 3600, "hours": 3600, "day": 86400, "days": 86400}


def bounded(dimension, item, budget, factors, references):
    if budget is None:
        return Check(dimension=dimension, status="not_applicable", reason="未设置此项上限")
    actual = number(item)
    a, b = norm(item.unit) if item else "", norm(budget.unit)
    display = f"{item.value} {item.unit or ''}" if item else None
    limit = f"{budget.value} {budget.unit or ''}"
    if actual is None or budget.value < 0 or (budget.lower is not None and budget.lower < 0) or budget.scale != "raw" or not a or not b or (a != b and not (a in factors and b in factors)):
        return Check(dimension=dimension, status="unknown", actual=display, limit=limit,
                     reason="需求缺失、冲突或无法证明单位换算", references=references)
    factor_a, factor_b = (factors.get(a, 1), factors.get(b, 1)) if a != b else (1, 1)
    required = actual * factor_a
    low = (budget.lower if budget.lower is not None else budget.value) * factor_b
    high = (budget.upper if budget.upper is not None else budget.value) * factor_b
    result = "match" if required <= low else "conflict" if required > high else "unknown"
    proof = "同单位比较" if a == b else f"按固定因子换算 {a} → {b}"
    reason = f"{proof}；" + {"match": "已报告需求未超过上限", "conflict": "已报告需求超过上限", "unknown": "需求处于预算不确定范围内"}[result]
    return Check(dimension=dimension, status=result, actual=display, limit=limit, reason=reason, references=references,
                 utilization=required / high if high > 0 else None)


def evaluate_constraints(project, methods, settings, measurements):
    constraints = project.constraints
    methods = {m.id: m for m in methods if m.status != "withdrawn"}
    result = []
    for setting in sorted(settings, key=lambda s: s.id):
        if setting.status == "withdrawn" or setting.method_id not in methods:
            continue
        refs = [Reference(kind="evidence", id=eid) for eid in sorted({e for f in setting.field_evidence for e in f.evidence_ids})]
        checks = []
        dataset = norm(setting.dataset)
        excluded = {norm(x) for x in constraints.excluded_datasets}
        allowed = {norm(x) for x in constraints.allowed_datasets}
        state = "not_applicable" if not excluded and not allowed else "unknown" if not dataset else "conflict" if dataset in excluded or (allowed and dataset not in allowed) else "match"
        if state != "not_applicable" and any(f.field_path == "dataset" and f.finding_status != "reported" for f in setting.field_evidence):
            state = "unknown"
        checks.append(Check(dimension="dataset_policy", status=state, actual=setting.dataset,
                            reason="排除列表 excluded_datasets 优先；按规范化名称匹配允许列表", references=refs))
        found = {norm(m.metric_name) for m in measurements if m.experiment_setting_id == setting.id and m.status != "withdrawn" and m.finding_status == "reported" and m.value is not None}
        missing = [m for m in constraints.required_metrics if norm(m) not in found]
        checks.append(Check(dimension="required_metrics", status="unknown" if missing else "match" if constraints.required_metrics else "not_applicable",
                            actual=", ".join(sorted(found)), reason=f"未找到有值测量: {', '.join(missing)}" if missing else "仅表示存在测量记录，不表示指标达标", references=refs))
        alternatives = []
        for device in constraints.compute:
            local = []
            kind = resource(setting, {"device", "device_kind"})
            model = resource(setting, {"device_model"})
            count = resource(setting, {"device_count"})
            for dim, reported, available in (("device_kind", kind, device.device_kind), ("device_model", model, device.device_model)):
                if available:
                    local.append(Check(dimension=dim, status="unknown" if reported is None else "match" if norm(reported.value) == norm(available) else "conflict",
                                       actual=str(reported.value) if reported else None, limit=available, reason=f"需求设备 {reported.value if reported else '未知'}；可用 {available}", references=refs))
            if device.device_count is not None:
                n = number(count)
                local.append(Check(dimension="device_count", status="unknown" if n is None else "match" if n <= device.device_count else "conflict",
                                   actual=n, limit=float(device.device_count), reason=f"需求设备数 {n:g}" if n is not None else "设备数量未报告", references=refs))
            if device.memory is not None:
                local.append(bounded("memory", resource(setting, {"memory", "gpu_memory", "vram"}), device.memory, MEMORY, refs))
            alternatives.append(local or [Check(dimension="compute", status="unknown", reason="设备配置没有可计算的字段")])
        if alternatives:
            # Each compute entry is a complete alternative; never mix CPU memory with GPU count.
            states = [status(x) for x in alternatives]
            chosen = states.index("match") if "match" in states else states.index("unknown") if "unknown" in states else 0
            checks.extend(alternatives[chosen])
        for dimension, aliases, budget, factors in (
            ("time_budget", {"training_time", "runtime", "time"}, constraints.time_budget, TIME),
            ("cost_budget", {"training_cost", "cost"}, constraints.cost_budget, {}),
        ):
            checks.append(bounded(dimension, resource(setting, aliases), budget, factors, refs))
        if constraints.data_access:
            checks.append(Check(dimension="data_access", status="unknown", actual=setting.dataset,
                                reason="访问说明不证明已取得数据使用权限或实际可访问", references=refs))
        if setting.status == "disputed" or setting.finding_status == "conflicting" or methods[setting.method_id].status == "disputed" or methods[setting.method_id].finding_status == "conflicting":
            checks.append(Check(dimension="source_state", status="unknown", reason="来源存在争议或冲突", references=refs))
        result.append(CandidateChecks(id=setting.id, method_id=setting.method_id,
                                     label=f"{methods[setting.method_id].name} / {setting.name}",
                                     method_status=methods[setting.method_id].status.value, setting_status=setting.status.value,
                                     status=status(checks), checks=checks))
    return result
