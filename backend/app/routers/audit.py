"""Audit log: READ ONLY. Append-only by design — no update/delete endpoints exist."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AuditLog

router = APIRouter()


@router.get("/audit-log")
def list_audit(limit: int = Query(50, le=500), agent: str | None = None,
               db: Session = Depends(get_db)):
    q = db.query(AuditLog).order_by(desc(AuditLog.ts)).limit(limit)
    if agent:
        q = q.filter(AuditLog.agent == agent)
    rows = q.all()
    return [{"id": r.id, "ts": r.ts.isoformat(), "agent": r.agent, "action": r.action,
             "decision": r.decision, "result": r.result,
             "correlation_id": r.correlation_id} for r in rows]
