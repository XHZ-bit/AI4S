"""Compatibility shape over the single account-scoped knowledge ledger."""

from app.knowledge import store, unified
from app.graphsvc.resources import access_links


def snapshot(project_id=None):
    with store.connection() as conn:
        data = unified.graph(conn, project_id=project_id, limit=100000)
        nodes = []
        by_id = {n["id"]: n for n in data["nodes"]}
        source_counts = {}
        for node in data["nodes"]:
            key = (node["project_id"], node["source_id"])
            source_counts[key] = source_counts.get(key, 0) + 1
        for n in data["nodes"]:
            if unified.is_source_root(n):
                n["metadata"] = {
                    **n.get("metadata", {}),
                    "source_root": True,
                    "child_count": source_counts[(n["project_id"], n["source_id"])] - 1,
                }
            evidence = store.evidence(conn, n["project_id"], n.get("evidence_ids", []))
            nodes.append(
                {
                    **n,
                    "uid": n["id"],
                    "node_id": n["id"],
                    "name": n["label"],
                    "type": n["kind"],
                    "access_links": access_links(n["label"], n["kind"]),
                    "sources": [
                        {
                            "paper_uid": n.get("paper_uid"),
                            "paper_title": n.get("source_title"),
                            "passage_id": n.get("metadata", {}).get(
                                "legacy_passage_id"
                            ),
                            "source_id": n["source_id"],
                            "project_id": n["project_id"],
                        }
                    ],
                    "evidence": evidence,
                }
            )
        links = [
            {
                **e,
                "rel_type": e["kind"],
                "quality_status": e.get("quality_status", "candidate"),
                "paper_uid": by_id[e["source"]].get("paper_uid"),
                "passage_id": e.get("metadata", {}).get("legacy_passage_id"),
            }
            for e in data["edges"]
        ]
        return {
            "nodes": nodes,
            "links": links,
            "backend": "sqlite",
            "contract": "unified-knowledge-v1",
            "scopes": data["scopes"],
            "notice": "统一知识图谱：资料库与研究空间共享来源，各空间的修订独立保存。",
        }


def view(limit=100, uid=None, depth=1, project_id=None):
    limit = max(1, min(int(limit), 500))
    data = snapshot(project_id)
    if uid is not None:
        source_root = any(n["uid"] == uid and unified.is_source_root(n) for n in data["nodes"])
        selected = {
            n["uid"]
            for n in data["nodes"]
            if n["uid"] == uid
            or n.get("paper_uid") == uid
            or n.get("metadata", {}).get("legacy_uid") == uid
        }
        for _ in range(max(1, min(depth, 3))):
            selected |= {
                endpoint
                for link in data["links"]
                if link["source"] in selected or link["target"] in selected
                for endpoint in (link["source"], link["target"])
            }
        data["nodes"] = sorted(
            [node for node in data["nodes"] if node["uid"] in selected],
            key=lambda node: (
                node["uid"] != uid,
                source_root and node["type"] in {"paper", "report", "code", "results"} and not unified.is_source_root(node),
            ),
        )
    # Keep related endpoints together when applying the display cap.
    nodes = data["nodes"][:limit]
    selected = {node["uid"] for node in nodes}
    links = [
        link
        for link in data["links"]
        if link["source"] in selected and link["target"] in selected
    ]
    return {
        **data,
        "nodes": nodes,
        "links": links[: limit * 3],
        "truncated": len(data["nodes"]) > limit or len(links) > limit * 3,
    }


def search(query, node_type=None, limit=20, project_id=None):
    return [
        node
        for node in snapshot(project_id)["nodes"]
        if query.casefold() in node["name"].casefold()
        and (not node_type or node["type"] == node_type)
    ][:limit]


def context(query="", node_type=None, limit=50, project_id=None, seed=None):
    """Show a collection of matches together with their actual source context."""
    limit = max(1, min(int(limit), 50))
    data = snapshot(project_id)
    all_nodes = {n["uid"]: n for n in data["nodes"]}
    links = data["links"]
    if seed:
        allowed = {
            n["uid"]
            for n in data["nodes"]
            if n["uid"] == seed
            or n.get("paper_uid") == seed
            or n.get("metadata", {}).get("legacy_uid") == seed
        }
        for _ in range(3):
            allowed |= {
                x
                for link in links
                if link["source"] in allowed or link["target"] in allowed
                for x in (link["source"], link["target"])
            }
        all_nodes = {k: v for k, v in all_nodes.items() if k in allowed}
        links = [
            link
            for link in links
            if link["source"] in allowed and link["target"] in allowed
        ]
    matches = [
        n
        for n in all_nodes.values()
        if query.casefold() in n["name"].casefold()
        and (not node_type or n["type"] == node_type)
    ]
    degree = {uid: 0 for uid in all_nodes}
    for link in links:
        degree[link["source"]] += 1
        degree[link["target"]] += 1
    matches.sort(key=lambda n: (-degree[n["uid"]], n["name"].casefold()))
    selected = [n["uid"] for n in matches[: min(20, max(1, limit // 2))]]
    matched = set(selected)
    edges_by_node = {uid: [] for uid in all_nodes}
    for link in links:
        edges_by_node[link["source"]].append(link["target"])
        edges_by_node[link["target"]].append(link["source"])
    # Round-robin neighbor inclusion keeps multiple matching entities visible.
    seen = set(selected)
    frontier = selected[:]
    for _ in range(2):
        next_frontier = []
        for uid in frontier:
            neighbors = sorted(
                edges_by_node[uid],
                key=lambda x: (
                    all_nodes[x]["type"] != "paper",
                    -degree[x],
                    all_nodes[x]["name"],
                ),
            )
            for other in neighbors:
                if other not in seen:
                    if len(selected) >= limit:
                        break
                    selected.append(other)
                    seen.add(other)
                    next_frontier.append(other)
        frontier = next_frontier
    result_nodes = [{**all_nodes[uid], "is_match": uid in matched} for uid in selected]
    result_links = [
        link for link in links if link["source"] in seen and link["target"] in seen
    ]
    return {
        **data,
        "nodes": result_nodes,
        "links": result_links[: limit * 3],
        "matched_count": len(matches),
        "shown_matches": len(matched),
        "context_count": len(result_nodes) - len(matched),
        "truncated": len(matches) > len(matched)
        or any(n not in seen for uid in seen for n in edges_by_node[uid])
        or len(result_links) > limit * 3,
        "notice": "匹配节点与关联论文、方法共同展示；所有连线来自当前空间已保存的来源记录。",
    }
