"""Locally reproducible findings from external model review; no live calls."""
import pytest

from app.db import projects as store
from app.models.research import FactRevisionRequest, FindingStatus, NamedValue, NumericValue, ComputeConstraint, PaperLinkCreate, PlanSaveRequest, ProtocolStep, StatusTransitionRequest, TaskKind, TaskStatus
from app.research.comparison import compare_conditions
from app.research.planning import build_plan_draft, build_snapshot_content
from tests.test_research_t1_storage import conn as database_fixture, make_project, link_paper, make_bundle, seed_snapshot
from tests.test_research_t3_decision_planning import plan_input, snapshot_input
from tests.test_research_t3_comparison import image_bundle, request, dimension, _binding

conn = database_fixture


@pytest.mark.parametrize("status", ["conflicting", "not_parsed", "not_found"])
def test_renaming_measurement_preserves_finding_state(conn, status):
    project = make_project(conn)
    bundle = make_bundle(project.id, link_paper(conn, project).id)
    bundle.measurements[0].finding_status = FindingStatus(status)
    bundle.measurements[0].value = None
    store.save_candidate_bundle(conn, bundle)
    updated = store.revise_fact(conn, project.id, bundle.measurements[0].id,
        FactRevisionRequest(expected_version=1, changes={"metric_name": "corrected"}, actor="Review", reason="Rename only"))
    assert updated.finding_status.value == status


@pytest.mark.parametrize("status", ["user_confirmed", "disputed", "withdrawn"])
def test_extraction_cannot_overwrite_reviewed_fact(conn, status):
    project = make_project(conn)
    bundle = make_bundle(project.id, link_paper(conn, project).id)
    store.save_candidate_bundle(conn, bundle)
    fact = bundle.methods[0]
    store.transition_fact(conn, project.id, fact.id, StatusTransitionRequest(expected_version=1,
        from_status="candidate", to_status=status, actor="Review", reason="Reviewed"))
    fact.version = 3
    fact.name = "replacement"
    with pytest.raises(store.InvalidStateError):
        store.save_candidate_bundle(conn, bundle)
    assert store.get_fact(conn, fact.id).status.value == status
    assert store.get_fact(conn, fact.id).version == 2


@pytest.mark.parametrize("kind", ["measurement", "evidence"])
def test_plan_save_rejects_unresolvable_references(conn, kind):
    project = make_project(conn)
    snapshot, _ = seed_snapshot(conn, project, link_paper(conn, project))
    plan = snapshot.plan.model_copy(deep=True)
    if kind == "measurement":
        plan.target_measurements = ["nonexistent-measurement"]
    else:
        plan.steps = [ProtocolStep(id="step1", title="Check", purpose="Verify", evidence_ids=["nonexistent-evidence"])]
    with pytest.raises(store.ProjectStoreError):
        store.save_plan(conn, project.id, PlanSaveRequest(expected_project_version=store.get_project(conn, project.id).version,
            expected_plan_version=plan.version, plan=plan))
    assert store.get_plan(conn, plan.id).version == snapshot.plan.version


@pytest.mark.parametrize("progress", [-0.1, 1.1, float("inf"), float("nan")])
def test_invalid_task_progress_does_not_corrupt_persisted_task(conn, progress):
    project = make_project(conn)
    task = store.create_task(conn, TaskKind.PROJECT_EXTRACTION, project.id, {})
    with pytest.raises(store.ProjectStoreError):
        store.update_task(conn, task.id, TaskStatus.RUNNING, progress=progress)
    assert store.get_task(conn, task.id).status == TaskStatus.QUEUED


@pytest.mark.parametrize("change", ["project", "version", "status", "document_version"])
def test_snapshot_validates_decision_and_document_versions(change):
    data = snapshot_input()
    if change == "project":
        data.decision.project_id = "foreign"
    elif change == "version":
        data.decision.project_version += 1
    elif change == "status":
        data.decision.status = "superseded"
    else:
        data.evidence[0].document_version = "another-version"
    with pytest.raises(ValueError):
        build_snapshot_content(data)


def test_plan_draft_rejects_missing_fact_evidence():
    data = plan_input()
    data.methods[0].field_evidence[0].evidence_ids = ["unknown-evidence"]
    with pytest.raises(ValueError):
        build_plan_draft(data)


def test_plan_and_comparison_reject_foreign_measurements():
    data = plan_input()
    data.measurements[0].project_id = "foreign"
    with pytest.raises(ValueError):
        build_plan_draft(data)
    bundle = image_bundle()
    bundle.measurements[0].project_id = "foreign"
    with pytest.raises(ValueError):
        compare_conditions(request(), bundle)


def test_dataset_version_conflict_does_not_contaminate_dataset_dimension():
    bundle = image_bundle()
    bundle.experiment_settings[0].field_evidence = [_binding("dataset", "ev-1"),
        _binding("methods[0].experiment_settings[0].dataset_version", "ev-1", "conflicting")]
    result = compare_conditions(request(), bundle)
    assert dimension(result, "dataset").comparable
    assert not dimension(result, "dataset_version").comparable


def test_template_is_not_labeled_as_model_output():
    assert build_plan_draft(plan_input()).source_kind.value == "system_template"


@pytest.mark.parametrize("claim", ["模型准确率达到0.95", "检测精度达到97", "image_AUROC达到0.95"])
def test_chinese_and_scoped_numeric_score_claims_are_rejected(claim):
    from app.research.suggestion_validation import validate_suggestion_steps
    accepted, rejected = validate_suggestion_steps({"additional_steps": [{"title": "检查", "purpose": "验证",
        "procedure": [claim], "acceptance_criteria": ["记录结果"], "evidence_ids": ["ev-1"]}]}, {"ev-1"})
    assert not accepted and rejected


def test_metric_like_identifier_is_not_an_unverified_score():
    from app.research.suggestion_validation import validate_suggestion_steps
    accepted, rejected = validate_suggestion_steps({"additional_steps": [{"title": "Check", "purpose": "Verify",
        "procedure": ["Inspect the AUROC2 identifier"], "acceptance_criteria": ["Record the definition"], "evidence_ids": ["ev-1"]}]}, {"ev-1"})
    assert accepted and not rejected


def test_resource_checks_cite_only_matching_field_evidence():
    from app.research.constraints import evaluate_constraints
    data = plan_input()
    data.project.constraints.allowed_datasets = ["MVTec AD"]
    data.project.constraints.compute = [ComputeConstraint(device_kind="gpu", memory=NumericValue(value=16, unit="GB"))]
    setting = data.experiment_settings[0]
    setting.resources = [NamedValue(name="memory", value=8, unit="GB")]
    setting.field_evidence = [_binding("dataset", "dataset-evidence"),
        _binding("methods[0].experiment_settings[0].resources[0].value", "memory-evidence")]
    checks = evaluate_constraints(data.project, data.methods, [setting], data.measurements)[0].checks
    memory = next(check for check in checks if check.dimension == "memory")
    dataset = next(check for check in checks if check.dimension == "dataset_policy")
    assert [ref.id for ref in memory.references] == ["memory-evidence"]
    assert [ref.id for ref in dataset.references] == ["dataset-evidence"]


@pytest.mark.parametrize("parent", ["method", "setting"])
def test_bundle_cannot_attach_children_to_another_papers_facts(conn, parent):
    project = make_project(conn)
    first = make_bundle(project.id, link_paper(conn, project).id)
    store.save_candidate_bundle(conn, first)
    conn.execute("INSERT INTO papers(uid,title,abstract) VALUES('paper-2','Other','')")
    conn.execute("INSERT INTO documents(id,paper_uid,content_hash,coverage) VALUES('doc-2','paper-2','def456','fulltext')")
    conn.commit()
    current = store.get_project(conn, project.id)
    link = store.link_paper(conn, project.id, current.version,
        PaperLinkCreate(expected_project_version=current.version, paper_uid="paper-2", role="method"))
    second = make_bundle(project.id, link.id, method_id="method-2")
    second.document_id, second.document_version = "doc-2", "sha256:def456"
    ref = second.evidence[0]
    ref.id, ref.paper_uid, ref.document_id, ref.document_version = "evidence-2", "paper-2", "doc-2", second.document_version
    for fact in [*second.methods, *second.experiment_settings, *second.measurements]:
        fact.field_evidence[0].evidence_ids = [ref.id]
    if parent == "method":
        second.experiment_settings[0].method_id = first.methods[0].id
    else:
        second.measurements[0].experiment_setting_id = first.experiment_settings[0].id
    with pytest.raises(store.InvalidStateError):
        store.save_candidate_bundle(conn, second)
    assert len(store.list_facts(conn, project.id)) == 3


def test_normalizing_metadata_does_not_mutate_input():
    from app.research_extraction.candidates import _normalize_passage
    metadata = {"original": True}
    _normalize_passage({"id": "p1", "text": "table", "metadata": metadata, "table_id": "Table 1"}, "doc1")
    assert metadata == {"original": True}


def test_inconsistent_numeric_bounds_are_retained_as_unparsed(monkeypatch):
    import json
    from app.research_extraction import candidates
    from tests.test_research_extraction import _input, _passage, _claim, _setting, _measurement
    quote = "ToySet score is between 91 and 95."
    measurement = _measurement("v1", "p1", "score", 91, quote)
    measurement["value"]["value"]["lower"] = 95
    raw = {"methods": [{"local_id": "m1", "claim_role": "current_paper_method",
                        "name": _claim("Willow", "p1", "We propose Willow."),
                        "experiment_settings": [_setting("s1", "p1", "ToySet", quote, measurement)]}]}
    monkeypatch.setattr(candidates, "chat", lambda *a, **k: json.dumps(raw))
    bundle = candidates.extract_candidates(_input([_passage("p1", "We propose Willow. " + quote)]))
    assert bundle.measurements[0].value is None
    assert bundle.measurements[0].finding_status == FindingStatus.NOT_PARSED
    assert any("invalid_numeric_bounds" in warning for warning in bundle.warnings)
