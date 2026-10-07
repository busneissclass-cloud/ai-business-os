"""AI Business OS — M0 foundation API."""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .db import SessionLocal, init_db
from .middleware import AuditMiddleware, CorrelationIdMiddleware
from .permissions import seed_permissions
from .routers import (agents, approvals, audit, brain, freshness, health, intent,
                      killswitch, leads, nba, permissions, security, settings,
                      verify)
from .agents.registry import seed_all


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    with SessionLocal() as db:
        seed_all(db)
    yield


app = FastAPI(title="AI Business OS", version="0.1.0-m0", lifespan=lifespan)

app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(AuditMiddleware)


app.include_router(health.router, prefix="/v1", tags=["health"])
app.include_router(killswitch.router, prefix="/v1", tags=["kill-switch"])
app.include_router(settings.router, prefix="/v1", tags=["settings"])
app.include_router(approvals.router, prefix="/v1", tags=["approvals"])
app.include_router(audit.router, prefix="/v1", tags=["audit"])
app.include_router(permissions.router, prefix="/v1", tags=["permissions"])
app.include_router(security.router, prefix="/v1", tags=["security"])
app.include_router(intent.router, prefix="/v1", tags=["intent"])
app.include_router(freshness.router, prefix="/v1", tags=["freshness"])
app.include_router(verify.router, prefix="/v1", tags=["verify"])
app.include_router(nba.router, prefix="/v1", tags=["nba"])
app.include_router(brain.router, prefix="/v1", tags=["brain"])
app.include_router(leads.router, prefix="/v1", tags=["leads"])
app.include_router(agents.router, prefix="/v1", tags=["agents"])


@app.get("/")
def root():
    return {"service": "ai-business-os", "version": "0.1.0-m0", "docs": "/docs"}
