"""Account recovery contract and security boundaries; SMTP and data are isolated."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import accounts
from app import access
from app.api import accounts as api
from app.config import Settings

PASSWORD = "long original account password"
NEW_PASSWORD = "a new long account passphrase"


@pytest.fixture
def mail_service(tmp_path, monkeypatch):
    settings = Settings(data_dir=str(tmp_path / "identity"), access_mode="multiuser", registration_enabled=True,
                        smtp_host="localhost", smtp_port=1025, smtp_security="plain", smtp_from_email="noreply@example.com",
                        auth_public_url="https://research.example.com", smtp_username="", smtp_password="", offline_mode=False)
    for module in (accounts, api, access):
        monkeypatch.setattr(module, "get_settings", lambda: settings)
    inbox = []
    operations = []

    class SMTP:
        fail = False

        def __init__(self, *args, **kwargs):
            operations.append(("connect", args, kwargs))
            if self.fail:
                raise OSError("synthetic delivery outage")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def ehlo(self):
            operations.append(("ehlo",))

        def starttls(self, **kwargs):
            operations.append(("starttls",))

        def login(self, username, password):
            operations.append(("login", username))

        def send_message(self, message):
            inbox.append(message)

    monkeypatch.setattr(accounts.smtplib, "SMTP", SMTP)
    monkeypatch.setattr(accounts.smtplib, "SMTP_SSL", SMTP)
    app = FastAPI()
    app.include_router(api.router)
    app.add_middleware(access.AccountBoundary)
    return settings, inbox, SMTP, operations, app


@pytest.fixture
def client(mail_service):
    with TestClient(mail_service[4], base_url="https://testserver") as client:
        yield client


def register(client, email="alice@example.com", username="alice"):
    response = client.post("/api/auth/register", json={"username": username, "password": PASSWORD, "email": email})
    assert response.status_code == 201, response.text
    client.headers["X-Atlas-CSRF"] = response.json()["csrf_token"]
    return response.json()


def token_from(mail):
    link = next(line for line in mail.get_content().splitlines() if line.startswith("https://"))
    parsed = urlsplit(link)
    assert parsed.netloc == "research.example.com" and not parsed.query
    return parse_qs(parsed.fragment)["token"][0]


def verify(client, mail_service):
    token = token_from(mail_service[1][-1])
    response = client.post("/api/auth/verify-email", json={"token": token})
    assert response.status_code == 200, response.text
    return token


def test_registration_verification_email_login_and_private_hashed_tokens(client, mail_service):
    body = register(client, " Alice@Example.com ")
    assert body["recovery_email_enabled"]
    assert body["user"]["pending_email"] == "alice@example.com" and body["user"]["email"] is None
    inbox = mail_service[1]
    assert len(inbox) == 1 and inbox[0]["To"] == "alice@example.com"
    token = token_from(inbox[0])
    assert token not in str(body)
    with closing(accounts._connect()) as conn:
        stored = conn.execute("SELECT token_hash FROM account_tokens").fetchone()[0]
        assert stored == accounts._token_hash(token) and stored != token
    # Pending email cannot be used for login or password recovery.
    assert client.post("/api/auth/login", json={"username": "alice@example.com", "password": PASSWORD}).status_code == 401
    missing = client.post("/api/auth/forgot-password", json={"email": "missing@example.com"})
    pending = client.post("/api/auth/forgot-password", json={"email": "alice@example.com"})
    assert missing.json() == pending.json() and len(inbox) == 1
    verify(client, mail_service)
    assert client.post("/api/auth/verify-email", json={"token": token}).status_code == 400
    session = client.get("/api/auth/session").json()
    assert session["user"]["email"] == "alice@example.com" and session["user"]["pending_email"] is None
    login = client.post("/api/auth/login", json={"username": "ALICE@EXAMPLE.COM", "password": PASSWORD})
    assert login.status_code == 200 and login.json()["user"]["id"] == body["user"]["id"]


def test_reset_is_single_use_revokes_all_sessions_and_recovery_codes(client, mail_service):
    register(client)
    verify(client, mail_service)
    code = client.post("/api/auth/recovery-code", json={"password": PASSWORD}).json()["code"]
    original = client.cookies.get(accounts.COOKIE_NAME)
    another, _ = accounts.login("alice", PASSWORD, "other-address")
    with TestClient(mail_service[4], base_url="https://testserver") as anonymous:
        unknown = anonymous.post("/api/auth/forgot-password", json={"email": "unknown@example.com"})
        known = anonymous.post("/api/auth/forgot-password", json={"email": "alice@example.com"})
        assert known.status_code == 200 and known.json() == unknown.json()
        token = token_from(mail_service[1][-1])
        assert token not in known.text
        reset = anonymous.post("/api/auth/reset-password", json={"token": token, "new_password": NEW_PASSWORD})
        assert reset.status_code == 200 and reset.json()["requires_login"]
        assert "Secure" in reset.headers["set-cookie"] and "HttpOnly" in reset.headers["set-cookie"]
        assert accounts.authenticate(original) is None and accounts.authenticate(another) is None
        assert client.get("/api/auth/session").json()["session_expired"] is True
        assert anonymous.post("/api/auth/reset-password", json={"token": token, "new_password": PASSWORD}).status_code == 400
        assert anonymous.post("/api/auth/recover", json={"username": "alice", "code": code, "new_password": PASSWORD}).status_code == 401
        assert anonymous.post("/api/auth/login", json={"username": "alice", "password": PASSWORD}).status_code == 401
        assert anonymous.post("/api/auth/login", json={"username": "alice@example.com", "password": NEW_PASSWORD}).status_code == 200


def test_links_expire_and_new_request_replaces_previous_link(client, mail_service, monkeypatch):
    register(client)
    verify(client, mail_service)
    assert client.post("/api/auth/forgot-password", json={"email": "alice@example.com"}).status_code == 200
    first = token_from(mail_service[1][-1])
    assert client.post("/api/auth/forgot-password", json={"email": "alice@example.com"}).status_code == 200
    second = token_from(mail_service[1][-1])
    assert client.post("/api/auth/reset-password", json={"token": first, "new_password": NEW_PASSWORD}).status_code == 400
    now = accounts.time.time()
    monkeypatch.setattr(accounts.time, "time", lambda: now + 1801)
    assert client.post("/api/auth/reset-password", json={"token": second, "new_password": NEW_PASSWORD}).status_code == 400
    assert accounts.login("alice", PASSWORD, "other-address")


def test_email_replacement_needs_password_and_csrf_and_keeps_old_until_verified(client, mail_service):
    register(client)
    verify(client, mail_service)
    req = {"email": "new@example.com", "password": PASSWORD}
    assert client.post("/api/auth/email", json=req, headers={"X-Atlas-CSRF": "bad"}).status_code == 403
    assert client.post("/api/auth/email", json={**req, "password": "wrong"}).status_code == 400
    assert client.post("/api/auth/email", json=req).status_code == 200
    user = client.get("/api/auth/session").json()["user"]
    assert user["email"] == "alice@example.com" and user["pending_email"] == "new@example.com"
    token = token_from(mail_service[1][-1])
    assert client.post("/api/auth/verify-email", json={"token": token}, headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.post("/api/auth/verify-email", json={"token": token}).status_code == 200
    assert client.get("/api/auth/session").json()["user"]["email"] == "new@example.com"
    assert client.post("/api/auth/login", json={"username": "alice@example.com", "password": PASSWORD}).status_code == 401


def test_pending_emails_do_not_reserve_another_users_address(client, mail_service):
    register(client)
    first_token = token_from(mail_service[1][-1])
    register(client, username="second")
    second_token = token_from(mail_service[1][-1])
    assert client.post("/api/auth/verify-email", json={"token": second_token}).status_code == 200
    assert client.post("/api/auth/verify-email", json={"token": first_token}).status_code == 409
    assert client.get("/api/auth/session").json()["user"]["email"] == "alice@example.com"


def test_smtp_outage_does_not_strand_registration_or_expose_account_existence(client, mail_service, caplog):
    mail_service[2].fail = True
    body = register(client)
    assert "暂未发出" in body["message"] and body["user"]
    assert not mail_service[1]
    with closing(accounts._connect()) as conn:
        assert conn.execute("SELECT COUNT(*) FROM account_tokens").fetchone()[0] == 0
    assert client.post("/api/auth/email", json={"email": "alice@example.com", "password": PASSWORD}).status_code == 503
    mail_service[2].fail = False
    assert client.post("/api/auth/email", json={"email": "alice@example.com", "password": PASSWORD}).status_code == 200
    verify(client, mail_service)
    mail_service[2].fail = True
    existing = client.post("/api/auth/forgot-password", json={"email": "alice@example.com"})
    missing = client.post("/api/auth/forgot-password", json={"email": "missing@example.com"})
    assert existing.status_code == 200 and existing.json() == missing.json()
    assert "alice@example.com" not in caplog.text and PASSWORD not in caplog.text


def test_capability_requires_safe_complete_mail_configuration(client, mail_service):
    settings = mail_service[0]
    assert client.get("/api/auth/session").json()["recovery_email_enabled"]
    settings.smtp_host = "smtp.example.com"
    assert not client.get("/api/auth/session").json()["recovery_email_enabled"]  # no plaintext to public host
    settings.smtp_security = "starttls"
    assert accounts.email_recovery_enabled()
    settings.auth_public_url = "http://research.example.com"
    assert not accounts.email_recovery_enabled()
    settings.auth_public_url = "https://research.example.com/?redirect=evil"
    assert not accounts.email_recovery_enabled()
    settings.auth_public_url = "https://research.example.com"
    settings.smtp_host = ""
    assert client.post("/api/auth/forgot-password", json={"email": "alice@example.com"}).status_code == 503
    assert client.post("/api/auth/register", json={"username": "alice", "password": PASSWORD, "email": "alice@example.com"}).status_code == 422
    assert not accounts.list_users()
    settings.smtp_host = "localhost"
    settings.offline_mode = True
    assert not accounts.email_recovery_enabled()


def test_starttls_precedes_auth_and_mail_url_does_not_trust_request_host(client, mail_service):
    mail_service[0].smtp_security = "starttls"
    mail_service[0].smtp_username = "mail-account"
    mail_service[0].smtp_password = "mock-credential"
    register(client)
    actions = [entry[0] for entry in mail_service[3]]
    assert actions.index("starttls") < actions.index("login")
    assert "https://research.example.com/#auth=verify-email" in mail_service[1][-1].get_content()
    assert "testserver" not in mail_service[1][-1].get_content()


def test_forgot_password_rate_limit_applies_equally_to_unknown_addresses(client):
    for _ in range(3):
        assert client.post("/api/auth/forgot-password", json={"email": "unknown@example.com"}).status_code == 200
    assert client.post("/api/auth/forgot-password", json={"email": "UNKNOWN@example.com"}).status_code == 429


def test_registration_limit_survives_login_cleanup(mail_service, monkeypatch):
    clock = [10_000]
    monkeypatch.setattr(accounts.time, "time", lambda: clock[0])
    for _ in range(10):
        with pytest.raises(accounts.AccountError) as error:
            accounts.register("!invalid", PASSWORD, "ip")
        assert error.value.status_code == 422
    clock[0] += 901
    with pytest.raises(accounts.AccountError):
        accounts.login("unknown", PASSWORD, "ip")
    with pytest.raises(accounts.AccountError) as error:
        accounts.register("valid", PASSWORD, "ip")
    assert error.value.status_code == 429
    clock[0] += 2700
    assert accounts.register("valid", PASSWORD, "ip")


def test_password_change_invalidates_every_recovery_method(client, mail_service):
    register(client)
    verify(client, mail_service)
    code = client.post("/api/auth/recovery-code", json={"password": PASSWORD}).json()["code"]
    client.post("/api/auth/forgot-password", json={"email": "alice@example.com"})
    token = token_from(mail_service[1][-1])
    assert client.post("/api/auth/password", json={"current_password": PASSWORD, "new_password": NEW_PASSWORD}).status_code == 200
    assert client.post("/api/auth/reset-password", json={"token": token, "new_password": PASSWORD}).status_code == 400
    assert client.post("/api/auth/recover", json={"username": "alice", "code": code, "new_password": PASSWORD}).status_code == 401


def test_simultaneous_reset_consumes_token_once(client, mail_service):
    register(client)
    verify(client, mail_service)
    client.post("/api/auth/forgot-password", json={"email": "alice@example.com"})
    token = token_from(mail_service[1][-1])

    def reset():
        try:
            accounts.reset_password_with_token(token, NEW_PASSWORD, "ip")
            return 200
        except accounts.AccountError as exc:
            return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(lambda _index: reset(), range(2))) == [200, 400]


def test_expired_cookie_can_be_cleared_without_csrf(client):
    client.cookies.set(accounts.COOKIE_NAME, "expired-cookie")
    response = client.post("/api/auth/logout")
    assert response.status_code == 200 and "Max-Age=0" in response.headers["set-cookie"]


@pytest.mark.parametrize("email", ["not-an-email", "alice@example.com\r\nBcc: victim@example.com", ".alice@example.com", "alice..name@example.com"])
def test_invalid_email_is_rejected_without_creating_an_account(client, email):
    response = client.post("/api/auth/register", json={"username": "alice", "password": PASSWORD, "email": email})
    assert response.status_code == 422 and not accounts.list_users()


def test_additive_migration_preserves_existing_accounts_and_recovery_codes(mail_service):
    import sqlite3
    from pathlib import Path

    directory = Path(mail_service[0].data_dir)
    directory.mkdir(parents=True)
    salt = b"legacy-salt-12345"
    with closing(sqlite3.connect(directory / "identity.db")) as conn:
        conn.executescript(accounts._SCHEMA)
        conn.execute("INSERT INTO users VALUES(?,?,?,?,?,?,?,?)", ("legacy-id", "legacy", "legacy", salt,
                     accounts._password_hash(PASSWORD, salt), "user", 0, 1000))
        conn.execute("INSERT INTO recovery_codes VALUES(?,?)", ("legacy-id", accounts._token_hash("legacy-code")))
        conn.commit()
    accounts.initialize()
    accounts.initialize()
    token, user = accounts.login("legacy", PASSWORD, "ip")
    assert user["id"] == "legacy-id" and user["email"] is None and accounts.authenticate(token)
    accounts.recover_with_code("legacy", "legacy-code", NEW_PASSWORD, "ip")
    assert accounts.authenticate(token) is None
    assert accounts.login("legacy", NEW_PASSWORD, "ip")


def test_local_stale_session_is_explicit_and_does_not_open_local_data(client, mail_service):
    mail_service[0].access_mode = "local"
    client.cookies.set(accounts.COOKIE_NAME, "stale-cookie", domain="testserver.local", path="/")
    response = client.get("/api/auth/session")
    assert response.status_code == 200
    assert response.json()["mode"] == "local" and response.json()["user"] is None
    assert response.json()["session_expired"] is True
    assert "set-cookie" not in response.headers
    assert client.get("/api/private-workspace").status_code == 401
    assert client.post("/api/auth/logout").status_code == 200
    assert "session_expired" not in client.get("/api/auth/session").json()
    assert client.get("/api/private-workspace").status_code == 404
