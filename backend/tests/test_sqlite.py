from app.db.sqlite import connect, get_paper, upsert_paper


def _doc(**kw):
    base = {
        "uid": "2401.12345",
        "arxiv_id": "2401.12345",
        "title": "Test Paper",
        "abstract": "Abs",
        "authors": ["A", "B"],
        "year": 2024,
        "venue": None,
        "categories": ["cs.RO"],
        "published": "2024-01-01",
        "pdf_url": None,
        "code_url": None,
        "source": "arxiv",
    }
    return {**base, **kw}


def test_upsert_and_get(tmp_path):
    conn = connect(str(tmp_path / "t.db"))
    uid = upsert_paper(conn, _doc())
    assert uid == "2401.12345"
    row = get_paper(conn, "2401.12345")
    assert row["title"] == "Test Paper"
    assert row["authors"] == ["A", "B"]
    upsert_paper(conn, _doc(title="Test Paper v2"))
    rows = conn.execute("SELECT title FROM papers").fetchall()
    assert len(rows) == 1 and rows[0]["title"] == "Test Paper v2"


def test_connect_creates_tasks_table():
    conn = connect(":memory:")
    tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"papers", "tasks"} <= tables
