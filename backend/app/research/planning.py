"""Pure, evidence-aware validation-plan and snapshot content assembly."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Any

from app.models.research import (
    DecisionStatus,
    EvidenceRef,
    ExperimentSetting,
    FindingStatus,
    MethodCard,
    PlanBuildInput,
    PlanStatus,
    ProjectSnapshot,
    ProtocolStep,
    RecordStatus,
    ReviewStatus,
    SnapshotBuildInput,
    SourceKind,
    ValidationPlan,
    VersionRef,
)
from app.research.suggestion_validation import validate_suggestion_steps


SuggestionProvider = Callable[[PlanBuildInput], dict[str, Any]]

def _facts(input: PlanBuildInput):
    methods = {item.id: item for item in input.methods}
    settings = {item.id: item for item in input.experiment_settings}
    measurements = {item.id: item for item in input.measurements}
    method = methods.get(input.decision.selected_method_id)
    if method is None or method.project_id != input.project.id:
        raise ValueError("decision references a method outside the project")
    if method.status == RecordStatus.WITHDRAWN:
        raise ValueError("withdrawn method cannot be used in a plan")
    selected_settings: list[ExperimentSetting] = []
    for setting_id in input.decision.selected_experiment_setting_ids:
        setting = settings.get(setting_id)
        if setting is None or setting.project_id != input.project.id:
            raise ValueError("decision references a setting outside the project")
        if setting.method_id != method.id:
            raise ValueError("selected setting does not belong to selected method")
        if setting.status == RecordStatus.WITHDRAWN:
            raise ValueError("withdrawn setting cannot be used in a plan")
        selected_settings.append(setting)
    selected_setting_ids = {item.id for item in selected_settings}
    selected_measurements = [
        item
        for item in measurements.values()
        if item.experiment_setting_id in selected_setting_ids
        and item.status != RecordStatus.WITHDRAWN
    ]
    return method, selected_settings, selected_measurements


def _fact_evidence_ids(fact) -> list[str]:
    return list(
        dict.fromkeys(
            evidence_id
            for binding in fact.field_evidence
            for evidence_id in binding.evidence_ids
        )
    )


def _source_label(source_kind: SourceKind) -> str:
    return {
        SourceKind.LITERATURE_REPORT: "文献报告",
        SourceKind.USER_INPUT: "用户设定",
        SourceKind.MODEL_SUGGESTION: "AI建议",
    }[source_kind]


def _template_steps(
    input: PlanBuildInput,
    method: MethodCard,
    settings: list[ExperimentSetting],
    measurements,
) -> list[ProtocolStep]:
    fact_evidence = list(
        dict.fromkeys(
            [
                *input.decision.evidence_ids,
                *_fact_evidence_ids(method),
                *(eid for setting in settings for eid in _fact_evidence_ids(setting)),
                *(eid for item in measurements for eid in _fact_evidence_ids(item)),
            ]
        )
    )
    datasets = [setting.dataset or "[待用户填写数据集]" for setting in settings]
    splits = [setting.split or "[待用户确认数据划分]" for setting in settings]
    protocols = [
        setting.evaluation_protocol or "[待用户确认评估协议]" for setting in settings
    ]
    metric_names = [item.metric_name for item in measurements] or ["[待用户填写指标]"]
    baselines = input.decision.considered_candidate_ids or ["[待用户选择基线]"]
    return [
        ProtocolStep(
            id="verify-evidence",
            title="核对路线与来源",
            purpose="在执行前区分论文报告、用户设定和 AI 建议，并确认未决事项。",
            inputs=[
                f"用户选择: {input.decision.selected_method_id}",
                f"用户理由: {input.decision.rationale}",
            ],
            procedure=[
                "用户逐项核对所选方法、实验设置与证据定位。",
                "对 disputed、conflicting、unknown、not_found、not_parsed 项保留未决标记。",
                "不把来源可定位解释为科学结论正确。",
            ],
            expected_observation="形成经用户确认的输入清单和未决清单。",
            acceptance_criteria=["所有进入执行阶段的关键字段均有来源或明确标为待填。"],
            evidence_ids=fact_evidence,
        ),
        ProtocolStep(
            id="freeze-data-and-split",
            title="冻结数据与划分",
            purpose="确保候选路线与基线使用同一可追溯数据范围和划分。",
            inputs=[
                f"数据: {', '.join(datasets)}",
                f"划分: {', '.join(splits)}",
                f"协议: {', '.join(protocols)}",
            ],
            procedure=[
                "用户确认可访问的数据版本、子集、预处理和划分。",
                "记录任何偏离文献设置的用户改动，不把改动写成论文报告。",
            ],
            expected_observation="获得可复核的数据与划分说明。",
            acceptance_criteria=["数据版本、子集、划分和评估协议均已填写或明确为未知。"],
            evidence_ids=fact_evidence,
        ),
        ProtocolStep(
            id="define-baselines-and-controls",
            title="确认基线与控制条件",
            purpose="在同一数据、划分、指标范围和聚合方式下定义首轮对照。",
            inputs=[f"候选基线事实 ID: {', '.join(baselines)}"],
            procedure=[
                "用户从已考虑候选中确认基线；系统不自动指定赢家。",
                "除被研究变量外，记录并固定其余可控条件。",
                "对缺失资源、随机种子或聚合方式保留待填项。",
            ],
            expected_observation="形成最小、可审阅的基线与控制变量清单。",
            acceptance_criteria=["不存在跨数据集、跨划分或跨指标范围的直接排名。"],
            evidence_ids=fact_evidence,
        ),
        ProtocolStep(
            id="run-minimal-validation",
            title="执行最小验证并保存产物",
            purpose="执行用户确认后的最小规模验证，不生成或声称官方命令。",
            inputs=[f"路线: {method.name}", f"实验设置: {', '.join(s.name for s in settings)}"],
            procedure=[
                "由用户补充并确认实际执行命令、环境和资源上限。",
                "保存配置、日志、随机种子、模型输出和失败记录。",
                "若资源、数据或实现不可用，明确记录失败，不填入预置成功结果。",
            ],
            expected_observation="获得真实运行产物，或获得可定位的失败记录。",
            acceptance_criteria=["每个实际结果均能追溯到本轮配置和原始产物。"],
            evidence_ids=fact_evidence,
        ),
        ProtocolStep(
            id="evaluate-and-decide",
            title="按预定指标复核",
            purpose="只在兼容条件内评估首轮结果，并由用户决定下一步。",
            inputs=[f"目标指标: {', '.join(metric_names)}"],
            procedure=[
                "保留指标范围、单位、聚合方式和不确定性。",
                "不把不同范围、协议或聚合方式的数值直接排序。",
                "由用户填写继续、调整或停止的判断，不由模型自动作最终决定。",
            ],
            expected_observation="形成带原始产物引用的首轮判断。",
            acceptance_criteria=["用户已填写定量或定性判断标准；未知项没有被猜测。"],
            evidence_ids=fact_evidence,
        ),
    ]


def build_plan_draft(
    input: PlanBuildInput,
    *,
    suggestion_provider: SuggestionProvider | None = None,
) -> ValidationPlan:
    """Build a reviewable draft; never save, execute, or claim measured results."""

    if input.decision.project_id != input.project.id:
        raise ValueError("decision belongs to another project")
    if input.decision.project_version != input.project.version:
        raise ValueError("decision was made against a different project version")
    if input.decision.status != DecisionStatus.ACTIVE:
        raise ValueError("only an active user decision can produce a plan draft")
    method, settings, measurements = _facts(input)
    evidence_by_id: dict[str, EvidenceRef] = {item.id: item for item in input.evidence}
    missing_decision_evidence = set(input.decision.evidence_ids) - set(evidence_by_id)
    if missing_decision_evidence:
        raise ValueError("decision references evidence outside the plan input")

    assumptions = [
        f"用户设定: {input.project.constraints.objective}",
        *[f"{_source_label(method.source_kind)}: {item}" for item in method.assumptions],
    ]
    unknowns: list[str] = []
    risks = [f"{_source_label(method.source_kind)}: {item}" for item in method.limitations]
    for setting in settings:
        if not setting.dataset:
            unknowns.append(f"实验设置 {setting.id} 的数据集未知")
        if not setting.split:
            unknowns.append(f"实验设置 {setting.id} 的数据划分未知")
        if not setting.evaluation_protocol:
            unknowns.append(f"实验设置 {setting.id} 的评估协议未知")
        if not setting.resources:
            unknowns.append(f"实验设置 {setting.id} 的资源需求未报告")
        if setting.finding_status != FindingStatus.REPORTED:
            unknowns.append(
                f"实验设置 {setting.id} 的查找状态为 {setting.finding_status.value}"
            )
    for fact in [method, *settings, *measurements]:
        if fact.status == RecordStatus.DISPUTED:
            unknowns.append(f"事实 {fact.id} 存在争议，执行前需复核")
        for binding in fact.field_evidence:
            if binding.finding_status == FindingStatus.CONFLICTING:
                unknowns.append(
                    f"事实 {fact.id} 字段 {binding.field_path} 的来源相互冲突"
                )
    referenced_evidence_ids = {
        *input.decision.evidence_ids,
        *(
            evidence_id
            for fact in [method, *settings, *measurements]
            for evidence_id in _fact_evidence_ids(fact)
        ),
    }
    for evidence_id in sorted(referenced_evidence_ids):
        evidence = evidence_by_id.get(evidence_id)
        if evidence and evidence.finding_status == FindingStatus.CONFLICTING:
            unknowns.append(f"证据 {evidence_id} 的来源内容相互冲突")
    if not measurements:
        unknowns.append("所选实验设置没有已关联测量，目标指标与范围待用户填写")

    steps = _template_steps(input, method, settings, measurements)
    if suggestion_provider is None:
        unknowns.append("未调用生成模型；当前为明确标记的结构化待填模板")
    else:
        try:
            suggestions = suggestion_provider(input.model_copy(deep=True))
        except Exception as exc:
            unknowns.append(f"生成模型不可用；保留结构化待填模板: {type(exc).__name__}")
        else:
            accepted, rejected = validate_suggestion_steps(
                suggestions, set(evidence_by_id)
            )
            steps.extend(accepted)
            unknowns.extend(rejected)

    return ValidationPlan(
        id=None,
        project_id=input.project.id,
        version=1,
        status=PlanStatus.DRAFT,
        title=f"[结构化待填模板] {input.project.title}：首轮验证",
        objective=input.project.constraints.objective,
        hypothesis=None,
        selected_method_id=method.id,
        selected_experiment_setting_ids=[item.id for item in settings],
        assumptions=list(dict.fromkeys(assumptions)),
        unknowns=list(dict.fromkeys(unknowns)),
        steps=steps,
        target_measurements=[item.id for item in measurements],
        risks=list(dict.fromkeys(risks)),
        source_kind=SourceKind.MODEL_SUGGESTION,
        review_status=ReviewStatus.CURRENT,
        review_reasons=[],
    )


def build_snapshot_content(input: SnapshotBuildInput) -> ProjectSnapshot:
    """Freeze exact dependency versions without mutating the supplied models."""

    if input.plan.id is None or input.plan.status != PlanStatus.SAVED:
        raise ValueError("only a user-confirmed saved plan can form a snapshot")
    method, settings, measurements = _facts(input)
    if input.plan.project_id != input.project.id:
        raise ValueError("plan belongs to another project")
    if input.plan.selected_method_id != input.decision.selected_method_id:
        raise ValueError("plan method differs from the active user decision")
    if input.plan.selected_experiment_setting_ids != input.decision.selected_experiment_setting_ids:
        raise ValueError("plan settings differ from the active user decision")

    all_facts = {
        item.id: item
        for item in [*input.methods, *input.experiment_settings, *input.measurements]
    }
    dependency_ids = [method.id, *(item.id for item in settings)]
    dependency_ids.extend(input.plan.target_measurements)
    dependency_ids.extend(input.decision.considered_candidate_ids)
    dependencies: list[VersionRef] = []
    for fact_id in dict.fromkeys(dependency_ids):
        fact = all_facts.get(fact_id)
        if fact is None or fact.project_id != input.project.id:
            raise ValueError(f"snapshot dependency is missing or belongs elsewhere: {fact_id}")
        dependencies.append(VersionRef(id=fact.id, version=fact.version))

    document_ids = {item.document_id for item in input.frozen_documents}
    evidence_by_id = {item.id: item for item in input.evidence}
    plan_evidence_ids = {
        evidence_id for step in input.plan.steps for evidence_id in step.evidence_ids
    }
    referenced_evidence_ids = set(input.decision.evidence_ids) | plan_evidence_ids
    missing_evidence = referenced_evidence_ids - set(evidence_by_id)
    if missing_evidence:
        raise ValueError("snapshot references evidence outside the supplied evidence set")
    for evidence_id in referenced_evidence_ids:
        evidence = evidence_by_id[evidence_id]
        if (
            evidence.source_kind == SourceKind.LITERATURE_REPORT
            and evidence.document_id not in document_ids
        ):
            raise ValueError(
                f"literature evidence {evidence_id} is outside frozen documents"
            )

    canonical = {
        "project_id": input.project.id,
        "project_version": input.project.version,
        "decision": [input.decision.id, input.decision.version],
        "plan": [input.plan.id, input.plan.version],
        "documents": [item.model_dump(mode="json") for item in input.frozen_documents],
        "facts": [item.model_dump(mode="json") for item in dependencies],
    }
    digest = hashlib.sha256(
        json.dumps(canonical, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:20]
    return ProjectSnapshot(
        id=f"snapshot-content-{digest}",
        project_id=input.project.id,
        snapshot_version=1,
        frozen_project_version=input.project.version,
        frozen_constraint_version=input.project.constraints.version,
        frozen_domain_profile_version=input.project.domain_profile_version,
        frozen_decision=VersionRef(
            id=input.decision.id, version=input.decision.version
        ),
        frozen_documents=[item.model_copy(deep=True) for item in input.frozen_documents],
        frozen_facts=dependencies,
        plan=input.plan.model_copy(deep=True),
        review_status=ReviewStatus.CURRENT,
        review_reasons=[],
        # The frozen input lacks a requested snapshot time.  Use the already
        # frozen project update time deterministically; T1 owns persisted IDs,
        # sequence numbers, and storage timestamps.
        created_at=input.project.updated_at,
    )
