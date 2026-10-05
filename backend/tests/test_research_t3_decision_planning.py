from copy import deepcopy

import pytest

from app.models.research import (
    CandidateBundle,
    DecisionValidationRequest,
    EvidenceRef,
    ExperimentSetting,
    FieldEvidence,
    FrozenDocument,
    Measurement,
    MethodCard,
    NamedValue,
    NumericValue,
    PlanBuildInput,
    PlanStatus,
    ProjectConstraints,
    ResearchDecision,
    ResearchDecisionCreate,
    ResearchProject,
    SnapshotBuildInput,
)
from app.research.decisions import validate_decision
from app.research.planning import build_plan_draft, build_snapshot_content
from datetime import UTC, datetime


NOW = datetime(2026, 10, 4, 8, 0, tzinfo=UTC)


def _evidence(eid, paper, document):
    return EvidenceRef(
        id=eid,
        source_kind="literature_report",
        finding_status="reported",
        kind="text",
        paper_uid=paper,
        document_id=document,
        document_version="sha256:abc",
        passage_id=f"passage-{eid}",
        quote="reported condition",
    )


def _binding(path, eid):
    return FieldEvidence(
        field_path=path,
        source_kind="literature_report",
        finding_status="reported",
        evidence_ids=[eid],
    )


def image_bundle():
    methods = []
    settings = []
    measurements = []
    evidence = []
    for index in (1, 2):
        eid = f"ev-{index}"
        evidence.append(_evidence(eid, f"paper-{index}", f"doc-{index}"))
        methods.append(
            MethodCard(
                id=f"method-{index}",
                project_id="project-1",
                version=1,
                source_kind="literature_report",
                finding_status="reported",
                field_evidence=[_binding("name", eid)],
                paper_link_id=f"link-{index}",
                name=f"Method {index}",
                assumptions=["固定数据范围"],
                limitations=["资源信息可能不完整"],
                created_at=NOW,
                updated_at=NOW,
            )
        )
        settings.append(
            ExperimentSetting(
                id=f"setting-{index}",
                project_id="project-1",
                version=1,
                source_kind="literature_report",
                finding_status="reported",
                field_evidence=[
                    _binding("dataset", eid),
                    _binding("split", eid),
                    _binding("evaluation_protocol", eid),
                ],
                paper_link_id=f"link-{index}",
                method_id=f"method-{index}",
                name=f"Setting {index}",
                dataset="MVTec AD",
                split="official",
                evaluation_protocol="official test split",
                resources=[NamedValue(name="training_time", value=2, unit="hour")],
                created_at=NOW,
                updated_at=NOW,
            )
        )
        measurements.append(
            Measurement(
                id=f"measurement-{index}",
                project_id="project-1",
                version=1,
                source_kind="literature_report",
                finding_status="reported",
                field_evidence=[_binding("metric_name", eid), _binding("value", eid)],
                experiment_setting_id=f"setting-{index}",
                metric_name="image_auroc",
                metric_scope="image",
                value=NumericValue(value=0.9, scale="fraction"),
                aggregation="macro",
                created_at=NOW,
                updated_at=NOW,
            )
        )
    return CandidateBundle(
        project_id="project-1",
        paper_link_id="bundle-link",
        document_id="bundle-doc",
        document_version="sha256:bundle",
        extraction_version="test-v1",
        evidence=evidence,
        methods=methods,
        experiment_settings=settings,
        measurements=measurements,
    )


def project():
    return ResearchProject(
        id="project-1",
        version=3,
        title="课题",
        research_question="问题",
        domain="image_anomaly_detection",
        domain_profile_version="image-anomaly-v1",
        constraints=ProjectConstraints(
            version=2,
            objective="验证首轮路线",
            required_metrics=["image_auroc"],
        ),
        created_at=NOW,
        updated_at=NOW,
    )


def decision_create(**updates):
    data = {
        "expected_project_version": 3,
        "selected_method_id": "method-1",
        "selected_experiment_setting_ids": ["setting-1"],
        "considered_candidate_ids": ["method-1", "setting-1", "method-2", "setting-2"],
        "rationale": "用户选择先做最小闭环验证",
        "evidence_ids": ["ev-1"],
    }
    data.update(updates)
    return ResearchDecisionCreate(**data)


def saved_decision(**updates):
    create = decision_create()
    data = {
        "id": "decision-1",
        "project_id": "project-1",
        "version": 1,
        "project_version": 3,
        "selected_method_id": create.selected_method_id,
        "selected_experiment_setting_ids": create.selected_experiment_setting_ids,
        "considered_candidate_ids": create.considered_candidate_ids,
        "rationale": create.rationale,
        "evidence_ids": create.evidence_ids,
        "created_at": NOW,
    }
    data.update(updates)
    return ResearchDecision(**data)


def validation_input(**decision_updates):
    bundle = image_bundle()
    return DecisionValidationRequest(
        project=project(),
        decision=decision_create(**decision_updates),
        methods=bundle.methods,
        experiment_settings=bundle.experiment_settings,
        measurements=bundle.measurements,
    )


def plan_input():
    bundle = image_bundle()
    return PlanBuildInput(
        project=project(),
        decision=saved_decision(),
        methods=bundle.methods,
        experiment_settings=bundle.experiment_settings,
        measurements=bundle.measurements,
        evidence=bundle.evidence,
    )


def test_user_selection_is_validated_but_never_replaced():
    result = validate_decision(validation_input())
    assert result.valid is True
    assert result.referenced_fact_ids[:2] == ["method-1", "setting-1"]
    assert any("最终路线来自用户选择" in warning for warning in result.warnings)
    assert any("candidate" in warning for warning in result.warnings)
    assert not any("method-2 更优" in warning for warning in result.warnings)


def test_selected_fact_from_another_project_is_rejected():
    request = validation_input()
    request.methods[0].project_id = "other-project"
    result = validate_decision(request)
    assert result.valid is False
    assert any("不属于当前课题" in error for error in result.errors)


def test_selected_setting_must_belong_to_selected_method():
    request = validation_input()
    request.experiment_settings[0].method_id = "method-2"
    result = validate_decision(request)
    assert result.valid is False
    assert any("不属于所选方法" in error for error in result.errors)


def test_withdrawn_selected_fact_is_rejected():
    request = validation_input()
    request.methods[0].status = "withdrawn"
    result = validate_decision(request)
    assert result.valid is False
    assert "所选方法已撤回" in result.errors


def test_unknown_decision_evidence_is_rejected():
    result = validate_decision(validation_input(evidence_ids=["not-in-project"]))
    assert result.valid is False
    assert any("证据不存在" in error for error in result.errors)


def test_conflicting_evidence_is_preserved_as_warning():
    request = validation_input()
    request.methods[0].field_evidence[0].finding_status = "conflicting"
    result = validate_decision(request)
    assert result.valid is True
    assert any("相互冲突" in warning for warning in result.warnings)


def test_missing_compute_information_is_warning_not_fabricated_fact():
    request = validation_input()
    request.project.constraints.compute = [{"device_kind": "gpu"}]
    request.experiment_settings[0].resources = []
    result = validate_decision(request)
    assert result.valid is True
    assert any("未报告资源信息" in warning for warning in result.warnings)


def test_plan_contains_required_sections_as_traceable_steps():
    plan = build_plan_draft(plan_input())
    assert plan.status.value == "draft"
    assert plan.title.startswith("[结构化待填模板]")
    assert plan.selected_method_id == "method-1"
    assert plan.target_measurements == ["measurement-1"]
    titles = {step.id for step in plan.steps}
    assert titles == {
        "verify-evidence",
        "freeze-data-and-split",
        "define-baselines-and-controls",
        "run-minimal-validation",
        "evaluate-and-decide",
    }
    combined = "\n".join(
        [
            plan.objective,
            *plan.assumptions,
            *plan.unknowns,
            *plan.risks,
            *(step.title for step in plan.steps),
            *(item for step in plan.steps for item in step.procedure),
            *(item for step in plan.steps for item in step.acceptance_criteria),
        ]
    )
    for expected in ("数据", "划分", "基线", "控制", "产物", "指标", "用户"):
        assert expected in combined
    assert all("ev-1" in step.evidence_ids for step in plan.steps)


def test_model_exception_returns_explicit_blank_template():
    def unavailable(_input):
        raise RuntimeError("model offline")

    plan = build_plan_draft(plan_input(), suggestion_provider=unavailable)
    assert len(plan.steps) == 5
    assert any("生成模型不可用" in item for item in plan.unknowns)
    assert not any("model offline" in item for item in plan.unknowns)


def test_plan_preserves_conflicting_evidence_as_unresolved_item():
    data = plan_input()
    data.evidence[0].finding_status = "conflicting"
    data.evidence[0].conflict_group_id = "conflict-1"
    plan = build_plan_draft(data)
    assert any("证据 ev-1" in item and "相互冲突" in item for item in plan.unknowns)


def test_unsupported_commands_and_unverified_scores_are_rejected():
    def unsafe(_input):
        return {
            "additional_steps": [
                {
                    "title": "执行官方命令",
                    "purpose": "复现",
                    "procedure": ["python train.py --epochs 100"],
                    "acceptance_criteria": ["AUROC 99%"],
                    "evidence_ids": ["ev-1"],
                }
            ]
        }

    plan = build_plan_draft(plan_input(), suggestion_provider=unsafe)
    assert len(plan.steps) == 5
    assert any("未经确认的命令" in item for item in plan.unknowns)


def test_ungrounded_model_content_is_rejected_from_plan_steps():
    def ungrounded(_input):
        return {
            "additional_steps": [
                {
                    "title": "无来源资源承诺",
                    "purpose": "声称单卡足够",
                    "procedure": ["承诺在指定资源上完成"],
                    "evidence_ids": [],
                }
            ]
        }

    plan = build_plan_draft(plan_input(), suggestion_provider=ungrounded)
    assert len(plan.steps) == 5
    assert any("缺少当前课题证据" in item for item in plan.unknowns)


def test_grounded_model_suggestion_remains_labeled_as_suggestion():
    def grounded(_input):
        return {
            "additional_steps": [
                {
                    "title": "补充敏感性检查",
                    "purpose": "检查用户关心的控制变量",
                    "procedure": ["由用户选择一个变量并保持其他条件不变"],
                    "acceptance_criteria": ["产物记录变量变化"],
                    "evidence_ids": ["ev-1"],
                }
            ]
        }

    plan = build_plan_draft(plan_input(), suggestion_provider=grounded)
    assert len(plan.steps) == 6
    assert plan.steps[-1].id == "model-suggestion-1"
    assert plan.source_kind.value == "model_suggestion"


def snapshot_input():
    base = plan_input()
    draft = build_plan_draft(base)
    saved = draft.model_copy(
        update={"id": "plan-1", "status": PlanStatus.SAVED, "version": 2}
    )
    return SnapshotBuildInput(
        **base.model_dump(),
        plan=saved,
        frozen_documents=[
            FrozenDocument(
                paper_link_id="link-1",
                paper_uid="paper-1",
                document_id="doc-1",
                document_version="sha256:abc",
                content_hash="abc",
            ),
            FrozenDocument(
                paper_link_id="link-2",
                paper_uid="paper-2",
                document_id="doc-2",
                document_version="sha256:abc",
                content_hash="abc",
            ),
        ],
    )


def test_snapshot_freezes_versions_and_does_not_mutate_input():
    data = snapshot_input()
    before = deepcopy(data.model_dump(mode="json"))
    snapshot = build_snapshot_content(data)
    after = data.model_dump(mode="json")
    assert after == before
    assert snapshot.frozen_project_version == 3
    assert snapshot.frozen_constraint_version == 2
    assert snapshot.frozen_decision.id == "decision-1"
    frozen = {(item.id, item.version) for item in snapshot.frozen_facts}
    assert ("method-1", 1) in frozen
    assert ("setting-1", 1) in frozen
    assert ("measurement-1", 1) in frozen
    assert snapshot.plan is not data.plan


def test_draft_plan_cannot_become_snapshot():
    data = snapshot_input()
    data.plan.status = PlanStatus.DRAFT
    with pytest.raises(ValueError, match="user-confirmed saved plan"):
        build_snapshot_content(data)


def test_snapshot_rejects_literature_evidence_outside_frozen_documents():
    data = snapshot_input()
    data.evidence[0].document_id = "doc-not-frozen"
    with pytest.raises(ValueError, match="outside frozen documents"):
        build_snapshot_content(data)
