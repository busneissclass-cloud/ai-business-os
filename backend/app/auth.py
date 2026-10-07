"""API key gate. Every /v1/* route (except /v1/health) requires X-API-Key.
Fail-closed: production refuses to boot without API_KEY. Constant-time compare."""
import hmac

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .config import settings

OPEN_PATHS = {"/", "/v1/health", "/dashboard", "/docs", "/openapi.json", "/redoc"}


class ApiKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.url.path in OPEN_PATHS:
            return await call_next(request)
        expected = settings.API_KEY
        if not expected:
            if settings.ENV == "production":
                return JSONResponse(
                    {"detail": "API_KEY not configured"}, status_code=503)
            return await call_next(request)  # dev mode: open, with warning at startup
        provided = request.headers.get("X-API-Key", "")
        if not provided or not hmac.compare_digest(provided, expected):
            return JSONResponse(
                {"detail": "invalid or missing API key"}, status_code=401)
        return await call_next(request)


def assert_production_ready() -> None:
    if settings.ENV == "production" and not settings.API_KEY:
        raise RuntimeError("API_KEY must be set when ENV=production — refusing to boot")
    if not settings.API_KEY:
        print("WARNING: API_KEY not set — API is open (dev mode only)")
