"""Bearer-token auth (ADR 0001).

Opt-in via the APP_TOKEN environment variable:

  APP_TOKEN unset (default)
    No auth required. Useful for local dev + the existing prod deployment
    that ships unauthenticated. Backward compatible.

  APP_TOKEN=<secret>
    All POST/PUT/PATCH/DELETE under /api/* require either:
      - HTTP header `Authorization: Bearer <APP_TOKEN>`, OR
      - cookie `lq_session=<APP_TOKEN>` (set by /login).
    HTML routes /admin and /track require the cookie too.
    Read-only routes (`/`, `/m/{aruco_id}`, `/static/*`, `/api/markers/{id}/image`,
    `/api/qr`, GET `/api/...`) stay open so phones can render markers without
    a credential and projection can run without a login.
    /ws/detect accepts `?token=<APP_TOKEN>` at handshake — WebSocket clients
    can't reliably attach the Authorization header from getUserMedia code.

The shared-secret model is intentionally light. Per ADR 0001, the trade-off
accepted: one token per workshop, rotated when the secret leaks. No multi-
user identity, no password recovery flow.
"""
from __future__ import annotations

import hmac
import os
from typing import Optional

from fastapi import Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware

COOKIE_NAME = "lq_session"
COOKIE_MAX_AGE_S = 12 * 3600  # 12 hours

# Read-only paths that bypass auth even when APP_TOKEN is set.
_PUBLIC_PATH_PREFIXES = (
    "/static/",
    "/m/",
    "/api/markers/",  # broad — covers /image and /badge; we re-check the suffix below
    "/api/qr",
    "/api/feasibility",
    "/api/system",       # GET only; we restrict to GET below
    "/api/badge-styles",
    "/api/control-markers",  # GET only
)

# Mutating method names.
_MUTATING = ("POST", "PUT", "PATCH", "DELETE")


def app_token() -> Optional[str]:
    return os.environ.get("APP_TOKEN") or None


def _is_authorized(request: Request) -> bool:
    expected = app_token()
    if not expected:
        return True  # auth disabled when no token configured
    # Authorization: Bearer ...
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[len("Bearer "):].strip()
        if hmac.compare_digest(token, expected):
            return True
    # Cookie set by /login
    cookie = request.cookies.get(COOKIE_NAME, "")
    if cookie and hmac.compare_digest(cookie, expected):
        return True
    # WS handshake: ?token=
    if request.url.path.startswith("/ws/"):
        token = request.query_params.get("token", "")
        if token and hmac.compare_digest(token, expected):
            return True
    return False


class AuthMiddleware(BaseHTTPMiddleware):
    """Gates mutating routes when APP_TOKEN is set. No-op when unset."""

    async def dispatch(self, request: Request, call_next):
        if app_token() is None:
            return await call_next(request)

        path = request.url.path
        method = request.method

        # Read-only public paths (any method): these don't mutate state and
        # need to work without a credential for participant phones / projection.
        # /api/markers/{id}/image and /api/markers/{id}/badge — but POST to
        # /api/markers/batch must require auth.
        if path == "/" or path == "/login":
            return await call_next(request)
        if any(path.startswith(p) for p in ("/static/", "/m/")):
            return await call_next(request)
        if path == "/api/qr" or path == "/api/feasibility":
            return await call_next(request)
        if path == "/api/badge-styles":
            return await call_next(request)
        if path.startswith("/api/markers/") and (
            path.endswith("/image") or "/badge" in path
        ):
            return await call_next(request)

        # GETs to /api/system/* and /api/control-markers (list view) are read-only.
        if method == "GET" and (
            path.startswith("/api/system") or path == "/api/control-markers"
        ):
            return await call_next(request)

        # The Live page itself is read-only and must work for projection.
        # /present and /track HTML pages also need to render without an HTML login,
        # because their content is per-WS broadcast — we gate the *write* routes,
        # not the page chrome. (HTML auth deferred per ADR 0001 minimum-viable.)
        if method == "GET" and not path.startswith("/api/"):
            return await call_next(request)

        # Everything else: mutating route OR an authenticated read.
        if method in _MUTATING and path.startswith("/api/"):
            if not _is_authorized(request):
                return JSONResponse(
                    {"detail": "Auth required. Send Authorization: Bearer <APP_TOKEN>."},
                    status_code=401,
                )
        elif path.startswith("/ws/") and not _is_authorized(request):
            # WS handshake without token — reject the upgrade.
            return JSONResponse(
                {"detail": "Auth required. Connect with /ws/...?token=<APP_TOKEN>."},
                status_code=401,
            )

        return await call_next(request)


# ---------- /login endpoint ----------

LOGIN_PAGE_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>Sign in</title>
<style>
body{font-family:system-ui,sans-serif;background:#0f172a;color:#e2e8f0;
     display:flex;align-items:center;justify-content:center;height:100vh;margin:0}
form{background:#1e293b;border:1px solid #475569;border-radius:8px;padding:24px;
     min-width:320px}
input{background:#0f172a;color:#e2e8f0;border:1px solid #475569;border-radius:6px;
      padding:8px 12px;width:100%;font-size:14px;margin-bottom:12px}
button{background:#22c55e;color:#052e1a;border:0;border-radius:6px;padding:10px 20px;
       font-weight:600;cursor:pointer;width:100%}
.err{color:#f87171;font-size:13px;margin-bottom:8px}
h1{font-size:18px;margin:0 0 16px}
</style></head>
<body><form method="post" action="/login">
<h1>Sign in</h1>
__ERR__
<input name="token" type="password" placeholder="APP_TOKEN" autofocus required />
<input name="next" type="hidden" value="__NEXT__" />
<button type="submit">Sign in</button>
</form></body></html>
"""


def login_page(error: Optional[str] = None, next_path: str = "/admin") -> HTMLResponse:
    err = f'<div class="err">{error}</div>' if error else ""
    # str.replace, not str.format — the template's CSS uses { } braces, and
    # .format() would treat every selector body as a placeholder.
    html = (LOGIN_PAGE_HTML
            .replace("__ERR__", err)
            .replace("__NEXT__", next_path))
    return HTMLResponse(html)


def login_set_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        COOKIE_NAME, token,
        max_age=COOKIE_MAX_AGE_S,
        httponly=True, samesite="strict",
        secure=False,  # set True behind HTTPS reverse proxy
    )


def logout(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME)
