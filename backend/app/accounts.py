"""Local identity store for personal accounts and controlled shared deployments."""

import hashlib
import logging
import re
import secrets
import smtplib
import sqlite3
import ssl
import time
from contextlib import closing
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from uuid import uuid4

from app.config import get_settings

COOKIE_NAME = "atlas_session"
_WINDOW_SECONDS = 15 * 60
_PAIR_LIMIT = 5
_IP_LIMIT = 30
_USERNAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{2,63}")
_EMAIL = re.compile(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,63}")
logger = logging.getLogger(__name__)
_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
 id TEXT PRIMARY KEY, username TEXT NOT NULL, username_key TEXT NOT NULL UNIQUE,
 password_salt BLOB NOT NULL, password_hash BLOB NOT NULL,
 role TEXT NOT NULL CHECK(role IN ('admin','user')),
 disabled INTEGER NOT NULL DEFAULT 0 CHECK(disabled IN (0,1)),
 created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS sessions (
 token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
 csrf_token TEXT NOT NULL, created_at REAL NOT NULL, expires_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_expiry ON sessions(expires_at);
CREATE TABLE IF NOT EXISTS login_attempts (
 bucket TEXT PRIMARY KEY, window_start REAL NOT NULL, failures INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS account_attempts (
 bucket TEXT PRIMARY KEY, expires_at REAL NOT NULL, attempts INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS recovery_codes (
 user_id TEXT PRIMARY KEY REFERENCES users(id), code_hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS account_tokens (
 token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
 purpose TEXT NOT NULL CHECK(purpose IN ('verify-email','reset-password')),
 email TEXT NOT NULL, created_at REAL NOT NULL, expires_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS idx_account_tokens_user ON account_tokens(user_id,purpose);
"""


class AccountError(ValueError):
    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.status_code = status_code


def _connect():
    directory = Path(get_settings().data_dir)
    directory.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(directory / "identity.db", timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=10000")
        conn.executescript(_SCHEMA)
        # Serialize additive migrations so simultaneous requests can upgrade an
        # existing installation without racing ALTER TABLE or losing accounts.
        conn.execute("BEGIN IMMEDIATE")
        columns = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
        for name in ("email", "pending_email"):
            if name not in columns:
                conn.execute(f"ALTER TABLE users ADD COLUMN {name} TEXT")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email) WHERE email IS NOT NULL")
        conn.commit()
    except Exception:
        conn.close()
        raise
    return conn


def initialize():
    """Create the identity schema. No default account or password is installed."""
    with closing(_connect()):
        pass


def _password_hash(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**15, r=8, p=3,
                          maxmem=64 * 1024 * 1024, dklen=32)


def _validate_password(password: str):
    if not isinstance(password, str) or not 12 <= len(password) <= 1024:
        raise AccountError("密码须为 12 至 1024 个字符")


def _public_user(row):
    return {"id": row["id"], "username": row["username"], "role": row["role"],
            "disabled": bool(row["disabled"]), "created_at": row["created_at"],
            "email": row["email"], "pending_email": row["pending_email"]}


def create_user(username: str, password: str, role: str = "user") -> dict:
    username = username.strip()
    if not _USERNAME.fullmatch(username):
        raise AccountError("用户名须为 3 至 64 位英文字母、数字、点、横线或下划线，并以字母或数字开头")
    if role not in {"admin", "user"}:
        raise AccountError("账号角色不合法")
    _validate_password(password)
    salt = secrets.token_bytes(16)
    password_hash = _password_hash(password, salt)
    with closing(_connect()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        if conn.execute("SELECT 1 FROM users WHERE username_key=?", (username.casefold(),)).fetchone():
            raise AccountError("用户名已存在", 409)
        if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] >= get_settings().max_users:
            raise AccountError("账号数量已达到当前部署上限", 409)
        user_id = uuid4().hex
        conn.execute("INSERT INTO users(id,username,username_key,password_salt,password_hash,role,disabled,created_at) VALUES(?,?,?,?,?,?,0,?)",
                     (user_id, username, username.casefold(), salt, password_hash, role, time.time()))
        conn.commit()
        return _public_user(conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone())


def list_users() -> list[dict]:
    with closing(_connect()) as conn:
        return [_public_user(row) for row in conn.execute("SELECT * FROM users ORDER BY created_at,id")]


def register(username: str, password: str, ip: str):
    with closing(_connect()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        _consume_limits(conn, ((f"register:{ip}", 10, 3600),), "注册尝试过多，请一小时后重试")
        conn.commit()
    return create_user(username, password, "user")


def is_active(user_id: str) -> bool:
    with closing(_connect()) as conn:
        row = conn.execute("SELECT disabled FROM users WHERE id=?", (user_id,)).fetchone()
        return bool(row and not row["disabled"])


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _buckets(username: str, ip: str):
    # Persistent, bounded-lifetime counters avoid growing per-process maps and
    # continue throttling password guesses after a service restart.
    pair = _token_hash(f"pair:{username.strip().casefold()}\0{ip}")
    address = _token_hash(f"ip:{ip}")
    return ((pair, _PAIR_LIMIT), (address, _IP_LIMIT))


def login(username: str, password: str, ip: str) -> tuple[str, dict]:
    """Return the opaque session token once; only its hash is stored on disk."""
    now = time.time()
    buckets = _buckets(username, ip)
    with closing(_connect()) as conn:
        # Serialize attempts through the small local account database, including
        # password verification, so parallel guesses cannot skip the counter.
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM login_attempts WHERE window_start<=?", (now - _WINDOW_SECONDS,))
        conn.execute("DELETE FROM sessions WHERE expires_at<=?", (now,))
        for bucket, limit in buckets:
            attempt = conn.execute("SELECT failures FROM login_attempts WHERE bucket=?", (bucket,)).fetchone()
            if attempt and attempt["failures"] >= limit:
                conn.commit()
                raise AccountError("登录尝试过多，请在 15 分钟后重试", 429)
        key = username.strip().casefold()
        row = conn.execute("SELECT * FROM users WHERE username_key=? OR email=?", (key, key)).fetchone()
        # Unknown and disabled accounts still perform the same password work.
        salt = row["password_salt"] if row else b"atlas-no-user-v1!"
        candidate = _password_hash(password, salt)
        valid = bool(row and secrets.compare_digest(candidate, row["password_hash"]) and not row["disabled"])
        if not valid:
            for bucket, _ in buckets:
                conn.execute("INSERT INTO login_attempts VALUES(?,?,1) ON CONFLICT(bucket) "
                             "DO UPDATE SET failures=failures+1", (bucket, now))
            conn.commit()
            raise AccountError("用户名或密码错误，或账号已停用", 401)
        conn.execute("DELETE FROM login_attempts WHERE bucket=?", (buckets[0][0],))
        token = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(32)
        conn.execute("INSERT INTO sessions VALUES(?,?,?,?,?)",
                     (_token_hash(token), row["id"], csrf_token, now,
                      now + get_settings().session_lifetime_hours * 3600))
        conn.commit()
        return token, {"id": row["id"], "username": row["username"],
                       "role": row["role"], "csrf_token": csrf_token,
                       "email": row["email"], "pending_email": row["pending_email"]}


def authenticate(token: str | None) -> dict | None:
    if not token or not isinstance(token, str) or len(token) > 256:
        return None
    now = time.time()
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT u.id,u.username,u.role,u.email,u.pending_email,s.csrf_token FROM sessions s JOIN users u ON u.id=s.user_id "
            "WHERE s.token_hash=? AND s.expires_at>? AND u.disabled=0", (_token_hash(token), now),
        ).fetchone()
        return dict(row) if row else None


def verify_csrf(user: dict | None, token: str | None) -> bool:
    expected = user.get("csrf_token") if user else None
    return bool(isinstance(expected, str) and isinstance(token, str) and token
                and secrets.compare_digest(expected.encode("utf-8"), token.encode("utf-8")))


def logout(token: str | None):
    if not token or not isinstance(token, str) or len(token) > 256:
        return
    with closing(_connect()) as conn:
        conn.execute("DELETE FROM sessions WHERE token_hash=?", (_token_hash(token),))
        conn.commit()


def set_disabled(user_id: str, disabled: bool, *, actor_id: str | None = None) -> dict:
    with closing(_connect()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if row is None:
            raise AccountError("账号不存在", 404)
        if disabled and user_id == actor_id:
            raise AccountError("不能停用当前登录的管理员账号", 409)
        if disabled and row["role"] == "admin" and not row["disabled"]:
            admins = conn.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND disabled=0").fetchone()[0]
            if admins <= 1:
                raise AccountError("不能停用最后一个可用的管理员账号", 409)
        conn.execute("UPDATE users SET disabled=? WHERE id=?", (int(disabled), user_id))
        if disabled:
            conn.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
            _clear_recovery(conn, user_id)
        conn.commit()
        return _public_user(conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone())


def change_password(user_id: str, current_password: str, new_password: str, *, ip: str = "local"):
    _validate_password(new_password)
    with closing(_connect()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        _verify_current_password(conn, user_id, current_password, ip)
        salt = secrets.token_bytes(16)
        conn.execute("UPDATE users SET password_salt=?,password_hash=? WHERE id=?",
                     (salt, _password_hash(new_password, salt), user_id))
        conn.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
        _clear_recovery(conn, user_id)
        conn.commit()


def reset_password(user_id: str, new_password: str):
    """Machine-operator recovery for the CLI; no unauthenticated HTTP endpoint."""
    _validate_password(new_password)
    salt = secrets.token_bytes(16)
    password_hash = _password_hash(new_password, salt)
    with closing(_connect()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        if not conn.execute("SELECT 1 FROM users WHERE id=?", (user_id,)).fetchone():
            raise AccountError("账号不存在", 404)
        conn.execute("UPDATE users SET password_salt=?,password_hash=? WHERE id=?", (salt, password_hash, user_id))
        conn.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
        _clear_recovery(conn, user_id)
        conn.commit()


def _consume_limits(conn, limits, message="操作过于频繁，请在 15 分钟后重试"):
    """Each action owns its expiry; login cleanup cannot reset other limits."""
    now = time.time()
    conn.execute("DELETE FROM account_attempts WHERE expires_at<=?", (now,))
    for key, limit, _window in limits:
        row = conn.execute("SELECT attempts FROM account_attempts WHERE bucket=?", (_token_hash(key),)).fetchone()
        if row and row[0] >= limit:
            raise AccountError(message, 429)
    for key, _limit, window in limits:
        conn.execute("INSERT INTO account_attempts VALUES(?,?,1) ON CONFLICT(bucket) DO UPDATE SET attempts=attempts+1",
                     (_token_hash(key), now + window))


def _clear_recovery(conn, user_id):
    conn.execute("DELETE FROM recovery_codes WHERE user_id=?", (user_id,))
    conn.execute("DELETE FROM account_tokens WHERE user_id=?", (user_id,))
    conn.execute("UPDATE users SET pending_email=NULL WHERE id=?", (user_id,))


def _verify_current_password(conn, user_id, password, ip):
    _consume_limits(conn, ((f"reauth:{user_id}:{ip}", 5, 900), (f"reauth-ip:{ip}", 30, 900)))
    # Persist unsuccessful attempts too, before credential verification.
    conn.commit()
    conn.execute("BEGIN IMMEDIATE")
    row = conn.execute("SELECT * FROM users WHERE id=? AND disabled=0", (user_id,)).fetchone()
    if row is None:
        raise AccountError("账号不存在或已停用", 403)
    if not secrets.compare_digest(_password_hash(password, row["password_salt"]), row["password_hash"]):
        raise AccountError("当前密码不正确", 400)
    return row


def normalize_email(email: str) -> str:
    value = email.strip().casefold()
    if len(value) > 254 or not _EMAIL.fullmatch(value) or ".." in value or value.startswith(".") or ".@" in value:
        raise AccountError("请输入有效的邮箱地址")
    return value


def email_recovery_enabled() -> bool:
    settings = get_settings()
    host = getattr(settings, "smtp_host", "").strip()
    sender = getattr(settings, "smtp_from_email", "").strip()
    base = getattr(settings, "auth_public_url", "").strip()
    if not host or not sender or not base or getattr(settings, "offline_mode", False):
        return False
    try:
        normalize_email(sender)
        url = urlsplit(base)
        loopback = {"localhost", "127.0.0.1", "::1"}
        safe_url = bool(url.hostname and not url.username and not url.password and not url.query and not url.fragment
                        and (url.scheme == "https" or (url.scheme == "http" and url.hostname in loopback)))
        security = getattr(settings, "smtp_security", "starttls")
        safe_transport = security in {"starttls", "ssl"} or (security == "plain" and host in loopback)
        return safe_url and safe_transport and not any(char.isspace() for char in base)
    except (ValueError, AccountError):
        return False


def _require_email_service():
    if not email_recovery_enabled():
        raise AccountError("此站点尚未启用邮件服务，请使用恢复码或联系管理员", 503)


def _new_email_token(conn, user_id, purpose, email, minutes):
    now = time.time()
    conn.execute("DELETE FROM account_tokens WHERE expires_at<=? OR (user_id=? AND purpose=?)", (now, user_id, purpose))
    token = secrets.token_urlsafe(32)
    conn.execute("INSERT INTO account_tokens VALUES(?,?,?,?,?,?)",
                 (_token_hash(token), user_id, purpose, email, now, now + minutes * 60))
    return token


def send_account_email(email: str, username: str, purpose: str, token: str) -> bool:
    """Never log addresses, SMTP credentials, or the one-time bearer token."""
    settings = get_settings()
    minutes = settings.password_reset_minutes if purpose == "reset-password" else 60
    action = "重设密码" if purpose == "reset-password" else "验证邮箱"
    link = settings.auth_public_url.strip().rstrip("/") + "/#" + urlencode({"auth": purpose, "token": token})
    mail = EmailMessage()
    mail["From"] = settings.smtp_from_email.strip()
    mail["To"] = email
    mail["Subject"] = f"PaperStride · {action}"
    mail.set_content(f"你好，{username}：\n\n请打开下面的链接{action}：\n{link}\n\n"
                     f"链接将在 {minutes} 分钟后失效，且只能使用一次。\n"
                     "如果你没有发起此操作，请忽略此邮件。请勿将链接转发给他人。\n\nPaperStride\n")
    try:
        _require_email_service()
        security = settings.smtp_security
        if security == "ssl":
            connection = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port,
                                          timeout=settings.smtp_timeout_seconds, context=ssl.create_default_context())
        else:
            connection = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout_seconds)
        with connection as smtp:
            smtp.ehlo()
            if security == "starttls":
                smtp.starttls(context=ssl.create_default_context())
                smtp.ehlo()
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(mail)
        return True
    except (OSError, smtplib.SMTPException, AccountError):
        logger.warning("Account email delivery failed; check SMTP configuration and service availability")
        with closing(_connect()) as conn:
            conn.execute("DELETE FROM account_tokens WHERE token_hash=?", (_token_hash(token),))
            conn.commit()
        return False


def bind_email(user_id: str, email: str, password: str, ip: str) -> bool:
    _require_email_service()
    email = normalize_email(email)
    with closing(_connect()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = _verify_current_password(conn, user_id, password, ip)
        owner = conn.execute("SELECT id FROM users WHERE email=? AND id<>?", (email, user_id)).fetchone()
        if owner:
            raise AccountError("此邮箱无法绑定，请使用其他邮箱", 409)
        if row["email"] == email:
            raise AccountError("此邮箱已验证，无需重复绑定", 409)
        conn.execute("UPDATE users SET pending_email=? WHERE id=?", (email, user_id))
        token = _new_email_token(conn, user_id, "verify-email", email, 60)
        conn.commit()
        username = row["username"]
    return send_account_email(email, username, "verify-email", token)


def verify_email(token: str, ip: str):
    with closing(_connect()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        _consume_limits(conn, ((f"verify-email:{ip}", 30, 900),))
        conn.commit()
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT t.user_id,t.email FROM account_tokens t JOIN users u ON u.id=t.user_id "
                           "WHERE t.token_hash=? AND t.purpose='verify-email' AND t.expires_at>? "
                           "AND u.disabled=0 AND u.pending_email=t.email", (_token_hash(token), time.time())).fetchone()
        if row is None:
            raise AccountError("验证链接无效或已过期，请在账号设置中重新发送", 400)
        owner = conn.execute("SELECT id FROM users WHERE email=? AND id<>?", (row["email"], row["user_id"])).fetchone()
        if owner:
            conn.execute("DELETE FROM account_tokens WHERE token_hash=?", (_token_hash(token),))
            conn.commit()
            raise AccountError("此邮箱无法绑定，请在账号设置中使用其他邮箱", 409)
        conn.execute("UPDATE users SET email=?,pending_email=NULL WHERE id=?", (row["email"], row["user_id"]))
        # A changed recovery address also invalidates links delivered to the old one.
        conn.execute("DELETE FROM account_tokens WHERE user_id=?", (row["user_id"],))
        conn.commit()


def prepare_password_reset(email: str, ip: str):
    """Return internal delivery details only; the API never exposes this value."""
    _require_email_service()
    email = normalize_email(email)
    with closing(_connect()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        _consume_limits(conn, ((f"forgot-email:{email}", 3, 900), (f"forgot-ip:{ip}", 20, 900)))
        row = conn.execute("SELECT id,username FROM users WHERE email=? AND disabled=0", (email,)).fetchone()
        delivery = None
        if row:
            token = _new_email_token(conn, row["id"], "reset-password", email, get_settings().password_reset_minutes)
            delivery = (email, row["username"], "reset-password", token)
        conn.commit()
        return delivery


def _replace_password(conn, user_id: str, password: str):
    salt = secrets.token_bytes(16)
    conn.execute("UPDATE users SET password_salt=?,password_hash=? WHERE id=?", (salt, _password_hash(password, salt), user_id))
    conn.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
    _clear_recovery(conn, user_id)


def reset_password_with_token(token: str, new_password: str, ip: str):
    _validate_password(new_password)
    with closing(_connect()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        _consume_limits(conn, ((f"reset-token:{ip}", 30, 900),))
        conn.commit()
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT t.user_id FROM account_tokens t JOIN users u ON u.id=t.user_id "
                           "WHERE t.token_hash=? AND t.purpose='reset-password' AND t.expires_at>? "
                           "AND u.disabled=0 AND u.email=t.email", (_token_hash(token), time.time())).fetchone()
        if row is None:
            raise AccountError("重置链接无效或已过期，请重新申请找回密码", 400)
        _replace_password(conn, row["user_id"], new_password)
        conn.commit()


def issue_recovery_code(user_id: str, password: str, ip: str):
    with closing(_connect()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        _verify_current_password(conn, user_id, password, ip)
        code = secrets.token_urlsafe(32)
        conn.execute("INSERT INTO recovery_codes VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET code_hash=excluded.code_hash",
                     (user_id, _token_hash(code)))
        conn.commit()
        return code


def recover_with_code(username: str, code: str, new_password: str, ip: str):
    _validate_password(new_password)
    with closing(_connect()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        _consume_limits(conn, ((f"recover:{username.strip().casefold()}:{ip}", 5, 900), (f"recover-ip:{ip}", 30, 900)),
                        "恢复尝试过多，请在 15 分钟后重试")
        conn.commit()
        conn.execute("BEGIN IMMEDIATE")
        key = username.strip().casefold()
        row = conn.execute("SELECT u.id,r.code_hash FROM users u JOIN recovery_codes r ON r.user_id=u.id "
                           "WHERE (u.username_key=? OR u.email=?) AND u.disabled=0", (key, key)).fetchone()
        expected = row["code_hash"] if row else "0" * 64
        valid = secrets.compare_digest(expected, _token_hash(code.strip()))
        if not row or not valid:
            raise AccountError("用户名或恢复码不正确，或账号已停用", 401)
        _replace_password(conn, row["id"], new_password)
        conn.commit()


def active_sessions(user_id: str, current_token: str):
    current = _token_hash(current_token)
    with closing(_connect()) as conn:
        return [{"id": row["token_hash"], "created_at": row["created_at"], "expires_at": row["expires_at"],
                 "current": row["token_hash"] == current} for row in conn.execute(
                     "SELECT token_hash,created_at,expires_at FROM sessions WHERE user_id=? AND expires_at>? ORDER BY created_at DESC",
                     (user_id, time.time()))]


def revoke_other_sessions(user_id: str, current_token: str):
    with closing(_connect()) as conn:
        conn.execute("DELETE FROM sessions WHERE user_id=? AND token_hash<>?", (user_id, _token_hash(current_token)))
        conn.commit()


def session_for_new_user(user_id: str):
    """Complete a successful registration without a second login throttle check."""
    with closing(_connect()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM users WHERE id=? AND disabled=0", (user_id,)).fetchone()
        if row is None:
            raise AccountError("账号不存在或已停用", 403)
        token = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(32)
        now = time.time()
        conn.execute("INSERT INTO sessions VALUES(?,?,?,?,?)", (_token_hash(token), user_id, csrf_token,
                     now, now + get_settings().session_lifetime_hours * 3600))
        conn.commit()
        return token, {"id": row["id"], "username": row["username"], "role": row["role"],
                       "email": row["email"], "pending_email": row["pending_email"], "csrf_token": csrf_token}
