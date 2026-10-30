"""Identity and account APIs without a network, model service, or real user data."""

import importlib.util
import json
import sqlite3
from contextlib import closing
from contextvars import ContextVar
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app import accounts
from app.api import accounts as api
from app.config import Settings

PASSWORD = "correct horse battery staple"
NEW_PASSWORD = "a different secure passphrase"


@pytest.fixture
def identity(tmp_path, monkeypatch):
    settings = Settings(data_dir=str(tmp_path / "identity"), access_mode="multiuser",
                        max_users=20, session_secure_cookie=True, session_lifetime_hours=12,
                        registration_enabled=True, smtp_host="", auth_public_url="")
    monkeypatch.setattr(accounts, "get_settings", lambda: settings)
    monkeypatch.setattr(api, "get_settings", lambda: settings)
    accounts.initialize()
    return settings


@pytest.fixture
def client(identity, monkeypatch):
    # Scope the account router separately; real deployment tenancy and CSRF
    # middleware are verified in the managed-mode integration suite.
    user_context = ContextVar("test_account_user", default=None)
    monkeypatch.setattr(api, "_current_user", user_context.get)
    application = FastAPI()

    @application.middleware("http")
    async def identify(request: Request, call_next):
        token = user_context.set(accounts.authenticate(request.cookies.get(accounts.COOKIE_NAME)))
        try:
            return await call_next(request)
        finally:
            user_context.reset(token)

    application.include_router(api.router)
    return TestClient(application, base_url="https://testserver")


def _sign_in(client, username="administrator", password=PASSWORD):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def test_password_storage_uses_unique_scrypt_salts_and_no_plaintext(identity):
    first = accounts.create_user("alice", PASSWORD)
    second = accounts.create_user("bob", PASSWORD)
    assert len(first["id"]) == 32 and first["id"] != second["id"]
    assert first["role"] == "user" and not first["disabled"]
    with closing(sqlite3.connect(Path(identity.data_dir) / "identity.db")) as conn:
        rows = conn.execute("SELECT password_salt,password_hash FROM users ORDER BY username").fetchall()
    assert rows[0][0] != rows[1][0] and rows[0][1] != rows[1][1]
    assert rows[0][1] == accounts._password_hash(PASSWORD, rows[0][0])
    assert PASSWORD.encode() not in (Path(identity.data_dir) / "identity.db").read_bytes()
    assert "password" not in json.dumps(accounts.list_users())


def test_user_validation_casefold_duplicates_and_capacity(identity):
    with pytest.raises(accounts.AccountError, match="密码"):
        accounts.create_user("alice", "short")
    with pytest.raises(accounts.AccountError, match="用户名"):
        accounts.create_user("../alice", PASSWORD)
    with pytest.raises(accounts.AccountError, match="角色"):
        accounts.create_user("alice", PASSWORD, "owner")
    accounts.create_user("Alice", PASSWORD)
    with pytest.raises(accounts.AccountError, match="已存在"):
        accounts.create_user("alice", PASSWORD)
    identity.max_users = 1
    with pytest.raises(accounts.AccountError, match="上限"):
        accounts.create_user("bob", PASSWORD)
    assert len(accounts.list_users()) == 1


def test_sessions_are_hashed_expire_and_revoke_independently(identity, monkeypatch):
    user = accounts.create_user("alice", PASSWORD)
    monkeypatch.setattr(accounts.time, "time", lambda: 1000)
    token, authenticated = accounts.login(" ALICE ", PASSWORD, "127.0.0.1")
    other_token, _ = accounts.login("alice", PASSWORD, "127.0.0.1")
    assert authenticated["id"] == user["id"]
    assert accounts.authenticate(token) == authenticated
    assert accounts.verify_csrf(authenticated, authenticated["csrf_token"])
    assert not accounts.verify_csrf(authenticated, "invalid")
    assert not accounts.verify_csrf(authenticated, "非ASCII")
    assert not accounts.verify_csrf(authenticated, None)
    with closing(sqlite3.connect(Path(identity.data_dir) / "identity.db")) as conn:
        stored = conn.execute("SELECT token_hash,expires_at FROM sessions").fetchall()
    assert len(stored) == 2 and all(row[0] != token for row in stored)
    assert stored[0][1] == 1000 + 12 * 3600
    accounts.logout(token)
    assert accounts.authenticate(token) is None
    assert accounts.authenticate(other_token)
    monkeypatch.setattr(accounts.time, "time", lambda: 1000 + 12 * 3600)
    assert accounts.authenticate(other_token) is None
    assert accounts.authenticate(None) is None
    assert accounts.authenticate("x" * 300) is None


def test_failed_login_is_limited_across_reinitialization_and_recovers(identity, monkeypatch):
    accounts.create_user("alice", PASSWORD)
    clock = [1000]
    monkeypatch.setattr(accounts.time, "time", lambda: clock[0])
    for _ in range(5):
        with pytest.raises(accounts.AccountError) as exc:
            accounts.login("alice", "wrong", "127.0.0.1")
        assert exc.value.status_code == 401
    accounts.initialize()
    with pytest.raises(accounts.AccountError) as exc:
        accounts.login("alice", PASSWORD, "127.0.0.1")
    assert exc.value.status_code == 429
    # Another source address has an independent account-and-address bucket.
    assert accounts.login("alice", PASSWORD, "127.0.0.2")
    clock[0] += 901
    assert accounts.login("alice", PASSWORD, "127.0.0.1")
    with closing(sqlite3.connect(Path(identity.data_dir) / "identity.db")) as conn:
        assert conn.execute("SELECT COUNT(*) FROM login_attempts").fetchone()[0] == 0


def test_ip_limit_covers_rotating_unknown_usernames(identity):
    for index in range(30):
        with pytest.raises(accounts.AccountError) as exc:
            accounts.login(f"unknown{index}", "wrong", "shared-address")
        assert exc.value.status_code == 401
    with pytest.raises(accounts.AccountError) as exc:
        accounts.login("another", "wrong", "shared-address")
    assert exc.value.status_code == 429


def test_disable_revokes_sessions_and_cannot_disable_self_or_last_admin(identity):
    admin = accounts.create_user("administrator", PASSWORD, "admin")
    user = accounts.create_user("alice", PASSWORD)
    token, _ = accounts.login("alice", PASSWORD, "ip")
    assert accounts.is_active(user["id"])
    accounts.set_disabled(user["id"], True, actor_id=admin["id"])
    assert not accounts.is_active(user["id"]) and accounts.authenticate(token) is None
    with pytest.raises(accounts.AccountError) as exc:
        accounts.login("alice", PASSWORD, "ip")
    assert exc.value.status_code == 401
    accounts.set_disabled(user["id"], False, actor_id=admin["id"])
    assert accounts.is_active(user["id"])
    assert accounts.authenticate(token) is None
    with pytest.raises(accounts.AccountError, match="当前登录"):
        accounts.set_disabled(admin["id"], True, actor_id=admin["id"])
    with pytest.raises(accounts.AccountError, match="最后一个"):
        accounts.set_disabled(admin["id"], True)
    second_admin = accounts.create_user("second-admin", PASSWORD, "admin")
    accounts.set_disabled(admin["id"], True, actor_id=second_admin["id"])
    assert not accounts.is_active(admin["id"])
    assert not accounts.is_active("missing")


def test_password_change_and_machine_recovery_revoke_every_session(identity):
    user = accounts.create_user("alice", PASSWORD)
    tokens = [accounts.login("alice", PASSWORD, "ip")[0] for _ in range(2)]
    with pytest.raises(accounts.AccountError, match="当前密码"):
        accounts.change_password(user["id"], "wrong", NEW_PASSWORD)
    assert all(accounts.authenticate(token) for token in tokens)
    accounts.change_password(user["id"], PASSWORD, NEW_PASSWORD)
    assert all(accounts.authenticate(token) is None for token in tokens)
    with pytest.raises(accounts.AccountError):
        accounts.login("alice", PASSWORD, "ip")
    fresh, _ = accounts.login("alice", NEW_PASSWORD, "ip")
    accounts.reset_password(user["id"], PASSWORD)
    assert accounts.authenticate(fresh) is None
    assert accounts.login("alice", PASSWORD, "ip")


def test_api_session_cookie_logout_and_password_rotation(client):
    accounts.create_user("administrator", PASSWORD, "admin")
    assert client.get("/api/auth/session").json() == {"mode": "multiuser", "user": None,
                                                    "registration_enabled": True, "recovery_email_enabled": False}
    result = _sign_in(client)
    assert result.status_code == 200
    cookie = result.headers["set-cookie"]
    assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=strict" in cookie
    assert "Max-Age=43200" in cookie and result.headers["Cache-Control"] == "no-store"
    body = result.json()
    assert body["user"]["role"] == "admin" and body["csrf_token"]
    assert client.get("/api/auth/session").json() == body
    original_token = client.cookies.get(accounts.COOKIE_NAME)
    result = client.post("/api/auth/password", json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})
    assert result.status_code == 200 and result.json()["requires_login"]
    assert accounts.authenticate(original_token) is None
    assert client.get("/api/auth/session").json()["user"] is None
    assert _sign_in(client, password=NEW_PASSWORD).status_code == 200
    active_token = client.cookies.get(accounts.COOKIE_NAME)
    assert client.post("/api/auth/logout").status_code == 200
    assert accounts.authenticate(active_token) is None
    assert client.get("/api/auth/session").json()["user"] is None


def test_admin_user_endpoints_reject_anonymous_and_regular_users(client):
    admin = accounts.create_user("administrator", PASSWORD, "admin")
    user = accounts.create_user("alice", PASSWORD)
    request = {"username": "invited", "password": PASSWORD}
    assert client.get("/api/auth/users").status_code == 401
    assert _sign_in(client, "alice").status_code == 200
    assert client.get("/api/auth/users").status_code == 403
    assert client.post("/api/auth/users", json=request).status_code == 403
    assert client.patch(f"/api/auth/users/{admin['id']}", json={"disabled": True}).status_code == 403
    assert _sign_in(client).status_code == 200
    assert len(client.get("/api/auth/users").json()["items"]) == 2
    created = client.post("/api/auth/users", json=request)
    assert created.status_code == 201 and created.json()["role"] == "user"
    assert client.post("/api/auth/users", json=request).status_code == 409
    assert client.patch(f"/api/auth/users/{user['id']}", json={"disabled": True}).json()["disabled"]
    assert client.patch(f"/api/auth/users/{admin['id']}", json={"disabled": True}).status_code == 409
    assert client.patch("/api/auth/users/missing", json={"disabled": True}).status_code == 404


def test_local_mode_supports_optional_accounts_and_registration_can_be_disabled(client, identity):
    identity.access_mode = "local"
    assert client.get("/api/auth/session").json() == {"mode": "local", "user": None,
                                                    "registration_enabled": True, "recovery_email_enabled": False}
    assert _sign_in(client).status_code == 401
    assert client.get("/api/auth/users").status_code == 401
    created = client.post("/api/auth/register", json={"username": "alice", "password": PASSWORD})
    assert created.status_code == 201 and created.json()["user"]["role"] == "user"
    assert client.get("/api/auth/users").status_code == 403
    identity.registration_enabled = False
    assert not client.get("/api/auth/session").json()["registration_enabled"]
    assert client.post("/api/auth/register", json={"username": "bob", "password": PASSWORD}).status_code == 403


def test_cli_uses_getpass_and_never_prints_credentials(identity, monkeypatch, capsys):
    path = Path(__file__).parents[1] / "scripts" / "manage_users.py"
    spec = importlib.util.spec_from_file_location("manage_users_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    prompts = []

    def getpass(prompt):
        prompts.append(prompt)
        return PASSWORD

    monkeypatch.setattr(module.getpass, "getpass", getpass)
    assert module.main(["create", "--username", "administrator"]) == 0
    captured = capsys.readouterr()
    assert len(prompts) == 2 and PASSWORD not in captured.out + captured.err
    assert json.loads(captured.out)["role"] == "admin"
    assert module.main(["list"]) == 0
    assert "password_hash" not in capsys.readouterr().out
    assert module.main(["reset-password", "--username", "administrator"]) == 0
    assert json.loads(capsys.readouterr().out)["sessions_revoked"]
    answers = iter([PASSWORD, "different"])
    monkeypatch.setattr(module.getpass, "getpass", lambda prompt: next(answers))
    assert module.main(["create", "--username", "mismatch"]) == 1
    assert len(accounts.list_users()) == 1
