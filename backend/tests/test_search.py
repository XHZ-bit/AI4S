from fastapi.testclient import TestClient

from app.db.sqlite import connect
from app.main import app
from app.search.service import index_paper, semantic_search


def test_index_and_search(monkeypatch):
    conn = connect(":memory:")
    # mock embed：含 "reinforcement" 的文本 -> [1.0]，否则 [0.0]
    monkeypatch.setattr(
        "app.search.service.embed",
        lambda texts: [[1.0 if "reinforcement" in t else 0.0] for t in texts],
    )
    index_paper(conn, "p1", "reinforcement learning policy gradient")
    index_paper(conn, "p2", "diffusion model for image generation")
    results = semantic_search(conn, "reinforcement learning", limit=2)
    assert results[0]["uid"] == "p1"
    assert results[0]["score"] > results[1]["score"]


def test_search_api(monkeypatch):
    conn = connect(":memory:")
    monkeypatch.setattr("app.search.service.embed", lambda texts: [[1.0] for _ in texts])
    monkeypatch.setattr("app.api.search._connect", lambda: conn)
    index_paper(conn, "p1", "test")
    client = TestClient(app)
    resp = client.get("/api/search", params={"q": "test"}).json()
    assert resp["items"][0]["uid"] == "p1"
