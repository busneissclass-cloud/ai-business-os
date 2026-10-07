"""Buying intent API: record signals, compute timing scores."""
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db, utcnow
from ..intent import compute_buying_intent
from ..models import BuyingIntentSignal

router = APIRouter()


class SignalIn(BaseModel):
    lead_id: str
    signal_type: str
    signal_source: str = "manual"
    signal_strength: int = 3
    evidence_url: str | None = None
    evidence_text: str | None = None
    confidence: str = "INFERENCE"
    ttl_days: int = 60  # decay window


@router.post("/signals")
def add_signal(body: SignalIn, db: Session = Depends(get_db)):
    s = BuyingIntentSignal(
        lead_id=body.lead_id, signal_type=body.signal_type,
        signal_source=body.signal_source, signal_strength=body.signal_strength,
        evidence_url=body.evidence_url, evidence_text=body.evidence_text,
        confidence=body.confidence,
        expires_at=utcnow() + timedelta(days=body.ttl_days))
    db.add(s)
    db.commit()
    return compute_buying_intent(db, body.lead_id)


@router.get("/leads/{lead_id}/buying-intent")
def get_intent(lead_id: str, db: Session = Depends(get_db)):
    out = compute_buying_intent(db, lead_id)
    if "error" in out:
        raise HTTPException(404, out["error"])
    return out
