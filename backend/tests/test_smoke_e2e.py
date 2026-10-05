"""端到端冒烟测试：collect API -> 后台采集 -> papers 查询 -> tasks 落库。

数据源（fetch_topic）用假数据 monkeypatch，不依赖 respx mock 窗口——
后台 worker 线程的生命周期超出 respx 装饰器的作用范围。
papers API 有独立的 _connect，需一并 patch 到同一个临时库，避免写入真实数据目录。
"""

import json
import time

from fastapi.testclient import TestClient

from app.db.sqlite import connect, get_paper
from app.main import app
from app.models.paper import PaperDoc


def _docs():
    return [
        PaperDoc(
            uid="2401.12345",
            arxiv_id="2401.12345",
            title="Diffusion Policy for Robot Manipulation",
            abstract="We propose a diffusion-based policy.",
            authors=["Cheng Chi", "Shuran Song"],
            year=2024,
            categories=["cs.RO", "cs.LG"],
        ),
        PaperDoc(
            uid="2310.08882",
            arxiv_id="2310.08882",
            title="DreamerV3",
            abstract="Mastering diverse domains.",
            authors=["Danijar Hafner"],
            year=2023,
            categories=["cs.LG"],
        ),
    ]


def test_smoke_collect_then_query(tmp_path, monkeypatch):
    conn = connect()
    monkeypatch.setattr("app.collector.service._connect", lambda: connect())
    monkeypatch.setattr("app.collector.service.backfill_citations", lambda c, u: 0)
    monkeypatch.setattr("app.collector.service.fetch_topic", lambda *a, **kw: _docs())
    # papers 路由走自己的 _connect/connect()，指向真实 data 目录，必须指向同一临时库
    monkeypatch.setattr("app.api.papers._connect", lambda: connect())

    saved = []
    import app.collector.service as svc

    monkeypatch.setattr(svc, "merge_paper", lambda p: saved.append(p["uid"]))

    # Execute the real worker deterministically inside the mocked integration boundary.
    # Thread scheduling/capacity is covered separately; teardown must not unpatch a running worker.
    monkeypatch.setattr("app.jobs.submit_task", lambda fn, *args: fn(*args))
    client = TestClient(app)
    resp = client.post(
        "/api/collect",
        json={
            "keywords": ["diffusion policy"],
            "categories": ["cs.RO"],
            "start_year": 2023,
            "max_results": 5,
        },
    )
    assert resp.status_code == 202
    task_id = resp.json()["task_id"]

    # fire-and-forget 后台线程：轮询等待任务完成（最多 5 秒）
    status = {}
    for _ in range(50):
        status = client.get(f"/api/collect/{task_id}").json()
        if status.get("status") == "done":
            break
        time.sleep(0.1)
    assert status["status"] == "done"

    listing = client.get("/api/papers").json()
    assert listing["total"] == 2
    assert set(saved) == {"2401.12345", "2310.08882"}
    detail = client.get("/api/papers/2401.12345").json()
    assert detail["year"] == 2024
    rows = conn.execute(
        "SELECT status, params_json FROM tasks WHERE type='collect'"
    ).fetchall()
    assert any(r["status"] == "done" for r in rows)
    assert json.loads(rows[0]["params_json"])["keywords"] == ["diffusion policy"]
    assert get_paper(conn, "2310.08882")["title"] == "DreamerV3"
