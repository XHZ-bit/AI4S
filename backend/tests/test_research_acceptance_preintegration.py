"""T6 pre-integration acceptance tests using only synthetic data and mocks.

These tests exercise delivered module boundaries with temporary SQLite databases.
They are not real-paper effectiveness tests and do not assert that T0 integration,
real models, or Neo4j are available.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from types import ModuleType

import httpx
import pytest
from pydantic import ValidationError as PydanticValidationError

from app.db import projects as store
from app.db.sqlite import connect
from app.models.research import (
    CandidateBundle,
    ComparisonCandidate,
    ComparisonRequest,
    ErrorDetail,
    EvidenceKind,
    EvidenceRef,
    ExperimentSetting,
    ExtractionInput,
    FieldEvidence,
    FrozenDocument,
    Measurement,
    MethodCard,
    NumericValue,
    PaperLinkCreate,
    PlanGenerateRequest,
    PlanSaveRequest,
    ProtocolStep,
    ProjectConstraints,
    ResearchDecisionCreate,
    ResearchProjectCreate,
    ResearchProjectPatch,
    SnapshotCreateRequest,
    StatusTransitionRequest,
    TaskKind,
    TaskStatus,
    ValidationPlan,
    VersionRef,
)
from app.research import service
from app.research_extraction import ModelInvocationError, extract_candidates


NOW = datetime(2026, 10, 4, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _authorized_fake_plan_provider(monkeypatch):
    monkeypatch.setattr(
        service,
        "plan_suggestion_provider",
        lambda value: {"additional_steps": [{
            "title": "人工复核", "purpose": "核对所选来源",
            "procedure": ["检查原文与所选设置，不运行命令"],
            "acceptance_criteria": ["用户确认来源；不确定时停止"],
            "evidence_ids": [value.evidence[0].id],
        }]},
    )


@pytest.fixture
def conn(tmp_path):
    value = connect(str(tmp_path / "t6-acceptance.sqlite3"))
    store.init_research_schema(value)
    for index in (1, 2):
        value.execute(
            "INSERT INTO papers(uid,title,abstract) VALUES(?,?,?)",
            (f"paper-{index}", f"Synthetic paper {index}", "synthetic"),
        )
        value.execute(
            "INSERT INTO documents(id,paper_uid,content_hash,coverage) VALUES(?,?,?,?)",
            (f"doc-{index}", f"paper-{index}", f"hash-{index}", "fulltext"),
        )
        value.execute(
            "INSERT INTO passages(id,document_id,heading,text,page,ordinal) VALUES(?,?,?,?,?,?)",
            (
                f"passage-{index}",
                f"doc-{index}",
                "Synthetic experiment",
                "AtlasNet was evaluated under a stated synthetic condition.",
                index,
                0,
            ),
        )
    value.commit()
    yield value
    value.close()


def create_project(conn, suffix: str = "1"):
    return store.create_project(
        conn,
        ResearchProjectCreate(
            title=f"Synthetic project {suffix}",
            research_question="Which synthetic route should be validated first?",
            domain="image_anomaly_detection",
            constraints=ProjectConstraints(
                version=1,
                objective="Exercise the acceptance workflow without real algorithms",
            ),
        ),
    )


def link_paper(conn, project, index: int = 1):
    return store.link_paper(
        conn,
        project.id,
        project.version,
        PaperLinkCreate(
            expected_project_version=project.version,
            paper_uid=f"paper-{index}",
            role="primary",
        ),
    )


def _binding(path: str, evidence_id: str, status: str = "reported"):
    return FieldEvidence(
        field_path=path,
        source_kind="literature_report",
        finding_status=status,
        evidence_ids=[evidence_id] if status in {"reported", "conflicting"} else [],
    )


def make_bundle(project, link, *, invalid_evidence: bool = False):
    evidence_id = f"evidence-{project.id}"
    evidence = EvidenceRef(
        id=evidence_id,
        source_kind="literature_report",
        finding_status="reported",
        kind=EvidenceKind.TEXT,
        paper_uid=link.paper_uid,
        document_id=link.linked_document_id,
        document_version=link.linked_document_version,
        passage_id="passage-1" if link.paper_uid == "paper-1" else "passage-2",
        quote="AtlasNet was evaluated under a stated synthetic condition.",
    )
    method = MethodCard(
        id=f"method-{project.id}",
        project_id=project.id,
        version=1,
        source_kind="literature_report",
        finding_status="reported",
        field_evidence=[
            _binding("name", "missing-evidence" if invalid_evidence else evidence_id)
        ],
        paper_link_id=link.id,
        name="AtlasNet",
        created_at=NOW,
        updated_at=NOW,
    )
    setting_a = ExperimentSetting(
        id=f"setting-a-{project.id}",
        project_id=project.id,
        version=1,
        source_kind="literature_report",
        finding_status="reported",
        field_evidence=[
            _binding("dataset", evidence_id),
            _binding("split", evidence_id),
            _binding("evaluation_protocol", evidence_id),
        ],
        paper_link_id=link.id,
        method_id=method.id,
        name="Setting A",
        dataset="SyntheticAD",
        split="official",
        evaluation_protocol="image-level synthetic protocol",
        created_at=NOW,
        updated_at=NOW,
    )
    setting_b = ExperimentSetting(
        id=f"setting-b-{project.id}",
        project_id=project.id,
        version=1,
        source_kind="literature_report",
        finding_status="reported",
        field_evidence=[
            _binding("dataset", evidence_id),
            _binding("split", evidence_id, "unknown"),
            _binding("evaluation_protocol", evidence_id),
        ],
        paper_link_id=link.id,
        method_id=method.id,
        name="Setting B",
        dataset="SyntheticAD",
        split=None,
        evaluation_protocol="pixel-level synthetic protocol",
        created_at=NOW,
        updated_at=NOW,
    )
    measurement_a = Measurement(
        id=f"measurement-a-{project.id}",
        project_id=project.id,
        version=1,
        source_kind="literature_report",
        finding_status="reported",
        field_evidence=[
            _binding("metric_name", evidence_id),
            _binding("metric_scope", evidence_id),
            _binding("value", evidence_id),
        ],
        experiment_setting_id=setting_a.id,
        metric_name="image_auroc",
        metric_scope="image",
        value=NumericValue(value=0.91, scale="fraction"),
        created_at=NOW,
        updated_at=NOW,
    )
    measurement_b = Measurement(
        id=f"measurement-b-{project.id}",
        project_id=project.id,
        version=1,
        source_kind="literature_report",
        finding_status="reported",
        field_evidence=[
            _binding("metric_name", evidence_id),
            _binding("metric_scope", evidence_id),
            _binding("value", evidence_id),
        ],
        experiment_setting_id=setting_b.id,
        metric_name="pixel_auroc",
        metric_scope="pixel",
        value=NumericValue(value=0.92, scale="fraction"),
        created_at=NOW,
        updated_at=NOW,
    )
    return CandidateBundle(
        project_id=project.id,
        paper_link_id=link.id,
        document_id=link.linked_document_id,
        document_version=link.linked_document_version,
        extraction_version="synthetic-t6-v1",
        evidence=[evidence],
        methods=[method],
        experiment_settings=[setting_a, setting_b],
        measurements=[measurement_a, measurement_b],
        warnings=["synthetic_fixture:not_a_real_paper_result"],
    )


def seed_complete_flow(conn, suffix: str = "1", paper_index: int = 1):
    project = create_project(conn, suffix)
    link = link_paper(conn, project, paper_index)
    project = store.get_project(conn, project.id)
    bundle = make_bundle(project, link)
    store.save_candidate_bundle(conn, bundle)
    comparison = service.compare_project_conditions(
        conn,
        project.id,
        ComparisonRequest(
            project_id=project.id,
            project_version=project.version,
            domain=project.domain,
            candidates=[
                ComparisonCandidate(
                    method_id=bundle.methods[0].id,
                    experiment_setting_id=bundle.experiment_settings[0].id,
                    measurement_ids=[bundle.measurements[0].id],
                ),
                ComparisonCandidate(
                    method_id=bundle.methods[0].id,
                    experiment_setting_id=bundle.experiment_settings[1].id,
                    measurement_ids=[bundle.measurements[1].id],
                ),
            ],
        ),
    )
    decision = service.create_decision(
        conn,
        project.id,
        ResearchDecisionCreate(
            expected_project_version=project.version,
            selected_method_id=bundle.methods[0].id,
            selected_experiment_setting_ids=[bundle.experiment_settings[0].id],
            considered_candidate_ids=[
                bundle.experiment_settings[0].id,
                bundle.experiment_settings[1].id,
            ],
            rationale="Human chose Setting A for the first synthetic check.",
            evidence_ids=[bundle.evidence[0].id],
        ),
    )
    draft = service.build_plan(
        conn,
        project.id,
        PlanGenerateRequest(
            expected_project_version=project.version,
            decision_id=decision.id,
            decision_version=decision.version,
        ),
    )
    plan = store.save_plan(
        conn,
        project.id,
        PlanSaveRequest(
            expected_project_version=project.version,
            expected_plan_version=0,
            plan=draft,
        ),
    )
    snapshot = service.create_snapshot(
        conn,
        project.id,
        SnapshotCreateRequest(
            expected_project_version=project.version,
            plan_id=plan.id,
            plan_version=plan.version,
        ),
    )
    return {
        "project": project,
        "link": link,
        "bundle": bundle,
        "comparison": comparison,
        "decision": decision,
        "plan": plan,
        "snapshot": snapshot,
    }


def test_synthetic_complete_flow_keeps_same_method_settings_separate(conn):
    result = seed_complete_flow(conn)
    facts = service.project_facts(conn, result["project"].id)
    assert len(facts.methods) == 1
    assert len(facts.experiment_settings) == 2
    assert {setting.method_id for setting in facts.experiment_settings} == {
        facts.methods[0].id
    }
    assert result["decision"].source_kind.value == "user_input"
    assert result["plan"].id is not None
    assert result["snapshot"].plan.id == result["plan"].id


def test_unknown_input_is_rejected_and_unknown_condition_is_not_zero():
    with pytest.raises(PydanticValidationError):
        ResearchProjectCreate.model_validate(
            {
                "title": "Synthetic",
                "research_question": "Question",
                "domain": "image_anomaly_detection",
                "constraints": {"version": 1, "objective": "Objective"},
                "unexpected": "must fail",
            }
        )
    setting = make_bundle(
        type("P", (), {"id": "p"})(),
        type(
            "L",
            (),
            {
                "id": "l",
                "paper_uid": "paper-1",
                "linked_document_id": "doc-1",
                "linked_document_version": "sha256:hash-1",
            },
        )(),
    ).experiment_settings[1]
    assert setting.split is None
    split_source = next(x for x in setting.field_evidence if x.field_path == "split")
    assert split_source.finding_status.value == "unknown"


def test_invalid_evidence_reference_rolls_back_transaction(conn):
    project = create_project(conn)
    link = link_paper(conn, project)
    project = store.get_project(conn, project.id)
    with pytest.raises(store.InvalidStateError, match="字段来源"):
        store.save_candidate_bundle(conn, make_bundle(project, link, invalid_evidence=True))
    assert store.list_facts(conn, project.id) == []
    assert store.list_evidence(conn, project.id) == []


def test_wrong_metric_scope_and_missing_split_are_not_ranked(conn):
    result = seed_complete_flow(conn)
    comparison = result["comparison"]
    assert any(not group.comparable for group in comparison.groups)
    combined = "\n".join(
        [
            *comparison.warnings,
            *(reason for group in comparison.groups for reason in group.reasons),
            *(dimension.reason or "" for dimension in comparison.dimensions),
        ]
    )
    assert "pixel" in combined.lower() or "指标" in combined
    assert "缺失" in combined or "不足" in combined


def test_stale_project_version_conflicts_without_overwrite(conn):
    project = create_project(conn)
    updated = store.update_project(
        conn,
        project.id,
        ResearchProjectPatch(expected_version=1, title="Updated once"),
    )
    with pytest.raises(store.VersionConflictError) as error:
        store.update_project(
            conn,
            project.id,
            ResearchProjectPatch(expected_version=1, title="Stale overwrite"),
        )
    assert error.value.current_version == updated.version
    assert store.get_project(conn, project.id).title == "Updated once"


def test_model_timeout_is_explicit_and_does_not_create_candidates(monkeypatch):
    from app.models.research import PaperLink

    paper_link = PaperLink(
        id="link-timeout",
        project_id="project-timeout",
        version=1,
        paper_uid="synthetic-timeout-paper",
        role="primary",
        linked_document_id="doc-timeout",
        linked_document_version="synthetic-v1",
        created_at=NOW,
        updated_at=NOW,
    )
    extraction_input = ExtractionInput(
        project_id=paper_link.project_id,
        paper_link=paper_link,
        document=FrozenDocument(
            paper_link_id=paper_link.id,
            paper_uid=paper_link.paper_uid,
            document_id="doc-timeout",
            document_version="synthetic-v1",
            content_hash="synthetic-hash",
        ),
        passages=[
            {
                "id": "p-timeout",
                "document_id": "doc-timeout",
                "heading": "Synthetic",
                "text": "Invented text for timeout handling.",
                "page": 1,
                "ordinal": 0,
                "kind": "text",
                "metadata_json": "{}",
            }
        ],
        domain="image_anomaly_detection",
        domain_profile_version="image-anomaly-v1",
    )

    def timeout(*_args, **_kwargs):
        raise httpx.ReadTimeout("synthetic timeout")

    monkeypatch.setattr("app.research_extraction.candidates.chat", timeout)
    with pytest.raises(ModelInvocationError, match="timed out"):
        extract_candidates(extraction_input)


def test_missing_plan_provider_fails_task_and_preserves_saved_content(conn, monkeypatch):
    result = seed_complete_flow(conn)
    monkeypatch.setattr(service, "plan_suggestion_provider", None)
    request = PlanGenerateRequest(
        expected_project_version=result["project"].version,
        decision_id=result["decision"].id,
        decision_version=result["decision"].version,
    )
    task = service.enqueue_plan_generation(
        conn, result["project"].id, request, lambda _task_id: None
    )

    failed = service.run_plan_generation_task(conn, task.id)

    assert failed.status == TaskStatus.FAILED
    assert failed.result is None
    assert failed.error is not None
    assert failed.error.code == "not_implemented"
    assert failed.error.retryable is False
    assert "尚未授权" in failed.error.message
    assert store.get_plan_version(
        conn, result["plan"].id, result["plan"].version
    ) == result["plan"]
    assert store.get_snapshot(
        conn, result["project"].id, result["snapshot"].id
    ) == result["snapshot"]


def test_human_authored_plan_can_be_saved_without_generation_provider(conn):
    project = create_project(conn)
    link = link_paper(conn, project)
    project = store.get_project(conn, project.id)
    bundle = make_bundle(project, link)
    store.save_candidate_bundle(conn, bundle)
    service.create_decision(
        conn,
        project.id,
        ResearchDecisionCreate(
            expected_project_version=project.version,
            selected_method_id=bundle.methods[0].id,
            selected_experiment_setting_ids=[bundle.experiment_settings[0].id],
            considered_candidate_ids=[bundle.experiment_settings[0].id],
            rationale="Human selected a minimal first validation route.",
            evidence_ids=[bundle.evidence[0].id],
        ),
    )
    manual = ValidationPlan(
        id="manual-plan-t6",
        project_id=project.id,
        version=1,
        title="Human-authored first validation",
        objective=project.constraints.objective,
        selected_method_id=bundle.methods[0].id,
        selected_experiment_setting_ids=[bundle.experiment_settings[0].id],
        unknowns=["Compute budget remains unknown and must not be inferred."],
        steps=[
            ProtocolStep(
                id="manual-check",
                title="Human-defined evidence check",
                purpose="Verify the frozen source before any execution.",
                procedure=["Review the cited synthetic passage."],
                acceptance_criteria=["The reviewer records an explicit decision."],
                evidence_ids=[bundle.evidence[0].id],
            )
        ],
        source_kind="user_input",
    )

    saved = store.save_plan(
        conn,
        project.id,
        PlanSaveRequest(
            expected_project_version=project.version,
            expected_plan_version=0,
            plan=manual,
        ),
    )
    snapshot = service.create_snapshot(
        conn,
        project.id,
        SnapshotCreateRequest(
            expected_project_version=project.version,
            plan_id=saved.id,
            plan_version=saved.version,
        ),
    )

    assert saved.source_kind.value == "user_input"
    assert saved.status.value == "saved"
    assert "Compute budget remains unknown" in saved.unknowns[0]
    assert snapshot.plan.id == saved.id


def test_failed_task_retry_creates_new_id_and_keeps_prior_failure(conn):
    project = create_project(conn)
    params = {"project_id": project.id, "synthetic": True}
    prior = store.create_task(conn, TaskKind.PLAN_GENERATION, project.id, params)
    prior = store.update_task(
        conn,
        prior.id,
        TaskStatus.FAILED,
        error=ErrorDetail(
            code="model_unavailable",
            message="synthetic model timeout",
            retryable=True,
        ),
    )
    dispatched: list[str] = []
    retried = service.enqueue_research_task(
        conn,
        prior.kind,
        project.id,
        params,
        dispatched.append,
        retry_of=prior.id,
    )
    assert retried.id != prior.id
    assert retried.status.value == "queued"
    assert dispatched == [retried.id]
    assert store.get_task(conn, prior.id).status.value == "failed"
    row = conn.execute(
        "SELECT retry_of FROM research_async_tasks WHERE task_id=?", (retried.id,)
    ).fetchone()
    assert row["retry_of"] == prior.id


def test_graph_projection_failure_preserves_snapshot_and_retry_succeeds(
    conn, monkeypatch
):
    result = seed_complete_flow(conn)
    module = ModuleType("app.research.graph_projection")
    module.build_graph_projection = lambda snapshot: snapshot

    def fail(_projection):
        raise RuntimeError("synthetic neo4j outage")

    module.project_graph = fail
    monkeypatch.setitem(sys.modules, "app.research.graph_projection", module)
    first = service.enqueue_graph_projection(
        conn,
        result["project"].id,
        result["snapshot"].id,
        lambda _task_id: None,
    )
    failed = service.run_research_task(conn, first.id)
    assert failed.status == TaskStatus.FAILED
    assert failed.error is not None and failed.error.retryable is True
    stored = store.get_snapshot(
        conn, result["project"].id, result["snapshot"].id
    )
    assert stored == result["snapshot"]
    state = store.get_projection_state(conn, result["snapshot"].id)
    assert state["status"] == "failed"
    assert state["attempt_count"] >= 1

    module.project_graph = lambda _projection: {"synthetic": "projected"}
    retry = service.enqueue_graph_projection(
        conn,
        result["project"].id,
        result["snapshot"].id,
        lambda _task_id: None,
        retry=True,
    )
    succeeded = service.run_research_task(conn, retry.id)
    assert retry.id != first.id
    assert succeeded.status == TaskStatus.SUCCEEDED
    assert store.get_task(conn, first.id).status == TaskStatus.FAILED
    assert store.get_projection_state(conn, result["snapshot"].id)["status"] == "succeeded"
    retry_of = conn.execute(
        "SELECT retry_of FROM research_async_tasks WHERE task_id=?", (retry.id,)
    ).fetchone()["retry_of"]
    assert retry_of == first.id


def test_plan_versions_and_dependency_review_scope_are_preserved(conn):
    first = seed_complete_flow(conn, "first", 1)
    second = seed_complete_flow(conn, "second", 2)
    prior = first["plan"]
    edited = store.save_plan(
        conn,
        first["project"].id,
        PlanSaveRequest(
            expected_project_version=first["project"].version,
            expected_plan_version=prior.version,
            plan=prior.model_copy(update={"objective": "Human-edited objective"}),
        ),
    )
    assert edited.version == prior.version + 1
    assert store.get_plan_version(conn, prior.id, prior.version).objective == prior.objective
    assert store.get_plan_version(conn, edited.id, edited.version).objective == "Human-edited objective"
    first_after_plan = store.get_snapshot(
        conn, first["project"].id, first["snapshot"].id
    )
    assert first_after_plan.review_status.value == "needs_review"
    assert store.get_snapshot(
        conn, second["project"].id, second["snapshot"].id
    ).review_status.value == "current"

    affected = store.mark_dependent_snapshots_for_review(
        conn,
        [VersionRef(id=first["bundle"].methods[0].id, version=1)],
        ["Synthetic evidence-linked fact changed"],
    )
    assert affected == 1
    assert "Synthetic evidence-linked fact changed" in store.get_snapshot(
        conn, first["project"].id, first["snapshot"].id
    ).review_reasons
    assert store.get_snapshot(
        conn, second["project"].id, second["snapshot"].id
    ).review_status.value == "current"


def test_constraint_change_marks_only_dependent_snapshot_for_review(conn):
    first = seed_complete_flow(conn, "constraint-first", 1)
    second = seed_complete_flow(conn, "constraint-second", 2)
    project = store.get_project(conn, first["project"].id)
    changed_constraints = project.constraints.model_copy(
        update={
            "version": project.constraints.version + 1,
            "objective": "Human changed the validation objective.",
        }
    )

    updated = store.update_project(
        conn,
        project.id,
        ResearchProjectPatch(
            expected_version=project.version,
            constraints=changed_constraints,
        ),
    )

    assert updated.constraints.version == project.constraints.version + 1
    impacted = store.get_snapshot(conn, project.id, first["snapshot"].id)
    assert impacted.review_status.value == "needs_review"
    assert "项目约束已更新" in impacted.review_reasons
    assert store.get_snapshot(
        conn, second["project"].id, second["snapshot"].id
    ).review_status.value == "current"


def test_json_export_contains_frozen_versions_sources_and_review_state(conn):
    result = seed_complete_flow(conn)
    payload = json.loads(service.snapshot_json(result["snapshot"]))

    assert payload["contract_version"] == "research-v1.1"
    assert payload["frozen_project_version"] == result["project"].version
    assert payload["frozen_constraint_version"] == result["project"].constraints.version
    assert payload["frozen_domain_profile_version"]
    assert payload["frozen_decision"] == {
        "id": result["decision"].id,
        "version": result["decision"].version,
    }
    assert payload["frozen_documents"][0]["document_version"]
    assert payload["frozen_facts"]
    assert payload["plan"]["source_kind"] == "model_suggestion"
    assert payload["review_status"] == "current"


def test_fact_status_transition_keeps_audit_and_prior_version(conn):
    result = seed_complete_flow(conn)
    method = result["bundle"].methods[0]
    changed = store.transition_fact(
        conn,
        result["project"].id,
        method.id,
        StatusTransitionRequest(
            expected_version=1,
            from_status="candidate",
            to_status="user_confirmed",
            actor="t6-human-reviewer",
            reason="Synthetic acceptance review",
        ),
    )
    assert changed.version == 2
    assert changed.status.value == "user_confirmed"
    audit = store.fact_audit(conn, method.id)
    assert len(audit) == 1
    assert audit[0]["actor"] == "t6-human-reviewer"
    count = conn.execute(
        "SELECT COUNT(*) AS n FROM research_fact_versions WHERE fact_id=?",
        (method.id,),
    ).fetchone()["n"]
    assert count == 2
