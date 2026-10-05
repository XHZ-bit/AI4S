"""Tests must never contact paid model services or mutate the user's local database."""

import pytest
import respx
import httpx
import ssl
import certifi


@pytest.fixture(scope="session")
def test_tls_context():
    # HTTP is mocked below; reuse a verified context instead of repeatedly loading
    # the Windows certificate store for every short-lived fake client.
    return ssl.create_default_context(cafile=certifi.where())


@pytest.fixture(autouse=True)
def isolated_services(tmp_path, monkeypatch, test_tls_context):
    from app.config import get_settings
    from app.db.sqlite import _initialized_paths

    original_init = httpx.Client.__init__

    def client_init(self, *args, **kwargs):
        if kwargs.get("verify", True) is True:
            kwargs["verify"] = test_tls_context
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.Client, "__init__", client_init)
    get_settings.cache_clear()
    # Never read a developer's .env, even when tests override selected fields.
    from app.config import Settings
    original_settings_init = Settings.__init__

    def settings_init(self, **kwargs):
        kwargs["_env_file"] = None
        original_settings_init(self, **kwargs)

    monkeypatch.setattr(Settings, "__init__", settings_init)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("RESEARCH_MODEL_ENABLED", "false")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "")
    monkeypatch.setenv("GROBID_BASE_URL", "http://127.0.0.1:1")
    _initialized_paths.clear()
    with respx.mock(assert_all_called=False, assert_all_mocked=True) as mock_router:
        mock_router.get("http://127.0.0.1:1/api/isalive").mock(
            side_effect=httpx.ConnectError("offline")
        )
        yield mock_router
    get_settings.cache_clear()
