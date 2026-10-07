"""Contact verification API. Honest states, never 'guaranteed'."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db, utcnow
from ..models import ContactVerification
from ..verify import verify_email, verify_phone

router = APIRouter()


class VerifyIn(BaseModel):
    kind: str  # email | phone
    value: str
    lead_id: str | None = None


@router.post("/contacts/verify")
def verify(body: VerifyIn, db: Session = Depends(get_db)):
    if body.kind == "email":
        result = verify_email(body.value)
    elif body.kind == "phone":
        result = verify_phone(body.value)
    else:
        raise HTTPException(400, "kind must be email|phone")
    db.add(ContactVerification(
        lead_id=body.lead_id, kind=body.kind, value=result["value"],
        status=result["status"], confidence=result["confidence"],
        checks=result["checks"], verified_at=utcnow()))
    db.commit()
    return result
