"""Source overview is a bounded read projection, never a rewrite of old nodes."""

import pytest
from fastapi.testclient import TestClient

from app.db import projects
from app.graphsvc import local
from app.knowledge import extraction, store, unified
from app.main import app
from app.models.research import ProjectConstraints, ResearchProjectCreate


def add_source(conn, scope, title, *, legacy_papers=0):
    sid = store.identity(scope, title)
    source = {
        "id": sid, "project_id": scope, "asset_id": sid, "kind": "paper",
        "title": title, "paper_uid": title, "version": "fixture-v1",
    }
    conn.execute("INSERT INTO kw_sources VALUES(?,?,?,?,?)", (sid, scope, sid, 0, store.encode(source)))
    root = store.put_record(conn, "kw_nodes", extraction.node(source, "root", "paper", title, "Source root", []))
    for index in range(legacy_papers):
        # Old entities retain their IDs, even when their labels/kinds resemble the root.
        child = store.put_record(conn, "kw_nodes", extraction.node(source, ["legacy", index], "paper", title, "Historical entity", [], metadata={"legacy_id": index + 1}))
        store.put_record(conn, "kw_edges", extraction.edge(source, root["id"], child["id"], "MENTIONS", "mentions", "Saved legacy claim", []))
    method = store.put_record(conn, "kw_nodes", extraction.node(source, "method", "method", "Useful method", "Source-backed method", [], parent_id=root["id"]))
    store.put_record(conn, "kw_edges", extraction.edge(source, root["id"], method["id"], "CONTAINS", "contains", "Saved grouping", []))
    return source, root, method


@pytest.fixture
def overview_data():
    with store.connection() as conn:
        pids = [projects.create_project(conn, ResearchProjectCreate(
            title=title, research_question="Inspect sources", domain="custom",
            constraints=ProjectConstraints(version=1, objective="Learn"),
        )).id for title in ["Space A", "Space B"]]
        records = [add_source(conn, "library", f"Source {index:02}", legacy_papers=27 if index == 0 else 0) for index in range(5)]
        records += [add_source(conn, pid, "Source 00", legacy_papers=2) for pid in pids]
    return pids, records


def test_source_overview_round_robins_scopes_and_paginates_only_real_roots(overview_data):
    pids, records = overview_data
    with store.connection() as conn:
        before = conn.total_changes
        first = unified.graph(conn, overview=True, limit=3)
        assert first["overview"] and first["total_nodes"] == 7 and first["truncated"]
        assert {node["project_id"] for node in first["nodes"]} == {"library", *pids}
        assert all(unified.is_source_root(node) and node["metadata"]["source_root"] for node in first["nodes"])
        assert first["nodes"][0]["metadata"]["child_count"] == 28
        second = unified.graph(conn, overview=True, limit=3, offset=3)
        third = unified.graph(conn, overview=True, limit=3, offset=6)
        shown = first["nodes"] + second["nodes"] + third["nodes"]
        assert len(shown) == len({node["id"] for node in shown}) == 7
        assert {node["id"] for node in shown} == {root["id"] for _, root, _ in records}
        assert not third["truncated"]
        assert conn.total_changes == before
        assert "source_root" not in store.record(conn, "kw_nodes", "library", records[0][1]["id"])["metadata"]


def test_overview_api_keeps_default_full_graph_and_scope_filters(overview_data):
    pids, _ = overview_data
    client = TestClient(app)
    for scope in [None, "library", *pids]:
        params = {"limit": 500, **({"project_id": scope} if scope else {})}
        full = client.get("/api/knowledge/graph", params=params).json()
        explicit_full = client.get("/api/knowledge/graph", params={**params, "overview": False}).json()
        old = client.get("/api/graph/overview", params=params).json()
        assert full == explicit_full
        assert [node["id"] for node in full["nodes"]] == [node["uid"] for node in old["nodes"]]
        overview = client.get("/api/knowledge/graph", params={**params, "overview": True}).json()
        assert all(unified.is_source_root(node) for node in overview["nodes"])
        assert len(overview["nodes"]) < len(full["nodes"])
        if scope:
            assert {node["project_id"] for node in overview["nodes"]} == {scope}
    assert client.get("/api/knowledge/graph", params={"overview": True, "project_id": "invalid"}).status_code == 404
    assert client.get("/api/knowledge/graph", params={"overview": True, "q": "absent"}).json()["nodes"] == []


def test_root_expansion_prioritizes_knowledge_but_search_retains_legacy_ids(overview_data):
    _, records = overview_data
    _, root, method = records[0]
    view = local.view(uid=root["id"], project_id="library", limit=3)
    assert view["nodes"][0]["uid"] == root["id"]
    assert view["nodes"][0]["metadata"]["source_root"]
    assert view["nodes"][0]["metadata"]["child_count"] == 28
    assert method["id"] in {node["uid"] for node in view["nodes"]}
    assert view["truncated"]
    found = local.search("Source 00", node_type="paper", project_id="library", limit=100)
    assert len(found) == 28 and len({node["uid"] for node in found}) == 28
    assert len(local.context("Source 00", node_type="paper", project_id="library")["nodes"]) > 1


def test_source_root_detail_keeps_deep_link_expansion_marker_without_writing(overview_data):
    _, records = overview_data
    root = records[0][1]
    response = TestClient(app).get(f'/api/knowledge/nodes/{root["id"]}', params={"project_id": "library"})
    assert response.status_code == 200
    assert response.json()["node"]["metadata"]["source_root"] is True
    overview = TestClient(app).get("/api/knowledge/graph", params={"overview": True, "project_id": "library"}).json()
    overview_root = next(node for node in overview["nodes"] if node["id"] == root["id"])
    assert response.json()["node"]["metadata"]["child_count"] == overview_root["metadata"]["child_count"] == 28
    with store.connection() as conn:
        assert "source_root" not in store.record(conn, "kw_nodes", "library", root["id"])["metadata"]


def test_same_named_legacy_paper_detail_is_not_promoted_to_source_root(overview_data):
    _, records = overview_data
    source, root, _ = records[0]
    legacy_id = store.identity("library", source["id"], ["legacy", 0])
    response = TestClient(app).get(f"/api/knowledge/nodes/{legacy_id}", params={"project_id": "library"})
    assert response.status_code == 200
    node = response.json()["node"]
    assert node["label"] == root["label"] and node["kind"] == "paper"
    assert node["id"] == legacy_id and not node["metadata"].get("source_root")


def test_overview_excludes_inactive_or_false_roots_and_caps_pages(overview_data):
    pids, records = overview_data
    source, root, method = records[0]
    with store.connection() as conn:
        method["quality_status"] = "withdrawn"
        store.put_record(conn, "kw_nodes", method, preserve_user=False)
        false_root = extraction.node(source, "other-root", "paper", "False root", "Not a source root", [])
        store.put_record(conn, "kw_nodes", false_root)
        malformed = extraction.node({**source, "project_id": pids[0]}, "root", "paper", "Wrong scope", "Wrong source scope", [])
        store.put_record(conn, "kw_nodes", malformed)
        conn.execute("UPDATE kw_sources SET removed=1 WHERE id=?", (records[1][0]["id"],))
        records[2][1]["hidden"] = True
        store.put_record(conn, "kw_nodes", records[2][1], preserve_user=False)
        for index in range(55):
            add_source(conn, "library", f"Extra {index:02}")
        value = unified.graph(conn, overview=True, limit=1000)
        assert len(value["nodes"]) == 50 and value["truncated"]
        assert {node["project_id"] for node in value["nodes"]} == {"library", *pids}
        remaining = unified.graph(conn, overview=True, offset=50, limit=1000)
        selected = {node["id"]: node for node in value["nodes"] + remaining["nodes"]}
        assert not {false_root["id"], malformed["id"], records[1][1]["id"], records[2][1]["id"]} & selected.keys()
        assert selected[root["id"]]["metadata"]["child_count"] == 28
        assert not remaining["truncated"]
