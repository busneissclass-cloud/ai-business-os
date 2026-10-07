"""Dashboard support endpoints: list views + routine trigger (M1)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc
from sqlalchemy.orm import Session

from ..agents.registry import run_agent
from ..db import get_db
from ..models import Approval, Lead, OutreachDraft

router = APIRouter()


@router.get("/leads")
def list_leads(limit: int = 50, db: Session = Depends(get_db)):
    rows = (db.query(Lead).order_by(desc(Lead.lead_score))
            .limit(min(limit, 200)).all())
    return [{"id": l.id, "business_name": l.business_name, "status": l.status,
             "tier": l.tier, "lead_score": l.lead_score,
             "buying_intent_score": l.buying_intent_score,
             "buying_intent_level": l.buying_intent_level,
             "website": l.website, "email": l.email, "phone": l.phone}
            for l in rows]


@router.get("/approvals")
def list_approvals(status: str = "PENDING", limit: int = 50,
                   db: Session = Depends(get_db)):
    q = db.query(Approval)
    if status != "ALL":
        q = q.filter(Approval.status == status)
    rows = q.order_by(desc(Approval.created_at)).limit(min(limit, 200)).all()
    return [{"id": a.id, "action": a.action, "status": a.status,
             "requested_agent": a.requested_agent,
             "risk_level": a.risk_level, "payload": a.payload,
             "created_at": a.created_at.isoformat() if a.created_at else None}
            for a in rows]


@router.get("/drafts")
def list_drafts(limit: int = 20, db: Session = Depends(get_db)):
    rows = (db.query(OutreachDraft).order_by(desc(OutreachDraft.created_at))
            .limit(min(limit, 100)).all())
    out = []
    for d in rows:
        lead = db.get(Lead, d.lead_id)
        out.append({"id": d.id, "lead_id": d.lead_id,
                    "lead_name": lead.business_name if lead else "?",
                    "channel": d.channel, "variant": d.variant,
                    "subject": d.subject, "body": d.body[:500],
                    "status": d.status, "approval_id": d.approval_id})
    return out


@router.get("/queue")
def get_queue(limit: int = 10, db: Session = Depends(get_db)):
    return run_agent(db, "prioritize", "build_queue", {"limit": limit})


@router.post("/routine/run")
def run_routine():
    from worker.celery_app import celery
    task = celery.send_task("worker.tasks.daily_routine")
    return {"task_id": task.id, "state": "QUEUED"}


@router.get("/routine/status/{task_id}")
def routine_status(task_id: str):
    from worker.celery_app import celery
    r = celery.AsyncResult(task_id)
    info = r.info if isinstance(r.info, dict) else {"raw": str(r.info)}
    return {"task_id": task_id, "state": r.state, "info": info}
