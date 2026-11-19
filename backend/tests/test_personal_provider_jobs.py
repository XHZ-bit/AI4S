import json

from app import preferences
from app.collector.service import run_collect
from app.db.sqlite import connect, upsert_paper
from app.jobs import _slots, run
from app.llm.client import configured
from app.models.paper import PaperDoc


def personal_provider(monkeypatch):
    monkeypatch.setattr(preferences, "read", lambda: {"provider": {
        "enabled": True,
        "base_url": "https://personal.example/v1",
        "model": "model",
        "encrypted_key": "encrypted",
    }})


def test_extract_job_accepts_personal_provider_without_platform_key(monkeypatch):
    personal_provider(monkeypatch)
    assert configured()
    conn = connect()
    upsert_paper(conn, PaperDoc(uid="paper-1", title="Test paper", year=2024).model_dump())
    task_id = conn.execute(
        "INSERT INTO tasks(type,params_json,status) VALUES(?,?,?)",
        ("extract", json.dumps({"uid": "paper-1"}), "queued"),
    ).lastrowid
    conn.commit()
    calls = []
    monkeypatch.setattr("app.pipeline.evidence.extract_document",
                        lambda _conn, paper: calls.append(paper["uid"]) or {"uid": paper["uid"]})
    assert _slots.acquire(blocking=False)
    run(task_id)
    row = conn.execute("SELECT status FROM tasks WHERE id=?", (task_id,)).fetchone()
    assert row["status"] == "done"
    assert calls == ["paper-1"]
    conn.close()


def test_collect_indexes_with_selected_personal_provider(monkeypatch):
    personal_provider(monkeypatch)
    monkeypatch.setattr("app.collector.service.fetch_topic", lambda *args: [
        PaperDoc(uid="paper-1", title="Test paper", year=2024, abstract="Example")])
    monkeypatch.setattr("app.collector.service.merge_paper", lambda *_args: None)
    calls = []
    monkeypatch.setattr("app.collector.service.index_papers",
                        lambda _conn, items: calls.extend(items))
    result = run_collect(keywords=["test"], categories=[], start_year=2024, max_results=1)
    assert result["collected"] == 1
    assert calls == [("paper-1", "Test paper\nExample")]


def test_configured_respects_offline_and_missing_personal_key(monkeypatch):
    from app.config import get_settings
    personal_provider(monkeypatch)
    assert configured()
    monkeypatch.setenv("OFFLINE_MODE", "true")
    get_settings.cache_clear()
    assert not configured()
    monkeypatch.setenv("OFFLINE_MODE", "false")
    get_settings.cache_clear()
    monkeypatch.setattr(preferences, "read", lambda: {"provider": {"enabled": True}})
    assert not configured()


def test_multiuser_configured_requires_active_account(monkeypatch):
    from app.config import get_settings
    from app.tenancy import current_user

    personal_provider(monkeypatch)
    monkeypatch.setenv("ACCESS_MODE", "multiuser")
    get_settings.cache_clear()
    assert current_user.get() is None
    assert not configured()
