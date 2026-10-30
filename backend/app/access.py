"""Opt-in account boundary around every API, including downloads and jobs."""

from urllib.parse import urlparse

from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import get_settings
from app.tenancy import user_scope


class AccountBoundary:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        from app.accounts import authenticate, verify_csrf
        request = Request(scope, receive=receive)
        path = request.url.path

        async def reject(status, message):
            response = JSONResponse({"detail": message}, status_code=status,
                                    headers={"Cache-Control": "no-store"})
            await response(scope, receive, send)

        if path in ("/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"):
            return await reject(404, "页面不存在")

        user = authenticate(request.cookies.get("atlas_session", ""))
        local = get_settings().access_mode == "local"
        public = path == "/health" or path == "/api/auth/session" or (
            path in ("/api/auth/login", "/api/auth/register", "/api/auth/recover", "/api/auth/forgot-password",
                     "/api/auth/reset-password", "/api/auth/verify-email") and request.method == "POST"
        )
        # A stale cookie must not prevent the browser from clearing it. Valid
        # sessions still require CSRF for logout, alongside the Origin check.
        if path == "/api/auth/logout" and request.method == "POST" and user is None:
            public = True
        if not public and user is None and (not local or get_settings().require_login or request.cookies.get("atlas_session")):
            return await reject(401, "请先登录；会话可能已过期或账号已停用")

        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            if origin:
                parsed = urlparse(origin)
                if parsed.scheme != request.url.scheme or parsed.netloc.lower() != request.headers.get("host", "").lower():
                    return await reject(403, "请求来源不合法，请从工作台重新操作")
            if not public and (user or not local) and not verify_csrf(user, request.headers.get("x-atlas-csrf", "")):
                return await reject(403, "会话校验失败，请刷新页面后重试")

        admin_paths = ("/api/review", "/api/learning/quality", "/api/learning/sources",
                       "/api/learning/relations", "/api/learning/feedback")
        if (user or not local) and any(path == prefix or path.startswith(prefix + "/") for prefix in admin_paths):
            if not user or user["role"] != "admin":
                return await reject(403, "此功能需要管理员权限")

        if not local and (path == "/api/collect" or path.startswith("/api/collect/") or (
            path.startswith("/api/papers/") and path.endswith("/fetch-fulltext")
        ) or (
            path.startswith("/api/projects/") and path.endswith("/sources/link")
        )):
            return await reject(503, "受控多人试用暂未开放远程采集，请直接上传 PDF")

        if not local and path == "/api/papers/upload":
            return await reject(409, "多人试用请使用后台上传解析入口 /api/papers/upload-async")

        if request.method not in ("GET", "HEAD", "OPTIONS"):
            source_upload = path.startswith('/api/projects/') and path.endswith('/sources') and len(path.strip('/').split('/')) == 4
            limit = (50 * 1024 * 1024 if local else get_settings().user_pdf_max_bytes) + 65536 if source_upload or path in ("/api/papers/upload-async", "/api/papers/upload") else 3 * 1024 * 1024 if path == "/api/preferences/avatar" else 1024 * 1024
            chunks = bytearray()
            async for chunk in request.stream():
                chunks.extend(chunk)
                if len(chunks) > limit:
                    return await reject(413, "请求超过当前大小限制")
            body = bytes(chunks)
            delivered = False
            original_receive = receive

            async def replay_body():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": body, "more_body": False}
                return await original_receive()

            receive = replay_body

        async def private_send(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers = [(k, v) for k, v in headers if k.lower() != b"cache-control"]
                headers.extend([(b"cache-control", b"no-store"), (b"vary", b"Cookie")])
                message = {**message, "headers": headers}
            await send(message)

        with user_scope(user):
            await self.app(scope, receive, private_send)
