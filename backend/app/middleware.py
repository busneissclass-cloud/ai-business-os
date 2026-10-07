"""Correlation IDs + request audit trail. PII redacted before logging."""
import time
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from .db import SessionLocal, utcnow
from .models import AuditLog
from .security import redact_pii


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        cid = request.headers.get("X-Correlation-ID") or uuid.uuid4().hex
        request.state.correlation_id = cid
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = cid
        return response


class AuditMiddleware(BaseHTTPMiddleware):
    SKIP = {"/v1/health"}

    async def dispatch(self, request: Request, call_next):
        start = time.monotonic()
        response = await call_next(request)
        if request.url.path not in self.SKIP:
            latency_ms = int((time.monotonic() - start) * 1000)
            try:
                db = SessionLocal()
                db.add(AuditLog(
                    agent="api-gateway",
                    action=f"{request.method} {redact_pii(request.url.path)}",
                    result="ok" if response.status_code < 400 else "error",
                    latency_ms=latency_ms,
                    correlation_id=getattr(request.state, "correlation_id", None),
                    ts=utcnow(),
                ))
                db.commit()
            except Exception:
                pass
            finally:
                try:
                    db.close()
                except Exception:
                    pass
        return response
