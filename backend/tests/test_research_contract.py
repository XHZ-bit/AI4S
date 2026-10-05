import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.models.research import (
    CONTRACT_VERSION,
    EvidenceKind,
    EvidenceLocator,
    EvidenceRef,
    FindingStatus,
    FrozenDocument,
    NumericScale,
    NumericValue,
    ProjectConstraints,
    ProjectSnapshot,
    ResearchProjectCreate,
    SourceKind,
    StatusTransitionRequest,
    ValidationPlan,
    VersionRef,
)


def constraints() -> ProjectConstraints:
    return ProjectConstraints(
        version=1,
        objective="验证小样本基线是否值得继续",
        allowed_datasets=[],
        excluded_datasets=[],
        required_metrics=["image_auroc"],
        compute=[],
        time_budget=NumericValue(value=8, unit="hour", scale="raw"),
        cost_budget=None,
        data_access=[],
        notes=[],
    )


def test_unknown_fields_and_missing_required_fields_are_rejected():
    with pytest.raises(ValidationError):
        ResearchProjectCreate(
            title="课题",
            research_question="问题",
            domain="image_anomaly_detection",
            constraints=constraints(),
            silently_ignored=True,
        )

    with pytest.raises(ValidationError):
        ResearchProjectCreate.model_validate(
            {
                "title": "课题",
                "domain": "image_anomaly_detection",
                "constraints": constraints().model_dump(mode="json"),
            }
        )


def test_numeric_value_preserves_value_unit_scale_and_range():
    value = NumericValue(
        value=95.2,
        unit="%",
        scale=NumericScale.PERCENT,
        lower=94.7,
        upper=95.7,
    )
    assert value.model_dump(mode="json") == {
        "value": 95.2,
        "unit": "%",
        "scale": "percent",
        "lower": 94.7,
        "upper": 95.7,
    }

    with pytest.raises(ValidationError):
        NumericValue(value=float("nan"), unit=None)
    with pytest.raises(ValidationError):
        NumericValue(value=3, unit="ms", lower=4, upper=5)


def test_literature_source_and_finding_status_require_traceable_evidence():
    with pytest.raises(ValidationError):
        EvidenceRef(
            id="ev-1",
            source_kind=SourceKind.LITERATURE_REPORT,
            finding_status=FindingStatus.REPORTED,
            kind=EvidenceKind.TEXT,
        )

    evidence = EvidenceRef(
        id="ev-1",
        source_kind="literature_report",
        finding_status="reported",
        kind="table",
        paper_uid="paper-1",
        document_id="doc-1",
        document_version="sha256:abc",
        locator=EvidenceLocator(page=4, table_id="table-2", row_label="method-a", column_label="AUROC"),
        quote="95.2",
        extraction_version="research-extract-v1",
    )
    assert evidence.locator and evidence.locator.column_label == "AUROC"

    with pytest.raises(ValidationError):
        EvidenceRef(
            id="ev-conflict",
            source_kind="literature_report",
            finding_status="conflicting",
            kind="text",
        )


def test_project_and_transition_versions_are_positive_and_transitions_are_frozen():
    with pytest.raises(ValidationError):
        ProjectConstraints(version=0, objective="invalid")

    transition = StatusTransitionRequest(
        expected_version=2,
        from_status="candidate",
        to_status="user_confirmed",
        actor="reviewer",
        reason="checked against the cited table",
    )
    assert transition.expected_version == 2

    with pytest.raises(ValidationError):
        StatusTransitionRequest(
            expected_version=2,
            from_status="withdrawn",
            to_status="user_confirmed",
            actor="reviewer",
            reason="skips required restoration to candidate",
        )


def test_project_snapshot_is_json_serializable_and_freezes_versions():
    now = datetime(2026, 10, 4, 8, 0, tzinfo=UTC)
    plan = ValidationPlan(
        id="plan-1",
        project_id="project-1",
        version=3,
        status="saved",
        title="首轮验证",
        objective="验证路线在固定小样本上的可行性",
        hypothesis=None,
        selected_method_id="method-1",
        selected_experiment_setting_ids=["setting-1"],
        assumptions=[],
        unknowns=["真实训练耗时未报告"],
        steps=[],
        target_measurements=["measurement-1"],
        risks=["数据许可尚待人工核对"],
        source_kind="user_input",
        review_status="current",
        review_reasons=[],
    )
    snapshot = ProjectSnapshot(
        id="snapshot-1",
        project_id="project-1",
        snapshot_version=1,
        frozen_project_version=7,
        frozen_constraint_version=2,
        frozen_domain_profile_version="image-anomaly-v1",
        frozen_decision=VersionRef(id="decision-1", version=2),
        frozen_documents=[
            FrozenDocument(
                paper_link_id="link-1",
                paper_uid="paper-1",
                document_id="doc-1",
                document_version="sha256:abc",
                content_hash="abc",
            )
        ],
        frozen_facts=[VersionRef(id="method-1", version=4)],
        plan=plan,
        review_status="current",
        review_reasons=[],
        created_at=now,
    )

    payload = json.loads(snapshot.model_dump_json())
    assert payload["contract_version"] == CONTRACT_VERSION
    assert payload["frozen_project_version"] == 7
    assert payload["frozen_documents"][0]["content_hash"] == "abc"
    assert payload["created_at"] == "2026-10-04T08:00:00Z"
