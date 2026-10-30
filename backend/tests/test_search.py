from contextlib import closing
import sqlite3

from fastapi.testclient import TestClient
import pytest

from app.db.search_index import available
from app.db.sqlite import connect
from app.main import app
from app.search.service import index_paper, lexical_search, semantic_search


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


def test_local_text_index_backfills_and_tracks_edits(tmp_path):
    path = str(tmp_path / "old.sqlite3")
    conn = connect(path)
    if not available(conn):
        pytest.skip("SQLite build has no trigram FTS5")
    conn.execute("INSERT INTO papers(uid,title,abstract) VALUES('p1','Synthetic Atlas','initial abstract')")
    conn.execute("INSERT INTO documents(id,paper_uid,content_hash,coverage) VALUES('d1','p1','h','fulltext')")
    conn.execute("INSERT INTO passages(id,document_id,heading,text,ordinal) "
                 "VALUES('s1','d1','Section','unique passage marker',0)")
    conn.execute("INSERT INTO passages(id,document_id,heading,text,ordinal) "
                 "VALUES('s2','d1','Later section','another passage marker',1)")
    conn.commit()
    assert lexical_search(conn, "Synthetic")[0]["uid"] == "p1"
    indexed = lexical_search(conn, "marker")
    from app.search import service
    original = service.search_index_available
    try:
        service.search_index_available = lambda _conn: False
        assert indexed == lexical_search(conn, "marker")
    finally:
        service.search_index_available = original
    assert indexed[0]["hit_reason"].startswith("原文片段匹配")
    conn.execute("UPDATE papers SET title='New title' WHERE uid='p1'")
    conn.execute("UPDATE passages SET text='changed passage token' WHERE id='s1'")
    conn.commit()
    assert lexical_search(conn, "Synthetic") == []
    assert lexical_search(conn, "marker")[0]["snippet"].startswith("another")
    assert lexical_search(conn, "changed")[0]["uid"] == "p1"
    # Safe, repeatable migration of an existing database does not duplicate rows.
    from app.db.search_index import init_search_index
    assert init_search_index(conn)
    assert conn.execute("SELECT COUNT(*) FROM passage_search_fts").fetchone()[0] == 2
    conn.close()


def _evidence_corpus(conn):
    conn.execute("INSERT INTO papers(uid,title,abstract) VALUES"
                 "('title-hit','Calibration variance study','Collected abstract'),"
                 "('passage-hit','Independent conditions','No metadata match')")
    for uid in ("title-hit", "passage-hit"):
        conn.execute("INSERT INTO documents(id,paper_uid,content_hash,coverage,created_at) VALUES(?,?,?,'fulltext',?)",
                     (f"old-{uid}", uid, f"original-{uid}", "2026-01-01"))
        conn.execute("INSERT INTO documents(id,paper_uid,content_hash,coverage,created_at) VALUES(?,?,?,'fulltext',?)",
                     (f"new-{uid}", uid, f"later-{uid}", "2026-02-01"))
        conn.execute("INSERT INTO passages(id,document_id,heading,text,page,ordinal) VALUES(?,?,?,?,?,?)",
                     (f"weak-{uid}", f"new-{uid}", "Background", "calibration " + "unrelated detail " * 100, 1, 0))
        conn.execute("INSERT INTO passages(id,document_id,heading,text,page,ordinal) VALUES(?,?,?,?,?,?)",
                     (f"strong-{uid}", f"old-{uid}", "Measured setting",
                      "Calibration variance is measured under a fixed split. Calibration variance changes with sample size.", 4, 3))
    conn.commit()


@pytest.mark.parametrize("force_scan", [False, True])
def test_best_source_passage_wins_over_newer_first_passage_and_title_hit_still_has_evidence(monkeypatch, force_scan):
    with closing(connect(":memory:")) as conn:
        if not force_scan and not available(conn):
            pytest.skip("SQLite build has no trigram FTS5")
        _evidence_corpus(conn)
        if force_scan:
            monkeypatch.setattr("app.search.service.search_index_available", lambda _: False)
        items = lexical_search(conn, "calibration variance")
        assert [item["uid"] for item in items] == ["title-hit", "passage-hit"]
        for item in items:
            assert item["passage_id"] == f"strong-{item['uid']}"
            assert item["document_id"] == f"old-{item['uid']}"
            assert item["document_version"] == f"sha256:original-{item['uid']}"
            assert item["page"] == 4
            assert "Calibration variance" in item["quote"]
            assert item["quote"] == item["snippet"]
            source = conn.execute("SELECT text FROM passages WHERE id=?", (item["passage_id"],)).fetchone()[0]
            assert item["quote"] in source
        assert items[0]["hit_reason"] == "标题匹配"


def test_short_chinese_query_uses_scan_and_unknown_page_remains_null(monkeypatch):
    conn = connect(":memory:")
    conn.execute("INSERT INTO papers(uid,title) VALUES('cn','工业图像检测')")
    conn.execute("INSERT INTO documents(id,paper_uid,content_hash,coverage) VALUES('cn-doc','cn','cn-hash','fulltext')")
    conn.execute("INSERT INTO passages(id,document_id,heading,text,ordinal) "
                 "VALUES('cn-text','cn-doc','摘要','这里记录图像处理的条件。',0)")
    # A short term cannot be a trigram MATCH query, even when FTS is available.
    conn.set_authorizer(lambda action, first, second, database, source:
                        sqlite3.SQLITE_DENY if first in ("paper_search_fts", "passage_search_fts") else sqlite3.SQLITE_OK)
    items = lexical_search(conn, "图像")
    assert items[0]["passage_id"] == "cn-text" and items[0]["page"] is None
    monkeypatch.setattr("app.api.search._connect", lambda: conn)
    response = TestClient(app).get("/api/search/v2", params={"q": "图像"})
    assert response.status_code == 200
    assert response.json()["items"][0]["page"] is None
    conn.close()


def test_v2_rrf_preserves_source_fields_and_does_not_invent_evidence_for_metadata(monkeypatch):
    conn = connect(":memory:")
    _evidence_corpus(conn)
    conn.execute("INSERT INTO papers(uid,title) VALUES('no-source','Calibration variance catalogue')")
    def semantic_matches(*args, **kwargs):
        return [{"uid": "title-hit", "score": 1.0}]

    conn.execute("INSERT INTO paper_embeddings(paper_uid,embedding) VALUES('title-hit',X'00')")
    monkeypatch.setattr("app.api.search.semantic_search", semantic_matches)
    monkeypatch.setattr("app.api.search._connect", lambda: conn)
    body = TestClient(app).get("/api/search/v2", params={"q": "calibration variance"}).json()
    assert body["mode"] == "hybrid"
    first = body["items"][0]
    assert first["uid"] == "title-hit" and first["passage_id"] == "strong-title-hit"
    assert first["score"] == pytest.approx(3 / 61)
    assert first["hit_reason"] == "标题匹配 + 语义相近"
    missing = next(item for item in body["items"] if item["uid"] == "no-source")
    assert "quote" not in missing and "passage_id" not in missing and "document_version" not in missing


def test_source_quote_preserves_long_unicode_text_and_omits_heading_only_hits(monkeypatch):
    conn = connect(":memory:")
    conn.execute("INSERT INTO papers(uid,title) VALUES('unicode','Unrelated title'),('heading','Heading example')")
    conn.execute("INSERT INTO documents(id,paper_uid,content_hash,coverage) VALUES"
                 "('unicode-doc','unicode','version','fulltext'),('heading-doc','heading','other','fulltext')")
    text = "ß" * 400 + " targetneedle in the original passage. " + "tail " * 100
    conn.execute("INSERT INTO passages(id,document_id,heading,text,ordinal) VALUES(?,?,?,?,0)",
                 ("unicode-text", "unicode-doc", "Source", text))
    conn.execute("INSERT INTO passages(id,document_id,heading,text,ordinal) VALUES"
                 "('heading-text','heading-doc','targetneedle','There is no matching text.',0)")
    monkeypatch.setattr("app.search.service.search_index_available", lambda _: False)
    items = lexical_search(conn, "targetneedle")
    assert [item["uid"] for item in items] == ["unicode"]
    assert "targetneedle" in items[0]["quote"] and len(items[0]["quote"]) <= 280
    assert items[0]["quote"] in text
    conn.close()


@pytest.mark.parametrize("force_scan", [False, True])
def test_passage_only_papers_use_source_relevance_before_uid(monkeypatch, force_scan):
    with closing(connect(":memory:")) as conn:
        if not force_scan and not available(conn):
            pytest.skip("SQLite build has no trigram FTS5")
        conn.execute("INSERT INTO papers(uid,title) VALUES('a-weak','Background notes'),('z-strong','Condition record')")
        for uid, text in (("a-weak", "calibration " + "unrelated note " * 100),
                          ("z-strong", "Calibration variance is measured. Calibration variance has a fixed setting.")):
            conn.execute("INSERT INTO documents(id,paper_uid,content_hash,coverage) VALUES(?,?,?,'fulltext')", (uid, uid, uid))
            conn.execute("INSERT INTO passages(id,document_id,heading,text,ordinal) VALUES(?,?,'Source',?,0)", (uid, uid, text))
        if force_scan:
            monkeypatch.setattr("app.search.service.search_index_available", lambda _: False)
        assert [item["uid"] for item in lexical_search(conn, "calibration variance")] == ["z-strong", "a-weak"]
