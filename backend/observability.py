"""Observability layer — telemetry (ADR 0036) + audit log (ADR 0009).

Hot-path callers don't touch the DB directly; they call `record_metric()` /
`record_audit()`, which buffer rows and flush in a background batch every
~2 seconds (or when the buffer hits 100 entries). This keeps the WS detection
loop's median frame latency well under 1 ms even when telemetry is verbose.

Reads are direct SELECTs — buffers don't matter for the /api/metrics or
/api/audit endpoints because the buffer flushes well within a query latency.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import threading
import time
import uuid
from contextlib import suppress
from datetime import datetime
from typing import Any, Optional

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from .db import AuditLog, Metric, SessionLocal

# ---------- structlog (JSON output, request_id correlated) ----------

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    cache_logger_on_first_use=True,
)
logger = structlog.get_logger("live-qr")


# ---------- buffered writes ----------

_metric_buffer: list[dict] = []
_audit_buffer: list[dict] = []
_buf_lock = threading.Lock()
FLUSH_INTERVAL_S = 2.0
FLUSH_TRIGGER_LEN = 100


def record_metric(name: str, value: float, **tags: Any) -> None:
    with _buf_lock:
        _metric_buffer.append({
            "t": datetime.utcnow(),
            "name": name,
            "value": float(value),
            "tags_json": json.dumps(tags) if tags else None,
        })
        if len(_metric_buffer) >= FLUSH_TRIGGER_LEN:
            _flush_metrics_locked()


def record_audit(
    *,
    actor_token_hash: Optional[str],
    method: str,
    path: str,
    query: Optional[str],
    status_code: int,
    request_id: Optional[str],
    body_summary: Optional[str],
    duration_ms: Optional[int],
) -> None:
    with _buf_lock:
        _audit_buffer.append({
            "t": datetime.utcnow(),
            "actor_token_hash": actor_token_hash,
            "method": method,
            "path": path[:400],
            "query": (query or None) and str(query)[:800],
            "status_code": int(status_code),
            "request_id": request_id,
            "body_summary": body_summary,
            "duration_ms": duration_ms,
        })
        if len(_audit_buffer) >= FLUSH_TRIGGER_LEN:
            _flush_audit_locked()


def _flush_metrics_locked() -> None:
    if not _metric_buffer:
        return
    rows, _metric_buffer[:] = list(_metric_buffer), []
    db = SessionLocal()
    try:
        db.bulk_insert_mappings(Metric, rows)
        db.commit()
    except Exception:
        logger.exception("metric flush failed", count=len(rows))
        db.rollback()
    finally:
        db.close()


def _flush_audit_locked() -> None:
    if not _audit_buffer:
        return
    rows, _audit_buffer[:] = list(_audit_buffer), []
    db = SessionLocal()
    try:
        db.bulk_insert_mappings(AuditLog, rows)
        db.commit()
    except Exception:
        logger.exception("audit flush failed", count=len(rows))
        db.rollback()
    finally:
        db.close()


def flush_now() -> None:
    """Public flush — used by tests + the background timer."""
    with _buf_lock:
        _flush_metrics_locked()
        _flush_audit_locked()


_flush_task: Optional[asyncio.Task] = None


async def _flush_loop() -> None:
    while True:
        await asyncio.sleep(FLUSH_INTERVAL_S)
        with suppress(Exception):
            flush_now()


def start_background_flush() -> None:
    """Start the periodic flush task. Call from FastAPI startup."""
    global _flush_task
    if _flush_task is not None and not _flush_task.done():
        return
    loop = asyncio.get_event_loop()
    _flush_task = loop.create_task(_flush_loop())


# ---------- audit middleware ----------

# Routes we DON'T audit (every-frame WS, observe stream, static files).
_AUDIT_EXEMPT_PREFIXES = ("/static/", "/api/markers/0/badge", "/ws/", "/api/feasibility")


class AuditMiddleware(BaseHTTPMiddleware):
    """Logs every successful POST/PUT/PATCH/DELETE under /api/*. Adds an
    X-Request-Id header to every response so logs and audit rows correlate."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex[:12]
        # Attach to context for structlog correlation.
        structlog.contextvars.bind_contextvars(request_id=request_id)
        start = time.monotonic()
        try:
            response: Response = await call_next(request)
        finally:
            structlog.contextvars.clear_contextvars()

        # Respond with the id so client errors can be cross-referenced.
        response.headers["X-Request-Id"] = request_id

        # Audit only the methods + path patterns we care about.
        method = request.method
        path = request.url.path
        if (
            method in ("POST", "PUT", "PATCH", "DELETE")
            and path.startswith("/api/")
            and not any(path.startswith(p) for p in _AUDIT_EXEMPT_PREFIXES)
            and 200 <= response.status_code < 400
        ):
            duration_ms = int((time.monotonic() - start) * 1000)
            actor = request.headers.get("Authorization") or ""
            actor_hash = _hash_token(actor) if actor else None
            record_audit(
                actor_token_hash=actor_hash,
                method=method,
                path=path,
                query=str(request.url.query) if request.url.query else None,
                status_code=response.status_code,
                request_id=request_id,
                body_summary=None,  # bodies often binary or huge — skip for now.
                duration_ms=duration_ms,
            )
            # Also drop a request-latency metric.
            record_metric(
                "http.request.duration_ms",
                duration_ms,
                method=method,
                path_prefix=_path_prefix(path),
                status=response.status_code,
            )
        return response


def _hash_token(authorization_header: str) -> str:
    """Last 8 hex chars of the SHA-256 of the bearer token (for audit only)."""
    h = hashlib.sha256(authorization_header.encode("utf-8")).hexdigest()
    return h[-8:]


def _path_prefix(path: str) -> str:
    """Coarse-grained route bucket: /api/markers/3/badge → /api/markers/_/badge."""
    parts = path.split("/")
    bucket = []
    for p in parts:
        if p.isdigit():
            bucket.append("_")
        else:
            bucket.append(p)
    return "/".join(bucket)
