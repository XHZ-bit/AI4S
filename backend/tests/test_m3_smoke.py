from fastapi.testclient import TestClient

from app.db.proposals import list_proposals
from app.db.sqlite import connect, upsert_paper
from app.main import app

LLM_JSON = """
{"entities": [
   {"type": "method", "name": "PPO", "confidence": 0.95, "evidence": "uses PPO"},
   {"type": "concept", "name": "clip objective", "confidence": 0.7, "evidence": "clip loss"}
 ],
 "relations": [
   {"rel_type": "USES", "src_name": "Diffusion Policy", "dst_name": "PPO", "confidence": 0.9, "evidence": "trained with PPO"},
   {"rel_type": "PREREQUISITE_OF", "src_name": "TD", "dst_name": "Actor-Critic", "confidence": 0.6, "evidence": "requires TD"}
 ]}
"""


def test_m3_smoke_full_chain(tmp_path, monkeypatch):
    conn = connect()
    upsert_paper(conn, {"uid": "2401.12345", "arxiv_id": "2401.12345", "title": "Diffusion Policy",
                         "abstract": "We propose...", "authors": [], "year": 2024, "venue": None,
                         "categories": [], "published": None, "pdf_url": None, "code_url": None, "source": "arxiv"})
    monkeypatch.setattr("app.api.extract._connect", lambda: connect())
    monkeypatch.setattr("app.pipeline.evidence.chat", lambda msgs, json_mode=False: LLM_JSON)
    monkeypatch.setattr("app.pipeline.extract.embed", lambda texts: [[1.0, 0.0] for _ in texts])
    monkeypatch.setattr("app.graphsvc.entities.merge_entity", lambda t, u, n: None)
    monkeypatch.setattr("app.graphsvc.entities.merge_relation", lambda r, s, d: None)

    client = TestClient(app)
    resp = client.post("/api/papers/2401.12345/extract")
    assert resp.status_code == 200
    body = resp.json()
    assert body["entities"] == 2 and body["relations"] == 2
    # 第二次执行：PPO 已在 entity_vectors（同向量 1.0 相似度=1.0 -> auto_merge 转 approved）
    resp2 = client.post("/api/papers/2401.12345/extract")
    assert resp2.status_code == 200
    statuses = {p["status"] for p in list_proposals(conn)}
    assert "auto_merged" not in statuses
