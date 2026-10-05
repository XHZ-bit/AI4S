"""Pure validation for user-authored research route decisions."""

from __future__ import annotations

from app.models.research import (
    DecisionValidationRequest,
    DecisionValidationResult,
    ExperimentSetting,
    FindingStatus,
    RecordStatus,
)


def _add_unique(target: list[str], message: str) -> None:
    if message not in target:
        target.append(message)


def _review_warnings(fact, warnings: list[str]) -> None:
    if fact.status == RecordStatus.CANDIDATE:
        _add_unique(warnings, f"事实 {fact.id} 仍是 candidate，尚未人工确认")
    elif fact.status == RecordStatus.DISPUTED:
        _add_unique(warnings, f"事实 {fact.id} 存在争议，选择被保留但需复核")
    if fact.finding_status != FindingStatus.REPORTED:
        _add_unique(
            warnings,
            f"事实 {fact.id} 的查找状态为 {fact.finding_status.value}，存在未决信息",
        )
    for binding in fact.field_evidence:
        if binding.finding_status == FindingStatus.CONFLICTING:
            _add_unique(
                warnings,
                f"事实 {fact.id} 字段 {binding.field_path} 存在相互冲突的证据",
            )


def validate_decision(request: DecisionValidationRequest) -> DecisionValidationResult:
    """Validate a user choice without selecting or ranking on the user's behalf."""

    project = request.project
    decision = request.decision
    errors: list[str] = []
    warnings: list[str] = []
    if decision.expected_project_version != project.version:
        errors.append(
            f"项目版本冲突: expected={decision.expected_project_version}, current={project.version}"
        )

    methods = {item.id: item for item in request.methods}
    settings = {item.id: item for item in request.experiment_settings}
    measurements = {item.id: item for item in request.measurements}
    all_facts = {**methods, **settings, **measurements}
    if len(all_facts) != len(methods) + len(settings) + len(measurements):
        errors.append("方法、实验设置和测量之间存在重复事实 ID")
    for fact in all_facts.values():
        if fact.project_id != project.id:
            errors.append(f"事实 {fact.id} 不属于当前课题 {project.id}")

    method = methods.get(decision.selected_method_id)
    if method is None:
        errors.append("所选方法不存在于当前候选事实")
    elif method.status == RecordStatus.WITHDRAWN:
        errors.append("所选方法已撤回")
    else:
        _review_warnings(method, warnings)

    selected_settings: list[ExperimentSetting] = []
    if len(set(decision.selected_experiment_setting_ids)) != len(
        decision.selected_experiment_setting_ids
    ):
        errors.append("所选实验设置 ID 重复")
    for setting_id in decision.selected_experiment_setting_ids:
        setting = settings.get(setting_id)
        if setting is None:
            errors.append(f"所选实验设置不存在: {setting_id}")
            continue
        if setting.status == RecordStatus.WITHDRAWN:
            errors.append(f"所选实验设置已撤回: {setting_id}")
            continue
        if method is not None and setting.method_id != method.id:
            errors.append(f"实验设置 {setting_id} 不属于所选方法 {method.id}")
        selected_settings.append(setting)
        _review_warnings(setting, warnings)

    considered: list[object] = []
    for fact_id in decision.considered_candidate_ids:
        fact = all_facts.get(fact_id)
        if fact is None:
            errors.append(f"被考虑候选不存在于当前课题: {fact_id}")
        else:
            considered.append(fact)
            if fact.status == RecordStatus.WITHDRAWN:
                warnings.append(f"被考虑候选 {fact_id} 已撤回，保留历史引用但不得选中")

    selected_setting_ids = {setting.id for setting in selected_settings}
    selected_measurements = [
        item
        for item in measurements.values()
        if item.experiment_setting_id in selected_setting_ids
    ]
    for measurement in selected_measurements:
        if measurement.status != RecordStatus.WITHDRAWN:
            _review_warnings(measurement, warnings)
    if not selected_measurements:
        warnings.append("所选实验设置没有可用测量，指标范围与验收阈值仍待用户确定")

    required_metrics = {item.casefold() for item in project.constraints.required_metrics}
    reported_metrics = {
        item.metric_name.casefold()
        for item in selected_measurements
        if item.status != RecordStatus.WITHDRAWN
    }
    missing_metrics = sorted(required_metrics - reported_metrics)
    if missing_metrics:
        warnings.append("课题要求的指标尚缺少已关联测量: " + ", ".join(missing_metrics))

    if project.constraints.compute:
        for setting in selected_settings:
            if not setting.resources:
                warnings.append(f"实验设置 {setting.id} 未报告资源信息，无法核对计算硬约束")

    referenced = [decision.selected_method_id, *decision.selected_experiment_setting_ids]
    referenced.extend(decision.considered_candidate_ids)
    referenced.extend(item.id for item in selected_measurements)
    referenced = list(dict.fromkeys(referenced))

    evidence_owners: dict[str, set[str]] = {}
    for fact in all_facts.values():
        for binding in fact.field_evidence:
            for evidence_id in binding.evidence_ids:
                evidence_owners.setdefault(evidence_id, set()).add(fact.id)
    selected_or_considered = set(referenced)
    for evidence_id in decision.evidence_ids:
        owners = evidence_owners.get(evidence_id)
        if not owners:
            errors.append(f"决策证据不存在于当前课题事实: {evidence_id}")
        elif not owners & selected_or_considered:
            errors.append(f"决策证据未绑定到所选或被考虑候选: {evidence_id}")

    if not decision.evidence_ids:
        warnings.append("用户决策尚未绑定证据；理由仍保留为 user_input，不改写成论文结论")
    warnings.append("最终路线来自用户选择；校验结果不会自动替用户更换候选。")
    return DecisionValidationResult(
        valid=not errors,
        errors=errors,
        warnings=list(dict.fromkeys(warnings)),
        referenced_fact_ids=referenced,
    )
