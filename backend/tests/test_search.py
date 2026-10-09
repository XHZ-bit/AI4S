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


def test_search_v2_uses_local_passage_and_explains_hit_without_model(monkeypatch):
    conn = connect(":memory:")
    conn.execute(
        "INSERT INTO papers(uid,title,abstract,authors_json,year,categories_json,source) "
        "VALUES('p-title','Diffusion Policy','robot control','[]',2024,'[]','fixture'),"
        "('p-passage','Second paper','different topic','[]',2023,'[]','fixture')"
    )
    conn.execute("INSERT INTO documents(id,paper_uid,content_hash,coverage) VALUES('d1','p-passage','hash','fulltext')")
    conn.execute("INSERT INTO passages(id,document_id,heading,text,ordinal) VALUES('s1','d1','Methods','diffusion policy appears here',0)")
    monkeypatch.setattr("app.api.search._connect", lambda: conn)
    result = TestClient(app).get("/api/search/v2", params={"q": "diffusion policy"})
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["mode"] == "keyword"
    assert [item["uid"] for item in body["items"]] == ["p-title", "p-passage"]
    assert body["items"][1]["hit_reason"].startswith("原文片段匹配")


def test_search_v2_fuses_available_semantic_and_lexical_results(monkeypatch):
    conn = connect(":memory:")
    conn.execute(
        "INSERT INTO papers(uid,title,abstract,authors_json,categories_json,source) "
        "VALUES('p1','Diffusion learning','model paper','[]','[]','fixture'),"
        "('p2','Robot control','policy paper','[]','[]','fixture')"
    )
    monkeypatch.setattr("app.search.service.embed", lambda texts: [
        [1.0 if "diffusion" in text.casefold() else 0.0] for text in texts
    ])
    index_paper(conn, "p1", "diffusion learning")
    index_paper(conn, "p2", "robot control")
    monkeypatch.setattr("app.api.search._connect", lambda: conn)
    body = TestClient(app).get("/api/search/v2", params={"q": "diffusion"}).json()
    assert body["mode"] == "hybrid"
    assert body["items"][0]["uid"] == "p1"
    assert "标题匹配 + 语义相近" == body["items"][0]["hit_reason"]
