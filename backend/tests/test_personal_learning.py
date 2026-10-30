import json
from contextlib import closing

import httpx
import pymupdf
from fastapi.testclient import TestClient

from app.main import app
from app.config import get_settings
from app import preferences


def signed(client, name):
    result = client.post("/api/auth/register", json={"username": name, "password": "test-password-123!"})
    assert result.status_code == 201, result.text
    return {"X-Atlas-CSRF": result.json()["csrf_token"]}


def draft(client):
    value = client.get("/api/preferences").json()
    for key in ("avatar_url", "default_model"):
        value.pop(key, None)
    value["provider"].pop("has_key", None)
    return value


def test_registration_scopes_preferences_graph_and_csrf():
    with TestClient(app) as first, TestClient(app) as second:
        first_headers = signed(first, "alice")
        _second_headers = signed(second, "bob")
        assert first.get("/api/auth/session").json()["user"]["role"] == "user"
        value = draft(first)
        value["profile"]["display_name"] = "Alice"
        assert first.put("/api/preferences", json=value).status_code == 403
        assert first.put("/api/preferences", json=value, headers=first_headers).status_code == 200
        assert second.get("/api/preferences").json()["profile"]["display_name"] == ""
        assert first.put("/api/preferences", json=value, headers=first_headers).status_code == 409
        assert first.get("/api/auth/users").status_code == 403
        assert first.get("/api/graph/overview").json()["nodes"] == []
        assert first.post("/api/auth/logout", headers=first_headers).status_code == 200
        assert first.get("/api/preferences").json()["profile"]["display_name"] == ""


def test_key_encryption_endpoint_and_provider_transport(monkeypatch, isolated_services):
    monkeypatch.setattr(preferences.socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("8.8.8.8", 443))])
    with TestClient(app) as client:
        headers = signed(client, "model-user")
        value = draft(client)
        value["provider"] = {"enabled": True, "base_url": "https://model.example/v1", "model": "personal-model", "api_key": "secret-personal-key"}
        response = client.put("/api/preferences", json=value, headers=headers)
        assert response.status_code == 200, response.text
        assert "secret-personal-key" not in response.text and "encrypted_key" not in response.text
        assert response.json()["provider"]["has_key"]
        from pathlib import Path
        stored = next(Path(get_settings().data_dir).glob("users/*/preferences.json")).read_text("utf-8")
        assert "secret-personal-key" not in stored
        route = isolated_services.post("https://8.8.8.8/v1/chat/completions").mock(return_value=httpx.Response(200, json={"choices": [{"message": {"content": "连接成功"}}]}))
        response = client.post("/api/preferences/test-model", headers=headers)
        assert response.status_code == 200
        assert route.calls[0].request.headers["authorization"] == "Bearer secret-personal-key"
        assert route.calls[0].request.headers["host"] == "model.example"
        assert route.calls[0].request.extensions["sni_hostname"] == "model.example"
        assert json.loads(route.calls[0].request.content)["model"] == "personal-model"
        value = draft(client)
        value["provider"]["base_url"] = "https://other.example/v1"
        assert client.put("/api/preferences", json=value, headers=headers).status_code == 422
        value["provider"] = {"enabled": False, "base_url": "", "model": "", "clear_key": True}
        result = client.put("/api/preferences", json=value, headers=headers).json()
        assert not result["provider"]["has_key"]
    monkeypatch.setattr(preferences.socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("127.0.0.1", 443))])
    import pytest
    with pytest.raises(ValueError):
        preferences.validate_endpoint("https://localhost/v1")


def test_lessons_grade_and_disabled_features_do_not_call_model(monkeypatch):
    def fail(*a, **k):
        raise AssertionError("disabled feature called model")
    monkeypatch.setattr("app.api.tutoring.make_plan", fail)
    with TestClient(app) as client:
        items = client.get("/api/tutor/lessons").json()["items"]
        assert {item['id'] for item in items} >= {'probability','dp-1','dp-2','dp-3','dp-4','dp-5'}
        assert "answer" not in items[0]["quiz"][0]
        result = client.post("/api/tutor/lessons/probability/quiz", json={"question_index": 0, "answer": 0}).json()
        assert not result["correct"] and "0.8" in result["explanation"]
        assert client.post("/api/tutor/lessons/probability/quiz", json={"question_index": 0, "answer": 1}).json()["correct"]
        value = draft(client)
        value["features"] = {key: False for key in value["features"]}
        assert client.put("/api/preferences", json=value).status_code == 200
        assert client.get("/api/tutor/lessons").json()["items"] == []
        assert client.post("/api/tutor/sessions", json={"question": "什么是期望？"}).status_code == 409
        assert client.post("/api/tutor/lessons/probability/quiz", json={"question_index": 0, "answer": 1}).status_code == 409
        assert client.post("/api/learning/papers/any/guide").status_code == 409


def test_tutor_default_qwen_and_answer_private(monkeypatch, isolated_services):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "preset-test-key")
    get_settings.cache_clear()
    plan = {"title": "理解期望", "goal": "分清平均与最可能", "prerequisites": [], "steps": [{"question": "什么是加权平均？", "explanation": "让每个值按概率参与平均。", "example": "0 和 1 的分布", "check": "期望一定能取到吗？"}], "terms": [], "quiz": [{"question": "期望必须是可能取值吗？", "options": ["是", "否"], "answer": 1, "explanation": "不必，公平骰子的期望是 3.5。"}]}
    route = isolated_services.post(get_settings().llm_api_base + "/chat/completions").mock(return_value=httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(plan, ensure_ascii=False)}}]}))
    with TestClient(app) as client:
        response = client.post("/api/tutor/sessions", json={"question": "期望是什么意思？"})
        assert response.status_code == 201, response.text
        result = response.json()
        assert "answer" not in result["plan"]["quiz"][0]
        payload = json.loads(route.calls[0].request.content)
        assert payload["model"] == get_settings().llm_model
        usage = client.get("/api/tutor/dashboard").json()["usage"]
        assert usage[0]["status"] == "completed"
        assert usage[0]["input_tokens"] is None
        assert usage[0]["seconds"] >= 0
        assert client.get(f"/api/tutor/sessions/{result['id']}").status_code == 200
        graded = client.post(f"/api/tutor/sessions/{result['id']}/quiz", json={"question_index": 0, "answer": 1})
        assert graded.json()["correct"]


def test_avatar_decodes_to_png_and_isolates():
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 10, 10), False)
    raw = pix.tobytes("png")
    with TestClient(app) as first, TestClient(app) as second:
        headers = signed(first, "avatar-owner")
        signed(second, "other-owner")
        assert first.post("/api/preferences/avatar", files={"file": ("avatar.svg", b"<svg onload='x'/>", "image/svg+xml")}, headers=headers).status_code == 422
        response = first.post("/api/preferences/avatar", files={"file": ("test.png", raw, "image/png")}, headers=headers)
        assert response.status_code == 200, response.text
        assert first.get("/api/preferences/avatar").content.startswith(b"\x89PNG")
        assert second.get("/api/preferences/avatar").status_code == 404


def test_personal_library_is_not_legacy_workspace():
    from app.db.sqlite import connect
    with closing(connect()) as conn:
        conn.execute("INSERT INTO papers(uid,title) VALUES('private-legacy','Local legacy paper')")
        conn.commit()
    with TestClient(app) as client:
        assert client.get("/api/learning/papers/private-legacy").status_code == 200
        signed(client, "new-space")
        assert client.get("/api/learning/papers/private-legacy").status_code == 404


def test_learning_dashboard_scopes_and_lazy_generation(monkeypatch):
    calls = []
    def plan(question, source, profile, features, history):
        calls.append((source, profile, features))
        return {"title": "测试", "goal": "学习", "steps": [{"question": "为什么", "explanation": "说明"}], "quiz": [], "terms": [], "prerequisites": [], "exercise": None}, "fixture"
    monkeypatch.setattr("app.api.tutoring.make_plan", plan)
    with TestClient(app) as client:
        features = draft(client)["features"]
        features["foundations"] = False
        assert client.post("/api/tutor/scopes", json={"name": "研究课题", "features": features}).status_code == 200
        client.post("/api/tutor/lessons/probability/quiz", json={"question_index": 0, "answer": 0})
        response = client.post("/api/tutor/sessions", json={"question": "解释期望", "scope": "研究课题", "phase": "explain"})
        assert response.status_code == 201, response.text
        assert not calls[-1][2]["coding"] and not calls[-1][2]["quizzes"] and not calls[-1][2]["foundations"]
        assert calls[-1][1]["knowledge_profile"][0]["state"] == "建议复习"
        data = client.get("/api/tutor/dashboard").json()
        assert data["knowledge"][0]["checked"] == 1
        assert data["scopes"][0]["name"] == "研究课题"
        assert client.post("/api/tutor/sessions", json={"question": "解释期望", "scope": "不存在"}).status_code == 404


def test_saved_tutor_source_and_practice(monkeypatch):
    from app.db.sqlite import connect
    from app.tutoring import store
    with closing(connect()) as conn:
        store(conn)
        conn.execute("INSERT INTO papers(uid,title,abstract) VALUES('source-test','Source paper','Original abstract')")
        conn.commit()
    from app.learning_catalog import LESSONS
    def plan(*args):
        return {"title": "例子", "goal": "练习", "steps": [{"question": "问题", "explanation": "解释"}], "quiz": [], "terms": [], "prerequisites": [], "exercise": LESSONS[0]["exercise"]}, "fixture"
    monkeypatch.setattr("app.api.tutoring.make_plan", plan)
    with TestClient(app) as client:
        first = client.post("/api/tutor/sessions", json={"question": "解释这篇论文", "paper_uid": "source-test"}).json()
        saved = client.get("/api/tutor/sessions/" + first["id"]).json()
        assert saved["source"]["paper_uid"] == "source-test"
        assert len(saved["source"]["snapshot_sha256"]) == 64
        follow = client.post("/api/tutor/sessions", json={"question": "请继续解释", "session_id": first["id"]}).json()
        assert follow["source"]["abstract"] == "Original abstract"
        assert client.post("/api/tutor/sessions/" + first["id"] + "/practice", json={"exercise_id": "expectation", "code": "pass", "passed": False}).status_code == 200
        assert client.post("/api/tutor/sessions/" + first["id"] + "/practice", json={"exercise_id": "wrong", "code": "pass", "passed": False}).status_code == 404


def test_tutor_invalid_model_format_is_recoverable(monkeypatch, isolated_services):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "preset-test-key")
    get_settings.cache_clear()
    route = isolated_services.post(get_settings().llm_api_base + "/chat/completions").mock(return_value=httpx.Response(200, json={"choices": [{"message": {"content": "invalid json"}}]}))
    with TestClient(app) as client:
        response = client.post("/api/tutor/sessions", json={"question": "解释期望", "phase": "explain"})
        assert response.status_code == 422
        assert "invalid json" not in response.text
        assert route.call_count == 1
        assert client.get("/api/tutor/sessions").json()["items"] == []
