from pathlib import Path

import httpx
import respx
from fastapi.testclient import TestClient

from app.collector.service import run_collect
from app.db.sqlite import connect, get_paper
from app.main import app
from app.models.paper import PaperDoc

FIXTURE = Path(__file__).parent / "fixtures" / "arxiv_atom.xml"


def test_run_collect_upserts_and_merges(tmp_path, monkeypatch):
    conn = connect()
    monkeypatch.setattr("app.collector.service._connect", lambda: connect())
    monkeypatch.setattr("app.collector.service.merge_paper", lambda p: merged.append(p["uid"]))
    merged = []
    # Task 9 将在 run_collect 中引入 backfill_citations；此行保证届时测试不发真实请求
    monkeypatch.setattr(
        "app.collector.service.backfill_citations", lambda conn, uids: 0, raising=False
    )

    @respx.mock
    def _run():
        respx.get("https://export.arxiv.org/api/query").mock(
            return_value=httpx.Response(200, text=FIXTURE.read_text())
        )
        return run_collect(keywords=["robot"], categories=["cs.RO"], start_year=2023, max_results=10)

    result = _run()
    assert result["collected"] == 2
    assert set(merged) == {"2401.12345", "2310.08882"}
    assert get_paper(conn, "2401.12345")["title"].startswith("Diffusion")
    row = conn.execute("SELECT status FROM tasks WHERE type='collect'").fetchone()
    assert row["status"] == "done"


def test_collect_api_end_to_end(tmp_path, monkeypatch):
    conn = connect()
    monkeypatch.setattr("app.collector.service._connect", lambda: connect())
    monkeypatch.setattr("app.collector.service.merge_paper", lambda p: None)
    monkeypatch.setattr(
        "app.collector.service.backfill_citations", lambda conn, uids: 0, raising=False
    )

    def _fake_fetch_topic(client, keywords, categories, start_year, max_results):
        return [
            PaperDoc(
                uid="2401.12345",
                arxiv_id="2401.12345",
                title="Diffusion Paper",
                abstract="abs",
                authors=["A"],
                year=2024,
                categories=["cs.RO"],
            )
        ]

    monkeypatch.setattr("app.collector.service.fetch_topic", _fake_fetch_topic)

    # Execute the real worker deterministically inside the mocked integration boundary.
    # Thread scheduling/capacity is covered separately; teardown must not unpatch a running worker.
    monkeypatch.setattr("app.jobs.submit_task", lambda fn, *args: fn(*args))
    client = TestClient(app)
    resp = client.post(
        "/api/collect",
        json={"keywords": ["robot"], "categories": ["cs.RO"], "start_year": 2023, "max_results": 10},
    )
    assert resp.status_code == 202
    task_id = resp.json()["task_id"]
    # fire-and-forget 后台线程：轮询等待任务完成（最多 5 秒）
    import time
    status = {}
    for _ in range(50):
        status = client.get(f"/api/collect/{task_id}").json()
        if status.get("status") == "done":
            break
        time.sleep(0.1)
    assert status["status"] == "done"
    assert get_paper(conn, "2401.12345")["title"] == "Diffusion Paper"
