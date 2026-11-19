import httpx
import respx

from app.llm.client import chat, embed

BASE = "https://fake-llm/v1"


@respx.mock
def test_chat_json_mode_and_retry(monkeypatch):
    monkeypatch.setattr("app.llm.client._base", lambda: BASE)
    monkeypatch.setattr("app.llm.client._api_key", lambda: "sk-test")
    monkeypatch.setattr("app.llm.client._RETRY_SLEEP", 0)
    route = respx.post(f"{BASE}/chat/completions")
    route.side_effect = [
        httpx.Response(500),
        httpx.Response(200, json={"choices": [{"message": {"content": '{"ok": true}'}}]}),
    ]
    out = chat([{"role": "user", "content": "hi"}], json_mode=True)
    assert out == '{"ok": true}'
    import json
    body = json.loads(route.calls.last.request.content)
    assert body["response_format"] == {"type": "json_object"}
    assert body["model"] == "qwen3.8-flash"


@respx.mock
def test_embed_returns_vectors_in_order(monkeypatch):
    monkeypatch.setattr("app.llm.client._base", lambda: BASE)
    monkeypatch.setattr("app.llm.client._api_key", lambda: "sk-test")
    respx.post(f"{BASE}/embeddings").mock(
        return_value=httpx.Response(
            200,
            json={"data": [{"index": 0, "embedding": [0.1, 0.2]}, {"index": 1, "embedding": [0.3, 0.4]}]},
        )
    )
    vecs = embed(["ppo", "proximal policy optimization"])
    assert vecs == [[0.1, 0.2], [0.3, 0.4]]


@respx.mock
def test_chat_raises_after_retries(monkeypatch):
    monkeypatch.setattr("app.llm.client._base", lambda: BASE)
    monkeypatch.setattr("app.llm.client._api_key", lambda: "sk-test")
    monkeypatch.setattr("app.llm.client._RETRY_SLEEP", 0)
    respx.post(f"{BASE}/chat/completions").mock(return_value=httpx.Response(500))
    import pytest
    with pytest.raises(httpx.HTTPError):
        chat([{"role": "user", "content": "hi"}])


@respx.mock
def test_chat_uses_personal_provider_with_pinned_address(monkeypatch):
    from app import preferences
    monkeypatch.setattr(preferences, "provider", lambda: {
        "api_key": "personal-key", "base_url": "https://personal.example/v1",
        "model": "personal-model", "address": "8.8.8.8", "host": "personal.example",
    })
    route = respx.post("https://8.8.8.8/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={"choices": [{"message": {"content": "hello"}}]})
    )
    assert chat([{"role": "user", "content": "hi"}]) == "hello"
    request = route.calls[0].request
    assert request.headers["authorization"] == "Bearer personal-key"
    assert request.headers["host"] == "personal.example"
    assert request.extensions["sni_hostname"] == "personal.example"
    import json
    assert json.loads(request.content)["model"] == "personal-model"


@respx.mock
def test_default_provider_embedding_uses_personal_key(monkeypatch):
    from app import preferences
    from app.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(preferences, "read", lambda: {"provider": {
        "enabled": True, "base_url": settings.llm_api_base, "embedding_model": ""
    }})
    monkeypatch.setattr(preferences, "provider", lambda: {
        "api_key": "personal-key", "base_url": settings.llm_api_base,
        "model": "chat-model", "address": "8.8.8.8", "host": "personal.example"
    })
    path = httpx.URL(settings.llm_api_base.rstrip("/") + "/embeddings").path
    route = respx.post("https://8.8.8.8" + path).mock(
        return_value=httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.1, 0.2]}]})
    )
    assert embed(["test"]) == [[0.1, 0.2]]
    request = route.calls[0].request
    assert request.headers["authorization"] == "Bearer personal-key"
    import json
    assert json.loads(request.content)["model"] == settings.llm_embed_model


def test_other_provider_requires_explicit_embedding_model(monkeypatch):
    from app import preferences
    from app.llm.client import embedding_identity
    import pytest
    selected = {"enabled": True, "base_url": "https://other.example/v1", "embedding_model": ""}
    monkeypatch.setattr(preferences, "read", lambda: {"provider": selected})
    with pytest.raises(RuntimeError, match="向量模型"):
        embedding_identity()
    selected["embedding_model"] = "custom-embed"
    assert embedding_identity() == ("https://other.example/v1", "custom-embed")
