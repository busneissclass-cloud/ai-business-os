"""Trust boundary API: scan untrusted content, review security events."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import desc
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import SecurityEvent
from ..trust import scan_external_content

router = APIRouter()


class ScanRequest(BaseModel):
    source: str  # e.g. "job_post:123", "scraped_site:example.com"
    text: str


@router.post("/security/scan")
def scan(req: ScanRequest, db: Session = Depends(get_db)):
    return scan_external_content(db, req.source, req.text)


@router.get("/security/events")
def events(limit: int = 50, db: Session = Depends(get_db)):
    rows = db.query(SecurityEvent).order_by(desc(SecurityEvent.ts)).limit(limit).all()
    return [{"id": e.id, "ts": e.ts.isoformat(), "category": e.category,
             "severity": e.severity, "source": e.source,
             "action": e.action_taken, "reviewed": e.reviewed,
             "detail": e.detail} for e in rows]
