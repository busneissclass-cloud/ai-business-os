"""Minimal lead CRUD for M0.5 (full CRM in M1)."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Lead

router = APIRouter()


class LeadIn(BaseModel):
    business_name: str
    tier: str | None = None
    lead_score: int | None = None
    website: str | None = None
    email: str | None = None
    phone: str | None = None
    notes: str | None = None


@router.post("/leads")
def create_lead(body: LeadIn, db: Session = Depends(get_db)):
    lead = Lead(business_name=body.business_name, tier=body.tier,
                lead_score=body.lead_score, website=body.website,
                email=body.email, phone=body.phone, notes=body.notes)
    db.add(lead)
    db.commit()
    return {"id": lead.id, "business_name": lead.business_name}


@router.get("/leads/{lead_id}")
def get_lead(lead_id: str, db: Session = Depends(get_db)):
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(404, "unknown lead")
    return {"id": lead.id, "business_name": lead.business_name,
            "status": lead.status, "tier": lead.tier,
            "buying_intent_score": lead.buying_intent_score,
            "buying_intent_level": lead.buying_intent_level}
