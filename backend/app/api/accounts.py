"""Cookie sessions, registration, verified email recovery, and account controls."""

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response
import os
from pydantic import BaseModel, Field

from app import accounts
from app.config import get_settings

router = APIRouter(prefix="/api/auth", tags=["accounts"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=1024)


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=12, max_length=1024)
    email: str | None = Field(default=None, max_length=254)


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=12, max_length=1024)
    role: str = "user"


class DisableRequest(BaseModel):
    disabled: bool


class PasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=12, max_length=1024)


class RecoveryIssue(BaseModel):
    password: str = Field(min_length=1, max_length=1024)


class RecoveryReset(BaseModel):
    username: str = Field(min_length=1, max_length=254)
    code: str = Field(min_length=1, max_length=160)
    new_password: str = Field(min_length=12, max_length=1024)


class EmailRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)


class BindEmailRequest(EmailRequest):
    password: str = Field(min_length=1, max_length=1024)


class TokenRequest(BaseModel):
    token: str = Field(min_length=1, max_length=160)


class ResetPasswordRequest(TokenRequest):
    new_password: str = Field(min_length=12, max_length=1024)


def _mode():
    return get_settings().access_mode


def _current_user():
    from app.tenancy import current_user
    return current_user.get()


def _require_user(*, admin=False):
    user = _current_user()
    if not user:
        raise HTTPException(401, "请先登录")
    if admin and user["role"] != "admin":
        raise HTTPException(403, "仅管理员可管理账号")
    return user


def _session(user):
    result = {"mode": _mode(), "user": None, "require_login": get_settings().require_login, "runtime_id": get_settings().runtime_id, "pid": os.getpid(), "registration_enabled": get_settings().registration_enabled,
              "recovery_email_enabled": accounts.email_recovery_enabled()}
    if user:
        result["user"] = {key: user.get(key) for key in ("id", "username", "role", "email", "pending_email")}
        result["csrf_token"] = user["csrf_token"]
    return result


def _translate(exc):
    return HTTPException(exc.status_code, str(exc))


def _ip(request: Request):
    return request.client.host if request.client else "unknown"


def _secure_cookie(request: Request):
    return get_settings().session_secure_cookie if _mode() == "multiuser" else request.url.scheme == "https"


def _set_session(request: Request, response: Response, token: str):
    accounts.logout(request.cookies.get(accounts.COOKIE_NAME))
    response.set_cookie(accounts.COOKIE_NAME, token, httponly=True, samesite="strict", secure=_secure_cookie(request),
                        max_age=get_settings().session_lifetime_hours * 3600, path="/")
    response.headers["Cache-Control"] = "no-store"


def _delete_session(request: Request, response: Response):
    response.delete_cookie(accounts.COOKIE_NAME, path="/", secure=_secure_cookie(request), httponly=True, samesite="strict")
    response.headers["Cache-Control"] = "no-store"


@router.get("/session")
def session(request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    user = _current_user()
    result = _session(user)
    if not user and request.cookies.get(accounts.COOKIE_NAME):
        # Keep this boundary until explicit logout or login; automatically
        # discarding a stale cookie could open the local workspace on refresh.
        result["session_expired"] = True
    return result


@router.post("/login")
def login(req: LoginRequest, request: Request, response: Response):
    try:
        token, user = accounts.login(req.username, req.password, _ip(request))
    except accounts.AccountError as exc:
        raise _translate(exc) from exc
    _set_session(request, response, token)
    return _session(user)


@router.post("/register", status_code=201)
def register(req: RegisterRequest, request: Request, response: Response):
    if not get_settings().registration_enabled:
        raise HTTPException(403, "此部署未开放注册，请联系维护者创建账号")
    try:
        email = accounts.normalize_email(req.email) if req.email else None
        if email and not accounts.email_recovery_enabled():
            raise accounts.AccountError("此站点尚未启用邮件服务，请暂不填写邮箱")
        user = accounts.register(req.username, req.password, _ip(request))
    except accounts.AccountError as exc:
        raise _translate(exc) from exc
    message = "账号已创建。建议在账号设置中生成并保存恢复码。"
    if email:
        # Account creation remains successful if delivery fails; users can retry
        # verification from settings without being stranded with a taken username.
        try:
            delivered = accounts.bind_email(user["id"], email, req.password, _ip(request))
            message = "账号已创建，验证邮件已发送。请验证邮箱后使用邮件找回密码。" if delivered else "账号已创建，但验证邮件暂未发出。请稍后在账号设置中重新发送。"
        except accounts.AccountError:
            message = "账号已创建，但邮箱暂未绑定。请在账号设置中检查邮箱并重新绑定。"
    token, user = accounts.session_for_new_user(user["id"])
    _set_session(request, response, token)
    return {**_session(user), "message": message}


@router.post("/logout")
def logout(request: Request, response: Response):
    # Expired sessions can still clear their cookie through this idempotent route.
    accounts.logout(request.cookies.get(accounts.COOKIE_NAME))
    _delete_session(request, response)
    return {"ok": True}


@router.post("/password")
def password(req: PasswordRequest, request: Request, response: Response):
    user = _require_user()
    try:
        accounts.change_password(user["id"], req.current_password, req.new_password, ip=_ip(request))
    except accounts.AccountError as exc:
        raise _translate(exc) from exc
    _delete_session(request, response)
    return {"ok": True, "requires_login": True}


@router.get("/users")
def users():
    _require_user(admin=True)
    return {"items": accounts.list_users()}


@router.post("/users", status_code=201)
def create_user(req: CreateUserRequest):
    _require_user(admin=True)
    try:
        return accounts.create_user(req.username, req.password, req.role)
    except accounts.AccountError as exc:
        raise _translate(exc) from exc


@router.patch("/users/{user_id}")
def disable_user(user_id: str, req: DisableRequest):
    actor = _require_user(admin=True)
    try:
        return accounts.set_disabled(user_id, req.disabled, actor_id=actor["id"])
    except accounts.AccountError as exc:
        raise _translate(exc) from exc


@router.post("/recovery-code")
def recovery_code(req: RecoveryIssue, request: Request, response: Response):
    user = _require_user()
    try:
        code = accounts.issue_recovery_code(user["id"], req.password, _ip(request))
    except accounts.AccountError as exc:
        raise _translate(exc) from exc
    response.headers["Cache-Control"] = "no-store"
    return {"code": code}


@router.post("/recover")
def recover(req: RecoveryReset, request: Request, response: Response):
    try:
        accounts.recover_with_code(req.username, req.code, req.new_password, _ip(request))
    except accounts.AccountError as exc:
        raise _translate(exc) from exc
    _delete_session(request, response)
    return {"ok": True, "requires_login": True, "message": "密码已更新，全部会话已退出。请重新登录并生成新的恢复码。"}


@router.get("/sessions")
def active_sessions(request: Request, response: Response):
    user = _require_user()
    response.headers["Cache-Control"] = "no-store"
    return {"items": accounts.active_sessions(user["id"], request.cookies.get(accounts.COOKIE_NAME, ""))}


@router.post("/sessions/revoke-others")
def revoke_others(request: Request):
    user = _require_user()
    accounts.revoke_other_sessions(user["id"], request.cookies.get(accounts.COOKIE_NAME, ""))
    return {"ok": True}


@router.post("/email")
def bind_email(req: BindEmailRequest, request: Request):
    user = _require_user()
    try:
        delivered = accounts.bind_email(user["id"], req.email, req.password, _ip(request))
    except accounts.AccountError as exc:
        raise _translate(exc) from exc
    if not delivered:
        raise HTTPException(503, "验证邮件暂未发送成功，请稍后重试或联系管理员")
    return {"ok": True, "message": "验证邮件已发送，请在 60 分钟内打开邮件链接。原邮箱在新邮箱验证前仍然有效。"}


@router.post("/verify-email")
def verify_email(req: TokenRequest, request: Request):
    try:
        accounts.verify_email(req.token, _ip(request))
    except accounts.AccountError as exc:
        raise _translate(exc) from exc
    return {"ok": True, "message": "邮箱已验证，现在可以使用此邮箱登录或找回密码。"}


@router.post("/forgot-password")
def forgot_password(req: EmailRequest, request: Request, background: BackgroundTasks):
    try:
        delivery = accounts.prepare_password_reset(req.email, _ip(request))
    except accounts.AccountError as exc:
        raise _translate(exc) from exc
    # SMTP happens after the response, so account existence cannot be inferred
    # from mail server latency or a recipient-specific transport error.
    if delivery:
        background.add_task(accounts.send_account_email, *delivery)
    return {"ok": True, "message": "如果该邮箱已验证并绑定有效账号，你将收到重置邮件。请检查收件箱及垃圾邮件，或稍后重试。"}


@router.post("/reset-password")
def reset_password(req: ResetPasswordRequest, request: Request, response: Response):
    try:
        accounts.reset_password_with_token(req.token, req.new_password, _ip(request))
    except accounts.AccountError as exc:
        raise _translate(exc) from exc
    _delete_session(request, response)
    return {"ok": True, "requires_login": True, "message": "密码已更新，全部会话已退出。请使用新密码登录。"}
