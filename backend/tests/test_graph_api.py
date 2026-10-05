from fastapi.testclient import TestClient

from app.main import app

NODES = [
    {"uid": "method:ppo", "name": "PPO", "type": "method"},
    {"uid": "method:sac", "name": "SAC", "type": "method"},
    {"uid": "concept:td", "name": "TD学习", "type": "concept"},
]
LINKS = [{"source": "method:ppo", "target": "concept:td", "rel_type": "USES"}]


def test_search_nodes(monkeypatch):
    monkeypatch.setattr(
        "app.graphsvc.queries.search_nodes",
        lambda q, **kw: [n for n in NODES if q.lower() in n["name"].lower()],
    )
    client = TestClient(app)
    resp = client.get("/api/graph/nodes", params={"q": "PO"}).json()
    assert [n["uid"] for n in resp["items"]] == ["method:ppo"]


def test_neighbors(monkeypatch):
    monkeypatch.setattr(
        "app.graphsvc.queries.neighbors", lambda uid, **kw: {"nodes": NODES, "links": LINKS}
    )
    client = TestClient(app)
    resp = client.get("/api/graph/neighbors/method:ppo").json()
    assert len(resp["nodes"]) == 3
    assert resp["links"][0]["rel_type"] == "USES"

def test_neighbors_uses_literal_bounded_depth_and_entity_label(monkeypatch):
    calls = []

    class Session:
        def __enter__(self): return self
        def __exit__(self, *args): return None
        def run(self, query, **params):
            calls.append((query, params))
            if "RETURN DISTINCT node.uid" in query:
                return [{"uid": "method:ppo", "name": "PPO", "type": "method"}]
            return []

    class Driver:
        def session(self): return Session()

    monkeypatch.setattr("app.graphsvc.queries.get_driver", lambda: Driver())
    from app.graphsvc.queries import neighbors

    result = neighbors("method:ppo", depth=99)
    assert result["nodes"][0]["uid"] == "method:ppo"
    assert all("$depth" not in query for query, _ in calls)
    assert all(":Entity" in query for query, _ in calls)
    assert "[*0..3]" in calls[0][0]
