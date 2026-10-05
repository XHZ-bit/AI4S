from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.models.research import (
    FrozenDocument,
    GraphEdge,
    GraphNode,
    GraphProjection,
    GraphQueryResult,
    PlanStatus,
    ProjectSnapshot,
    ProtocolStep,
    SourceKind,
    ValidationPlan,
    VersionRef,
)
from app.research import graph_projection, graph_queries
from app.research.graph_projection import ProjectionState


def _snapshot(
    *, project_id: str = "project-a", snapshot_id: str = "snapshot-1", version: int = 1
) -> ProjectSnapshot:
    plan = ValidationPlan(
        id=f"plan-{project_id}-{version}",
        project_id=project_id,
        version=version,
        status=PlanStatus.SAVED,
        title="首轮验证",
        objective="验证所选路线",
        selected_method_id="method-1",
        selected_experiment_setting_ids=["setting-1", "setting-2"],
        steps=[
            ProtocolStep(
                id="step-1",
                title="核对来源",
                purpose="保留显式证据路径",
                evidence_ids=["evidence-literature", "evidence-user"],
            )
        ],
        target_measurements=["measurement-1"],
        source_kind=SourceKind.USER_INPUT,
    )
    return ProjectSnapshot(
        id=snapshot_id,
        project_id=project_id,
        snapshot_version=version,
        frozen_project_version=version,
        frozen_constraint_version=version,
        frozen_domain_profile_version="image-anomaly-v1",
        frozen_decision=VersionRef(id=f"decision-{project_id}", version=version),
        frozen_documents=[
            FrozenDocument(
                paper_link_id="paper-link-1",
                paper_uid="paper-1",
                document_id="document-1",
                document_version="v1",
                content_hash="sha256:fixture",
            )
        ],
        frozen_facts=[
            VersionRef(id="method-1", version=1),
            VersionRef(id="setting-1", version=1),
            VersionRef(id="setting-2", version=1),
            VersionRef(id="measurement-1", version=1),
            VersionRef(id="unclassified-fact", version=2),
        ],
        plan=plan,
        created_at=datetime(2026, 10, 4, tzinfo=UTC),
    )


class FakeProjectionBackend:
    def __init__(self):
        self.states: dict[tuple[str, str], ProjectionState] = {}
        self.projections: dict[tuple[str, str], GraphProjection] = {}
        self.tokens: dict[tuple[str, str], str] = {}
        self.begin_calls = 0
        self.cleared_keys: list[tuple[str, str]] = []
        self.fail_replace = False

    def get_state(self, project_id: str, snapshot_id: str):
        return self.states.get((project_id, snapshot_id))

    def begin(self, projection, digest: str, token: str):
        key = (projection.project_id, projection.snapshot_id)
        self.begin_calls += 1
        self.cleared_keys.append(key)
        self.tokens[key] = token
        self.projections.pop(key, None)
        self.states[key] = ProjectionState(
            project_id=projection.project_id,
            snapshot_id=projection.snapshot_id,
            snapshot_version=projection.snapshot_version,
            status="building",
            digest=digest,
            current=False,
        )

    def replace(self, projection, token: str):
        key = (projection.project_id, projection.snapshot_id)
        if self.fail_replace:
            raise OSError("isolated graph interrupted")
        if self.tokens.get(key) != token:
            raise graph_projection.ProjectionSupersededError("stale token")
        self.projections[key] = projection
        return len(projection.nodes), len(projection.edges)

    def complete(
        self,
        projection,
        digest: str,
        token: str,
        node_count: int,
        edge_count: int,
    ):
        key = (projection.project_id, projection.snapshot_id)
        if self.tokens.get(key) != token:
            raise graph_projection.ProjectionSupersededError("stale token")
        newer_exists = any(
            state.project_id == projection.project_id
            and state.status == "complete"
            and state.snapshot_version > projection.snapshot_version
            for state in self.states.values()
        )
        current = not newer_exists
        if current:
            for other_key, state in list(self.states.items()):
                if (
                    state.project_id == projection.project_id
                    and state.status == "complete"
                    and state.snapshot_version <= projection.snapshot_version
                ):
                    self.states[other_key] = ProjectionState(
                        **{**state.__dict__, "current": False}
                    )
        state = ProjectionState(
            project_id=projection.project_id,
            snapshot_id=projection.snapshot_id,
            snapshot_version=projection.snapshot_version,
            status="complete",
            digest=digest,
            current=current,
            projected_nodes=node_count,
            projected_edges=edge_count,
        )
        self.states[key] = state
        return state

    def fail(self, projection, token: str, message: str):
        key = (projection.project_id, projection.snapshot_id)
        state = self.states.get(key)
        if state is not None and self.tokens.get(key) == token:
            self.states[key] = ProjectionState(
                **{**state.__dict__, "status": "failed", "current": False}
            )


def test_snapshot_projection_preserves_settings_sources_and_claims():
    projection = graph_projection.build_graph_projection(_snapshot())
    nodes = {node.id: node for node in projection.nodes}
    edges = {(edge.kind, edge.source_id, edge.target_id) for edge in projection.edges}

    assert nodes["method-1"].kind == "method"
    assert nodes["setting-1"].kind == "experiment_setting"
    assert nodes["setting-2"].kind == "experiment_setting"
    assert nodes["measurement-1"].kind == "measurement"
    assert nodes["claim:unclassified-fact:v2"].kind == "evidence_claim"
    assert nodes["unclassified-fact"].properties["classification"] == (
        "unknown_from_snapshot_reference"
    )
    assert ("HAS_SETTING", "method-1", "setting-1") in edges
    assert ("HAS_SETTING", "method-1", "setting-2") in edges
    assert ("CITES_EVIDENCE", "planstep:plan-project-a-1:step-1", "evidence-user") in edges
    assert ("CITES_EVIDENCE", "planstep:plan-project-a-1:step-1", "evidence-literature") in edges


def test_sync_is_idempotent_project_scoped_retryable_and_newest_wins(monkeypatch):
    backend = FakeProjectionBackend()
    monkeypatch.setattr(graph_projection, "_get_projection_backend", lambda: backend)

    first = graph_projection.build_graph_projection(_snapshot())
    result = graph_projection.project_graph(first)
    repeated = graph_projection.project_graph(first)
    assert result == repeated
    assert backend.begin_calls == 1

    other_project = graph_projection.build_graph_projection(
        _snapshot(project_id="project-b", snapshot_id="snapshot-1")
    )
    graph_projection.project_graph(other_project)
    assert ("project-a", "snapshot-1") in backend.projections
    assert ("project-b", "snapshot-1") in backend.projections

    backend.fail_replace = True
    interrupted = graph_projection.build_graph_projection(
        _snapshot(snapshot_id="snapshot-interrupted", version=2)
    )
    with pytest.raises(RuntimeError, match="同步失败"):
        graph_projection.project_graph(interrupted)
    assert backend.states[("project-a", "snapshot-interrupted")].status == "failed"
    assert ("project-a", "snapshot-1") in backend.projections

    backend.fail_replace = False
    graph_projection.project_graph(interrupted)
    assert backend.states[("project-a", "snapshot-interrupted")].status == "complete"
    assert backend.states[("project-a", "snapshot-interrupted")].current is True
    assert backend.states[("project-a", "snapshot-1")].current is False

    late_old = graph_projection.build_graph_projection(
        _snapshot(snapshot_id="snapshot-late-old", version=1)
    )
    graph_projection.project_graph(late_old)
    assert backend.states[("project-a", "snapshot-late-old")].current is False
    assert backend.states[("project-a", "snapshot-interrupted")].current is True
    assert backend.cleared_keys[-1] == ("project-a", "snapshot-late-old")


def _rich_projection(*, include_evidence_edge: bool = True) -> GraphProjection:
    nodes = [
        GraphNode(id="method", kind="method", label="Method"),
        GraphNode(id="setting-a", kind="experiment_setting", label="Setting A"),
        GraphNode(id="setting-b", kind="experiment_setting", label="Setting B"),
        GraphNode(id="measurement-a", kind="measurement", label="AUROC A"),
        GraphNode(id="measurement-b", kind="measurement", label="AUROC B"),
        GraphNode(id="claim", kind="evidence_claim", label="Claim"),
        GraphNode(
            id="evidence-literature",
            kind="evidence",
            label="Literature evidence",
            properties={
                "source_kind": "literature_report",
                "finding_status": "withdrawn",
                "detail_ref": "evidence-literature",
                "locator_json": '{"page":3,"table_id":"table-2"}',
            },
        ),
        GraphNode(
            id="evidence-user",
            kind="evidence",
            label="User correction",
            properties={
                "source_kind": "user_input",
                "detail_ref": "evidence-user",
            },
        ),
        GraphNode(id="step", kind="plan_step", label="Step"),
        GraphNode(id="decision", kind="decision", label="Decision"),
        GraphNode(id="plan", kind="plan", label="Plan"),
        GraphNode(id="unrelated-plan", kind="plan", label="Unrelated plan"),
    ]
    raw_edges = [
        ("has-a", "HAS_SETTING", "method", "setting-a"),
        ("has-b", "HAS_SETTING", "method", "setting-b"),
        ("measure-a", "HAS_MEASUREMENT", "setting-a", "measurement-a"),
        ("measure-b", "HAS_MEASUREMENT", "setting-b", "measurement-b"),
        ("supported", "SUPPORTED_BY", "measurement-a", "claim"),
        ("source-lit", "FROM_SOURCE", "claim", "evidence-literature"),
        ("source-user", "FROM_SOURCE", "claim", "evidence-user"),
        ("governs", "GOVERNS_PLAN", "decision", "plan"),
        ("step", "HAS_STEP", "plan", "step"),
    ]
    if include_evidence_edge:
        raw_edges.append(("cites", "CITES_EVIDENCE", "step", "evidence-literature"))
    edges = [
        GraphEdge(
            id=edge_id,
            kind=kind,
            source_id=source,
            target_id=target,
            fact_ids=["claim"] if kind in {"SUPPORTED_BY", "FROM_SOURCE"} else [],
            evidence_ids=[target] if target.startswith("evidence-") else [],
            properties={"explanation": f"fixture {kind}"},
        )
        for edge_id, kind, source, target in raw_edges
    ]
    return GraphProjection(
        project_id="project-a",
        snapshot_id="snapshot-1",
        snapshot_version=7,
        nodes=nodes,
        edges=edges,
    )


def test_three_explainable_queries_use_only_explicit_paths():
    projection = _rich_projection()

    method = graph_queries.explain_method_context(projection, "method")
    assert {"setting-a", "setting-b", "measurement-a", "measurement-b"} <= {
        node.id for node in method.nodes
    }
    assert "evidence-literature" in {node.id for node in method.nodes}
    assert "evidence-user" in {node.id for node in method.nodes}
    assert all(edge.properties.get("path") for edge in method.edges)

    dependencies = graph_queries.explain_dependencies(projection, "decision")
    assert {"decision", "plan", "step", "evidence-literature"} <= {
        node.id for node in dependencies.nodes
    }

    impact = graph_queries.explain_impact(projection, "evidence-literature")
    impacted_ids = {node.id for node in impact.nodes}
    assert {"decision", "plan"} <= impacted_ids
    assert "unrelated-plan" not in impacted_ids
    assert all(edge.properties.get("explanation") for edge in impact.edges)


def test_withdrawn_evidence_keeps_historical_impact_but_removed_edge_does_not():
    historical = graph_queries.explain_impact(
        _rich_projection(include_evidence_edge=True), "evidence-literature"
    )
    assert "plan" in {node.id for node in historical.nodes}

    revised = graph_queries.explain_impact(
        _rich_projection(include_evidence_edge=False), "evidence-literature"
    )
    assert {node.id for node in revised.nodes} == {"evidence-literature"}
    assert revised.edges == []


class FakeQueryBackend:
    def __init__(self, read):
        self.read = read

    def load(self, query):
        assert query.project_id == "project-a"
        return self.read


class FailingQueryBackend:
    def load(self, query):
        raise OSError("isolated Neo4j unavailable")


def test_query_contract_rejects_incomplete_and_returns_frontend_consumable_shape(
    monkeypatch,
):
    projection = _rich_projection()
    building = graph_queries.ProjectionRead(
        projection=projection, status="building", current=False
    )
    monkeypatch.setattr(
        graph_queries, "_get_query_backend", lambda: FakeQueryBackend(building)
    )
    with pytest.raises(RuntimeError, match="building"):
        graph_queries.query_dependencies(
            "project-a", "snapshot-1", "decision"
        )

    complete = graph_queries.ProjectionRead(
        projection=projection, status="complete", current=True
    )
    monkeypatch.setattr(
        graph_queries, "_get_query_backend", lambda: FakeQueryBackend(complete)
    )
    responses = {
        "dependencies": graph_queries.query_dependencies(
            "project-a", "snapshot-1", "decision"
        ),
        "method": graph_queries.query_method_context(
            "project-a", "snapshot-1", "method"
        ),
        "impact": graph_queries.query_impact(
            "project-a", "snapshot-1", "evidence-literature"
        ),
    }
    for response in responses.values():
        validated = GraphQueryResult.model_validate(response.model_dump(mode="json"))
        status = next(
            node for node in validated.nodes if node.kind == "projection_status"
        )
        assert validated.project_id == "project-a"
        assert validated.snapshot_id == "snapshot-1"
        assert status.properties == {
            "status": "complete",
            "sync_status": "complete",
            "requested_snapshot_id": "snapshot-1",
            "actual_snapshot_id": "snapshot-1",
            "actual_snapshot_version": 7,
            "current": True,
        }
        assert all(edge.kind and edge.properties.get("path") for edge in validated.edges)

    method = responses["method"]
    assert {"setting-a", "setting-b", "measurement-a", "measurement-b"} <= {
        node.id for node in method.nodes
    }
    validated = responses["impact"]
    evidence = next(node for node in validated.nodes if node.id == "evidence-literature")
    assert evidence.properties["detail_ref"] == "evidence-literature"
    assert evidence.properties["locator_json"] == '{"page":3,"table_id":"table-2"}'
    assert {node.id for node in validated.nodes if node.kind in {"decision", "plan"}} == {
        "decision",
        "plan",
    }

    monkeypatch.setattr(
        graph_queries, "_get_query_backend", lambda: FailingQueryBackend()
    )
    with pytest.raises(RuntimeError, match="图服务不可用"):
        graph_queries.query_dependencies("project-a", "snapshot-1", "decision")
