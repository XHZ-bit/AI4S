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

def test_neighbors_uses_bounded_canonical_graph_without_external_driver(monkeypatch):
    calls = []

    def snapshot(project_id=None):
        calls.append(project_id)
        nodes = [{'uid': str(i), 'name': str(i), 'type': 'concept'} for i in range(8)]
        return {'nodes': nodes, 'links': [{'source': str(i), 'target': str(i+1)} for i in range(7)]}
    monkeypatch.setattr('app.graphsvc.local.snapshot', snapshot)
    from app.graphsvc.queries import neighbors

    result = neighbors('0', depth=99)
    assert [node['uid'] for node in result['nodes']] == ['0', '1', '2', '3']
    assert calls == [None]
