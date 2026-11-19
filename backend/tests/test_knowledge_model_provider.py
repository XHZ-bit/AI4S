"""Verify knowledge calls honour the selected provider and do not fall back."""

from contextlib import contextmanager
from types import SimpleNamespace

import httpx
import pytest

from app.knowledge import model


class Connection:
    def execute(self, *args):
        return None


@contextmanager
def connection(_project):
    yield Connection()


def test_personal_provider_is_used_and_pinned(monkeypatch):
    settings = SimpleNamespace(
        dashscope_api_key="platform-secret", tutor_default_api_key="", offline_mode=False, access_mode="local",
        knowledge_model_enabled=True, llm_model="platform-model",
        llm_api_base="https://platform.example/v1", research_model_max_input_chars=10000,
        llm_timeout_seconds=20, knowledge_hourly_request_limit=0,
    )
    monkeypatch.setattr(model, "get_settings", lambda: settings)
    monkeypatch.setattr(model.preferences, "read", lambda: {
        "provider": {"enabled": True, "encrypted_key": "ciphertext",
                     "model": "personal-model", "base_url": "https://personal.example/v1"}
    })
    monkeypatch.setattr(model.preferences, "provider", lambda: {
        "model": "personal-model", "base_url": "https://personal.example/v1",
        "api_key": "personal-secret", "address": "8.8.8.8", "host": "personal.example",
    })
    monkeypatch.setattr(model.store, "connection", connection)
    calls = []

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, url, **kwargs):
            calls.append((url, kwargs))
            return httpx.Response(200, json={"choices": [{"message": {"content": '{"ok": true}'}}]},
                                  request=httpx.Request("POST", url))

    monkeypatch.setattr(model.httpx, "Client", Client)
    assert model.available()
    assert model.structured("system", {}, model.Budget("project", "run"), "test") == {"ok": True}
    url, request = calls[0]
    assert url.host == "8.8.8.8"
    assert request["headers"]["Host"] == "personal.example"
    assert request["headers"]["Authorization"] == "Bearer personal-secret"
    assert request["extensions"]["sni_hostname"] == "personal.example"
    assert request["json"]["model"] == "personal-model"


def test_invalid_selected_provider_does_not_fall_back(monkeypatch):
    settings = SimpleNamespace(dashscope_api_key="platform-secret", tutor_default_api_key="", offline_mode=False,
                               access_mode="local", knowledge_model_enabled=True)
    monkeypatch.setattr(model, "get_settings", lambda: settings)
    monkeypatch.setattr(model.preferences, "read", lambda: {
        "provider": {"enabled": True, "encrypted_key": "ciphertext",
                     "model": "personal-model", "base_url": "https://personal.example/v1"}
    })
    def invalid():
        raise ValueError("模型密钥无法解密")
    monkeypatch.setattr(model.preferences, "provider", invalid)
    with pytest.raises(model.ModelUnavailable, match="模型密钥无法解密"):
        model.structured("system", {}, model.Budget("project", "run"), "test")
    settings.offline_mode = True
    assert not model.available()
