import httpx
import respx

from app.collector.citations import backfill_citations
from app.db.sqlite import connect, upsert_paper


def _paper(uid, arxiv_id=None):
    return {
        "uid": uid,
        "arxiv_id": arxiv_id,
        "title": uid,
        "abstract": "a",
        "authors": [],
        "year": 2024,
        "venue": None,
        "categories": [],
        "published": None,
        "pdf_url": None,
        "code_url": None,
        "source": "arxiv",
    }


def test_backfill_creates_edges(tmp_path, monkeypatch):
    conn = connect(str(tmp_path / "t.db"))
    upsert_paper(conn, _paper("2401.12345", "2401.12345"))
    upsert_paper(conn, _paper("2013.12345", "2013.12345"))
    upsert_paper(conn, _paper("upload-x"))  # 无 arxiv_id，应跳过

    edges = []
    monkeypatch.setattr("app.collector.citations.merge_cites_batch", lambda pairs: edges.extend(pairs))

    respx.get("https://api.semanticscholar.org/graph/v1/paper/arXiv:2401.12345/citations").mock(
        return_value=httpx.Response(
            200,
            json={"data": [{"citedPaper": {"externalIds": {"ArXiv": "2013.12345"}}}]},
        )
    )

    with respx.mock:
        added = backfill_citations(conn, ["2401.12345", "upload-x"])
    assert added == 1
    assert edges == [("2401.12345", "2013.12345")]


def test_backfill_survives_single_failure(tmp_path, monkeypatch):
    import app.collector.citations as cit

    conn = connect(str(tmp_path / "t.db"))
    upsert_paper(conn, _paper("a", "a"))
    upsert_paper(conn, _paper("b", "b"))
    monkeypatch.setattr(cit, "merge_cites_batch", lambda pairs: None)
    monkeypatch.setattr(cit, "fetch_citations", lambda client, uid: (_ for _ in ()).throw(RuntimeError("boom")) if uid == "a" else ["c"])

    added = cit.backfill_citations(conn, ["a", "b"])
    assert added == 1
