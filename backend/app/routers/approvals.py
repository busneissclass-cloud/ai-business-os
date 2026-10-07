"""Hardened approval lifecycle.
An approval is valid ONLY for the exact approved payload_hash.
Payload change after approval -> INVALID, must re-request."""
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import as_utc, get_db, utcnow
from ..deps import correlation_id
from ..models import Approval, AuditLog, IdempotencyKey
from ..security import payload_hash, sign_approval, verify_approval_signature

router = APIRouter()
POLICY_VERSION = "v1"


class ApprovalCreate(BaseModel):
    action: str
    payload: dict
    requested_by: str = "owner"
    requested_agent: str | None = None
    risk_level: str = "MEDIUM"
    autonomy_level: str = "L2"
    expires_in_hours: int = 24


class ApprovalDecide(BaseModel):
    decision: str  # approved | rejected
    decided_by: str = "owner"


class ApprovalExecute(BaseModel):
    payload: dict  # must hash-match the approved payload


def _audit(db, cid, agent, action, decision, result="ok"):
    db.add(AuditLog(agent=agent, action=action, decision=decision,
                    result=result, correlation_id=cid, ts=utcnow()))


@router.post("/approvals")
def create_approval(body: ApprovalCreate, request: Request, db: Session = Depends(get_db)):
    cid = correlation_id(request)
    phash = payload_hash(body.payload)
    ap = Approval(
        action=body.action, payload=body.payload, payload_hash=phash,
        requested_by=body.requested_by, requested_agent=body.requested_agent,
        status="PENDING", risk_level=body.risk_level, autonomy_level=body.autonomy_level,
        policy_version=POLICY_VERSION,
        expires_at=utcnow() + timedelta(hours=body.expires_in_hours),
        idempotency_key=uuid.uuid4().hex,
    )
    db.add(ap)
    _audit(db, cid, "approvals", f"CREATE {ap.id}", f"action={body.action}")
    db.commit()
    return {"id": ap.id, "status": ap.status, "payload_hash": phash,
            "idempotency_key": ap.idempotency_key}


@router.post("/approvals/{approval_id}/decide")
def decide_approval(approval_id: str, body: ApprovalDecide, request: Request,
                    db: Session = Depends(get_db)):
    cid = correlation_id(request)
    ap = db.get(Approval, approval_id)
    if not ap:
        raise HTTPException(404, "unknown approval")
    if ap.status != "PENDING":
        raise HTTPException(409, f"cannot decide from status {ap.status}")
    if ap.expires_at and as_utc(ap.expires_at) < utcnow():
        ap.status = "EXPIRED"
        _audit(db, cid, "approvals", f"EXPIRE {ap.id}", "expired before decision")
        db.commit()
        raise HTTPException(410, "approval expired")
    if body.decision == "approved":
        ap.status = "APPROVED"
        ap.approval_signature = sign_approval(ap.id, ap.payload_hash)
    elif body.decision == "rejected":
        ap.status = "REJECTED"
    else:
        raise HTTPException(400, "decision must be approved|rejected")
    ap.decided_by = body.decided_by
    ap.decided_at = utcnow()
    _audit(db, cid, "approvals", f"DECIDE {ap.id}", f"{body.decision} by {body.decided_by}")
    db.commit()
    return {"id": ap.id, "status": ap.status}


@router.post("/approvals/{approval_id}/revoke")
def revoke_approval(approval_id: str, request: Request, db: Session = Depends(get_db)):
    cid = correlation_id(request)
    ap = db.get(Approval, approval_id)
    if not ap:
        raise HTTPException(404, "unknown approval")
    if ap.status not in ("PENDING", "APPROVED"):
        raise HTTPException(409, f"cannot revoke from status {ap.status}")
    ap.status = "REVOKED"
    _audit(db, cid, "approvals", f"REVOKE {ap.id}", "revoked by owner")
    db.commit()
    return {"id": ap.id, "status": ap.status}


@router.post("/approvals/{approval_id}/execute")
def execute_approval(approval_id: str, body: ApprovalExecute, request: Request,
                     db: Session = Depends(get_db)):
    """Execute ONLY if: APPROVED + unexpired + signature valid + payload hash matches.
    Idempotent via the approval's idempotency_key."""
    cid = correlation_id(request)
    ap = db.get(Approval, approval_id)
    if not ap:
        raise HTTPException(404, "unknown approval")
    if ap.status != "APPROVED":
        raise HTTPException(409, f"cannot execute from status {ap.status}")
    if ap.expires_at and as_utc(ap.expires_at) < utcnow():
        ap.status = "EXPIRED"
        db.commit()
        raise HTTPException(410, "approval expired")
    if not verify_approval_signature(ap.id, ap.payload_hash, ap.approval_signature):
        _audit(db, cid, "approvals", f"EXECUTE {ap.id}", "signature invalid", result="blocked")
        db.commit()
        raise HTTPException(403, "approval signature invalid")

    # THE hard rule: payload must hash-match exactly.
    if payload_hash(body.payload) != ap.payload_hash:
        _audit(db, cid, "approvals", f"EXECUTE {ap.id}",
               "payload hash mismatch — approval invalidated", result="blocked")
        db.commit()
        raise HTTPException(409, "payload changed after approval — approval invalid, re-request required")

    # Idempotency: never execute twice.
    existing = db.get(IdempotencyKey, ap.idempotency_key)
    if existing and existing.status == "SUCCEEDED":
        return {"id": ap.id, "status": ap.status, "execution": "already-executed",
                "result": ap.execution_result}
    if not existing:
        existing = IdempotencyKey(key=ap.idempotency_key, action=ap.action,
                                 actor=ap.requested_by, request_hash=ap.payload_hash,
                                 status="IN_PROGRESS")
        db.add(existing)

    ap.status = "EXECUTING"
    db.commit()

    # M0: no real side effects yet — the gate itself is what's being proven.
    ap.execution_result = {"note": "M0: execution gate verified; no side effects wired yet",
                           "payload_hash": ap.payload_hash}
    ap.execution_status = "SUCCEEDED"
    ap.status = "EXECUTED"
    existing.status = "SUCCEEDED"
    existing.result_reference = ap.id
    _audit(db, cid, "approvals", f"EXECUTE {ap.id}", "executed", result="ok")
    db.commit()
    return {"id": ap.id, "status": ap.status, "execution": "executed",
            "result": ap.execution_result}


@router.get("/approvals/{approval_id}")
def get_approval(approval_id: str, db: Session = Depends(get_db)):
    ap = db.get(Approval, approval_id)
    if not ap:
        raise HTTPException(404, "unknown approval")
    return {"id": ap.id, "action": ap.action, "status": ap.status,
            "payload_hash": ap.payload_hash, "risk_level": ap.risk_level,
            "expires_at": ap.expires_at.isoformat() if ap.expires_at else None}
