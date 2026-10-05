"""Versioned AtlasV2 projection for immutable research project snapshots.

SQLite remains the source of truth.  This module only derives a namespaced,
rebuildable Neo4j projection and never writes back to the business database.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from app.db.neo4j_client import get_driver
from app.models.research import (
    GraphEdge,
    GraphNode,
    GraphProjection,
    GraphProjectionResult,
    ProjectSnapshot,
)


ATLAS_LABEL = "AtlasV2"
PROJECTION_LABEL = "AtlasV2Projection"
NODE_LABEL = "AtlasV2Node"
RELATIONSHIP_TYPE = "ATLAS_V2_REL"


class ProjectionConflictError(RuntimeError):
    """The same immutable snapshot was presented with different graph content."""


class ProjectionSupersededError(RuntimeError):
    """A newer retry took ownership of the same projection while this run worked."""


@dataclass(frozen=True)
class ProjectionState:
    project_id: str
    snapshot_id: str
    snapshot_version: int
    status: str
    digest: str
    current: bool
    projected_nodes: int = 0
    projected_edges: int = 0


class ProjectionBackend(Protocol):
    def get_state(self, project_id: str, snapshot_id: str) -> ProjectionState | None: ...

    def begin(self, projection: GraphProjection, digest: str, token: str) -> None: ...

    def replace(self, projection: GraphProjection, token: str) -> tuple[int, int]: ...

    def complete(
        self,
        projection: GraphProjection,
        digest: str,
        token: str,
        node_count: int,
        edge_count: int,
    ) -> ProjectionState: ...

    def fail(self, projection: GraphProjection, token: str, message: str) -> None: ...


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _edge_id(kind: str, source_id: str, target_id: str) -> str:
    value = f"{kind}\x1f{source_id}\x1f{target_id}".encode()
    return f"edge:{hashlib.sha256(value).hexdigest()[:24]}"


def _claim_id(fact_id: str, version: int) -> str:
    return f"claim:{fact_id}:v{version}"


def _document_node_id(document_id: str, document_version: str) -> str:
    return f"document:{document_id}:{document_version}"


def _add_edge(
    edges: dict[str, GraphEdge],
    kind: str,
    source_id: str,
    target_id: str,
    *,
    fact_ids: list[str] | None = None,
    evidence_ids: list[str] | None = None,
    explanation: str,
) -> None:
    edge = GraphEdge(
        id=_edge_id(kind, source_id, target_id),
        kind=kind,
        source_id=source_id,
        target_id=target_id,
        fact_ids=sorted(set(fact_ids or [])),
        evidence_ids=sorted(set(evidence_ids or [])),
        properties={"explanation": explanation},
    )
    edges[edge.id] = edge


def build_graph_projection(snapshot: ProjectSnapshot) -> GraphProjection:
    """Build the explicit graph derivable from a frozen public snapshot.

    The public snapshot currently contains version references rather than full
    fact payloads.  Consequently, this function classifies only IDs whose role
    is explicit in the plan and leaves all other frozen facts as ``fact``.  It
    never guesses experiment-to-measurement or evidence-to-document links.
    """

    nodes: dict[str, GraphNode] = {}
    edges: dict[str, GraphEdge] = {}
    plan = snapshot.plan
    if plan.id is None:
        raise ValueError("快照中的方案必须具有已保存 ID")

    project_node_id = f"project:{snapshot.project_id}"
    snapshot_node_id = f"snapshot:{snapshot.id}"
    nodes[project_node_id] = GraphNode(
        id=project_node_id,
        kind="project",
        label=snapshot.project_id,
        properties={
            "project_id": snapshot.project_id,
            "frozen_project_version": snapshot.frozen_project_version,
            "frozen_constraint_version": snapshot.frozen_constraint_version,
            "domain_profile_version": snapshot.frozen_domain_profile_version,
        },
    )
    nodes[snapshot_node_id] = GraphNode(
        id=snapshot_node_id,
        kind="snapshot",
        label=f"Snapshot v{snapshot.snapshot_version}",
        properties={
            "snapshot_id": snapshot.id,
            "snapshot_version": snapshot.snapshot_version,
            "review_status": snapshot.review_status.value,
        },
    )
    nodes[snapshot.frozen_decision.id] = GraphNode(
        id=snapshot.frozen_decision.id,
        kind="decision",
        label=f"Decision v{snapshot.frozen_decision.version}",
        properties={"version": snapshot.frozen_decision.version},
    )
    nodes[plan.id] = GraphNode(
        id=plan.id,
        kind="plan",
        label=plan.title,
        properties={
            "version": plan.version,
            "status": plan.status.value,
            "source_kind": plan.source_kind.value,
            "review_status": plan.review_status.value,
        },
    )
    _add_edge(
        edges,
        "SNAPSHOT_OF",
        snapshot_node_id,
        project_node_id,
        explanation="该不可变快照属于此课题。",
    )
    _add_edge(
        edges,
        "FREEZES_DECISION",
        snapshot_node_id,
        snapshot.frozen_decision.id,
        explanation="快照冻结了指定版本的用户路线决策。",
    )
    _add_edge(
        edges,
        "FREEZES_PLAN",
        snapshot_node_id,
        plan.id,
        explanation="快照冻结了指定版本的验证方案。",
    )

    method_id = plan.selected_method_id
    nodes[method_id] = GraphNode(
        id=method_id,
        kind="method",
        label=method_id,
        properties={"role": "selected_method"},
    )
    _add_edge(
        edges,
        "SELECTS_METHOD",
        snapshot.frozen_decision.id,
        method_id,
        fact_ids=[method_id],
        explanation="冻结决策显式选择了该方法。",
    )
    _add_edge(
        edges,
        "USES_METHOD",
        plan.id,
        method_id,
        fact_ids=[method_id],
        explanation="验证方案显式采用该方法。",
    )

    for setting_id in sorted(set(plan.selected_experiment_setting_ids)):
        nodes[setting_id] = GraphNode(
            id=setting_id,
            kind="experiment_setting",
            label=setting_id,
            properties={"method_id": method_id},
        )
        _add_edge(
            edges,
            "SELECTS_SETTING",
            snapshot.frozen_decision.id,
            setting_id,
            fact_ids=[setting_id],
            explanation="冻结决策显式选择了该实验设置。",
        )
        _add_edge(
            edges,
            "USES_SETTING",
            plan.id,
            setting_id,
            fact_ids=[setting_id],
            explanation="验证方案显式采用该实验设置。",
        )
        _add_edge(
            edges,
            "HAS_SETTING",
            method_id,
            setting_id,
            fact_ids=[method_id, setting_id],
            explanation="方案明确把该实验设置归于所选方法。",
        )

    for measurement_id in sorted(set(plan.target_measurements)):
        nodes[measurement_id] = GraphNode(
            id=measurement_id,
            kind="measurement",
            label=measurement_id,
            properties={"role": "target_measurement"},
        )
        _add_edge(
            edges,
            "TARGETS_MEASUREMENT",
            plan.id,
            measurement_id,
            fact_ids=[measurement_id],
            explanation="验证方案显式列出该目标测量。",
        )

    evidence_ids: set[str] = set()
    for step in plan.steps:
        step_id = f"planstep:{plan.id}:{step.id}"
        nodes[step_id] = GraphNode(
            id=step_id,
            kind="plan_step",
            label=step.title,
            properties={"step_id": step.id, "purpose": step.purpose},
        )
        _add_edge(
            edges,
            "HAS_STEP",
            plan.id,
            step_id,
            explanation="验证方案包含该步骤。",
        )
        for evidence_id in sorted(set(step.evidence_ids)):
            evidence_ids.add(evidence_id)
            existing = nodes.get(evidence_id)
            if existing is not None and existing.kind != "evidence":
                raise ValueError(
                    f"证据 ID {evidence_id} 与 {existing.kind} 节点 ID 冲突"
                )
            nodes[evidence_id] = GraphNode(
                id=evidence_id,
                kind="evidence",
                label=evidence_id,
                properties={
                    "detail_ref": evidence_id,
                    "detail_status": "not_embedded_in_public_snapshot",
                },
            )
            _add_edge(
                edges,
                "CITES_EVIDENCE",
                step_id,
                evidence_id,
                evidence_ids=[evidence_id],
                explanation="该方案步骤显式引用了此证据。",
            )

    all_fact_ids = {ref.id for ref in snapshot.frozen_facts}
    represented_ids = {
        method_id,
        *plan.selected_experiment_setting_ids,
        *plan.target_measurements,
    }
    for ref in sorted(snapshot.frozen_facts, key=lambda item: (item.id, item.version)):
        if ref.id not in nodes:
            nodes[ref.id] = GraphNode(
                id=ref.id,
                kind="fact",
                label=ref.id,
                properties={"version": ref.version, "fact_type": "not_embedded"},
            )
        else:
            properties = dict(nodes[ref.id].properties)
            properties["version"] = ref.version
            nodes[ref.id] = nodes[ref.id].model_copy(update={"properties": properties})
        claim_id = _claim_id(ref.id, ref.version)
        nodes[claim_id] = GraphNode(
            id=claim_id,
            kind="evidence_claim",
            label=f"{ref.id} v{ref.version}",
            properties={"fact_id": ref.id, "fact_version": ref.version},
        )
        _add_edge(
            edges,
            "ASSERTS_FACT",
            claim_id,
            ref.id,
            fact_ids=[ref.id],
            explanation="该证据主张对应快照冻结的事实版本。",
        )
        _add_edge(
            edges,
            "RELIES_ON_CLAIM",
            plan.id,
            claim_id,
            fact_ids=[ref.id],
            explanation="方案冻结并依赖此事实版本；不表示科学结论必然正确。",
        )

    _add_edge(
        edges,
        "GOVERNS_PLAN",
        snapshot.frozen_decision.id,
        plan.id,
        fact_ids=sorted(all_fact_ids),
        evidence_ids=sorted(evidence_ids),
        explanation="该用户决策是冻结方案的路线依据。",
    )

    for document in snapshot.frozen_documents:
        document_node_id = _document_node_id(
            document.document_id, document.document_version
        )
        nodes[document_node_id] = GraphNode(
            id=document_node_id,
            kind="source_document",
            label=f"{document.paper_uid} / {document.document_version}",
            properties={
                "paper_link_id": document.paper_link_id,
                "paper_uid": document.paper_uid,
                "document_id": document.document_id,
                "document_version": document.document_version,
                "content_hash": document.content_hash,
            },
        )
        _add_edge(
            edges,
            "FREEZES_SOURCE",
            snapshot_node_id,
            document_node_id,
            explanation="快照冻结了该论文文档版本作为来源。",
        )

    # ``represented_ids`` is deliberately retained as an audit-friendly marker:
    # no unrepresented frozen fact is silently classified as a method/setting/result.
    for fact_id in sorted(all_fact_ids - represented_ids):
        properties = dict(nodes[fact_id].properties)
        properties["classification"] = "unknown_from_snapshot_reference"
        nodes[fact_id] = nodes[fact_id].model_copy(update={"properties": properties})

    return GraphProjection(
        project_id=snapshot.project_id,
        snapshot_id=snapshot.id,
        snapshot_version=snapshot.snapshot_version,
        nodes=sorted(nodes.values(), key=lambda item: item.id),
        edges=sorted(edges.values(), key=lambda item: item.id),
    )


def _projection_digest(projection: GraphProjection) -> str:
    payload = projection.model_dump(mode="json")
    payload["nodes"] = sorted(payload["nodes"], key=lambda item: item["id"])
    payload["edges"] = sorted(payload["edges"], key=lambda item: item["id"])
    return hashlib.sha256(_json(payload).encode()).hexdigest()


def _projection_key(projection: GraphProjection) -> str:
    return f"{projection.project_id}:{projection.snapshot_id}"


def _node_row(projection: GraphProjection, node: GraphNode, token: str) -> dict:
    return {
        "uid": f"{_projection_key(projection)}:{node.id}",
        "business_id": node.id,
        "kind": node.kind,
        "label": node.label,
        "properties_json": _json(node.properties),
        "sync_token": token,
    }


def _edge_row(projection: GraphProjection, edge: GraphEdge, token: str) -> dict:
    namespace = _projection_key(projection)
    return {
        "edge_id": edge.id,
        "source_uid": f"{namespace}:{edge.source_id}",
        "target_uid": f"{namespace}:{edge.target_id}",
        "kind": edge.kind,
        "fact_ids": edge.fact_ids,
        "evidence_ids": edge.evidence_ids,
        "properties_json": _json(edge.properties),
        "sync_token": token,
    }


def _single(result) -> object | None:
    return result.single() if hasattr(result, "single") else next(iter(result), None)


def _value(record: object, key: str, default=None):
    if record is None:
        return default
    if hasattr(record, "get"):
        return record.get(key, default)
    return record[key]  # type: ignore[index]


class _Neo4jProjectionBackend:
    def get_state(self, project_id: str, snapshot_id: str) -> ProjectionState | None:
        query = """
        // atlasv2:projection-state
        MATCH (p:AtlasV2:AtlasV2Projection {project_id: $project_id, snapshot_id: $snapshot_id})
        RETURN p.project_id AS project_id, p.snapshot_id AS snapshot_id,
               p.snapshot_version AS snapshot_version, p.status AS status,
               p.digest AS digest, coalesce(p.current, false) AS current,
               coalesce(p.projected_nodes, 0) AS projected_nodes,
               coalesce(p.projected_edges, 0) AS projected_edges
        """
        with get_driver().session() as session:
            record = _single(
                session.run(query, project_id=project_id, snapshot_id=snapshot_id)
            )
        if record is None:
            return None
        return ProjectionState(
            project_id=_value(record, "project_id"),
            snapshot_id=_value(record, "snapshot_id"),
            snapshot_version=int(_value(record, "snapshot_version")),
            status=_value(record, "status"),
            digest=_value(record, "digest", ""),
            current=bool(_value(record, "current", False)),
            projected_nodes=int(_value(record, "projected_nodes", 0)),
            projected_edges=int(_value(record, "projected_edges", 0)),
        )

    def begin(self, projection: GraphProjection, digest: str, token: str) -> None:
        key = _projection_key(projection)

        with get_driver().session() as session:
            session.run(
                """
                CREATE CONSTRAINT atlas_v2_projection_key IF NOT EXISTS
                FOR (p:AtlasV2Projection) REQUIRE p.projection_key IS UNIQUE
                """
            ).consume()
            session.run(
                """
                CREATE CONSTRAINT atlas_v2_node_uid IF NOT EXISTS
                FOR (n:AtlasV2Node) REQUIRE n.uid IS UNIQUE
                """
            ).consume()

        def write(tx) -> None:
            tx.run(
                """
                // atlasv2:begin
                MERGE (p:AtlasV2:AtlasV2Projection {projection_key: $projection_key})
                SET p.project_id = $project_id, p.snapshot_id = $snapshot_id,
                    p.snapshot_version = $snapshot_version, p.status = 'building',
                    p.current = false, p.digest = $digest, p.sync_token = $token,
                    p.projected_nodes = 0, p.projected_edges = 0,
                    p.started_at = $started_at, p.last_error = null
                """,
                projection_key=key,
                project_id=projection.project_id,
                snapshot_id=projection.snapshot_id,
                snapshot_version=projection.snapshot_version,
                digest=digest,
                token=token,
                started_at=datetime.now(UTC).isoformat(),
            ).consume()
            tx.run(
                """
                // atlasv2:clear-exact-version
                MATCH (n:AtlasV2:AtlasV2Node {projection_key: $projection_key})
                DETACH DELETE n
                """,
                projection_key=key,
            ).consume()

        with get_driver().session() as session:
            session.execute_write(write)

    def replace(self, projection: GraphProjection, token: str) -> tuple[int, int]:
        key = _projection_key(projection)
        node_rows = [_node_row(projection, node, token) for node in projection.nodes]
        node_ids = {node.id for node in projection.nodes}
        for edge in projection.edges:
            if edge.source_id not in node_ids or edge.target_id not in node_ids:
                raise ValueError(f"边 {edge.id} 引用了不存在的节点")
        edge_rows = [_edge_row(projection, edge, token) for edge in projection.edges]

        def write(tx) -> tuple[int, int]:
            node_record = _single(
                tx.run(
                    """
                    // atlasv2:write-nodes
                    MATCH (p:AtlasV2:AtlasV2Projection {
                        projection_key: $projection_key,
                        sync_token: $token,
                        status: 'building'
                    })
                    WITH p
                    UNWIND $rows AS row
                    MERGE (n:AtlasV2:AtlasV2Node {uid: row.uid})
                    SET n.projection_key = $projection_key,
                        n.project_id = $project_id, n.snapshot_id = $snapshot_id,
                        n.snapshot_version = $snapshot_version,
                        n.business_id = row.business_id, n.kind = row.kind,
                        n.label = row.label, n.properties_json = row.properties_json,
                        n.sync_token = row.sync_token
                    RETURN count(n) AS written
                    """,
                    projection_key=key,
                    project_id=projection.project_id,
                    snapshot_id=projection.snapshot_id,
                    snapshot_version=projection.snapshot_version,
                    token=token,
                    rows=node_rows,
                )
            )
            edge_record = _single(
                tx.run(
                    """
                    // atlasv2:write-edges
                    MATCH (p:AtlasV2:AtlasV2Projection {
                        projection_key: $projection_key,
                        sync_token: $token,
                        status: 'building'
                    })
                    WITH p
                    UNWIND $rows AS row
                    MATCH (source:AtlasV2:AtlasV2Node {
                        uid: row.source_uid, sync_token: $token
                    })
                    MATCH (target:AtlasV2:AtlasV2Node {
                        uid: row.target_uid, sync_token: $token
                    })
                    MERGE (source)-[rel:ATLAS_V2_REL {
                        projection_key: $projection_key, edge_id: row.edge_id
                    }]->(target)
                    SET rel.project_id = $project_id,
                        rel.snapshot_id = $snapshot_id,
                        rel.snapshot_version = $snapshot_version,
                        rel.kind = row.kind, rel.fact_ids = row.fact_ids,
                        rel.evidence_ids = row.evidence_ids,
                        rel.properties_json = row.properties_json,
                        rel.sync_token = row.sync_token
                    RETURN count(rel) AS written
                    """,
                    projection_key=key,
                    project_id=projection.project_id,
                    snapshot_id=projection.snapshot_id,
                    snapshot_version=projection.snapshot_version,
                    token=token,
                    rows=edge_rows,
                )
            )
            return (
                int(_value(node_record, "written", 0)),
                int(_value(edge_record, "written", 0)),
            )

        with get_driver().session() as session:
            written = session.execute_write(write)
        if written != (len(node_rows), len(edge_rows)):
            raise ProjectionSupersededError("同一快照已有更新的同步尝试接管")
        return written

    def complete(
        self,
        projection: GraphProjection,
        digest: str,
        token: str,
        node_count: int,
        edge_count: int,
    ) -> ProjectionState:
        key = _projection_key(projection)

        def write(tx):
            record = _single(
                tx.run(
                    """
                    // atlasv2:complete
                    MATCH (p:AtlasV2:AtlasV2Projection {
                        projection_key: $projection_key,
                        sync_token: $token,
                        status: 'building'
                    })
                    OPTIONAL MATCH (newer:AtlasV2:AtlasV2Projection {
                        project_id: $project_id, status: 'complete'
                    })
                    WHERE newer.snapshot_version > $snapshot_version
                    WITH p, count(newer) AS newer_count
                    SET p.status = 'complete', p.current = (newer_count = 0),
                        p.digest = $digest, p.projected_nodes = $node_count,
                        p.projected_edges = $edge_count,
                        p.completed_at = $completed_at, p.last_error = null
                    RETURN p.current AS current
                    """,
                    projection_key=key,
                    project_id=projection.project_id,
                    snapshot_version=projection.snapshot_version,
                    digest=digest,
                    token=token,
                    node_count=node_count,
                    edge_count=edge_count,
                    completed_at=datetime.now(UTC).isoformat(),
                )
            )
            if record is None:
                return None
            current = bool(_value(record, "current", False))
            if current:
                tx.run(
                    """
                    // atlasv2:retire-older-current
                    MATCH (older:AtlasV2:AtlasV2Projection {project_id: $project_id})
                    WHERE older.projection_key <> $projection_key
                      AND coalesce(older.current, false) = true
                      AND older.snapshot_version <= $snapshot_version
                    SET older.current = false
                    """,
                    project_id=projection.project_id,
                    projection_key=key,
                    snapshot_version=projection.snapshot_version,
                ).consume()
            return current

        with get_driver().session() as session:
            current = session.execute_write(write)
        if current is None:
            raise ProjectionSupersededError("同步令牌已失效，不能发布半完成投影")
        return ProjectionState(
            project_id=projection.project_id,
            snapshot_id=projection.snapshot_id,
            snapshot_version=projection.snapshot_version,
            status="complete",
            digest=digest,
            current=current,
            projected_nodes=node_count,
            projected_edges=edge_count,
        )

    def fail(self, projection: GraphProjection, token: str, message: str) -> None:
        with get_driver().session() as session:
            session.run(
                """
                // atlasv2:fail
                MATCH (p:AtlasV2:AtlasV2Projection {
                    projection_key: $projection_key,
                    sync_token: $token
                })
                SET p.status = 'failed', p.current = false,
                    p.last_error = $message, p.failed_at = $failed_at
                """,
                projection_key=_projection_key(projection),
                token=token,
                message=message[:4000],
                failed_at=datetime.now(UTC).isoformat(),
            ).consume()


def _get_projection_backend() -> ProjectionBackend:
    return _Neo4jProjectionBackend()


def project_graph(projection: GraphProjection) -> GraphProjectionResult:
    """Idempotently synchronize one isolated AtlasV2 snapshot projection."""

    digest = _projection_digest(projection)
    token = uuid4().hex
    backend = _get_projection_backend()
    try:
        existing = backend.get_state(projection.project_id, projection.snapshot_id)
        if existing is not None and existing.snapshot_version != projection.snapshot_version:
            raise ProjectionConflictError("同一快照 ID 不能对应不同快照版本")
        if existing is not None and existing.status == "complete":
            if existing.digest != digest:
                raise ProjectionConflictError("不可变快照的图内容与已发布投影不一致")
            return GraphProjectionResult(
                project_id=projection.project_id,
                snapshot_id=projection.snapshot_id,
                projected_nodes=existing.projected_nodes,
                projected_edges=existing.projected_edges,
            )
        backend.begin(projection, digest, token)
        node_count, edge_count = backend.replace(projection, token)
        backend.complete(
            projection, digest, token, node_count=node_count, edge_count=edge_count
        )
    except (ProjectionConflictError, ProjectionSupersededError):
        raise
    except Exception as exc:
        try:
            backend.fail(projection, token, str(exc))
        except Exception:
            pass
        raise RuntimeError(f"AtlasV2 图投影同步失败: {exc}") from exc
    return GraphProjectionResult(
        project_id=projection.project_id,
        snapshot_id=projection.snapshot_id,
        projected_nodes=node_count,
        projected_edges=edge_count,
    )
