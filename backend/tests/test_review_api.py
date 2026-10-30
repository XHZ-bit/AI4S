from fastapi.testclient import TestClient

from app.db.proposals import get_proposal, save_proposal
from app.db.sqlite import connect
from app.main import app

GRAPH = []


def _patch(monkeypatch, conn):
    GRAPH.clear()
    monkeypatch.setattr("app.api.review._connect", lambda: connect())
    monkeypatch.setattr("app.graphsvc.entities.merge_entity", lambda t, u, n: GRAPH.append(("E", t, u, n)))
    monkeypatch.setattr("app.graphsvc.entities.merge_relation", lambda r, s, d: GRAPH.append(("R", r, s, d)))


def test_review_queue_and_approve_entity(tmp_path, monkeypatch):
    conn = connect()
    _patch(monkeypatch, conn)
    pid = save_proposal(conn, "p1", "entity", {"type": "method", "name": "PPO", "evidence": "we use PPO"}, 0.9)

    client = TestClient(app)
    q = client.get("/api/review/queue").json()
    assert [i["id"] for i in q["items"]] == [pid]

    resp = client.post(f"/api/review/{pid}/decision", json={"action": "approve"})
    assert resp.status_code == 200
    assert get_proposal(conn, pid)["status"] == "approved"
    from app.knowledge.unified import ledger
    assert any(r['payload'].get('name') == 'PPO' for r in ledger(conn))
    assert GRAPH == []


def test_approve_relation_resolves_uids(tmp_path, monkeypatch):
    conn = connect()
    _patch(monkeypatch, conn)
    rid = save_proposal(conn, "p1", "relation",
                        {"rel_type": "USES", "src_name": "Diffusion Policy", "src_type": "method",
                         "dst_name": "PPO", "dst_type": "method", "evidence": "e"}, 0.9)
    client = TestClient(app)
    client.post(f"/api/review/{rid}/decision", json={"action": "approve"})
    from app.knowledge.unified import ledger
    relation = next(r for r in ledger(conn) if r['kind'] == 'relation')
    assert (relation['payload']['rel_type'], relation['payload']['src_uid'], relation['payload']['dst_uid']) == ('USES', 'method:diffusion-policy', 'method:ppo')
    assert GRAPH == []


def test_reject_and_edit(tmp_path, monkeypatch):
    conn = connect()
    _patch(monkeypatch, conn)
    r1 = save_proposal(conn, "p1", "entity", {"type": "method", "name": "Bad", "evidence": "e"}, 0.9)
    r2 = save_proposal(conn, "p1", "entity", {"type": "method", "name": "PPO", "evidence": "e"}, 0.9)
    client = TestClient(app)
    client.post(f"/api/review/{r1}/decision", json={"action": "reject"})
    assert get_proposal(conn, r1)["status"] == "rejected"
    client.post(f"/api/review/{r2}/decision",
                json={"action": "edit", "payload": {"type": "concept", "name": "clip objective", "evidence": "e2"}})
    assert get_proposal(conn, r2)["status"] == "approved"
    from app.knowledge.unified import ledger, graph
    assert any(r['payload'].get('name') == 'clip objective' for r in ledger(conn))
    assert not any(n['label'] == 'Bad' for n in graph(conn)['nodes'])
    assert GRAPH == []


def test_invalid_rel_type_rejected_400(tmp_path, monkeypatch):
    conn = connect()
    _patch(monkeypatch, conn)
    rid = save_proposal(conn, "p1", "relation",
                        {"rel_type": "HACKED", "src_name": "a", "dst_name": "b", "evidence": "e"}, 0.9)
    client = TestClient(app)
    resp = client.post(f"/api/review/{rid}/decision", json={"action": "approve"})
    assert resp.status_code == 400
