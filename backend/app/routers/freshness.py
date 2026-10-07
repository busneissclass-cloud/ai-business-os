"""Freshness API: per-field verification status, recompute, revalidate."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..freshness import compute_freshness, mark_field_verified

router = APIRouter()


class VerifyField(BaseModel):
    field: str
    source: str = "manual"


@router.get("/leads/{lead_id}/freshness")
def get_freshness(lead_id: str, db: Session = Depends(get_db)):
    out = compute_freshness(db, lead_id)
    if "error" in out:
        raise HTTPException(404, out["error"])
    return out


@router.post("/leads/{lead_id}/revalidate")
def revalidate(lead_id: str, body: VerifyField, db: Session = Depends(get_db)):
    mark_field_verified(db, lead_id, body.field, body.source)
    return compute_freshness(db, lead_id)
