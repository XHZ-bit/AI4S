from fastapi.testclient import TestClient

from app.db.sqlite import connect
from app.main import app
from app.models.roadmap import RoadmapResult

FAKE_RESULT = RoadmapResult(
    goal="测试目标",
    phases=[],
    innovations=[],
)


def test_generate_roadmap(monkeypatch):
    conn = connect(":memory:")
    monkeypatch.setattr("app.api.roadmap._connect", lambda: conn)
    monkeypatch.setattr("app.api.roadmap.generate_roadmap",
                        lambda profile, conn=None: RoadmapResult(id=1, goal=profile.goal, phases=[], innovations=[]))
    client = TestClient(app)
    resp = client.post("/api/roadmap/generate", json={"profile": {"goal": "测试目标"}})
    assert resp.status_code == 200
    body = resp.json()
    assert body["goal"] == "测试目标"
    assert body["id"] == 1


def test_generate_roadmap_reports_missing_dashscope_key(monkeypatch):
    conn = connect(":memory:")
    monkeypatch.setattr("app.api.roadmap._connect", lambda: conn)
    monkeypatch.setattr(
        "app.api.roadmap.generate_roadmap",
        lambda profile, conn=None: (_ for _ in ()).throw(
            RuntimeError("DASHSCOPE_API_KEY is not configured")
        ),
    )
    client = TestClient(app)
    resp = client.post("/api/roadmap/generate", json={"profile": {"goal": "测试目标"}})
    assert resp.status_code == 503
    assert resp.json()["detail"] == "DASHSCOPE_API_KEY is not configured"


def test_get_roadmap(monkeypatch):
    conn = connect(":memory:")
    from app.db.roadmaps import save_roadmap
    from app.models.roadmap import LearnerProfile
    rid = save_roadmap(conn, FAKE_RESULT, LearnerProfile(goal="测试目标"))
    monkeypatch.setattr("app.api.roadmap._connect", lambda: conn)
    client = TestClient(app)
    resp = client.get(f"/api/roadmap/{rid}")
    assert resp.status_code == 200
    assert resp.json()["goal"] == "测试目标"


def test_list_roadmaps(monkeypatch):
    conn = connect(":memory:")
    from app.db.roadmaps import save_roadmap
    from app.models.roadmap import LearnerProfile
    save_roadmap(conn, FAKE_RESULT, LearnerProfile(goal="g1"))
    monkeypatch.setattr("app.api.roadmap._connect", lambda: conn)
    client = TestClient(app)
    resp = client.get("/api/roadmap")
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 1


def test_update_progress(monkeypatch):
    from app.db.roadmaps import save_roadmap
    from app.models.roadmap import LearnerProfile, RoadmapItem, RoadmapPhase
    result = RoadmapResult(
        goal="g", phases=[RoadmapPhase(phase=1, title="p", weeks="w", items=[
            RoadmapItem(kind="paper", title="t", reason="r", evidence="e")])], innovations=[],
    )
    conn = connect(":memory:")
    rid = save_roadmap(conn, result, LearnerProfile(goal="g"))
    monkeypatch.setattr("app.api.roadmap._connect", lambda: conn)
    client = TestClient(app)
    resp = client.patch(f"/api/roadmap/{rid}/progress", json={"phase": 1, "item_index": 0, "done": True})
    assert resp.status_code == 200
    assert resp.json()["phases"][0]["items"][0]["done"] is True
