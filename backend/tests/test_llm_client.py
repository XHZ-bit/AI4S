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
    assert body["model"] == "qwen3.7-flash"


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
