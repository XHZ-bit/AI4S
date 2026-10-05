from datetime import UTC, datetime
import json
from types import ModuleType
import sys

import pytest

from app.db import projects as store
from app.db.sqlite import connect
from app.models.research import (
    CandidateBundle,
    ComparisonCandidate,
    ComparisonRequest,
    EvidenceKind,
    EvidenceRef,
    ExperimentSetting,
    FieldEvidence,
    FrozenDocument,
    GraphNode,
    GraphEdge,
    GraphProjection,
    GraphProjectionResult,
    GraphQuery,
    GraphQueryResult,
    Measurement,
    MethodCard,
    NumericValue,
    PaperLinkCreate,
    PaperLinkPatch,
    PlanGenerateRequest,
    PlanSaveRequest,
    ProjectConstraints,
    ProjectSnapshot,
    ResearchDecisionCreate,
    ResearchProjectCreate,
    ResearchProjectPatch,
    StatusTransitionRequest,
    TaskKind,
    TaskStatus,
    ValidationPlan,
    VersionRef,
)
from app.research import service


@pytest.fixture
def conn(tmp_path):
    value = connect(str(tmp_path / "research-t1.sqlite3"))
    store.init_research_schema(value)
    value.execute(
        "INSERT INTO papers(uid,title,abstract) VALUES(?,?,?)", ("paper-1", "Paper", "")
    )
    value.execute(
        "INSERT INTO documents(id,paper_uid,content_hash,coverage) VALUES(?,?,?,?)",
        ("doc-1", "paper-1", "abc123", "fulltext"),
    )
    value.execute(
        "INSERT INTO passages(id,document_id,heading,text,page,ordinal) VALUES(?,?,?,?,?,?)",
        ("passage-1", "doc-1", "Method", "Method A", 1, 0),
    )
    value.commit()
    yield value
    value.close()


def make_project(conn, title="课题"):
    return store.create_project(
        conn,
        ResearchProjectCreate(
            title=title,
            research_question="哪个候选值得验证？",
            domain="image_anomaly_detection",
            constraints=ProjectConstraints(version=1, objective="首轮验证"),
        ),
    )


def link_paper(conn, project):
    return store.link_paper(
        conn,
        project.id,
        project.version,
        PaperLinkCreate(
            expected_project_version=project.version,
            paper_uid="paper-1",
            role="primary",
        ),
    )


def make_bundle(project_id, link_id, *, method_id="method-1", bad_evidence=False):
    now = datetime.now(UTC)
    evidence = EvidenceRef(
        id="evidence-1",
        source_kind="literature_report",
        finding_status="reported",
        kind=EvidenceKind.TEXT,
        paper_uid="paper-1",
        document_id="doc-1",
        document_version="sha256:abc123",
        passage_id="passage-1",
        quote="Method A",
    )
    binding = FieldEvidence(
        field_path="name",
        source_kind="literature_report",
        finding_status="reported",
        evidence_ids=["missing" if bad_evidence else evidence.id],
    )
    method = MethodCard(
        id=method_id,
        project_id=project_id,
        version=1,
        status="candidate",
        source_kind="literature_report",
        finding_status="reported",
        field_evidence=[binding],
        paper_link_id=link_id,
        name="Method A",
        created_at=now,
        updated_at=now,
    )
    setting = ExperimentSetting(
        id=f"setting-{method_id}",
        project_id=project_id,
        version=1,
        source_kind="literature_report",
        finding_status="reported",
        field_evidence=[binding],
        paper_link_id=link_id,
        method_id=method.id,
        name="fixed",
        dataset="MVTec",
        split="official",
        created_at=now,
        updated_at=now,
    )
    measurement = Measurement(
        id=f"measurement-{method_id}",
        project_id=project_id,
        version=1,
        source_kind="literature_report",
        finding_status="reported",
        field_evidence=[binding],
        experiment_setting_id=setting.id,
        metric_name="image_auroc",
        value=NumericValue(value=0.9),
        created_at=now,
        updated_at=now,
    )
    return CandidateBundle(
        project_id=project_id,
        paper_link_id=link_id,
        document_id="doc-1",
        document_version="sha256:abc123",
        extraction_version="test-v1",
        evidence=[evidence],
        methods=[method],
        experiment_settings=[setting],
        measurements=[measurement],
    )


def seed_facts(conn, project, link):
    bundle = make_bundle(project.id, link.id)
    store.save_candidate_bundle(conn, bundle)
    return (
        bundle.methods[0],
        bundle.experiment_settings[0],
        bundle.measurements[0],
        bundle.evidence[0],
    )


def seed_snapshot(conn, project, link):
    project = store.get_project(conn, project.id)
    method, setting, measurement, evidence = seed_facts(conn, project, link)
    decision = store.save_decision(
        conn,
        project.id,
        ResearchDecisionCreate(
            expected_project_version=project.version,
            selected_method_id=method.id,
            selected_experiment_setting_ids=[setting.id],
            considered_candidate_ids=[measurement.id],
            rationale="最小闭环",
            evidence_ids=[evidence.id],
        ),
    )
    plan = store.save_plan(
        conn,
        project.id,
        PlanSaveRequest(
            expected_project_version=project.version,
            expected_plan_version=0,
            plan=ValidationPlan(
                project_id=project.id,
                version=1,
                title="验证方案",
                objective="验证可行性",
                selected_method_id=method.id,
                selected_experiment_setting_ids=[setting.id],
                target_measurements=[measurement.id],
                source_kind="user_input",
            ),
        ),
    )
    snapshot = ProjectSnapshot(
        id="snapshot-1",
        project_id=project.id,
        snapshot_version=1,
        frozen_project_version=project.version,
        frozen_constraint_version=project.constraints.version,
        frozen_domain_profile_version=project.domain_profile_version,
        frozen_decision=VersionRef(id=decision.id, version=decision.version),
        frozen_documents=[
            FrozenDocument(
                paper_link_id=link.id,
                paper_uid="paper-1",
                document_id="doc-1",
                document_version="sha256:abc123",
                content_hash="abc123",
            )
        ],
        frozen_facts=[
            VersionRef(id=method.id, version=1),
            VersionRef(id=setting.id, version=1),
            VersionRef(id=measurement.id, version=1),
        ],
        plan=plan,
        created_at=datetime.now(UTC),
    )
    return store.save_snapshot(conn, snapshot), method


def test_link_is_idempotent_and_project_version_conflicts(conn):
    project = make_project(conn)
    link = link_paper(conn, project)
    current = store.get_project(conn, project.id)
    same = link_paper(conn, current)
    assert same.id == link.id
    assert store.get_project(conn, project.id).version == 2
    with pytest.raises(store.VersionConflictError):
        store.update_project(
            conn, project.id, ResearchProjectPatch(expected_version=1, title="stale")
        )


def test_invalid_evidence_reference_rolls_back_and_projects_are_isolated(conn):
    first = make_project(conn, "A")
    link = link_paper(conn, first)
    with pytest.raises(store.InvalidStateError):
        store.save_candidate_bundle(
            conn, make_bundle(first.id, link.id, bad_evidence=True)
        )
    assert store.list_facts(conn, first.id) == []
    second = make_project(conn, "B")
    seed_facts(conn, first, link)
    with pytest.raises(store.NotFoundError):
        store.save_decision(
            conn,
            second.id,
            ResearchDecisionCreate(
                expected_project_version=second.version,
                selected_method_id="method-1",
                selected_experiment_setting_ids=["setting-method-1"],
                rationale="越权",
            ),
        )


def test_transition_audit_and_transaction_history(conn):
    project = make_project(conn)
    link = link_paper(conn, project)
    method, *_ = seed_facts(conn, project, link)
    changed = store.transition_fact(
        conn,
        project.id,
        method.id,
        StatusTransitionRequest(
            expected_version=1,
            from_status="candidate",
            to_status="user_confirmed",
            actor="reviewer",
            reason="核对完成",
        ),
    )
    assert changed.version == 2
    assert len(store.fact_audit(conn, method.id)) == 1
    assert (
        conn.execute(
            "SELECT COUNT(*) n FROM research_fact_versions WHERE fact_id=?",
            (method.id,),
        ).fetchone()["n"]
        == 2
    )


def test_snapshot_is_immutable_and_projection_outbox_is_atomic(conn):
    project = make_project(conn)
    link = link_paper(conn, project)
    snapshot, _ = seed_snapshot(conn, project, link)
    state = store.get_projection_state(conn, snapshot.id)
    assert state["status"] == "pending"
    with pytest.raises(store.InvalidStateError):
        store.save_snapshot(
            conn, snapshot.model_copy(update={"frozen_project_version": 999})
        )
    assert (
        store.get_snapshot(conn, project.id, snapshot.id).frozen_project_version
        == snapshot.frozen_project_version
    )


def test_projection_failure_keeps_snapshot_and_is_retryable(conn, monkeypatch):
    project = make_project(conn)
    link = link_paper(conn, project)
    snapshot, _ = seed_snapshot(conn, project, link)
    module = ModuleType("app.research.graph_projection")
    module.build_graph_projection = lambda value: value

    def fail(_):
        raise RuntimeError("neo4j down")

    module.project_graph = fail
    monkeypatch.setitem(sys.modules, "app.research.graph_projection", module)
    with pytest.raises(service.CapabilityUnavailable):
        service.run_graph_projection(conn, snapshot.id)
    assert store.get_snapshot(conn, project.id, snapshot.id) == snapshot
    state = store.get_projection_state(conn, snapshot.id)
    assert state["status"] == "failed" and state["attempt_count"] == 1


def test_graph_projection_and_query_preserve_identity_and_parameters(conn, monkeypatch):
    project = make_project(conn)
    link = link_paper(conn, project)
    snapshot, _ = seed_snapshot(conn, project, link)
    projection_module = ModuleType("app.research.graph_projection")
    projection_module.build_graph_projection = lambda value: value
    projection_module.project_graph = lambda value: GraphProjectionResult(
        project_id=value.project_id,
        snapshot_id=value.id,
        projected_nodes=3,
        projected_edges=2,
    )
    monkeypatch.setitem(sys.modules, "app.research.graph_projection", projection_module)
    projected = service.run_graph_projection(conn, snapshot.id)
    assert projected.project_id == project.id
    assert store.get_projection_state(conn, snapshot.id)["status"] == "succeeded"

    seen = []
    query_module = ModuleType("app.research.graph_queries")

    def query_project_graph(query):
        seen.append(query)
        return GraphQueryResult(
            project_id=query.project_id,
            snapshot_id=query.snapshot_id,
            nodes=[
                GraphNode(
                    id=query.node_ids[0], kind=query.kinds[0], label="动态查询结果"
                )
            ],
        )

    query_module.query_project_graph = query_project_graph
    monkeypatch.setitem(sys.modules, "app.research.graph_queries", query_module)
    result = service.query_graph(
        conn,
        GraphQuery(
            project_id=project.id,
            snapshot_id=snapshot.id,
            node_ids=["method-1"],
            kinds=["method"],
            limit=7,
        ),
    )
    assert result.nodes[0].id == "method-1"
    assert seen[0].limit == 7


def test_graph_query_rejects_cross_project_pending_and_wrong_result(conn, monkeypatch):
    project = make_project(conn)
    link = link_paper(conn, project)
    snapshot, _ = seed_snapshot(conn, project, link)
    other = make_project(conn, "其他课题")
    with pytest.raises(store.NotFoundError):
        service.query_graph(
            conn, GraphQuery(project_id=other.id, snapshot_id=snapshot.id)
        )
    with pytest.raises(service.CapabilityUnavailable, match="pending"):
        service.query_graph(
            conn, GraphQuery(project_id=project.id, snapshot_id=snapshot.id)
        )


def test_real_t5_three_query_modes_and_sync_status(conn, monkeypatch):
    from app.research import graph_queries

    project = make_project(conn)
    link = link_paper(conn, project)
    snapshot, _ = seed_snapshot(conn, project, link)
    store.update_projection_state(conn, snapshot.id, "succeeded")
    projection = GraphProjection(
        project_id=project.id,
        snapshot_id=snapshot.id,
        snapshot_version=snapshot.snapshot_version,
        nodes=[
            GraphNode(id="decision-1", kind="decision", label="决策"),
            GraphNode(id="method-1", kind="method", label="方法"),
            GraphNode(id="setting-1", kind="experiment_setting", label="设置"),
            GraphNode(id="plan-1", kind="plan", label="方案"),
            GraphNode(id="evidence-1", kind="evidence", label="证据"),
        ],
        edges=[
            GraphEdge(
                id="selects",
                kind="SELECTS_METHOD",
                source_id="decision-1",
                target_id="method-1",
            ),
            GraphEdge(
                id="setting",
                kind="HAS_SETTING",
                source_id="method-1",
                target_id="setting-1",
            ),
            GraphEdge(
                id="cites",
                kind="CITES_EVIDENCE",
                source_id="plan-1",
                target_id="evidence-1",
            ),
        ],
    )

    class Backend:
        def load(self, query):
            assert query.project_id == project.id
            assert query.snapshot_id == snapshot.id
            return graph_queries.ProjectionRead(
                projection=projection, status="complete", current=True
            )

    monkeypatch.setattr(graph_queries, "_get_query_backend", lambda: Backend())
    cases = [
        ("dependency_path", "decision-1", "selects"),
        ("method_context", "method-1", "setting"),
        ("impact_path", "evidence-1", "cites"),
    ]
    for mode, anchor, expected_edge in cases:
        result = service.query_graph(
            conn,
            GraphQuery(
                project_id=project.id,
                snapshot_id=snapshot.id,
                node_ids=[anchor],
                kinds=[mode],
            ),
        )
        assert expected_edge in {edge.id for edge in result.edges}
        status = next(node for node in result.nodes if node.kind == "projection_status")
        assert status.properties["status"] == "complete"

    with pytest.raises(store.ValidationError):
        service.query_graph(
            conn,
            GraphQuery(
                project_id=project.id,
                snapshot_id=snapshot.id,
                kinds=["impact_path"],
            ),
        )

    store.update_projection_state(conn, snapshot.id, "succeeded")
    query_module = ModuleType("app.research.graph_queries")
    query_module.query_project_graph = lambda query: GraphQueryResult(
        project_id="wrong-project", snapshot_id=query.snapshot_id
    )
    monkeypatch.setitem(sys.modules, "app.research.graph_queries", query_module)
    with pytest.raises(service.CapabilityUnavailable, match="不属于"):
        service.query_graph(
            conn, GraphQuery(project_id=project.id, snapshot_id=snapshot.id)
        )


def test_removing_link_marks_only_history_for_review(conn):
    project = make_project(conn)
    link = link_paper(conn, project)
    snapshot, _ = seed_snapshot(conn, project, link)
    store.update_paper_link(
        conn, project.id, link.id, PaperLinkPatch(expected_version=1, status="removed")
    )
    stale = store.get_snapshot(conn, project.id, snapshot.id)
    assert stale.review_status.value == "needs_review"
    assert stale.frozen_documents == snapshot.frozen_documents


def test_project_constraint_change_marks_frozen_snapshot_for_review(conn):
    project = make_project(conn)
    link = link_paper(conn, project)
    snapshot, _ = seed_snapshot(conn, project, link)
    current = store.get_project(conn, project.id)
    updated_constraints = current.constraints.model_copy(
        update={"version": 2, "objective": "调整后的首轮验证目标"}
    )

    store.update_project(
        conn,
        project.id,
        ResearchProjectPatch(
            expected_version=current.version,
            constraints=updated_constraints,
        ),
    )

    stale = store.get_snapshot(conn, project.id, snapshot.id)
    assert stale.review_status.value == "needs_review"
    assert "项目约束已更新" in stale.review_reasons
    assert stale.frozen_constraint_version == snapshot.frozen_constraint_version


def test_duplicate_tasks_are_idempotent_and_extraction_handler_uses_t2_substitute(
    conn, monkeypatch
):
    project = make_project(conn)
    link = link_paper(conn, project)
    project = store.get_project(conn, project.id)
    params = {"project_id": project.id, "link_id": link.id, "document_id": "doc-1"}
    first = store.create_task(conn, TaskKind.PROJECT_EXTRACTION, project.id, params)
    second = store.create_task(conn, TaskKind.PROJECT_EXTRACTION, project.id, params)
    assert second.id == first.id
    module = ModuleType("app.research.extraction")
    module.extract_candidates = lambda input: make_bundle(project.id, link.id)
    monkeypatch.setitem(sys.modules, "app.research.extraction", module)
    finished = service.run_research_task(conn, first.id)
    assert finished.status.value == "succeeded"
    assert len(store.list_facts(conn, project.id)) == 3
    assert service.run_research_task(conn, first.id).id == first.id


def test_t3_comparison_decision_and_plan_orchestration(conn, monkeypatch):
    project = make_project(conn)
    link = link_paper(conn, project)
    project = store.get_project(conn, project.id)
    first = make_bundle(project.id, link.id)
    second = make_bundle(project.id, link.id, method_id="method-2").model_copy(
        update={"evidence": []}
    )
    store.save_candidate_bundle(conn, first)
    store.save_candidate_bundle(conn, second)
    comparison = service.compare_project_conditions(
        conn,
        project.id,
        ComparisonRequest(
            project_id=project.id,
            project_version=project.version,
            domain=project.domain,
            candidates=[
                ComparisonCandidate(
                    method_id="method-1",
                    experiment_setting_id="setting-method-1",
                    measurement_ids=["measurement-method-1"],
                ),
                ComparisonCandidate(
                    method_id="method-2",
                    experiment_setting_id="setting-method-2",
                    measurement_ids=["measurement-method-2"],
                ),
            ],
        ),
    )
    assert comparison.project_id == project.id
    decision = service.create_decision(
        conn,
        project.id,
        ResearchDecisionCreate(
            expected_project_version=project.version,
            selected_method_id="method-1",
            selected_experiment_setting_ids=["setting-method-1"],
            considered_candidate_ids=["method-1", "method-2"],
            rationale="先验证 Method A",
            evidence_ids=["evidence-1"],
        ),
    )
    with pytest.raises(service.CapabilityUnavailable, match="尚未授权接入"):
        service.build_plan(
            conn,
            project.id,
            PlanGenerateRequest(
                expected_project_version=project.version,
                decision_id=decision.id,
                decision_version=decision.version,
            ),
        )
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
    draft = service.build_plan(
        conn,
        project.id,
        PlanGenerateRequest(
            expected_project_version=project.version,
            decision_id=decision.id,
            decision_version=decision.version,
        ),
    )
    assert draft.id is None and draft.project_id == project.id


def test_additive_schema_preserves_legacy_rows(tmp_path):
    conn = connect(str(tmp_path / "legacy.sqlite3"))
    conn.execute(
        "INSERT INTO papers(uid,title,abstract) VALUES(?,?,?)",
        ("legacy", "Old", "kept"),
    )
    conn.commit()
    store.init_research_schema(conn)
    assert (
        conn.execute("SELECT abstract FROM papers WHERE uid=?", ("legacy",)).fetchone()[
            "abstract"
        ]
        == "kept"
    )
    conn.close()


def test_async_plan_without_provider_finishes_failed_with_explicit_error(conn):
    project = make_project(conn)
    link = link_paper(conn, project)
    seed_facts(conn, project, link)
    project = store.get_project(conn, project.id)
    decision = store.save_decision(
        conn,
        project.id,
        ResearchDecisionCreate(
            expected_project_version=project.version,
            selected_method_id="method-1",
            selected_experiment_setting_ids=["setting-method-1"],
            rationale="验证无 provider 时的明确失败",
            evidence_ids=["evidence-1"],
        ),
    )
    dispatched = []
    task = service.enqueue_plan_generation(
        conn,
        project.id,
        PlanGenerateRequest(
            expected_project_version=project.version,
            decision_id=decision.id,
            decision_version=decision.version,
        ),
        dispatched.append,
    )

    assert task.status == TaskStatus.QUEUED
    assert dispatched == [task.id]
    finished = service.run_research_task(conn, task.id)
    assert finished.status == TaskStatus.FAILED
    assert finished.result is None
    assert finished.error is not None
    assert finished.error.code == "not_implemented"
    assert finished.error.retryable is False
    assert "尚未授权接入" in finished.error.message


def test_restart_interrupts_task_and_failed_projection_can_retry(conn, monkeypatch):
    project = make_project(conn)
    link = link_paper(conn, project)
    snapshot, _ = seed_snapshot(conn, project, link)
    dispatched = []
    original = service.enqueue_graph_projection(
        conn, project.id, snapshot.id, dispatched.append
    )
    store.update_task(conn, original.id, TaskStatus.RUNNING, progress=0.2)
    store.update_projection_state(conn, snapshot.id, "running")

    assert store.interrupt_incomplete_tasks(conn) == 1
    interrupted = store.get_task(conn, original.id)
    assert interrupted.status == TaskStatus.INTERRUPTED
    assert interrupted.result is None
    store.update_projection_state(
        conn, snapshot.id, "failed", error="interrupted by restart"
    )

    retry = service.enqueue_graph_projection(
        conn, project.id, snapshot.id, dispatched.append, retry=True
    )
    assert retry.id != original.id
    assert retry.status == TaskStatus.QUEUED
    assert dispatched == [original.id, retry.id]
    retry_row = conn.execute(
        "SELECT retry_of FROM research_async_tasks WHERE task_id=?", (retry.id,)
    ).fetchone()
    assert retry_row["retry_of"] == original.id
    assert store.get_projection_state(conn, snapshot.id)["status"] == "pending"

    projection_module = ModuleType("app.research.graph_projection")
    projection_module.build_graph_projection = lambda value: value
    projection_module.project_graph = lambda value: GraphProjectionResult(
        project_id=value.project_id,
        snapshot_id=value.id,
        projected_nodes=1,
        projected_edges=0,
    )
    monkeypatch.setitem(sys.modules, "app.research.graph_projection", projection_module)
    completed = service.run_research_task(conn, retry.id)
    assert completed.status == TaskStatus.SUCCEEDED
    assert store.get_projection_state(conn, snapshot.id)["status"] == "succeeded"
    assert store.get_snapshot(conn, project.id, snapshot.id) is not None


def test_constraint_conflict_does_not_overwrite_reviewed_snapshot(conn):
    project = make_project(conn)
    link = link_paper(conn, project)
    snapshot, _ = seed_snapshot(conn, project, link)
    current = store.get_project(conn, project.id)
    updated = store.update_project(
        conn,
        project.id,
        ResearchProjectPatch(
            expected_version=current.version,
            constraints=current.constraints.model_copy(
                update={"version": 2, "objective": "更新后的约束"}
            ),
        ),
    )
    with pytest.raises(store.VersionConflictError) as conflict:
        store.update_project(
            conn,
            project.id,
            ResearchProjectPatch(
                expected_version=current.version,
                constraints=current.constraints.model_copy(
                    update={"version": 2, "objective": "过期写入"}
                ),
            ),
        )

    assert conflict.value.current_version == updated.version
    assert store.get_project(conn, project.id) == updated
    reviewed = store.get_snapshot(conn, project.id, snapshot.id)
    assert reviewed.review_status.value == "needs_review"
    assert reviewed.review_reasons == ["项目约束已更新"]
    assert reviewed.frozen_project_version == snapshot.frozen_project_version
    assert reviewed.frozen_constraint_version == snapshot.frozen_constraint_version


def test_snapshot_json_export_keeps_frozen_refs_after_dependency_changes(conn):
    project = make_project(conn)
    link = link_paper(conn, project)
    snapshot, method = seed_snapshot(conn, project, link)
    store.transition_fact(
        conn,
        project.id,
        method.id,
        StatusTransitionRequest(
            expected_version=1,
            from_status="candidate",
            to_status="disputed",
            actor="reviewer",
            reason="证据存在争议",
        ),
    )
    current = store.get_project(conn, project.id)
    store.update_project(
        conn,
        project.id,
        ResearchProjectPatch(
            expected_version=current.version,
            constraints=current.constraints.model_copy(
                update={"version": 2, "objective": "新的项目条件"}
            ),
        ),
    )

    exported = json.loads(
        service.snapshot_json(
            store.get_snapshot(conn, project.id, snapshot.id)
        ).decode("utf-8")
    )
    assert exported["review_status"] == "needs_review"
    assert {tuple(ref.values()) for ref in exported["frozen_facts"]} == {
        (ref.id, ref.version) for ref in snapshot.frozen_facts
    }
    assert exported["frozen_documents"] == [
        item.model_dump(mode="json") for item in snapshot.frozen_documents
    ]
    assert exported["frozen_project_version"] == snapshot.frozen_project_version
    assert exported["frozen_constraint_version"] == snapshot.frozen_constraint_version
    assert exported["frozen_decision"] == snapshot.frozen_decision.model_dump(
        mode="json"
    )
    assert exported["plan"]["id"] == snapshot.plan.id
    assert exported["plan"]["version"] == snapshot.plan.version
    assert store.list_facts(conn, project.id, kind="method")[0].version == 2
