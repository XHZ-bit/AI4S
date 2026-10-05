"""Explainable queries over complete, project-scoped AtlasV2 projections."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol

from app.db.neo4j_client import get_driver
from app.models.research import GraphEdge, GraphNode, GraphProjection, GraphQuery, GraphQueryResult


DEPENDENCY_QUERY = "dependency_path"
METHOD_CONTEXT_QUERY = "method_context"
IMPACT_QUERY = "impact_path"
_INTERNAL_LOAD_LIMIT = 10_001

_DEPENDENCY_EDGE_KINDS = {
    "FREEZES_DECISION",
    "FREEZES_PLAN",
    "SELECTS_METHOD",
    "SELECTS_SETTING",
    "GOVERNS_PLAN",
    "USES_METHOD",
    "USES_SETTING",
    "TARGETS_MEASUREMENT",
    "RELIES_ON_CLAIM",
    "ASSERTS_FACT",
    "HAS_STEP",
    "CITES_EVIDENCE",
    "FREEZES_SOURCE",
}
_METHOD_EDGE_KINDS = {
    "HAS_SETTING",
    "HAS_MEASUREMENT",
    "ASSERTS_FACT",
    "SUPPORTED_BY",
    "FROM_SOURCE",
}
_IMPACT_EDGE_KINDS = {
    "CITES_EVIDENCE",
    "HAS_STEP",
    "RELIES_ON_CLAIM",
    "GOVERNS_PLAN",
    "FREEZES_PLAN",
    "ASSERTS_FACT",
    "USES_METHOD",
    "USES_SETTING",
    "TARGETS_MEASUREMENT",
    "SELECTS_METHOD",
    "SELECTS_SETTING",
}


@dataclass(frozen=True)
class ProjectionRead:
    projection: GraphProjection
    status: str
    current: bool


class QueryBackend(Protocol):
    def load(self, query: GraphQuery) -> ProjectionRead | None: ...


def _single(result):
    return result.single() if hasattr(result, "single") else next(iter(result), None)


def _value(record, key: str, default=None):
    if record is None:
        return default
    if hasattr(record, "get"):
        return record.get(key, default)
    return record[key]


def _decode_properties(value: str | None) -> dict:
    if not value:
        return {}
    decoded = json.loads(value)
    if not isinstance(decoded, dict):
        raise RuntimeError("AtlasV2 节点或关系属性格式无效")
    return decoded


class _Neo4jQueryBackend:
    def load(self, query: GraphQuery) -> ProjectionRead | None:
        marker_query = """
        // atlasv2:query-status
        MATCH (p:AtlasV2:AtlasV2Projection {
            project_id: $project_id, snapshot_id: $snapshot_id
        })
        RETURN p.status AS status, coalesce(p.current, false) AS current,
               p.snapshot_version AS snapshot_version,
               p.projection_key AS projection_key
        """
        nodes_query = """
        // atlasv2:query-nodes
        MATCH (n:AtlasV2:AtlasV2Node {projection_key: $projection_key})
        RETURN n.business_id AS id, n.kind AS kind, n.label AS label,
               n.properties_json AS properties_json
        ORDER BY n.business_id
        LIMIT $load_limit
        """
        edges_query = """
        // atlasv2:query-edges
        MATCH (source:AtlasV2:AtlasV2Node {projection_key: $projection_key})
              -[rel:ATLAS_V2_REL {projection_key: $projection_key}]->
              (target:AtlasV2:AtlasV2Node {projection_key: $projection_key})
        RETURN rel.edge_id AS id, rel.kind AS kind,
               source.business_id AS source_id, target.business_id AS target_id,
               coalesce(rel.fact_ids, []) AS fact_ids,
               coalesce(rel.evidence_ids, []) AS evidence_ids,
               rel.properties_json AS properties_json
        ORDER BY rel.edge_id
        LIMIT $load_limit
        """
        try:
            with get_driver().session() as session:
                marker = _single(
                    session.run(
                        marker_query,
                        project_id=query.project_id,
                        snapshot_id=query.snapshot_id,
                    )
                )
                if marker is None:
                    return None
                status = str(_value(marker, "status", "pending"))
                current = bool(_value(marker, "current", False))
                snapshot_version = int(_value(marker, "snapshot_version", 0))
                projection_key = _value(marker, "projection_key")
                if status != "complete":
                    return ProjectionRead(
                        projection=GraphProjection(
                            project_id=query.project_id,
                            snapshot_id=query.snapshot_id,
                            snapshot_version=max(1, snapshot_version),
                        ),
                        status=status,
                        current=current,
                    )
                nodes = [
                    GraphNode(
                        id=_value(row, "id"),
                        kind=_value(row, "kind"),
                        label=_value(row, "label"),
                        properties=_decode_properties(_value(row, "properties_json")),
                    )
                    for row in session.run(
                        nodes_query,
                        projection_key=projection_key,
                        load_limit=_INTERNAL_LOAD_LIMIT,
                    )
                ]
                edges = [
                    GraphEdge(
                        id=_value(row, "id"),
                        kind=_value(row, "kind"),
                        source_id=_value(row, "source_id"),
                        target_id=_value(row, "target_id"),
                        fact_ids=list(_value(row, "fact_ids", [])),
                        evidence_ids=list(_value(row, "evidence_ids", [])),
                        properties=_decode_properties(_value(row, "properties_json")),
                    )
                    for row in session.run(
                        edges_query,
                        projection_key=projection_key,
                        load_limit=_INTERNAL_LOAD_LIMIT,
                    )
                ]
                if (
                    len(nodes) >= _INTERNAL_LOAD_LIMIT
                    or len(edges) >= _INTERNAL_LOAD_LIMIT
                ):
                    raise RuntimeError(
                        "AtlasV2 投影超过首版安全查询上限，不能返回可能不完整的路径"
                    )
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(f"AtlasV2 图服务不可用: {exc}") from exc
        return ProjectionRead(
            projection=GraphProjection(
                project_id=query.project_id,
                snapshot_id=query.snapshot_id,
                snapshot_version=snapshot_version,
                nodes=nodes,
                edges=edges,
            ),
            status=status,
            current=current,
        )


def _get_query_backend() -> QueryBackend:
    return _Neo4jQueryBackend()


def _status_node(read: ProjectionRead, requested_snapshot_id: str) -> GraphNode:
    return GraphNode(
        id=f"projection-status:{read.projection.snapshot_id}",
        kind="projection_status",
        label=f"AtlasV2 {read.status}",
        properties={
            "status": read.status,
            "sync_status": read.status,
            "requested_snapshot_id": requested_snapshot_id,
            "actual_snapshot_id": read.projection.snapshot_id,
            "actual_snapshot_version": read.projection.snapshot_version,
            "current": read.current,
        },
    )


def _edge_with_explanation(edge: GraphEdge, nodes: dict[str, GraphNode]) -> GraphEdge:
    source = nodes.get(edge.source_id)
    target = nodes.get(edge.target_id)
    properties = dict(edge.properties)
    properties["path"] = (
        f"{source.label if source else edge.source_id} "
        f"-[{edge.kind}]-> {target.label if target else edge.target_id}"
    )
    properties.setdefault(
        "explanation",
        f"显式关系 {edge.kind} 将 {edge.source_id} 与 {edge.target_id} 连接。",
    )
    return edge.model_copy(update={"properties": properties})


def _walk(
    projection: GraphProjection,
    anchor_ids: list[str],
    allowed_kinds: set[str],
    *,
    reverse: bool,
    limit: int,
) -> GraphQueryResult:
    nodes = {node.id: node for node in projection.nodes}
    selected_node_ids = {node_id for node_id in anchor_ids if node_id in nodes}
    selected_edges: dict[str, GraphEdge] = {}
    frontier = list(selected_node_ids)
    while frontier and len(selected_edges) < limit:
        current = frontier.pop(0)
        for edge in projection.edges:
            if edge.kind not in allowed_kinds or edge.id in selected_edges:
                continue
            matches = edge.target_id == current if reverse else edge.source_id == current
            if not matches:
                continue
            next_id = edge.source_id if reverse else edge.target_id
            selected_edges[edge.id] = _edge_with_explanation(edge, nodes)
            if next_id not in selected_node_ids:
                selected_node_ids.add(next_id)
                frontier.append(next_id)
            if len(selected_edges) >= limit:
                break
    selected_nodes = [nodes[node_id] for node_id in selected_node_ids]
    return GraphQueryResult(
        project_id=projection.project_id,
        snapshot_id=projection.snapshot_id,
        nodes=sorted(selected_nodes, key=lambda item: item.id)[:limit],
        edges=sorted(selected_edges.values(), key=lambda item: item.id)[:limit],
    )


def explain_dependencies(
    projection: GraphProjection, node_id: str, *, limit: int = 200
) -> GraphQueryResult:
    """Return explicit fact/evidence paths used by a decision or plan."""

    return _walk(
        projection, [node_id], _DEPENDENCY_EDGE_KINDS, reverse=False, limit=limit
    )


def explain_method_context(
    projection: GraphProjection, method_id: str, *, limit: int = 200
) -> GraphQueryResult:
    """Return explicitly linked settings, measurements, claims and sources."""

    return _walk(
        projection, [method_id], _METHOD_EDGE_KINDS, reverse=False, limit=limit
    )


def explain_impact(
    projection: GraphProjection, changed_evidence_id: str, *, limit: int = 200
) -> GraphQueryResult:
    """Return decisions/plans that explicitly depend on changed evidence or a claim."""

    return _walk(
        projection,
        [changed_evidence_id],
        _IMPACT_EDGE_KINDS,
        reverse=True,
        limit=limit,
    )


def _merge_results(
    projection: GraphProjection, results: list[GraphQueryResult], limit: int
) -> GraphQueryResult:
    nodes = {node.id: node for result in results for node in result.nodes}
    edges = {edge.id: edge for result in results for edge in result.edges}
    return GraphQueryResult(
        project_id=projection.project_id,
        snapshot_id=projection.snapshot_id,
        nodes=sorted(nodes.values(), key=lambda item: item.id)[:limit],
        edges=sorted(edges.values(), key=lambda item: item.id)[:limit],
    )


def _load_complete(query: GraphQuery) -> ProjectionRead:
    try:
        read = _get_query_backend().load(query)
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"AtlasV2 图服务不可用: {exc}") from exc
    if read is None:
        raise RuntimeError("AtlasV2 投影不存在或尚未同步")
    if read.status != "complete":
        raise RuntimeError(f"AtlasV2 投影尚不可查询，当前状态: {read.status}")
    return read


def _with_status(
    result: GraphQueryResult,
    read: ProjectionRead,
    requested_snapshot_id: str,
    limit: int,
) -> GraphQueryResult:
    status_node = _status_node(read, requested_snapshot_id)
    nodes = [node for node in result.nodes if node.id != status_node.id]
    return result.model_copy(update={"nodes": ([status_node] + nodes)[:limit]})


def query_project_graph(query: GraphQuery) -> GraphQueryResult:
    """Query only a complete AtlasV2 projection and include sync status."""

    read = _load_complete(query)

    projection = read.projection
    modes = set(query.kinds) & {
        DEPENDENCY_QUERY,
        METHOD_CONTEXT_QUERY,
        IMPACT_QUERY,
    }
    if modes and not query.node_ids:
        raise RuntimeError("路径查询必须提供 node_ids")
    results: list[GraphQueryResult] = []
    for node_id in query.node_ids:
        if DEPENDENCY_QUERY in modes:
            results.append(explain_dependencies(projection, node_id, limit=query.limit))
        if METHOD_CONTEXT_QUERY in modes:
            results.append(explain_method_context(projection, node_id, limit=query.limit))
        if IMPACT_QUERY in modes:
            results.append(explain_impact(projection, node_id, limit=query.limit))
    if results:
        result = _merge_results(projection, results, query.limit)
        return _with_status(result, read, query.snapshot_id, query.limit)

    ordinary_kinds = set(query.kinds) - modes
    selected_nodes = [
        node
        for node in projection.nodes
        if (not query.node_ids or node.id in query.node_ids)
        and (not ordinary_kinds or node.kind in ordinary_kinds)
    ]
    node_index = {node.id: node for node in projection.nodes}
    if query.node_ids:
        selected_ids = {node.id for node in selected_nodes}
        selected_edges = [
            _edge_with_explanation(edge, node_index)
            for edge in projection.edges
            if edge.source_id in selected_ids or edge.target_id in selected_ids
        ]
        selected_ids.update(
            endpoint
            for edge in selected_edges
            for endpoint in (edge.source_id, edge.target_id)
        )
        selected_nodes = [node for node in projection.nodes if node.id in selected_ids]
    else:
        selected_ids = {node.id for node in selected_nodes}
        selected_edges = [
            _edge_with_explanation(edge, node_index)
            for edge in projection.edges
            if edge.source_id in selected_ids and edge.target_id in selected_ids
        ]
    result = GraphQueryResult(
        project_id=projection.project_id,
        snapshot_id=projection.snapshot_id,
        nodes=selected_nodes[: query.limit],
        edges=selected_edges[: query.limit],
    )
    return _with_status(result, read, query.snapshot_id, query.limit)


def query_dependencies(
    project_id: str, snapshot_id: str, node_id: str, *, limit: int = 200
) -> GraphQueryResult:
    query = GraphQuery(project_id=project_id, snapshot_id=snapshot_id, limit=limit)
    read = _load_complete(query)
    result = explain_dependencies(read.projection, node_id, limit=limit)
    return _with_status(result, read, snapshot_id, limit)


def query_method_context(
    project_id: str, snapshot_id: str, method_id: str, *, limit: int = 200
) -> GraphQueryResult:
    query = GraphQuery(project_id=project_id, snapshot_id=snapshot_id, limit=limit)
    read = _load_complete(query)
    result = explain_method_context(read.projection, method_id, limit=limit)
    return _with_status(result, read, snapshot_id, limit)


def query_impact(
    project_id: str,
    snapshot_id: str,
    changed_evidence_id: str,
    *,
    limit: int = 200,
) -> GraphQueryResult:
    query = GraphQuery(project_id=project_id, snapshot_id=snapshot_id, limit=limit)
    read = _load_complete(query)
    result = explain_impact(read.projection, changed_evidence_id, limit=limit)
    return _with_status(result, read, snapshot_id, limit)
